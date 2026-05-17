-- ============================================
-- REAL-TIME DASHBOARD QUERIES
-- ============================================
-- Optimized queries for live operational dashboards

-- Query 1: Current Hour Metrics
SELECT
    'Last Hour' as time_period,
    COUNT(DISTINCT user_id) as active_users,
    COUNT(DISTINCT transaction_id) as transactions,
    COALESCE(SUM(total_amount), 0) as revenue,
    COALESCE(AVG(total_amount), 0) as avg_order_value,
    COUNT(DISTINCT session_id) as sessions,
    COALESCE(SUM(quantity), 0) as items_sold
FROM transactions
WHERE transaction_date >= NOW() - INTERVAL '1 hour';

-- Query 2: Today vs Yesterday Comparison
WITH today_metrics AS (
    SELECT
        COUNT(DISTINCT user_id) as users,
        COUNT(*) as transactions,
        SUM(total_amount) as revenue
    FROM transactions
    WHERE DATE(transaction_date) = CURRENT_DATE
),
yesterday_metrics AS (
    SELECT
        COUNT(DISTINCT user_id) as users,
        COUNT(*) as transactions,
        SUM(total_amount) as revenue
    FROM transactions
    WHERE DATE(transaction_date) = CURRENT_DATE - 1
)
SELECT
    t.users as today_users,
    y.users as yesterday_users,
    ROUND(100.0 * (t.users - y.users) / NULLIF(y.users, 0), 2) as user_change_pct,
    t.transactions as today_transactions,
    y.transactions as yesterday_transactions,
    ROUND(100.0 * (t.transactions - y.transactions) / NULLIF(y.transactions, 0), 2) as transaction_change_pct,
    t.revenue as today_revenue,
    y.revenue as yesterday_revenue,
    ROUND(100.0 * (t.revenue - y.revenue) / NULLIF(y.revenue, 0), 2) as revenue_change_pct
FROM today_metrics t, yesterday_metrics y;

-- Query 3: Hourly Trend (Last 24 Hours)
SELECT
    DATE_TRUNC('hour', transaction_date) as hour,
    COUNT(DISTINCT user_id) as active_users,
    COUNT(*) as transactions,
    SUM(total_amount) as revenue,
    AVG(total_amount) as avg_order_value
FROM transactions
WHERE transaction_date >= NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', transaction_date)
ORDER BY hour DESC;

-- Query 4: Top Products (Last Hour)
SELECT
    p.product_id,
    p.product_name,
    p.category,
    COUNT(*) as purchase_count,
    SUM(t.quantity) as units_sold,
    SUM(t.total_amount) as revenue,
    AVG(t.total_amount) as avg_sale_price
FROM transactions t
JOIN products p ON t.product_id = p.product_id
WHERE t.transaction_date >= NOW() - INTERVAL '1 hour'
GROUP BY p.product_id, p.product_name, p.category
ORDER BY revenue DESC
LIMIT 10;

-- Query 5: Top Categories (Real-time)
SELECT
    p.category,
    COUNT(DISTINCT t.user_id) as unique_buyers,
    COUNT(*) as transactions,
    SUM(t.total_amount) as revenue,
    SUM(t.quantity) as units_sold,
    AVG(t.total_amount) as avg_order_value
FROM transactions t
JOIN products p ON t.product_id = p.product_id
WHERE t.transaction_date >= NOW() - INTERVAL '1 hour'
GROUP BY p.category
ORDER BY revenue DESC;

-- Query 6: Geographic Performance (Real-time)
SELECT
    u.country,
    u.city,
    COUNT(DISTINCT t.user_id) as active_users,
    COUNT(*) as transactions,
    SUM(t.total_amount) as revenue
FROM transactions t
JOIN users u ON t.user_id = u.user_id
WHERE t.transaction_date >= NOW() - INTERVAL '1 hour'
GROUP BY u.country, u.city
ORDER BY revenue DESC
LIMIT 20;

-- Query 7: New vs Returning Customers (Today)
WITH customer_first_purchase AS (
    SELECT
        user_id,
        MIN(transaction_date) as first_purchase_date
    FROM transactions
    GROUP BY user_id
)
SELECT
    CASE
        WHEN DATE(cfp.first_purchase_date) = CURRENT_DATE THEN 'New'
        ELSE 'Returning'
    END as customer_type,
    COUNT(DISTINCT t.user_id) as customers,
    COUNT(*) as transactions,
    SUM(t.total_amount) as revenue,
    AVG(t.total_amount) as avg_order_value
FROM transactions t
JOIN customer_first_purchase cfp ON t.user_id = cfp.user_id
WHERE DATE(t.transaction_date) = CURRENT_DATE
GROUP BY customer_type;

-- Query 8: Payment Method Distribution (Real-time)
SELECT
    payment_method,
    COUNT(*) as transaction_count,
    SUM(total_amount) as revenue,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct_of_transactions,
    ROUND(100.0 * SUM(total_amount) / SUM(SUM(total_amount)) OVER (), 2) as pct_of_revenue
FROM transactions
WHERE transaction_date >= NOW() - INTERVAL '24 hours'
GROUP BY payment_method
ORDER BY revenue DESC;

-- Query 9: Customer Lifetime Value Leaderboard
SELECT
    u.user_id,
    u.email,
    u.registration_date,
    u.customer_segment,
    COUNT(t.transaction_id) as total_purchases,
    SUM(t.total_amount) as lifetime_value,
    MAX(t.transaction_date) as last_purchase_date,
    CURRENT_DATE - MAX(t.transaction_date)::date as days_since_last_purchase
FROM users u
JOIN transactions t ON u.user_id = t.user_id
GROUP BY u.user_id, u.email, u.registration_date, u.customer_segment
ORDER BY lifetime_value DESC
LIMIT 100;

-- Query 10: Real-time Inventory Alerts
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.stock_quantity as current_stock,
    COUNT(t.transaction_id) as sales_last_24h,
    SUM(t.quantity) as units_sold_last_24h,
    -- Estimated days until stockout
    CASE
        WHEN COUNT(t.transaction_id) > 0
        THEN ROUND(p.stock_quantity::numeric / (SUM(t.quantity)::numeric / 1), 1)  -- 1 day sales rate
        ELSE NULL
    END as days_until_stockout
FROM products p
LEFT JOIN transactions t ON p.product_id = t.product_id
    AND t.transaction_date >= NOW() - INTERVAL '24 hours'
GROUP BY p.product_id, p.product_name, p.category, p.stock_quantity
HAVING p.stock_quantity < 50 OR
       (p.stock_quantity::numeric / NULLIF(SUM(t.quantity), 0)) < 7  -- Less than 7 days stock
ORDER BY days_until_stockout NULLS LAST
LIMIT 20;
