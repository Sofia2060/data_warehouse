"""Thay Trino bang DuckDB (Gold gia lap) khi kiem thu offline: dich SQL Trino -> DuckDB bang sqlglot."""
import os
from decimal import Decimal

import duckdb
import pandas as pd
import sqlglot

DB = os.environ.get("MOCK_GOLD", os.path.join(os.path.dirname(__file__), "mock_gold.duckdb"))
QUERIES = []   # ghi lai cac cau SQL da chay (de kiem tra)


def run_query(sql: str, user: str = "streamlit", max_rows=None) -> pd.DataFrame:
    QUERIES.append((user, sql))
    duck_sql = sqlglot.transpile(sql, read="trino", write="duckdb")[0]
    con = duckdb.connect(DB, read_only=True)
    try:
        con.execute("USE gold")
        cur = con.execute(duck_sql)
        rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
        cols = [d[0] for d in cur.description]
    finally:
        con.close()
    return pd.DataFrame([[float(v) if isinstance(v, Decimal) else v for v in r] for r in rows], columns=cols)
