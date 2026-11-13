-- =========================================================
-- Cac cau truy van kiem tra (chay trong Trino CLI hoac DBeaver)
-- Ket qua mong doi ghi o cuoi moi cau
-- =========================================================

-- [BRONZE] So dong theo sheet  -> 525461 / 541910 / tong 1067371
SELECT _source_sheet, COUNT(*) AS so_dong FROM iceberg.bronze.online_retail GROUP BY 1
UNION ALL
SELECT 'TONG', COUNT(*) FROM iceberg.bronze.online_retail;

-- [SILVER] So dong 4 model  -> 1033036 / 1007902 / 19104 / 6030
SELECT 'stg_retail_transactions' AS bang, COUNT(*) AS so_dong FROM iceberg.silver.stg_retail_transactions
UNION ALL SELECT 'stg_sales',            COUNT(*) FROM iceberg.silver.stg_sales
UNION ALL SELECT 'stg_cancellations',    COUNT(*) FROM iceberg.silver.stg_cancellations
UNION ALL SELECT 'stg_rejected_records', COUNT(*) FROM iceberg.silver.stg_rejected_records;

-- [SILVER] Ly do loai ban ghi -> 2616 gia<=0, 3392 ton kho, 16 test, 6 no xau
SELECT reject_reason, COUNT(*) FROM iceberg.silver.stg_rejected_records GROUP BY 1 ORDER BY 2 DESC;

-- [GOLD] So dong cac bang -> 1007902 / 5879 / 4742 / 739 / 43 / 739
SELECT 'fact_sales' AS bang, COUNT(*) AS so_dong FROM iceberg.gold.fact_sales
UNION ALL SELECT 'dim_customers',    COUNT(*) FROM iceberg.gold.dim_customers
UNION ALL SELECT 'dim_products',     COUNT(*) FROM iceberg.gold.dim_products
UNION ALL SELECT 'dim_date',         COUNT(*) FROM iceberg.gold.dim_date
UNION ALL SELECT 'dim_country',      COUNT(*) FROM iceberg.gold.dim_country
UNION ALL SELECT 'wide_daily_sales', COUNT(*) FROM iceberg.gold.wide_daily_sales;

-- [GOLD] Doi soat doanh thu -> ca 3 deu bang 20464972.388
SELECT (SELECT SUM(line_revenue)  FROM iceberg.silver.stg_sales)       AS silver,
       (SELECT SUM(line_revenue)  FROM iceberg.gold.fact_sales)        AS fact,
       (SELECT SUM(total_revenue) FROM iceberg.gold.wide_daily_sales)  AS wide_table;

-- [GOLD] Vi du truy van Star Schema: doanh thu theo thi truong va nam
SELECT c.market, d.year, ROUND(SUM(f.line_revenue), 0) AS doanh_thu
FROM iceberg.gold.fact_sales f
JOIN iceberg.gold.dim_country c ON f.country_key = c.country_key
JOIN iceberg.gold.dim_date    d ON f.date_key    = d.date_key
GROUP BY 1, 2 ORDER BY 2, 1;

-- [GOLD] Xem thu wide table
SELECT * FROM iceberg.gold.wide_daily_sales ORDER BY sale_date DESC LIMIT 10;
