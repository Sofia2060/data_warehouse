import pytest

from agent.sql_guard import GuardError, check

OK = [
    "SELECT * FROM fact_sales",
    "select count(*) from iceberg.gold.fact_sales",
    "SELECT p.description, sum(f.quantity) q FROM fact_sales f JOIN dim_products p ON f.product_key = p.product_key "
    "GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
    "WITH t AS (SELECT * FROM wide_daily_sales) SELECT * FROM t",
    "SELECT 1 FROM dim_date UNION ALL SELECT 2 FROM dim_country",
    "SELECT * FROM gold.dim_customers;",
    "SELECT * FROM fact_sales -- top\n",
    "SELECT 'DROP TABLE x' AS s FROM dim_date",           # chu DROP nam trong chuoi: hop le
    "SELECT * FROM (SELECT * FROM fact_sales) x",
]

WRITE = [
    "DROP TABLE fact_sales",
    "DELETE FROM fact_sales",
    "delete from fact_sales where 1=1",
    "INSERT INTO fact_sales SELECT * FROM fact_sales",
    "UPDATE dim_products SET description = 'x'",
    "CREATE TABLE gold.x AS SELECT * FROM fact_sales",
    "ALTER TABLE fact_sales ADD COLUMN x int",
    "TRUNCATE TABLE fact_sales",
    "SELECT * FROM fact_sales; DROP TABLE fact_sales",
    "SELECT 1 FROM dim_date;\nDELETE FROM fact_sales",
    "MERGE INTO fact_sales t USING dim_date s ON t.date_key = s.date_key WHEN MATCHED THEN DELETE",
    "GRANT SELECT ON fact_sales TO x",
    "SET SESSION query_max_run_time = '1h'",
    "USE iceberg.bronze",
    "CALL system.sync_partition_metadata('gold','x','FULL')",
    "SHOW TABLES",
    "EXPLAIN ANALYZE SELECT * FROM fact_sales",
    "SELECT * INTO t2 FROM fact_sales",
    "/* x */ DrOp /* y */ TABLE fact_sales",
]

BAD_TABLE = [
    "SELECT * FROM iceberg.bronze.online_retail",
    "SELECT * FROM silver.stg_sales",
    "SELECT * FROM system.runtime.queries",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM hive.gold.fact_sales",
    "SELECT * FROM secret_table",
    "WITH fact_sales AS (SELECT 1) SELECT * FROM iceberg.silver.fact_sales",
]


@pytest.mark.parametrize("sql", OK)
def test_ok(sql):
    out = check(sql)
    assert "LIMIT" in out.upper()


@pytest.mark.parametrize("sql", WRITE)
def test_write_rejected(sql):
    with pytest.raises(GuardError) as e:
        check(sql)
    assert e.value.write_attempt


@pytest.mark.parametrize("sql", BAD_TABLE)
def test_bad_table(sql):
    with pytest.raises(GuardError) as e:
        check(sql)
    assert not e.value.write_attempt


def test_empty_and_syntax():
    for s in ["", "   ", ";"]:
        with pytest.raises(GuardError):
            check(s)
    with pytest.raises(GuardError):
        check("SELECT FROM WHERE")


def test_limit_added_after_comment():
    out = check("SELECT * FROM fact_sales -- comment", max_rows=50)
    assert out.endswith("\nLIMIT 50")


def test_existing_limit_kept():
    out = check("SELECT * FROM fact_sales LIMIT 5", max_rows=50)
    assert out == "SELECT * FROM fact_sales LIMIT 5"
