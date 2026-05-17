"""
Kafka → PostgreSQL consumer (no Spark required).
Reads purchase events from the 'transactions' Kafka topic
and inserts them directly into the PostgreSQL transactions table.
"""

import json
import logging
import signal
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from kafka import KafkaConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = dict(
    host="localhost", port=5432,
    database="ecommerce", user="postgres", password="postgres",
)

INSERT_SQL = """
    INSERT INTO transactions
        (user_id, product_id, session_id, transaction_date,
         quantity, unit_price, total_amount, payment_method, order_status)
    VALUES
        (%(user_id)s, %(product_id)s, %(session_id)s, %(transaction_date)s,
         %(quantity)s, %(unit_price)s, %(total_amount)s, %(payment_method)s, 'completed')
    ON CONFLICT DO NOTHING
"""


def run():
    log.info("Connecting to Kafka...")
    consumer = KafkaConsumer(
        "transactions",
        bootstrap_servers=["localhost:9092"],
        group_id="pg-transaction-writer",
        auto_offset_reset="latest",
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
    )

    log.info("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    inserted = 0

    def _shutdown(sig, frame):
        log.info("Shutting down — %d rows inserted this session.", inserted)
        consumer.close()
        conn.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("Listening for purchase events on 'transactions' topic...")

    for message in consumer:
        event = message.value
        if event.get("event_type") != "purchase":
            continue

        try:
            row = {
                "user_id":          event["user_id"],
                "product_id":       event["product_id"],
                "session_id":       event.get("session_id"),
                "transaction_date": datetime.now(timezone.utc).replace(tzinfo=None),
                "quantity":         event["quantity"],
                "unit_price":       event["unit_price"],
                "total_amount":     event["total_amount"],
                "payment_method":   event.get("payment_method", "unknown"),
            }
            with conn.cursor() as cur:
                cur.execute(INSERT_SQL, row)
            conn.commit()
            inserted += 1

            if inserted % 10 == 0:
                log.info("Inserted %d transactions so far.", inserted)

        except Exception as exc:
            log.warning("Failed to insert event %s: %s", event.get("event_id"), exc)
            conn.rollback()


if __name__ == "__main__":
    run()
