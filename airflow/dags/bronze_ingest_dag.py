"""
bronze_ingest_dag - Nap du lieu tho tu 2 sheet Excel vao tang Bronze (iceberg.bronze.online_retail).

check_source_file -> spark_ingest_bronze -> verify_bronze
  * check_source_file : file .xlsx ton tai trong /opt/data cua container spark-ingest
  * spark_ingest_bronze: spark-submit ingest_bronze.py (doc 2 sheet, unionByName, ghi bang Iceberg)
  * verify_bronze     : doi soat so dong tung sheet qua Trino

Luu y: ingest_bronze.py ghi bang createOrReplace() nen moi lan chay la nap lai toan bo tu file nguon
(idempotent). DAG nay khong duoc kich hoat theo lich - do lakehouse_pipeline_dag goi.
"""
from datetime import timedelta

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from lakehouse_common import DEFAULT_ARGS, SPARK_CONTAINER, START_DATE, docker_exec, trino_rows


def _verify_bronze(params, **_):
    expected = {
        "Year 2009-2010": params["rows_sheet_2009_2010"],
        "Year 2010-2011": params["rows_sheet_2010_2011"],
    }
    actual = dict(trino_rows(
        "SELECT _source_sheet, count(*) FROM iceberg.bronze.online_retail "
        "WHERE _source_sheet IN ('Year 2009-2010', 'Year 2010-2011') GROUP BY 1"))
    print(f"Mong doi: {expected}\nThuc te : {actual}")
    wrong = {s: (expected[s], actual.get(s, 0)) for s in expected if actual.get(s, 0) != expected[s]}
    if wrong:
        raise AirflowFailException(f"So dong Bronze khong khop (mong doi, thuc te): {wrong}")


with DAG(
    dag_id="bronze_ingest_dag",
    description="Nap du lieu tho 2 sheet vao tang Bronze",
    schedule=None,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={
        "rows_sheet_2009_2010": Param(525461, type="integer", description="So dong sheet Year 2009-2010"),
        "rows_sheet_2010_2011": Param(541910, type="integer", description="So dong sheet Year 2010-2011"),
    },
    tags=["bronze", "ingestion"],
    doc_md=__doc__,
) as dag:
    check_source_file = BashOperator(
        task_id="check_source_file",
        bash_command=docker_exec(SPARK_CONTAINER, "bash -c 'ls -l /opt/data/*.xlsx'"),
    )
    spark_ingest_bronze = BashOperator(
        task_id="spark_ingest_bronze",
        bash_command=docker_exec(
            SPARK_CONTAINER, "spark-submit --driver-memory 3g /opt/ingest/ingest_bronze.py"),
        execution_timeout=timedelta(minutes=45),
    )
    verify_bronze = PythonOperator(task_id="verify_bronze", python_callable=_verify_bronze)

    check_source_file >> spark_ingest_bronze >> verify_bronze
