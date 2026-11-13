"""
trino_client.py - Ket noi Trino va tra ket qua truy van ve dang pandas DataFrame.

Moi ung dung dung mot ten user rieng (streamlit, groq-agent) de phan biet truy van trong Trino UI.
"""
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import trino

from common import config


def connect(user: str):
    return trino.dbapi.connect(
        host=config.TRINO_HOST,
        port=config.TRINO_PORT,
        user=user,
        catalog=config.TRINO_CATALOG,
        schema=config.GOLD_SCHEMA,
        session_properties={"query_max_run_time": config.QUERY_MAX_RUN_TIME},
    )


def _to_plain(value):
    """Decimal -> float de pandas/plotly tinh toan va ve bieu do duoc."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def run_query(sql: str, user: str = "streamlit", max_rows: int | None = None) -> pd.DataFrame:
    """Chay mot cau SELECT tren Trino. max_rows: chi lay toi da so dong nay (chan ket qua qua lon)."""
    conn = connect(user)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
        cols = [c[0] for c in cur.description]
        if max_rows:
            try:
                cur.cancel()  # khong doc tiep phan con lai cua ket qua
            except Exception:  # noqa: BLE001 - truy van da ket thuc thi khong can huy
                pass
    finally:
        conn.close()
    df = pd.DataFrame([[_to_plain(v) for v in r] for r in rows], columns=cols)
    return df


def to_jsonable(df: pd.DataFrame) -> list:
    """Chuyen DataFrame thanh list dong co the dua vao JSON (ngay thang -> chuoi ISO)."""
    out = []
    for row in df.itertuples(index=False):
        out.append([v.isoformat() if isinstance(v, (date, datetime)) else
                    (None if (isinstance(v, float) and pd.isna(v)) else v) for v in row])
    return out
