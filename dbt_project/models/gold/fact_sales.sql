-- Bang su kien: 1 dong = 1 dong san pham tren 1 hoa don
select
    s.transaction_id                                          as sales_key,
    cast(date_format(s.invoice_day, 'yyyyMMdd') as int)       as date_key,
    {{ dbt_utils.generate_surrogate_key(['s.customer_id']) }} as customer_key,
    {{ dbt_utils.generate_surrogate_key(['s.stock_code']) }}  as product_key,
    {{ dbt_utils.generate_surrogate_key(['s.country']) }}     as country_key,
    s.invoice                                                 as invoice_no,
    s.invoice_date                                            as invoice_datetime,
    s.quantity,
    s.price                                                   as unit_price,
    s.line_revenue,
    s.is_non_product
from {{ ref('stg_sales') }} s
