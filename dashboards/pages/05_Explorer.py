import pandas as pd
import streamlit as st

from api_client import client
from components.charts import churn_gauge
from components.style import (
    CHURN_COLORS,
    SEGMENT_COLORS,
    churn_badge,
    inject_css,
    page_header,
    seg_badge,
    section,
)

st.set_page_config(page_title="Explorer | Analytics", layout="wide")
inject_css()

page_header("Explorer", "Deep-dive into any customer or product")

tab_customer, tab_product = st.tabs(["Customer Lookup", "Product Lookup"])

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMER TAB
# ─────────────────────────────────────────────────────────────────────────────
with tab_customer:
    col_in, col_btn = st.columns([2, 1])
    with col_in:
        cust_id = st.number_input("User ID", min_value=1, max_value=10000,
                                   value=st.session_state.get("explorer_uid", 1),
                                   key="explorer_uid_input", step=1)
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        c_lookup = st.button("Lookup Customer", type="primary", use_container_width=True)

    if c_lookup or "explorer_uid" in st.session_state:
        st.session_state.explorer_uid = cust_id

        with st.spinner("Fetching customer profile..."):
            rfm   = client.get_customer_rfm(cust_id)
            churn = client.get_customer_churn(cust_id)
            recs  = client.get_user_recommendations(cust_id)

        if not rfm and not churn:
            st.error(f"User {cust_id} not found.")
        else:
            st.markdown("---")
            col_rfm, col_churn = st.columns(2)

            # ── RFM Card ──────────────────────────────────────────────────
            with col_rfm:
                section("RFM Profile")
                if rfm:
                    seg   = rfm.get("customer_segment", "Other")
                    color = SEGMENT_COLORS.get(seg, "#9ca3af")
                    st.markdown(
                        f'<div style="text-align:center; margin-bottom:16px">'
                        f'{seg_badge(seg)}</div>',
                        unsafe_allow_html=True,
                    )

                    mc1, mc2, mc3 = st.columns(3)
                    mc1.markdown(
                        f'<div class="info-card"><div class="info-card-title">Recency</div>'
                        f'<div class="info-card-value" style="color:{color}">'
                        f'{rfm["recency_days"]}d</div></div>',
                        unsafe_allow_html=True,
                    )
                    mc2.markdown(
                        f'<div class="info-card"><div class="info-card-title">Frequency</div>'
                        f'<div class="info-card-value" style="color:{color}">'
                        f'{rfm["frequency"]}</div></div>',
                        unsafe_allow_html=True,
                    )
                    mc3.markdown(
                        f'<div class="info-card"><div class="info-card-title">Monetary</div>'
                        f'<div class="info-card-value" style="color:{color}">'
                        f'${rfm["monetary"]:,.0f}</div></div>',
                        unsafe_allow_html=True,
                    )

                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("R Score", f"{rfm['r_score']} / 5")
                    sc2.metric("F Score", f"{rfm['f_score']} / 5")
                    sc3.metric("M Score", f"{rfm['m_score']} / 5")

                    st.markdown(
                        f'<div class="info-card" style="margin-top:12px">'
                        f'<div class="info-card-title">Recommended Action</div>'
                        f'<div style="color:#e2e8f0; font-size:14px; margin-top:4px">'
                        f'{rfm.get("recommended_action","—")}</div></div>',
                        unsafe_allow_html=True,
                    )

            # ── Churn Card ────────────────────────────────────────────────
            with col_churn:
                section("Churn Risk")
                if churn:
                    label = churn.get("churn_risk_label", "Low")
                    prob  = churn.get("churn_probability", 0.0)

                    st.markdown(
                        f'<div style="text-align:center; margin-bottom:8px">'
                        f'{churn_badge(label)}</div>',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(churn_gauge(prob, label), use_container_width=True)

                    factors = churn.get("top_risk_factors", [])
                    if factors:
                        st.markdown("**Top Risk Factors:**")
                        for factor in factors:
                            st.markdown(
                                f'<div class="risk-factor">⚠ {factor}</div>',
                                unsafe_allow_html=True,
                            )

            # ── Recommendations ───────────────────────────────────────────
            st.markdown("---")
            section(f"Recommended Products for User {cust_id}")
            if recs:
                df_recs = pd.DataFrame(recs)
                df_recs["current_price"] = df_recs["current_price"].apply(lambda x: f"${x:,.2f}")
                df_recs["recommendation_score"] = df_recs["recommendation_score"].apply(
                    lambda x: f"{x:.0f} buyers"
                )
                df_recs = df_recs.rename(columns={
                    "product_name":         "Product",
                    "category":             "Category",
                    "current_price":        "Price",
                    "recommendation_score": "Score",
                    "reason":               "Reason",
                })
                st.dataframe(df_recs[["Product", "Category", "Price", "Score", "Reason"]],
                             use_container_width=True, hide_index=True)
            else:
                st.info("No recommendations available for this user.")

# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT TAB
# ─────────────────────────────────────────────────────────────────────────────
with tab_product:
    col_pin, col_pbtn = st.columns([2, 1])
    with col_pin:
        prod_id = st.number_input("Product ID", min_value=1, max_value=1000,
                                   value=st.session_state.get("explorer_pid", 1),
                                   key="explorer_pid_input", step=1)
    with col_pbtn:
        st.markdown("<br>", unsafe_allow_html=True)
        p_lookup = st.button("Lookup Product", type="primary", use_container_width=True)

    if p_lookup or "explorer_pid" in st.session_state:
        st.session_state.explorer_pid = prod_id

        with st.spinner("Fetching product details..."):
            product = client.get_product(prod_id)
            similar = client.get_similar_products(prod_id)

        if not product:
            st.error(f"Product {prod_id} not found.")
        else:
            st.markdown("---")
            section("Product Detail")

            pc1, pc2, pc3, pc4 = st.columns(4)
            pc1.markdown(
                f'<div class="info-card"><div class="info-card-title">Category</div>'
                f'<div class="info-card-value" style="font-size:16px">'
                f'{product["category"]}</div></div>',
                unsafe_allow_html=True,
            )
            pc2.markdown(
                f'<div class="info-card"><div class="info-card-title">Price</div>'
                f'<div class="info-card-value">${product["current_price"]:,.2f}</div></div>',
                unsafe_allow_html=True,
            )
            pc3.markdown(
                f'<div class="info-card"><div class="info-card-title">Stock</div>'
                f'<div class="info-card-value" style="color:{"#ef4444" if product["stock_quantity"] < 20 else "#22c55e"}">'
                f'{product["stock_quantity"]:,}</div></div>',
                unsafe_allow_html=True,
            )
            pc4.markdown(
                f'<div class="info-card"><div class="info-card-title">Revenue (24h)</div>'
                f'<div class="info-card-value" style="color:#7c3aed">'
                f'${product["revenue_24h"]:,.0f}</div></div>',
                unsafe_allow_html=True,
            )

            detail_cols = st.columns(3)
            detail_cols[0].metric("Units Sold (24h)", f'{product["units_sold_24h"]:,}')
            if product.get("brand"):
                detail_cols[1].metric("Brand", product["brand"])
            if product.get("subcategory"):
                detail_cols[2].metric("Subcategory", product["subcategory"])

            # ── Similar products ───────────────────────────────────────────
            st.markdown("---")
            section("Customers Who Bought This Also Bought")
            if similar:
                df_sim = pd.DataFrame(similar)
                df_sim["current_price"]  = df_sim["current_price"].apply(lambda x: f"${x:,.2f}")
                df_sim["confidence_pct"] = df_sim["confidence_pct"].apply(lambda x: f"{x:.1f}%")

                df_sim = df_sim.rename(columns={
                    "product_name":  "Product",
                    "category":      "Category",
                    "current_price": "Price",
                    "confidence_pct":"Confidence",
                    "lift":          "Lift",
                })
                st.dataframe(df_sim[["Product","Category","Price","Confidence","Lift"]], use_container_width=True, hide_index=True)
            else:
                st.info("Not enough co-purchase data for this product.")
