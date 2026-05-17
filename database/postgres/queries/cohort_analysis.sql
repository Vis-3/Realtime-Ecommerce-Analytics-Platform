-- ============================================
-- COHORT RETENTION ANALYSIS
-- ============================================
-- Analyzes customer retention by registration cohort
-- Shows how many customers from each month return to purchase

WITH user_cohorts AS (
    -- Get each user's cohort (month of registration) and purchase months
    SELECT
        u.user_id,
        DATE_TRUNC('month', u.registration_date) as cohort_month,
        DATE_TRUNC('month', t.transaction_date) as transaction_month,
        t.total_amount
    FROM users u
    LEFT JOIN transactions t ON u.user_id = t.user_id
),
cohort_sizes AS (
    -- Calculate the size of each cohort
    SELECT
        cohort_month,
        COUNT(DISTINCT user_id) as cohort_size
    FROM user_cohorts
    GROUP BY cohort_month
),
cohort_data AS (
    -- Count active users per cohort per month
    SELECT
        uc.cohort_month,
        uc.transaction_month,
        COUNT(DISTINCT uc.user_id) as active_users,
        SUM(uc.total_amount) as cohort_revenue,
        cs.cohort_size
    FROM user_cohorts uc
    JOIN cohort_sizes cs ON uc.cohort_month = cs.cohort_month
    WHERE uc.transaction_month IS NOT NULL
    GROUP BY uc.cohort_month, uc.transaction_month, cs.cohort_size
)
SELECT
    cohort_month,
    cohort_size,
    transaction_month,
    active_users,
    cohort_revenue,
    -- Calculate retention rate
    ROUND(100.0 * active_users / cohort_size, 2) as retention_rate,
    -- Calculate months since cohort start
    EXTRACT(YEAR FROM AGE(transaction_month, cohort_month)) * 12 +
    EXTRACT(MONTH FROM AGE(transaction_month, cohort_month)) as months_since_registration,
    -- Calculate revenue per user
    ROUND(cohort_revenue / active_users, 2) as revenue_per_active_user
FROM cohort_data
ORDER BY cohort_month, transaction_month;

-- ============================================
-- COHORT LIFETIME VALUE PROJECTION
-- ============================================
-- Projects customer lifetime value based on cohort behavior

WITH cohort_revenue AS (
    SELECT
        DATE_TRUNC('month', u.registration_date) as cohort_month,
        u.user_id,
        EXTRACT(YEAR FROM AGE(t.transaction_date, u.registration_date)) * 12 +
        EXTRACT(MONTH FROM AGE(t.transaction_date, u.registration_date)) as month_number,
        SUM(t.total_amount) as monthly_revenue
    FROM users u
    JOIN transactions t ON u.user_id = t.user_id
    GROUP BY cohort_month, u.user_id, month_number
)
SELECT
    cohort_month,
    month_number,
    COUNT(DISTINCT user_id) as active_users,
    SUM(monthly_revenue) as total_revenue,
    AVG(monthly_revenue) as avg_revenue_per_user,
    -- Cumulative LTV
    SUM(SUM(monthly_revenue)) OVER (
        PARTITION BY cohort_month
        ORDER BY month_number
    ) / COUNT(DISTINCT user_id) as cumulative_ltv
FROM cohort_revenue
GROUP BY cohort_month, month_number
ORDER BY cohort_month, month_number;
