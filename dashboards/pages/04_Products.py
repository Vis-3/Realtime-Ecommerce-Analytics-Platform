import pandas as pd
import streamlit as st

from api_client import client
from components.charts import category_treemap, top_products_chart
from components.kpi_tiles import unavailable
from components.style import inject_css, insight_block, page_header, section

st.set_page_config(page_title="Products | Analytics", layout="wide")
inject_css()

page_header("Product Analytics", "Category breakdown, top performers, and inventory health")

# ── Category treemap ──────────────────────────────────────────────────────────
section("Revenue by Category (Last 30 Days)")

insight_block(
    "Tile area is proportional to revenue. Hover for exact figures and buyer counts. "
    "Use this to identify which categories deserve more inventory depth."
)

cats = client.get_top_categories()
if cats:
    col_tree, col_stat = st.columns([3, 1])
    with col_tree:
        st.plotly_chart(category_treemap(cats), use_container_width=True)
    with col_stat:
        df_cats = pd.DataFrame(cats)
        df_cats["revenue"]       = df_cats["revenue"].apply(lambda x: f"${x:,.0f}")
        df_cats["unique_buyers"] = df_cats["unique_buyers"].apply(lambda x: f"{x:,}")
        df_cats = df_cats.rename(columns={
            "category":      "Category",
            "revenue":       "Revenue",
            "unique_buyers": "Buyers",
            "units_sold":    "Units",
        })
        st.dataframe(df_cats[["Category", "Revenue", "Buyers", "Units"]],
                     use_container_width=True, hide_index=True)

    top_cat = max(cats, key=lambda c: c["revenue"])
    insight_block(
        f"<b>{top_cat['category']}</b> leads with ${top_cat['revenue']:,.0f} in revenue "
        f"from {top_cat['unique_buyers']:,} unique buyers. "
        "Consider expanding inventory depth in this category.",
        variant="success",
    )
else:
    unavailable("Category data")

st.divider()

# ── Today's top products ──────────────────────────────────────────────────────
section("Today's Performance")

col1, col2 = st.columns(2)

with col1:
    products = client.get_top_products(limit=10)
    if products:
        st.plotly_chart(top_products_chart(products, "Top 10 Products Today"),
                        use_container_width=True)
    else:
        unavailable("Top products")

with col2:
    cats_today = client.get_top_categories()
    if cats_today:
        st.plotly_chart(top_products_chart(cats_today, "Top Categories Today"),
                        use_container_width=True)
    else:
        unavailable("Top categories")

st.divider()

# ── Inventory alerts ──────────────────────────────────────────────────────────
section("Inventory Health Alerts")

insight_block(
    "Products flagged here have fewer than 50 units in stock or fewer than 7 days of "
    "inventory remaining at current sales velocity. Act on Critical items immediately.",
    variant="warning",
)

alerts = client.get_inventory_alerts()

if alerts:
    critical = [a for a in alerts if a.get("days_until_stockout") is not None and a["days_until_stockout"] < 3]
    warning  = [a for a in alerts if a.get("days_until_stockout") is not None and 3 <= a["days_until_stockout"] < 7]
    no_sales = [a for a in alerts if a.get("days_until_stockout") is None]

    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">Critical (under 3 days)</div>'
            f'<div class="kpi-value" style="color:#ef4444">{len(critical)}</div>'
            f'</div>', unsafe_allow_html=True,
        )
    with bc2:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">Warning (3 to 7 days)</div>'
            f'<div class="kpi-value" style="color:#f59e0b">{len(warning)}</div>'
            f'</div>', unsafe_allow_html=True,
        )
    with bc3:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">No Recent Sales</div>'
            f'<div class="kpi-value" style="color:#6b7280">{len(no_sales)}</div>'
            f'</div>', unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    if critical:
        st.error(f"{len(critical)} product(s) will stock out within 3 days. Reorder immediately.")

    df_alerts = pd.DataFrame(alerts)
    df_alerts["days_until_stockout"] = df_alerts["days_until_stockout"].apply(
        lambda x: f"{x:.1f}d" if x is not None else "n/a"
    )
    df_alerts = df_alerts.rename(columns={
        "product_id":          "ID",
        "product_name":        "Product",
        "category":            "Category",
        "current_stock":       "Stock",
        "units_sold_last_24h": "Sold (24h)",
        "days_until_stockout": "Days to Stockout",
    })
    st.dataframe(df_alerts, use_container_width=True, hide_index=True)
else:
    st.success("All products have healthy stock levels.")
