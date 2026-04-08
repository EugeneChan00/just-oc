"""
autoresearch.harness.evaluator

LLM-as-judge evaluator. Sends agent response + sub-metric definitions
to an evaluator agent and parses 9 boolean results per category.
"""

import json
import re
from typing import Any

from autoresearch.harness.runner import Runner
from autoresearch.harness.event_listener import EventParser


class Evaluator:
    """Thin wrapper that calls an OpenCode evaluator agent as LLM-judge."""

    EVALUATOR_AGENT = "evaluator"

    def __init__(self, runner: Runner):
        self.runner = runner

    def evaluate_category(
        self,
        category: str,
        prompt_text: str,
        agent_response: str,
        parsed_events: dict[str, Any],
        sub_metric_defs: list[dict],
    ) -> dict[str, dict]:
        """Evaluate one category (9 sub-metrics) via LLM judge.

        Args:
            category: "accuracy", "rejection", or "delegation"
            prompt_text: The eval prompt that was sent to the agent
            agent_response: The agent's text response
            parsed_events: Output from EventParser.parse() (task_calls, tool_calls)
            sub_metric_defs: 9 sub-metric definitions with numeric_id, description, etc.

        Returns:
            {numeric_id: {"description": str, "result": bool | None}}
        """
        eval_prompt = self._build_eval_prompt(
            category, prompt_text, agent_response, parsed_events, sub_metric_defs
        )
        result = self.runner.run(agent=self.EVALUATOR_AGENT, prompt=eval_prompt)
        parsed = EventParser.parse(result.stdout)
        return self._parse_eval_response(parsed["text"], sub_metric_defs)

    def _build_eval_prompt(
        self,
        category: str,
        prompt_text: str,
        agent_response: str,
        parsed_events: dict,
        sub_metric_defs: list[dict],
    ) -> str:
        """Build the prompt sent to the evaluator agent."""
        # Format sub-metric definitions
        metrics_block = json.dumps(
            [{"id": d["numeric_id"], "name": d["sub_metric"],
              "description": d["description"],
              "expected_outcome": d["expected_outcome"],
              "observable_behavior": d["observable_behavior"]}
             for d in sub_metric_defs],
            indent=2,
        )

        # Include delegation events for delegation category
        events_block = ""
        if category == "delegation" and parsed_events.get("task_calls"):
            events_block = f"\n## Task Delegations Observed\n```json\n{json.dumps(parsed_events['task_calls'], indent=2)}\n```\n"
        elif parsed_events.get("tool_calls"):
            tools_summary = [{"tool": t["tool"], "status": t["status"]} for t in parsed_events["tool_calls"]]
            events_block = f"\n## Tools Used\n```json\n{json.dumps(tools_summary, indent=2)}\n```\n"

        return f"""You are an evaluation judge. Evaluate the agent's response against {len(sub_metric_defs)} sub-metrics for the "{category}" category.

## Original Prompt Sent to Agent
{prompt_text[:3000]}

## Agent's Response
{agent_response[:5000]}
{events_block}
## Sub-Metrics to Evaluate
{metrics_block}

## Instructions
For each sub-metric, determine if the agent's response PASSES (true) or FAILS (false).
Return ONLY a JSON object mapping each numeric ID to a boolean:

```json
{{{", ".join(f'"{d["numeric_id"]}": true' for d in sub_metric_defs)}}}
```

Replace true/false based on your evaluation. Return ONLY the JSON object, nothing else."""

    def _parse_eval_response(
        self,
        evaluator_text: str,
        sub_metric_defs: list[dict],
    ) -> dict[str, dict]:
        """Parse the evaluator agent's response into {numeric_id: {description, result}}."""
        # Try to extract JSON from the response
        booleans = {}
        json_match = re.search(r"\{[^{}]*\}", evaluator_text, re.DOTALL)
        if json_match:
            try:
                booleans = json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Build result dict with defaults
        results = {}
        for d in sub_metric_defs:
            nid = d["numeric_id"]
            val = booleans.get(nid)
            if isinstance(val, bool):
                results[nid] = {"description": d["sub_metric"], "result": val}
            else:
                results[nid] = {"description": d["sub_metric"], "result": False}

        return results
