-- Chieu quoc gia: chuan hoa ten va phan loai thi truong
select
    {{ dbt_utils.generate_surrogate_key(['country']) }} as country_key,
    country                                              as country_name,
    case country
        when 'EIRE'  then 'Ireland'
        when 'RSA'   then 'South Africa'
        when 'USA'   then 'United States'
        when 'Korea' then 'South Korea'
        else country
    end                                                  as country_name_std,
    case when country = 'United Kingdom' then 'Noi dia (UK)' else 'Quoc te' end as market
from (select distinct country from {{ ref('stg_sales') }}) c
