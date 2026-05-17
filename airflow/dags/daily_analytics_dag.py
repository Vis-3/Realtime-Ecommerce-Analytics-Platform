"""
DAG: Daily Analytics Pipeline
Schedule: 2:00 AM daily  (after daily_transactions_dag at 1 AM)

Flow:
  check_yesterdays_data
    → run_data_quality_checks
      → branch_on_quality
        → quality_pass / quality_fail_alert
          → dbt_test_staging          [schema tests on stg_transactions + stg_users]
            → dbt_run_marts           [int_rfm_scores → mart_rfm_segments,
                                       mart_churn_features, mart_daily_snapshot]
              → apply_rfm_to_users    [UPDATE users.customer_segment from mart]
              → apply_churn_scores    [UPDATE users.churn_risk_score from mart_churn_features]
              → apply_snapshot_to_log [UPSERT daily_report_log from mart_daily_snapshot]
                → notify_completion

WHY dbt:
  Previously the RFM segmentation, churn score, and daily snapshot were
  SQL strings embedded inside this file.  dbt moves that logic into
  versioned, tested, self-documenting models.  Airflow now orchestrates
  *when* transformations run — not *how* they work.  If a column is renamed,
  dbt tests catch it here before the 2 AM run ever updates the users table.
"""

from datetime import datetime, timedelta
import logging

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "ecommerce_postgres"
DBT_DIR          = "/opt/airflow/dbt"
# --project-dir and --profiles-dir are subcommand flags in dbt 1.x (go after run/test)
DBT_FLAGS        = f"--project-dir {DBT_DIR} --profiles-dir {DBT_DIR} --no-use-colors"

# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------

def check_yesterdays_data(**context):
    hook  = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    count = hook.get_first("""
        SELECT COUNT(*)
        FROM transactions
        WHERE DATE(transaction_date) = CURRENT_DATE - 1
    """)[0]

    log.info("Yesterday's transaction count: %d", count)
    context["ti"].xcom_push(key="yesterday_txn_count", value=count)

    if count == 0:
        raise AirflowSkipException("No transactions found for yesterday — skipping pipeline")


def run_data_quality_checks(**context):
    hook     = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    failures = []

    null_users = hook.get_first(
        "SELECT COUNT(*) FROM transactions WHERE user_id IS NULL"
    )[0]
    if null_users > 0:
        failures.append(f"null_user_ids={null_users}")

    bad_amounts = hook.get_first(
        "SELECT COUNT(*) FROM transactions WHERE total_amount < 0"
    )[0]
    if bad_amounts > 0:
        failures.append(f"negative_amounts={bad_amounts}")

    orphans = hook.get_first("""
        SELECT COUNT(*)
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.user_id
        WHERE u.user_id IS NULL
          AND DATE(t.transaction_date) = CURRENT_DATE - 1
    """)[0]
    if orphans > 0:
        failures.append(f"orphan_transactions={orphans}")

    result = "fail" if failures else "pass"
    context["ti"].xcom_push(key="quality_result",   value=result)
    context["ti"].xcom_push(key="quality_failures", value=failures)
    log.info("Quality check result: %s | failures=%s", result, failures)
    return result


def branch_on_quality(**context):
    result = context["ti"].xcom_pull(
        task_ids="run_data_quality_checks", key="quality_result"
    )
    return "quality_pass" if result == "pass" else "quality_fail_alert"


def quality_fail_alert(**context):
    failures = context["ti"].xcom_pull(
        task_ids="run_data_quality_checks", key="quality_failures"
    )
    log.warning(
        "Quality checks FAILED for %s — pipeline continues with known issues: %s",
        context["ds"], failures,
    )


def notify_completion(**context):
    ti        = context["ti"]
    txn_count = ti.xcom_pull(task_ids="check_yesterdays_data", key="yesterday_txn_count") or 0

    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    row  = hook.get_first("""
        SELECT total_revenue, avg_order_value
        FROM daily_report_log
        WHERE report_date = CURRENT_DATE - 1
    """)
    revenue = float(row[0]) if row and row[0] else 0.0
    aov     = float(row[1]) if row and row[1] else 0.0

    log.info(
        "Daily pipeline complete for %s | transactions=%d | revenue=$%.2f | AOV=$%.2f",
        context["ds"], txn_count, revenue, aov,
    )


# ---------------------------------------------------------------------------
# Write-back SQL — applied after dbt marts are built
# ---------------------------------------------------------------------------

APPLY_RFM_SQL = """
UPDATE users u
SET
    customer_segment = m.customer_segment,
    updated_at       = CURRENT_TIMESTAMP
FROM mart_rfm_segments m
WHERE u.user_id = m.user_id;
"""

APPLY_CHURN_SQL = """
UPDATE users u
SET
    churn_risk_score = LEAST(1.0, ROUND(
        (cf.recency_days::numeric / 365)
        * (1 - LEAST(1.0, cf.frequency::numeric / 20)),
        2
    )),
    updated_at = CURRENT_TIMESTAMP
FROM mart_churn_features cf
WHERE u.user_id = cf.user_id;
"""

APPLY_SNAPSHOT_SQL = """
INSERT INTO daily_report_log
    (report_date, total_users, total_transactions, total_revenue, avg_order_value, created_at)
SELECT
    report_date,
    total_users,
    total_transactions,
    total_revenue,
    avg_order_value,
    CURRENT_TIMESTAMP
FROM mart_daily_snapshot
WHERE report_date = CURRENT_DATE - 1
ON CONFLICT (report_date) DO UPDATE
    SET total_users        = EXCLUDED.total_users,
        total_transactions = EXCLUDED.total_transactions,
        total_revenue      = EXCLUDED.total_revenue,
        avg_order_value    = EXCLUDED.avg_order_value,
        created_at         = EXCLUDED.created_at;
"""

# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

default_args = {
    "owner":           "data-engineering",
    "depends_on_past": False,
    "retries":         1,
    "retry_delay":     timedelta(minutes=10),
}

with DAG(
    dag_id="daily_analytics_dag",
    description="Quality gate → dbt transformations → write-back to operational tables",
    schedule_interval="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["daily", "rfm", "churn", "dbt"],
) as dag:

    t_check_yesterday = PythonOperator(
        task_id="check_yesterdays_data",
        python_callable=check_yesterdays_data,
    )

    t_quality = PythonOperator(
        task_id="run_data_quality_checks",
        python_callable=run_data_quality_checks,
    )

    t_branch = BranchPythonOperator(
        task_id="branch_on_quality",
        python_callable=branch_on_quality,
    )

    t_quality_pass = EmptyOperator(task_id="quality_pass")

    t_quality_fail = PythonOperator(
        task_id="quality_fail_alert",
        python_callable=quality_fail_alert,
    )

    # dbt build = run + test in dependency order for each model.
    # Staging views are created first, tested, then intermediate and mart tables
    # are built on top. If a staging test fails, downstream marts never run.
    t_dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"dbt build {DBT_FLAGS} "
            "--select stg_transactions stg_users "
            "int_rfm_scores "
            "mart_rfm_segments mart_churn_features mart_daily_snapshot"
        ),
        trigger_rule=TriggerRule.ONE_SUCCESS,
    )

    t_apply_rfm = PostgresOperator(
        task_id="apply_rfm_to_users",
        postgres_conn_id=POSTGRES_CONN_ID,
        sql=APPLY_RFM_SQL,
    )

    t_apply_churn = PostgresOperator(
        task_id="apply_churn_scores",
        postgres_conn_id=POSTGRES_CONN_ID,
        sql=APPLY_CHURN_SQL,
    )

    t_apply_snapshot = PostgresOperator(
        task_id="apply_snapshot_to_log",
        postgres_conn_id=POSTGRES_CONN_ID,
        sql=APPLY_SNAPSHOT_SQL,
    )

    t_notify = PythonOperator(
        task_id="notify_completion",
        python_callable=notify_completion,
        trigger_rule=TriggerRule.ALL_SUCCESS,
    )

    # Pipeline wiring
    t_check_yesterday >> t_quality >> t_branch
    t_branch >> [t_quality_pass, t_quality_fail]
    [t_quality_pass, t_quality_fail] >> t_dbt_build
    # rfm and churn both UPDATE users — run sequentially to avoid deadlock
    t_dbt_build >> t_apply_rfm >> t_apply_churn
    # snapshot writes to daily_report_log (different table) — safe to run in parallel
    t_dbt_build >> t_apply_snapshot
    [t_apply_churn, t_apply_snapshot] >> t_notify
