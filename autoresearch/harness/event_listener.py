"""
autoresearch.harness.event_listener

Parses OpenCode NDJSON stdout into structured events.
OpenCode v1.4.0 emits: step_start, tool_use, text, step_finish, error.
Docs: https://opencode.ai
"""

import json
from typing import Any


class EventParser:
    """Parse OpenCode NDJSON stdout into structured events."""

    @staticmethod
    def parse(stdout: str) -> dict[str, Any]:
        """Parse NDJSON stdout from `opencode run --format json`.

        Returns:
            {
                "text": str,                  # concatenated agent text response
                "task_calls": list[dict],      # task tool dispatches (delegation)
                "tool_calls": list[dict],      # all other tool calls
                "tokens": dict | None,         # token usage from final step_finish
                "error": str | None,           # error message if any
            }
        """
        text_parts: list[str] = []
        task_calls: list[dict] = []
        tool_calls: list[dict] = []
        tokens: dict | None = None
        error: str | None = None

        for line in stdout.strip().splitlines():
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type")
            part = event.get("part", {})

            if etype == "text":
                text_parts.append(part.get("text", ""))

            elif etype == "tool_use":
                tool = part.get("tool", "")
                state = part.get("state", {})
                inp = state.get("input", {})
                out = state.get("output", "")
                meta = state.get("metadata", {})

                if tool == "task":
                    task_calls.append({
                        "subagent_type": inp.get("subagent_type", "").replace("-", "_"),
                        "description": inp.get("description", ""),
                        "prompt": inp.get("prompt", ""),
                        "output": out,
                        "session_id": meta.get("sessionId", ""),
                        "status": state.get("status", ""),
                    })
                else:
                    tool_calls.append({
                        "tool": tool,
                        "input": inp,
                        "output": out,
                        "status": state.get("status", ""),
                    })

            elif etype == "step_finish":
                if part.get("reason") == "stop":
                    tokens = part.get("tokens")

            elif etype == "error":
                err = event.get("error", {})
                error = err.get("data", {}).get("message", err.get("name", "unknown error"))

        return {
            "text": "".join(text_parts),
            "task_calls": task_calls,
            "tool_calls": tool_calls,
            "tokens": tokens,
            "error": error,
        }
