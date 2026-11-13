"""
config.py - Cau hinh dung chung cho pipeline du bao doanh thu bang Prophet (muc 3.8)

Mac dinh dung cho moi truong Docker (container airflow-*). Khi chay tren may host:
    TRINO_HOST=localhost TRINO_PORT=8090 MINIO_ENDPOINT=http://localhost:9000 python ml/train.py
"""
import os

# ---------------------------------------------------------------- Nguon du lieu (Gold Layer)
TRINO_HOST = os.getenv("TRINO_HOST", "trino")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8080"))
TRINO_USER = os.getenv("TRINO_USER", "ml-pipeline")
TRINO_CATALOG = "iceberg"
GOLD_SCHEMA = "gold"
WIDE_TABLE = "wide_daily_sales"

# ---------------------------------------------------------------- Model Registry tren MinIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")
BUCKET = os.getenv("MODEL_BUCKET", "warehouse")
MODEL_NAME = "prophet_revenue"
REGISTRY_PREFIX = f"models/{MODEL_NAME}"          # s3://warehouse/models/prophet_revenue/<version>/...
LATEST_KEY = f"{REGISTRY_PREFIX}/latest.json"     # con tro toi phien ban dang duoc trien khai

# ---------------------------------------------------------------- Chia du lieu va du bao
TEST_RATIO = 0.2            # 80% dau de huan luyen, 20% cuoi de kiem tra (chia theo thoi gian)
FORECAST_DAYS = 30
INTERVAL_WIDTH = 0.8        # khoang tin cay 80%
SEED = 42

# ---------------------------------------------------------------- Grid Search (cross-validation tren tap train)
CV_INITIAL_DAYS = 300       # cua so huan luyen toi thieu cua fold dau tien
CV_PERIOD_DAYS = 30         # khoang cach giua hai moc cat (cutoff)
CV_HORIZON_DAYS = 30        # do dai du bao moi fold (bang horizon thuc te cua bai toan)

PARAM_GRID = {
    "changepoint_prior_scale": [0.01, 0.05, 0.5],
    "seasonality_prior_scale": [1.0, 10.0],
    "seasonality_mode": ["additive", "multiplicative"],
    "yearly_seasonality": [False, True],
}
PARAM_GRID_QUICK = {        # che do --quick: kiem tra nhanh pipeline, khong dung de nghiem thu
    "changepoint_prior_scale": [0.05, 0.5],
    "seasonality_mode": ["additive", "multiplicative"],
}

# ---------------------------------------------------------------- Tieu chi nghiem thu nghiep vu
# Mo hinh chi duoc "promote" (ghi vao latest.json) khi dat TAT CA tieu chi sau tren tap test:
#   1. WAPE cua Tuned Prophet thap hon Baseline Prophet
#   2. WAPE cua Tuned Prophet thap hon mo hinh naive theo tuan (seasonal naive)
#   3. WAPE cua Tuned Prophet khong vuot nguong toi da duoi day
# WAPE = tong |sai so| / tong doanh thu thuc te - on dinh khi co ngay doanh thu = 0 (MAPE khong tinh duoc).
ACCEPT_MAX_WAPE = float(os.getenv("ACCEPT_MAX_WAPE", "0.40"))
