import streamlit as st
import json
from datetime import datetime

EVENT_COLORS = {
    "round_start": "blue",
    "round_end": "green",
    "eval_prompt": "orange",
    "score": "purple",
    "error": "red",
    "info": "gray",
}


def render_log(event: dict, auto_scroll: bool = True) -> None:
    """Render a single event in the log."""
    event_type = event.get("type", "unknown")
    timestamp = event.get("timestamp", datetime.now().isoformat())
    color = EVENT_COLORS.get(event_type, "black")

    with st.container():
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(
                f"<span style='color:{color}'>●</span> `{event_type}`",
                unsafe_allow_html=True,
            )
        with col2:
            st.text(f"[{timestamp}] {json.dumps(event.get('data', {}), indent=2)}")

        if event_type == "eval_prompt":
            st.code(event.get("data", {}).get("prompt", ""), language="text")

        st.divider()


def render_progress(event: dict) -> None:
    """Render round progress."""
    if event.get("type") == "round_start":
        round_num = event.get("data", {}).get("round", "?")
        st.metric("Current Round", round_num)
    elif event.get("type") == "round_end":
        score = event.get("data", {}).get("score", 0)
        accepted = event.get("data", {}).get("accepted", False)
        st.metric(
            "Latest Score",
            f"{score:.3f}",
            delta="✓ improved" if accepted else "✗ no improvement",
        )


def render_metrics(event: dict) -> None:
    """Render live metrics dashboard."""
    if event.get("type") == "score_update":
        data = event.get("data", {})
        cols = st.columns(4)
        cols[0].metric("Composite", f"{data.get('composite', 0):.3f}")
        cols[1].metric("Standalone", f"{data.get('standalone', 0):.3f}")
        cols[2].metric("Composite-Ex", f"{data.get('composite_ex', 0):.3f}")
        cols[3].metric("Std Dev", f"{data.get('std', 0):.3f}")
