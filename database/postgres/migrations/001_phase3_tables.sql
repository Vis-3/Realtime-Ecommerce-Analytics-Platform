-- ============================================
-- PHASE 3 SCHEMA ADDITIONS
-- Run once against the running postgres container:
-- docker exec -i ecommerce_postgres psql -U postgres -d ecommerce < database/postgres/migrations/001_phase3_tables.sql
-- ============================================

-- Daily report snapshot log (written by daily_analytics_dag)
CREATE TABLE IF NOT EXISTS daily_report_log (
    id                 SERIAL PRIMARY KEY,
    report_date        DATE         NOT NULL UNIQUE,
    total_users        INTEGER,
    total_transactions INTEGER,
    total_revenue      DECIMAL(12, 2),
    avg_order_value    DECIMAL(10, 2),
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Model registry (written by model_retraining_dag)
CREATE TABLE IF NOT EXISTS model_registry (
    id          SERIAL PRIMARY KEY,
    model_name  VARCHAR(100) NOT NULL,
    version     VARCHAR(50)  NOT NULL,
    trained_at  TIMESTAMP    NOT NULL,
    metrics     JSONB,
    is_active   BOOLEAN   DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (model_name, version)
);

CREATE INDEX IF NOT EXISTS idx_model_registry_active
    ON model_registry (model_name, is_active);

COMMENT ON TABLE daily_report_log IS 'Daily snapshot written by Airflow daily_analytics_dag at 2 AM';
COMMENT ON TABLE model_registry   IS 'Versioned model artifacts written by model_retraining_dag every Sunday';
