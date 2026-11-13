# Lakehouse Online Retail II — Hướng dẫn sử dụng

Hệ thống Data Lakehouse theo kiến trúc **Medallion (Bronze → Silver → Gold)** cho bộ dữ liệu **UCI Online Retail II** (giao dịch bán lẻ trực tuyến 12/2009 – 12/2011), chạy hoàn toàn bằng **Docker Compose**.

| Thành phần | Công nghệ |
|---|---|
| Lưu trữ đối tượng | MinIO (tương thích Amazon S3) |
| Định dạng bảng | Apache Iceberg |
| Danh mục bảng (catalog) | Hive Metastore 3.1.3 + PostgreSQL |
| Nạp dữ liệu Bronze | Apache Spark (PySpark) |
| Biến đổi Silver, Gold | dbt-core + dbt-spark |
| Truy vấn | Trino 470 |
| Điều phối | Apache Airflow 2.10 (LocalExecutor) |
| Dự báo doanh thu | Facebook Prophet, Model Registry trên MinIO |

---

## 1. Yêu cầu máy

- **Docker Desktop** (Windows: chọn *Use WSL 2* khi cài) — https://www.docker.com/products/docker-desktop/
- Cấp cho Docker **ít nhất 6 GB RAM** (*Settings → Resources*). Máy 8 GB: để 5–6 GB và đóng bớt trình duyệt.
- Khoảng **10 GB** dung lượng trống.
- Các cổng còn trống: `9000`, `9001`, `9083`, `4040`, `4041`, `10000`, `8080`, `8081`, `8090`.

## 2. Cấu trúc thư mục

```
lakehouse-online-retail/
├── docker-compose.yml        Khai báo 12 container (8 hạ tầng dữ liệu + 4 Airflow)
├── data/online_retail.xlsx   Dữ liệu gốc (2 sheet: Year 2009-2010, Year 2010-2011)
├── ingest/
│   ├── ingest_bronze.py      Script Spark nạp tầng Bronze
│   └── synthetic_ingest.py   Script Spark sinh dữ liệu giả lập để kiểm thử cập nhật gia tăng
├── dbt_project/              Dự án dbt
│   ├── models/silver/        4 model làm sạch
│   ├── models/gold/          Star Schema (1 fact, 4 dim) + Wide Table
│   └── macros/               Macro dùng chung
├── airflow/                  Image Airflow + 6 DAG trong airflow/dags/ (mục 3.7)
├── ml/                       Pipeline Prophet: train.py, registry.py, ... (mục 3.8)
├── queries/
│   ├── kiem_tra.sql          Các câu SQL đối soát kết quả
│   ├── truy_van_mau.sql      11 truy vấn mẫu theo loại (mục 3.6.3)
│   └── benchmark_trino.py    Đo hiệu năng truy vấn (mục 3.6.5)
└── hive/  spark/  trino/  dbt/   Cấu hình image và kết nối
```

## 3. Các container

| Container | Vai trò | Địa chỉ |
|---|---|---|
| postgres-db | Lưu metadata của Hive Metastore | — |
| minio | Lưu file dữ liệu và metadata Iceberg | http://localhost:9001 (`admin` / `password`) |
| create-minio-bucket | Tạo bucket `warehouse`, chạy 1 lần rồi dừng | — |
| hive-metastore | Danh mục bảng Iceberg dùng chung cho Spark và Trino | — |
| spark-ingest | Chạy job nạp tầng Bronze | http://localhost:4040 (khi job đang chạy) |
| spark-thrift-server | Cổng Spark SQL để dbt kết nối | — |
| dbt | Chạy model Silver, Gold và kiểm thử | http://localhost:8081 (dbt docs) |
| trino | Truy vấn SQL trên các bảng Iceberg | http://localhost:8090 |
| airflow-init | Tạo database `airflow_db`, migrate schema, tạo user `admin`; chạy 1 lần rồi dừng | — |
| airflow-webserver | Giao diện Airflow | http://localhost:8080 (`admin` / `admin`) |
| airflow-scheduler | Lập lịch và chạy task của 6 DAG | — |
| airflow-triggerer | Theo dõi các task deferrable (DAG cha chờ DAG con) | — |

“Hệ thống có 14 container: 12 container trong docker-compose.yml và 2 container ứng dụng (streamlit, groq-agent) trong docker-compose.app.yml, xem README_UNG_DUNG.md. Với Airflow, hãy cấp cho Docker ít nhất 8 GB RAM.”

---

## 4. Chạy hệ thống từ đầu

Mở **PowerShell** (Windows) hoặc **Terminal** (macOS), di chuyển vào thư mục dự án:

```
cd D:\lakehouse-online-retail
```

### Bước 1 — Khởi động hạ tầng

```
docker compose up -d --build
```

Lần đầu mất 15–30 phút để tải image. Kiểm tra trạng thái:

```
docker compose ps
```

Kết quả đúng: 7 container **Up** (có `healthy`), riêng `create-minio-bucket` ở trạng thái **Exited (0)**.

> **Quan trọng:** sau khi `hive-metastore` đã lên `healthy` lần đầu, mở `docker-compose.yml`, đổi `IS_RESUME: "false"` thành `IS_RESUME: "true"`, rồi lưu lại. Nếu không đổi, các lần khởi động sau Hive Metastore sẽ báo lỗi vì schema đã tồn tại (xem mục 7).

### Bước 2 — Nạp tầng Bronze (Spark)

```
docker exec -it spark-ingest spark-submit --driver-memory 3g /opt/ingest/ingest_bronze.py
```

Mất 3–6 phút. Cuối log phải có:

```
[2/6] Doc sheet 'Year 2009-2010': 525,461 dong
[2/6] Doc sheet 'Year 2010-2011': 541,910 dong
[6/6] Doi soat: doc 1,067,371 dong - trong bang 1,067,371 dong
HOAN THANH: tang Bronze da san sang.
```

### Bước 3 — Tạo tầng Silver và Gold (dbt)

```
docker exec -it dbt dbt deps
docker exec -it dbt dbt debug
docker exec -it dbt dbt build
```

- `dbt deps` tải thư viện `dbt_utils` (cần chạy lại mỗi khi container `dbt` được tạo mới).
- `dbt debug` phải báo **All checks passed!**
- `dbt build` mất 2–5 phút, dòng cuối phải là `Completed successfully`, `ERROR=0`.

Chỉ chạy lại một tầng khi sửa code:

```
docker exec -it dbt dbt build --select silver --indirect-selection=cautious
docker exec -it dbt dbt build --select gold
```

---

## 5. Kiểm tra kết quả

### Truy vấn bằng Trino

```
docker exec -it trino trino
```

Ví dụ (thoát bằng `quit;`):

```sql
SHOW SCHEMAS FROM iceberg;
SELECT _source_sheet, COUNT(*) FROM iceberg.bronze.online_retail GROUP BY 1;
SELECT * FROM iceberg.gold.wide_daily_sales ORDER BY sale_date LIMIT 10;
```

Toàn bộ câu đối soát nằm trong `queries/kiem_tra.sql`; kết quả mong đợi ghi ở chú thích cuối mỗi câu. Có thể chạy bằng Trino CLI hoặc DBeaver (kết nối `localhost:8090`, user bất kỳ, không mật khẩu).

### Xem file trên MinIO

Mở http://localhost:9001 → bucket `warehouse` → thư mục `bronze/`, `silver/`, `gold/`. Mỗi bảng gồm thư mục `data/` (file Parquet) và `metadata/` (metadata Iceberg).

### Xem Data Lineage

```
docker exec -it dbt dbt docs generate
docker exec -it dbt dbt docs serve --port 8081 --host 0.0.0.0
```

Mở http://localhost:8081 → bấm biểu tượng tròn ở góc phải dưới (*View Lineage Graph*). Nhấn `Ctrl + C` để tắt.

### Số liệu mong đợi

| Tầng | Bảng | Số dòng |
|---|---|---|
| Bronze | online_retail | 1.067.371 |
| Silver | stg_retail_transactions | 1.033.036 |
| Silver | stg_sales | 1.007.902 |
| Silver | stg_cancellations | 19.104 |
| Silver | stg_rejected_records | 6.030 |
| Gold | fact_sales | 1.007.902 |
| Gold | dim_customers | 5.879 |
| Gold | dim_products | 4.742 |
| Gold | dim_date | 739 |
| Gold | dim_country | 43 |
| Gold | wide_daily_sales | 739 |

Tổng doanh thu khớp ở cả ba nơi (stg_sales = fact_sales = wide_daily_sales): **20.464.972,39 £**.

---

## 5A. Điều phối tự động bằng Airflow (mục 3.7)

Airflow chỉ là bộ điều phối: các task gọi `docker exec` vào `spark-ingest` và `dbt` (qua `/var/run/docker.sock`), truy vấn Gold qua Trino, và chạy `ml/train.py` ngay trong container Airflow.

1. Đã làm Bước 1–3 ở mục 4 (Bronze, Silver, Gold có dữ liệu) và `docker compose up -d --build` để dựng thêm 4 container Airflow (lần đầu build image mất 5–10 phút vì cài Prophet).
2. Mở http://localhost:8080 (`admin` / `admin`). **Cả 6 DAG đang tạm dừng sẵn** — bật công tắc từng DAG (DAG con tạm dừng thì DAG cha chờ mãi).
3. Trên Linux, trước `docker compose up` chạy `export DOCKER_GID=$(stat -c %g /var/run/docker.sock)`. Docker Desktop (Windows/macOS) không cần.

| DAG | Lịch | Chức năng |
|---|---|---|
| `service_healthcheck_dag` | mỗi 10 phút | Kiểm tra TCP/HTTP/`docker inspect` từng container; `streamlit`, `groq-agent` chưa có thì hiện *skipped* |
| `bronze_ingest_dag` | do DAG cha gọi | Kiểm tra file nguồn → `spark-submit ingest_bronze.py` → đối soát số dòng từng sheet |
| `dbt_transform_dag` | do DAG cha gọi | `dbt deps` → run/test Silver → run/test Gold → đối soát doanh thu → `dbt docs generate`. Tham số `full_refresh` |
| `model_retrain_dag` | Chủ nhật 03:00 | Kiểm tra Gold → `ml/train.py` → xác nhận mô hình đạt nghiệm thu |
| `lakehouse_pipeline_dag` | 02:00 hằng ngày | DAG cha: kiểm tra dịch vụ → Bronze → dbt → huấn luyện → báo cáo |
| `synthetic_ingest_dag` | thủ công | Nạp thêm dữ liệu giả lập, kiểm thử cập nhật gia tăng (xem dưới) |

Chạy thử nhanh: bấm **Trigger DAG** trên `lakehouse_pipeline_dag` (Graph view sẽ thấy 5 task lần lượt xanh).

### Kiểm thử cập nhật gia tăng (mục 4.6)

`Trigger DAG w/ config` trên `synthetic_ingest_dag` với `mode=append` (mặc định 3000 dòng, 3 ngày). DAG sinh đơn hàng mới sau ngày cuối cùng của Bronze, kèm ~1% dòng "bẩn" mỗi loại (đơn hủy, giá 0, khách vãng lai, dòng trùng), chạy dbt rồi kiểm tra: Bronze/`fact_sales` tăng, ngày cuối của `wide_daily_sales` tiến lên, doanh thu khớp 3 nơi, Silver đã loại dòng trùng.

Trả hệ thống về trạng thái gốc: chạy lại với `mode=purge` (xóa dòng giả lập khỏi Bronze và dựng lại Silver bằng `--full-refresh`). Chạy `bronze_ingest_dag` cũng xóa dữ liệu giả lập vì nạp lại Bronze từ file nguồn.

## 5B. Dự báo doanh thu bằng Prophet (mục 3.8)

```
docker exec -it airflow-scheduler python /opt/ml/train.py            # đầy đủ (Grid Search 24 tổ hợp, vài phút)
docker exec -it airflow-scheduler python /opt/ml/train.py --quick    # lưới nhỏ, chỉ để thử pipeline
```

Hoặc `Trigger DAG` trên `model_retrain_dag`. Kết quả nằm trong MinIO, bucket `warehouse`, thư mục `models/prophet_revenue/<phiên bản>/`:

| File | Nội dung |
|---|---|
| `model.pkl`, `model.json` | Mô hình Prophet đã huấn luyện lại trên toàn bộ dữ liệu |
| `metrics.json` | Chỉ số Baseline / Seasonal naive / Tuned (MAE, RMSE, MAPE, sMAPE, WAPE), tham số tốt nhất, kết quả Grid Search, kết quả nghiệm thu |
| `forecast.csv` | Dự báo 30 ngày: `yhat`, `yhat_lower`, `yhat_upper` (khoảng tin cậy 80%) |
| `test_predictions.csv`, `test_comparison.png`, `forecast.png` | Dự báo trên tập Test và biểu đồ cho báo cáo |

`models/prophet_revenue/latest.json` chỉ được cập nhật khi mô hình đạt cả 3 tiêu chí nghiệm thu (`ml/config.py`): WAPE của Tuned thấp hơn Baseline, thấp hơn Seasonal naive, và không vượt `ACCEPT_MAX_WAPE`. Ứng dụng Streamlit đọc forecast.csv và metrics.json của phiên bản ghi trong latest.json.`.

Chạy trên máy host (không cần Docker cho phần Prophet, nhưng cần Trino và MinIO đang chạy):

```
pip install -r ml/requirements.txt
set TRINO_HOST=localhost& set TRINO_PORT=8090& set MINIO_ENDPOINT=http://localhost:9000
python ml/train.py
```

## 5C. Đo hiệu năng Trino (mục 3.6.5)

```
pip install trino
python queries/benchmark_trino.py --runs 5
```

In bảng Markdown (11 truy vấn trong `queries/truy_van_mau.sql`, mỗi truy vấn 1 lần warm-up + 5 lần đo) và ghi `queries/benchmark_result.csv`.

---

## 6. Tắt và bật lại

```
docker compose stop        Tắt, giữ nguyên dữ liệu
docker compose start       Bật lại
docker compose down        Xóa container, giữ dữ liệu (volume)
docker compose down -v     XÓA SẠCH dữ liệu để làm lại từ đầu
```

Sau `down -v`, nhớ đổi lại `IS_RESUME: "false"` trước khi `up`, rồi làm lại từ mục 4.

## 7. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `hive-metastore` không lên, log có `relation "BUCKETING_COLS" already exists` | Schema đã được tạo ở lần trước. Đổi `IS_RESUME` thành `"true"` rồi `docker compose up -d`. |
| `hive-metastore` không lên trên máy mới, log báo thiếu bảng metastore | Đang để `IS_RESUME: "true"` khi database còn trống. Đổi thành `"false"`, chạy `docker compose down -v` rồi `up -d --build`. |
| `port is already allocated` | Cổng bị chương trình khác dùng. Sửa số bên trái trong mục `ports:` (vd `8090:8080` → `8095:8080`). |
| Spark báo `Java heap space` hoặc container bị tắt | Tăng RAM cho Docker, hoặc đổi `--driver-memory 3g` thành `2g`. |
| Spark không tìm thấy file Excel | Kiểm tra file `.xlsx` nằm trong thư mục `data/`. |
| `dbt debug` lỗi kết nối | `spark-thrift-server` khởi động chậm 1–2 phút. Chờ rồi chạy lại; xem log: `docker logs spark-thrift-server`. |
| `dbt build` báo không tìm thấy `dbt_utils` | Chưa chạy `docker exec -it dbt dbt deps`. |
| `Table 'iceberg.bronze.online_retail' does not exist` | Chưa chạy Bước 2, hoặc đã `down -v`. Chạy lại Bước 2. |

Xem log của một container bất kỳ: `docker logs <tên-container>`.

---

**Nguồn dữ liệu:** Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D
