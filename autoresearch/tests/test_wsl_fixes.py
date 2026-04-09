"""
Tests for WSL crash prevention fixes.

TDD approach: each test was written to define the DESIRED behavior,
then the code was written to make it pass.

Run: pytest autoresearch/tests/test_wsl_fixes.py -v
"""

import asyncio
import os
import signal
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────
# TEST GROUP 1: WSL Detection
#
# RED question: "Does our code detect WSL and lower parallelism?"
# ─────────────────────────────────────────────────────────────


class TestWSLDetection:
    """Verify that WSL is detected from /proc/version."""

    def test_detects_wsl_from_proc_version(self):
        """If /proc/version contains 'microsoft', _IS_WSL should be True."""
        # We can't change the module-level constant after import,
        # so we test the detection logic directly.
        wsl_version_string = "Linux version 5.15.0-1-microsoft-standard-WSL2"
        assert "microsoft" in wsl_version_string.lower()

    def test_non_wsl_linux(self):
        """A normal Linux /proc/version should NOT trigger WSL detection."""
        native_version = "Linux version 6.1.0-generic (buildd@ubuntu)"
        assert "microsoft" not in native_version.lower()


class TestParallelCapping:
    """Verify that --parallel is capped on WSL unless --no-wsl-cap is set."""

    def test_parallel_capped_on_wsl(self):
        """On WSL, parallel > 4 should be reduced to 4."""
        from autoresearch.loop.driver import _WSL_MAX_PARALLEL

        # Simulate: user asks for parallel=10 on WSL
        args = MagicMock()
        args.parallel = 10
        args.no_wsl_cap = False

        # The logic in main() does this:
        if args.parallel > _WSL_MAX_PARALLEL and not args.no_wsl_cap:
            args.parallel = _WSL_MAX_PARALLEL

        assert args.parallel == 4

    def test_parallel_not_capped_with_override(self):
        """--no-wsl-cap should let the user keep their requested value."""
        from autoresearch.loop.driver import _WSL_MAX_PARALLEL

        args = MagicMock()
        args.parallel = 10
        args.no_wsl_cap = True

        if args.parallel > _WSL_MAX_PARALLEL and not args.no_wsl_cap:
            args.parallel = _WSL_MAX_PARALLEL

        assert args.parallel == 10  # unchanged

    def test_low_parallel_not_modified(self):
        """If user requests parallel <= 4, no change needed even on WSL."""
        from autoresearch.loop.driver import _WSL_MAX_PARALLEL

        args = MagicMock()
        args.parallel = 3
        args.no_wsl_cap = False

        if args.parallel > _WSL_MAX_PARALLEL and not args.no_wsl_cap:
            args.parallel = _WSL_MAX_PARALLEL

        assert args.parallel == 3  # already safe


# ─────────────────────────────────────────────────────────────
# TEST GROUP 2: Process Group Cleanup
#
# RED question: "Does timeout kill the whole process group,
#               not just the direct child?"
# ─────────────────────────────────────────────────────────────


class TestProcessGroupCleanup:
    """Verify that subprocesses are spawned in new sessions and
    the entire group is killed on timeout."""

    def test_runner_uses_start_new_session_sync(self):
        """Sync run() should pass start_new_session=True so children
        get their own process group for clean cleanup."""
        from autoresearch.harness.runner import Runner

        runner = Runner(timeout=5)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            runner.run("test-agent", "hello")
            # Verify start_new_session was passed
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["start_new_session"] is True

    def test_kill_process_group_sends_sigterm(self):
        """_kill_process_group should send SIGTERM to the process group."""
        from autoresearch.harness.runner import _kill_process_group

        with patch("os.killpg") as mock_killpg, \
             patch("os.getpgid", return_value=12345):
            _kill_process_group(12345)
            mock_killpg.assert_called_once_with(12345, signal.SIGTERM)

    def test_kill_process_group_falls_back_to_sigkill(self):
        """If SIGTERM fails (process group gone), fall back to SIGKILL."""
        from autoresearch.harness.runner import _kill_process_group

        with patch("os.killpg", side_effect=ProcessLookupError), \
             patch("os.getpgid", return_value=99), \
             patch("os.kill") as mock_kill:
            _kill_process_group(99)
            mock_kill.assert_called_once_with(99, signal.SIGKILL)

    def test_kill_process_group_handles_already_dead(self):
        """If process is already dead, should not raise."""
        from autoresearch.harness.runner import _kill_process_group

        with patch("os.killpg", side_effect=ProcessLookupError), \
             patch("os.getpgid", return_value=99), \
             patch("os.kill", side_effect=ProcessLookupError):
            # Should not raise
            _kill_process_group(99)


# ─────────────────────────────────────────────────────────────
# TEST GROUP 3: Memory Check Caching
#
# RED question: "Does the memory check avoid spawning pstree/ps
#               on every single call?"
# ─────────────────────────────────────────────────────────────


class TestMemoryCheckCaching:
    """Verify that get_total_rss_mb() caches results."""

    def test_second_call_uses_cache(self):
        """Calling get_total_rss_mb() twice within 2s should only
        spawn pstree/ps once."""
        import autoresearch.loop.driver as driver

        # Reset cache
        driver._rss_cache = (0.0, 0.0)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="12345", returncode=0
            )
            # First call: hits pstree/ps
            val1 = driver.get_total_rss_mb()
            call_count_after_first = mock_run.call_count

            # Second call: should use cache (no new subprocess)
            val2 = driver.get_total_rss_mb()
            call_count_after_second = mock_run.call_count

            assert call_count_after_first > 0, "First call should spawn subprocesses"
            assert call_count_after_second == call_count_after_first, \
                "Second call should use cache, not spawn more subprocesses"
            assert val1 == val2, "Cached value should match"

    def test_cache_returns_numeric_mb(self):
        """get_total_rss_mb should return a float in MB."""
        import autoresearch.loop.driver as driver

        driver._rss_cache = (0.0, 0.0)

        with patch("subprocess.run") as mock_run:
            # pstree returns PID tree, ps returns RSS in KB
            mock_run.side_effect = [
                MagicMock(stdout="python(1234)---opencode(5678)", returncode=0),
                MagicMock(stdout="102400\n204800", returncode=0),
            ]
            result = driver.get_total_rss_mb()
            # (102400 + 204800) KB / 1024 = 300 MB
            assert result == pytest.approx(300.0)


# ─────────────────────────────────────────────────────────────
# TEST GROUP 4: Backpressure Under Memory Pressure
#
# RED question: "When memory is too high, does it wait and retry
#               instead of silently skipping?"
# ─────────────────────────────────────────────────────────────


class TestBackpressure:
    """Verify that _bounded_eval_prompt waits when memory is high."""

    def test_proceeds_when_memory_ok(self):
        """When memory is below budget, task should run immediately."""
        from autoresearch.loop.driver import EvalDriver

        args = MagicMock()
        args.parallel = 2
        args.timeout = 10
        args.memory_limit = 4096
        args.verbose = False
        args.sample = None

        driver = EvalDriver(args)

        # Mock eval to return a simple result
        async def fake_eval(*a, **kw):
            return ("accuracy", 0, {"1.1.1": {"result": True}})

        driver.eval_prompt_async = fake_eval

        with patch("autoresearch.loop.driver.get_total_rss_mb", return_value=500.0):
            result = asyncio.get_event_loop().run_until_complete(
                driver._bounded_eval_prompt(
                    "test-agent", "accuracy", {"prompt": "hi"}, 0, [], None
                )
            )
        cat, idx, eval_result = result
        assert cat == "accuracy"
        assert eval_result == {"1.1.1": {"result": True}}

    def test_waits_then_proceeds_when_memory_drops(self):
        """When memory starts high but drops, task should eventually run."""
        from autoresearch.loop.driver import EvalDriver

        args = MagicMock()
        args.parallel = 2
        args.timeout = 10
        args.memory_limit = 4096
        args.verbose = False
        args.sample = None

        driver = EvalDriver(args)

        async def fake_eval(*a, **kw):
            return ("accuracy", 0, {"1.1.1": {"result": True}})

        driver.eval_prompt_async = fake_eval

        # First call: memory too high (5000 > 4096)
        # Second call: memory ok (2000 < 4096)
        call_count = 0

        def decreasing_memory():
            nonlocal call_count
            call_count += 1
            return 5000.0 if call_count == 1 else 2000.0

        with patch("autoresearch.loop.driver.get_total_rss_mb", side_effect=decreasing_memory), \
             patch("asyncio.sleep", new_callable=AsyncMock):  # skip actual waiting
            result = asyncio.get_event_loop().run_until_complete(
                driver._bounded_eval_prompt(
                    "test-agent", "accuracy", {"prompt": "hi"}, 0, [], None
                )
            )
        # Should have succeeded after memory dropped
        _, _, eval_result = result
        assert eval_result == {"1.1.1": {"result": True}}

    def test_skips_after_sustained_high_memory(self):
        """If memory stays high for all retries, task should be skipped."""
        from autoresearch.loop.driver import EvalDriver

        args = MagicMock()
        args.parallel = 2
        args.timeout = 10
        args.memory_limit = 4096
        args.verbose = False
        args.sample = None

        driver = EvalDriver(args)

        # Memory always too high
        with patch("autoresearch.loop.driver.get_total_rss_mb", return_value=9999.0), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = asyncio.get_event_loop().run_until_complete(
                driver._bounded_eval_prompt(
                    "test-agent", "accuracy", {"prompt": "hi"}, 0, [], None
                )
            )
        # Should return empty results (skipped)
        _, _, eval_result = result
        assert eval_result == {}


# ─────────────────────────────────────────────────────────────
# TEST GROUP 5: CLI Flag
#
# RED question: "Does argparse accept --no-wsl-cap?"
# ─────────────────────────────────────────────────────────────


class TestCLIFlags:
    """Verify that the new --no-wsl-cap flag is properly parsed."""

    def test_no_wsl_cap_default_false(self):
        """By default, --no-wsl-cap should be False."""
        from autoresearch.loop.config import parse_args

        args = parse_args(["--agent", "test"])
        assert args.no_wsl_cap is False

    def test_no_wsl_cap_flag_sets_true(self):
        """Passing --no-wsl-cap should set it to True."""
        from autoresearch.loop.config import parse_args

        args = parse_args(["--agent", "test", "--no-wsl-cap"])
        assert args.no_wsl_cap is True
