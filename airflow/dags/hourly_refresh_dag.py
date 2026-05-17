"""
DAG 1: Hourly Materialized View Refresh
Schedule: top of every hour
Keeps daily_metrics and user_metrics fresh for dashboard queries.
"""

from datetime import datetime, timedelta
import logging

from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "ecommerce_postgres"

# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def on_failure_callback(context):
    log.error(
        "Task failed | dag=%s | task=%s | ts=%s",
        context["dag"].dag_id,
        context["task_instance"].task_id,
        context["ts"],
    )


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------

def check_postgres_connection(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    hook.get_conn()
    log.info("PostgreSQL connection OK")


def validate_refresh(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    dm_count = hook.get_first("SELECT COUNT(*) FROM daily_metrics")[0]
    um_count = hook.get_first("SELECT COUNT(*) FROM user_metrics")[0]

    if dm_count == 0:
        raise AirflowException("daily_metrics is empty after refresh")
    if um_count == 0:
        raise AirflowException("user_metrics is empty after refresh")

    log.info("Validation passed | daily_metrics=%d rows | user_metrics=%d rows", dm_count, um_count)
    return {"daily_metrics": dm_count, "user_metrics": um_count}


def log_refresh_stats(**context):
    ti = context["ti"]
    stats = ti.xcom_pull(task_ids="validate_refresh")
    ti.xcom_push(key="refresh_stats", value=stats)
    log.info("Refresh stats pushed to XCom: %s", stats)


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": on_failure_callback,
}

with DAG(
    dag_id="hourly_refresh_dag",
    description="Refresh daily_metrics and user_metrics materialized views every hour",
    schedule_interval="0 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["hourly", "materialized-views", "phase3"],
) as dag:

    t_check_conn = PythonOperator(
        task_id="check_postgres_connection",
        python_callable=check_postgres_connection,
    )

    # CONCURRENTLY keeps the view queryable while the refresh runs
    t_refresh_daily = PostgresOperator(
        task_id="refresh_daily_metrics",
        postgres_conn_id=POSTGRES_CONN_ID,
        sql="REFRESH MATERIALIZED VIEW CONCURRENTLY daily_metrics;",
    )

    t_refresh_user = PostgresOperator(
        task_id="refresh_user_metrics",
        postgres_conn_id=POSTGRES_CONN_ID,
        sql="REFRESH MATERIALIZED VIEW CONCURRENTLY user_metrics;",
    )

    t_validate = PythonOperator(
        task_id="validate_refresh",
        python_callable=validate_refresh,
    )

    t_log_stats = PythonOperator(
        task_id="log_refresh_stats",
        python_callable=log_refresh_stats,
    )

    # Pipeline order
    t_check_conn >> t_refresh_daily >> t_refresh_user >> t_validate >> t_log_stats
