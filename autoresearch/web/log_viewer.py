"""
autoresearch.web.log_viewer

LogViewer component for rendering individual events with color-coded types.
"""

import streamlit as st
import json
from datetime import datetime


# Event type to color mapping
EVENT_COLORS = {
    "round_start": "blue",
    "round_end": "green",
    "eval_prompt": "orange",
    "score_update": "purple",
    "score": "purple",
    "error": "red",
    "info": "gray",
}


class LogViewer:
    """Renders individual events with color-coded types."""

    def render_event(self, event: dict) -> None:
        """
        Render a single event in the log.

        Args:
            event: Event dict with 'type', 'timestamp', and 'data' fields.
        """
        event_type = event.get("type", "unknown")
        timestamp = event.get("timestamp", datetime.now().isoformat())
        color = EVENT_COLORS.get(event_type, "black")
        data = event.get("data", {})

        with st.container():
            col1, col2 = st.columns([1, 4])
            with col1:
                st.markdown(
                    f"<span style='color:{color}'>●</span> `{event_type}`",
                    unsafe_allow_html=True,
                )
            with col2:
                st.text(f"[{timestamp}] {json.dumps(data, indent=2)}")

            if event_type == "eval_prompt":
                st.code(data.get("prompt", ""), language="text")

            st.divider()


# Module-level function for backward compatibility
def render_log(event: dict, auto_scroll: bool = True) -> None:
    """Render a single event in the log (backward compatibility wrapper)."""
    viewer = LogViewer()
    viewer.render_event(event)
