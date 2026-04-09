"""
autoresearch.harness.runner

Wraps `opencode run --attach http://localhost:13568 --agent <name> --format json`.
Docs: https://opencode.ai
"""

import asyncio
import subprocess
from dataclasses import dataclass


@dataclass
class AsyncResult:
    """Mirror of subprocess.CompletedProcess for async runs."""
    stdout: str
    stderr: str
    returncode: int


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
        """Run opencode agent synchronously. Returns CompletedProcess with NDJSON stdout."""
        cmd = [self.opencode_path, "run", "--attach", "http://localhost:13568", "--agent", agent, "--format", "json"]
        return subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            cwd=cwd,
        )

    async def run_async(
        self,
        agent: str,
        prompt: str,
        cwd: str | None = None,
    ) -> AsyncResult:
        """Run opencode agent asynchronously. Returns AsyncResult with NDJSON stdout."""
        cmd = [self.opencode_path, "run", "--attach", "http://localhost:13568", "--agent", agent, "--format", "json"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=prompt.encode()),
                timeout=self.timeout,
            )
            return AsyncResult(
                stdout=stdout_bytes.decode() if stdout_bytes else "",
                stderr=stderr_bytes.decode() if stderr_bytes else "",
                returncode=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise subprocess.TimeoutExpired(cmd, self.timeout)
