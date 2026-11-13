"""Dựng bản giả lập tầng Gold (DuckDB) từ online_retail.xlsx, bám sát logic dbt của nhóm.
Chỉ dùng để kiểm thử offline code ứng dụng; không phải một phần của hệ thống."""
import sys
import duckdb
import pandas as pd

SRC, OUT = sys.argv[1], sys.argv[2]
frames = []
for sheet in ["Year 2009-2010", "Year 2010-2011"]:
    df = pd.read_excel(SRC, sheet_name=sheet, dtype={"Invoice": str, "StockCode": str, "Description": str, "Customer ID": str})
    df.columns = ["invoice", "stock_code", "description", "quantity", "invoice_date", "price", "customer_id", "country"]
    df["_source_sheet"] = sheet
    df["_source_row"] = range(2, len(df) + 2)
    frames.append(df)
bronze = pd.concat(frames, ignore_index=True)
print("bronze", len(bronze))

con = duckdb.connect(OUT)
con.register("b", bronze)
con.execute("CREATE SCHEMA IF NOT EXISTS gold")
con.execute("""
CREATE OR REPLACE TABLE t AS
WITH ranked AS (
  SELECT *, row_number() OVER (PARTITION BY invoice, stock_code, description, quantity, invoice_date, price, customer_id, country
                               ORDER BY _source_sheet, _source_row) rn FROM b)
SELECT md5(_source_sheet || '|' || CAST(_source_row AS VARCHAR)) transaction_id,
       trim(invoice) invoice, upper(trim(stock_code)) stock_code, trim(description) description,
       CAST(quantity AS INT) quantity, CAST(price AS DECIMAL(12,3)) price,
       CAST(invoice_date AS TIMESTAMP) invoice_date, CAST(invoice_date AS DATE) invoice_day,
       coalesce(trim(customer_id), 'UNKNOWN') customer_id, trim(country) country,
       trim(invoice) LIKE 'C%' is_cancelled
FROM ranked WHERE rn = 1""")
con.execute("""
CREATE OR REPLACE TABLE s AS
SELECT *, CAST(quantity * price AS DECIMAL(14,3)) line_revenue,
  (stock_code IN ('POST','DOT','C2','M','D','S','BANK CHARGES','ADJUST','ADJUST2','AMAZONFEE','CRUK','PADS','B')
   OR stock_code LIKE 'GIFT%') is_non_product
FROM t WHERE NOT is_cancelled AND price > 0 AND quantity > 0 AND invoice NOT LIKE 'A%'
  AND stock_code NOT LIKE 'TEST%' AND lower(coalesce(description,'')) NOT LIKE '%test%'""")
con.execute("CREATE OR REPLACE TABLE c AS SELECT invoice_day, CAST(quantity*price AS DECIMAL(14,3)) cancelled_value FROM t WHERE is_cancelled")
con.execute("""
CREATE OR REPLACE TABLE gold.fact_sales AS
SELECT transaction_id sales_key, CAST(strftime(invoice_day,'%Y%m%d') AS INT) date_key,
  md5(customer_id) customer_key, md5(stock_code) product_key, md5(country) country_key,
  invoice invoice_no, invoice_date invoice_datetime, quantity, price unit_price, line_revenue, is_non_product
FROM s""")
con.execute("""
CREATE OR REPLACE TABLE gold.dim_customers AS
SELECT md5(customer_id) customer_key, customer_id, false is_guest,
  arg_max(country, invoice_date) latest_country, min(invoice_day) first_purchase_date, max(invoice_day) last_purchase_date
FROM s WHERE customer_id <> 'UNKNOWN' GROUP BY customer_id
UNION ALL SELECT md5('UNKNOWN'), 'UNKNOWN', true, NULL, NULL, NULL""")
con.execute("""
CREATE OR REPLACE TABLE gold.dim_products AS
SELECT md5(stock_code) product_key, stock_code, arg_max(description, invoice_date) description,
  CASE WHEN bool_or(is_non_product) THEN 'Phi dich vu' ELSE 'San pham' END product_type, min(invoice_day) first_sold_date
FROM s GROUP BY stock_code""")
con.execute("""
CREATE OR REPLACE TABLE gold.dim_country AS
SELECT md5(country) country_key, country country_name,
  CASE country WHEN 'EIRE' THEN 'Ireland' WHEN 'RSA' THEN 'South Africa' WHEN 'USA' THEN 'United States'
               WHEN 'Korea' THEN 'South Korea' ELSE country END country_name_std,
  CASE WHEN country = 'United Kingdom' THEN 'Noi dia (UK)' ELSE 'Quoc te' END market
FROM (SELECT DISTINCT country FROM s)""")
con.execute("""
CREATE OR REPLACE TABLE gold.dim_date AS
SELECT CAST(strftime(d,'%Y%m%d') AS INT) date_key, CAST(d AS DATE) full_date, day(d) "day", month(d) "month",
  strftime(d,'%B') month_name, quarter(d) "quarter", year(d) "year", isodow(d) day_of_week, strftime(d,'%A') day_name,
  isodow(d) >= 6 is_weekend
FROM (SELECT unnest(generate_series((SELECT min(invoice_day) FROM t)::TIMESTAMP, (SELECT max(invoice_day) FROM t)::TIMESTAMP, INTERVAL 1 DAY)) d)""")
con.execute("""
CREATE OR REPLACE TABLE gold.wide_daily_sales AS
WITH daily AS (SELECT CAST(invoice_datetime AS DATE) sale_date, sum(line_revenue) total_revenue,
                      count(DISTINCT invoice_no) total_orders, sum(quantity) total_quantity FROM gold.fact_sales GROUP BY 1),
cancel AS (SELECT invoice_day sale_date, sum(cancelled_value) cancelled_revenue FROM c GROUP BY 1),
j AS (SELECT d.full_date sale_date, coalesce(s.total_revenue,0) total_revenue, coalesce(cc.cancelled_revenue,0) cancelled_revenue,
             coalesce(s.total_orders,0) total_orders, coalesce(s.total_quantity,0) total_quantity,
             d.day_of_week, d."month", d."year", d.is_weekend
      FROM gold.dim_date d LEFT JOIN daily s ON d.full_date = s.sale_date LEFT JOIN cancel cc ON d.full_date = cc.sale_date)
SELECT sale_date, total_revenue, cancelled_revenue, total_revenue + cancelled_revenue net_revenue, total_orders, total_quantity,
  CASE WHEN total_orders > 0 THEN CAST(total_revenue / total_orders AS DECIMAL(14,2)) END avg_order_value,
  day_of_week, "month", "year", is_weekend, total_orders > 0 is_trading_day,
  avg(total_revenue) OVER (ORDER BY sale_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) rolling_mean_7d,
  avg(total_revenue) OVER (ORDER BY sale_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) rolling_mean_30d
FROM j""")
for tbl in ["fact_sales", "dim_customers", "dim_products", "dim_country", "dim_date", "wide_daily_sales"]:
    print(tbl, con.execute(f"SELECT count(*) FROM gold.{tbl}").fetchone()[0])
print("revenue fact", con.execute("SELECT sum(line_revenue) FROM gold.fact_sales").fetchone()[0])
print("revenue wide", con.execute("SELECT sum(total_revenue) FROM gold.wide_daily_sales").fetchone()[0])
print("trading days", con.execute("SELECT count(*) FILTER (WHERE is_trading_day) FROM gold.wide_daily_sales").fetchone()[0])
for t in ["t", "s", "c"]:
    con.execute(f"DROP TABLE {t}")
con.close()
