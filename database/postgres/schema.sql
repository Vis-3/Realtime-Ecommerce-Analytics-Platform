-- ============================================
-- E-COMMERCE ANALYTICS DATABASE SCHEMA (FIXED)
-- Star Schema Design for OLAP + OLTP
-- ============================================

-- Drop existing tables if they exist
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP MATERIALIZED VIEW IF EXISTS daily_metrics CASCADE;
DROP MATERIALIZED VIEW IF EXISTS user_metrics CASCADE;

-- ============================================
-- DIMENSION TABLES
-- ============================================

-- Users Dimension
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    registration_date DATE NOT NULL,
    country VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(100),
    zip_code VARCHAR(20),
    age_group VARCHAR(20),
    gender VARCHAR(20),
    persona VARCHAR(20) DEFAULT 'New',
    customer_segment VARCHAR(50),
    lifetime_value DECIMAL(12, 2) DEFAULT 0,
    churn_risk_score DECIMAL(3, 2),
    last_purchase_date DATE,
    total_purchases INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Products Dimension
CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    brand VARCHAR(100),
    unit_cost DECIMAL(10, 2) NOT NULL,
    current_price DECIMAL(10, 2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0,
    supplier VARCHAR(100),
    weight_kg DECIMAL(6, 2),
    dimensions VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sessions Dimension (user browsing sessions)
CREATE TABLE sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id),
    session_start TIMESTAMP NOT NULL,
    session_end TIMESTAMP,
    device_type VARCHAR(50),
    browser VARCHAR(50),
    os VARCHAR(50),
    country VARCHAR(100),
    referrer VARCHAR(255),
    landing_page VARCHAR(255),
    pages_viewed INTEGER DEFAULT 0,
    duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- FACT TABLE (PARTITIONED)
-- ============================================

-- Transactions Fact Table
-- NOTE: Primary key must include partition key (transaction_date)
CREATE TABLE transactions (
    transaction_id BIGSERIAL,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    session_id VARCHAR(255),
    transaction_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10, 2) NOT NULL CHECK (unit_price >= 0),
    total_amount DECIMAL(12, 2) NOT NULL CHECK (total_amount >= 0),
    discount_amount DECIMAL(10, 2) DEFAULT 0 CHECK (discount_amount >= 0),
    tax_amount DECIMAL(10, 2) DEFAULT 0,
    shipping_cost DECIMAL(10, 2) DEFAULT 0,
    payment_method VARCHAR(50),
    shipping_address VARCHAR(255),
    order_status VARCHAR(50) DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Composite primary key including partition key
    PRIMARY KEY (transaction_id, transaction_date)
) PARTITION BY RANGE (transaction_date);

-- Create partitions for transactions (by month)
-- 2024
CREATE TABLE transactions_2024_01 PARTITION OF transactions FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE transactions_2024_02 PARTITION OF transactions FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
CREATE TABLE transactions_2024_03 PARTITION OF transactions FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');
CREATE TABLE transactions_2024_04 PARTITION OF transactions FOR VALUES FROM ('2024-04-01') TO ('2024-05-01');
CREATE TABLE transactions_2024_05 PARTITION OF transactions FOR VALUES FROM ('2024-05-01') TO ('2024-06-01');
CREATE TABLE transactions_2024_06 PARTITION OF transactions FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');
CREATE TABLE transactions_2024_07 PARTITION OF transactions FOR VALUES FROM ('2024-07-01') TO ('2024-08-01');
CREATE TABLE transactions_2024_08 PARTITION OF transactions FOR VALUES FROM ('2024-08-01') TO ('2024-09-01');
CREATE TABLE transactions_2024_09 PARTITION OF transactions FOR VALUES FROM ('2024-09-01') TO ('2024-10-01');
CREATE TABLE transactions_2024_10 PARTITION OF transactions FOR VALUES FROM ('2024-10-01') TO ('2024-11-01');
CREATE TABLE transactions_2024_11 PARTITION OF transactions FOR VALUES FROM ('2024-11-01') TO ('2024-12-01');
CREATE TABLE transactions_2024_12 PARTITION OF transactions FOR VALUES FROM ('2024-12-01') TO ('2025-01-01');
-- 2025
CREATE TABLE transactions_2025_01 PARTITION OF transactions FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE transactions_2025_02 PARTITION OF transactions FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE transactions_2025_03 PARTITION OF transactions FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
CREATE TABLE transactions_2025_04 PARTITION OF transactions FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');
CREATE TABLE transactions_2025_05 PARTITION OF transactions FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');
CREATE TABLE transactions_2025_06 PARTITION OF transactions FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
CREATE TABLE transactions_2025_07 PARTITION OF transactions FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');
CREATE TABLE transactions_2025_08 PARTITION OF transactions FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');
CREATE TABLE transactions_2025_09 PARTITION OF transactions FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');
CREATE TABLE transactions_2025_10 PARTITION OF transactions FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
CREATE TABLE transactions_2025_11 PARTITION OF transactions FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
CREATE TABLE transactions_2025_12 PARTITION OF transactions FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');
-- 2026
CREATE TABLE transactions_2026_01 PARTITION OF transactions FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE transactions_2026_02 PARTITION OF transactions FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE transactions_2026_03 PARTITION OF transactions FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE transactions_2026_04 PARTITION OF transactions FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE transactions_2026_05 PARTITION OF transactions FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE transactions_2026_06 PARTITION OF transactions FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
-- Default partition catches anything outside the defined ranges
CREATE TABLE transactions_default PARTITION OF transactions DEFAULT;

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

-- Users indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_registration_date ON users(registration_date);
CREATE INDEX idx_users_segment ON users(customer_segment);
CREATE INDEX idx_users_churn_risk ON users(churn_risk_score DESC);
CREATE INDEX idx_users_country_city ON users(country, city);

-- Products indexes
CREATE INDEX idx_products_category ON products(category, subcategory);
CREATE INDEX idx_products_brand ON products(brand);
CREATE INDEX idx_products_price ON products(current_price);

-- Sessions indexes
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_start ON sessions(session_start);
CREATE INDEX idx_sessions_device ON sessions(device_type);

-- Transactions indexes (critical for query performance)
CREATE INDEX idx_transactions_user_date ON transactions(user_id, transaction_date DESC);
CREATE INDEX idx_transactions_product ON transactions(product_id);
CREATE INDEX idx_transactions_date ON transactions(transaction_date DESC);
CREATE INDEX idx_transactions_session ON transactions(session_id);
CREATE INDEX idx_transactions_amount ON transactions(total_amount DESC);
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_product_id ON transactions(product_id);

-- ============================================
-- MATERIALIZED VIEWS FOR ANALYTICS
-- ============================================

-- Daily Metrics View (refreshed hourly)
CREATE MATERIALIZED VIEW daily_metrics AS
SELECT 
    DATE(transaction_date) as metric_date,
    COUNT(DISTINCT user_id) as daily_active_users,
    COUNT(DISTINCT transaction_id) as total_transactions,
    SUM(total_amount) as total_revenue,
    AVG(total_amount) as avg_order_value,
    SUM(quantity) as total_items_sold,
    COUNT(DISTINCT session_id) as total_sessions,
    SUM(discount_amount) as total_discounts,
    COUNT(DISTINCT 
        CASE WHEN transaction_date >= DATE(transaction_date) 
        THEN user_id END
    ) as new_customers
FROM transactions
GROUP BY DATE(transaction_date);

-- Create index on materialized view
CREATE UNIQUE INDEX idx_daily_metrics_date ON daily_metrics(metric_date);

-- User Metrics View (for RFM analysis)
CREATE MATERIALIZED VIEW user_metrics AS
SELECT 
    u.user_id,
    u.email,
    u.customer_segment,
    COALESCE(CURRENT_DATE - MAX(t.transaction_date)::date, 9999) as recency_days,
    COUNT(DISTINCT t.transaction_id) as frequency,
    COALESCE(SUM(t.total_amount), 0) as monetary,
    COALESCE(AVG(t.total_amount), 0) as avg_order_value,
    MAX(t.transaction_date) as last_purchase_date,
    MIN(t.transaction_date) as first_purchase_date,
    COUNT(DISTINCT DATE(t.transaction_date)) as purchase_days,
    COALESCE(SUM(t.quantity), 0) as total_items_purchased
FROM users u
LEFT JOIN transactions t ON u.user_id = t.user_id
GROUP BY u.user_id, u.email, u.customer_segment;

CREATE UNIQUE INDEX idx_user_metrics_user_id ON user_metrics(user_id);

-- ============================================
-- FUNCTIONS & TRIGGERS
-- ============================================

-- Function to update user metrics on new transaction
CREATE OR REPLACE FUNCTION update_user_metrics()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE users
    SET 
        lifetime_value = (
            SELECT COALESCE(SUM(total_amount), 0)
            FROM transactions
            WHERE user_id = NEW.user_id
        ),
        last_purchase_date = NEW.transaction_date::date,
        total_purchases = (
            SELECT COUNT(*)
            FROM transactions
            WHERE user_id = NEW.user_id
        ),
        updated_at = CURRENT_TIMESTAMP
    WHERE user_id = NEW.user_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update user metrics
CREATE TRIGGER trigger_update_user_metrics
AFTER INSERT ON transactions
FOR EACH ROW
EXECUTE FUNCTION update_user_metrics();

-- ============================================
-- REAL-TIME METRICS TABLE
-- ============================================

-- Table for real-time streaming aggregations
CREATE TABLE realtime_metrics (
    id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    event_type VARCHAR(50),
    event_count INTEGER,
    unique_users INTEGER,
    unique_sessions INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_realtime_metrics_window ON realtime_metrics(window_start, window_end);

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE users IS 'Customer dimension table with lifetime metrics';
COMMENT ON TABLE products IS 'Product catalog dimension table';
COMMENT ON TABLE transactions IS 'Fact table for all purchase transactions (partitioned by month)';
COMMENT ON MATERIALIZED VIEW daily_metrics IS 'Pre-aggregated daily KPIs (refresh hourly)';
COMMENT ON MATERIALIZED VIEW user_metrics IS 'User-level RFM metrics (refresh hourly)';