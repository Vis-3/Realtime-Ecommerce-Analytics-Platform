import pandas as pd
import streamlit as st

from api_client import client
from components.charts import top_products_chart
from components.kpi_tiles import unavailable
from components.style import SEGMENT_COLORS, inject_css, page_header, section

st.set_page_config(page_title="Recommendations | Analytics", layout="wide")
inject_css()

page_header("Product Recommendations", "Trending, personalised, and item-based recommendations")

# ── Trending products ───────────────────────────────────────────────────────
section("Trending Products — Last 24 Hours")
trending = client.get_trending()

if trending:
    col1, col2 = st.columns([3, 2])
    with col1:
        st.plotly_chart(top_products_chart(trending, title="Top 20 Products by Revenue (24h)"),
                        use_container_width=True)
    with col2:
        df_trend = pd.DataFrame(trending)
        df_trend.insert(0, "Rank", range(1, len(df_trend) + 1))
        df_trend["revenue"]        = df_trend["revenue"].apply(lambda x: f"${x:,.0f}")
        df_trend["current_price"]  = df_trend["current_price"].apply(lambda x: f"${x:,.2f}")
        df_trend = df_trend.rename(columns={
            "product_name":  "Product",
            "category":      "Category",
            "current_price": "Price",
            "units_sold":    "Units",
            "revenue":       "Revenue",
        })
        st.dataframe(df_trend[["Rank","Product","Category","Units","Revenue"]],
                     use_container_width=True, hide_index=True, height=440)
else:
    unavailable("Trending products")

st.divider()

# ── User recommendations ────────────────────────────────────────────────────
section("Personalised Recommendations")
col_input, col_btn = st.columns([2, 1])

with col_input:
    user_id = st.number_input("Enter User ID", min_value=1, max_value=10000,
                               value=st.session_state.get("rec_user_id", 1),
                               key="rec_user_input", step=1)
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    lookup = st.button("Get Recommendations", type="primary", use_container_width=True)

if lookup or "rec_user_id" in st.session_state:
    st.session_state.rec_user_id = user_id
    with st.spinner("Fetching recommendations..."):
        recs  = client.get_user_recommendations(user_id)
        rfm   = client.get_customer_rfm(user_id)

    if rfm:
        seg = rfm.get("customer_segment", "Unknown")
        st.markdown(
            f'Recommendations for **User {user_id}** &nbsp;'
            f'<span class="seg-badge" style="background:{SEGMENT_COLORS.get(seg, "#9ca3af")}">'
            f'{seg}</span>',
            unsafe_allow_html=True,
        )

    if recs:
        df_recs = pd.DataFrame(recs)
        df_recs["current_price"]        = df_recs["current_price"].apply(lambda x: f"${x:,.2f}")
        df_recs["recommendation_score"] = df_recs["recommendation_score"].apply(lambda x: f"{x:.0f} buyers")
        df_recs = df_recs.rename(columns={
            "product_name":         "Product",
            "category":             "Category",
            "current_price":        "Price",
            "recommendation_score": "Similarity Score",
            "reason":               "Why",
        })
        st.dataframe(df_recs[["Product","Category","Price","Similarity Score","Why"]],
                     use_container_width=True, hide_index=True)
    elif recs is not None:
        st.info(f"No recommendations found for User {user_id} — they may have purchased too few items.")
    else:
        unavailable(f"Recommendations for User {user_id}")

st.divider()

# ── Similar products ────────────────────────────────────────────────────────
section("Customers Who Bought This Also Bought")
col_p, col_pb = st.columns([2, 1])

with col_p:
    product_id = st.number_input("Enter Product ID", min_value=1, max_value=1000,
                                  value=st.session_state.get("sim_product_id", 1),
                                  key="sim_product_input", step=1)
with col_pb:
    st.markdown("<br>", unsafe_allow_html=True)
    p_lookup = st.button("Find Similar", type="primary", use_container_width=True)

if p_lookup or "sim_product_id" in st.session_state:
    st.session_state.sim_product_id = product_id
    with st.spinner("Computing similarities..."):
        product  = client.get_product(product_id)
        similar  = client.get_similar_products(product_id)

    if product:
        st.markdown(
            f'Similar to: **{product["product_name"]}** — '
            f'`{product["category"]}` — ${product["current_price"]:.2f}',
        )

    if similar:
        df_sim = pd.DataFrame(similar)
        df_sim["current_price"]  = df_sim["current_price"].apply(lambda x: f"${x:,.2f}")
        df_sim["confidence_pct"] = df_sim["confidence_pct"].apply(lambda x: f"{x:.1f}%")

        df_sim = df_sim.rename(columns={
            "product_name":   "Product",
            "category":       "Category",
            "current_price":  "Price",
            "confidence_pct": "Confidence",
            "lift":           "Lift",
        })
        st.dataframe(df_sim[["Product","Category","Price","Confidence","Lift"]], use_container_width=True, hide_index=True)
    elif similar is not None:
        st.info(f"Not enough co-purchase data for Product {product_id}.")
    else:
        unavailable(f"Similar products for Product {product_id}")
