-- Bang phang theo ngay cho Machine Learning (Prophet)
with daily as (
    select
        cast(invoice_datetime as date)  as sale_date,
        sum(line_revenue)               as total_revenue,
        count(distinct invoice_no)      as total_orders,
        sum(quantity)                   as total_quantity
    from {{ ref('fact_sales') }}
    group by 1
),
cancel as (
    select invoice_day as sale_date, sum(cancelled_value) as cancelled_revenue
    from {{ ref('stg_cancellations') }}
    group by 1
),
joined as (
    select
        d.full_date                                         as sale_date,
        coalesce(s.total_revenue, 0)                        as total_revenue,
        coalesce(c.cancelled_revenue, 0)                    as cancelled_revenue,
        coalesce(s.total_orders, 0)                         as total_orders,
        coalesce(s.total_quantity, 0)                       as total_quantity,
        d.day_of_week, d.month, d.year, d.is_weekend
    from {{ ref('dim_date') }} d
    left join daily  s on d.full_date = s.sale_date
    left join cancel c on d.full_date = c.sale_date
)
select
    sale_date,
    total_revenue,
    cancelled_revenue,
    total_revenue + cancelled_revenue                       as net_revenue,
    total_orders,
    total_quantity,
    case when total_orders > 0
         then cast(total_revenue / total_orders as decimal(14, 2)) end as avg_order_value,
    day_of_week, month, year, is_weekend,
    total_orders > 0                                        as is_trading_day,
    avg(total_revenue) over (order by sale_date
        rows between 6 preceding and current row)           as rolling_mean_7d,
    avg(total_revenue) over (order by sale_date
        rows between 29 preceding and current row)          as rolling_mean_30d
from joined
