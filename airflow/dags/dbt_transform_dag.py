"""
dbt_transform_dag - Chay cac bai test dbt va chuyen doi Bronze -> Silver -> Gold.

dbt_deps -> silver_run -> silver_test -> gold_run -> gold_test -> reconcile_revenue -> dbt_docs_generate
  * silver_*: 4 model lam sach (stg_retail_transactions, stg_sales, stg_cancellations, stg_rejected_records)
  * gold_*  : Star Schema (fact_sales + 4 dim) va wide_daily_sales
  * test    : unique / not_null / relationships / equal_rowcount trong schema.yml - test loi thi DAG dung
  * reconcile_revenue: tong doanh thu stg_sales = fact_sales = wide_daily_sales
  * dbt_docs_generate: sinh lai catalog + do thi Data Lineage

Tham so full_refresh=true: dung lai bang Silver incremental (stg_sales) tu dau. Can khi du lieu Bronze
bi nap lai hoac bi xoa (vd purge du lieu gia lap), vi stg_sales chi them dong moi, khong xoa dong cu.
"""
from datetime import timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from lakehouse_common import (DBT_CONTAINER, DEFAULT_ARGS, START_DATE, assert_revenue_reconciled,
                              docker_exec, lakehouse_snapshot)

DBT = docker_exec(DBT_CONTAINER, "dbt")
FULL_REFRESH = "{{ '--full-refresh' if (params.full_refresh | string | lower) == 'true' else '' }}"


def _reconcile(**_):
    snap = lakehouse_snapshot()
    print(snap)
    assert_revenue_reconciled(snap)
    print(f"Doanh thu khop o 3 noi: {snap['revenue_fact']:,.3f}")


with DAG(
    dag_id="dbt_transform_dag",
    description="Test dbt va chuyen doi Silver -> Gold",
    schedule=None,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={"full_refresh": Param(False, type="boolean", description="Dung lai Silver incremental tu dau")},
    tags=["silver", "gold", "dbt"],
    doc_md=__doc__,
) as dag:
    dbt_deps = BashOperator(task_id="dbt_deps", bash_command=f"{DBT} deps")
    silver_run = BashOperator(task_id="silver_run", bash_command=f"{DBT} run --select silver {FULL_REFRESH}",
                              execution_timeout=timedelta(minutes=30))
    # cautious: chi chay test co MOI bang cha thuoc Silver; neu khong, test equal_rowcount cua fact_sales
    # (tham chieu stg_sales) bi keo vao khi Gold chua ton tai (he thong moi dung)
    silver_test = BashOperator(task_id="silver_test",
                               bash_command=f"{DBT} test --select silver --indirect-selection=cautious")
    gold_run = BashOperator(task_id="gold_run", bash_command=f"{DBT} run --select gold",
                            execution_timeout=timedelta(minutes=30))
    gold_test = BashOperator(task_id="gold_test", bash_command=f"{DBT} test --select gold")
    reconcile_revenue = PythonOperator(task_id="reconcile_revenue", python_callable=_reconcile)
    dbt_docs_generate = BashOperator(task_id="dbt_docs_generate", bash_command=f"{DBT} docs generate")

    (dbt_deps >> silver_run >> silver_test >> gold_run >> gold_test
     >> reconcile_revenue >> dbt_docs_generate)
