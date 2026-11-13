"""
train.py - Pipeline huan luyen mo hinh du bao doanh thu theo ngay bang Facebook Prophet (muc 3.8)

Cac buoc:
  1. Trich xuat iceberg.gold.wide_daily_sales qua Trino -> chuan hoa (ds, y)
  2. Chia Train/Test theo thoi gian (80/20)
  3. Mo hinh Baseline: Prophet tham so mac dinh (+ seasonal naive de doi chung)
  4. Tinh chinh sieu tham so bang Grid Search + cross-validation theo thoi gian tren tap Train
  5. Huan luyen Tuned Prophet tren tap Train, danh gia tren tap Test (MAE, RMSE, MAPE, sMAPE, WAPE)
  6. Kiem tra tieu chi nghiem thu nghiep vu
  7. Huan luyen lai tren toan bo du lieu, du bao 30 ngay (khoang tin cay 80%)
  8. Dong goi: model.pkl, metrics.json, forecast.csv, bieu do -> MinIO Model Registry

Cach chay (trong container airflow-* hoac tren may host):
    python /opt/ml/train.py                         # day du, ghi len MinIO
    python /opt/ml/train.py --quick                 # luoi tham so nho, chay nhanh de kiem tra
    python train.py --source csv --csv wide.csv --out-dir ./out    # offline, khong can Trino/MinIO
"""
import argparse
import io
import itertools
import json
import logging
import os
import pickle
import sys
import time
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from prophet import Prophet  # noqa: E402
from prophet.diagnostics import cross_validation  # noqa: E402
from prophet.serialize import model_to_json  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import data  # noqa: E402
import metrics  # noqa: E402

logging.getLogger("cmdstanpy").disabled = True      # moi lan fit in 2 dong INFO, lam nhieu log Airflow
# Prophet canh bao lap lai moi lan fit khi bat yearly_seasonality voi < 2 nam du lieu; giu lai thanh
# ghi chu mot lan trong metrics.json ("notes") thay vi in 24+ lan trong log
logging.getLogger("prophet").setLevel(logging.ERROR)


# ---------------------------------------------------------------- Mo hinh
def build_model(params=None) -> Prophet:
    """Baseline = khong truyen params (Prophet mac dinh)."""
    return Prophet(interval_width=config.INTERVAL_WIDTH, **(params or {}))


def predict(model: Prophet, ds) -> pd.DataFrame:
    """Du bao va cat ve 0: doanh thu khong the am."""
    fc = model.predict(pd.DataFrame({"ds": pd.to_datetime(ds)}))
    for col in ("yhat", "yhat_lower", "yhat_upper"):
        fc[col] = fc[col].clip(lower=0)
    return fc


def seasonal_naive(train_y: np.ndarray, n: int) -> np.ndarray:
    """Lap lai 7 ngay cuoi cua tap train - moc so sanh don gian nhat cho chuoi co chu ky tuan."""
    last_week = train_y[-7:]
    return np.array([last_week[i % 7] for i in range(n)])


# ---------------------------------------------------------------- Grid Search
def grid_search(train: pd.DataFrame, grid: dict) -> list:
    keys = list(grid)
    combos = [dict(zip(keys, values)) for values in itertools.product(*grid.values())]
    horizon = config.CV_HORIZON_DAYS
    initial = min(config.CV_INITIAL_DAYS, max(60, len(train) - 3 * horizon))
    print(f"[4/8] Grid Search: {len(combos)} to hop tham so, cross-validation initial={initial}d "
          f"period={config.CV_PERIOD_DAYS}d horizon={horizon}d", flush=True)

    results = []
    for i, params in enumerate(combos, 1):
        t0 = time.time()
        try:
            model = build_model(params)
            model.fit(train[["ds", "y"]])
            cv = cross_validation(
                model, initial=f"{initial} days", period=f"{config.CV_PERIOD_DAYS} days",
                horizon=f"{horizon} days", disable_tqdm=True,
            )
            y, yhat = cv["y"].to_numpy(), cv["yhat"].clip(lower=0).to_numpy()
            row = {"params": params, "cv_wape": metrics.wape(y, yhat),
                   "cv_rmse": metrics.rmse(y, yhat), "cv_folds": int(cv["cutoff"].nunique())}
        except Exception as exc:  # mot to hop loi khong lam hong ca luoi
            row = {"params": params, "cv_wape": float("inf"), "cv_rmse": float("inf"),
                   "cv_folds": 0, "error": str(exc)[:200]}
        results.append(row)
        print(f"      [{i:>2}/{len(combos)}] cv_wape={row['cv_wape']:.4f} cv_rmse={row['cv_rmse']:,.0f} "
              f"({time.time() - t0:.1f}s) {params}", flush=True)

    results.sort(key=lambda r: r["cv_wape"])
    if not np.isfinite(results[0]["cv_wape"]):
        raise RuntimeError("Tat ca to hop tham so deu loi khi cross-validation")
    return results


# ---------------------------------------------------------------- Bieu do
def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def plot_test(test_pred: pd.DataFrame) -> bytes:
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(test_pred["ds"], test_pred["y"], color="#222222", lw=1.4, label="Thực tế")
    ax.plot(test_pred["ds"], test_pred["baseline_yhat"], color="#e08a1e", lw=1.2, label="Baseline Prophet")
    ax.plot(test_pred["ds"], test_pred["tuned_yhat"], color="#1f77b4", lw=1.4, label="Tuned Prophet")
    ax.fill_between(test_pred["ds"], test_pred["tuned_yhat_lower"], test_pred["tuned_yhat_upper"],
                    color="#1f77b4", alpha=0.15, label="Khoảng tin cậy 80%")
    ax.set_title("Doanh thu theo ngày trên tập Test")
    ax.set_ylabel("Doanh thu (£)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    return _png(fig)


def plot_forecast(history: pd.DataFrame, forecast: pd.DataFrame) -> bytes:
    hist = history.tail(90)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(hist["ds"], hist["y"], color="#222222", lw=1.3, label="Lịch sử (90 ngày cuối)")
    ax.plot(forecast["ds"], forecast["yhat"], color="#1f77b4", lw=1.6, label=f"Dự báo {len(forecast)} ngày")
    ax.fill_between(forecast["ds"], forecast["yhat_lower"], forecast["yhat_upper"],
                    color="#1f77b4", alpha=0.18, label="Khoảng tin cậy 80%")
    ax.set_title(f"Dự báo doanh thu {len(forecast)} ngày tiếp theo")
    ax.set_ylabel("Doanh thu (£)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    return _png(fig)


# ---------------------------------------------------------------- Tien ich
def clean(obj):
    """Doi kieu numpy/pandas sang kieu JSON; NaN, Inf -> None."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    return obj


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------- Pipeline
def run(args) -> dict:
    version = args.version or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = time.time()
    print(f"=== Prophet pipeline - version {version} ===", flush=True)

    # 1. Trich xuat va chuan hoa
    raw = data.load_from_csv(args.csv) if args.source == "csv" else data.load_from_trino()
    df = data.prepare(raw)
    print(f"[1/8] Doc {len(df)} ngay: {df['ds'].min().date()} -> {df['ds'].max().date()}, "
          f"{int(df['is_trading_day'].sum())} ngay co giao dich", flush=True)

    # 2. Chia Train/Test theo thoi gian
    train, test = data.time_split(df, config.TEST_RATIO)
    print(f"[2/8] Train {len(train)} ngay (den {train['ds'].max().date()}), "
          f"Test {len(test)} ngay (tu {test['ds'].min().date()})", flush=True)

    # 3. Baseline
    base_model = build_model()
    base_model.fit(train[["ds", "y"]])
    base_fc = predict(base_model, test["ds"])
    naive_yhat = seasonal_naive(train["y"].to_numpy(), len(test))
    y_test = test["y"].to_numpy()
    base_m = metrics.evaluate(y_test, base_fc["yhat"].to_numpy())
    naive_m = metrics.evaluate(y_test, naive_yhat)
    print(f"[3/8] Baseline Prophet WAPE={base_m['wape']:.4f} RMSE={base_m['rmse']:,.0f} | "
          f"Seasonal naive WAPE={naive_m['wape']:.4f}", flush=True)

    # 4. Grid Search tren tap Train
    grid = config.PARAM_GRID_QUICK if args.quick else config.PARAM_GRID
    grid_results = grid_search(train, grid)
    best = grid_results[0]
    print(f"      -> Tham so tot nhat: {best['params']} (cv_wape={best['cv_wape']:.4f})", flush=True)

    # 5. Tuned Prophet: huan luyen tren Train, danh gia tren Test
    tuned_model = build_model(best["params"])
    tuned_model.fit(train[["ds", "y"]])
    tuned_fc = predict(tuned_model, test["ds"])
    tuned_m = metrics.evaluate(y_test, tuned_fc["yhat"].to_numpy())
    print(f"[5/8] Tuned Prophet WAPE={tuned_m['wape']:.4f} RMSE={tuned_m['rmse']:,.0f} "
          f"MAE={tuned_m['mae']:,.0f}", flush=True)

    # 6. Nghiem thu nghiep vu
    checks = {
        "tuned_beats_baseline_wape": bool(tuned_m["wape"] < base_m["wape"]),
        "tuned_beats_seasonal_naive_wape": bool(tuned_m["wape"] < naive_m["wape"]),
        "tuned_wape_within_limit": bool(tuned_m["wape"] <= config.ACCEPT_MAX_WAPE),
    }
    passed = all(checks.values())
    print(f"[6/8] Nghiem thu: {'DAT' if passed else 'KHONG DAT'} {checks}", flush=True)

    # 7. Huan luyen lai tren toan bo du lieu va du bao
    final_model = build_model(best["params"])
    final_model.fit(df[["ds", "y"]])
    future_ds = pd.date_range(df["ds"].max() + pd.Timedelta(days=1), periods=config.FORECAST_DAYS, freq="D")
    fc = predict(final_model, future_ds)
    forecast = fc[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    print(f"[7/8] Du bao {config.FORECAST_DAYS} ngay: {future_ds[0].date()} -> {future_ds[-1].date()}, "
          f"tong yhat={forecast['yhat'].sum():,.0f}", flush=True)

    test_pred = pd.DataFrame({
        "ds": test["ds"].to_numpy(), "y": y_test,
        "baseline_yhat": base_fc["yhat"].to_numpy(), "naive_yhat": naive_yhat,
        "tuned_yhat": tuned_fc["yhat"].to_numpy(),
        "tuned_yhat_lower": tuned_fc["yhat_lower"].to_numpy(),
        "tuned_yhat_upper": tuned_fc["yhat_upper"].to_numpy(),
    })

    notes = []
    if best["params"].get("yearly_seasonality") and len(train) < 730:
        notes.append(f"yearly_seasonality duoc uoc luong tu {len(train)} ngay (< 2 nam) nen mua vu nam "
                     "chi dua tren mot chu ky - ket qua phu thuoc nhieu vao mua cao diem cuoi nam")
    if args.quick:
        notes.append("che do --quick: luoi tham so rut gon, khong dung de nghiem thu")

    doc = clean({
        "model_name": config.MODEL_NAME,
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_seconds": round(time.time() - started, 1),
        "mode": "quick" if args.quick else "full",
        "data": {
            "source": f"{config.TRINO_CATALOG}.{config.GOLD_SCHEMA}.{config.WIDE_TABLE}" if args.source == "trino"
                      else args.csv,
            "rows": len(df), "start": df["ds"].min(), "end": df["ds"].max(),
            "trading_days": int(df["is_trading_day"].sum()),
            "train_rows": len(train), "train_end": train["ds"].max(),
            "test_rows": len(test), "test_start": test["ds"].min(),
            "split": f"{int((1 - config.TEST_RATIO) * 100)}/{int(config.TEST_RATIO * 100)} theo thoi gian",
        },
        "baseline_prophet": base_m,
        "seasonal_naive": naive_m,
        "tuned_prophet": tuned_m,
        "best_params": best["params"],
        "best_cv_wape": best["cv_wape"],
        "grid_results": grid_results,
        "improvement_vs_baseline": {
            "wape_pct": (base_m["wape"] - tuned_m["wape"]) / base_m["wape"] * 100,
            "rmse_pct": (base_m["rmse"] - tuned_m["rmse"]) / base_m["rmse"] * 100,
            "mae_pct": (base_m["mae"] - tuned_m["mae"]) / base_m["mae"] * 100,
        },
        "acceptance": {"max_wape": config.ACCEPT_MAX_WAPE, "checks": checks, "passed": passed},
        "forecast": {
            "horizon_days": config.FORECAST_DAYS, "interval_width": config.INTERVAL_WIDTH,
            "start": future_ds[0], "end": future_ds[-1],
            "total_yhat": forecast["yhat"].sum(),
            "total_lower": forecast["yhat_lower"].sum(), "total_upper": forecast["yhat_upper"].sum(),
        },
        "final_model_trained_on": "train+test (toan bo du lieu)",
        "notes": notes,
        "promoted": False,
    })

    # 8. Dong goi
    artifacts = {
        "model.pkl": (pickle.dumps(final_model), "application/octet-stream"),
        "model.json": (model_to_json(final_model).encode("utf-8"), "application/json"),
        "forecast.csv": (csv_bytes(forecast), "text/csv"),
        "test_predictions.csv": (csv_bytes(test_pred), "text/csv"),
        "test_comparison.png": (plot_test(test_pred), "image/png"),
        "forecast.png": (plot_forecast(df, forecast), "image/png"),
    }

    if args.out_dir:
        out = os.path.join(args.out_dir, version)
        os.makedirs(out, exist_ok=True)
        for name, (blob, _) in artifacts.items():
            with open(os.path.join(out, name), "wb") as f:
                f.write(blob)
        with open(os.path.join(out, "metrics.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"[8/8] Da luu artifact vao thu muc {out}", flush=True)
    else:
        import registry

        doc["promoted"] = passed
        for name, (blob, ctype) in artifacts.items():
            registry.put_bytes(registry.version_key(version, name), blob, ctype)
        registry.put_json(registry.version_key(version, "metrics.json"), doc)
        if passed:
            registry.promote(version, doc)
        print(f"[8/8] Da ghi s3://{config.BUCKET}/{config.REGISTRY_PREFIX}/{version}/ "
              f"({'da promote lam latest' if passed else 'KHONG promote vi chua dat nghiem thu'})", flush=True)

    print(f"=== Xong sau {time.time() - started:.0f}s ===", flush=True)
    return doc


def main():
    parser = argparse.ArgumentParser(description="Huan luyen Prophet du bao doanh thu")
    parser.add_argument("--source", choices=["trino", "csv"], default="trino")
    parser.add_argument("--csv", help="duong dan CSV (khi --source csv)")
    parser.add_argument("--version", help="ma phien ban (mac dinh: thoi gian UTC hien tai)")
    parser.add_argument("--quick", action="store_true", help="luoi tham so nho, chay nhanh")
    parser.add_argument("--out-dir", help="ghi artifact ra thu muc local thay vi MinIO")
    args = parser.parse_args()
    if args.source == "csv" and not args.csv:
        parser.error("--source csv can --csv <duong dan>")
    run(args)


if __name__ == "__main__":
    main()
