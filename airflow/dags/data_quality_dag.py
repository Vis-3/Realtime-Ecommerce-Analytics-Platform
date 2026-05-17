"""
DAG 3: Data Quality Checks
Schedule: 1:30 AM daily (runs before daily_analytics_dag at 2 AM)
7 parallel checks — each pushes pass/fail to XCom.
summarize_quality always runs via TriggerRule.ALL_DONE.
"""

from datetime import datetime, timedelta
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "ecommerce_postgres"


# ---------------------------------------------------------------------------
# Generic check helper
# ---------------------------------------------------------------------------

def _push_result(ti, check_name, status, value):
    result = {"check": check_name, "status": status, "value": value}
    ti.xcom_push(key=check_name, value=result)
    log.info("[%s] status=%s value=%s", check_name, status, value)
    return result


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def check_null_user_ids(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    count = hook.get_first(
        "SELECT COUNT(*) FROM transactions WHERE user_id IS NULL"
    )[0]
    status = "fail" if count > 0 else "pass"
    _push_result(context["ti"], "check_null_user_ids", status, count)
    if status == "fail":
        raise ValueError(f"Found {count} transactions with NULL user_id")


def check_null_amounts(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    count = hook.get_first(
        "SELECT COUNT(*) FROM transactions WHERE total_amount IS NULL OR total_amount < 0"
    )[0]
    status = "fail" if count > 0 else "pass"
    _push_result(context["ti"], "check_null_amounts", status, count)
    if status == "fail":
        raise ValueError(f"Found {count} transactions with NULL or negative total_amount")


def check_orphan_transactions(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    count = hook.get_first("""
        SELECT COUNT(*)
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.user_id
        WHERE u.user_id IS NULL
    """)[0]
    status = "fail" if count > 0 else "pass"
    _push_result(context["ti"], "check_orphan_transactions", status, count)
    if status == "fail":
        raise ValueError(f"Found {count} orphan transactions with no matching user")


def check_duplicate_transactions(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    count = hook.get_first("""
        SELECT COUNT(*) FROM (
            SELECT transaction_id
            FROM transactions
            GROUP BY transaction_id
            HAVING COUNT(*) > 1
        ) dupes
    """)[0]
    status = "fail" if count > 0 else "pass"
    _push_result(context["ti"], "check_duplicate_transactions", status, count)
    if status == "fail":
        raise ValueError(f"Found {count} duplicate transaction_ids")


def check_revenue_anomaly(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    row = hook.get_first("""
        WITH yesterday AS (
            SELECT COALESCE(SUM(total_amount), 0) AS rev
            FROM transactions
            WHERE DATE(transaction_date) = CURRENT_DATE - 1
        ),
        week_avg AS (
            SELECT COALESCE(AVG(daily_rev), 0) AS avg_rev FROM (
                SELECT DATE(transaction_date), SUM(total_amount) AS daily_rev
                FROM transactions
                WHERE transaction_date >= CURRENT_DATE - 8
                  AND transaction_date <  CURRENT_DATE - 1
                GROUP BY DATE(transaction_date)
            ) t
        )
        SELECT yesterday.rev, week_avg.avg_rev
        FROM yesterday, week_avg
    """)
    yesterday_rev, avg_rev = float(row[0]), float(row[1])

    status = "pass"
    detail = f"yesterday={yesterday_rev:.2f} 7d_avg={avg_rev:.2f}"

    if avg_rev > 0:
        ratio = yesterday_rev / avg_rev
        if ratio > 3.0 or ratio < 0.1:
            status = "fail"
            detail += f" ratio={ratio:.2f} (threshold: 0.1–3.0)"

    _push_result(context["ti"], "check_revenue_anomaly", status, detail)
    if status == "fail":
        raise ValueError(f"Revenue anomaly detected: {detail}")


def check_transaction_volume(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    row = hook.get_first("""
        WITH yesterday AS (
            SELECT COUNT(*) AS cnt
            FROM transactions
            WHERE DATE(transaction_date) = CURRENT_DATE - 1
        ),
        week_avg AS (
            SELECT COALESCE(AVG(daily_cnt), 0) AS avg_cnt FROM (
                SELECT DATE(transaction_date), COUNT(*) AS daily_cnt
                FROM transactions
                WHERE transaction_date >= CURRENT_DATE - 8
                  AND transaction_date <  CURRENT_DATE - 1
                GROUP BY DATE(transaction_date)
            ) t
        )
        SELECT yesterday.cnt, week_avg.avg_cnt
        FROM yesterday, week_avg
    """)
    yesterday_cnt, avg_cnt = int(row[0]), float(row[1])

    status = "pass"
    detail = f"yesterday={yesterday_cnt} 7d_avg={avg_cnt:.1f}"

    if avg_cnt > 0:
        ratio = yesterday_cnt / avg_cnt
        if ratio > 3.0 or ratio < 0.1:
            status = "fail"
            detail += f" ratio={ratio:.2f} (threshold: 0.1–3.0)"

    _push_result(context["ti"], "check_transaction_volume", status, detail)
    if status == "fail":
        raise ValueError(f"Transaction volume anomaly: {detail}")


def check_stale_materialized_views(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    rows = hook.get_records("""
        SELECT relname,
               EXTRACT(EPOCH FROM (NOW() - last_analyze)) / 3600.0 AS hours_since_analyze
        FROM pg_stat_user_tables
        WHERE relname IN ('daily_metrics', 'user_metrics')
    """)

    stale = []
    for relname, hours in rows:
        if hours is not None and hours > 2:
            stale.append(f"{relname} ({hours:.1f}h ago)")

    status = "fail" if stale else "pass"
    detail = stale if stale else "both views refreshed within 2 hours"
    _push_result(context["ti"], "check_stale_materialized_views", status, detail)
    if status == "fail":
        raise ValueError(f"Stale materialized views: {detail}")


# ---------------------------------------------------------------------------
# Summary task
# ---------------------------------------------------------------------------

CHECK_TASK_IDS = [
    "check_null_user_ids",
    "check_null_amounts",
    "check_orphan_transactions",
    "check_duplicate_transactions",
    "check_revenue_anomaly",
    "check_transaction_volume",
    "check_stale_materialized_views",
]


def summarize_quality(**context):
    ti = context["ti"]
    results = []
    for task_id in CHECK_TASK_IDS:
        result = ti.xcom_pull(task_ids=task_id, key=task_id)
        if result:
            results.append(result)

    passed = [r for r in results if r.get("status") == "pass"]
    failed = [r for r in results if r.get("status") == "fail"]

    log.info("=" * 60)
    log.info("DATA QUALITY REPORT — %s", context["ds"])
    log.info("Passed: %d / %d", len(passed), len(results))
    for r in passed:
        log.info("  PASS | %s | value=%s", r["check"], r["value"])
    for r in failed:
        log.warning("  FAIL | %s | value=%s", r["check"], r["value"])
    log.info("=" * 60)

    # Push summary for downstream DAGs to consume
    ti.xcom_push(key="quality_summary", value={
        "date": context["ds"],
        "total": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "status": "pass" if not failed else "fail",
    })


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="data_quality_dag",
    description="7 parallel data quality checks — runs nightly at 1:30 AM before daily pipeline",
    schedule_interval="30 1 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["quality", "daily", "phase3"],
) as dag:

    t_null_users = PythonOperator(
        task_id="check_null_user_ids",
        python_callable=check_null_user_ids,
    )

    t_null_amounts = PythonOperator(
        task_id="check_null_amounts",
        python_callable=check_null_amounts,
    )

    t_orphans = PythonOperator(
        task_id="check_orphan_transactions",
        python_callable=check_orphan_transactions,
    )

    t_duplicates = PythonOperator(
        task_id="check_duplicate_transactions",
        python_callable=check_duplicate_transactions,
    )

    t_revenue = PythonOperator(
        task_id="check_revenue_anomaly",
        python_callable=check_revenue_anomaly,
    )

    t_volume = PythonOperator(
        task_id="check_transaction_volume",
        python_callable=check_transaction_volume,
    )

    t_stale_views = PythonOperator(
        task_id="check_stale_materialized_views",
        python_callable=check_stale_materialized_views,
    )

    # ALL_DONE: summarize runs whether checks pass or fail
    t_summarize = PythonOperator(
        task_id="summarize_quality",
        python_callable=summarize_quality,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # All 7 checks run in parallel, then summarize
    [
        t_null_users,
        t_null_amounts,
        t_orphans,
        t_duplicates,
        t_revenue,
        t_volume,
        t_stale_views,
    ] >> t_summarize
