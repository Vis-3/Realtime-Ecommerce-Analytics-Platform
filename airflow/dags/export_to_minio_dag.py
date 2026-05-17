"""
DAG: Export to MinIO (Object Storage)
Schedule: 3:00 AM daily  (after daily_analytics_dag at 2 AM, dbt marts are fresh)

WHY THIS DAG EXISTS:
    The dbt marts and raw transactions live in Postgres, but Postgres is an
    OLTP database — it is not designed for large sequential scans.  Exporting
    to MinIO (S3-compatible object storage) as Parquet files serves two purposes:

    1. Archival: historical data accumulates cheaply in object storage without
       bloating Postgres or slowing down OLTP queries.

    2. Spark input: the cohort_retention PySpark job reads from MinIO so it
       never touches Postgres during its scan-heavy computation.  Postgres only
       sees the small aggregated result written back at the end.

PARQUET:
    Column-oriented format; Spark, DuckDB, and every cloud warehouse can read
    it natively.  Writing via pyarrow keeps the Airflow worker lightweight —
    no Spark needed for the export step itself.

PIPELINE:
    ensure_bucket_exists
        → [export_transactions,
           export_mart_rfm,
           export_mart_churn,
           export_mart_snapshot]   (all parallel)
        → log_export_summary
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "ecommerce_postgres"
MINIO_HOST       = "minio:9000"
MINIO_KEY        = "minioadmin"
MINIO_SECRET     = "minioadmin"
BUCKET           = "ecommerce-exports"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minio_client():
    from minio import Minio
    return Minio(MINIO_HOST, access_key=MINIO_KEY, secret_key=MINIO_SECRET, secure=False)


def _df_to_parquet_bytes(df) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq
    buf   = io.BytesIO()
    table = pa.Table.from_pandas(df)
    pq.write_table(table, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def ensure_bucket_exists(**_):
    client = _minio_client()
    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
        log.info("Created MinIO bucket: %s", BUCKET)
    else:
        log.info("Bucket already exists: %s", BUCKET)


def _export(table_name: str, query: str, object_path: str, ti, **_):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    df   = hook.get_pandas_df(query)
    log.info("Fetched %d rows from %s", len(df), table_name)

    data   = _df_to_parquet_bytes(df)
    client = _minio_client()
    client.put_object(
        BUCKET, object_path,
        io.BytesIO(data), len(data),
        content_type="application/octet-stream",
    )
    log.info("Exported → s3://%s/%s (%d bytes)", BUCKET, object_path, len(data))
    ti.xcom_push(key=f"{table_name}_rows", value=len(df))


def export_transactions(ti, **_):
    _export(
        table_name="transactions",
        query="""
            SELECT transaction_id, user_id, product_id,
                   transaction_date::date AS transaction_date,
                   quantity, unit_price, total_amount, payment_method
            FROM transactions
        """,
        object_path="transactions/transactions.parquet",
        ti=ti,
    )


def export_mart_rfm(ti, **_):
    _export(
        table_name="mart_rfm_segments",
        query="SELECT * FROM mart_rfm_segments",
        object_path="marts/mart_rfm_segments.parquet",
        ti=ti,
    )


def export_mart_churn(ti, **_):
    _export(
        table_name="mart_churn_features",
        query="SELECT * FROM mart_churn_features",
        object_path="marts/mart_churn_features.parquet",
        ti=ti,
    )


def export_mart_snapshot(ti, **_):
    _export(
        table_name="mart_daily_snapshot",
        query="SELECT * FROM mart_daily_snapshot",
        object_path="marts/mart_daily_snapshot.parquet",
        ti=ti,
    )


def log_export_summary(ti, **_):
    for name in ["transactions", "mart_rfm_segments", "mart_churn_features", "mart_daily_snapshot"]:
        rows = ti.xcom_pull(key=f"{name}_rows") or 0
        log.info("%-30s  %d rows", name, rows)
    log.info("All exports complete → s3://%s/", BUCKET)


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

default_args = {
    "owner":           "data-engineering",
    "depends_on_past": False,
    "retries":         1,
    "retry_delay":     timedelta(minutes=5),
}

with DAG(
    dag_id="export_to_minio_dag",
    description="Export dbt marts + raw transactions to MinIO as Parquet (Spark input)",
    schedule_interval="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["daily", "minio", "parquet", "export"],
) as dag:

    t_bucket = PythonOperator(
        task_id="ensure_bucket_exists",
        python_callable=ensure_bucket_exists,
    )

    t_txn = PythonOperator(
        task_id="export_transactions",
        python_callable=export_transactions,
    )

    t_rfm = PythonOperator(
        task_id="export_mart_rfm",
        python_callable=export_mart_rfm,
    )

    t_churn = PythonOperator(
        task_id="export_mart_churn",
        python_callable=export_mart_churn,
    )

    t_snapshot = PythonOperator(
        task_id="export_mart_snapshot",
        python_callable=export_mart_snapshot,
    )

    t_summary = PythonOperator(
        task_id="log_export_summary",
        python_callable=log_export_summary,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_bucket >> [t_txn, t_rfm, t_churn, t_snapshot] >> t_summary
