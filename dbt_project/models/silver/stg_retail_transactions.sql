-- Model trung gian tang Silver
-- Buoc 1: ep kieu, TRIM | Buoc 2: khu trung lap | Buoc 3: Customer ID NULL -> 'UNKNOWN'
-- Buoc 4: gan co don huy (is_cancelled)
with ranked as (
    select
        *,
        row_number() over (
            partition by invoice, stock_code, description, quantity,
                         invoice_date, price, customer_id, country
            order by _source_sheet, _source_row
        ) as rn
    from {{ source('bronze', 'online_retail') }}
)

select
    {{ md5_key("concat(_source_sheet, '|', cast(_source_row as string))") }} as transaction_id,
    trim(invoice)                               as invoice,
    upper(trim(stock_code))                     as stock_code,
    trim(description)                           as description,
    cast(quantity as int)                       as quantity,
    cast(price as decimal(12, 3))               as price,
    cast(invoice_date as timestamp_ntz)         as invoice_date,
    cast(invoice_date as date)                  as invoice_day,
    coalesce(trim(customer_id), 'UNKNOWN')      as customer_id,
    customer_id is null                         as is_guest,
    trim(country)                               as country,
    trim(invoice) like 'C%'                     as is_cancelled,
    _source_sheet,
    _source_row
from ranked
where rn = 1
