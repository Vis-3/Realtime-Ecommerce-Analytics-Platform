/*
  Mart: one row per calendar day with revenue KPIs.
  Airflow upserts the row for CURRENT_DATE - 1 into daily_report_log.
  Keeping all days in this mart means the data team can query trends
  directly without going back to the raw fact table.
*/
SELECT
    transaction_date                                    AS report_date,
    COUNT(DISTINCT user_id)                             AS total_users,
    COUNT(DISTINCT transaction_id)                      AS total_transactions,
    ROUND(SUM(total_amount)::numeric, 2)                AS total_revenue,
    ROUND(AVG(total_amount)::numeric, 2)                AS avg_order_value
FROM {{ ref('stg_transactions') }}
GROUP BY transaction_date
