from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Customer / RFM
# ---------------------------------------------------------------------------

class RFMScore(BaseModel):
    user_id: int
    email: str
    recency_days: int
    frequency: int
    monetary: float
    r_score: int
    f_score: int
    m_score: int
    customer_segment: str
    recommended_action: str


class ChurnPrediction(BaseModel):
    user_id: int
    email: str
    churn_probability: float
    churn_risk_label: str           # "Low" | "Medium" | "High"
    top_risk_factors: list[str]


class SegmentSummary(BaseModel):
    customer_segment: str
    customer_count: int
    segment_percentage: float
    avg_recency_days: int
    avg_frequency: float
    avg_monetary: float
    total_revenue: float
    recommended_action: str


class AtRiskCustomer(BaseModel):
    user_id: int
    email: str
    churn_risk_score: float
    recency_days: int
    frequency: int
    monetary: float


class TopCustomer(BaseModel):
    user_id: int
    email: str
    customer_segment: Optional[str]
    lifetime_value: float
    total_purchases: int
    recency_days: int
    last_purchase_date: Optional[str]


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class ProductRecommendation(BaseModel):
    product_id: int
    product_name: str
    category: str
    current_price: float
    recommendation_score: float
    reason: str


class SimilarProduct(BaseModel):
    product_id: int
    product_name: str
    category: str
    current_price: float
    confidence_pct: float
    lift: float


class TrendingProduct(BaseModel):
    product_id: int
    product_name: str
    category: str
    current_price: float
    units_sold: int
    revenue: float


# ---------------------------------------------------------------------------
# Dashboard KPIs
# ---------------------------------------------------------------------------

class DailyKPI(BaseModel):
    date: str
    revenue: float
    transactions: int
    active_users: int
    avg_order_value: float
    items_sold: int


class RealtimeKPI(BaseModel):
    period: str
    revenue: float
    transactions: int
    active_users: int
    avg_order_value: float
    sessions: int
    items_sold: int


class TodayVsYesterday(BaseModel):
    today_users: int
    yesterday_users: int
    user_change_pct: float
    today_transactions: int
    yesterday_transactions: int
    transaction_change_pct: float
    today_revenue: float
    yesterday_revenue: float
    revenue_change_pct: float


class HourlyRevenue(BaseModel):
    hour: str
    transactions: int
    revenue: float


class CountryRevenue(BaseModel):
    country: str
    unique_buyers: int
    orders: int
    revenue: float


class CustomerTypeSplit(BaseModel):
    customer_type: str
    customers: int
    transactions: int
    revenue: float
    avg_order_value: float


class PaymentBreakdown(BaseModel):
    payment_method: str
    transaction_count: int
    revenue: float
    pct_of_transactions: float
    pct_of_revenue: float


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

class TopProduct(BaseModel):
    product_id: int
    product_name: str
    category: str
    units_sold: int
    revenue: float


class TopCategory(BaseModel):
    category: str
    unique_buyers: int
    units_sold: int
    revenue: float


class InventoryAlert(BaseModel):
    product_id: int
    product_name: str
    category: str
    current_stock: int
    units_sold_last_24h: int
    days_until_stockout: Optional[float]


class ProductDetail(BaseModel):
    product_id: int
    product_name: str
    category: str
    subcategory: Optional[str]
    brand: Optional[str]
    current_price: float
    stock_quantity: int
    units_sold_24h: int
    revenue_24h: float


# ---------------------------------------------------------------------------
# New analytics schemas
# ---------------------------------------------------------------------------

class RFMScatterPoint(BaseModel):
    user_id: int
    recency_days: int
    frequency: int
    monetary: float
    customer_segment: Optional[str]
    lifetime_value: float


class WeeklyRevenue(BaseModel):
    week_start: str
    revenue: float
    transactions: int
    avg_order_value: float
    active_users: int


class AgeGroupRevenue(BaseModel):
    age_group: str
    customers: int
    transactions: int
    revenue: float
    avg_order_value: float


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

class HealthStatus(BaseModel):
    status: str
    version: str


class DBHealth(BaseModel):
    status: str
    latency_ms: float


class RedisHealth(BaseModel):
    status: str
    latency_ms: float
