import streamlit as st
from event_client import EventClient
from log_viewer import render_log
from progress_viewer import render_progress
from metrics_dashboard import render_metrics


def main():
    st.set_page_config(page_title="AutoResearch Event Viewer")

    st.header("AutoResearch Real-Time Event Viewer")

    # Connection config
    col1, col2 = st.columns([3, 1])
    with col1:
        event_url = st.text_input("Event stream URL", "http://localhost:8000/events")
    with col2:
        auto_scroll = st.checkbox("Auto-scroll", value=True)

    # Metrics summary
    metrics_placeholder = st.empty()

    # Round progress
    progress_placeholder = st.empty()

    # Event log
    st.header("Event Log")
    log_placeholder = st.empty()

    # Connect and stream
    client = EventClient(event_url)
    for event in client.stream():
        # Update metrics
        metrics_placeholder.write(render_metrics(event))

        # Update progress
        progress_placeholder.write(render_progress(event))

        # Update log
        with log_placeholder.container():
            render_log(event, auto_scroll=auto_scroll)


if __name__ == "__main__":
    main()
