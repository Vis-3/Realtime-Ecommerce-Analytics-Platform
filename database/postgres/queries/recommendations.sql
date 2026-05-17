-- ============================================
-- COLLABORATIVE FILTERING RECOMMENDATIONS
-- ============================================
-- Recommend products based on similar users' purchases (user-based CF)

WITH user_product_purchases AS (
    -- Create user-product interaction matrix
    SELECT DISTINCT
        user_id,
        product_id
    FROM transactions
),
user_similarity AS (
    -- Calculate similarity between users using Jaccard similarity
    -- (based on common products purchased)
    SELECT
        a.user_id as user_a,
        b.user_id as user_b,
        COUNT(*) as common_products,
        (SELECT COUNT(DISTINCT product_id) FROM user_product_purchases WHERE user_id = a.user_id) as products_a,
        (SELECT COUNT(DISTINCT product_id) FROM user_product_purchases WHERE user_id = b.user_id) as products_b
    FROM user_product_purchases a
    JOIN user_product_purchases b
        ON a.product_id = b.product_id
        AND a.user_id < b.user_id  -- Avoid duplicate pairs
    GROUP BY a.user_id, b.user_id
    HAVING COUNT(*) >= 2  -- At least 2 products in common
),
similarity_scores AS (
    -- Calculate Jaccard similarity coefficient
    SELECT
        user_a,
        user_b,
        common_products::float / (products_a + products_b - common_products) as jaccard_similarity
    FROM user_similarity
    WHERE (products_a + products_b - common_products) > 0
)
SELECT
    -- Recommendations for user_id = 1 (example)
    1 as target_user,
    t.product_id,
    p.product_name,
    p.category,
    p.current_price,
    -- Sum of similarity scores from users who bought this product
    SUM(ss.jaccard_similarity) as recommendation_score,
    COUNT(DISTINCT ss.user_b) as recommended_by_n_similar_users
FROM similarity_scores ss
JOIN transactions t ON (
    (ss.user_b = t.user_id AND ss.user_a = 1) OR
    (ss.user_a = t.user_id AND ss.user_b = 1)
)
JOIN products p ON t.product_id = p.product_id
WHERE t.product_id NOT IN (
    -- Exclude products already purchased by target user
    SELECT product_id FROM transactions WHERE user_id = 1
)
AND (
    (ss.user_a = 1 AND ss.user_b = t.user_id) OR
    (ss.user_b = 1 AND ss.user_a = t.user_id)
)
GROUP BY t.product_id, p.product_name, p.category, p.current_price
HAVING SUM(ss.jaccard_similarity) > 0.1  -- Minimum similarity threshold
ORDER BY recommendation_score DESC
LIMIT 20;

-- ============================================
-- ITEM-BASED COLLABORATIVE FILTERING
-- ============================================
-- "Customers who bought X also bought Y"

WITH product_pairs AS (
    -- Find pairs of products purchased together
    SELECT
        t1.product_id as product_a,
        t2.product_id as product_b,
        COUNT(DISTINCT t1.user_id) as co_purchase_count
    FROM transactions t1
    JOIN transactions t2
        ON t1.user_id = t2.user_id
        AND t1.product_id < t2.product_id  -- Avoid duplicates
    GROUP BY t1.product_id, t2.product_id
    HAVING COUNT(DISTINCT t1.user_id) >= 5  -- At least 5 co-purchases
),
product_popularity AS (
    -- Count how many users bought each product
    SELECT
        product_id,
        COUNT(DISTINCT user_id) as user_count
    FROM transactions
    GROUP BY product_id
)
SELECT
    pp.product_a,
    pa.product_name as product_a_name,
    pp.product_b,
    pb.product_name as product_b_name,
    pp.co_purchase_count,
    popa.user_count as product_a_buyers,
    popb.user_count as product_b_buyers,
    -- Lift: How much more likely to buy B given A
    ROUND(
        (pp.co_purchase_count::float / popa.user_count) /
        (popb.user_count::float / (SELECT COUNT(DISTINCT user_id) FROM users)),
        2
    ) as lift,
    -- Confidence: P(B|A)
    ROUND(100.0 * pp.co_purchase_count / popa.user_count, 2) as confidence_pct
FROM product_pairs pp
JOIN products pa ON pp.product_a = pa.product_id
JOIN products pb ON pp.product_b = pb.product_id
JOIN product_popularity popa ON pp.product_a = popa.product_id
JOIN product_popularity popb ON pp.product_b = popb.product_id
WHERE lift > 1.5  -- Only show strong associations
ORDER BY lift DESC, co_purchase_count DESC
LIMIT 50;
