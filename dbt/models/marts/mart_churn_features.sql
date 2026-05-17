/*
  Mart: the 7 features the XGBoost churn model is trained on.
  Centralising feature engineering here means:
    1. train_model.py and the API both reference the same definitions
    2. any feature change is one edit — not split across Python and SQL
    3. dbt tests catch null features before a retraining run starts

  Feature definitions:
    recency_days      days since last purchase
    frequency         total distinct orders
    monetary          cumulative spend ($)
    avg_order_value   mean order size ($)
    tenure_days       days since first purchase
    purchase_velocity orders per day over lifetime
    recency_ratio     recency_days / tenure_days (1 = never bought again)
*/
WITH base AS (
    SELECT
        user_id,
        (CURRENT_DATE - MAX(transaction_date))::int  AS recency_days,
        COUNT(DISTINCT transaction_id)               AS frequency,
        SUM(total_amount)                            AS monetary,
        AVG(total_amount)                            AS avg_order_value,
        (CURRENT_DATE - MIN(transaction_date))::int  AS tenure_days,
        MAX(transaction_date)                        AS last_purchase_date,
        MIN(transaction_date)                        AS first_purchase_date
    FROM {{ ref('stg_transactions') }}
    GROUP BY user_id
)
SELECT
    user_id,
    recency_days,
    frequency,
    monetary::numeric(14, 2)        AS monetary,
    avg_order_value::numeric(10, 2) AS avg_order_value,
    tenure_days,
    CASE WHEN tenure_days > 0
         THEN ROUND(frequency::numeric / tenure_days, 6)
         ELSE 0
    END                             AS purchase_velocity,
    CASE WHEN tenure_days > 0
         THEN ROUND(recency_days::numeric / tenure_days, 4)
         ELSE 1
    END                             AS recency_ratio,
    last_purchase_date,
    first_purchase_date,
    CURRENT_TIMESTAMP               AS computed_at
FROM base
