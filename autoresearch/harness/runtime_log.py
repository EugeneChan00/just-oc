"""
autoresearch.harness.runtime_log

JSONL runtime logger. Records every opencode event during eval runs
for post-hoc analysis of agent behavior and optimization research.

Output: autoresearch/logs/<agent-name>/<run-id>.jsonl
Each line is one event with timestamp, event type, and payload.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RuntimeLog:
    """Append-only JSONL logger for eval runtime events."""

    def __init__(self, logs_dir: str | Path = "autoresearch/logs"):
        self.logs_dir = Path(logs_dir)
        self._file = None
        self._path = None

    def start(self, agent_name: str, run_id: str) -> Path:
        """Open a new log file for this eval run."""
        agent_dir = self.logs_dir / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)
        self._path = agent_dir / f"{run_id}.jsonl"
        self._file = open(self._path, "a")
        self._emit("run_start", {"agent_name": agent_name, "run_id": run_id})
        return self._path

    def close(self) -> None:
        """Flush and close the log file."""
        if self._file:
            self._emit("run_end", {})
            self._file.close()
            self._file = None

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Write one JSONL line."""
        if not self._file:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            "type": event_type,
            **data,
        }
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()

    def log_agent_run(
        self,
        agent_name: str,
        category: str,
        prompt_index: int,
        prompt_preview: str,
    ) -> None:
        """Log the start of an agent eval prompt run."""
        self._emit("agent_run_start", {
            "agent_name": agent_name,
            "category": category,
            "prompt_index": prompt_index,
            "prompt_preview": prompt_preview[:200],
        })

    def log_agent_response(
        self,
        agent_name: str,
        category: str,
        prompt_index: int,
        response_text: str,
        task_calls: list[dict],
        tool_calls: list[dict],
        tokens: dict | None,
        error: str | None,
        elapsed_seconds: float,
    ) -> None:
        """Log the agent's response and runtime events."""
        self._emit("agent_response", {
            "agent_name": agent_name,
            "category": category,
            "prompt_index": prompt_index,
            "response_preview": response_text[:500],
            "response_length": len(response_text),
            "task_calls_count": len(task_calls),
            "task_calls": [
                {"subagent_type": tc.get("subagent_type"), "description": tc.get("description")}
                for tc in task_calls
            ],
            "tool_calls_count": len(tool_calls),
            "tools_used": list({tc.get("tool") for tc in tool_calls}),
            "tokens": tokens,
            "error": error,
            "elapsed_seconds": round(elapsed_seconds, 2),
        })

    def log_eval_result(
        self,
        agent_name: str,
        category: str,
        prompt_index: int,
        eval_results: dict[str, dict],
        elapsed_seconds: float,
    ) -> None:
        """Log the evaluator's boolean verdicts."""
        passes = sum(1 for v in eval_results.values() if v.get("result") is True)
        total = len(eval_results)
        self._emit("eval_result", {
            "agent_name": agent_name,
            "category": category,
            "prompt_index": prompt_index,
            "passes": passes,
            "total": total,
            "results": {k: v.get("result") for k, v in eval_results.items()},
            "elapsed_seconds": round(elapsed_seconds, 2),
        })

    def log_raw_ndjson(self, agent_name: str, category: str, prompt_index: int, stdout: str) -> None:
        """Log the raw NDJSON output from opencode for post-hoc research."""
        self._emit("raw_ndjson", {
            "agent_name": agent_name,
            "category": category,
            "prompt_index": prompt_index,
            "stdout_length": len(stdout),
            "lines": stdout.strip().splitlines()[:50],  # cap at 50 lines
        })

    def log_scaffold(self, agent_name: str, scaffold_path: str) -> None:
        """Log scaffold creation."""
        self._emit("scaffold_created", {
            "agent_name": agent_name,
            "path": str(scaffold_path),
        })
