import streamlit as st

SEGMENT_COLORS = {
    "Champions":           "#FFD700",
    "Loyal Customers":     "#22c55e",
    "Potential Loyalists": "#84cc16",
    "New Customers":       "#3b82f6",
    "Promising":           "#a855f7",
    "Need Attention":      "#f59e0b",
    "About to Sleep":      "#fb923c",
    "At Risk":             "#ef4444",
    "Cannot Lose Them":    "#dc2626",
    "Hibernating":         "#6b7280",
    "Lost":                "#374151",
    "Other":               "#9ca3af",
}

CHURN_COLORS = {"Low": "#22c55e", "Medium": "#f59e0b", "High": "#ef4444"}
PLOTLY_TEMPLATE = "plotly_dark"
ACCENT  = "#7c3aed"
ACCENT2 = "#06b6d4"


def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* ── KPI cards ── */
    .kpi-card {
        background: #13151e;
        border: 1px solid rgba(124,58,237,0.15);
        border-top: 2px solid #7c3aed;
        border-radius: 0 0 12px 12px;
        padding: 22px 18px;
        text-align: center;
        transition: border-top-color 0.2s, box-shadow 0.2s;
    }
    .kpi-card:hover {
        border-top-color: #06b6d4;
        box-shadow: 0 4px 24px rgba(124,58,237,0.12);
    }
    .kpi-label {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 10px;
    }
    .kpi-value {
        font-size: 30px;
        font-weight: 700;
        color: #f1f5f9;
        line-height: 1;
        margin-bottom: 8px;
    }
    .kpi-delta-pos { font-size: 12px; color: #22c55e; font-weight: 600; }
    .kpi-delta-neg { font-size: 12px; color: #ef4444; font-weight: 600; }
    .kpi-delta-neu { font-size: 12px; color: #64748b; font-weight: 600; }

    /* ── Section headers ── */
    .section-header {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #94a3b8;
        padding: 0 0 0 12px;
        border-left: 3px solid #7c3aed;
        margin-bottom: 20px;
        margin-top: 4px;
    }

    /* ── Insight callout ── */
    .insight-card {
        border-left: 3px solid #7c3aed;
        background: rgba(124,58,237,0.05);
        border-radius: 0 8px 8px 0;
        padding: 12px 16px;
        margin: 10px 0 18px 0;
    }
    .insight-card.warning {
        border-left-color: #f59e0b;
        background: rgba(245,158,11,0.05);
    }
    .insight-card.success {
        border-left-color: #22c55e;
        background: rgba(34,197,94,0.05);
    }
    .insight-text {
        font-size: 13px;
        color: #94a3b8;
        line-height: 1.65;
    }
    .insight-text b { color: #cbd5e1; font-weight: 600; }
    .insight-text i { color: #94a3b8; font-style: italic; }

    /* ── Pipeline nodes (home page) ── */
    .pipeline-row {
        display: flex;
        align-items: stretch;
        justify-content: center;
        gap: 0;
        flex-wrap: wrap;
        margin: 28px 0;
    }
    .pipeline-node {
        background: #13151e;
        border: 1px solid rgba(124,58,237,0.2);
        border-top: 2px solid rgba(124,58,237,0.5);
        border-radius: 0 0 10px 10px;
        padding: 14px 22px;
        text-align: center;
        min-width: 120px;
        transition: border-top-color 0.2s;
    }
    .pipeline-node:hover { border-top-color: #06b6d4; }
    .pipeline-step {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.12em;
        color: #7c3aed;
        margin-bottom: 5px;
        font-family: 'JetBrains Mono', monospace;
    }
    .pipeline-node-label {
        font-size: 12px;
        font-weight: 700;
        color: #e2e8f0;
        margin-bottom: 4px;
    }
    .pipeline-node-sub {
        font-size: 10px;
        color: #475569;
        line-height: 1.4;
    }
    .pipeline-arrow {
        display: flex;
        align-items: center;
        padding: 0 8px;
        color: rgba(124,58,237,0.4);
        font-size: 14px;
        flex-shrink: 0;
    }

    /* ── Feature cards (home page) ── */
    .feature-card {
        background: #13151e;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
        padding: 22px 18px;
        min-height: 180px;
        transition: border-color 0.2s, box-shadow 0.2s;
    }
    .feature-card:hover {
        border-color: rgba(124,58,237,0.4);
        box-shadow: 0 4px 20px rgba(124,58,237,0.1);
    }
    .feature-tag {
        display: inline-block;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        padding: 3px 8px;
        border-radius: 4px;
        margin-bottom: 12px;
    }
    .feature-title {
        font-size: 14px;
        font-weight: 700;
        color: #e2e8f0;
        margin-bottom: 8px;
        line-height: 1.3;
    }
    .feature-desc {
        font-size: 11px;
        color: #475569;
        line-height: 1.55;
    }

    /* ── Segment badges ── */
    .seg-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        color: #0e1117;
        letter-spacing: 0.02em;
    }

    /* ── Churn badges ── */
    .churn-high { background:#ef4444; color:#fff; padding:3px 10px; border-radius:4px; font-size:11px; font-weight:700; letter-spacing:0.05em; }
    .churn-med  { background:#f59e0b; color:#0e1117; padding:3px 10px; border-radius:4px; font-size:11px; font-weight:700; }
    .churn-low  { background:#22c55e; color:#0e1117; padding:3px 10px; border-radius:4px; font-size:11px; font-weight:700; }

    /* ── Health dots ── */
    .dot-ok  { height:8px; width:8px; background:#22c55e; border-radius:50%; display:inline-block; box-shadow:0 0 5px #22c55e; }
    .dot-err { height:8px; width:8px; background:#ef4444; border-radius:50%; display:inline-block; box-shadow:0 0 5px #ef4444; }

    /* ── Info cards ── */
    .info-card {
        background: #13151e;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 10px;
    }
    .info-card-title {
        font-size: 10px;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        margin-bottom: 6px;
    }
    .info-card-value { font-size: 20px; font-weight: 700; color: #f1f5f9; }

    /* ── Risk factors ── */
    .risk-factor {
        background: rgba(239,68,68,0.08);
        border-left: 2px solid #ef4444;
        border-radius: 0 4px 4px 0;
        padding: 7px 12px;
        margin: 4px 0;
        font-size: 12px;
        color: #fca5a5;
    }

    /* ── Page title ── */
    .page-title {
        font-size: 26px;
        font-weight: 800;
        background: linear-gradient(135deg, #7c3aed, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 3px;
        letter-spacing: -0.01em;
    }
    .page-subtitle {
        font-size: 13px;
        color: #475569;
        margin-bottom: 24px;
        letter-spacing: 0.01em;
    }

    /* ── Streamlit overrides ── */
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    div[data-testid="metric-container"] {
        background: #13151e;
        border: 1px solid rgba(124,58,237,0.15);
        border-top: 2px solid #7c3aed;
        border-radius: 0 0 10px 10px;
        padding: 16px;
    }
    .stTabs [data-baseweb="tab"] { font-weight: 600; font-size: 13px; letter-spacing: 0.02em; }
    .stButton > button { border-radius: 6px; font-weight: 600; font-size: 13px; }
    </style>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def section(title: str):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)


def insight_block(text: str, icon: str = "", variant: str = "default"):
    css_class = {
        "warning": "insight-card warning",
        "success": "insight-card success",
    }.get(variant, "insight-card")
    st.markdown(
        f'<div class="{css_class}"><span class="insight-text">{text}</span></div>',
        unsafe_allow_html=True,
    )


def seg_badge(segment: str) -> str:
    color = SEGMENT_COLORS.get(segment, "#9ca3af")
    return f'<span class="seg-badge" style="background:{color}">{segment}</span>'


def churn_badge(label: str) -> str:
    cls = {"High": "churn-high", "Medium": "churn-med", "Low": "churn-low"}.get(label, "churn-low")
    return f'<span class="{cls}">{label} Risk</span>'


def health_dot(status: str) -> str:
    ok = status == "ok"
    return f'<span class="{"dot-ok" if ok else "dot-err"}"></span>'
