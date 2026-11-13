"""
lakehouse_common.py - Hang so va ham dung chung cho 6 DAG (khong phai DAG)

* docker_exec(): dung lenh "docker exec" vao container spark-ingest / dbt (Airflow chi la bo dieu phoi,
  viec nang do container chuyen biet thuc hien)
* trino_rows() / lakehouse_snapshot(): truy van Trino de kiem tra ket qua sau moi buoc
* SERVICES / run_check(): danh sach va ham kiem tra suc khoe cac container
"""
import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from datetime import timedelta

import pendulum
from airflow.exceptions import AirflowFailException, AirflowSkipException

TZ = pendulum.timezone("Asia/Ho_Chi_Minh")
START_DATE = pendulum.datetime(2026, 1, 1, tz=TZ)

DEFAULT_ARGS = {
    "owner": "lakehouse",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

SPARK_CONTAINER = "spark-ingest"
DBT_CONTAINER = "dbt"


def docker_exec(container: str, command: str) -> str:
    return f"docker exec {container} {command}"


# ---------------------------------------------------------------- Trino
def trino_rows(sql: str) -> list:
    import trino

    conn = trino.dbapi.connect(
        host=os.environ.get("TRINO_HOST", "trino"),
        port=int(os.environ.get("TRINO_PORT", "8080")),
        user="airflow", catalog="iceberg",
    )
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()


def scalar(sql: str):
    return trino_rows(sql)[0][0]


def lakehouse_snapshot() -> dict:
    """Anh chup so lieu 3 tang - dung de doi chieu truoc/sau khi chay pipeline."""
    return {
        "bronze_rows": int(scalar("SELECT count(*) FROM iceberg.bronze.online_retail")),
        "silver_sales_rows": int(scalar("SELECT count(*) FROM iceberg.silver.stg_sales")),
        "gold_fact_rows": int(scalar("SELECT count(*) FROM iceberg.gold.fact_sales")),
        "wide_days": int(scalar("SELECT count(*) FROM iceberg.gold.wide_daily_sales")),
        "wide_last_day": str(scalar("SELECT max(sale_date) FROM iceberg.gold.wide_daily_sales")),
        "revenue_silver": float(scalar("SELECT sum(line_revenue) FROM iceberg.silver.stg_sales")),
        "revenue_fact": float(scalar("SELECT sum(line_revenue) FROM iceberg.gold.fact_sales")),
        "revenue_wide": float(scalar("SELECT sum(total_revenue) FROM iceberg.gold.wide_daily_sales")),
    }


def assert_revenue_reconciled(snap: dict, tolerance: float = 0.01) -> None:
    """Tong doanh thu phai khop giua stg_sales, fact_sales va wide_daily_sales."""
    values = (snap["revenue_silver"], snap["revenue_fact"], snap["revenue_wide"])
    if max(values) - min(values) > tolerance:
        raise AirflowFailException(
            f"Doanh thu khong khop giua cac tang: silver={values[0]:,.3f} fact={values[1]:,.3f} "
            f"wide={values[2]:,.3f}")


# ---------------------------------------------------------------- Kiem tra suc khoe dich vu
# kind: tcp | http | trino | container. optional=True: container chua trien khai thi bo qua (skipped)
SERVICES = [
    {"id": "postgres-db", "kind": "tcp", "host": "postgres-db", "port": 5432},
    {"id": "minio", "kind": "http", "url": "http://minio:9000/minio/health/live"},
    {"id": "hive-metastore", "kind": "tcp", "host": "hive-metastore", "port": 9083},
    {"id": "spark-thrift-server", "kind": "tcp", "host": "spark-thrift-server", "port": 10000},
    {"id": "trino", "kind": "trino", "url": "http://trino:8080/v1/info"},
    {"id": "airflow-webserver", "kind": "http", "url": "http://airflow-webserver:8080/health"},
    {"id": "spark-ingest", "kind": "container"},
    {"id": "dbt", "kind": "container"},
    {"id": "streamlit", "kind": "container", "optional": True},
    {"id": "groq-agent", "kind": "container", "optional": True},
]
CORE_SERVICE_IDS = ["postgres-db", "minio", "hive-metastore", "spark-thrift-server", "trino",
                    "spark-ingest", "dbt"]


def _http_get(url: str, timeout: int = 5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:       # server tra loi (vd 403/404) = dang song
        return exc.code, b""


def run_check(service: dict) -> str:
    """Nem exception neu dich vu khong khoe; tra ve mo ta ngan khi khoe."""
    kind, name = service["kind"], service["id"]
    if kind == "tcp":
        socket.create_connection((service["host"], service["port"]), timeout=5).close()
        return f"{name}: {service['host']}:{service['port']} mo cong"
    if kind == "http":
        status, _ = _http_get(service["url"])
        if status >= 500:
            raise RuntimeError(f"{name}: HTTP {status}")
        return f"{name}: HTTP {status}"
    if kind == "trino":
        status, body = _http_get(service["url"])
        if status != 200 or json.loads(body).get("starting", True):
            raise RuntimeError(f"{name}: chua san sang (HTTP {status})")
        return f"{name}: san sang"
    if kind == "container":
        proc = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name],
                              capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            if service.get("optional"):
                raise AirflowSkipException(f"{name}: chua duoc trien khai (bo qua)")
            raise RuntimeError(f"{name}: khong tim thay container")
        if proc.stdout.strip() != "true":
            raise RuntimeError(f"{name}: container khong chay")
        return f"{name}: container dang chay"
    raise ValueError(f"kind khong hop le: {kind}")


def check_core_services() -> None:
    """Dung lam cong chan dau pipeline: loi neu bat ky dich vu loi cot loi nao khong khoe."""
    failures = []
    for svc in SERVICES:
        if svc["id"] not in CORE_SERVICE_IDS:
            continue
        try:
            print("OK  ", run_check(svc))
        except Exception as exc:  # noqa: BLE001
            print("LOI ", svc["id"], exc)
            failures.append(f"{svc['id']}: {exc}")
    if failures:
        raise AirflowFailException("Dich vu chua san sang - " + "; ".join(failures))
