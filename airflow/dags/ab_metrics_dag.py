"""
DAG: A/B Experiment Metrics
Schedule: 4:00 AM daily  (after export_to_minio_dag at 3 AM)

WHY THIS DAG EXISTS:
    GrowthBook can compute statistical significance automatically, but it needs
    a data source to read from.  This DAG computes the conversion metric
    (purchased within 7 days of experiment assignment) per variant and writes
    it to ab_experiment_metrics.  GrowthBook is configured to query this table
    via its Postgres data source integration, giving it real conversion data
    for significance testing without any custom code in GrowthBook itself.

CONVERSION DEFINITION:
    A user "converted" if they made at least one purchase within 7 days of
    being assigned to the experiment.  This is a conservative definition —
    it measures the short-term behavioural response to the discount offer,
    which is the right signal for churn intervention effectiveness.

PIPELINE:
    check_assignments_exist
        → compute_conversion_metrics
        → log_summary
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "ecommerce_postgres"
EXPERIMENT_KEY   = "churn-discount-v1"

COMPUTE_METRICS_SQL = """
INSERT INTO ab_experiment_metrics
    (metric_date, experiment_key, variant, assigned_users, converted_users, conversion_rate)
SELECT
    CURRENT_DATE                                                    AS metric_date,
    a.experiment_key,
    a.variant,
    COUNT(DISTINCT a.user_id)                                       AS assigned_users,
    COUNT(DISTINCT t.user_id)                                       AS converted_users,
    ROUND(
        COUNT(DISTINCT t.user_id)::numeric
        / NULLIF(COUNT(DISTINCT a.user_id), 0),
        4
    )                                                               AS conversion_rate
FROM ab_assignments a
LEFT JOIN transactions t
       ON a.user_id = t.user_id
      AND t.transaction_date >= a.assigned_at
      AND t.transaction_date <= a.assigned_at + INTERVAL '7 days'
WHERE a.experiment_key = 'churn-discount-v1'
GROUP BY a.experiment_key, a.variant
ON CONFLICT (metric_date, experiment_key, variant) DO UPDATE
    SET assigned_users  = EXCLUDED.assigned_users,
        converted_users = EXCLUDED.converted_users,
        conversion_rate = EXCLUDED.conversion_rate,
        computed_at     = CURRENT_TIMESTAMP;
"""


def check_assignments_exist(**context):
    hook  = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    count = hook.get_first(
        "SELECT COUNT(*) FROM ab_assignments WHERE experiment_key = %s",
        parameters=(EXPERIMENT_KEY,),
    )[0]

    log.info("ab_assignments for %s: %d rows", EXPERIMENT_KEY, count)
    if count == 0:
        raise AirflowSkipException(
            "No experiment assignments yet — "
            "call GET /experiment/offer/{user_id} to generate assignments"
        )
    context["ti"].xcom_push(key="total_assignments", value=count)


def compute_conversion_metrics(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    hook.run(COMPUTE_METRICS_SQL)
    log.info("Conversion metrics written to ab_experiment_metrics for %s", EXPERIMENT_KEY)


def log_summary(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    rows = hook.get_records(
        """
        SELECT variant, assigned_users, converted_users, conversion_rate
        FROM ab_experiment_metrics
        WHERE experiment_key = %s AND metric_date = CURRENT_DATE
        ORDER BY variant
        """,
        parameters=(EXPERIMENT_KEY,),
    )
    total_assigned = context["ti"].xcom_pull(
        task_ids="check_assignments_exist", key="total_assignments"
    ) or 0

    log.info("=== Experiment: %s ===", EXPERIMENT_KEY)
    log.info("Total assignments: %d", total_assigned)
    for variant, assigned, converted, rate in rows:
        log.info(
            "  %-20s  assigned=%d  converted=%d  rate=%.1f%%",
            variant, assigned, converted or 0, (rate or 0) * 100,
        )


default_args = {
    "owner":           "data-engineering",
    "depends_on_past": False,
    "retries":         1,
    "retry_delay":     timedelta(minutes=5),
}

with DAG(
    dag_id="ab_metrics_dag",
    description="Daily conversion metrics for churn discount A/B experiment",
    schedule_interval="0 4 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["daily", "ab-testing", "growthbook"],
) as dag:

    t_check = PythonOperator(
        task_id="check_assignments_exist",
        python_callable=check_assignments_exist,
    )

    t_metrics = PythonOperator(
        task_id="compute_conversion_metrics",
        python_callable=compute_conversion_metrics,
    )

    t_summary = PythonOperator(
        task_id="log_summary",
        python_callable=log_summary,
    )

    t_check >> t_metrics >> t_summary
