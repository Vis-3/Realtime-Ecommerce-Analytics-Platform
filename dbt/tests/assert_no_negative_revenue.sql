-- Singular test: fails (returns rows) if any transaction has negative revenue.
-- The staging model already filters these out, but this test makes the
-- guarantee explicit and visible in dbt docs.
SELECT transaction_id
FROM {{ ref('stg_transactions') }}
WHERE total_amount < 0
