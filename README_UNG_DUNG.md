# Tầng ứng dụng (mục 3.9): Streamlit Dashboard và Groq LLM Agent

Phần này thêm 2 container `streamlit` và `groq-agent` vào hệ thống. Bạn **không cần sửa** bất kỳ file nào có sẵn của nhóm.

## 1. Chép file vào thư mục dự án

Chép các file sau vào thư mục gốc của dự án (cùng chỗ với `docker-compose.yml`):

```
app/                      mã nguồn 2 container (Dockerfile dùng chung)
docker-compose.app.yml    khai báo 2 container mới
.env.example              mẫu file cấu hình khóa Groq
tests/                    kiểm thử offline (không bắt buộc)
```

## 2. Tạo khóa Groq

1. Vào https://console.groq.com/keys và tạo khóa (miễn phí).
2. Chép `.env.example` thành `.env` và điền `GROQ_API_KEY=...`.
3. Thêm dòng `.env` vào `.gitignore`. **Không** đưa file `.env` lên Git hay thư mục Drive chia sẻ công khai.

Mô hình mặc định là `openai/gpt-oss-120b`, vì Groq đã ngừng `llama-3.3-70b-versatile` từ ngày 16/08/2026. Muốn đổi mô hình thì sửa `GROQ_MODEL` trong `.env`.

## 3. Chạy

Hệ thống phải đã có tầng Gold (đã chạy bronze_ingest và dbt). Mô hình Prophet phải đã chạy `model_retrain_dag` ít nhất một lần thì tab Dự báo mới có dữ liệu.

```
docker compose -f docker-compose.yml -f docker-compose.app.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.app.yml ps
```

Từ đây, mọi lệnh `docker compose` đều phải kèm cả hai tham số `-f` như trên.

| Địa chỉ | Nội dung |
|---|---|
| http://localhost:8501 | Dashboard 3 tab, Trợ lý AI ở thanh bên |
| http://localhost:8000/docs | API của Agent, thử câu hỏi trực tiếp |
| http://localhost:8000/health | Trạng thái Agent (có khóa Groq hay chưa) |

Chạy 3 kịch bản kiểm thử của mục 4.4:

```
docker exec -it groq-agent python -m agent.cli --demo
docker exec -it groq-agent python -m agent.cli "Top 5 best-selling products?"
```

Sau khi sửa code trong `app/`, phải build lại image:

```
docker compose -f docker-compose.yml -f docker-compose.app.yml up -d --build streamlit groq-agent
```

## 4. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| Tab 1 báo "Không truy vấn được tầng Gold" | Kiểm tra Trino đã chạy và đã `dbt build` xong |
| Tab 2 báo "Model Registry chưa có mô hình đạt nghiệm thu" | Chạy `model_retrain_dag` trên Airflow |
| Thanh bên báo "groq-agent chưa có GROQ_API_KEY" | Điền khóa vào `.env`, rồi chạy lại lệnh `up -d` |
| Agent báo lỗi model không tồn tại | Mô hình trên Groq đã ngừng, đổi `GROQ_MODEL` (xem console.groq.com/docs/deprecations) |
| Cổng 8000 hoặc 8501 đã bị chiếm | Đổi số cổng bên trái trong `docker-compose.app.yml` |

## 5. Kiểm thử offline (không cần Docker)

Chạy tại thư mục gốc dự án:

```
pip install -r app/requirements.txt duckdb==1.1.3 openpyxl "moto[server]==5.1.10" pytest
python tests/build_mock_gold.py data/online_retail.xlsx tests/mock_gold.duckdb
PYTHONPATH=app:tests pytest -q tests
```

Kết quả mong đợi: `55 passed`. Bản Gold dựng lại cho 1.007.902 dòng `fact_sales` và tổng doanh thu 20.464.972,39 £, khớp với mục 3.6.4. File `tests/mock_gold.duckdb` đã được `tests/.gitignore` loại khỏi Git.
