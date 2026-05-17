-- ============================================
-- PERFORMANCE TESTING QUERIES
-- ============================================
-- Test query performance and index effectiveness

-- Enable timing
\timing on

-- Test 1: Index usage on transactions
EXPLAIN ANALYZE
SELECT * FROM transactions
WHERE user_id = 100
AND transaction_date >= '2024-01-01'
ORDER BY transaction_date DESC;

-- Test 2: Materialized view performance
EXPLAIN ANALYZE
SELECT * FROM daily_metrics
WHERE metric_date >= CURRENT_DATE - 30
ORDER BY metric_date DESC;

-- Test 3: Join performance
EXPLAIN ANALYZE
SELECT
    t.transaction_id,
    u.email,
    p.product_name,
    t.total_amount
FROM transactions t
JOIN users u ON t.user_id = u.user_id
JOIN products p ON t.product_id = p.product_id
WHERE t.transaction_date >= NOW() - INTERVAL '7 days'
LIMIT 1000;

-- Test 4: Aggregation performance
EXPLAIN ANALYZE
SELECT
    DATE(transaction_date),
    COUNT(*),
    SUM(total_amount)
FROM transactions
WHERE transaction_date >= CURRENT_DATE - 90
GROUP BY DATE(transaction_date);

-- Show index sizes
SELECT
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as index_size
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexname::regclass) DESC;

-- Show table sizes
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(tablename::regclass)) as total_size,
    pg_size_pretty(pg_relation_size(tablename::regclass)) as table_size,
    pg_size_pretty(pg_total_relation_size(tablename::regclass) - pg_relation_size(tablename::regclass)) as indexes_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;
