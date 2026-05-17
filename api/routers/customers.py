import logging

import psycopg2.extras
import redis
from fastapi import APIRouter, Depends, HTTPException, Query

from api.config import settings
from api.dependencies import cache_get, cache_set, get_db, get_redis
from api.models.ml_models import get_risk_factors, load_churn_model, predict_churn
from api.models.schemas import (
    AtRiskCustomer,
    ChurnPrediction,
    RFMScore,
    RFMScatterPoint,
    SegmentSummary,
    TopCustomer,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/customers", tags=["customers"])

SEGMENT_ACTIONS = {
    "Champions":          "Reward, Upsell premium products",
    "Loyal Customers":    "Upsell, Ask for reviews",
    "Potential Loyalists":"Offer membership, Recommend products",
    "New Customers":      "Provide onboarding support",
    "Promising":          "Offer loyalty programs",
    "Need Attention":     "Limited time offers",
    "About to Sleep":     "Engagement campaigns",
    "At Risk":            "Win-back campaigns, Special discounts",
    "Cannot Lose Them":   "Personalized reactivation offers",
    "Hibernating":        "Re-engagement emails",
    "Lost":               "Aggressive win-back or ignore",
}


def _score_ntile(value: float, breakpoints: list[float], reverse: bool = False) -> int:
    """Convert a raw value into a 1–5 score using pre-computed quintile edges."""
    for i, edge in enumerate(breakpoints):
        if value <= edge:
            score = i + 1
            return (6 - score) if reverse else score
    return 5 if not reverse else 1


def _get_distribution(conn, r: redis.Redis) -> dict:
    """Return cached percentile breakpoints for recency/frequency/monetary."""
    key = "rfm:distribution"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            percentile_cont(ARRAY[0.2,0.4,0.6,0.8]) WITHIN GROUP (ORDER BY recency_days)  AS r_edges,
            percentile_cont(ARRAY[0.2,0.4,0.6,0.8]) WITHIN GROUP (ORDER BY frequency)     AS f_edges,
            percentile_cont(ARRAY[0.2,0.4,0.6,0.8]) WITHIN GROUP (ORDER BY monetary)      AS m_edges
        FROM user_metrics
        WHERE frequency > 0
    """)
    row = cur.fetchone()
    cur.close()

    dist = {
        "r_edges": list(row["r_edges"]),
        "f_edges": list(row["f_edges"]),
        "m_edges": list(row["m_edges"]),
    }
    cache_set(r, key, dist, settings.cache_ttl_long)
    return dist


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{user_id}/rfm", response_model=RFMScore)
def get_user_rfm(
    user_id: int,
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"rfm:{user_id}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT um.user_id, um.email, um.recency_days, um.frequency,
               um.monetary, um.customer_segment
        FROM user_metrics um
        WHERE um.user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    cur.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    dist = _get_distribution(conn, r)
    r_score = _score_ntile(row["recency_days"], dist["r_edges"], reverse=True)
    f_score = _score_ntile(row["frequency"],    dist["f_edges"])
    m_score = _score_ntile(row["monetary"],     dist["m_edges"])

    segment = row["customer_segment"] or "Other"
    result = {
        "user_id":            row["user_id"],
        "email":              row["email"],
        "recency_days":       int(row["recency_days"]),
        "frequency":          int(row["frequency"]),
        "monetary":           float(row["monetary"]),
        "r_score":            r_score,
        "f_score":            f_score,
        "m_score":            m_score,
        "customer_segment":   segment,
        "recommended_action": SEGMENT_ACTIONS.get(segment, "Monitor"),
    }
    cache_set(r, key, result, settings.cache_ttl_medium)
    return result


@router.get("/{user_id}/churn", response_model=ChurnPrediction)
def get_user_churn(
    user_id: int,
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"churn:{user_id}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT um.user_id, u.email,
               um.recency_days, um.frequency, um.monetary, um.avg_order_value,
               um.first_purchase_date, um.last_purchase_date
        FROM user_metrics um
        JOIN users u ON um.user_id = u.user_id
        WHERE um.user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    cur.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    features = {
        "recency_days":       float(row["recency_days"]),
        "frequency":          float(row["frequency"]),
        "monetary":           float(row["monetary"]),
        "avg_order_value":    float(row["avg_order_value"]),
        "first_purchase_date": row["first_purchase_date"],
        "last_purchase_date":  row["last_purchase_date"],
    }
    model = load_churn_model(settings.model_path)
    prob, label = predict_churn(model, features)
    factors = get_risk_factors(model, features)

    result = {
        "user_id":           row["user_id"],
        "email":             row["email"],
        "churn_probability": prob,
        "churn_risk_label":  label,
        "top_risk_factors":  factors,
    }
    cache_set(r, key, result, settings.cache_ttl_medium)
    return result


@router.get("/segments", response_model=list[SegmentSummary])
def get_segments(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "segments:all"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        WITH rfm_base AS (
            SELECT user_id,
                   recency_days, frequency, monetary
            FROM user_metrics
        ),
        scored AS (
            SELECT user_id,
                NTILE(5) OVER (ORDER BY recency_days DESC) AS r,
                NTILE(5) OVER (ORDER BY frequency)         AS f,
                NTILE(5) OVER (ORDER BY monetary)          AS m,
                recency_days, frequency, monetary
            FROM rfm_base
        ),
        segmented AS (
            SELECT user_id, recency_days, frequency, monetary,
                CASE
                    WHEN r >= 4 AND f >= 4 AND m >= 4 THEN 'Champions'
                    WHEN r >= 3 AND f >= 4             THEN 'Loyal Customers'
                    WHEN r >= 4 AND f >= 3             THEN 'Potential Loyalists'
                    WHEN r >= 4 AND f <= 2             THEN 'New Customers'
                    WHEN r >= 3 AND m >= 4             THEN 'Promising'
                    WHEN r >= 3 AND f >= 3             THEN 'Need Attention'
                    WHEN r <= 2 AND f >= 4 AND m >= 4  THEN 'At Risk'
                    WHEN r <= 1 AND f >= 4 AND m >= 4  THEN 'Cannot Lose Them'
                    WHEN r <= 2 AND f >= 3             THEN 'About to Sleep'
                    WHEN r <= 2 AND f <= 2             THEN 'Hibernating'
                    WHEN r <= 1                        THEN 'Lost'
                    ELSE 'Other'
                END AS customer_segment
            FROM scored
        )
        SELECT
            customer_segment,
            COUNT(*)                                              AS customer_count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2)   AS segment_percentage,
            AVG(recency_days)::integer                           AS avg_recency_days,
            ROUND(AVG(frequency)::numeric, 2)                   AS avg_frequency,
            ROUND(AVG(monetary)::numeric, 2)                    AS avg_monetary,
            ROUND(SUM(monetary)::numeric, 2)                    AS total_revenue
        FROM segmented
        GROUP BY customer_segment
        ORDER BY total_revenue DESC
    """)
    rows = cur.fetchall()
    cur.close()

    result = [
        {**dict(r), "recommended_action": SEGMENT_ACTIONS.get(r["customer_segment"], "Monitor")}
        for r in rows
    ]
    cache_set(r, key, result, settings.cache_ttl_long)
    return result


@router.get("/at-risk", response_model=list[AtRiskCustomer])
def get_at_risk(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"at_risk:p{page}:s{page_size}"
    cached = cache_get(r, key)
    if cached:
        return cached

    offset = (page - 1) * page_size
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT u.user_id, u.email, u.churn_risk_score,
               um.recency_days, um.frequency, um.monetary
        FROM users u
        JOIN user_metrics um ON u.user_id = um.user_id
        WHERE u.churn_risk_score > 0.7
        ORDER BY u.churn_risk_score DESC
        LIMIT %s OFFSET %s
    """, (page_size, offset))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_medium)
    return rows


@router.get("/rfm-scatter", response_model=list[RFMScatterPoint])
def get_rfm_scatter(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """Return a sample of up to 500 users with raw R/F/M for scatter-plot visualisation."""
    key = "rfm:scatter"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT u.user_id,
               um.recency_days,
               um.frequency,
               um.monetary,
               COALESCE(u.customer_segment, 'Other') AS customer_segment,
               COALESCE(u.lifetime_value, 0)         AS lifetime_value
        FROM user_metrics um
        JOIN users u ON um.user_id = u.user_id
        WHERE um.frequency > 0
        ORDER BY RANDOM()
        LIMIT 500
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_long)
    return rows


@router.get("/top", response_model=list[TopCustomer])
def get_top_customers(
    limit: int = Query(50, ge=1, le=200),
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"top_customers:{limit}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT u.user_id, u.email, u.customer_segment,
               u.lifetime_value, u.total_purchases,
               um.recency_days,
               um.last_purchase_date::text AS last_purchase_date
        FROM users u
        JOIN user_metrics um ON u.user_id = um.user_id
        ORDER BY u.lifetime_value DESC
        LIMIT %s
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_long)
    return rows
