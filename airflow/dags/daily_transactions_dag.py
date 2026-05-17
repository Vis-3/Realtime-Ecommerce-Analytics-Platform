"""
DAG: Daily Transaction Generator
Schedule: 1:00 AM daily  (runs before daily_analytics_dag at 2:00 AM)

WHY THIS DAG EXISTS:
    The Kafka producer simulates real-time user sessions but requires both
    Kafka and the consumer to be running.  For a scheduled daily job we want
    something simpler and more reliable: insert today's transactions directly
    into Postgres using the same persona-driven behavioural model used when
    seeding, so the dashboard always has fresh data without manual intervention.

HOW MANY TRANSACTIONS:
    Each user gets a daily purchase probability derived from their persona's
    Weibull scale parameter  (probability ≈ 1 / scale).  With 10 K users this
    produces ~300-400 transactions/day — realistic for a mid-size e-commerce
    store and enough to show visible movement on every dashboard chart.

PIPELINE:
    check_connection
        → generate_daily_transactions   (persona-weighted inserts)
        → validate_transaction_count    (fails loudly if 0 rows)
        → trigger_view_refresh          (so dashboard is live immediately)
        → log_summary
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, date

from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "ecommerce_postgres"

# ---------------------------------------------------------------------------
# Persona parameters — must match seed_transactions.py
# daily_prob = 1 / ipt_scale  (expected purchases per day)
# ---------------------------------------------------------------------------
PERSONA_CONFIG = {
    #              daily_prob   price_mu  price_sig  qty_max
    "Champion":   (1 / 10,      3.6,      0.7,       5),
    "Loyal":      (1 / 22,      3.3,      0.8,       4),
    "New":        (1 / 44,      3.1,      0.9,       3),
    "Hibernating":(1 / 60,      3.0,      0.9,       3),
    "AtRisk":     (1 / 200,     3.1,      0.8,       3),
}

PAYMENT_METHODS = ["credit_card", "paypal", "debit_card", "apple_pay"]


# ---------------------------------------------------------------------------
# Task: check connection
# ---------------------------------------------------------------------------

def check_connection(**context):
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    hook.get_conn()
    log.info("PostgreSQL connection OK")


# ---------------------------------------------------------------------------
# Task: generate transactions
# ---------------------------------------------------------------------------

def generate_daily_transactions(**context):
    import numpy as np

    hook    = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    conn    = hook.get_conn()
    cur     = conn.cursor()
    today   = date.today()

    # Load users and products
    cur.execute("SELECT user_id, persona FROM users")
    users = cur.fetchall()

    cur.execute("SELECT product_id FROM products")
    product_ids = [r[0] for r in cur.fetchall()]

    if not product_ids:
        raise AirflowException("No products found — cannot generate transactions")

    rng      = np.random.default_rng()
    inserted = 0
    batch    = []

    for user_id, persona in users:
        cfg = PERSONA_CONFIG.get(persona, PERSONA_CONFIG["New"])
        daily_prob, price_mu, price_sig, qty_max = cfg

        if rng.random() > daily_prob:
            continue   # this user doesn't purchase today

        product_id   = int(rng.choice(product_ids))
        quantity     = int(rng.integers(1, qty_max + 1))
        unit_price   = float(np.clip(rng.lognormal(price_mu, price_sig), 5.0, 500.0))
        unit_price   = round(unit_price, 2)
        total_amount = round(quantity * unit_price, 2)
        discount     = round(float(rng.uniform(0, min(total_amount * 0.15, 20))), 2)
        payment      = random.choice(PAYMENT_METHODS)

        # Random time between 7 AM and 11 PM
        hour   = int(rng.integers(7, 23))
        minute = int(rng.integers(0, 60))
        ts     = datetime.combine(today, datetime.min.time()).replace(
            hour=hour, minute=minute
        )

        batch.append((user_id, product_id, ts, quantity,
                      unit_price, total_amount, discount, payment))

    if batch:
        cur.executemany("""
            INSERT INTO transactions
                (user_id, product_id, transaction_date, quantity,
                 unit_price, total_amount, discount_amount, payment_method)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, batch)
        conn.commit()
        inserted = len(batch)

    cur.close()
    conn.close()

    log.info("Generated %d transactions for %s", inserted, today)
    context["ti"].xcom_push(key="transactions_generated", value=inserted)

    # Persona breakdown for observability
    persona_counts: dict[str, int] = {}
    for _, persona in users:
        cfg = PERSONA_CONFIG.get(persona, PERSONA_CONFIG["New"])
        # approximate expected count
        persona_counts[persona] = persona_counts.get(persona, 0)
    log.info("Daily transaction generation complete | total=%d", inserted)


# ---------------------------------------------------------------------------
# Task: validate
# ---------------------------------------------------------------------------

def validate_transaction_count(**context):
    generated = context["ti"].xcom_pull(
        task_ids="generate_daily_transactions", key="transactions_generated"
    ) or 0

    if generated == 0:
        raise AirflowException(
            "No transactions were generated today. "
            "Check that users exist and persona probabilities are non-zero."
        )

    log.info("Validation passed — %d transactions generated", generated)


# ---------------------------------------------------------------------------
# Task: log summary
# ---------------------------------------------------------------------------

def log_summary(**context):
    generated = context["ti"].xcom_pull(
        task_ids="generate_daily_transactions", key="transactions_generated"
    ) or 0

    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    row  = hook.get_first("""
        SELECT COUNT(*), COALESCE(SUM(total_amount), 0), COALESCE(AVG(total_amount), 0)
        FROM transactions
        WHERE transaction_date::date = CURRENT_DATE
    """)

    count   = row[0] if row else 0
    revenue = float(row[1]) if row else 0.0
    aov     = float(row[2]) if row else 0.0

    log.info(
        "Today's snapshot | date=%s | transactions=%d | revenue=$%.2f | AOV=$%.2f",
        context["ds"], count, revenue, aov,
    )


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

def on_failure_callback(context):
    log.error(
        "Task failed | dag=%s | task=%s | ts=%s",
        context["dag"].dag_id,
        context["task_instance"].task_id,
        context["ts"],
    )


default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": on_failure_callback,
}

with DAG(
    dag_id="daily_transactions_dag",
    description="Generate daily transactions from persona-weighted probabilities, then refresh views",
    schedule_interval="0 1 * * *",   # 1 AM — before analytics pipeline at 2 AM
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["daily", "simulation", "transactions"],
) as dag:

    t_check = PythonOperator(
        task_id="check_connection",
        python_callable=check_connection,
    )

    t_generate = PythonOperator(
        task_id="generate_daily_transactions",
        python_callable=generate_daily_transactions,
        execution_timeout=timedelta(minutes=10),
    )

    t_validate = PythonOperator(
        task_id="validate_transaction_count",
        python_callable=validate_transaction_count,
    )

    # Trigger the view refresh so the dashboard is live immediately,
    # without waiting for the hourly refresh to fire on its own.
    t_refresh = TriggerDagRunOperator(
        task_id="trigger_view_refresh",
        trigger_dag_id="hourly_refresh_dag",
        wait_for_completion=False,  # fire-and-forget; don't block the transactions DAG
    )

    t_summary = PythonOperator(
        task_id="log_summary",
        python_callable=log_summary,
    )

    t_check >> t_generate >> t_validate >> t_refresh >> t_summary
