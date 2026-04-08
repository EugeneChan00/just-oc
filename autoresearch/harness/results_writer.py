"""
autoresearch.harness.results_writer

Writes eval results to JSONL per autoresearch/results/eval_schema.md.
Each line: {run_id, agent_name, timestamp, "1.1.1": {description, result}, ...}
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ResultsWriter:
    """Append eval results to per-agent JSONL files."""

    def __init__(self, results_dir: str | Path = "autoresearch/results"):
        self.results_dir = Path(results_dir)

    def write(self, agent_name: str, run_id: str, eval_results: dict[str, dict]) -> Path:
        """Append one JSONL record to results/<agent-name>/results.jsonl.

        Args:
            agent_name: Agent that was evaluated.
            run_id: Run identifier (e.g., "run-001-1").
            eval_results: {numeric_id: {"description": str, "result": bool | None}}.

        Returns:
            Path to the results file.
        """
        agent_dir = self.results_dir / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)
        results_file = agent_dir / "results.jsonl"

        record = {
            "run_id": run_id,
            "agent_name": agent_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **eval_results,
        }

        with open(results_file, "a") as f:
            f.write(json.dumps(record) + "\n")

        return results_file

    def read_all(self, agent_name: str) -> list[dict[str, Any]]:
        """Read all records for an agent."""
        results_file = self.results_dir / agent_name / "results.jsonl"
        if not results_file.exists():
            return []
        records = []
        for line in results_file.read_text().strip().splitlines():
            if line:
                records.append(json.loads(line))
        return records
