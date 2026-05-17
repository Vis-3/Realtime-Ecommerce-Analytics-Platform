import logging

import psycopg2.extras
import redis
from fastapi import APIRouter, Depends, HTTPException, Query

from api.config import settings
from api.dependencies import cache_get, cache_set, get_db, get_redis
from api.models.schemas import InventoryAlert, ProductDetail, TopCategory, TopProduct

log = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


@router.get("/top", response_model=list[TopProduct])
def get_top_products(
    limit: int = Query(10, ge=1, le=50),
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"products:top:{limit}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT p.product_id, p.product_name, p.category,
               SUM(t.quantity)                         AS units_sold,
               ROUND(SUM(t.total_amount)::numeric, 2)  AS revenue
        FROM transactions t
        JOIN products p ON t.product_id = p.product_id
        WHERE t.transaction_date >= CURRENT_DATE
        GROUP BY p.product_id, p.product_name, p.category
        ORDER BY revenue DESC
        LIMIT %s
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_short)
    return rows


@router.get("/top/category", response_model=list[TopCategory])
def get_top_categories(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "products:top_category"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            p.category,
            COUNT(DISTINCT t.user_id)              AS unique_buyers,
            SUM(t.quantity)                        AS units_sold,
            ROUND(SUM(t.total_amount)::numeric, 2) AS revenue
        FROM transactions t
        JOIN products p ON t.product_id = p.product_id
        WHERE t.transaction_date >= CURRENT_DATE
        GROUP BY p.category
        ORDER BY revenue DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_short)
    return rows


@router.get("/inventory/alerts", response_model=list[InventoryAlert])
def get_inventory_alerts(
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = "inventory:alerts"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            p.product_id, p.product_name, p.category,
            p.stock_quantity                   AS current_stock,
            COALESCE(SUM(t.quantity), 0)::int  AS units_sold_last_24h,
            CASE
                WHEN SUM(t.quantity) > 0
                THEN ROUND(p.stock_quantity::numeric / SUM(t.quantity), 1)
                ELSE NULL
            END AS days_until_stockout
        FROM products p
        LEFT JOIN transactions t
            ON p.product_id = t.product_id
           AND t.transaction_date >= NOW() - INTERVAL '24 hours'
        GROUP BY p.product_id, p.product_name, p.category, p.stock_quantity
        HAVING p.stock_quantity < 50
            OR (p.stock_quantity::numeric / NULLIF(SUM(t.quantity), 0)) < 7
        ORDER BY days_until_stockout NULLS LAST
        LIMIT 20
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    cache_set(r, key, rows, settings.cache_ttl_medium)
    return rows


@router.get("/{product_id}", response_model=ProductDetail)
def get_product(
    product_id: int,
    conn=Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = f"product:{product_id}"
    cached = cache_get(r, key)
    if cached:
        return cached

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            p.product_id, p.product_name, p.category, p.subcategory,
            p.brand, p.current_price, p.stock_quantity,
            COALESCE(SUM(t.quantity), 0)::int              AS units_sold_24h,
            COALESCE(SUM(t.total_amount), 0)               AS revenue_24h
        FROM products p
        LEFT JOIN transactions t
            ON p.product_id = t.product_id
           AND t.transaction_date >= NOW() - INTERVAL '24 hours'
        WHERE p.product_id = %s
        GROUP BY p.product_id, p.product_name, p.category,
                 p.subcategory, p.brand, p.current_price, p.stock_quantity
    """, (product_id,))
    row = cur.fetchone()
    cur.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    result = dict(row)
    cache_set(r, key, result, settings.cache_ttl_medium)
    return result
