"""Chay Dashboard that (dashboard/streamlit_app.py) voi Trino thay bang DuckDB va MinIO thay bang moto.
    streamlit run tests/demo_dashboard.py   (PYTHONPATH=app:tests)"""
import os

import duck_backend
from common import config, trino_client

trino_client.run_query = duck_backend.run_query
config.MINIO_ENDPOINT = os.environ.get("DEMO_S3", "http://127.0.0.1:5078")
config.AGENT_URL = os.environ.get("DEMO_AGENT", "http://127.0.0.1:8000")

from dashboard import streamlit_app  # noqa: E402

streamlit_app.main()
