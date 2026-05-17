SELECT
    user_id,
    email,
    persona,
    customer_segment,
    registration_date,
    country,
    age_group,
    churn_risk_score
FROM {{ source('ecommerce', 'users') }}
WHERE user_id IS NOT NULL
