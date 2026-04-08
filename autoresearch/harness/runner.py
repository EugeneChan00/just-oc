"""
autoresearch.harness.runner

Wraps `opencode run --agent <name> --format json`.
"""

import json
import subprocess
from typing import Generator, Optional


class Runner:
    """Runner wraps opencode binary invocation for agent evaluation."""

    def __init__(self, opencode_path: str = "opencode"):
        """
        Initialize Runner with opencode binary path.

        Args:
            opencode_path: Path to opencode binary. Default "opencode".
        """
        self.opencode_path = opencode_path

    def run(
        self,
        agent: str,
        prompt: str,
        format: str = "json",
    ) -> subprocess.CompletedProcess:
        """
        Run opencode with the given agent and prompt.

        Args:
            agent: Agent name to run (e.g., "backend-developer").
            prompt: The prompt/question to send to the agent.
            format: Output format. Default "json" (NDJSON).

        Returns:
            subprocess.CompletedProcess with stdout containing NDJSON output.

        Raises:
            FileNotFoundError: If opencode binary not found.
            subprocess.CalledProcessError: If opencode returns non-zero exit.
        """
        cmd = [
            self.opencode_path,
            "run",
            "--agent",
            agent,
            "--format",
            format,
        ]
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result

    def run_streaming(
        self,
        agent: str,
        prompt: str,
    ) -> Generator[dict, None, None]:
        """
        Run opencode and yield parsed JSON objects as they arrive.

        NDJSON: one JSON object per line.

        Args:
            agent: Agent name to run.
            prompt: The prompt/question to send.

        Yields:
            dict: Parsed JSON objects from NDJSON output stream.

        Raises:
            FileNotFoundError: If opencode binary not found.
        """
        cmd = [
            self.opencode_path,
            "run",
            "--agent",
            agent,
            "--format",
            "json",
        ]
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, _ = process.communicate(input=prompt, timeout=60)

        for line in stdout.strip().split("\n"):
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
