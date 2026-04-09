"""
autoresearch.harness.runner

Wraps `opencode run --attach http://localhost:13568 --agent <name> --format json`.
Docs: https://opencode.ai
"""

import asyncio
import os
import signal
import subprocess
from dataclasses import dataclass


@dataclass
class AsyncResult:
    """Mirror of subprocess.CompletedProcess for async runs."""
    stdout: str
    stderr: str
    returncode: int


def _kill_process_group(pid: int) -> None:
    """Kill an entire process group. Falls back to single-process kill."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


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
            start_new_session=True,  # new process group for clean cleanup
        )

    async def run_async(
        self,
        agent: str,
        prompt: str,
        cwd: str | None = None,
    ) -> AsyncResult:
        """Run opencode agent asynchronously. Returns AsyncResult with NDJSON stdout."""
        cmd = [self.opencode_path, "run", "--attach", "http://localhost:13568", "--agent", agent, "--format", "json"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            start_new_session=True,  # new process group for clean cleanup
        )
        try:
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
            _kill_process_group(proc.pid)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                # Force kill if SIGTERM didn't work
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
            raise subprocess.TimeoutExpired(cmd, self.timeout)
        except BaseException:
            # Ensure cleanup on any unexpected error (e.g. CancelledError)
            if proc.returncode is None:
                _kill_process_group(proc.pid)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            raise
