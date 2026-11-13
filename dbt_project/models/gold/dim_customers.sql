-- Chieu khach hang (SCD Type 1: luu quoc gia gan nhat)
with known as (
    select
        customer_id,
        max_by(country, invoice_date) as latest_country,
        min(invoice_day)              as first_purchase_date,
        max(invoice_day)              as last_purchase_date
    from {{ ref('stg_sales') }}
    where customer_id <> 'UNKNOWN'
    group by customer_id
)
select
    {{ dbt_utils.generate_surrogate_key(['customer_id']) }} as customer_key,
    customer_id,
    false as is_guest,
    latest_country,
    first_purchase_date,
    last_purchase_date
from known

union all

-- 1 dong dai dien cho toan bo khach vang lai
select
    {{ dbt_utils.generate_surrogate_key(["'UNKNOWN'"]) }},
    'UNKNOWN',
    true,
    cast(null as string),
    cast(null as date),
    cast(null as date)
