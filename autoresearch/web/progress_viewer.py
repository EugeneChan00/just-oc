"""
autoresearch.web.progress_viewer

ProgressViewer component for displaying current round and latest score delta.
"""

import streamlit as st


class ProgressViewer:
    """Displays current round and latest score delta."""

    def render(self, round_num: int, score_delta: float, status: str) -> None:
        """
        Render round progress.

        Args:
            round_num: Current round number.
            score_delta: Score change from previous round.
            status: Status string ('running', 'improved', 'no_improvement', 'converged').
        """
        col1, col2 = st.columns(2)

        with col1:
            st.metric("Current Round", round_num)

        with col2:
            if status == "improved":
                delta_display = f"✓ +{score_delta:.3f}"
            elif status == "no_improvement":
                delta_display = f"✗ {score_delta:.3f}"
            elif status == "converged":
                delta_display = "✓ converged"
            else:
                delta_display = "..."

            st.metric("Score Delta", delta_display)


# Module-level function for backward compatibility
def render_progress(event: dict) -> None:
    """Render round progress (backward compatibility wrapper)."""
    viewer = ProgressViewer()

    if event.get("type") == "round_start":
        round_num = event.get("data", {}).get("round", "?")
        viewer.render(round_num, 0.0, "running")
    elif event.get("type") == "round_end":
        round_num = event.get("data", {}).get("round", "?")
        score = event.get("data", {}).get("score", 0)
        accepted = event.get("data", {}).get("accepted", False)
        delta = score - 0.0  # Would need previous score for accurate delta
        status = "improved" if accepted else "no_improvement"
        viewer.render(round_num, delta, status)
