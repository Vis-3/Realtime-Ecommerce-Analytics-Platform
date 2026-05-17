"""
Persona-aware E-Commerce Event Generator.

Why personas matter here:
  In the original generator every user had identical purchase probability
  (effectively ~5.6% per session). Real platforms see dramatically different
  behaviour: a Champion visits frequently and converts often; a Hibernating
  user rarely shows up and almost never buys. Uniform simulation produces
  flat feature distributions that give the ML model nothing to learn from.

  Each user is now weighted for session selection and carries persona-specific
  conversion probabilities and price distributions, so the Kafka stream
  reflects the same behavioural structure that was seeded into Postgres.
"""

import json
import os
import random
import time
from datetime import datetime

import numpy as np
from kafka import KafkaProducer
import psycopg2

# ---------------------------------------------------------------------------
# Persona configuration
# ---------------------------------------------------------------------------

# Probability that a given persona appears in any given session.
# Champions and Loyal customers are more likely to be browsing at any moment.
SESSION_WEIGHTS = {
    "Champion":    5.0,
    "Loyal":       3.0,
    "New":         1.0,
    "Hibernating": 0.3,
    "AtRisk":      0.1,
}

# Probability of completing a purchase once the user has added to cart.
# Overall session purchase rate = 0.7 (click) × 0.4 (cart) × this value.
CART_TO_PURCHASE = {
    "Champion":    0.90,   # ~25% of sessions end in purchase
    "Loyal":       0.60,   # ~17%
    "New":         0.30,   # ~8%
    "Hibernating": 0.15,   # ~4%
    "AtRisk":      0.07,   # ~2%
}

# Log-normal price parameters per persona (μ and σ in log-space).
# Champions spend more per order; Hibernating users buy cheaper items.
PRICE_PARAMS = {
    "Champion":    (3.6, 0.7),   # median ~$37
    "Loyal":       (3.3, 0.8),   # median ~$27
    "New":         (3.1, 0.9),   # median ~$22
    "Hibernating": (2.9, 0.9),   # median ~$18
    "AtRisk":      (3.1, 0.8),   # median ~$22
}

PAYMENT_METHODS = ["credit_card", "paypal", "debit_card", "apple_pay"]
PAGES           = ["/home", "/products", "/product-detail", "/cart",
                   "/checkout", "/account", "/search", "/category"]
DEVICES         = ["mobile", "desktop", "tablet"]
BROWSERS        = ["Chrome", "Firefox", "Safari", "Edge"]
REFERRERS       = ["google", "facebook", "direct", "email"]
SOURCES         = ["search", "recommendation", "category", "homepage"]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class EventGenerator:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=[os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        self.conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            database=os.getenv("POSTGRES_DB", "ecommerce"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        )

        self.users       = self._load_users()
        self.product_ids = self._load_product_ids()
        self._weights    = [SESSION_WEIGHTS.get(u[1], 1.0) for u in self.users]

        print(f"Loaded {len(self.users):,} users and {len(self.product_ids):,} products")
        self._print_persona_summary()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_users(self) -> list[tuple]:
        """Return list of (user_id, persona) for all users."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT user_id, persona FROM users")
            return cur.fetchall()

    def _load_product_ids(self) -> list[int]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT product_id FROM products")
            return [r[0] for r in cur.fetchall()]

    def _print_persona_summary(self) -> None:
        from collections import Counter
        counts = Counter(u[1] for u in self.users)
        print("Persona distribution:")
        for persona, n in sorted(counts.items()):
            print(f"  {persona:<14} {n:>6,} users  (session weight {SESSION_WEIGHTS.get(persona, 1.0):.1f}x)")

    # ------------------------------------------------------------------
    # User selection
    # ------------------------------------------------------------------

    def _pick_user(self) -> tuple[int, str]:
        """Weighted random selection — Champions appear ~50x more than AtRisk."""
        (user_id, persona), = random.choices(self.users, weights=self._weights, k=1)
        return user_id, persona

    # ------------------------------------------------------------------
    # Event builders
    # ------------------------------------------------------------------

    @staticmethod
    def _event_id() -> str:
        return f"evt_{int(time.time() * 1_000_000)}_{random.randint(1000, 9999)}"

    @staticmethod
    def _session_id() -> str:
        return f"session_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

    def _page_view(self, user_id: int, session_id: str) -> dict:
        return {
            "event_id":    self._event_id(),
            "event_type":  "page_view",
            "user_id":     user_id,
            "session_id":  session_id,
            "timestamp":   datetime.now().isoformat(),
            "page":        random.choice(PAGES),
            "device_type": random.choice(DEVICES),
            "browser":     random.choice(BROWSERS),
            "referrer":    random.choice(REFERRERS),
        }

    def _product_click(self, user_id: int, session_id: str) -> dict:
        return {
            "event_id":   self._event_id(),
            "event_type": "product_click",
            "user_id":    user_id,
            "session_id": session_id,
            "product_id": random.choice(self.product_ids),
            "timestamp":  datetime.now().isoformat(),
            "position":   random.randint(1, 20),
            "source":     random.choice(SOURCES),
        }

    def _add_to_cart(self, user_id: int, session_id: str) -> dict:
        return {
            "event_id":   self._event_id(),
            "event_type": "add_to_cart",
            "user_id":    user_id,
            "session_id": session_id,
            "product_id": random.choice(self.product_ids),
            "quantity":   random.randint(1, 3),
            "timestamp":  datetime.now().isoformat(),
        }

    def _purchase(self, user_id: int, session_id: str, persona: str) -> dict:
        mu, sigma  = PRICE_PARAMS.get(persona, PRICE_PARAMS["New"])
        unit_price = float(np.clip(np.random.lognormal(mu, sigma), 5.0, 500.0))
        unit_price = round(unit_price, 2)
        quantity   = random.randint(1, 4)
        return {
            "event_id":       self._event_id(),
            "event_type":     "purchase",
            "user_id":        user_id,
            "session_id":     session_id,
            "product_id":     random.choice(self.product_ids),
            "quantity":       quantity,
            "unit_price":     unit_price,
            "total_amount":   round(quantity * unit_price, 2),
            "payment_method": random.choice(PAYMENT_METHODS),
            "persona":        persona,
            "timestamp":      datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Session simulation
    # ------------------------------------------------------------------

    def simulate_session(self) -> None:
        """
        Simulate one user session with persona-driven conversion rates.

        Session funnel (probabilities are the same for all personas at
        the browse stage; divergence happens at the cart→purchase step):
          100%  page view
           70%  product click
           40%  add to cart   (after click)
          CART_TO_PURCHASE[persona]  purchase  (after cart)
        """
        user_id, persona = self._pick_user()
        session_id = self._session_id()

        self.producer.send("user_events", self._page_view(user_id, session_id))

        if random.random() < 0.70:
            time.sleep(random.uniform(0.05, 0.3))
            self.producer.send("user_events", self._product_click(user_id, session_id))

            if random.random() < 0.40:
                time.sleep(random.uniform(0.1, 0.5))
                self.producer.send("user_events", self._add_to_cart(user_id, session_id))

                purchase_prob = CART_TO_PURCHASE.get(persona, 0.20)
                if random.random() < purchase_prob:
                    time.sleep(random.uniform(0.2, 1.0))
                    self.producer.send("transactions", self._purchase(user_id, session_id, persona))

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, sessions_per_second: int = 10, duration_seconds: int | None = None) -> None:
        print(f"\nStarting event generator")
        print(f"  Rate     : ~{sessions_per_second} sessions/sec")
        print(f"  Duration : {'infinite' if duration_seconds is None else f'{duration_seconds}s'}")
        print(f"  Topics   : user_events, transactions")
        print("Press Ctrl+C to stop\n")

        start      = time.time()
        n_sessions = 0

        try:
            while True:
                if duration_seconds and (time.time() - start) > duration_seconds:
                    break

                self.simulate_session()
                n_sessions += 1

                if n_sessions % 200 == 0:
                    elapsed = time.time() - start
                    rate    = n_sessions / elapsed if elapsed else 0
                    print(f"[{elapsed:6.0f}s] sessions={n_sessions:,}  rate={rate:.1f}/s")

                time.sleep(1.0 / sessions_per_second)

        except KeyboardInterrupt:
            print("\nStopping...")

        finally:
            elapsed = time.time() - start
            print(f"\nFinal: {n_sessions:,} sessions in {elapsed:.1f}s "
                  f"({n_sessions / elapsed:.1f}/s)")
            self.producer.flush()
            self.producer.close()
            self.conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Persona-aware e-commerce event generator")
    parser.add_argument("--rate",     type=int, default=10,   help="Sessions per second (default: 10)")
    parser.add_argument("--duration", type=int, default=None, help="Duration in seconds (default: infinite)")
    args = parser.parse_args()

    generator = EventGenerator()
    generator.run(sessions_per_second=args.rate, duration_seconds=args.duration)
