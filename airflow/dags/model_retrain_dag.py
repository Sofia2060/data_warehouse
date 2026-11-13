"""
model_retrain_dag - Huan luyen lai mo hinh Prophet du bao doanh thu dinh ky (hang tuan, Chu nhat 03:00).

check_gold_data -> train_prophet -> validate_model
  * check_gold_data: wide_daily_sales du dai (>= 365 ngay) de chia Train/Test va cross-validation
  * train_prophet  : python /opt/ml/train.py (Baseline, Grid Search, Tuned, nghiem thu, du bao 30 ngay,
                     ghi s3://warehouse/models/prophet_revenue/<version>/)
  * validate_model : doc metrics.json tu MinIO; DAG do neu mo hinh khong dat tieu chi nghiem thu
                     (khi do latest.json khong bi thay doi - mo hinh cu van duoc giu)

Tham so quick=true: luoi tham so nho, chi dung de thu nhanh pipeline. Mo hinh quick thuong khong dat nghiem thu
(khong co yearly_seasonality trong luoi) nen validate_model do va latest.json khong doi - day la hanh vi dung.
"""
import sys
from datetime import timedelta

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from lakehouse_common import DEFAULT_ARGS, START_DATE, trino_rows

MIN_DAYS = 365


def _check_gold_data(**_):
    days, first, last = trino_rows(
        "SELECT count(*), min(sale_date), max(sale_date) FROM iceberg.gold.wide_daily_sales")[0]
    print(f"wide_daily_sales: {days} ngay, {first} -> {last}")
    if days < MIN_DAYS:
        raise AirflowFailException(f"Chi co {days} ngay du lieu, can it nhat {MIN_DAYS}")


def _validate_model(ts_nodash, **_):
    sys.path.insert(0, "/opt/ml")
    import config
    import registry

    doc = registry.get_json(registry.version_key(ts_nodash, "metrics.json"))
    base, tuned = doc["baseline_prophet"], doc["tuned_prophet"]
    print(f"Version {ts_nodash} | tham so tot nhat: {doc['best_params']}")
    print(f"Baseline WAPE={base['wape']:.4f} RMSE={base['rmse']:,.0f} | "
          f"Tuned WAPE={tuned['wape']:.4f} RMSE={tuned['rmse']:,.0f}")
    print(f"Nghiem thu: {doc['acceptance']['checks']}")
    if not doc["acceptance"]["passed"]:
        raise AirflowFailException("Mo hinh moi KHONG dat tieu chi nghiem thu - giu nguyen mo hinh dang dung")
    latest = registry.get_json(config.LATEST_KEY)
    if latest["version"] != ts_nodash:
        raise AirflowFailException(f"latest.json tro toi {latest['version']}, khong phai {ts_nodash}")
    print(f"Da promote {ts_nodash} lam mo hinh dang dung")


with DAG(
    dag_id="model_retrain_dag",
    description="Huan luyen lai mo hinh Prophet dinh ky",
    schedule="0 3 * * 0",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={"quick": Param(False, type="boolean",
                           description="Luoi tham so nho de thu nhanh pipeline; thuong KHONG dat nghiem thu nen task validate_model se do")},
    tags=["ml", "prophet"],
    doc_md=__doc__,
) as dag:
    check_gold_data = PythonOperator(task_id="check_gold_data", python_callable=_check_gold_data)
    train_prophet = BashOperator(
        task_id="train_prophet",
        bash_command="python /opt/ml/train.py --version {{ ts_nodash }} "
                     "{{ '--quick' if (params.quick | string | lower) == 'true' else '' }}",
        execution_timeout=timedelta(minutes=90),
        retries=0,
    )
    validate_model = PythonOperator(task_id="validate_model", python_callable=_validate_model)

    check_gold_data >> train_prophet >> validate_model
