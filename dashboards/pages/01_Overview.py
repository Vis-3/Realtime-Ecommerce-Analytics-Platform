import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from api_client import client
from components.charts import (
    age_group_chart,
    dow_heatmap,
    geo_revenue_chart,
    hourly_revenue_chart,
    new_vs_returning_chart,
    payment_pie_chart,
    revenue_trend_chart,
    weekly_revenue_chart,
)
from components.kpi_tiles import kpi_row, unavailable
from components.style import inject_css, insight_block, page_header, section

st.set_page_config(page_title="Overview | Analytics", layout="wide")
inject_css()
st_autorefresh(interval=60_000, key="overview_refresh")

page_header("Real-time Overview", "Auto-refreshes every 60 seconds")

# ── Right now ─────────────────────────────────────────────────────────────────
section("Last Hour")

with st.spinner(""):
    rt  = client.get_realtime_kpi()
    tvs = client.get_today_vs_yesterday()

if rt:
    kpi_row([
        {"label": "Revenue",         "value": f"{rt['revenue']:,.0f}",        "prefix": "$"},
        {"label": "Orders",          "value": f"{rt['transactions']:,}",      "suffix": " orders"},
        {"label": "Active Users",    "value": f"{rt['active_users']:,}",      "suffix": " users"},
        {"label": "Avg Order Value", "value": f"{rt['avg_order_value']:.2f}", "prefix": "$"},
        {"label": "Items Sold",      "value": f"{rt['items_sold']:,}",        "suffix": " items"},
    ])
else:
    unavailable("Real-time KPIs")

# ── Today vs Yesterday ────────────────────────────────────────────────────────
if tvs:
    section("Today vs Yesterday")
    kpi_row([
        {"label": "Revenue Today",     "value": f"{tvs['today_revenue']:,.0f}",
         "prefix": "$", "delta": tvs.get("revenue_change_pct", 0)},
        {"label": "Orders Today",      "value": f"{tvs['today_transactions']:,}",
         "suffix": " orders", "delta": tvs.get("transaction_change_pct", 0)},
        {"label": "Users Today",       "value": f"{tvs['today_users']:,}",
         "suffix": " users", "delta": tvs.get("user_change_pct", 0)},
        {"label": "Yesterday Revenue", "value": f"{tvs['yesterday_revenue']:,.0f}", "prefix": "$"},
    ])

    rev_delta = tvs.get("revenue_change_pct", 0) or 0
    if rev_delta > 5:
        insight_block(
            f"Revenue is up <b>{rev_delta:+.1f}%</b> vs yesterday. Strong momentum.",
            variant="success",
        )
    elif rev_delta < -5:
        insight_block(
            f"Revenue is down <b>{rev_delta:.1f}%</b> vs yesterday. "
            "Check the hourly breakdown below for any drop-off patterns.",
            variant="warning",
        )
    else:
        insight_block(
            f"Revenue is tracking close to yesterday (<b>{rev_delta:+.1f}%</b>). "
            "Scroll down for the 30-day trend."
        )

st.divider()

# ── Revenue trends ────────────────────────────────────────────────────────────
section("Revenue Trends")

insight_block(
    "Daily revenue with a <b>7-day moving average</b> to smooth day-to-day noise, "
    "alongside average order value on the right axis."
)

col1, col2 = st.columns([3, 2])
with col1:
    daily = client.get_daily_kpis(days=30)
    if daily:
        st.plotly_chart(revenue_trend_chart(daily), use_container_width=True)
    else:
        unavailable("Daily revenue trend")

with col2:
    hourly = client.get_hourly_revenue()
    if hourly:
        st.plotly_chart(hourly_revenue_chart(hourly), use_container_width=True)
    else:
        unavailable("Hourly revenue")

col3, col4 = st.columns(2)
with col3:
    weekly = client.get_weekly_revenue(weeks=12)
    if weekly:
        st.plotly_chart(weekly_revenue_chart(weekly), use_container_width=True)
    else:
        unavailable("Weekly revenue")

with col4:
    daily_long = client.get_daily_kpis(days=90)
    if daily_long:
        st.plotly_chart(dow_heatmap(daily_long), use_container_width=True)
    else:
        unavailable("Day-of-week heatmap")

if daily_long:
    df_dow  = pd.DataFrame(daily_long)
    df_dow["date"] = pd.to_datetime(df_dow["date"])
    df_dow["dow"]  = df_dow["date"].dt.day_name()
    best_day = df_dow.groupby("dow")["revenue"].mean().idxmax()
    insight_block(
        f"<b>{best_day}</b> is historically your highest-revenue day of the week. "
        "Scheduling promotions to launch on this day will maximise initial lift."
    )

st.divider()

# ── Customer breakdown ────────────────────────────────────────────────────────
section("Who Are Today's Customers")

col5, col6 = st.columns(2)
with col5:
    nvr = client.get_new_vs_returning()
    if nvr:
        st.plotly_chart(new_vs_returning_chart(nvr), use_container_width=True)
    else:
        unavailable("New vs returning")

with col6:
    age = client.get_revenue_by_age_group()
    if age:
        st.plotly_chart(age_group_chart(age), use_container_width=True)
    else:
        unavailable("Age group breakdown")

if age:
    top_age = max(age, key=lambda x: x["revenue"])
    insight_block(
        f"The <b>{top_age['age_group']}</b> age group drives the most revenue: "
        f"${top_age['revenue']:,.0f} over the last 30 days across {top_age['customers']:,} customers. "
        "Tailor your highest-impact campaigns to this cohort.",
        variant="success",
    )

col7, col8 = st.columns(2)
with col7:
    payments = client.get_payment_breakdown()
    if payments:
        st.plotly_chart(payment_pie_chart(payments), use_container_width=True)
    else:
        unavailable("Payment breakdown")

with col8:
    if payments:
        top_payment = max(payments, key=lambda p: p["pct_of_revenue"])
        st.markdown("<br>", unsafe_allow_html=True)
        insight_block(
            f"<b>{top_payment['payment_method'].replace('_',' ').title()}</b> accounts for "
            f"<b>{top_payment['pct_of_revenue']:.1f}%</b> of revenue. "
            "Ensuring this payment method is always available is operationally critical."
        )

st.divider()

# ── Geographic breakdown ──────────────────────────────────────────────────────
section("Geographic Revenue (Last 30 Days)")

insight_block(
    "Revenue distribution across markets. Darker shading indicates higher revenue. "
    "Use this to identify untapped markets and prioritise localisation efforts."
)

geo = client.get_revenue_by_country()
if geo:
    st.plotly_chart(geo_revenue_chart(geo), use_container_width=True)
    top3 = sorted(geo, key=lambda x: x["revenue"], reverse=True)[:3]
    top3_str = ", ".join(f"<b>{c['country']}</b> (${c['revenue']:,.0f})" for c in top3)
    insight_block(
        f"Top 3 markets by revenue: {top3_str}. "
        "Consider localised pricing and promotions for your leading market.",
        variant="success",
    )
else:
    unavailable("Geographic data")
