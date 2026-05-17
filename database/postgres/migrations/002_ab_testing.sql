-- ============================================================
-- A/B Testing tables for the churn discount experiment
-- Run once:
--   Get-Content database\postgres\migrations\002_ab_testing.sql | docker exec -i ecommerce_postgres psql -U postgres -d ecommerce
-- ============================================================

-- One row per (user, experiment) — same user always gets the same variant
CREATE TABLE IF NOT EXISTS ab_assignments (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER      NOT NULL,
    experiment_key  VARCHAR(100) NOT NULL,
    variant         VARCHAR(50)  NOT NULL,
    assigned_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, experiment_key)
);

CREATE INDEX IF NOT EXISTS idx_ab_assignments_experiment
    ON ab_assignments (experiment_key, variant);

CREATE INDEX IF NOT EXISTS idx_ab_assignments_user
    ON ab_assignments (user_id);

-- Daily rollup: conversion = purchase within 7 days of assignment
CREATE TABLE IF NOT EXISTS ab_experiment_metrics (
    id              SERIAL PRIMARY KEY,
    metric_date     DATE         NOT NULL,
    experiment_key  VARCHAR(100) NOT NULL,
    variant         VARCHAR(50)  NOT NULL,
    assigned_users  INTEGER,
    converted_users INTEGER,
    conversion_rate NUMERIC(6, 4),
    computed_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (metric_date, experiment_key, variant)
);

COMMENT ON TABLE ab_assignments        IS 'GrowthBook experiment assignments — one row per user per experiment';
COMMENT ON TABLE ab_experiment_metrics IS 'Daily conversion metrics per variant — read by GrowthBook as a data source';
