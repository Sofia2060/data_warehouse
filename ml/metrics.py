"""
metrics.py - Cac chi so danh gia mo hinh du bao doanh thu

Bang wide_daily_sales co ngay doanh thu = 0 (khong giao dich), nen MAPE chi tinh tren ngay co doanh thu.
WAPE va sMAPE khong bi loi chia cho 0 nen duoc dung lam chi so chinh de so sanh.
"""
import numpy as np


def mae(y, yhat) -> float:
    return float(np.mean(np.abs(y - yhat)))


def rmse(y, yhat) -> float:
    return float(np.sqrt(np.mean((y - yhat) ** 2)))


def mape(y, yhat) -> float:
    """Sai so phan tram trung binh - chi tinh tren cac ngay co doanh thu thuc te > 0."""
    mask = y > 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y[mask] - yhat[mask]) / y[mask])))


def smape(y, yhat) -> float:
    denom = np.abs(y) + np.abs(yhat)
    ratio = np.where(denom == 0, 0.0, 2 * np.abs(y - yhat) / np.where(denom == 0, 1, denom))
    return float(np.mean(ratio))


def wape(y, yhat) -> float:
    """Weighted APE = tong |sai so| / tong doanh thu thuc te."""
    total = np.sum(np.abs(y))
    return float(np.sum(np.abs(y - yhat)) / total) if total > 0 else float("nan")


def evaluate(y, yhat) -> dict:
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    return {
        "mae": mae(y, yhat),
        "rmse": rmse(y, yhat),
        "mape_trading_days": mape(y, yhat),
        "smape": smape(y, yhat),
        "wape": wape(y, yhat),
    }
