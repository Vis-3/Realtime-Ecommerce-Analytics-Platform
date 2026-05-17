import streamlit as st


def kpi_card(label: str, value: str, delta: float = None, prefix: str = "", suffix: str = ""):
    """Render a single styled KPI card."""
    if delta is not None:
        if delta > 0:
            delta_html = f'<div class="kpi-delta-pos">▲ {delta:+.1f}%</div>'
        elif delta < 0:
            delta_html = f'<div class="kpi-delta-neg">▼ {delta:.1f}%</div>'
        else:
            delta_html = f'<div class="kpi-delta-neu">— 0.0%</div>'
    else:
        delta_html = ""

    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{prefix}{value}{suffix}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def kpi_row(metrics: list[dict]):
    """
    Render a horizontal row of KPI cards.
    Each dict: {label, value, delta=None, prefix="", suffix=""}
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            kpi_card(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
                prefix=m.get("prefix", ""),
                suffix=m.get("suffix", ""),
            )
    st.markdown("<br>", unsafe_allow_html=True)


def info_card(label: str, value: str):
    st.markdown(f"""
    <div class="info-card">
        <div class="info-card-title">{label}</div>
        <div class="info-card-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)


def unavailable(message: str = "Data unavailable"):
    st.warning(f"⚠ {message} — API may be down or returning no data.")
