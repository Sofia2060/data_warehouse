"""May chu gia lap API Groq (OpenAI-compatible) de kiem tra thu vien groq gui dung tham so.
Buoc sinh SQL (co response_format json) tra ve SQL theo tu khoa trong cau hoi; buoc dien giai tra ve van ban."""
import json
import time

import uvicorn
from fastapi import FastAPI, Request

SCENARIOS = {
    "best-selling": """SELECT p.stock_code, p.description, sum(f.quantity) AS total_quantity,
       round(sum(f.line_revenue), 2) AS revenue
FROM fact_sales f
JOIN dim_products p ON f.product_key = p.product_key
WHERE p.product_type = 'San pham'
GROUP BY p.stock_code, p.description
ORDER BY total_quantity DESC
LIMIT 5""",
    "xuất khẩu": """SELECT co.country_name_std AS country, round(sum(f.line_revenue), 2) AS revenue,
       count(DISTINCT f.invoice_no) AS orders
FROM fact_sales f
JOIN dim_country co ON f.country_key = co.country_key
WHERE co.market = 'Quoc te'
GROUP BY co.country_name_std
ORDER BY revenue DESC
LIMIT 5""",
    "Pareto": """WITH product_revenue AS (
    SELECT p.stock_code, sum(f.line_revenue) AS revenue
    FROM fact_sales f
    JOIN dim_products p ON f.product_key = p.product_key
    WHERE p.product_type = 'San pham'
    GROUP BY p.stock_code
), ranked AS (
    SELECT stock_code, revenue,
           sum(revenue) OVER (ORDER BY revenue DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / sum(revenue) OVER () AS cum_share
    FROM product_revenue
)
SELECT CASE WHEN cum_share <= 0.80 THEN 'A' WHEN cum_share <= 0.95 THEN 'B' ELSE 'C' END AS pareto_group,
       count(*) AS product_count, round(sum(revenue), 2) AS revenue,
       round(100 * sum(revenue) / (SELECT sum(revenue) FROM product_revenue), 2) AS revenue_share_pct
FROM ranked
GROUP BY 1
ORDER BY 1""",
    "xóa": "DELETE FROM fact_sales",
}

app = FastAPI()
LOG = []


@app.post("/openai/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    LOG.append(body)
    if body.get("response_format", {}).get("type") == "json_object":
        q = next(m["content"] for m in body["messages"] if m["role"] == "user")
        sql = next((s for k, s in SCENARIOS.items() if k.lower() in q.lower()), None)
        content = json.dumps({"sql": sql, "note": "giả lập"} if sql else {"sql": None, "note": "Ngoài phạm vi dữ liệu."},
                             ensure_ascii=False)
    else:
        content = "Kết quả (giả lập, chưa gọi Groq thật): xem bảng dữ liệu bên dưới."
    return {"id": "x", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


@app.get("/log")
def log():
    return LOG


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8899, log_level="warning")
