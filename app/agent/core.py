"""
core.py - Luong xu ly cua Groq LLM Agent (Text-to-SQL) gom 4 buoc:

  1. Tiep nhan cau hoi ngon ngu tu nhien (tieng Viet hoac tieng Anh).
  2. Sinh SQL: gui cau hoi + mo ta schema Gold cho LLM, nhan ve JSON {"sql", "note"}.
  3. Kiem soat an toan: sql_guard chi cho phep SELECT tren 6 bang Gold, tu them LIMIT.
     Neu SQL sai cu phap / sai bang / Trino bao loi -> gui loi lai cho LLM sua (toi da AGENT_MAX_ATTEMPTS lan).
     Neu SQL co y dinh ghi/xoa du lieu -> tu choi ngay, khong thu lai.
  4. Thuc thi tren Trino (user "groq-agent"), gui bang ket qua cho LLM dien giai thanh cau tra loi.
"""
import json
import time

from agent import llm, sql_guard
from agent.schema_context import ANSWER_SYSTEM_PROMPT, SQL_SYSTEM_PROMPT
from common import config, trino_client

MAX_QUESTION_LENGTH = 500


def _result(question, **kw):
    base = {"question": question, "ok": False, "sql": None, "note": None, "columns": [], "rows": [],
            "row_count": 0, "answer": None, "error": None, "attempts": 0, "elapsed_s": None}
    base.update(kw)
    return base


def ask(question: str, run_query=None) -> dict:
    """run_query: ham thuc thi SQL (mac dinh Trino); tham so de thay the khi kiem thu."""
    run_query = run_query or trino_client.run_query
    t0 = time.time()
    question = (question or "").strip()
    if not question:
        return _result(question, error="Câu hỏi rỗng.")
    if len(question) > MAX_QUESTION_LENGTH:
        return _result(question, error=f"Câu hỏi dài quá {MAX_QUESTION_LENGTH} ký tự.")

    messages = [{"role": "system", "content": SQL_SYSTEM_PROMPT},
                {"role": "user", "content": question}]
    sql, note, df, last_error = None, None, None, None
    attempts = 0
    for attempts in range(1, config.AGENT_MAX_ATTEMPTS + 1):
        # ---- Buoc 2: sinh SQL
        try:
            out = llm.chat_json(messages)
        except llm.LLMError as exc:
            return _result(question, error=str(exc), attempts=attempts, elapsed_s=round(time.time() - t0, 2))
        raw_sql, note = out.get("sql"), out.get("note")
        if not raw_sql:
            # LLM cho rang cau hoi nam ngoai pham vi du lieu
            return _result(question, ok=True, note=note, answer=note or "Câu hỏi nằm ngoài phạm vi dữ liệu.",
                           attempts=attempts, elapsed_s=round(time.time() - t0, 2))
        messages.append({"role": "assistant", "content": json.dumps(out, ensure_ascii=False)})

        # ---- Buoc 3: kiem soat an toan
        try:
            sql = sql_guard.check(str(raw_sql), max_rows=config.AGENT_MAX_ROWS)
        except sql_guard.GuardError as exc:
            if exc.write_attempt:
                return _result(question, sql=str(raw_sql), note=note, attempts=attempts,
                               error=f"sql_guard từ chối: {exc}", elapsed_s=round(time.time() - t0, 2))
            last_error = f"sql_guard: {exc}"
            messages.append({"role": "user", "content": f"Câu SQL bị từ chối ({exc}). Hãy sửa và trả lại JSON."})
            continue

        # ---- Buoc 4a: thuc thi tren Trino
        try:
            df = run_query(sql, user="groq-agent", max_rows=config.AGENT_MAX_ROWS)
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001 - loi cot/ham khong ton tai, het thoi gian...
            last_error = f"Trino: {str(exc)[:500]}"
            messages.append({"role": "user", "content": f"Trino báo lỗi khi chạy câu SQL: {str(exc)[:500]}. "
                                                         "Hãy sửa câu SQL và trả lại JSON."})

    if df is None:
        return _result(question, sql=sql, note=note, attempts=attempts,
                       error=f"Không tạo được câu SQL hợp lệ sau {attempts} lần thử. Lỗi cuối: {last_error}",
                       elapsed_s=round(time.time() - t0, 2))

    # ---- Buoc 4b: dien giai ket qua
    preview = df.head(config.AGENT_ROWS_TO_LLM).to_csv(index=False)
    try:
        answer = llm.chat([
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Câu hỏi: {question}\n\nSQL:\n{sql}\n\n"
                                        f"Kết quả ({len(df)} dòng, hiển thị tối đa {config.AGENT_ROWS_TO_LLM}):\n{preview}"},
        ], max_tokens=2048)
    except llm.LLMError as exc:
        answer = f"(Không diễn giải được kết quả: {exc})"

    return _result(question, ok=True, sql=sql, note=note, columns=list(df.columns),
                   rows=trino_client.to_jsonable(df), row_count=len(df), answer=answer,
                   attempts=attempts, elapsed_s=round(time.time() - t0, 2))
