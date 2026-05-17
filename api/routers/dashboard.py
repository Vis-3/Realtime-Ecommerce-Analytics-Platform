import logging

import psycopg2.extras
import redis
from fastapi import APIRouter, Depends, Query

from api.config import settings
from api.dependencies import cache_get, cache_set, get_db, get_redis
from api.models.schemas import (
    AgeGroupRevenue,
    CountryRevenue,
    CustomerTypeSplit,
    DailyKPI,
    HourlyRevenue,
    PaymentBreakdown,
    RealtimeKPI,
    TodayVsYesterday,
    WeeklyRevenue,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpi/realtime", response_model=RealtimeKPI)
def get_realtime_kpi(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "kpi:realtime"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(DISTINCT user_id)       AS active_users,
            COUNT(DISTINCT transaction_id) AS transactions,
            COALESCE(SUM(total_amount), 0) AS revenue,
            COALESCE(AVG(total_amount), 0) AS avg_order_value,
            COUNT(DISTINCT session_id)    AS sessions,
            COALESCE(SUM(quantity), 0)    AS items_sold
        FROM transactions
        WHERE transaction_date >= NOW() - INTERVAL '1 hour'
    """)
    row = cur.fetchone()
    cur.close()

    result = {
        "period":          "last_1_hour",
        "active_users":    int(row["active_users"]),
        "transactions":    int(row["transactions"]),
        "revenue":         float(row["revenue"]),
        "avg_order_value": float(row["avg_order_value"]),
        "sessions":        int(row["sessions"]),
        "items_sold":      int(row["items_sold"]),
    }
    cache_set(r, key, result, settings.cache_ttl_short)
    return result


@router.get("/kpi/today-vs-yesterday", response_model=TodayVsYesterday)
def get_today_vs_yesterday(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "kpi:today_vs_yesterday"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        WITH today AS (
            SELECT COUNT(DISTINCT user_id) AS users,
                   COUNT(*)               AS transactions,
                   COALESCE(SUM(total_amount), 0) AS revenue
            FROM transactions WHERE DATE(transaction_date) = CURRENT_DATE
        ),
        yesterday AS (
            SELECT COUNT(DISTINCT user_id) AS users,
                   COUNT(*)               AS transactions,
                   COALESCE(SUM(total_amount), 0) AS revenue
            FROM transactions WHERE DATE(transaction_date) = CURRENT_DATE - 1
        )
        SELECT
            t.users    AS today_users,
            y.users    AS yesterday_users,
            ROUND(100.0 * (t.users - y.users) / NULLIF(y.users, 0), 2) AS user_change_pct,
            t.transactions AS today_transactions,
            y.transactions AS yesterday_transactions,
            ROUND(100.0 * (t.transactions - y.transactions) / NULLIF(y.transactions, 0), 2) AS transaction_change_pct,
            t.revenue  AS today_revenue,
            y.revenue  AS yesterday_revenue,
            ROUND(100.0 * (t.revenue - y.revenue) / NULLIF(y.revenue, 0), 2) AS revenue_change_pct
        FROM today t, yesterday y
    """)
    row = dict(cur.fetchone())
    cur.close()

    # Coerce None (no data) to 0.0
    for k, v in row.items():
        if v is None:
            row[k] = 0

    cache_set(r, key, row, settings.cache_ttl_short)
    return row


@router.get("/kpi/daily", response_model=list[DailyKPI])
def get_daily_kpis(
    days: int = Query(30, ge=1, le=365),
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"kpi:daily:{days}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            metric_date::text      AS date,
            total_revenue          AS revenue,
            total_transactions     AS transactions,
            daily_active_users     AS active_users,
            avg_order_value,
            total_items_sold       AS items_sold
        FROM daily_metrics
        WHERE metric_date >= CURRENT_DATE - %s
        ORDER BY metric_date DESC
    """, (days,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_long)
    return rows


@router.get("/revenue/hourly", response_model=list[HourlyRevenue])
def get_hourly_revenue(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "revenue:hourly"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            DATE_TRUNC('hour', transaction_date)::text AS hour,
            COUNT(*)                                   AS transactions,
            ROUND(SUM(total_amount)::numeric, 2)       AS revenue
        FROM transactions
        WHERE transaction_date >= NOW() - INTERVAL '24 hours'
        GROUP BY DATE_TRUNC('hour', transaction_date)
        ORDER BY hour DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_short)
    return rows


@router.get("/revenue/by-country", response_model=list[CountryRevenue])
def get_revenue_by_country(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "revenue:by_country"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            u.country,
            COUNT(DISTINCT t.user_id)              AS unique_buyers,
            COUNT(*)                               AS orders,
            ROUND(SUM(t.total_amount)::numeric, 2) AS revenue
        FROM transactions t
        JOIN users u ON t.user_id = u.user_id
        WHERE t.transaction_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY u.country
        ORDER BY revenue DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_long)
    return rows


@router.get("/customers/new-vs-returning", response_model=list[CustomerTypeSplit])
def get_new_vs_returning(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "customers:new_vs_returning"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        WITH first_purchase AS (
            SELECT user_id, MIN(transaction_date)::date AS first_date
            FROM transactions GROUP BY user_id
        )
        SELECT
            CASE WHEN fp.first_date = CURRENT_DATE THEN 'New' ELSE 'Returning' END AS customer_type,
            COUNT(DISTINCT t.user_id)              AS customers,
            COUNT(*)                               AS transactions,
            ROUND(SUM(t.total_amount)::numeric, 2) AS revenue,
            ROUND(AVG(t.total_amount)::numeric, 2) AS avg_order_value
        FROM transactions t
        JOIN first_purchase fp ON t.user_id = fp.user_id
        WHERE DATE(t.transaction_date) = CURRENT_DATE
        GROUP BY customer_type
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_short)
    return rows


@router.get("/revenue/weekly", response_model=list[WeeklyRevenue])
def get_weekly_revenue(
    weeks: int = Query(12, ge=4, le=52),
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"revenue:weekly:{weeks}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            DATE_TRUNC('week', metric_date)::text          AS week_start,
            ROUND(SUM(total_revenue)::numeric, 2)          AS revenue,
            SUM(total_transactions)                        AS transactions,
            ROUND(AVG(avg_order_value)::numeric, 2)        AS avg_order_value,
            SUM(daily_active_users)                        AS active_users
        FROM daily_metrics
        WHERE metric_date >= CURRENT_DATE - (%s * 7)
        GROUP BY DATE_TRUNC('week', metric_date)
        ORDER BY week_start DESC
        LIMIT %s
    """, (weeks, weeks))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_long)
    return rows


@router.get("/revenue/by-age-group", response_model=list[AgeGroupRevenue])
def get_revenue_by_age_group(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "revenue:by_age_group"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COALESCE(u.age_group, 'Unknown')               AS age_group,
            COUNT(DISTINCT t.user_id)                      AS customers,
            COUNT(*)                                       AS transactions,
            ROUND(SUM(t.total_amount)::numeric, 2)         AS revenue,
            ROUND(AVG(t.total_amount)::numeric, 2)         AS avg_order_value
        FROM transactions t
        JOIN users u ON t.user_id = u.user_id
        WHERE t.transaction_date >= CURRENT_DATE - 30
        GROUP BY u.age_group
        ORDER BY revenue DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_long)
    return rows


@router.get("/payments", response_model=list[PaymentBreakdown])
def get_payment_breakdown(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "payments:breakdown"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            payment_method,
            COUNT(*)                                                               AS transaction_count,
            ROUND(SUM(total_amount)::numeric, 2)                                  AS revenue,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2)                     AS pct_of_transactions,
            ROUND(100.0 * SUM(total_amount) / SUM(SUM(total_amount)) OVER(), 2)   AS pct_of_revenue
        FROM transactions
        WHERE transaction_date >= NOW() - INTERVAL '24 hours'
        GROUP BY payment_method
        ORDER BY revenue DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_medium)
    return rows
