"""
synthetic_ingest.py - Gia lap nap them du lieu moi vao tang Bronze de kiem thu cap nhat gia tang (muc 3.7, 4.6)

Cach chay (trong container spark-ingest, thuong do synthetic_ingest_dag goi):
    spark-submit --driver-memory 2g /opt/ingest/synthetic_ingest.py --mode append --rows 3000 --days 3
    spark-submit /opt/ingest/synthetic_ingest.py --mode purge

Che do append:
  1. Lay mau ngau nhien cac dong hop le tu Bronze (san pham, don gia, khach hang, quoc gia, gio mua)
  2. Gom thanh cac don hang moi, danh so hoa don moi (>= 900000), ngay mua nam SAU ngay cuoi cung
     hien co trong Bronze -> stg_sales (incremental) nhan dung cac dong moi
  3. Cai them mot ti le nho dong "ban" de kiem tra tang Silver: don huy (C...), gia = 0,
     khach vang lai (customer_id NULL) va dong trung lap hoan toan
  4. Ghi noi (append) vao iceberg.bronze.online_retail, _source_sheet = 'synthetic_<tag>'
Che do purge: xoa toan bo dong co _source_sheet bat dau bang 'synthetic_' (sau do chay dbt voi --full-refresh)
"""
import argparse
import re
import sys

from pyspark.sql import SparkSession, Window, functions as F

TARGET = "bronze.online_retail"
PREFIX = "synthetic_"
FIRST_INVOICE = 900000       # so hoa don that nam trong khoang 489434 - 581587
LINES_PER_ORDER = 8


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["append", "purge"], default="append")
    p.add_argument("--rows", type=int, default=3000, help="so dong hop le can sinh")
    p.add_argument("--days", type=int, default=3, help="so ngay moi trai deu cac don hang")
    p.add_argument("--tag", default="", help="nhan lan chay (mac dinh: thoi gian hien tai)")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    if not 1 <= args.rows <= 200000:
        p.error("--rows phai trong khoang 1..200000")
    if not 1 <= args.days <= 60:
        p.error("--days phai trong khoang 1..60")
    return args


def purge(spark):
    before = spark.table(TARGET).count()
    spark.sql(f"DELETE FROM {TARGET} WHERE _source_sheet LIKE '{PREFIX}%'")
    after = spark.table(TARGET).count()
    print(f"PURGE: {before:,} -> {after:,} dong (da xoa {before - after:,} dong gia lap)")
    print("Luu y: chay lai dbt voi --full-refresh de Silver/Gold khong con du lieu gia lap.")


def build_rows(spark, bronze, args):
    """Dung DataFrame cac dong gia lap (chua ghi vao bang).

    Tra ve (df, so dong hop le, so dong ban moi loai, ngay cuoi cua Bronze truoc khi nap, ten sheet gia lap).
    """
    tag = re.sub(r"[^A-Za-z0-9]", "", args.tag) or spark.sql(
        "SELECT date_format(current_timestamp(), 'yyyyMMddHHmmss')").first()[0]
    sheet_name = f"{PREFIX}{tag}"

    columns = bronze.columns                      # giu nguyen thu tu cot cua bang dich
    last_day = bronze.agg(F.max(F.col("invoice_date").cast("date"))).first()[0]
    next_invoice = (bronze.filter(F.col("_source_sheet").startswith(PREFIX))
                    .filter(F.col("invoice").rlike("^[0-9]+$"))
                    .agg(F.max(F.col("invoice").cast("int"))).first()[0])
    first_invoice = max(FIRST_INVOICE, (next_invoice or 0) + 1)

    # Nguon lay mau: dong ban hang binh thuong cua du lieu that
    pool = (bronze.filter(~F.col("_source_sheet").startswith(PREFIX))
            .filter(~F.col("invoice").startswith("C"))
            .filter((F.col("quantity") > 0) & (F.col("price") > 0))
            .filter(F.col("customer_id").isNotNull() & F.col("description").isNotNull()))
    pool_size = pool.count()
    frac = min(1.0, args.rows * 1.5 / pool_size)
    sample = (pool.sample(False, frac, args.seed)
              .orderBy(F.rand(args.seed)).limit(args.rows))

    # Gom thanh don hang: moi don co LINES_PER_ORDER dong, chung khach hang / quoc gia / gio mua
    w_all = Window.orderBy(F.monotonically_increasing_id())
    s = sample.withColumn("rn", F.row_number().over(w_all))
    s = s.withColumn("grp", ((F.col("rn") - 1) / LINES_PER_ORDER).cast("int"))
    w_grp = Window.partitionBy("grp").orderBy("rn")
    s = (s.withColumn("o_customer", F.first("customer_id").over(w_grp))
          .withColumn("o_country", F.first("country").over(w_grp))
          .withColumn("o_time", F.date_format(F.first("invoice_date").over(w_grp), "HH:mm:ss")))

    # date_add(ngay, cot) chi nhan so nguyen o mot so phien ban PySpark -> dung bieu thuc SQL
    new_day = F.expr(f"date_add(DATE'{last_day.isoformat()}', 1 + (grp % {args.days}))")
    good = (s.select(
                (F.lit(first_invoice) + F.col("grp")).cast("string").alias("invoice"),
                "stock_code", "description", "quantity",
                F.concat_ws(" ", new_day.cast("string"), F.col("o_time")).alias("invoice_date"),
                "price",
                F.col("o_customer").alias("customer_id"),
                F.col("o_country").alias("country"))
              .withColumn("invoice_date", F.expr("CAST(invoice_date AS TIMESTAMP_NTZ)")))
    good = good.cache()
    n_good = good.count()

    # Dong "ban" de kiem tra Silver (moi loai ~1% so dong hop le)
    k = max(1, n_good // 100)
    pick = lambda: good.orderBy(F.rand(args.seed + 1)).limit(k)
    cancel = (pick().withColumn("invoice", F.concat(F.lit("C"), F.col("invoice")))
                    .withColumn("quantity", -F.col("quantity")))
    zero_price = pick().withColumn("price", F.lit(0.0))
    guest = pick().withColumn("customer_id", F.lit(None).cast("string"))
    duplicate = pick()
    dirty = cancel.unionByName(zero_price).unionByName(guest).unionByName(duplicate)

    allrows = good.unionByName(dirty)
    w_row = Window.orderBy("invoice", "stock_code", "invoice_date")
    out = (allrows
           .withColumn("quantity", F.col("quantity").cast("long"))
           .withColumn("price", F.col("price").cast("double"))
           .withColumn("_source_sheet", F.lit(sheet_name))
           .withColumn("_source_row", (F.row_number().over(w_row) + 1).cast("long"))
           .withColumn("_ingested_at", F.current_timestamp())
           .select(*columns))
    return out, n_good, k, last_day, sheet_name


def append(spark, args):
    bronze = spark.table(TARGET)
    out, n_good, k, last_day, sheet_name = build_rows(spark, bronze, args)

    before = bronze.count()
    out.writeTo(TARGET).append()
    after = spark.table(TARGET).count()
    n_total = after - before

    print(f"APPEND: sheet '{sheet_name}', ngay moi {last_day} + 1 .. + {args.days}")
    print(f"        {n_good:,} dong hop le + {n_total - n_good:,} dong 'ban' "
          f"(huy={k}, gia 0={k}, vang lai={k}, trung lap={k})")
    print(f"        Bronze: {before:,} -> {after:,} dong")
    print(f"SYNTHETIC_ROWS={n_total}")


def main():
    args = parse_args()
    spark = SparkSession.builder.appName(f"synthetic_ingest_{args.mode}").enableHiveSupport().getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        purge(spark) if args.mode == "purge" else append(spark, args)
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
