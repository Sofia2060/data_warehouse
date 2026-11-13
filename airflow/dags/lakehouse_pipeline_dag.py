"""
lakehouse_pipeline_dag - DAG cha dieu phoi toan bo chuoi pipeline End-to-End (chay luc 02:00 moi ngay).

precheck_services -> trigger_bronze_ingest -> trigger_dbt_transform -> trigger_model_retrain -> report_summary
  * precheck_services : cong chan - cac dich vu cot loi (Postgres, MinIO, Hive, Spark, Trino, dbt) phai khoe
  * trigger_*         : kich hoat DAG con va cho den khi xong (deferrable - giai phong worker khi cho,
                        airflow-triggerer theo doi). DAG con that bai -> DAG cha dung, khong chay buoc sau
  * report_summary    : in anh chup so lieu Bronze / Silver / Gold sau khi chay

Tham so full_refresh (mac dinh true): sau khi Bronze duoc nap lai tu file nguon, dung lai Silver incremental
de Silver/Gold khong con sot du lieu gia lap tu synthetic_ingest_dag.
Can bat (unpause) ca 6 DAG; DAG con dang tam dung se khong bao gio chay.
"""
from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from lakehouse_common import (DEFAULT_ARGS, START_DATE, check_core_services, lakehouse_snapshot)


def _report(**_):
    snap = lakehouse_snapshot()
    for key, value in snap.items():
        print(f"{key:>18}: {value:,}" if isinstance(value, (int, float)) else f"{key:>18}: {value}")


def _trigger(task_id: str, dag_id: str, conf: dict | None = None) -> TriggerDagRunOperator:
    return TriggerDagRunOperator(
        task_id=task_id,
        trigger_dag_id=dag_id,
        conf=conf or {},
        wait_for_completion=True,
        deferrable=True,
        poke_interval=20,
        reset_dag_run=True,
        allowed_states=["success"],
        failed_states=["failed"],
        retries=0,
    )


with DAG(
    dag_id="lakehouse_pipeline_dag",
    description="DAG cha: Bronze -> Silver/Gold -> huan luyen mo hinh",
    schedule="0 2 * * *",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={"full_refresh": Param(True, type="boolean", description="Dung lai Silver incremental tu dau")},
    render_template_as_native_obj=True,      # de conf truyen sang DAG con la boolean that, khong phai chuoi
    tags=["orchestration"],
    doc_md=__doc__,
) as dag:
    precheck_services = PythonOperator(task_id="precheck_services", python_callable=check_core_services)
    trigger_bronze_ingest = _trigger("trigger_bronze_ingest", "bronze_ingest_dag")
    trigger_dbt_transform = _trigger("trigger_dbt_transform", "dbt_transform_dag",
                                     conf={"full_refresh": "{{ params.full_refresh }}"})
    trigger_model_retrain = _trigger("trigger_model_retrain", "model_retrain_dag")
    report_summary = PythonOperator(task_id="report_summary", python_callable=_report)

    (precheck_services >> trigger_bronze_ingest >> trigger_dbt_transform
     >> trigger_model_retrain >> report_summary)
