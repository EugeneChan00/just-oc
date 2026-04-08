import streamlit as st


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
