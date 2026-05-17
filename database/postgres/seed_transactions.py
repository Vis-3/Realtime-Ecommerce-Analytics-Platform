"""
Persona-driven transaction seeder.

Replaces the uniform-random SQL transaction seed with purchase sequences
sampled from Weibull inter-purchase time distributions, calibrated against
the UCI Online Retail dataset (541K transactions, 4,338 customers).

Why Weibull?
  The UCI dataset inter-purchase times fit a Weibull(shape=0.93, scale=44)
  distribution. shape < 1 means the hazard rate decreases over time — a
  customer who just bought is LESS likely to buy again immediately, which
  matches real shopping behavior. Each persona gets a different scale
  parameter reflecting how frequently they actually purchase.

Why forward-looking churn label?
  Defining churn as recency > 90 days and using recency as a feature is
  circular — the model just learns the threshold, not actual behavior.
  Instead we compute features at SNAPSHOT_DATE and label = did NOT purchase
  in the 30 days after. This forces the model to learn behavioral signals
  (trajectory, frequency patterns) rather than re-deriving the label.

Run after seed_data.sql:
    python seed_transactions.py
"""

import os
import numpy as np
import psycopg2
import psycopg2.extras
from datetime import date, timedelta, datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB = dict(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", 5432)),
    database=os.getenv("POSTGRES_DB", "ecommerce"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "postgres"),
)

TODAY          = date.today()
SNAPSHOT_DATE  = TODAY - timedelta(days=30)   # features computed as of here
HISTORY_START  = date(2024, 1, 1)             # earliest transaction date
BATCH_SIZE     = 2000
RNG            = np.random.default_rng(42)

# ---------------------------------------------------------------------------
# Persona parameters — calibrated against UCI Online Retail
#
# ipt_shape : Weibull shape  (0.93 across all — from dataset fit)
# ipt_scale : Weibull scale  (mean inter-purchase time in days, per persona)
# price_mu  : log-normal μ for unit price  (ln-scale)
# price_sig : log-normal σ for unit price
# qty_max   : max items per transaction
# ---------------------------------------------------------------------------

PERSONAS = {
    #                ipt_shape  ipt_scale  price_mu  price_sig  qty_max
    "Champion":    (  0.93,      10,        3.6,      0.7,       5  ),
    "Loyal":       (  0.93,      22,        3.3,      0.8,       4  ),
    "AtRisk":      (  0.93,      15,        3.3,      0.8,       4  ),
    "New":         (  0.93,      44,        3.1,      0.9,       3  ),
    "Hibernating": (  0.93,      60,        3.0,      0.9,       3  ),
}

PAYMENT_METHODS = ["credit_card", "paypal", "debit_card", "apple_pay"]


# ---------------------------------------------------------------------------
# Purchase date generation
# ---------------------------------------------------------------------------

def _weibull_ipt(shape: float, scale: float) -> int:
    """Sample one inter-purchase time in whole days (minimum 1)."""
    return max(1, int(RNG.weibull(shape) * scale))


def generate_purchase_dates(persona: str, reg_date: date) -> list[date]:
    """
    Return a list of purchase dates for one user.

    The last purchase date is determined by persona:
      Champion / Loyal  → buying up to today (active customers)
      AtRisk            → stopped 90-180 days before today (were loyal, now gone)
      Hibernating       → last purchase 45-300 days ago (irregular, lapsing)
      New               → 1-2 purchases total, anywhere in their tenure
    """
    shape, scale, *_ = PERSONAS[persona]
    start = max(reg_date, HISTORY_START)

    if persona == "AtRisk":
        # High historical frequency, then a hard stop.
        days_since_last = int(RNG.integers(90, 181))
        end = TODAY - timedelta(days=days_since_last)
    elif persona == "Hibernating":
        # Wide spread — some lapsed recently, some long ago.
        days_since_last = int(RNG.integers(45, 301))
        end = TODAY - timedelta(days=days_since_last)
    else:
        # Champion, Loyal, New — potentially active up to today.
        end = TODAY

    if start > end:
        # Edge case: user registered after their persona's activity window.
        return [start]

    dates: list[date] = []
    current = start

    while current <= end:
        dates.append(current)
        current += timedelta(days=_weibull_ipt(shape, scale))

        if persona == "New" and len(dates) >= 2:
            break

    return dates if dates else [start]


# ---------------------------------------------------------------------------
# Transaction generation
# ---------------------------------------------------------------------------

def _make_transaction(user_id: int, persona: str, purchase_date: date,
                       product_ids: list[int]) -> tuple:
    _, _, price_mu, price_sig, qty_max = PERSONAS[persona]

    product_id   = int(RNG.choice(product_ids))
    quantity     = int(RNG.integers(1, qty_max + 1))
    unit_price   = float(np.clip(RNG.lognormal(price_mu, price_sig), 5.0, 500.0))
    unit_price   = round(unit_price, 2)
    total_amount = round(quantity * unit_price, 2)
    discount     = round(float(RNG.uniform(0, min(total_amount * 0.15, 20))), 2)
    payment      = PAYMENT_METHODS[int(RNG.integers(0, len(PAYMENT_METHODS)))]

    # Randomise time-of-day (8 AM – 10 PM)
    ts = datetime.combine(purchase_date, datetime.min.time()) + timedelta(
        hours=int(RNG.integers(8, 22)),
        minutes=int(RNG.integers(0, 60)),
    )

    return (user_id, product_id, ts, quantity, unit_price, total_amount, discount, payment)


def seed_transactions(conn, product_ids: list[int]) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, persona, registration_date FROM users ORDER BY user_id")
    users = cursor.fetchall()
    cursor.close()

    print(f"Generating transactions for {len(users):,} users...")

    batch: list[tuple] = []
    total = 0

    for user_id, persona, reg_date in users:
        persona = persona if persona in PERSONAS else "New"
        if isinstance(reg_date, datetime):
            reg_date = reg_date.date()

        for purchase_date in generate_purchase_dates(persona, reg_date):
            batch.append(_make_transaction(user_id, persona, purchase_date, product_ids))

        if len(batch) >= BATCH_SIZE:
            _flush(conn, batch)
            total += len(batch)
            print(f"  {total:,} transactions inserted...")
            batch = []

    if batch:
        _flush(conn, batch)
        total += len(batch)

    print(f"Done — {total:,} transactions inserted.")


def _flush(conn, batch: list[tuple]) -> None:
    cursor = conn.cursor()
    psycopg2.extras.execute_values(
        cursor,
        """
        INSERT INTO transactions
            (user_id, product_id, transaction_date, quantity,
             unit_price, total_amount, discount_amount, payment_method)
        VALUES %s
        ON CONFLICT DO NOTHING
        """,
        batch,
    )
    conn.commit()
    cursor.close()


# ---------------------------------------------------------------------------
# Verification — quick sanity check after seeding
# ---------------------------------------------------------------------------

def verify(conn) -> None:
    cursor = conn.cursor()
    cursor.execute("""
        WITH last_purchase AS (
            SELECT user_id,
                   MAX(transaction_date)::date AS last_date,
                   COUNT(transaction_id)        AS txn_count,
                   AVG(total_amount)            AS avg_aov
            FROM transactions
            GROUP BY user_id
        )
        SELECT
            u.persona,
            COUNT(DISTINCT u.user_id)                                        AS users,
            COALESCE(SUM(lp.txn_count), 0)::bigint                          AS transactions,
            ROUND(AVG(CURRENT_DATE - lp.last_date))                         AS avg_recency_days,
            ROUND(AVG(lp.avg_aov)::numeric, 2)                              AS avg_order_value,
            ROUND(
                SUM(CASE WHEN CURRENT_DATE - lp.last_date > 90
                         THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(DISTINCT u.user_id), 0) * 100, 1
            )                                                                AS churn_pct
        FROM users u
        LEFT JOIN last_purchase lp ON lp.user_id = u.user_id
        GROUP BY u.persona
        ORDER BY avg_recency_days
    """)
    rows = cursor.fetchall()
    cursor.close()

    print("\n--- Verification ---")
    print(f"{'Persona':<14} {'Users':>6} {'Txns':>8} {'Avg Recency':>12} {'Avg AOV':>9} {'Churn%':>7}")
    print("-" * 62)
    for row in rows:
        print(f"{str(row[0]):<14} {row[1]:>6,} {row[2]:>8,} {str(row[3]):>12} {str(row[4]):>9} {str(row[5]):>6}%")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    conn = psycopg2.connect(**DB)

    cur = conn.cursor()
    cur.execute("SELECT product_id FROM products")
    product_ids = [r[0] for r in cur.fetchall()]
    cur.close()

    if not product_ids:
        raise RuntimeError("No products found. Run seed_data.sql first.")

    seed_transactions(conn, product_ids)
    verify(conn)

    # Refresh materialized views so the dashboard reflects the new data
    print("\nRefreshing materialized views...")
    cur = conn.cursor()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY daily_metrics")
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY user_metrics")
    conn.commit()
    cur.close()

    conn.close()
    print("Seeding complete.")
