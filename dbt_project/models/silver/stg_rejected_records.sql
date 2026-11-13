-- Ban ghi loi bi loai khoi luong ban hang, kem ly do (phuc vu kiem toan du lieu)
select
    t.*,
    case
        when t.invoice like 'A%'                                  then 'Dieu chinh no xau (A)'
        when t.stock_code like 'TEST%'
          or lower(coalesce(t.description, '')) like '%test%'     then 'San pham thu nghiem'
        when t.quantity <= 0                                      then 'Dieu chinh ton kho (quantity <= 0)'
        when t.price <= 0                                         then 'Gia khong hop le (price <= 0)'
    end as reject_reason
from {{ ref('stg_retail_transactions') }} t
where not t.is_cancelled
  and (t.price <= 0
       or t.quantity <= 0
       or t.invoice like 'A%'
       or t.stock_code like 'TEST%'
       or lower(coalesce(t.description, '')) like '%test%')
