"""Chay API groq-agent that (agent.api) nhung Trino thay bang DuckDB; Groq tro toi may chu gia lap qua GROQ_BASE_URL."""
import sys

import uvicorn

import duck_backend
from common import trino_client

trino_client.run_query = duck_backend.run_query       # core.ask goi trino_client.run_query luc chay

from agent.api import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8000, log_level="warning")
