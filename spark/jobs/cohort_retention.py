"""
PySpark job: Monthly cohort retention analysis.

WHY SPARK:
    Cohort retention requires pairing every user's purchase months against their
    first purchase month — effectively a self-join across the full transaction
    history. At 162K+ rows growing daily, that pattern is too scan-heavy to run
    inside Postgres at 3 AM alongside the analytics pipeline. Spark reads the
    Parquet export from MinIO, processes it in memory with its DataFrame API,
    and writes back only the aggregated result (a few hundred rows) to Postgres.
    Postgres never sees the heavy scan.

WHAT IT COMPUTES:
    For each cohort (users whose first purchase was in month X):
      - cohort_size: how many users made their first purchase in month X
      - retained_users: how many of those users purchased in month X+N
      - retention_rate: retained_users / cohort_size

    Example output row:
      cohort_month=2024-01, months_since_first=3, cohort_size=450,
      retained_users=198, retention_rate=0.44

    This shows whether Champions return reliably (they do) and how fast
    New/Hibernating cohorts fall off — the shape of the curves validates
    the persona-driven simulator.

RUN:
    docker compose --profile spark run --rm spark
"""

import os
import tempfile
import logging

import psycopg2
from minio import Minio
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MINIO_HOST    = os.getenv("MINIO_HOST",       "minio:9000")
MINIO_KEY     = os.getenv("MINIO_ACCESS_KEY",  "minioadmin")
MINIO_SECRET  = os.getenv("MINIO_SECRET_KEY",  "minioadmin")
BUCKET        = "ecommerce-exports"

POSTGRES_HOST = os.getenv("POSTGRES_HOST",     "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB   = os.getenv("POSTGRES_DB",       "ecommerce")
POSTGRES_USER = os.getenv("POSTGRES_USER",     "postgres")
POSTGRES_PASS = os.getenv("POSTGRES_PASSWORD", "postgres")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("cohort_retention")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.driver.memory", "1g")
        .getOrCreate()
    )


def fetch_parquet(client: Minio, remote_path: str) -> str:
    """Download a Parquet object from MinIO to a local temp file."""
    tmp = tempfile.mktemp(suffix=".parquet")
    client.fget_object(BUCKET, remote_path, tmp)
    log.info("Downloaded s3://%s/%s → %s", BUCKET, remote_path, tmp)
    return tmp


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_cohort_retention(spark: SparkSession, parquet_path: str):
    """
    Input columns needed: user_id, transaction_date (DATE)

    Steps:
      1. Truncate transaction_date to month → purchase_month
      2. Find each user's cohort_month = MIN(purchase_month)
      3. Cross-reference: for each (user, purchase_month) how many months
         since cohort_month?
      4. Aggregate: distinct retained users per (cohort_month, months_since_first)
      5. Divide by cohort_size to get retention_rate
    """
    df = spark.read.parquet(parquet_path)

    # One row per (user_id, purchase_month) — deduplicated
    purchases = (
        df.select(
            F.col("user_id"),
            F.date_trunc("month", F.col("transaction_date").cast("date"))
            .cast("date")
            .alias("purchase_month"),
        )
        .distinct()
    )

    # Cohort = each user's first purchase month
    cohorts = purchases.groupBy("user_id").agg(
        F.min("purchase_month").alias("cohort_month")
    )

    # Join every purchase back to its cohort
    joined = purchases.join(cohorts, on="user_id")

    # Months elapsed since cohort month
    joined = joined.withColumn(
        "months_since_first",
        (
            F.year("purchase_month")  * 12 + F.month("purchase_month")
            - F.year("cohort_month")  * 12 - F.month("cohort_month")
        ).cast("int"),
    )

    # Cohort size = users present at month 0
    cohort_sizes = (
        joined.filter(F.col("months_since_first") == 0)
        .groupBy("cohort_month")
        .agg(F.countDistinct("user_id").alias("cohort_size"))
    )

    # Retained users per period
    retained = (
        joined.groupBy("cohort_month", "months_since_first")
        .agg(F.countDistinct("user_id").alias("retained_users"))
    )

    result = (
        retained
        .join(cohort_sizes, on="cohort_month")
        .withColumn(
            "retention_rate",
            F.round(F.col("retained_users") / F.col("cohort_size"), 4),
        )
        .orderBy("cohort_month", "months_since_first")
    )

    return result


# ---------------------------------------------------------------------------
# Postgres write-back
# ---------------------------------------------------------------------------

def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cohort_retention (
            cohort_month        DATE        NOT NULL,
            months_since_first  INTEGER     NOT NULL,
            cohort_size         INTEGER     NOT NULL,
            retained_users      INTEGER     NOT NULL,
            retention_rate      NUMERIC(6, 4),
            computed_at         TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (cohort_month, months_since_first)
        )
    """)


def write_to_postgres(result_df):
    rows = result_df.collect()
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT, dbname=POSTGRES_DB,
        user=POSTGRES_USER, password=POSTGRES_PASS,
    )
    cur = conn.cursor()
    ensure_table(cur)
    cur.execute("TRUNCATE cohort_retention")
    cur.executemany(
        """
        INSERT INTO cohort_retention
            (cohort_month, months_since_first, cohort_size, retained_users, retention_rate)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [
            (
                row.cohort_month,
                row.months_since_first,
                row.cohort_size,
                row.retained_users,
                float(row.retention_rate),
            )
            for row in rows
        ],
    )
    conn.commit()
    cur.close()
    conn.close()
    log.info("Wrote %d cohort retention rows to Postgres", len(rows))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    client = Minio(MINIO_HOST, access_key=MINIO_KEY, secret_key=MINIO_SECRET, secure=False)
    parquet_path = fetch_parquet(client, "transactions/transactions.parquet")

    spark  = build_spark()
    result = compute_cohort_retention(spark, parquet_path)

    log.info("Sample cohort retention output:")
    result.show(20, truncate=False)

    write_to_postgres(result)
    spark.stop()
    log.info("Cohort retention job complete")


if __name__ == "__main__":
    main()
