"""
synthetic_ingest_dag - Gia lap nap them du lieu moi de kiem thu cap nhat gia tang (incremental) end-to-end.

snapshot_before -> spark_synthetic -> trigger_dbt_transform -> verify_after
  * snapshot_before     : chup so dong / doanh thu Bronze, Silver, Gold truoc khi nap
  * spark_synthetic     : spark-submit synthetic_ingest.py - sinh don hang moi (ngay sau ngay cuoi cung)
                          cung mot ti le dong "ban" (don huy, gia = 0, khach vang lai, dong trung lap)
                          roi APPEND vao Bronze
  * trigger_dbt_transform: chay dbt_transform_dag (stg_sales incremental chi them dong moi)
  * verify_after        : Bronze/Fact tang, ngay cuoi cung cua wide_daily_sales tien len,
                          doanh thu khop 3 noi; Silver da loai dong trung lap

Tham so mode=purge: xoa du lieu gia lap khoi Bronze, chay dbt voi full_refresh de tra he thong ve trang thai goc.
Luu y: lan chay tiep theo cua bronze_ingest_dag cung xoa du lieu gia lap vi nap lai Bronze tu file nguon.
"""
from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from lakehouse_common import (DEFAULT_ARGS, SPARK_CONTAINER, START_DATE, assert_revenue_reconciled,
                              docker_exec, lakehouse_snapshot, scalar)

SYNTH = "_source_sheet LIKE 'synthetic_%'"


def _snapshot_before(**_):
    snap = lakehouse_snapshot()
    print("Truoc khi nap:", snap)
    return snap          # luu vao XCom


def _verify_after(ti, params, **_):
    before = ti.xcom_pull(task_ids="snapshot_before")
    after = lakehouse_snapshot()
    print("Truoc:", before)
    print("Sau  :", after)
    assert_revenue_reconciled(after)

    bronze_synth = int(scalar(f"SELECT count(*) FROM iceberg.bronze.online_retail WHERE {SYNTH}"))
    silver_synth = int(scalar(f"SELECT count(*) FROM iceberg.silver.stg_retail_transactions WHERE {SYNTH}"))
    print(f"Dong gia lap: Bronze={bronze_synth:,} | Silver(stg_retail_transactions)={silver_synth:,} "
          f"(Silver loai {bronze_synth - silver_synth:,} dong trung lap)")

    problems = []
    if params["mode"] == "append":
        if after["bronze_rows"] <= before["bronze_rows"]:
            problems.append("Bronze khong tang")
        if after["gold_fact_rows"] <= before["gold_fact_rows"]:
            problems.append("fact_sales khong tang")
        if after["wide_last_day"] <= before["wide_last_day"]:
            problems.append("ngay cuoi cua wide_daily_sales khong tien len")
        if after["revenue_wide"] <= before["revenue_wide"]:
            problems.append("tong doanh thu khong tang")
        if bronze_synth == 0 or silver_synth == 0:
            problems.append("khong thay dong gia lap o Bronze/Silver")
        if silver_synth >= bronze_synth:
            problems.append("Silver khong loai dong trung lap")
    else:
        if bronze_synth or silver_synth:
            problems.append("van con dong gia lap sau khi purge")
    if problems:
        raise AirflowFailException("Kiem tra that bai: " + "; ".join(problems))
    print("Kiem tra cap nhat gia tang: DAT")


with DAG(
    dag_id="synthetic_ingest_dag",
    description="Gia lap nap them du lieu moi de kiem thu cap nhat gia tang",
    schedule=None,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={
        "mode": Param("append", enum=["append", "purge"], description="append: nap them | purge: xoa du lieu gia lap"),
        "n_rows": Param(3000, type="integer", minimum=100, maximum=200000, description="So dong hop le can sinh"),
        "days": Param(3, type="integer", minimum=1, maximum=60, description="So ngay moi"),
    },
    render_template_as_native_obj=True,
    tags=["bronze", "testing"],
    doc_md=__doc__,
) as dag:
    snapshot_before = PythonOperator(task_id="snapshot_before", python_callable=_snapshot_before)
    spark_synthetic = BashOperator(
        task_id="spark_synthetic",
        bash_command=docker_exec(
            SPARK_CONTAINER,
            "spark-submit --driver-memory 2g /opt/ingest/synthetic_ingest.py "
            "--mode {{ params.mode }} --rows {{ params.n_rows }} --days {{ params.days }} "
            "--tag {{ ts_nodash }}"),
    )
    trigger_dbt_transform = TriggerDagRunOperator(
        task_id="trigger_dbt_transform",
        trigger_dag_id="dbt_transform_dag",
        conf={"full_refresh": "{{ params.mode == 'purge' }}"},
        wait_for_completion=True,
        deferrable=True,
        poke_interval=20,
        reset_dag_run=True,
        allowed_states=["success"],
        failed_states=["failed"],
        retries=0,
    )
    verify_after = PythonOperator(task_id="verify_after", python_callable=_verify_after)

    snapshot_before >> spark_synthetic >> trigger_dbt_transform >> verify_after
