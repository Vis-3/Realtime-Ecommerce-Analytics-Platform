import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from components.style import ACCENT, ACCENT2, PLOTLY_TEMPLATE, SEGMENT_COLORS

_LAYOUT = dict(
    template=PLOTLY_TEMPLATE,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#e2e8f0"),
    margin=dict(l=0, r=0, t=32, b=0),
    legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
)


def _layout(**overrides) -> dict:
    """Return _LAYOUT merged with overrides — avoids duplicate-kwarg errors."""
    return {**_LAYOUT, **overrides}


# ── Existing charts ───────────────────────────────────────────────────────────

def revenue_trend_chart(daily_kpis: list) -> go.Figure:
    """Revenue bars + AOV line + 7-day moving average."""
    df = pd.DataFrame(reversed(daily_kpis))
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df["ma7"] = df["revenue"].rolling(7, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["date"], y=df["revenue"], name="Daily Revenue",
        marker_color=ACCENT, opacity=0.7,
        hovertemplate="<b>%{x|%b %d}</b><br>Revenue: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["ma7"], name="7-day MA",
        line=dict(color="#f1f5f9", width=2, dash="dot"),
        hovertemplate="7d MA: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["avg_order_value"], name="Avg Order Value",
        line=dict(color=ACCENT2, width=2),
        yaxis="y2",
        hovertemplate="AOV: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT,
        title="30-Day Revenue Trend with 7-Day Moving Average",
        yaxis=dict(title="Revenue ($)", gridcolor="rgba(255,255,255,0.06)"),
        yaxis2=dict(title="AOV ($)", overlaying="y", side="right", gridcolor="rgba(0,0,0,0)"),
        bargap=0.3, hovermode="x unified",
    )
    return fig


def rfm_segment_chart(segments: list) -> go.Figure:
    segs    = [s["customer_segment"] for s in segments]
    revenue = [s["total_revenue"] for s in segments]
    counts  = [s["customer_count"] for s in segments]
    colors  = [SEGMENT_COLORS.get(s, "#9ca3af") for s in segs]

    fig = go.Figure(go.Bar(
        y=segs, x=revenue, orientation="h",
        marker_color=colors,
        text=[f"  {c:,} users" for c in counts],
        textposition="inside", insidetextanchor="start",
        textfont=dict(color="#0e1117", size=11, family="Inter"),
        hovertemplate="<b>%{y}</b><br>Revenue: $%{x:,.0f}<br>Users: %{text}<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT, title="Revenue by Customer Segment",
        xaxis=dict(title="Total Revenue ($)", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(autorange="reversed"), height=420,
    )
    return fig


def churn_gauge(probability: float, label: str) -> go.Figure:
    color = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}.get(label, "#94a3b8")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(probability * 100, 1),
        number=dict(suffix="%", font=dict(size=36, color=color)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor="#64748b"),
            bar=dict(color=color, thickness=0.25),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            steps=[
                dict(range=[0, 40],   color="rgba(34,197,94,0.15)"),
                dict(range=[40, 70],  color="rgba(245,158,11,0.15)"),
                dict(range=[70, 100], color="rgba(239,68,68,0.15)"),
            ],
            threshold=dict(line=dict(color=color, width=3), thickness=0.75, value=probability * 100),
        ),
        title=dict(text="Churn Probability", font=dict(size=14, color="#94a3b8")),
    ))
    fig.update_layout(**_layout(height=220, margin=dict(l=20, r=20, t=40, b=0)))
    return fig


def hourly_revenue_chart(hourly: list) -> go.Figure:
    hours   = [h["hour"][-8:-3] for h in reversed(hourly)]
    revenue = [h["revenue"] for h in reversed(hourly)]
    bar_colors = [ACCENT2 if i == len(hours) - 1 else ACCENT for i in range(len(hours))]

    fig = go.Figure(go.Bar(
        x=hours, y=revenue, marker_color=bar_colors, name="Revenue",
        hovertemplate="<b>%{x}</b><br>$%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT, title="Hourly Revenue (last 24h)",
        xaxis=dict(title="Hour", gridcolor="rgba(0,0,0,0)"),
        yaxis=dict(title="Revenue ($)", gridcolor="rgba(255,255,255,0.06)"),
        bargap=0.25,
    )
    return fig


def geo_revenue_chart(country_data: list) -> go.Figure:
    countries = [c["country"] for c in country_data]
    revenue   = [c["revenue"] for c in country_data]
    buyers    = [c["unique_buyers"] for c in country_data]

    fig = px.choropleth(
        locations=countries, locationmode="country names",
        color=revenue, hover_name=countries,
        hover_data={"unique_buyers": buyers},
        color_continuous_scale=["#1a1d27", ACCENT, ACCENT2],
        labels={"color": "Revenue ($)"},
    )
    fig.update_layout(
        **_LAYOUT, title="Revenue by Country (last 30 days)",
        geo=dict(
            bgcolor="rgba(0,0,0,0)", showframe=False,
            showcoastlines=True, coastlinecolor="rgba(255,255,255,0.1)",
            showland=True, landcolor="#1a1d27",
            showocean=True, oceancolor="#0e1117",
        ),
        coloraxis_colorbar=dict(title="Revenue ($)", tickfont=dict(color="#94a3b8")),
        height=380,
    )
    return fig


def payment_pie_chart(payments: list) -> go.Figure:
    methods = [p["payment_method"] or "Unknown" for p in payments]
    counts  = [p["transaction_count"] for p in payments]
    colors  = [ACCENT, ACCENT2, "#f59e0b", "#22c55e", "#ef4444", "#a855f7"]

    fig = go.Figure(go.Pie(
        labels=methods, values=counts, hole=0.55,
        marker=dict(colors=colors[:len(methods)], line=dict(color="#0e1117", width=2)),
        textinfo="percent+label", textfont=dict(size=12),
        hovertemplate="<b>%{label}</b><br>%{value:,} txns (%{percent})<extra></extra>",
    ))
    fig.update_layout(**_LAYOUT, title="Payment Methods (24h)", height=320)
    return fig


def new_vs_returning_chart(data: list) -> go.Figure:
    types   = [d["customer_type"] for d in data]
    revenue = [d["revenue"] for d in data]
    users   = [d["customers"] for d in data]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Revenue", x=types, y=revenue,
        marker_color=[ACCENT2, ACCENT], yaxis="y",
        hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="Users", x=types, y=users,
        mode="markers+text",
        marker=dict(size=14, color="#f1f5f9", symbol="diamond"),
        text=[f"{u:,}" for u in users], textposition="top center",
        yaxis="y2",
        hovertemplate="%{y:,} users<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT, title="New vs Returning Customers Today",
        yaxis=dict(title="Revenue ($)", gridcolor="rgba(255,255,255,0.06)"),
        yaxis2=dict(title="Users", overlaying="y", side="right"),
        bargap=0.5, height=300,
    )
    return fig


def top_products_chart(products: list, title="Top Products") -> go.Figure:
    names   = [p.get("product_name", p.get("category", "?"))[:28] for p in reversed(products)]
    revenue = [p["revenue"] for p in reversed(products)]
    cats    = [p.get("category", "") for p in reversed(products)]
    cat_set = list(dict.fromkeys(cats))
    palette = [ACCENT, ACCENT2, "#f59e0b", "#22c55e", "#ef4444", "#a855f7", "#fb923c"]
    cat_colors = {c: palette[i % len(palette)] for i, c in enumerate(cat_set)}
    colors = [cat_colors.get(c, ACCENT) for c in cats]

    fig = go.Figure(go.Bar(
        y=names, x=revenue, orientation="h", marker_color=colors,
        hovertemplate="<b>%{y}</b><br>$%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT, title=title,
        xaxis=dict(title="Revenue ($)", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(autorange="reversed"),
        height=max(300, len(products) * 36),
    )
    return fig


def churn_histogram(at_risk: list) -> go.Figure:
    scores = [r["churn_risk_score"] for r in at_risk]
    fig = go.Figure(go.Histogram(
        x=scores, nbinsx=20,
        marker=dict(
            color=scores,
            colorscale=[[0, "#22c55e"], [0.4, "#f59e0b"], [0.7, "#ef4444"], [1, "#dc2626"]],
            line=dict(color="#0e1117", width=0.5),
        ),
        hovertemplate="Score: %{x:.2f}<br>Count: %{y}<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT, title="Churn Risk Score Distribution",
        xaxis=dict(title="Churn Risk Score", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(title="# Users", gridcolor="rgba(255,255,255,0.06)"),
        height=300,
    )
    return fig


# ── New charts ────────────────────────────────────────────────────────────────

def rfm_scatter_chart(data: list) -> go.Figure:
    """
    RFM bubble chart: x=recency, y=frequency, size=monetary, color=segment.
    Classic data-science segmentation visual.
    """
    if not data:
        return go.Figure()

    df = pd.DataFrame(data)
    df["customer_segment"] = df["customer_segment"].fillna("Other")

    # Normalise monetary to bubble size (px range 6–40)
    m_min, m_max = df["monetary"].min(), df["monetary"].max()
    if m_max > m_min:
        df["bubble"] = 6 + 34 * (df["monetary"] - m_min) / (m_max - m_min)
    else:
        df["bubble"] = 12

    fig = go.Figure()
    for seg, grp in df.groupby("customer_segment"):
        color = SEGMENT_COLORS.get(seg, "#9ca3af")
        fig.add_trace(go.Scatter(
            x=grp["recency_days"], y=grp["frequency"],
            mode="markers",
            name=seg,
            marker=dict(
                size=grp["bubble"],
                color=color,
                opacity=0.72,
                line=dict(color="rgba(0,0,0,0.3)", width=0.5),
            ),
            customdata=grp[["user_id", "monetary"]].values,
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Recency: %{x}d ago<br>"
                "Orders: %{y}<br>"
                "Spend: $%{customdata[1]:,.0f}<br>"
                "User: #%{customdata[0]}<extra></extra>"
            ),
        ))

    fig.update_layout(
        **_layout(
            title="RFM Customer Map — Recency vs Frequency (bubble = spend)",
            xaxis=dict(
                title="Recency (days since last purchase) →  higher = worse",
                gridcolor="rgba(255,255,255,0.06)", autorange="reversed",
            ),
            yaxis=dict(title="Frequency (total orders)", gridcolor="rgba(255,255,255,0.06)"),
            height=500,
            legend=dict(
                bgcolor="rgba(20,22,32,0.85)", bordercolor="rgba(255,255,255,0.1)",
                borderwidth=1, font=dict(size=11),
            ),
        )
    )
    return fig


def ltv_histogram(customers: list) -> go.Figure:
    """Distribution of customer lifetime values with quartile annotations."""
    if not customers:
        return go.Figure()

    vals = [c["lifetime_value"] for c in customers if c.get("lifetime_value")]
    df = pd.Series(vals)
    q25, q50, q75 = df.quantile([0.25, 0.5, 0.75])

    fig = go.Figure(go.Histogram(
        x=vals, nbinsx=30,
        marker=dict(
            color=vals,
            colorscale=[[0, "#1a1d27"], [0.5, ACCENT], [1, ACCENT2]],
            line=dict(color="#0e1117", width=0.5),
        ),
        hovertemplate="LTV: $%{x:,.0f}<br>Customers: %{y}<extra></extra>",
    ))
    # Add quartile lines
    for val, label, col in [(q25, "Q1", "#94a3b8"), (q50, "Median", "#f1f5f9"), (q75, "Q3", ACCENT2)]:
        fig.add_vline(x=val, line=dict(color=col, dash="dash", width=1.5),
                      annotation_text=f"{label} ${val:,.0f}",
                      annotation_font=dict(color=col, size=11))

    fig.update_layout(
        **_LAYOUT,
        title="Customer Lifetime Value Distribution",
        xaxis=dict(title="Lifetime Value ($)", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(title="# Customers", gridcolor="rgba(255,255,255,0.06)"),
        height=320,
    )
    return fig


def segment_radar_chart(segments: list) -> go.Figure:
    """Normalised radar comparing top segments on R (inverted), F, M dimensions."""
    if not segments:
        return go.Figure()

    top = sorted(segments, key=lambda s: s["total_revenue"], reverse=True)[:6]
    dims = ["Recency\n(low=good)", "Frequency", "Spend"]

    # Normalise each dimension to 0–1 across the shown segments
    r_vals = [s["avg_recency_days"] for s in top]
    f_vals = [s["avg_frequency"]    for s in top]
    m_vals = [s["avg_monetary"]     for s in top]

    def norm_inv(vals):  # lower raw → higher score
        mx, mn = max(vals), min(vals)
        return [1 - (v - mn) / (mx - mn + 1e-9) for v in vals]

    def norm(vals):
        mx, mn = max(vals), min(vals)
        return [(v - mn) / (mx - mn + 1e-9) for v in vals]

    r_n, f_n, m_n = norm_inv(r_vals), norm(f_vals), norm(m_vals)

    def _hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    palette = [ACCENT, ACCENT2, "#f59e0b", "#22c55e", "#ef4444", "#a855f7"]
    fig = go.Figure()
    for i, seg in enumerate(top):
        name = seg["customer_segment"]
        scores = [r_n[i], f_n[i], m_n[i], r_n[i]]  # close the polygon
        labels = dims + [dims[0]]
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatterpolar(
            r=scores, theta=labels, fill="toself",
            name=name,
            line=dict(color=color),
            fillcolor=_hex_to_rgba(color, 0.15),
            opacity=0.85,
            hovertemplate=f"<b>{name}</b><br>%{{theta}}: %{{r:.2f}}<extra></extra>",
        ))

    fig.update_layout(
        **_LAYOUT,
        title="Segment Profile Comparison (normalised R·F·M)",
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, range=[0, 1], gridcolor="rgba(255,255,255,0.1)",
                            tickfont=dict(size=9, color="#64748b")),
            angularaxis=dict(gridcolor="rgba(255,255,255,0.1)", tickfont=dict(size=11)),
        ),
        height=420,
        showlegend=True,
    )
    return fig


def weekly_revenue_chart(weekly: list) -> go.Figure:
    """Weekly revenue bars with week-over-week % growth line."""
    if not weekly:
        return go.Figure()

    df = pd.DataFrame(reversed(weekly))
    df["week_label"] = pd.to_datetime(df["week_start"]).dt.strftime("W%U\n%b %d")
    df["wow_pct"] = df["revenue"].pct_change() * 100

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df["week_label"], y=df["revenue"], name="Weekly Revenue",
        marker_color=ACCENT, opacity=0.8,
        hovertemplate="<b>%{x}</b><br>$%{y:,.0f}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=df["week_label"], y=df["wow_pct"], name="WoW Growth %",
        mode="lines+markers",
        line=dict(color=ACCENT2, width=2),
        marker=dict(size=6, color=ACCENT2),
        hovertemplate="WoW: %{y:+.1f}%<extra></extra>",
    ), secondary_y=True)

    fig.update_layout(
        **_LAYOUT,
        title="Weekly Revenue Trend with Week-over-Week Growth",
        bargap=0.3, hovermode="x unified",
    )
    fig.update_yaxes(
        title_text="Revenue ($)", gridcolor="rgba(255,255,255,0.06)", secondary_y=False
    )
    fig.update_yaxes(
        title_text="WoW Growth (%)", gridcolor="rgba(0,0,0,0)", secondary_y=True,
        zeroline=True, zerolinecolor="rgba(255,255,255,0.2)",
    )
    return fig


def dow_heatmap(daily_kpis: list) -> go.Figure:
    """Average revenue by day-of-week across the last N weeks — reveals seasonality."""
    if not daily_kpis:
        return go.Figure()

    df = pd.DataFrame(daily_kpis)
    df["date"] = pd.to_datetime(df["date"])
    df["dow"]  = df["date"].dt.day_name()
    df["week"] = df["date"].dt.isocalendar().week.astype(str)

    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = df.pivot_table(values="revenue", index="week", columns="dow", aggfunc="sum")
    pivot = pivot.reindex(columns=[c for c in order if c in pivot.columns])

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=[f"Wk {w}" for w in pivot.index.tolist()],
        colorscale=[[0, "#0e1117"], [0.5, ACCENT], [1, ACCENT2]],
        hovertemplate="<b>%{x}</b>, Week %{y}<br>Revenue: $%{z:,.0f}<extra></extra>",
        colorbar=dict(title="Revenue ($)", tickfont=dict(color="#94a3b8")),
    ))
    fig.update_layout(
        **_layout(
            title="Revenue Heatmap by Day of Week",
            xaxis=dict(title=""),
            yaxis=dict(title="", autorange="reversed"),
            height=max(260, len(pivot) * 22),
            margin=dict(l=60, r=10, t=40, b=10),
        )
    )
    return fig


def age_group_chart(data: list) -> go.Figure:
    """Revenue and average order value by customer age group."""
    if not data:
        return go.Figure()

    df = pd.DataFrame(data)
    palette = [ACCENT, ACCENT2, "#f59e0b", "#22c55e", "#ef4444"]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df["age_group"], y=df["revenue"], name="Revenue",
        marker_color=[palette[i % len(palette)] for i in range(len(df))],
        hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.0f}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=df["age_group"], y=df["avg_order_value"], name="Avg Order Value",
        mode="lines+markers+text",
        line=dict(color="#f1f5f9", width=2),
        marker=dict(size=8, color="#f1f5f9"),
        text=[f"${v:.0f}" for v in df["avg_order_value"]],
        textposition="top center",
        hovertemplate="AOV: $%{y:,.2f}<extra></extra>",
    ), secondary_y=True)

    fig.update_layout(
        **_LAYOUT, title="Revenue & AOV by Age Group (last 30 days)",
        bargap=0.35, hovermode="x unified",
    )
    fig.update_yaxes(title_text="Revenue ($)", gridcolor="rgba(255,255,255,0.06)", secondary_y=False)
    fig.update_yaxes(title_text="Avg Order Value ($)", gridcolor="rgba(0,0,0,0)", secondary_y=True)
    return fig


def category_treemap(categories: list) -> go.Figure:
    """Revenue treemap by product category — instantly shows relative category sizes."""
    if not categories:
        return go.Figure()

    labels  = [c.get("category", c.get("product_name", "?")) for c in categories]
    parents = ["" for _ in categories]
    values  = [c["revenue"] for c in categories]
    buyers  = [c.get("unique_buyers", 0) for c in categories]

    palette = [ACCENT, ACCENT2, "#f59e0b", "#22c55e", "#ef4444", "#a855f7",
               "#fb923c", "#0ea5e9", "#84cc16", "#f43f5e"]

    fig = go.Figure(go.Treemap(
        labels=labels, parents=parents, values=values,
        customdata=buyers,
        texttemplate="<b>%{label}</b><br>$%{value:,.0f}",
        hovertemplate="<b>%{label}</b><br>Revenue: $%{value:,.0f}<br>Buyers: %{customdata:,}<extra></extra>",
        marker=dict(
            colors=palette[:len(labels)],
            line=dict(width=2, color="#0e1117"),
        ),
        textfont=dict(size=13),
    ))
    fig.update_layout(
        **_layout(
            title="Category Revenue Treemap (last 30 days)",
            height=380,
            margin=dict(l=0, r=0, t=40, b=0),
        )
    )
    return fig
