"""
sql_guard.py - Lop kiem soat an toan cho cau SQL do LLM sinh ra (chi cho phep SELECT tren tang Gold).

Kiem tra tren cay cu phap (AST) bang sqlglot thay vi so khop chuoi, nen khong bi qua mat boi
chu hoa/thuong, chu thich hay khoang trang. Cac lop kiem tra:
  1. Do dai va noi dung khong rong.
  2. Dung MOT cau lenh (chan "SELECT ...; DROP ...").
  3. Cau lenh goc la truy van doc (SELECT hoac UNION/INTERSECT/EXCEPT cua cac SELECT).
  4. Trong toan bo cay khong co nut ghi/thay doi du lieu (INSERT, UPDATE, DELETE, MERGE, DROP,
     CREATE, ALTER, TRUNCATE, GRANT, SET, USE, SELECT ... INTO, lenh khong phan tich duoc ...).
  5. Chi doc 6 bang Gold cho phep (hoac CTE tu dat ten); chan system.*, information_schema, schema khac.
  6. Them LIMIT neu truy van ngoai cung chua co, de khong tra ve hang trieu dong.
"""
import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

logging.getLogger("sqlglot").setLevel(logging.ERROR)

ALLOWED_TABLES = {"fact_sales", "dim_customers", "dim_products", "dim_date", "dim_country",
                  "wide_daily_sales"}
ALLOWED_SCHEMA = "gold"
ALLOWED_CATALOG = "iceberg"
MAX_SQL_LENGTH = 5000

_FORBIDDEN_NODES = tuple(getattr(exp, name) for name in (
    "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "TruncateTable",
    "Command", "Set", "Use", "Grant", "Into", "LoadData", "Copy", "Describe", "Transaction",
    "Commit", "Rollback", "Pragma", "Analyze", "Refresh", "Cache", "Uncache", "Comment",
) if hasattr(exp, name))
_READ_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)


class GuardError(Exception):
    """SQL bi tu choi. write_attempt=True khi cau lenh co y dinh ghi/thay doi du lieu."""

    def __init__(self, message: str, write_attempt: bool = False):
        super().__init__(message)
        self.write_attempt = write_attempt


def check(sql: str, max_rows: int = 200) -> str:
    """Tra ve cau SQL an toan de thuc thi, hoac nem GuardError."""
    if not sql or not sql.strip():
        raise GuardError("Câu SQL rỗng.")
    text = sql.strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    if len(text) > MAX_SQL_LENGTH:
        raise GuardError(f"Câu SQL dài quá {MAX_SQL_LENGTH} ký tự.")

    try:
        statements = [s for s in sqlglot.parse(text, read="trino") if s is not None]
    except ParseError as exc:
        raise GuardError(f"Câu SQL sai cú pháp Trino: {str(exc).splitlines()[0]}") from exc
    if len(statements) != 1:
        raise GuardError("Chỉ được phép một câu lệnh SQL.", write_attempt=len(statements) > 1)
    stmt = statements[0]

    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise GuardError(f"Chỉ cho phép truy vấn đọc (SELECT); phát hiện lệnh {type(node).__name__.upper()}.",
                             write_attempt=True)
    if not isinstance(stmt, _READ_ROOTS):
        raise GuardError(f"Chỉ cho phép truy vấn SELECT, không cho phép {type(stmt).__name__.upper()}.",
                         write_attempt=True)

    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    for table in stmt.find_all(exp.Table):
        name = (table.name or "").lower()
        db = (table.db or "").lower()
        catalog = (table.catalog or "").lower()
        if not name:
            raise GuardError("Không cho phép đọc từ hàm bảng (table function).")
        if name in cte_names and not db and not catalog:
            continue
        if name not in ALLOWED_TABLES or db not in ("", ALLOWED_SCHEMA) or catalog not in ("", ALLOWED_CATALOG):
            full = ".".join(p for p in (catalog, db, name) if p)
            raise GuardError(f"Bảng '{full}' không nằm trong 6 bảng Gold được phép: "
                             + ", ".join(sorted(ALLOWED_TABLES)) + ".")

    if stmt.args.get("limit") is None and stmt.args.get("fetch") is None:
        # Xuong dong truoc LIMIT de khong bi mot chu thich "--" o cuoi cau nuot mat
        text = f"{text}\nLIMIT {max_rows}"
    return text
