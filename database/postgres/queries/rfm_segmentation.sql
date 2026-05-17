-- ============================================
-- RFM SEGMENTATION ANALYSIS
-- ============================================
-- Segments customers by Recency, Frequency, Monetary value

WITH rfm_base AS (
    -- Calculate RFM metrics for each user
    SELECT
        u.user_id,
        u.email,
        u.registration_date,
        -- Recency: Days since last purchase
        COALESCE(CURRENT_DATE - MAX(t.transaction_date)::date, 9999) as recency_days,
        -- Frequency: Number of purchases
        COALESCE(COUNT(DISTINCT t.transaction_id), 0) as frequency,
        -- Monetary: Total amount spent
        COALESCE(SUM(t.total_amount), 0) as monetary
    FROM users u
    LEFT JOIN transactions t ON u.user_id = t.user_id
    GROUP BY u.user_id, u.email, u.registration_date
),
rfm_scores AS (
    -- Assign quintile scores (1-5) for each metric
    SELECT
        user_id,
        email,
        recency_days,
        frequency,
        monetary,
        -- Lower recency is better, so reverse the order
        NTILE(5) OVER (ORDER BY recency_days DESC) as r_score,
        -- Higher frequency is better
        NTILE(5) OVER (ORDER BY frequency) as f_score,
        -- Higher monetary is better
        NTILE(5) OVER (ORDER BY monetary) as m_score
    FROM rfm_base
),
rfm_segments AS (
    -- Assign customer segments based on RFM scores
    SELECT
        *,
        CASE
            -- Champions: Best customers (High R, F, M)
            WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'

            -- Loyal Customers: Consistent buyers
            WHEN r_score >= 3 AND f_score >= 4 THEN 'Loyal Customers'

            -- Potential Loyalists: Recent customers with good frequency
            WHEN r_score >= 4 AND f_score >= 3 THEN 'Potential Loyalists'

            -- New Customers: Recent but low frequency
            WHEN r_score >= 4 AND f_score <= 2 THEN 'New Customers'

            -- Promising: Recent, low frequency but high monetary
            WHEN r_score >= 3 AND m_score >= 4 THEN 'Promising'

            -- Need Attention: Above average recency/frequency/monetary
            WHEN r_score >= 3 AND f_score >= 3 THEN 'Need Attention'

            -- About to Sleep: Below average recency but good frequency
            WHEN r_score <= 2 AND f_score >= 3 THEN 'About to Sleep'

            -- At Risk: Were good customers but haven't returned
            WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4 THEN 'At Risk'

            -- Cannot Lose Them: High value customers who haven't purchased recently
            WHEN r_score <= 1 AND f_score >= 4 AND m_score >= 4 THEN 'Cannot Lose Them'

            -- Hibernating: Low recency, frequency, monetary
            WHEN r_score <= 2 AND f_score <= 2 THEN 'Hibernating'

            -- Lost: Haven't purchased in very long time
            WHEN r_score <= 1 THEN 'Lost'

            ELSE 'Other'
        END as customer_segment,
        -- Create RFM score string for easy reference
        CONCAT(r_score, f_score, m_score) as rfm_score
    FROM rfm_scores
)
SELECT
    customer_segment,
    COUNT(*) as customer_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as segment_percentage,
    AVG(recency_days)::integer as avg_recency_days,
    AVG(frequency)::numeric(10,2) as avg_frequency,
    AVG(monetary)::numeric(10,2) as avg_monetary,
    SUM(monetary)::numeric(12,2) as total_revenue,
    -- Recommended action for each segment
    CASE customer_segment
        WHEN 'Champions' THEN 'Reward, Upsell premium products'
        WHEN 'Loyal Customers' THEN 'Upsell, Ask for reviews'
        WHEN 'Potential Loyalists' THEN 'Offer membership, Recommend products'
        WHEN 'New Customers' THEN 'Provide onboarding support'
        WHEN 'Promising' THEN 'Offer loyalty programs'
        WHEN 'Need Attention' THEN 'Limited time offers'
        WHEN 'About to Sleep' THEN 'Engagement campaigns'
        WHEN 'At Risk' THEN 'Win-back campaigns, Special discounts'
        WHEN 'Cannot Lose Them' THEN 'Personalized reactivation offers'
        WHEN 'Hibernating' THEN 'Re-engagement emails'
        WHEN 'Lost' THEN 'Aggressive win-back or ignore'
        ELSE 'Monitor'
    END as recommended_action
FROM rfm_segments
GROUP BY customer_segment
ORDER BY total_revenue DESC;

-- ============================================
-- INDIVIDUAL USER RFM DETAILS
-- ============================================
-- Get RFM details for specific users (useful for personalization)

SELECT
    rs.user_id,
    rs.email,
    rs.recency_days,
    rs.frequency,
    rs.monetary,
    rs.r_score,
    rs.f_score,
    rs.m_score,
    rs.rfm_score,
    rs.customer_segment,
    -- Add additional context
    u.registration_date,
    u.country,
    u.age_group,
    -- Next best action
    CASE rs.customer_segment
        WHEN 'Champions' THEN 'Send exclusive VIP offer'
        WHEN 'At Risk' THEN 'Send 20% win-back coupon'
        WHEN 'New Customers' THEN 'Send welcome series email'
        WHEN 'Lost' THEN 'Final win-back attempt or suppress'
        ELSE 'Standard marketing'
    END as next_action
FROM rfm_segments rs
JOIN users u ON rs.user_id = u.user_id
ORDER BY rs.monetary DESC
LIMIT 100;
