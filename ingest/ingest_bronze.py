"""
ingest_bronze.py - Nap du lieu tho Online Retail II vao tang Bronze (Apache Iceberg tren MinIO)

Cach chay (trong container spark-ingest):
    spark-submit --driver-memory 3g /opt/ingest/ingest_bronze.py

Cac buoc:
  1. Tao 3 schema bronze / silver / gold (neu chua co)
  2. Doc tung sheet Excel voi kieu du lieu tuong minh (ma dinh danh = chuoi)
  3. Doi ten cot sang snake_case
  4. Gan sieu du lieu truy vet: _source_sheet, _source_row, _ingested_at
  5. Hop nhat 2 sheet bang unionByName (KHONG loai trung o tang nay)
  6. Ghi vao bang iceberg.bronze.online_retail va doi soat so dong
"""
import glob
import os
import sys
import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import StructType, StructField, StringType, LongType, DoubleType

# Lay file .xlsx dau tien trong thu muc data (vd: online_retail_II.xlsx hoac online_retail.xlsx)
_found = sorted(glob.glob("/opt/data/*.xlsx"))
SRC_PATH = os.environ.get("SRC_PATH", _found[0] if _found else "/opt/data/online_retail_II.xlsx")
SHEETS = ["Year 2009-2010", "Year 2010-2011"]
TARGET = "bronze.online_retail"        # = iceberg.bronze.online_retail khi truy van bang Trino
LOCAL_TEST = os.environ.get("LOCAL_TEST") == "1"   # chi dung khi thu nghiem khong co Iceberg

# ---------------------------------------------------------------- Spark session
# Cau hinh Iceberg + Hive Metastore + MinIO nam trong spark/spark-defaults.conf
builder = SparkSession.builder.appName("bronze_ingest")
if LOCAL_TEST:
    builder = builder.config("spark.sql.session.timeZone", "UTC")
else:
    builder = builder.enableHiveSupport()
spark = builder.getOrCreate()
spark.sparkContext.setLogLevel("WARN")

# ---------------------------------------------------------------- Buoc 1: schema
if not LOCAL_TEST:
    for ns in ["bronze", "silver", "gold"]:
        spark.sql(f"CREATE DATABASE IF NOT EXISTS {ns}")
    print("[1/6] Da tao schema bronze, silver, gold trong Hive Metastore")

# ---------------------------------------------------------------- Buoc 2-4: doc tung sheet
# Doc InvoiceDate dang chuoi roi ep sang TIMESTAMP_NTZ (khong mui gio) de tranh lech gio
schema = StructType([
    StructField("invoice", StringType()),
    StructField("stock_code", StringType()),
    StructField("description", StringType()),
    StructField("quantity", LongType()),
    StructField("invoice_date", StringType()),
    StructField("price", DoubleType()),
    StructField("customer_id", StringType()),
    StructField("country", StringType()),
    StructField("_source_sheet", StringType()),
    StructField("_source_row", LongType()),
])
STR_COLS = ["invoice", "stock_code", "description", "customer_id", "country"]

print(f"Doc file nguon: {SRC_PATH}")
frames, expected = [], 0
for sheet in SHEETS:
    pdf = pd.read_excel(SRC_PATH, sheet_name=sheet,
                        dtype={"Invoice": str, "StockCode": str,
                               "Description": str, "Customer ID": str})
    # Buoc 3: doi ten cot
    pdf.columns = ["invoice", "stock_code", "description", "quantity",
                   "invoice_date", "price", "customer_id", "country"]
    pdf["invoice_date"] = pdf["invoice_date"].dt.strftime("%Y-%m-%d %H:%M:%S")
    # O trong (NaN) -> None de Spark hieu la NULL
    for c in STR_COLS:
        pdf[c] = pdf[c].astype(object).where(pdf[c].notna(), None)
    # Buoc 4: sieu du lieu truy vet
    pdf["_source_sheet"] = sheet
    pdf["_source_row"] = range(2, len(pdf) + 2)          # dong 1 cua sheet la tieu de
    frames.append(spark.createDataFrame(pdf, schema=schema))
    expected += len(pdf)
    print(f"[2/6] Doc sheet '{sheet}': {len(pdf):,} dong")

# ---------------------------------------------------------------- Buoc 5: union
bronze = (frames[0].unionByName(frames[1])
          .withColumn("invoice_date", F.expr("CAST(invoice_date AS TIMESTAMP_NTZ)"))
          .withColumn("_ingested_at", F.current_timestamp()))
print(f"[5/6] Hop nhat 2 sheet: {expected:,} dong (chua loai trung)")

# ---------------------------------------------------------------- Buoc 6: ghi + doi soat
if LOCAL_TEST:
    out = os.environ.get("LOCAL_OUT", "/tmp/bronze_test")
    bronze.write.mode("overwrite").parquet(out)
    actual = spark.read.parquet(out).count()
else:
    bronze.writeTo(TARGET).using("iceberg").createOrReplace()
    actual = spark.table(TARGET).count()

print(f"[6/6] Doi soat: doc {expected:,} dong - trong bang {actual:,} dong")
if actual != expected:
    print("LOI: so dong khong khop!")
    sys.exit(1)
print("HOAN THANH: tang Bronze da san sang.")
spark.stop()
