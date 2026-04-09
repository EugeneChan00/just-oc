"""
autoresearch.harness.evaluator

LLM-as-judge evaluator. Sends agent response + sub-metric definitions
to an evaluator agent and parses 9 boolean results per category.
"""

import json
import re
import subprocess
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
        """Evaluate one category (9 sub-metrics) via LLM judge (sync).

        Returns {numeric_id: {"description": str, "result": bool | None}}.
        On evaluator failure, returns all False with error flag.
        """
        if not agent_response.strip():
            return self._all_false(sub_metric_defs, reason="empty_response")

        eval_prompt = self._build_eval_prompt(
            category, prompt_text, agent_response, parsed_events, sub_metric_defs
        )

        try:
            result = self.runner.run(agent=self.EVALUATOR_AGENT, prompt=eval_prompt)
            parsed = EventParser.parse(result.stdout)
            evaluator_text = parsed["text"]
        except subprocess.TimeoutExpired:
            return self._all_false(sub_metric_defs, reason="evaluator_timeout")
        except Exception:
            return self._all_false(sub_metric_defs, reason="evaluator_error")

        if not evaluator_text.strip():
            return self._all_false(sub_metric_defs, reason="evaluator_empty")

        return self._parse_eval_response(evaluator_text, sub_metric_defs)

    async def evaluate_category_async(
        self,
        category: str,
        prompt_text: str,
        agent_response: str,
        parsed_events: dict[str, Any],
        sub_metric_defs: list[dict],
    ) -> dict[str, dict]:
        """Evaluate one category (9 sub-metrics) via LLM judge (async)."""
        if not agent_response.strip():
            return self._all_false(sub_metric_defs, reason="empty_response")

        eval_prompt = self._build_eval_prompt(
            category, prompt_text, agent_response, parsed_events, sub_metric_defs
        )

        try:
            result = await self.runner.run_async(agent=self.EVALUATOR_AGENT, prompt=eval_prompt)
            parsed = EventParser.parse(result.stdout)
            evaluator_text = parsed["text"]
        except subprocess.TimeoutExpired:
            return self._all_false(sub_metric_defs, reason="evaluator_timeout")
        except Exception:
            return self._all_false(sub_metric_defs, reason="evaluator_error")

        if not evaluator_text.strip():
            return self._all_false(sub_metric_defs, reason="evaluator_empty")

        return self._parse_eval_response(evaluator_text, sub_metric_defs)

    def _build_eval_prompt(
        self,
        category: str,
        prompt_text: str,
        agent_response: str,
        parsed_events: dict,
        sub_metric_defs: list[dict],
    ) -> str:
        """Build the prompt sent to the evaluator agent."""
        metrics_block = json.dumps(
            [{"id": d["numeric_id"], "name": d["sub_metric"],
              "description": d["description"],
              "expected_outcome": d["expected_outcome"],
              "observable_behavior": d["observable_behavior"]}
             for d in sub_metric_defs],
            indent=2,
        )

        events_block = ""
        if category == "delegation" and parsed_events.get("task_calls"):
            events_block = f"\n## Task Delegations Observed\n```json\n{json.dumps(parsed_events['task_calls'], indent=2)}\n```\n"
        elif parsed_events.get("tool_calls"):
            tools_summary = [{"tool": t["tool"], "status": t["status"]} for t in parsed_events["tool_calls"]]
            events_block = f"\n## Tools Used\n```json\n{json.dumps(tools_summary, indent=2)}\n```\n"

        ids_example = ", ".join(f'"{d["numeric_id"]}": true' for d in sub_metric_defs)

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

Return ONLY a valid JSON object. Example format:
{{{ids_example}}}

Replace each true/false based on your evaluation. Output ONLY the JSON, no other text."""

    def _parse_eval_response(
        self,
        evaluator_text: str,
        sub_metric_defs: list[dict],
    ) -> dict[str, dict]:
        """Parse the evaluator agent's response into {numeric_id: {description, result}}."""
        booleans = {}

        # Try multiple extraction strategies
        # 1. Find JSON block (possibly with nested content)
        for pattern in [
            r"```json\s*(\{.*?\})\s*```",  # fenced JSON block
            r"```\s*(\{.*?\})\s*```",        # fenced block without json tag
            r"(\{[^{}]*\})",                  # simple non-nested braces
        ]:
            match = re.search(pattern, evaluator_text, re.DOTALL)
            if match:
                try:
                    booleans = json.loads(match.group(1))
                    break
                except json.JSONDecodeError:
                    continue

        # 2. If no regex match, try parsing the entire text as JSON
        if not booleans:
            try:
                booleans = json.loads(evaluator_text.strip())
            except json.JSONDecodeError:
                pass

        # Build result dict
        results = {}
        for d in sub_metric_defs:
            nid = d["numeric_id"]
            val = booleans.get(nid)
            if isinstance(val, bool):
                results[nid] = {"description": d["sub_metric"], "result": val}
            else:
                results[nid] = {"description": d["sub_metric"], "result": False}

        return results

    def _all_false(self, sub_metric_defs: list[dict], reason: str = "") -> dict[str, dict]:
        """Return all-false results (used when evaluator fails)."""
        return {
            d["numeric_id"]: {"description": d["sub_metric"], "result": False, "_reason": reason}
            for d in sub_metric_defs
        }
