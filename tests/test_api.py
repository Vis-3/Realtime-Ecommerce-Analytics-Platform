"""
FastAPI endpoint tests.
Run from ecommerce-analytics/:
    pytest tests/ -v

Requires a running API (docker compose up api) or set API_BASE_URL env var.
Uses httpx for async-compatible requests against the live service.
"""

import os

import pytest
import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT  = 10


def get(path: str, params: dict = None):
    return requests.get(f"{BASE_URL}{path}", params=params, timeout=TIMEOUT)


# ── Health checks ──────────────────────────────────────────────────────────────

def test_health_returns_ok():
    r = get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_db_health_returns_latency():
    r = get("/health/db")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["latency_ms"], (int, float))
    assert body["latency_ms"] < 1000


def test_redis_health_returns_latency():
    r = get("/health/redis")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["latency_ms"], (int, float))


# ── Dashboard KPIs ─────────────────────────────────────────────────────────────

def test_realtime_kpi_shape():
    r = get("/dashboard/kpi/realtime")
    assert r.status_code == 200
    body = r.json()
    for field in ("revenue", "transactions", "active_users", "avg_order_value", "items_sold"):
        assert field in body, f"Missing field: {field}"
    assert body["revenue"] >= 0
    assert body["transactions"] >= 0


def test_daily_kpis_returns_list():
    r = get("/dashboard/kpi/daily", {"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    if body:
        row = body[0]
        assert "date" in row
        assert "revenue" in row
        assert row["revenue"] >= 0


def test_weekly_revenue_returns_list():
    r = get("/dashboard/revenue/weekly", {"weeks": 4})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    if body:
        assert "week_start" in body[0]
        assert "revenue"    in body[0]


def test_revenue_by_country_returns_list():
    r = get("/dashboard/revenue/by-country")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_age_group_revenue_returns_list():
    r = get("/dashboard/revenue/by-age-group")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    if body:
        assert "age_group" in body[0]
        assert "revenue"   in body[0]


# ── Customer endpoints ─────────────────────────────────────────────────────────

def test_segments_returns_11_segments():
    r = get("/customers/segments")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0
    seg_names = {s["customer_segment"] for s in body}
    assert len(seg_names) > 3, "Expected multiple distinct segments"


def test_rfm_scatter_returns_sample():
    r = get("/customers/rfm-scatter")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0
    row = body[0]
    for field in ("user_id", "recency_days", "frequency", "monetary", "customer_segment"):
        assert field in row, f"Missing field: {field}"


def test_customer_rfm_valid_user():
    r = get("/customers/1/rfm")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == 1
    assert 1 <= body["r_score"] <= 5
    assert 1 <= body["f_score"] <= 5
    assert 1 <= body["m_score"] <= 5


def test_customer_rfm_invalid_user():
    r = get("/customers/999999/rfm")
    assert r.status_code == 404


def test_customer_churn_valid_user():
    r = get("/customers/1/churn")
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["churn_probability"] <= 1.0
    assert body["churn_risk_label"] in ("Low", "Medium", "High")
    assert isinstance(body["top_risk_factors"], list)


def test_at_risk_customers_paginated():
    r = get("/customers/at-risk", {"page": 1, "page_size": 10})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) <= 10


# ── Products & recommendations ─────────────────────────────────────────────────

def test_top_products_returns_list():
    r = get("/products/top", {"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) <= 5


def test_trending_products_returns_list():
    r = get("/recommendations/trending")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_product_not_found():
    r = get("/products/999999")
    assert r.status_code == 404
