import numpy as np
import pandas as pd
import streamlit as st

from api_client import client
from components.charts import (
    churn_histogram,
    ltv_histogram,
    rfm_scatter_chart,
    rfm_segment_chart,
    segment_radar_chart,
)
from components.kpi_tiles import unavailable
from components.style import (
    inject_css,
    insight_block,
    page_header,
    section,
    seg_badge,
)

st.set_page_config(page_title="Customers | Analytics", layout="wide")
inject_css()

page_header("Customer Analytics", "RFM segmentation, churn prediction, and lifetime value")

insight_block(
    "Every customer is scored on three dimensions: <b>Recency</b> (how recently they purchased), "
    "<b>Frequency</b> (how often), and <b>Monetary value</b> (how much they spend). "
    "This RFM framework groups 10,000 customers into 11 actionable segments."
)

# ── RFM Scatter ───────────────────────────────────────────────────────────────
section("RFM Customer Map")

scatter_data = client.get_rfm_scatter()
if scatter_data:
    st.plotly_chart(rfm_scatter_chart(scatter_data), use_container_width=True)
    n          = len(scatter_data)
    champions  = [d for d in scatter_data if d.get("customer_segment") == "Champions"]
    at_risk    = [d for d in scatter_data if d.get("customer_segment") == "At Risk"]
    insight_block(
        f"Each bubble represents one customer (sample of {n:,}). "
        f"<b>Champions</b> cluster top-left (frequent, recent buyers): {len(champions)} in this sample. "
        f"<b>At Risk</b> customers drift right as recency grows: {len(at_risk)} flagged. "
        "Bubble size reflects total spend."
    )
else:
    unavailable("RFM scatter data")

st.divider()

# ── Segment breakdown ─────────────────────────────────────────────────────────
section("Segment Distribution and Revenue Contribution")

segments = client.get_segments()

if segments:
    col1, col2 = st.columns([2, 3])

    with col1:
        st.plotly_chart(rfm_segment_chart(segments), use_container_width=True)

    with col2:
        df = pd.DataFrame(segments)
        df = df.rename(columns={
            "customer_segment":   "Segment",
            "customer_count":     "Users",
            "segment_percentage": "% Share",
            "avg_recency_days":   "Avg Recency",
            "avg_frequency":      "Avg Orders",
            "avg_monetary":       "Avg Spend",
            "total_revenue":      "Total Revenue",
            "recommended_action": "Recommended Action",
        })
        df["Total Revenue"] = df["Total Revenue"].apply(lambda x: f"${x:,.0f}")
        df["Avg Spend"]     = df["Avg Spend"].apply(lambda x: f"${x:,.2f}")
        df["% Share"]       = df["% Share"].apply(lambda x: f"{x:.1f}%")
        df["Avg Recency"]   = df["Avg Recency"].apply(lambda x: f"{x}d")
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    section("Segment Profile Comparison")
    insight_block(
        "Radar chart comparing the top 6 segments on normalised R, F, and M dimensions. "
        "A larger filled area means strength across all three metrics. "
        "Champions fill the spider; Lost customers barely register."
    )
    st.plotly_chart(segment_radar_chart(segments), use_container_width=True)

    top_seg = max(segments, key=lambda s: s["total_revenue"])
    insight_block(
        f"<b>{top_seg['customer_segment']}</b> is your highest-revenue segment: "
        f"${top_seg['total_revenue']:,.0f} total across {top_seg['customer_count']:,} customers. "
        f"Recommended action: <i>{top_seg['recommended_action']}</i>.",
        variant="success",
    )
else:
    unavailable("Segment data")

st.divider()

# ── Churn risk ────────────────────────────────────────────────────────────────
section("Churn Risk Analysis")

insight_block(
    "Churn probability is computed per-customer using a trained classifier on recency, frequency, "
    "monetary value, and average order value. Users above <b>0.70</b> are flagged as high-risk.",
    variant="warning",
)

if "churn_page" not in st.session_state:
    st.session_state.churn_page = 1

at_risk = client.get_at_risk(page=st.session_state.churn_page, page_size=20)

col_hist, col_table = st.columns([1, 2])

with col_hist:
    all_risk = client.get_at_risk(page=1, page_size=100) or []
    if all_risk:
        st.plotly_chart(churn_histogram(all_risk), use_container_width=True)
    n_at_risk = len(all_risk)
    st.markdown(
        f'<div style="text-align:center; color:#ef4444; font-size:30px; font-weight:800; '
        f'letter-spacing:-0.02em">{n_at_risk}</div>'
        f'<div style="text-align:center; color:#64748b; font-size:11px; text-transform:uppercase; '
        f'letter-spacing:0.08em; margin-top:4px">users at high churn risk</div>',
        unsafe_allow_html=True,
    )

with col_table:
    if at_risk:
        df_risk = pd.DataFrame(at_risk)
        df_risk["churn_risk_score"] = df_risk["churn_risk_score"].apply(lambda x: f"{x:.2f}")
        df_risk["monetary"]         = df_risk["monetary"].apply(lambda x: f"${x:,.2f}")
        df_risk = df_risk.rename(columns={
            "user_id":          "ID",
            "email":            "Email",
            "churn_risk_score": "Risk Score",
            "recency_days":     "Days Since Purchase",
            "frequency":        "Orders",
            "monetary":         "Total Spend",
        })
        st.dataframe(df_risk, use_container_width=True, hide_index=True)

        pcol1, pcol2, pcol3 = st.columns([1, 2, 1])
        with pcol1:
            if st.button("Prev", disabled=st.session_state.churn_page <= 1):
                st.session_state.churn_page -= 1
                st.rerun()
        with pcol2:
            st.markdown(
                f'<div style="text-align:center; color:#64748b; font-size:12px; padding-top:8px">'
                f'Page {st.session_state.churn_page}</div>',
                unsafe_allow_html=True,
            )
        with pcol3:
            if st.button("Next", disabled=len(at_risk) < 20):
                st.session_state.churn_page += 1
                st.rerun()
    else:
        st.success("No customers above churn risk threshold.")

st.divider()

# ── Lifetime value ────────────────────────────────────────────────────────────
section("Lifetime Value Distribution and Top Customers")

insight_block(
    "The histogram reveals the long tail typical of e-commerce: "
    "a small number of high-value customers drive a disproportionate share of revenue. "
    "Quartile markers show where your customer base concentrates."
)

top = client.get_top_customers(limit=200)

if top:
    col_ltv, col_tbl = st.columns([2, 3])

    with col_ltv:
        st.plotly_chart(ltv_histogram(top), use_container_width=True)

    with col_tbl:
        df_top = pd.DataFrame(top[:50])
        df_top.insert(0, "Rank", range(1, len(df_top) + 1))
        df_top["lifetime_value"]    = df_top["lifetime_value"].apply(lambda x: f"${x:,.2f}")
        df_top["recency_days"]      = df_top["recency_days"].apply(lambda x: f"{x}d")
        df_top["last_purchase_date"] = df_top["last_purchase_date"].fillna("n/a")
        df_top["customer_segment"]   = df_top["customer_segment"].fillna("Other")
        df_top = df_top.rename(columns={
            "user_id":            "ID",
            "email":              "Email",
            "customer_segment":   "Segment",
            "lifetime_value":     "Lifetime Value",
            "total_purchases":    "Orders",
            "recency_days":       "Last Purchase",
            "last_purchase_date": "Last Date",
        })
        st.dataframe(
            df_top[["Rank", "Email", "Segment", "Lifetime Value", "Orders", "Last Purchase", "Last Date"]],
            use_container_width=True, hide_index=True,
        )

    ltv_vals  = sorted([c["lifetime_value"] for c in top], reverse=True)
    total_ltv = sum(ltv_vals)
    top20_pct = sum(ltv_vals[:max(1, len(ltv_vals) // 5)]) / total_ltv * 100 if total_ltv else 0
    insight_block(
        f"The top 20% of customers by LTV account for <b>{top20_pct:.0f}%</b> of total revenue "
        "in this sample. Protecting and rewarding these customers is your highest-ROI retention strategy.",
        variant="success",
    )
else:
    unavailable("Top customers")
