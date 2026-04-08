"""
autoresearch.harness.event_listener

Tracks tool calls during agent execution.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ToolCall:
    """Represents a single tool call event from the agent."""

    tool_name: str
    arguments: dict
    result: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class EventListener:
    """Tracks and parses tool call events from NDJSON output."""

    def __init__(self):
        """Initialize EventListener with empty tool call history."""
        self.tool_calls: List[ToolCall] = []

    def reset(self) -> None:
        """Clear accumulated events."""
        self.tool_calls.clear()

    def parse_stream(self, ndjson_lines: List[str]) -> List[ToolCall]:
        """
        Parse NDJSON lines from runner output.

        Extracts tool_name, arguments, result from each event.
        Returns list of ToolCall objects.

        Args:
            ndjson_lines: List of NDJSON string lines from runner output.

        Returns:
            List of ToolCall objects parsed from the stream.

        Note:
            NDJSON event shape assumed:
            {"type": "tool_call", "tool": "read", "args": {"filePath": "foo.py"}, "result": "..."}
            {"type": "tool_call", "tool": "write", "args": {"content": "..."}, "result": null}
            {"type": "agent_turn", "content": "..."}
        """
        parsed = []
        for line in ndjson_lines:
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") == "tool_call":
                tool_name = event.get("tool", "")
                args = event.get("args", {})
                result = event.get("result")
                timestamp = event.get("timestamp", time.time())

                tool_call = ToolCall(
                    tool_name=tool_name,
                    arguments=args,
                    result=result,
                    timestamp=timestamp,
                )
                parsed.append(tool_call)
                self.tool_calls.append(tool_call)

        return parsed

    def get_tool_frequency(self) -> Dict[str, int]:
        """
        Returns {tool_name: count} for all tracked calls.

        Returns:
            Dictionary mapping tool names to their call counts.
        """
        freq: Dict[str, int] = {}
        for tc in self.tool_calls:
            freq[tc.tool_name] = freq.get(tc.tool_name, 0) + 1
        return freq

    def get_tools_used(self) -> List[str]:
        """
        Returns unique tool names used.

        Returns:
            List of unique tool names in order of first use.
        """
        seen = set()
        tools = []
        for tc in self.tool_calls:
            if tc.tool_name not in seen:
                seen.add(tc.tool_name)
                tools.append(tc.tool_name)
        return tools
