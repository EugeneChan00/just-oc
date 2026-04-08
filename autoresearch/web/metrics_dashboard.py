"""
autoresearch.web.metrics_dashboard

MetricsDashboard component for showing live metrics.
"""

import streamlit as st


class MetricsDashboard:
    """Shows live composite/standalone/composite_ex/std metrics."""

    def update(
        self, composite: float, standalone: float, composite_ex: float, std: float
    ) -> None:
        """
        Update the metrics display.

        Args:
            composite: Composite score (0.0-1.0).
            standalone: Standalone score (0.0-1.0).
            composite_ex: Composite-ex score (0.0-1.0).
            std: Standard deviation (0.0-1.0).
        """
        cols = st.columns(4)
        cols[0].metric("Composite", f"{composite:.3f}")
        cols[1].metric("Standalone", f"{standalone:.3f}")
        cols[2].metric("Composite-Ex", f"{composite_ex:.3f}")
        cols[3].metric("Std Dev", f"{std:.3f}")


# Module-level function for backward compatibility
def render_metrics(event: dict) -> None:
    """Render live metrics dashboard (backward compatibility wrapper)."""
    dashboard = MetricsDashboard()

    if event.get("type") == "score_update":
        data = event.get("data", {})
        dashboard.update(
            composite=data.get("composite", 0),
            standalone=data.get("standalone", 0),
            composite_ex=data.get("composite_ex", 0),
            std=data.get("std", 0),
        )
