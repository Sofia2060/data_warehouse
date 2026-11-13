"""
data.py - Trich xuat bang phang tu Gold Layer va chuan hoa ve dinh dang dau vao cua Prophet (ds, y)
"""
import pandas as pd

import config


def load_from_trino() -> pd.DataFrame:
    """Doc iceberg.gold.wide_daily_sales qua Trino."""
    import trino

    conn = trino.dbapi.connect(
        host=config.TRINO_HOST, port=config.TRINO_PORT, user=config.TRINO_USER,
        catalog=config.TRINO_CATALOG, schema=config.GOLD_SCHEMA,
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT sale_date, total_revenue, is_trading_day "
        f"FROM {config.TRINO_CATALOG}.{config.GOLD_SCHEMA}.{config.WIDE_TABLE} ORDER BY sale_date"
    )
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    return pd.DataFrame(rows, columns=cols)


def load_from_csv(path: str) -> pd.DataFrame:
    """Doc ban xuat CSV cua wide_daily_sales (dung khi chay offline / kiem thu)."""
    return pd.read_csv(path)


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Doi ten cot ve (ds, y) va kiem tra tinh toan ven cua chuoi thoi gian.

    Tra ve DataFrame gom: ds (datetime), y (float, doanh thu ngay), is_trading_day (bool).
    """
    df = pd.DataFrame({
        "ds": pd.to_datetime(raw["sale_date"]),
        "y": pd.to_numeric(raw["total_revenue"]).astype(float),
    })
    if "is_trading_day" in raw.columns:
        df["is_trading_day"] = raw["is_trading_day"].astype(bool)
    else:
        df["is_trading_day"] = df["y"] > 0
    df = df.sort_values("ds").reset_index(drop=True)

    if df["y"].isna().any():
        raise ValueError("Cot doanh thu con gia tri NULL")
    if (df["y"] < 0).any():
        raise ValueError("Doanh thu am - kiem tra lai tang Silver (don huy phai nam ngoai total_revenue)")
    if df["ds"].duplicated().any():
        raise ValueError("Ngay bi trung lap trong wide_daily_sales")
    expected_days = (df["ds"].iloc[-1] - df["ds"].iloc[0]).days + 1
    if expected_days != len(df):
        raise ValueError(f"Chuoi ngay khong lien tuc: co {len(df)} dong, can {expected_days}")
    return df


def time_split(df: pd.DataFrame, test_ratio: float):
    """Chia theo thoi gian (khong xao tron): phan dau = train, phan cuoi = test."""
    n_train = int(len(df) * (1 - test_ratio))
    return df.iloc[:n_train].copy(), df.iloc[n_train:].copy()
