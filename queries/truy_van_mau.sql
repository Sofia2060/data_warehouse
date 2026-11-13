-- =========================================================
-- Bo truy van mau tren Gold Layer, phan theo loai (muc 3.6.3)
-- Chay bang Trino CLI / DBeaver, hoac do hieu nang bang queries/benchmark_trino.py (muc 3.6.5)
-- Moi truy van bat dau bang dong:  -- [Qn] Ten | Loai truy van
-- =========================================================

-- [Q1] Tra cuu mot san pham theo ma | Tra cuu diem (point lookup)
SELECT product_key, stock_code, description, product_type, first_sold_date
FROM iceberg.gold.dim_products
WHERE stock_code = '85123A';

-- [Q2] Dem so dong bang su kien | Tong hop toan bang
SELECT count(*) AS so_dong FROM iceberg.gold.fact_sales;

-- [Q3] Tong doanh thu, so don, so luong | Tong hop toan bang
SELECT round(sum(line_revenue), 2) AS doanh_thu,
       count(DISTINCT invoice_no)  AS so_don,
       sum(quantity)               AS so_luong
FROM iceberg.gold.fact_sales;

-- [Q4] Doanh thu theo thi truong va nam | Star join (1 chieu x 2)
SELECT c.market, d.year, round(sum(f.line_revenue), 0) AS doanh_thu
FROM iceberg.gold.fact_sales f
JOIN iceberg.gold.dim_country c ON f.country_key = c.country_key
JOIN iceberg.gold.dim_date    d ON f.date_key    = d.date_key
GROUP BY 1, 2
ORDER BY 2, 1;

-- [Q5] Top 5 san pham ban chay nhat theo so luong | Star join (1 chieu)
SELECT p.stock_code, p.description, sum(f.quantity) AS so_luong, round(sum(f.line_revenue), 0) AS doanh_thu
FROM iceberg.gold.fact_sales f
JOIN iceberg.gold.dim_products p ON f.product_key = p.product_key
WHERE p.product_type = 'San pham'
GROUP BY 1, 2
ORDER BY 3 DESC
LIMIT 5;

-- [Q6] Top 5 quoc gia xuat khau (ngoai UK) theo doanh thu | Star join (1 chieu)
SELECT c.country_name_std AS quoc_gia, round(sum(f.line_revenue), 0) AS doanh_thu
FROM iceberg.gold.fact_sales f
JOIN iceberg.gold.dim_country c ON f.country_key = c.country_key
WHERE c.market = 'Quoc te'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 5;

-- [Q7] Top 10 khach hang co ten theo doanh thu | Star join (1 chieu, loc khach vang lai)
SELECT c.customer_id, c.latest_country, round(sum(f.line_revenue), 0) AS doanh_thu
FROM iceberg.gold.fact_sales f
JOIN iceberg.gold.dim_customers c ON f.customer_key = c.customer_key
WHERE NOT c.is_guest
GROUP BY 1, 2
ORDER BY 3 DESC
LIMIT 10;

-- [Q8] Doanh thu theo thang, san pham, thi truong - 10 dong lon nhat | Star join (3 chieu)
SELECT d.year, d.month, p.description, c.market, round(sum(f.line_revenue), 0) AS doanh_thu
FROM iceberg.gold.fact_sales f
JOIN iceberg.gold.dim_date     d ON f.date_key    = d.date_key
JOIN iceberg.gold.dim_products p ON f.product_key = p.product_key
JOIN iceberg.gold.dim_country  c ON f.country_key = c.country_key
WHERE p.product_type = 'San pham'
GROUP BY 1, 2, 3, 4
ORDER BY 5 DESC
LIMIT 10;

-- [Q9] Tang truong doanh thu theo thang (MoM) | Window function (lag)
WITH m AS (
    SELECT d.year AS yr, d.month AS mth, sum(f.line_revenue) AS revenue
    FROM iceberg.gold.fact_sales f
    JOIN iceberg.gold.dim_date d ON f.date_key = d.date_key
    GROUP BY 1, 2
)
SELECT yr, mth, round(revenue, 0) AS doanh_thu,
       round((revenue - lag(revenue) OVER (ORDER BY yr, mth)) / lag(revenue) OVER (ORDER BY yr, mth) * 100, 1) AS mom_pct
FROM m
ORDER BY yr, mth;

-- [Q10] Phan nhom Pareto A-B-C (A = 80% doanh thu dau, B = 15% tiep, C = 5% cuoi) | Window function (tich luy)
WITH p AS (
    SELECT product_key, sum(line_revenue) AS rev
    FROM iceberg.gold.fact_sales
    GROUP BY 1
), r AS (
    SELECT product_key, rev,
           sum(rev) OVER (ORDER BY rev DESC) / sum(rev) OVER () AS cum_share
    FROM p
)
SELECT CASE WHEN cum_share <= 0.80 THEN 'A' WHEN cum_share <= 0.95 THEN 'B' ELSE 'C' END AS nhom,
       count(*) AS so_san_pham, round(sum(rev), 0) AS doanh_thu
FROM r
GROUP BY 1
ORDER BY 1;

-- [Q11] Trich xuat chuoi thoi gian cho Prophet | Trich xuat cho ML (doc bang phang)
SELECT sale_date, total_revenue, is_trading_day
FROM iceberg.gold.wide_daily_sales
ORDER BY sale_date;
