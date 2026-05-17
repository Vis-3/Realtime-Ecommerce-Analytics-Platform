import logging

import psycopg2.extras
import redis
from fastapi import APIRouter, Depends, HTTPException

from api.config import settings
from api.dependencies import cache_get, cache_set, get_db, get_redis
from api.models.schemas import ProductRecommendation, SimilarProduct, TrendingProduct

log = logging.getLogger(__name__)
router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/user/{user_id}", response_model=list[ProductRecommendation])
def get_user_recommendations(
    user_id: int,
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"recs:user:{user_id}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Verify user exists
    cur.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    cur.execute("""
        WITH target_products AS (
            SELECT DISTINCT product_id
            FROM transactions
            WHERE user_id = %(uid)s
        ),
        similar_buyers AS (
            SELECT DISTINCT t.user_id
            FROM transactions t
            WHERE t.product_id IN (SELECT product_id FROM target_products)
              AND t.user_id <> %(uid)s
        ),
        candidate_products AS (
            SELECT t.product_id,
                   COUNT(DISTINCT t.user_id) AS buyer_overlap
            FROM transactions t
            JOIN similar_buyers sb ON t.user_id = sb.user_id
            WHERE t.product_id NOT IN (SELECT product_id FROM target_products)
            GROUP BY t.product_id
        )
        SELECT p.product_id, p.product_name, p.category,
               p.current_price, cp.buyer_overlap
        FROM candidate_products cp
        JOIN products p ON cp.product_id = p.product_id
        ORDER BY cp.buyer_overlap DESC
        LIMIT 10
    """, {"uid": user_id})
    rows = cur.fetchall()
    cur.close()

    result = [
        {
            "product_id":           row["product_id"],
            "product_name":         row["product_name"],
            "category":             row["category"],
            "current_price":        float(row["current_price"]),
            "recommendation_score": float(row["buyer_overlap"]),
            "reason":               "customers like you also bought",
        }
        for row in rows
    ]
    cache_set(r, key, result, settings.cache_ttl_medium)
    return result


@router.get("/similar/{product_id}", response_model=list[SimilarProduct])
def get_similar_products(
    product_id: int,
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"recs:similar:{product_id}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT 1 FROM products WHERE product_id = %s", (product_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    cur.execute("""
        WITH product_pairs AS (
            SELECT
                t2.product_id AS paired_product_id,
                COUNT(DISTINCT t1.user_id) AS co_purchase_count
            FROM transactions t1
            JOIN transactions t2
                ON t1.user_id = t2.user_id
               AND t2.product_id <> t1.product_id
            WHERE t1.product_id = %(pid)s
            GROUP BY t2.product_id
            HAVING COUNT(DISTINCT t1.user_id) >= 2
        ),
        product_popularity AS (
            SELECT product_id, COUNT(DISTINCT user_id) AS user_count
            FROM transactions
            GROUP BY product_id
        ),
        total_users AS (
            SELECT COUNT(DISTINCT user_id) AS n FROM users
        )
        SELECT
            p.product_id, p.product_name, p.category, p.current_price,
            pp.co_purchase_count,
            popa.user_count AS base_buyers,
            popb.user_count AS paired_buyers,
            ROUND(
                (pp.co_purchase_count::float / NULLIF(popa.user_count, 0))
                / (popb.user_count::float / NULLIF(tu.n, 0)),
                2
            ) AS lift,
            ROUND(
                100.0 * pp.co_purchase_count / NULLIF(popa.user_count, 0),
                2
            ) AS confidence_pct
        FROM product_pairs pp
        JOIN products p          ON pp.paired_product_id = p.product_id
        JOIN product_popularity popa ON popa.product_id = %(pid)s
        JOIN product_popularity popb ON popb.product_id = pp.paired_product_id
        CROSS JOIN total_users tu
        ORDER BY lift DESC, pp.co_purchase_count DESC
        LIMIT 10
    """, {"pid": product_id})
    rows = cur.fetchall()
    cur.close()

    result = [
        {
            "product_id":     row["product_id"],
            "product_name":   row["product_name"],
            "category":       row["category"],
            "current_price":  float(row["current_price"]),
            "confidence_pct": float(row["confidence_pct"] or 0),
            "lift":           float(row["lift"] or 0),
        }
        for row in rows
    ]
    cache_set(r, key, result, settings.cache_ttl_long)
    return result


@router.get("/trending", response_model=list[TrendingProduct])
def get_trending(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "recs:trending"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT p.product_id, p.product_name, p.category, p.current_price,
               SUM(t.quantity)      AS units_sold,
               SUM(t.total_amount)  AS revenue
        FROM transactions t
        JOIN products p ON t.product_id = p.product_id
        WHERE t.transaction_date >= NOW() - INTERVAL '24 hours'
        GROUP BY p.product_id, p.product_name, p.category, p.current_price
        ORDER BY revenue DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    cur.close()

    result = [
        {
            "product_id":    row["product_id"],
            "product_name":  row["product_name"],
            "category":      row["category"],
            "current_price": float(row["current_price"]),
            "units_sold":    int(row["units_sold"] or 0),
            "revenue":       float(row["revenue"] or 0),
        }
        for row in rows
    ]
    cache_set(r, key, result, settings.cache_ttl_short)
    return result
