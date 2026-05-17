import logging
import os

import requests

log = logging.getLogger(__name__)

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


class APIClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.timeout = 8

    def _get(self, path: str, params: dict = None):
        try:
            resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("API call failed: %s %s — %s", path, params, exc)
            return None

    # ── Health ────────────────────────────────────────────────────────────
    def get_health(self):          return self._get("/health")
    def get_db_health(self):       return self._get("/health/db")
    def get_redis_health(self):    return self._get("/health/redis")

    # ── Dashboard KPIs ────────────────────────────────────────────────────
    def get_realtime_kpi(self):              return self._get("/dashboard/kpi/realtime")
    def get_today_vs_yesterday(self):        return self._get("/dashboard/kpi/today-vs-yesterday")
    def get_daily_kpis(self, days=30):       return self._get("/dashboard/kpi/daily", {"days": days})
    def get_weekly_revenue(self, weeks=12):  return self._get("/dashboard/revenue/weekly", {"weeks": weeks})
    def get_hourly_revenue(self):            return self._get("/dashboard/revenue/hourly")
    def get_revenue_by_country(self):        return self._get("/dashboard/revenue/by-country")
    def get_revenue_by_age_group(self):      return self._get("/dashboard/revenue/by-age-group")
    def get_new_vs_returning(self):          return self._get("/dashboard/customers/new-vs-returning")
    def get_payment_breakdown(self):         return self._get("/dashboard/payments")

    # ── Customers ─────────────────────────────────────────────────────────
    def get_segments(self):                          return self._get("/customers/segments")
    def get_rfm_scatter(self):                       return self._get("/customers/rfm-scatter")
    def get_at_risk(self, page=1, page_size=20):     return self._get("/customers/at-risk", {"page": page, "page_size": page_size})
    def get_top_customers(self, limit=50):           return self._get("/customers/top", {"limit": limit})
    def get_customer_rfm(self, user_id):             return self._get(f"/customers/{user_id}/rfm")
    def get_customer_churn(self, user_id):           return self._get(f"/customers/{user_id}/churn")

    # ── Recommendations ───────────────────────────────────────────────────
    def get_trending(self):                          return self._get("/recommendations/trending")
    def get_user_recommendations(self, user_id):    return self._get(f"/recommendations/user/{user_id}")
    def get_similar_products(self, product_id):     return self._get(f"/recommendations/similar/{product_id}")

    # ── Products ──────────────────────────────────────────────────────────
    def get_top_products(self, limit=10):    return self._get("/products/top", {"limit": limit})
    def get_top_categories(self):            return self._get("/products/top/category")
    def get_inventory_alerts(self):          return self._get("/products/inventory/alerts")
    def get_product(self, product_id):       return self._get(f"/products/{product_id}")


client = APIClient()
