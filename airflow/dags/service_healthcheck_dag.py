"""
service_healthcheck_dag - Giam sat suc khoe cac container moi 10 phut.

Moi dich vu co mot task check_<ten> chay song song (TCP / HTTP / docker inspect). Task cuoi `summarize`
(trigger_rule = all_done) tong hop ket qua va chi do khi co it nhat mot dich vu loi.
Container chua duoc trien khai (streamlit, groq-agent) hien thi trang thai skipped.
"""
from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.python import PythonOperator
from airflow.utils.state import TaskInstanceState
from airflow.utils.trigger_rule import TriggerRule

from lakehouse_common import DEFAULT_ARGS, SERVICES, START_DATE, run_check


def _check(service: dict) -> None:
    print(run_check(service))


def _summarize(dag_run, **_):
    bad_states = (TaskInstanceState.FAILED, TaskInstanceState.UPSTREAM_FAILED)
    failed = [ti.task_id.removeprefix("check_") for ti in dag_run.get_task_instances()
              if ti.task_id.startswith("check_") and ti.state in bad_states]
    if failed:
        raise AirflowFailException("Dich vu khong khoe: " + ", ".join(sorted(failed)))
    print("Tat ca dich vu dang hoat dong binh thuong")


with DAG(
    dag_id="service_healthcheck_dag",
    description="Giam sat suc khoe cac container moi 10 phut",
    schedule="*/10 * * * *",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULT_ARGS, "retries": 0},
    tags=["monitoring"],
    doc_md=__doc__,
) as dag:
    checks = [
        PythonOperator(task_id=f"check_{svc['id']}", python_callable=_check, op_kwargs={"service": svc})
        for svc in SERVICES
    ]
    summarize = PythonOperator(task_id="summarize", python_callable=_summarize,
                               trigger_rule=TriggerRule.ALL_DONE)
    checks >> summarize
