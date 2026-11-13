"""
queries.py - Cac cau SQL Trino cua Dashboard, doc truc tiep Star Schema va bang phang tang Gold.

Tham so loc (ngay, thi truong) chi nhan gia tri tu widget cua Dashboard: ngay la doi tuong date,
thi truong nam trong danh sach co dinh MARKETS, nen ghep vao SQL khong co nguy co SQL injection.
"""
from datetime import date

MARKETS = {"Tất cả": None, "Nội địa (UK)": "Noi dia (UK)", "Quốc tế": "Quoc te"}

_STAR_JOIN = """
FROM fact_sales f
JOIN dim_date d      ON f.date_key = d.date_key
JOIN dim_country co  ON f.country_key = co.country_key"""


def _where(start: date, end: date, market_label: str) -> str:
    if not isinstance(start, date) or not isinstance(end, date):
        raise ValueError("Khoang ngay khong hop le")
    market = MARKETS[market_label]          # KeyError neu gia tri khong nam trong danh sach
    cond = f"WHERE d.full_date BETWEEN DATE '{start.isoformat()}' AND DATE '{end.isoformat()}'"
    if market:
        cond += f" AND co.market = '{market}'"
    return cond


def date_bounds() -> str:
    return "SELECT min(sale_date) AS d0, max(sale_date) AS d1 FROM wide_daily_sales"


def kpis(start, end, market) -> str:
    return f"""
SELECT
    sum(f.line_revenue)                                              AS revenue,
    count(DISTINCT f.invoice_no)                                     AS orders,
    sum(f.line_revenue) / nullif(count(DISTINCT f.invoice_no), 0)    AS aov,
    count(DISTINCT CASE WHEN NOT cu.is_guest THEN cu.customer_id END) AS customers
{_STAR_JOIN}
JOIN dim_customers cu ON f.customer_key = cu.customer_key
{_where(start, end, market)}"""


def monthly_by_market(start, end, market) -> str:
    return f"""
SELECT date_trunc('month', d.full_date) AS month, co.market,
       sum(f.line_revenue) AS revenue, count(DISTINCT f.invoice_no) AS orders
{_STAR_JOIN}
{_where(start, end, market)}
GROUP BY 1, 2
ORDER BY 1, 2"""


def market_share(start, end, market) -> str:
    return f"""
SELECT co.market, sum(f.line_revenue) AS revenue
{_STAR_JOIN}
{_where(start, end, market)}
GROUP BY 1
ORDER BY 2 DESC"""


def top_products(start, end, market, n: int = 10) -> str:
    return f"""
SELECT p.stock_code, p.description, sum(f.quantity) AS quantity, sum(f.line_revenue) AS revenue
{_STAR_JOIN}
JOIN dim_products p ON f.product_key = p.product_key
{_where(start, end, market)} AND p.product_type = 'San pham'
GROUP BY 1, 2
ORDER BY revenue DESC
LIMIT {int(n)}"""


def top_export_countries(start, end, market, n: int = 10) -> str:
    return f"""
SELECT co.country_name_std AS country, sum(f.line_revenue) AS revenue, count(DISTINCT f.invoice_no) AS orders
{_STAR_JOIN}
{_where(start, end, market)} AND co.market = 'Quoc te'
GROUP BY 1
ORDER BY revenue DESC
LIMIT {int(n)}"""


def daily_history() -> str:
    return """
SELECT sale_date, total_revenue, rolling_mean_7d, rolling_mean_30d
FROM wide_daily_sales
ORDER BY sale_date"""
