"""
autoresearch.harness.runner

Wraps `opencode run --agent <name> --format json`.
Docs: https://opencode.ai
"""

import subprocess


class Runner:
    """Thin subprocess wrapper for opencode CLI."""

    def __init__(self, opencode_path: str = "opencode", timeout: int = 300):
        self.opencode_path = opencode_path
        self.timeout = timeout

    def run(
        self,
        agent: str,
        prompt: str,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess:
        """Run opencode agent, return CompletedProcess with NDJSON stdout.

        Args:
            agent: Agent name (e.g., "ceo", "backend_developer_worker").
            prompt: The prompt to send to the agent via stdin.
            cwd: Working directory for the agent process (scaffold path).

        Returns:
            CompletedProcess with stdout containing NDJSON lines.
        """
        cmd = [self.opencode_path, "run", "--agent", agent, "--format", "json"]
        return subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            cwd=cwd,
        )
