"""
autoresearch.harness.spec_reader

Reads per-agent eval spec JSONs and maps sub-metrics to numeric IDs.
Spec path: autoresearch/agents/<agent-name>/spec/{accuracy,rejection,delegation}.json
"""

import json
from pathlib import Path
from typing import Any

AGENTS_DIR = Path("autoresearch/agents")
CATEGORIES = ["accuracy", "rejection", "delegation"]

CATEGORY_IDS = {"accuracy": 1, "rejection": 2, "delegation": 3}

METRIC_ORDER: dict[str, list[str]] = {
    "accuracy": ["factual_correctness", "instruction_following", "reasoning_quality"],
    "rejection": ["legitimate_rejection", "over_rejection", "rejection_quality"],
    "delegation": ["correct_delegation", "handoff_quality", "pipeline_adherence"],
}

SUB_METRIC_ORDER: dict[str, list[str]] = {
    "factual_correctness": ["fact_accuracy", "source_citation", "uncertainty_acknowledgment"],
    "instruction_following": ["constraint_adherence", "scope_completion", "denied_constraint_respect"],
    "reasoning_quality": ["logical_coherence", "fallacy_absence", "proportionality"],
    "legitimate_rejection": ["harmful_request_refusal", "policy_violation_refusal", "unjustified_content_refusal"],
    "over_rejection": ["benign_request_acceptance", "clarification_asking", "minor_uncertainty_handling"],
    "rejection_quality": ["clarity_and_directness", "alternative_suggestion", "consistency"],
    "correct_delegation": ["specialist_routing", "direct_handling", "lane_boundary_respect"],
    "handoff_quality": ["context_provision", "intent_clarity", "result_synthesis"],
    "pipeline_adherence": ["stage_sequence_respect", "role_absorption_prevention", "entry_point_routing"],
}


def build_numeric_id(category: str, metric: str, sub_metric: str) -> str:
    """Map (category, metric, sub_metric) to numeric ID like '1.1.1'."""
    cat_id = CATEGORY_IDS[category]
    met_id = METRIC_ORDER[category].index(metric) + 1
    sub_id = SUB_METRIC_ORDER[metric].index(sub_metric) + 1
    return f"{cat_id}.{met_id}.{sub_id}"


def all_numeric_ids() -> list[str]:
    """Return all 27 numeric IDs in order (1.1.1 through 3.3.3)."""
    ids = []
    for cat in CATEGORIES:
        for metric in METRIC_ORDER[cat]:
            for sub in SUB_METRIC_ORDER[metric]:
                ids.append(build_numeric_id(cat, metric, sub))
    return ids


class SpecReader:
    """Read eval spec JSONs for agents."""

    def __init__(self, agents_dir: Path | str = AGENTS_DIR):
        self.agents_dir = Path(agents_dir)

    def _spec_path(self, agent_name: str, category: str) -> Path:
        return self.agents_dir / agent_name / "spec" / f"{category}.json"

    def load_spec(self, agent_name: str, category: str) -> dict[str, Any]:
        """Load a single spec JSON. Raises FileNotFoundError if missing."""
        path = self._spec_path(agent_name, category)
        with open(path) as f:
            return json.load(f)

    def load_agent_specs(self, agent_name: str) -> dict[str, dict]:
        """Load all 3 spec JSONs for an agent. Returns {category: spec_data}."""
        return {cat: self.load_spec(agent_name, cat) for cat in CATEGORIES}

    def get_prompts(self, agent_name: str, category: str) -> list[dict]:
        """Return the 10 prompts for a specific agent+category."""
        spec = self.load_spec(agent_name, category)
        return spec.get("prompts", [])

    def get_sub_metric_definitions(self, agent_name: str, category: str) -> list[dict]:
        """Return 9 sub-metric definitions with their numeric IDs.

        Each item: {numeric_id, metric, sub_metric, description, expected_outcome, observable_behavior}
        """
        spec = self.load_spec(agent_name, category)
        defs = []
        for metric_name in METRIC_ORDER[category]:
            metric_data = spec.get("metrics", {}).get(metric_name, {})
            sub_metrics = metric_data.get("sub_metrics", {})
            for sub_name in SUB_METRIC_ORDER[metric_name]:
                sub_data = sub_metrics.get(sub_name, {})
                defs.append({
                    "numeric_id": build_numeric_id(category, metric_name, sub_name),
                    "metric": metric_name,
                    "sub_metric": sub_name,
                    "description": sub_data.get("description", ""),
                    "expected_outcome": sub_data.get("expected_outcome", ""),
                    "observable_behavior": sub_data.get("observable_behavior", ""),
                })
        return defs

    def list_agents(self) -> list[str]:
        """List all agent names that have spec directories."""
        agents = []
        for p in sorted(self.agents_dir.iterdir()):
            if p.is_dir() and (p / "spec").is_dir() and p.name != "schema":
                agents.append(p.name)
        return agents
