import streamlit as st


def render_metrics(event: dict) -> None:
    """Render live metrics dashboard."""
    if event.get("type") == "score_update":
        data = event.get("data", {})
        cols = st.columns(4)
        cols[0].metric("Composite", f"{data.get('composite', 0):.3f}")
        cols[1].metric("Standalone", f"{data.get('standalone', 0):.3f}")
        cols[2].metric("Composite-Ex", f"{data.get('composite_ex', 0):.3f}")
        cols[3].metric("Std Dev", f"{data.get('std', 0):.3f}")
