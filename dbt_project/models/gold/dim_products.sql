-- Chieu san pham: moi stock_code 1 dong, lay mo ta moi nhat
select
    {{ dbt_utils.generate_surrogate_key(['stock_code']) }} as product_key,
    stock_code,
    max_by(description, invoice_date)                       as description,
    case when bool_or(is_non_product) then 'Phi dich vu' else 'San pham' end as product_type,
    min(invoice_day)                                        as first_sold_date
from {{ ref('stg_sales') }}
group by stock_code
