/*
  Intermediate: compute raw RFM metrics and NTILE quintile scores per user.
  This is a view — it runs fresh each time mart_rfm_segments is built.

  NTILE(5) gives scores 1–5 where:
    r_score: 5 = most recent purchaser (low recency_days)
    f_score: 5 = most frequent purchaser
    m_score: 5 = highest spender
*/
WITH rfm_base AS (
    SELECT
        user_id,
        (CURRENT_DATE - MAX(transaction_date))::int  AS recency_days,
        COUNT(DISTINCT transaction_id)               AS frequency,
        SUM(total_amount)                            AS monetary,
        AVG(total_amount)                            AS avg_order_value,
        MIN(transaction_date)                        AS first_purchase_date,
        MAX(transaction_date)                        AS last_purchase_date
    FROM {{ ref('stg_transactions') }}
    GROUP BY user_id
)
SELECT
    user_id,
    recency_days,
    frequency,
    monetary,
    avg_order_value,
    first_purchase_date,
    last_purchase_date,
    NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
    NTILE(5) OVER (ORDER BY frequency)         AS f_score,
    NTILE(5) OVER (ORDER BY monetary)          AS m_score
FROM rfm_base
