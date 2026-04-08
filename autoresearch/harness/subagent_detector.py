"""
autoresearch.harness.subagent_detector

Parses runner output to detect which OpenCode subagent was selected for writing tasks.
"""

import json
import re
from typing import List, Optional


class SubagentDetector:
    """Detects which subagent was invoked from NDJSON output."""

    # Regex patterns for agent archetype detection
    PATTERNS = {
        "frontend-developer": re.compile(
            r"FRONTEND_DEVELOPER|frontend-developer", re.IGNORECASE
        ),
        "backend-developer": re.compile(
            r"BACKEND_DEVELOPER|backend-developer", re.IGNORECASE
        ),
        "test-engineer": re.compile(r"TEST_ENGINEER|test-engineer", re.IGNORECASE),
        "agentic-engineer": re.compile(
            r"AGENTIC_ENGINEER|agentic-engineer", re.IGNORECASE
        ),
        "business-analyst": re.compile(
            r"BUSINESS_ANALYST|business-analyst", re.IGNORECASE
        ),
        "researcher": re.compile(r"RESEARCHER|researcher", re.IGNORECASE),
        "quantitative-developer": re.compile(
            r"QUANTITATIVE_DEVELOPER|quantitative-developer", re.IGNORECASE
        ),
        "solution-architect": re.compile(
            r"SOLUTION_ARCHITECT|solution-architect", re.IGNORECASE
        ),
        "strategic-scoper": re.compile(
            r"STRATEGIC_SCOPER|strategic-scoper", re.IGNORECASE
        ),
        "architect": re.compile(r"ARCHITECT|architect", re.IGNORECASE),
        "verifier": re.compile(r"VERIFIER|verifier", re.IGNORECASE),
        "builder": re.compile(r"BUILDER|builder", re.IGNORECASE),
        "scoper": re.compile(r"SCOPER|scoper", re.IGNORECASE),
    }

    def __init__(self):
        """Initialize SubagentDetector with regex patterns."""
        self.patterns = self.PATTERNS.copy()

    def detect(self, ndjson_lines: List[str]) -> Optional[str]:
        """
        Parse NDJSON output and detect which subagent was invoked.

        Returns the first detected subagent name (e.g., 'backend-developer') or None.

        Args:
            ndjson_lines: List of NDJSON string lines from runner output.

        Returns:
            Subagent name string or None if no subagent detected.
        """
        for line in ndjson_lines:
            if not line:
                continue

            # Try to parse as JSON and look for agent_dispatch
            try:
                event = json.loads(line)
                if event.get("type") == "agent_dispatch":
                    agent = event.get("agent")
                    if agent:
                        return agent
            except json.JSONDecodeError:
                pass

            # Scan text content for archetype mentions
            for agent_name, pattern in self.patterns.items():
                if pattern.search(line):
                    return agent_name

        return None

    def detect_all(self, ndjson_lines: List[str]) -> List[str]:
        """
        Return all detected subagent invocations in order.

        Args:
            ndjson_lines: List of NDJSON string lines from runner output.

        Returns:
            List of detected subagent names in order of appearance.
        """
        detected = []

        for line in ndjson_lines:
            if not line:
                continue

            # Try to parse as JSON and look for agent_dispatch
            try:
                event = json.loads(line)
                if event.get("type") == "agent_dispatch":
                    agent = event.get("agent")
                    if agent and agent not in detected:
                        detected.append(agent)
                    continue
            except json.JSONDecodeError:
                pass

            # Scan text content for archetype mentions
            for agent_name, pattern in self.patterns.items():
                if pattern.search(line) and agent_name not in detected:
                    detected.append(agent_name)

        return detected
