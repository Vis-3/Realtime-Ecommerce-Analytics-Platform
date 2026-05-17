/*
  Mart: apply business segment labels to RFM scores.
  Materialized as a TABLE so Airflow can do a single bulk UPDATE
  from this table back to users.customer_segment.

  Segment thresholds match the original inline SQL in daily_analytics_dag.py
  but are now tested (accepted_values in schema.yml) and documented here.
*/
SELECT
    user_id,
    recency_days,
    frequency,
    monetary::numeric(14, 2)        AS monetary,
    avg_order_value::numeric(10, 2) AS avg_order_value,
    r_score,
    f_score,
    m_score,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 4                   THEN 'Loyal Customers'
        WHEN r_score >= 4 AND f_score >= 3                   THEN 'Potential Loyalists'
        WHEN r_score >= 4 AND f_score <= 2                   THEN 'New Customers'
        WHEN r_score >= 3 AND m_score >= 4                   THEN 'Promising'
        WHEN r_score >= 3 AND f_score >= 3                   THEN 'Need Attention'
        WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4  THEN 'At Risk'
        WHEN r_score <= 1 AND f_score >= 4 AND m_score >= 4  THEN 'Cannot Lose Them'
        WHEN r_score <= 2 AND f_score >= 3                   THEN 'About to Sleep'
        WHEN r_score <= 2 AND f_score <= 2                   THEN 'Hibernating'
        WHEN r_score <= 1                                    THEN 'Lost'
        ELSE                                                      'Other'
    END                             AS customer_segment,
    CURRENT_TIMESTAMP               AS computed_at
FROM {{ ref('int_rfm_scores') }}
