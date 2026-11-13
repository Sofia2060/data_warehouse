"""
config.py - Cau hinh dung chung cho tang ung dung (muc 3.9): streamlit va groq-agent.

Gia tri mac dinh dung trong mang Docker "lakehouse_net". Khi chay tren may host:
    TRINO_HOST=localhost TRINO_PORT=8090 MINIO_ENDPOINT=http://localhost:9000 AGENT_URL=http://localhost:8000
"""
import os

# ---------------------------------------------------------------- Trino (Serving Layer, muc 3.6)
TRINO_HOST = os.getenv("TRINO_HOST", "trino")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8080"))
TRINO_CATALOG = "iceberg"
GOLD_SCHEMA = "gold"
QUERY_MAX_RUN_TIME = os.getenv("QUERY_MAX_RUN_TIME", "60s")   # Trino tu huy truy van qua thoi gian nay

# ---------------------------------------------------------------- Model Registry tren MinIO (muc 3.8)
# Cung quy uoc voi ml/config.py va ml/registry.py cua pipeline Prophet
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")
MODEL_BUCKET = os.getenv("MODEL_BUCKET", "warehouse")
MODEL_NAME = "prophet_revenue"
REGISTRY_PREFIX = f"models/{MODEL_NAME}"           # s3://warehouse/models/prophet_revenue/<version>/...
LATEST_KEY = f"{REGISTRY_PREFIX}/latest.json"      # con tro toi phien ban dang trien khai
DEFAULT_MAX_WAPE = 0.40                            # chi dung khi metrics.json khong ghi nguong

# ---------------------------------------------------------------- Groq LLM Agent
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Groq da ngung llama-3.3-70b-versatile tu 16/08/2026 (console.groq.com/docs/deprecations);
# mo hinh thay the duoc khuyen nghi la openai/gpt-oss-120b. Doi mo hinh bang bien GROQ_MODEL.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
AGENT_URL = os.getenv("AGENT_URL", "http://groq-agent:8000")
AGENT_MAX_ROWS = int(os.getenv("AGENT_MAX_ROWS", "200"))        # so dong toi da Agent tra ve
AGENT_MAX_ATTEMPTS = int(os.getenv("AGENT_MAX_ATTEMPTS", "3"))  # 1 lan dau + 2 lan tu sua loi
AGENT_ROWS_TO_LLM = 30                                          # so dong gui lai LLM de dien giai
