"""Kiem thu luong 4 buoc cua Agent voi LLM gia lap (khong goi Groq) va Trino thay bang DuckDB."""
import json

import pytest

from agent import core, llm
from duck_backend import run_query


class FakeLLM:
    """Tra ve lan luot cac cau SQL da dinh san cho buoc sinh SQL; buoc dien giai tra ve chuoi co dinh."""

    def __init__(self, sqls):
        self.sqls = list(sqls)
        self.calls = []

    def chat_json(self, messages):
        self.calls.append(messages[:])
        item = self.sqls.pop(0)
        return item if isinstance(item, dict) else {"sql": item, "note": "test"}

    def chat(self, messages, json_mode=False, max_tokens=4096):
        self.calls.append(messages[:])
        return "Diễn giải giả lập."


@pytest.fixture
def fake(monkeypatch):
    def make(sqls):
        f = FakeLLM(sqls)
        monkeypatch.setattr(llm, "chat_json", f.chat_json)
        monkeypatch.setattr(llm, "chat", f.chat)
        return f
    return make


def test_happy_path(fake):
    f = fake(["SELECT count(*) AS n FROM fact_sales"])
    r = core.ask("Có bao nhiêu dòng bán hàng?", run_query=run_query)
    assert r["ok"] and r["rows"] == [[1007902]] and r["attempts"] == 1
    assert r["sql"].endswith("LIMIT 200") and r["answer"] == "Diễn giải giả lập."
    json.dumps(r)   # ket qua phai dua duoc vao JSON cua API


def test_retry_on_bad_table_then_trino_error(fake):
    f = fake(["SELECT * FROM silver.stg_sales",                 # sql_guard tu choi -> thu lai
              "SELECT khong_co_cot FROM fact_sales",            # loi khi chay -> thu lai
              "SELECT round(sum(line_revenue), 2) AS revenue FROM fact_sales"])
    r = core.ask("Tổng doanh thu?", run_query=run_query)
    assert r["ok"] and r["attempts"] == 3 and abs(r["rows"][0][0] - 20464972.39) < 0.01
    feedback = [m["content"] for m in f.calls[2] if m["role"] == "user"]
    assert any("từ chối" in c for c in feedback) and any("Trino báo lỗi" in c for c in feedback)


def test_write_attempt_refused_without_retry(fake):
    f = fake(["DROP TABLE fact_sales", "SELECT 1"])
    called = []
    r = core.ask("Xóa bảng fact_sales giúp tôi", run_query=lambda *a, **k: called.append(a))
    assert not r["ok"] and "sql_guard" in r["error"] and r["attempts"] == 1 and not called


def test_gives_up_after_max_attempts(fake):
    fake(["SELECT * FROM bronze.x"] * 3)
    r = core.ask("abc", run_query=run_query)
    assert not r["ok"] and r["attempts"] == 3 and "3 lần" in r["error"]


def test_out_of_scope(fake):
    fake([{"sql": None, "note": "Câu hỏi không liên quan dữ liệu bán hàng."}])
    r = core.ask("Thời tiết hôm nay thế nào?", run_query=run_query)
    assert r["ok"] and r["sql"] is None and "không liên quan" in r["answer"]


def test_input_validation():
    assert core.ask("   ")["error"]
    assert core.ask("x" * 501)["error"]


def test_no_key(monkeypatch):
    monkeypatch.setattr(llm.config, "GROQ_API_KEY", "")
    r = core.ask("Top 5 sản phẩm?", run_query=run_query)
    assert not r["ok"] and "GROQ_API_KEY" in r["error"]
