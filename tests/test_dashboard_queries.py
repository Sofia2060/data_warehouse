"""Chay moi cau SQL cua Dashboard tren Gold gia lap va doi chieu voi so lieu nhom da cong bo (muc 3.6.4)."""
from datetime import date

import pytest
import sqlglot

from dashboard import queries as Q
from duck_backend import run_query

D0, D1 = date(2009, 12, 1), date(2011, 12, 9)
TOTAL = 20_464_972.39   # tong doanh thu fact_sales nhom da doi soat


def test_all_queries_parse_as_trino():
    for fn in (Q.kpis, Q.monthly_by_market, Q.market_share, Q.top_products, Q.top_export_countries):
        for m in Q.MARKETS:
            sqlglot.parse_one(fn(D0, D1, m), read="trino")
    sqlglot.parse_one(Q.daily_history(), read="trino")
    sqlglot.parse_one(Q.date_bounds(), read="trino")


def test_bounds():
    b = run_query(Q.date_bounds()).iloc[0]
    assert str(b.d0)[:10] == "2009-12-01" and str(b.d1)[:10] == "2011-12-09"


def test_kpi_totals():
    k = run_query(Q.kpis(D0, D1, "Tất cả")).iloc[0]
    assert abs(k.revenue - TOTAL) < 0.01
    uk = run_query(Q.kpis(D0, D1, "Nội địa (UK)")).iloc[0]
    intl = run_query(Q.kpis(D0, D1, "Quốc tế")).iloc[0]
    assert abs(uk.revenue + intl.revenue - TOTAL) < 0.01
    assert abs(k.aov - k.revenue / k.orders) < 1e-6
    print("KPI", k.to_dict(), "UK share", uk.revenue / TOTAL)


def test_monthly_and_share_sum():
    mon = run_query(Q.monthly_by_market(D0, D1, "Tất cả"))
    assert abs(mon.revenue.sum() - TOTAL) < 0.01
    assert len(mon) == 25 * 2      # 25 thang (12/2009 - 12/2011) x 2 thi truong
    sh = run_query(Q.market_share(D0, D1, "Tất cả"))
    assert abs(sh.revenue.sum() - TOTAL) < 0.01


def test_tops():
    tp = run_query(Q.top_products(D0, D1, "Tất cả"))
    assert len(tp) == 10 and tp.revenue.is_monotonic_decreasing
    tc = run_query(Q.top_export_countries(D0, D1, "Tất cả"))
    assert len(tc) == 10 and "United Kingdom" not in set(tc.country)
    assert run_query(Q.top_export_countries(D0, D1, "Nội địa (UK)")).empty
    print(tp.head(3).to_string(), tc.head(3).to_string(), sep="\n")


def test_filters_narrow():
    k = run_query(Q.kpis(date(2011, 1, 1), date(2011, 1, 31), "Tất cả")).iloc[0]
    assert 0 < k.revenue < TOTAL


def test_bad_market_rejected():
    with pytest.raises(KeyError):
        Q.kpis(D0, D1, "x' OR '1'='1")


def test_history():
    h = run_query(Q.daily_history())
    assert len(h) == 739 and abs(h.total_revenue.sum() - TOTAL) < 0.01
