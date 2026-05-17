"""
E-Commerce Analytics Platform — Home / Landing Page
"""

import time

import streamlit as st

from api_client import client
from components.style import health_dot, inject_css

st.set_page_config(
    page_title="E-Commerce Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 16px 4px 12px 4px;">
        <div style="font-size:15px; font-weight:800; color:#e2e8f0; letter-spacing:-0.01em">
            E-Commerce Analytics
        </div>
        <div style="font-size:11px; color:#475569; margin-top:3px; letter-spacing:0.04em">
            REAL-TIME PLATFORM v1.0
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown(
        '<div style="font-size:10px; font-weight:700; letter-spacing:0.1em; color:#475569; '
        'text-transform:uppercase; margin-bottom:10px">Service Health</div>',
        unsafe_allow_html=True,
    )
    api   = client.get_health()
    db    = client.get_db_health()
    redis = client.get_redis_health()

    api_status   = api.get("status",     "error") if api   else "error"
    db_status    = db.get("status",      "error") if db    else "error"
    redis_status = redis.get("status",   "error") if redis else "error"
    db_ms        = db.get("latency_ms",  "--")    if db    else "--"
    redis_ms     = redis.get("latency_ms","--")   if redis else "--"

    st.markdown(f'{health_dot(api_status)} &nbsp; **API** &emsp; `{api_status}`',         unsafe_allow_html=True)
    st.markdown(f'{health_dot(db_status)} &nbsp; **PostgreSQL** &emsp; `{db_ms} ms`',     unsafe_allow_html=True)
    st.markdown(f'{health_dot(redis_status)} &nbsp; **Redis** &emsp; `{redis_ms} ms`',    unsafe_allow_html=True)

    st.divider()
    st.markdown(
        '<div style="font-size:10px; font-weight:700; letter-spacing:0.1em; color:#475569; '
        'text-transform:uppercase; margin-bottom:10px">Navigation</div>',
        unsafe_allow_html=True,
    )
    st.page_link("streamlit_app.py",           label="Home")
    st.page_link("pages/01_Overview.py",        label="Real-time Overview")
    st.page_link("pages/02_Customers.py",       label="Customer Analytics")
    st.page_link("pages/03_Recommendations.py", label="Recommendations")
    st.page_link("pages/04_Products.py",        label="Product Analytics")
    st.page_link("pages/05_Explorer.py",        label="Explorer")

    st.divider()
    st.markdown(
        f'<div style="font-size:10px; color:#334155; text-align:left">'
        f'Last checked {time.strftime("%H:%M:%S")}</div>',
        unsafe_allow_html=True,
    )

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding: 52px 0 36px 0;">
    <div style="
        font-size: 38px;
        font-weight: 800;
        background: linear-gradient(135deg, #7c3aed, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.02em;
        line-height: 1.1;
        margin-bottom: 14px;
    ">E-Commerce Analytics Platform</div>
    <div style="font-size: 15px; color: #475569; max-width: 560px; line-height: 1.65;">
        An end-to-end data engineering and machine learning pipeline built on
        Kafka, PostgreSQL, Airflow, FastAPI, and Redis. From raw events to
        real-time customer intelligence in a single platform.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Pipeline architecture ─────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:10px; font-weight:700; letter-spacing:0.12em; color:#475569; '
    'text-transform:uppercase; margin-bottom:14px">Data Pipeline</div>',
    unsafe_allow_html=True,
)

st.markdown("""
<div class="pipeline-row">
    <div class="pipeline-node">
        <div class="pipeline-step">01</div>
        <div class="pipeline-node-label">Kafka</div>
        <div class="pipeline-node-sub">Event streaming<br>4 partitions</div>
    </div>
    <div class="pipeline-arrow">&#8594;</div>
    <div class="pipeline-node">
        <div class="pipeline-step">02</div>
        <div class="pipeline-node-label">PostgreSQL 15</div>
        <div class="pipeline-node-sub">Star schema<br>Monthly partitions</div>
    </div>
    <div class="pipeline-arrow">&#8594;</div>
    <div class="pipeline-node">
        <div class="pipeline-step">03</div>
        <div class="pipeline-node-label">Airflow</div>
        <div class="pipeline-node-sub">4 DAGs<br>RFM + Churn + ML</div>
    </div>
    <div class="pipeline-arrow">&#8594;</div>
    <div class="pipeline-node">
        <div class="pipeline-step">04</div>
        <div class="pipeline-node-label">FastAPI + Redis</div>
        <div class="pipeline-node-sub">22 endpoints<br>Tiered caching</div>
    </div>
    <div class="pipeline-arrow">&#8594;</div>
    <div class="pipeline-node">
        <div class="pipeline-step">05</div>
        <div class="pipeline-node-label">Streamlit</div>
        <div class="pipeline-node-sub">Live dashboard<br>60s auto-refresh</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Feature cards ─────────────────────────────────────────────────────────────
cards = [
    ("OVERVIEW",        "#7c3aed", "Real-time Overview",
     "Live KPIs, revenue trends with 7-day moving average, day-of-week heatmap, and geographic breakdown.",
     "pages/01_Overview.py"),
    ("CUSTOMERS",       "#06b6d4", "Customer Analytics",
     "RFM scatter plot, 11-segment analysis, churn risk leaderboard, and lifetime value distribution.",
     "pages/02_Customers.py"),
    ("RECOMMENDATIONS", "#a855f7", "Recommendations",
     "Collaborative filtering, personalised product picks, and item-based similarity with lift scores.",
     "pages/03_Recommendations.py"),
    ("PRODUCTS",        "#f59e0b", "Product Analytics",
     "Category revenue treemap, top product rankings, and real-time inventory stockout alerts.",
     "pages/04_Products.py"),
    ("EXPLORER",        "#22c55e", "Explorer",
     "Drill into any customer (RFM profile, churn gauge, recommendations) or product by ID.",
     "pages/05_Explorer.py"),
]

c1, c2, c3, c4, c5 = st.columns(5)
for col, (tag, color, title, desc, page) in zip([c1, c2, c3, c4, c5], cards):
    with col:
        st.markdown(f"""
        <div class="feature-card">
            <div class="feature-tag" style="background:{color}18; color:{color}">{tag}</div>
            <div class="feature-title">{title}</div>
            <div class="feature-desc">{desc}</div>
        </div>
        """, unsafe_allow_html=True)
        st.page_link(page, label="Open")

st.markdown("<br>", unsafe_allow_html=True)
st.divider()

# ── Stats row ─────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:10px; font-weight:700; letter-spacing:0.12em; color:#475569; '
    'text-transform:uppercase; text-align:center; margin-bottom:18px">Dataset at a Glance</div>',
    unsafe_allow_html=True,
)

cols = st.columns(7)
stats = [
    ("100K+", "Transactions"),
    ("10K",   "Customers"),
    ("1K",    "Products"),
    ("11",    "RFM Segments"),
    ("22+",   "API Endpoints"),
    ("4",     "Airflow DAGs"),
    ("2",     "Kafka Topics"),
]
for col, (val, label) in zip(cols, stats):
    col.markdown(
        f'<div style="text-align:center">'
        f'<div style="font-size:22px; font-weight:800; color:#7c3aed; letter-spacing:-0.02em">{val}</div>'
        f'<div style="font-size:10px; color:#475569; text-transform:uppercase; '
        f'letter-spacing:0.08em; margin-top:5px">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
