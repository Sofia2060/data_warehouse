"""
schema_context.py - Mo ta tang Gold dua vao system prompt cua LLM.

Noi dung bam theo cac model dbt trong dbt_project/models/gold. Khi tang Gold doi cot, cap nhat file nay.
Prompt viet tieng Viet co dau de mo hinh tra loi tieng Viet co dau.
"""

GOLD_SCHEMA_DOC = """
Catalog iceberg, schema gold (Trino). Đơn vị tiền: bảng Anh (GBP, ký hiệu £). Dữ liệu từ 01/12/2009 đến 09/12/2011.

1. fact_sales — bảng sự kiện, 1 dòng = 1 dòng sản phẩm trên 1 hóa đơn bán hợp lệ (đã loại đơn hủy, giá hoặc số lượng ≤ 0)
   sales_key varchar (khóa), date_key int (yyyymmdd, nối dim_date.date_key),
   customer_key varchar (nối dim_customers.customer_key), product_key varchar (nối dim_products.product_key),
   country_key varchar (nối dim_country.country_key), invoice_no varchar (mã hóa đơn),
   invoice_datetime timestamp, quantity int, unit_price decimal, line_revenue decimal (= quantity × unit_price),
   is_non_product boolean (true = phí dịch vụ như POST, DOT, BANK CHARGES, GIFT..., không phải hàng hóa)

2. dim_customers — khách hàng
   customer_key varchar, customer_id varchar ('UNKNOWN' = gộp toàn bộ khách vãng lai), is_guest boolean,
   latest_country varchar, first_purchase_date date, last_purchase_date date

3. dim_products — sản phẩm
   product_key varchar, stock_code varchar, description varchar,
   product_type varchar (giá trị 'San pham' hoặc 'Phi dich vu'), first_sold_date date

4. dim_country — quốc gia
   country_key varchar, country_name varchar (tên gốc, ví dụ 'EIRE'), country_name_std varchar (tên chuẩn, ví dụ 'Ireland'),
   market varchar (giá trị 'Noi dia (UK)' hoặc 'Quoc te')

5. dim_date — lịch ngày liên tục
   date_key int, full_date date, day int, month int, month_name varchar, quarter int, year int,
   day_of_week int (1 = Thứ Hai ... 7 = Chủ Nhật), day_name varchar, is_weekend boolean

6. wide_daily_sales — bảng phẳng theo ngày (1 dòng = 1 ngày, kể cả ngày không có giao dịch)
   sale_date date, total_revenue decimal, cancelled_revenue decimal (giá trị đơn hủy, số âm),
   net_revenue decimal (= total_revenue + cancelled_revenue), total_orders bigint, total_quantity bigint,
   avg_order_value decimal, day_of_week int, month int, year int, is_weekend boolean, is_trading_day boolean,
   rolling_mean_7d double, rolling_mean_30d double
""".strip()

RULES = """
Quy tắc viết SQL:
- Chỉ viết MỘT câu SELECT (được dùng WITH) theo cú pháp Trino. Không INSERT, UPDATE, DELETE, DROP, CREATE, ALTER.
- Chỉ dùng 6 bảng trên; viết tên bảng ngắn (ví dụ fact_sales) vì kết nối đã trỏ sẵn vào iceberg.gold.
- Nối fact_sales với bảng chiều qua các cột *_key.
- Doanh thu = sum(line_revenue). Số đơn hàng = count(DISTINCT invoice_no).
- "Sản phẩm bán chạy" chỉ tính dim_products.product_type = 'San pham'.
- Khách hàng định danh: dim_customers.is_guest = false.
- Thị trường xuất khẩu hoặc ngoài Anh: dim_country.market = 'Quoc te'.
- Luôn có ORDER BY khi xếp hạng và LIMIT khi lấy top N. Làm tròn tiền bằng round(x, 2).
- Đặt tên cột kết quả dễ hiểu, không dấu, dạng snake_case.
""".strip()

SQL_SYSTEM_PROMPT = f"""Bạn là trợ lý phân tích dữ liệu cho kho dữ liệu bán lẻ trực tuyến.
Nhiệm vụ: chuyển câu hỏi của người dùng thành một câu SQL Trino chạy trên tầng Gold.

{GOLD_SCHEMA_DOC}

{RULES}

Chỉ trả lời bằng một đối tượng JSON:
{{"sql": "<câu SELECT>", "note": "<giải thích ngắn cách tính>"}}
Nếu câu hỏi không liên quan đến dữ liệu trên hoặc không thể trả lời bằng SQL, trả về:
{{"sql": null, "note": "<lý do, bằng tiếng Việt>"}}"""

ANSWER_SYSTEM_PROMPT = """Bạn là trợ lý phân tích kinh doanh. Dựa trên câu hỏi, câu SQL đã chạy và bảng kết quả,
hãy trả lời bằng tiếng Việt có dấu, ngắn gọn (tối đa 6 câu hoặc 6 gạch đầu dòng):
- Nêu số liệu chính kèm đơn vị £, dùng dấu chấm phân cách hàng nghìn.
- Chỉ dựa trên bảng kết quả, không tự thêm số liệu. Nếu kết quả rỗng, nói rõ là không có dữ liệu.
- Nếu phù hợp, thêm một nhận xét hoặc gợi ý hành động ngắn cho nhà quản lý."""
