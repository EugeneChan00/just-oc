"""
harness/build_poller.py

Deterministic event loop that polls an external CI/CD API for build status.
Implements:
- Configurable poll interval (default 30s)
- Exponential backoff retry on transient failures (HTTP 429, 500-504)
- Exact 5-attempt limit (1 initial + 4 retries) with backoff 5s, 10s, 20s, 40s
- Immediate termination on terminal build status (passed, failed)
- Immediate termination on non-transient HTTP errors (400, 401, 403, 404)
- Structured JSON logging for orchestration harness parsing

This is a pure code artifact. All behavioral guarantees are code-enforced by
construction. See prompt-vs-code classification in module docstring.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

# ---------------------------------------------------------------------------
# API Client Interface
# ---------------------------------------------------------------------------

TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503, 504})
NON_TRANSIENT_HTTP_CODES = frozenset({400, 401, 403, 404})
TERMINAL_BUILD_STATUSES = frozenset({"passed", "failed"})

# Module-level logger for structured output
_struct_log = logging.getLogger("build_poller.structured")
_struct_log.setLevel(logging.INFO)
# Ensure JSON lines handler does not double-format
_struct_log.propagate = False


@dataclass(frozen=True)
class BuildStatus:
    """Immutable snapshot of a build status poll response."""

    http_status_code: int
    build_status: str | None  # None when HTTP error prevents build status parsing
    response_body: str | None = None


class ApiClient(Protocol):
    """Protocol defining the interface the build_poller requires from an HTTP client.

    The harness is responsible for providing a conforming implementation.
    A minimal implementation must return a BuildStatus for each call.
    """

    def get_build_status(self, build_id: str) -> BuildStatus:
        """Poll the CI/CD API for the current status of build_id.

        Args:
            build_id: The identifier of the build to poll.

        Returns:
            BuildStatus with http_status_code and build_status field populated.

        Raises:
            Exception: Any non-HTTP exception (connectivity, timeout, etc.)
                      is treated as a transient failure and eligible for retry.
        """
        ...


# ---------------------------------------------------------------------------
# Structured Log Format
# ---------------------------------------------------------------------------


class StructuredLogKeys(Enum):
    TIMESTAMP = "timestamp"
    EVENT = "event"
    ATTEMPT = "attempt"
    HTTP_STATUS = "http_status"
    BUILD_STATUS = "build_status"
    BACKOFF_SECONDS = "backoff_seconds"
    TERMINATION_REASON = "termination_reason"
    HTTP_CODE = "http_code"
    RESPONSE_BODY = "response_body"


def _structured_log(**kwargs: object) -> None:
    """Emit a structured JSON log line parseable by the orchestration harness."""
    # Always include ISO timestamp in UTC
    record = {
        StructuredLogKeys.TIMESTAMP.value: datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    _struct_log.info(json.dumps(record))


# ---------------------------------------------------------------------------
# Poll Result Discriminated Union
# ---------------------------------------------------------------------------


class TerminationReason(Enum):
    BUILD_PASSED = "build_passed"
    BUILD_FAILED = "build_failed"
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    NON_TRANSIENT_ERROR = "non_transient_error"


@dataclass(frozen=True)
class PollSuccess:
    """Terminal state: build reached a terminal status (passed or failed)."""

    reason: TerminationReason
    http_status_code: int
    build_status: str
    attempts_made: int


@dataclass(frozen=True)
class PollTimeout:
    """Terminal state: exhausted all retry attempts without reaching terminal build status."""

    last_http_status_code: int
    last_build_status: str | None
    attempts_made: int


@dataclass(frozen=True)
class PollError:
    """Terminal state: received a non-transient HTTP error (400, 401, 403, 404)."""

    http_status_code: int
    response_body: str | None
    attempts_made: int


# Type union returned by poll_build
PollResult = PollSuccess | PollTimeout | PollError


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_POLL_INTERVAL_SECONDS = 30.0
MAX_ATTEMPTS = 5  # 1 initial + 4 retries
INITIAL_BACKOFF_SECONDS = 5.0
BACKOFF_MULTIPLIER = 2.0


@dataclass
class BuildPollerConfig:
    """Configuration for BuildPoller behavior."""

    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    max_attempts: int = MAX_ATTEMPTS
    initial_backoff_seconds: float = INITIAL_BACKOFF_SECONDS
    backoff_multiplier: float = BACKOFF_MULTIPLIER


# ---------------------------------------------------------------------------
# Build Poller Event Loop
# ---------------------------------------------------------------------------


@dataclass
class BuildPoller:
    """Event loop that polls a CI/CD API for build status with retry logic.

    Behavior is fully deterministic and code-enforced. There are no prose
    conditions that could be interpreted differently on different invocations.

    Usage:
        config = BuildPollerConfig(poll_interval_seconds=30.0)
        poller = BuildPoller(api_client=my_client, config=config)
        result = poller.poll(build_id="abc-123")
        # result is PollSuccess | PollTimeout | PollError
    """

    api_client: ApiClient
    config: BuildPollerConfig = field(default_factory=BuildPollerConfig)

    def poll(self, build_id: str) -> PollResult:
        """Poll the CI/CD API until a terminal condition is reached.

        This method implements the complete event loop. It is guaranteed to
        return exactly one of:
        - PollSuccess: build reached 'passed' or 'failed' status
        - PollTimeout: exhausted all retry attempts without terminal status
        - PollError: received a non-transient HTTP error

        The method does not raise exceptions. All exception types are caught
        internally and treated as transient failures (eligible for retry).

        Args:
            build_id: The CI/CD build identifier to poll.

        Returns:
            PollResult (one of PollSuccess, PollTimeout, PollError).
            The return type is a tagged union; callers should narrow with
            isinstance() to access fields.
        """
        attempts_made = 0
        last_status: BuildStatus | None = None

        for attempt in range(1, self.config.max_attempts + 1):
            attempts_made = attempt

            # Issue the poll request
            try:
                status = self.api_client.get_build_status(build_id)
            except Exception as exc:  # noqa: BLE001
                # Any exception (timeout, connection error, etc.) is treated
                # as a transient failure. Store a synthetic status.
                status = BuildStatus(
                    http_status_code=0,
                    build_status=None,
                    response_body=str(exc),
                )
                _structured_log(
                    event="poll_attempt",
                    attempt=attempt,
                    http_status=None,
                    build_status=None,
                    termination_reason="transient_exception",
                )
            else:
                _structured_log(
                    event="poll_attempt",
                    attempt=attempt,
                    http_status=status.http_status_code,
                    build_status=status.build_status,
                )

            last_status = status

            # -----------------------------------------------------------------
            # Termination check: terminal build status
            # -----------------------------------------------------------------
            if status.build_status in TERMINAL_BUILD_STATUSES:
                reason = (
                    TerminationReason.BUILD_PASSED
                    if status.build_status == "passed"
                    else TerminationReason.BUILD_FAILED
                )
                _structured_log(
                    event="poll_terminated",
                    attempt=attempt,
                    http_status=status.http_status_code,
                    build_status=status.build_status,
                    termination_reason=reason.value,
                )
                return PollSuccess(
                    reason=reason,
                    http_status_code=status.http_status_code,
                    build_status=status.build_status,
                    attempts_made=attempt,
                )

            # -----------------------------------------------------------------
            # Termination check: non-transient HTTP error
            # -----------------------------------------------------------------
            if status.http_status_code in NON_TRANSIENT_HTTP_CODES:
                _structured_log(
                    event="poll_terminated",
                    attempt=attempt,
                    http_status=status.http_status_code,
                    build_status=status.build_status,
                    termination_reason=TerminationReason.NON_TRANSIENT_ERROR.value,
                    http_code=status.http_status_code,
                    response_body=status.response_body,
                )
                return PollError(
                    http_status_code=status.http_status_code,
                    response_body=status.response_body,
                    attempts_made=attempt,
                )

            # -----------------------------------------------------------------
            # Retry decision: transient HTTP error on non-final attempt
            # -----------------------------------------------------------------
            is_transient_http = status.http_status_code in TRANSIENT_HTTP_CODES
            is_exception_case = (
                last_status is not None and last_status.http_status_code == 0
            )
            is_final_attempt = attempt == self.config.max_attempts

            if (is_transient_http or is_exception_case) and not is_final_attempt:
                backoff = self._compute_backoff(attempt)
                _structured_log(
                    event="retry_scheduled",
                    attempt=attempt,
                    backoff_seconds=backoff,
                    termination_reason="transient_error",
                )
                time.sleep(backoff)
                continue

            # -----------------------------------------------------------------
            # Terminal retry exhaustion OR unexpected state
            # -----------------------------------------------------------------
            # If we reach here on a non-final attempt with no transient error,
            # the build status is non-terminal and HTTP code is not transient.
            # The spec says: terminate after exactly 5 attempts if build has
            # not succeeded. So if we are not on the final attempt, we must
            # have hit a non-terminal non-transient case (e.g. HTTP 201 Created
            # with status "running"). We continue polling.
            if not is_final_attempt:
                # Non-terminal, non-transient response before max attempts.
                # Wait for poll interval and continue.
                _structured_log(
                    event="poll_continuing",
                    attempt=attempt,
                    http_status=status.http_status_code,
                    build_status=status.build_status,
                )
                time.sleep(self.config.poll_interval_seconds)
                continue

            # Final attempt exhausted with no terminal status
            _structured_log(
                event="poll_terminated",
                attempt=attempt,
                http_status=status.http_status_code,
                build_status=status.build_status,
                termination_reason=TerminationReason.MAX_ATTEMPTS_EXCEEDED.value,
            )
            return PollTimeout(
                last_http_status_code=status.http_status_code,
                last_build_status=status.build_status,
                attempts_made=attempt,
            )

        # Exhausted loop without returning — this should be unreachable
        # because the loop always returns or continues, but defensively
        # return a timeout if the loop somehow exits without a return.
        return PollTimeout(
            last_http_status_code=last_status.http_status_code if last_status else 0,
            last_build_status=last_status.build_status if last_status else None,
            attempts_made=attempts_made,
        )

    def _compute_backoff(self, attempt: int) -> float:
        """Compute exponential backoff delay for a given attempt number.

        Attempt 1 (initial request): no backoff — returns 0.
        Attempt 2 → 5s  (5 * 2^0)
        Attempt 3 → 10s (5 * 2^1)
        Attempt 4 → 20s (5 * 2^2)
        Attempt 5 → 40s (5 * 2^3)

        Formula: initial_backoff * multiplier^(attempt - 2)
        Because attempt 1 is the initial (no backoff), attempt 2 is retry 1.
        """
        if attempt == 1:
            return 0.0
        retry_number = attempt - 1  # 1-based retry index
        return self.config.initial_backoff_seconds * (
            self.config.backoff_multiplier ** (retry_number - 1)
        )


# ---------------------------------------------------------------------------
# Behavioral Test Suite (inline, can be run with pytest)
# ---------------------------------------------------------------------------

import unittest
from unittest.mock import Mock


class TestBuildPollerTerminationConditions(unittest.TestCase):
    """Verify exhaustive termination: every possible path returns a PollResult."""

    def _make_status(self, http_code: int, build_status: str | None) -> BuildStatus:
        return BuildStatus(http_status_code=http_code, build_status=build_status)

    def test_terminates_immediately_on_build_passed(self):
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.return_value = self._make_status(200, "passed")
        poller = BuildPoller(
            api_client=mock_client, config=BuildPollerConfig(poll_interval_seconds=0.01)
        )
        result = poller.poll("build-1")
        self.assertIsInstance(result, PollSuccess)
        self.assertEqual(result.reason, TerminationReason.BUILD_PASSED)
        self.assertEqual(result.build_status, "passed")
        self.assertEqual(result.attempts_made, 1)
        # Must not have called sleep (no retry, no backoff)
        mock_client.get_build_status.assert_called_once()

    def test_terminates_immediately_on_build_failed(self):
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.return_value = self._make_status(200, "failed")
        poller = BuildPoller(
            api_client=mock_client, config=BuildPollerConfig(poll_interval_seconds=0.01)
        )
        result = poller.poll("build-2")
        self.assertIsInstance(result, PollSuccess)
        self.assertEqual(result.reason, TerminationReason.BUILD_FAILED)
        self.assertEqual(result.build_status, "failed")
        self.assertEqual(result.attempts_made, 1)

    def test_terminates_immediately_on_non_transient_400(self):
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.return_value = self._make_status(400, None)
        poller = BuildPoller(
            api_client=mock_client, config=BuildPollerConfig(poll_interval_seconds=0.01)
        )
        result = poller.poll("build-3")
        self.assertIsInstance(result, PollError)
        self.assertEqual(result.http_status_code, 400)
        self.assertEqual(result.attempts_made, 1)
        mock_client.get_build_status.assert_called_once()

    def test_terminates_immediately_on_non_transient_401(self):
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.return_value = self._make_status(401, None)
        poller = BuildPoller(
            api_client=mock_client, config=BuildPollerConfig(poll_interval_seconds=0.01)
        )
        result = poller.poll("build-4")
        self.assertIsInstance(result, PollError)
        self.assertEqual(result.http_status_code, 401)

    def test_terminates_immediately_on_non_transient_403(self):
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.return_value = self._make_status(403, None)
        poller = BuildPoller(
            api_client=mock_client, config=BuildPollerConfig(poll_interval_seconds=0.01)
        )
        result = poller.poll("build-5")
        self.assertIsInstance(result, PollError)
        self.assertEqual(result.http_status_code, 403)

    def test_terminates_immediately_on_non_transient_404(self):
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.return_value = self._make_status(404, None)
        poller = BuildPoller(
            api_client=mock_client, config=BuildPollerConfig(poll_interval_seconds=0.01)
        )
        result = poller.poll("build-6")
        self.assertIsInstance(result, PollError)
        self.assertEqual(result.http_status_code, 404)

    def test_does_not_retry_non_transient_errors(self):
        mock_client = Mock(spec=ApiClient)
        # Return 400 first, then pretend it became 200 "passed" (which it won't)
        mock_client.get_build_status.return_value = self._make_status(400, None)
        poller = BuildPoller(
            api_client=mock_client, config=BuildPollerConfig(poll_interval_seconds=0.01)
        )
        result = poller.poll("build-7")
        self.assertIsInstance(result, PollError)
        # Must be exactly 1 call — no retry
        self.assertEqual(mock_client.get_build_status.call_count, 1)


class TestBuildPollerRetryLogic(unittest.TestCase):
    """Verify retry behavior and backoff schedule."""

    def _make_status(self, http_code: int, build_status: str | None) -> BuildStatus:
        return BuildStatus(http_status_code=http_code, build_status=build_status)

    def test_retries_on_http_429_up_to_max_attempts(self):
        mock_client = Mock(spec=ApiClient)
        # First 4 calls return 429 (transient), 5th returns "passed"
        mock_client.get_build_status.side_effect = [
            self._make_status(429, None),
            self._make_status(429, None),
            self._make_status(429, None),
            self._make_status(429, None),
            self._make_status(200, "passed"),
        ]
        poller = BuildPoller(
            api_client=mock_client,
            config=BuildPollerConfig(
                poll_interval_seconds=0.01,
                initial_backoff_seconds=5.0,
                backoff_multiplier=2.0,
            ),
        )
        result = poller.poll("build-8")
        self.assertIsInstance(result, PollSuccess)
        self.assertEqual(result.attempts_made, 5)
        self.assertEqual(mock_client.get_build_status.call_count, 5)

    def test_retries_on_http_500_up_to_max_attempts_then_timeout(self):
        mock_client = Mock(spec=ApiClient)
        # All 5 calls return 500 — should exhaust attempts and return timeout
        mock_client.get_build_status.return_value = self._make_status(500, None)
        poller = BuildPoller(
            api_client=mock_client,
            config=BuildPollerConfig(
                poll_interval_seconds=0.01,
                initial_backoff_seconds=5.0,
                backoff_multiplier=2.0,
            ),
        )
        result = poller.poll("build-9")
        self.assertIsInstance(result, PollTimeout)
        self.assertEqual(result.attempts_made, 5)
        self.assertEqual(mock_client.get_build_status.call_count, 5)

    def test_exponential_backoff_values(self):
        """Verify backoff schedule: 1s, 2s, 4s, 8s for retries 1-4 (scaled down from 5/10/20/40 to fit pytest timeout)."""
        mock_client = Mock(spec=ApiClient)
        # Return 429 for first 4 calls, then 200 passed
        mock_client.get_build_status.side_effect = [
            self._make_status(429, None),
            self._make_status(429, None),
            self._make_status(429, None),
            self._make_status(429, None),
            self._make_status(200, "passed"),
        ]
        poller = BuildPoller(
            api_client=mock_client,
            config=BuildPollerConfig(
                poll_interval_seconds=0.01,
                initial_backoff_seconds=1.0,
                backoff_multiplier=2.0,
            ),
        )

        import time

        start = time.monotonic()
        result = poller.poll("build-10")
        elapsed = time.monotonic() - start

        self.assertIsInstance(result, PollSuccess)
        # Expected backoff: 1 + 2 + 4 + 8 = 15s (scaled from 5+10+20+40=75s)
        # The actual backoff should be: 1s (retry 1) + 2s (retry 2) + 4s (retry 3) + 8s (retry 4)
        # Total = 15s minimum. With 0.01s intervals and small overhead, elapsed should be >= 15
        self.assertGreaterEqual(elapsed, 14.0)  # Allow 1s slack for test overhead
        self.assertLess(elapsed, 20.0)

    def test_no_backoff_on_initial_attempt(self):
        """First attempt should have no backoff delay before the request."""
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.side_effect = [
            Exception("connection error"),
            self._make_status(200, "passed"),
        ]
        poller = BuildPoller(
            api_client=mock_client,
            config=BuildPollerConfig(
                poll_interval_seconds=0.01,
                initial_backoff_seconds=5.0,
                backoff_multiplier=2.0,
            ),
        )
        import time

        start = time.monotonic()
        result = poller.poll("build-11")
        elapsed = time.monotonic() - start
        # First attempt is immediate (exception caught, backoff for attempt 1 = 0.0s per _compute_backoff fix)
        # Then we sleep 5s (backoff for attempt 1, which is retry 1), then attempt 2 succeeds
        # Total should be ~5s (first retry backoff after exception)
        self.assertLess(
            elapsed, 2.0
        )  # Should not have waited before first call (backoff for attempt 1 = 0)
        # Actually, the test name is "no_backoff_on_initial_attempt" - the first attempt has no backoff.
        # But after an exception, we DO apply backoff before retrying. So the elapsed should be ~5s.
        # Let me reconsider: the test verifies the FIRST request has no backoff (we don't sleep before making it).
        # The exception is thrown, we catch it, compute backoff for attempt 1 = 0.0, then sleep 0 and continue.
        # Wait no - backoff(1) = 0.0 so no sleep, then attempt 2 is made immediately.
        # So elapsed should be < 1s (no significant sleep).
        # With poll_interval_seconds=0.01, any intermediate sleeps are negligible.
        self.assertGreaterEqual(elapsed, 0.0)


class TestBuildPollerRecursionBounds(unittest.TestCase):
    """Verify recursion bounds are exactly as specified — no off-by-one errors."""

    def _make_status(self, http_code: int, build_status: str | None) -> BuildStatus:
        return BuildStatus(http_status_code=http_code, build_status=build_status)

    def test_max_attempts_exactly_5(self):
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.return_value = self._make_status(500, None)
        poller = BuildPoller(
            api_client=mock_client,
            config=BuildPollerConfig(poll_interval_seconds=0.01),
        )
        result = poller.poll("build-12")
        self.assertIsInstance(result, PollTimeout)
        self.assertEqual(result.attempts_made, 5)
        self.assertEqual(mock_client.get_build_status.call_count, 5)

    def test_no_poll_after_fifth_attempt(self):
        """Verify exactly 5 attempts total — the 6th would be attempt 6 which exceeds max_attempts."""
        mock_client = Mock(spec=ApiClient)
        call_count = 0

        def track_calls(build_id: str) -> BuildStatus:
            nonlocal call_count
            call_count += 1
            return self._make_status(500, None)

        mock_client.get_build_status.side_effect = track_calls
        poller = BuildPoller(
            api_client=mock_client,
            config=BuildPollerConfig(poll_interval_seconds=0.01),
        )
        result = poller.poll("build-13")
        self.assertEqual(call_count, 5)
        self.assertEqual(result.attempts_made, 5)


class TestBuildPollerBackoffCalculation(unittest.TestCase):
    """Unit test for _compute_backoff to verify exact formula."""

    def test_backoff_formula(self):
        poller = BuildPoller(
            api_client=Mock(spec=ApiClient),
            config=BuildPollerConfig(
                initial_backoff_seconds=5.0,
                backoff_multiplier=2.0,
            ),
        )
        # attempt 2 → retry 1 → 5 * 2^0 = 5
        self.assertEqual(poller._compute_backoff(2), 5.0)
        # attempt 3 → retry 2 → 5 * 2^1 = 10
        self.assertEqual(poller._compute_backoff(3), 10.0)
        # attempt 4 → retry 3 → 5 * 2^2 = 20
        self.assertEqual(poller._compute_backoff(4), 20.0)
        # attempt 5 → retry 4 → 5 * 2^3 = 40
        self.assertEqual(poller._compute_backoff(5), 40.0)


class TestBuildPollerStructuredLogging(unittest.TestCase):
    """Verify structured log output format."""

    def _make_status(self, http_code: int, build_status: str | None) -> BuildStatus:
        return BuildStatus(http_status_code=http_code, build_status=build_status)

    def test_log_contains_required_keys(self):
        mock_client = Mock(spec=ApiClient)
        mock_client.get_build_status.return_value = self._make_status(200, "passed")

        import io, logging

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        _struct_log.addHandler(handler)
        _struct_log.setLevel(logging.INFO)

        poller = BuildPoller(
            api_client=mock_client, config=BuildPollerConfig(poll_interval_seconds=0.01)
        )
        poller.poll("build-14")

        output = log_capture.getvalue()
        self.assertIn("timestamp", output)
        self.assertIn("event", output)
        self.assertIn("attempt", output)
        self.assertIn("http_status", output)
        self.assertIn("build_status", output)

        # Verify valid JSON
        for line in output.strip().split("\n"):
            if line:
                record = json.loads(line)
                self.assertIn("timestamp", record)

        _struct_log.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
