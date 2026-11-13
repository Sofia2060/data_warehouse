-- Chieu thoi gian: chuoi ngay lien tuc tu ngay giao dich dau tien den cuoi cung
with bounds as (
    select min(invoice_day) as d0, max(invoice_day) as d1
    from {{ ref('stg_retail_transactions') }}
),
spine as (
    select explode(sequence(d0, d1, interval 1 day)) as full_date
    from bounds
)
select
    cast(date_format(full_date, 'yyyyMMdd') as int) as date_key,
    full_date,
    dayofmonth(full_date)                           as day,
    month(full_date)                                as month,
    date_format(full_date, 'MMMM')                  as month_name,
    quarter(full_date)                              as quarter,
    year(full_date)                                 as year,
    weekday(full_date) + 1                          as day_of_week,   -- 1 = Thu Hai ... 7 = Chu Nhat
    date_format(full_date, 'EEEE')                  as day_name,
    weekday(full_date) >= 5                         as is_weekend
from spine
