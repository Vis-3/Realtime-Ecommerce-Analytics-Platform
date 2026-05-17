-- ============================================
-- SEED DATA
-- Persona distribution calibrated against UCI Online Retail dataset:
--   Hibernating 41%, New 34%, Champion 14%, Loyal 9%, AtRisk 2%
-- Transactions are generated separately by seed_transactions.py
-- using Weibull-sampled inter-purchase times per persona.
-- ============================================

-- Generate 10,000 users with persona assignments
INSERT INTO users (
    email, first_name, last_name, registration_date,
    country, city, state, zip_code, age_group, gender, persona
)
SELECT
    'user' || gs || '@example.com',
    'First' || gs,
    'Last'  || gs,
    -- Registration date varies by persona: Champions are older customers,
    -- New customers registered recently, others in between.
    CASE
        WHEN r < 0.41 THEN CURRENT_DATE - (365  + (random() * 365))::integer   -- Hibernating: 1-2 yrs ago
        WHEN r < 0.75 THEN CURRENT_DATE - (       random() * 180 )::integer    -- New:         0-6 months ago
        WHEN r < 0.89 THEN CURRENT_DATE - (365  + (random() * 730))::integer   -- Champion:    1-3 yrs ago
        WHEN r < 0.98 THEN CURRENT_DATE - (180  + (random() * 545))::integer   -- Loyal:       6-24 months ago
        ELSE               CURRENT_DATE - (365  + (random() * 365))::integer   -- AtRisk:      1-2 yrs ago
    END,
    (ARRAY['USA', 'Canada', 'UK', 'Germany', 'France'])[floor(random() * 5 + 1)],
    'City' || (random() * 100)::integer,
    (ARRAY['CA', 'NY', 'TX', 'FL', 'WA'])[floor(random() * 5 + 1)],
    (10000 + random() * 90000)::integer::text,
    (ARRAY['18-24', '25-34', '35-44', '45-54', '55+'])[floor(random() * 5 + 1)],
    (ARRAY['Male', 'Female', 'Other'])[floor(random() * 3 + 1)],
    CASE
        WHEN r < 0.41 THEN 'Hibernating'
        WHEN r < 0.75 THEN 'New'
        WHEN r < 0.89 THEN 'Champion'
        WHEN r < 0.98 THEN 'Loyal'
        ELSE               'AtRisk'
    END
FROM (
    SELECT gs, random() AS r
    FROM generate_series(1, 10000) gs
) sub;

-- Generate 1,000 products
-- Prices follow a realistic range; cost is 40-60% of price.
INSERT INTO products (product_name, category, subcategory, brand, unit_cost, current_price, stock_quantity)
SELECT
    'Product ' || gs,
    (ARRAY['Electronics', 'Clothing', 'Home & Garden', 'Sports', 'Books'])[floor(random() * 5 + 1)],
    'Subcategory ' || (random() * 20)::integer,
    'Brand '       || (random() * 50)::integer,
    (random() * 80  + 5 )::numeric(10, 2),
    (random() * 180 + 10)::numeric(10, 2),
    (random() * 1000)::integer
FROM generate_series(1, 1000) gs;

-- Refresh materialized views after seed_transactions.py has run.
-- (Handled at the end of seed_transactions.py automatically.)
