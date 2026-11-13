-- Cac dong thuoc don huy (Invoice bat dau bang 'C'), phuc vu chi so quan ly huy don
select
    transaction_id,
    invoice,
    stock_code,
    description,
    quantity,
    price,
    cast(quantity * price as decimal(14, 3)) as cancelled_value,
    invoice_date,
    invoice_day,
    customer_id,
    country,
    current_timestamp() as processed_at
from {{ ref('stg_retail_transactions') }}
where is_cancelled
