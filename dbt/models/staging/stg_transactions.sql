/*
  Staging layer: clean and type-cast raw transactions.
  Filters out rows with null users or negative amounts before
  any downstream transformation sees them.
*/
SELECT
    transaction_id,
    user_id,
    product_id,
    transaction_date::date   AS transaction_date,
    quantity,
    unit_price::numeric      AS unit_price,
    total_amount::numeric    AS total_amount,
    discount_amount::numeric AS discount_amount,
    payment_method,
    order_status
FROM {{ source('ecommerce', 'transactions') }}
WHERE user_id      IS NOT NULL
  AND total_amount >= 0
