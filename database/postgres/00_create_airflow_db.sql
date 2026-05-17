-- Creates the airflow metadata database if it doesn't already exist.
-- Named 00_ so it runs before schema.sql and seed_data.sql.
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
