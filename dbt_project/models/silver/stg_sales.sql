-- Giao dich ban hang hop le (Buoc 5: loc loi, Buoc 6: tinh line_revenue)
{{ config(
    materialized='incremental',
    unique_key='transaction_id',
    incremental_strategy='merge'
) }}

select
    t.transaction_id,
    t.invoice,
    t.stock_code,
    t.description,
    t.quantity,
    t.price,
    t.invoice_date,
    t.invoice_day,
    t.customer_id,
    t.is_guest,
    t.country,
    cast(t.quantity * t.price as decimal(14, 3))      as line_revenue,
    (t.stock_code in ('POST', 'DOT', 'C2', 'M', 'D', 'S', 'BANK CHARGES', 'ADJUST',
                      'ADJUST2', 'AMAZONFEE', 'CRUK', 'PADS', 'B')
       or t.stock_code like 'GIFT%')                  as is_non_product,
    current_timestamp()                               as processed_at
from {{ ref('stg_retail_transactions') }} t
where not t.is_cancelled
  and t.price > 0
  and t.quantity > 0
  and t.invoice not like 'A%'
  and t.stock_code not like 'TEST%'
  and lower(coalesce(t.description, '')) not like '%test%'
{% if is_incremental() %}
  and t.invoice_date > (select max(invoice_date) from {{ this }})
{% endif %}
