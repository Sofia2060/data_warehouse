FROM apache/airflow:2.10.5-python3.11

# Docker CLI (khong kem daemon): DAG goi "docker exec" vao container spark-ingest va dbt
# thong qua /var/run/docker.sock duoc mount tu may host
USER root
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

USER airflow
# trino  : truy van Gold qua Trino tu DAG va pipeline ML
# boto3  : doc/ghi Model Registry tren MinIO
# prophet: huan luyen mo hinh du bao doanh thu (ml/train.py)
# Dung file constraints cua Airflow de cac thu vien khong lam hong ban cai dat san
ARG AIRFLOW_VERSION=2.10.5
ARG PYTHON_VERSION=3.11
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
