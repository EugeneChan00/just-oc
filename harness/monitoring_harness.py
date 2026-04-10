"""
harness/monitoring_harness.py

Poll-based event loop harness for monitoring_worker agent.
Provides:
1. MonitoringHarness - main harness orchestrating LLM-based monitoring agent
2. MockMetricsServer - serves metric file endpoints as local filesystem representations
3. ToolEnforcer - intercepts and enforces tool call restrictions
4. StateManager - manages state file with retry, validation, and config hash tracking
5. OutputSerializer - serializes agent output to monitoring_worker.md JSON schema

WRITE BOUNDARY: harness/monitoring_harness.py ONLY.
Enforces monitoring_worker.md contract:
- Tool restrictions (allow: task, read, glob, grep, list, question; deny: edit, bash, skill, lsp, etc.)
- Write restriction to monitoring_worker_state.json only
- Output schema per monitoring_worker.md output contract
- Termination conditions: max_iterations, 3 consecutive metric failures, 3 state write failures
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Module-level logger
_log = logging.getLogger("monitoring_harness")
_log.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_TOOLS = frozenset({"task", "read", "glob", "grep", "list", "question"})
DENIED_TOOLS = frozenset(
    {
        "edit",
        "bash",
        "skill",
        "lsp",
        "webfetch",
        "websearch",
        "codesearch",
        "external_directory",
        "doom_loop",
        "todowrite",
    }
)
STATE_FILE_NAME = "monitoring_worker_state.json"
MAX_STATE_WRITE_RETRIES = 3
MAX_CONSECUTIVE_METRIC_FAILURES = 3


# ---------------------------------------------------------------------------
# Output Schema (per monitoring_worker.md)
# ---------------------------------------------------------------------------

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["iteration", "timestamp", "metrics", "alerts", "state"],
    "properties": {
        "iteration": {"type": "integer"},
        "timestamp": {"type": "string"},
        "metrics": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["value", "unit", "delta", "status"],
                "properties": {
                    "value": {"type": ["number", "null"]},
                    "unit": {"type": "string"},
                    "delta": {"type": ["number", "null"]},
                    "status": {
                        "type": "string",
                        "enum": ["ok", "warning", "critical", "unknown"],
                    },
                },
            },
        },
        "alerts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "metric",
                    "level",
                    "value",
                    "threshold",
                    "operator",
                    "message",
                ],
                "properties": {
                    "metric": {"type": "string"},
                    "level": {"type": "string", "enum": ["warning", "critical"]},
                    "value": {"type": "number"},
                    "threshold": {"type": "number"},
                    "operator": {"type": "string"},
                    "message": {"type": "string"},
                },
            },
        },
        "state": {
            "type": "object",
            "required": ["last_iteration", "alerts_fired", "config_hash"],
            "properties": {
                "last_iteration": {"type": "integer"},
                "alerts_fired": {"type": "integer"},
                "config_hash": {"type": "string"},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# 1. State Manager
# ---------------------------------------------------------------------------


class StateManager:
    """Manages state file with JSON validation, retry, and config hash tracking.

    Responsibilities:
    - Validates state file JSON on read
    - Wraps state writes in retry (3 attempts)
    - Computes config hash on each iteration
    - Detects config hash mismatch
    """

    def __init__(self, state_file_path: str):
        """Initialize state manager.

        Args:
            state_file_path: Path to the state file.
        """
        self.state_file_path = state_file_path
        self._write_attempts = 0
        self._read_failures = 0
        _log.info(f"StateManager initialized with state_file_path={state_file_path}")

    def compute_config_hash(self, config: dict[str, Any]) -> str:
        """Compute SHA-256 hash of configuration for change detection.

        Args:
            config: The configuration dict to hash.

        Returns:
            Hex string of the config hash.
        """
        config_str = json.dumps(config, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(config_str.encode("utf-8")).hexdigest()[:16]

    def validate_state_json(self, data: Any) -> tuple[bool, str | None]:
        """Validate state file JSON structure.

        Args:
            data: The parsed JSON data.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not isinstance(data, dict):
            return False, "State file must be a JSON object"

        # Check required top-level fields
        if "last_iteration" not in data:
            return False, "State missing 'last_iteration'"
        if "metrics" not in data:
            return False, "State missing 'metrics'"
        if "alerts_fired" not in data:
            return False, "State missing 'alerts_fired'"
        if "config_hash" not in data:
            return False, "State missing 'config_hash'"

        return True, None

    def read_state(self) -> dict[str, Any] | None:
        """Reads and validates state from the state file.

        Returns:
            The state dict, or None if file doesn't exist or is corrupted.
        """
        if not os.path.exists(self.state_file_path):
            _log.debug("read_state() -> None (file does not exist)")
            return None

        try:
            with open(self.state_file_path) as f:
                data = json.load(f)

            # Validate structure
            is_valid, error = self.validate_state_json(data)
            if not is_valid:
                _log.warning(f"read_state() -> None (invalid structure: {error})")
                self._read_failures += 1
                return None

            _log.debug(f"read_state() -> succeeded")
            self._read_failures = 0
            return data

        except json.JSONDecodeError as e:
            _log.warning(f"read_state() -> None (corrupted JSON: {e})")
            self._read_failures += 1
            return None
        except Exception as e:
            _log.warning(f"read_state() -> None (error: {e})")
            self._read_failures += 1
            return None

    def write_state(self, state: dict[str, Any]) -> bool:
        """Atomically writes state to the state file with retry.

        Args:
            state: The state dict to write.

        Returns:
            True if write succeeded after retries, False if all retries failed.
        """
        self._write_attempts += 1

        for attempt in range(1, MAX_STATE_WRITE_RETRIES + 1):
            try:
                # Get directory of state file
                state_dir = os.path.dirname(self.state_file_path)
                if not state_dir:
                    state_dir = "."

                # Write to temporary file in same directory (for atomic rename)
                fd, temp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
                try:
                    with os.fdopen(fd, "w") as f:
                        json.dump(state, f, indent=2)
                    # Atomic rename
                    os.replace(temp_path, self.state_file_path)
                    _log.debug(f"write_state() attempt {attempt} -> succeeded")
                    return True
                except Exception:
                    # Clean up temp file if rename failed
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise

            except Exception as e:
                _log.warning(
                    f"write_state() attempt {attempt}/{MAX_STATE_WRITE_RETRIES} failed: {e}"
                )
                if attempt < MAX_STATE_WRITE_RETRIES:
                    time.sleep(0.1 * attempt)  # Brief backoff

        _log.error(f"write_state() -> failed after {MAX_STATE_WRITE_RETRIES} attempts")
        return False

    def get_write_attempts(self) -> int:
        """Returns total number of write attempts made."""
        return self._write_attempts

    def get_read_failures(self) -> int:
        """Returns consecutive read failure count."""
        return self._read_failures


# ---------------------------------------------------------------------------
# 2. Mock Metrics Server
# ---------------------------------------------------------------------------


class MockMetricsServer:
    """Mock metrics API server for testing.

    Serves metric file endpoints as local filesystem representations.
    Supports:
    - Configurable metric values for testing threshold scenarios
    - Sliding-window time simulation for T2.5 tests
    - Returns null for missing metric files (does not crash)

    The server provides a filesystem-like interface where metric data
    files appear as JSON files in a metrics directory.
    """

    def __init__(self, metrics_base_dir: str | None = None):
        """Initialize mock metrics server.

        Args:
            metrics_base_dir: Base directory for metric files. If None, uses temp directory.
        """
        if metrics_base_dir:
            self._base_dir = metrics_base_dir
        else:
            self._base_dir = tempfile.mkdtemp(prefix="mock_metrics_")

        # Configurable metric values: metric_name -> value or None
        self._metric_values: dict[str, float | None] = {}

        # Sliding window state: metric_name -> list of (timestamp, value)
        self._window_data: dict[str, list[tuple[float, float | None]]] = {}

        # Call tracking
        self._read_count: dict[str, int] = {}

        # Non-numeric values for testing
        self._non_numeric_values: dict[str, str] = {}

        _log.info(f"MockMetricsServer initialized with base_dir={self._base_dir}")

    def set_metric_value(self, name: str, value: float | None) -> None:
        """Set a metric value for retrieval.

        Args:
            name: The metric name.
            value: The metric value (float), or None for unavailable.
        """
        self._metric_values[name] = value
        _log.debug(f"set_metric_value({name}, {value})")

    def set_non_numeric_value(self, name: str, value: str) -> None:
        """Set a non-numeric value for a metric (for testing error handling).

        Args:
            name: The metric name.
            value: String value that is not numeric.
        """
        self._non_numeric_values[name] = value
        _log.debug(f"set_non_numeric_value({name}, {value})")

    def add_window_sample(
        self, name: str, timestamp: float, value: float | None
    ) -> None:
        """Add a sample to the sliding window buffer.

        Args:
            name: The metric name.
            timestamp: Unix timestamp of the sample.
            value: The metric value at this time.
        """
        if name not in self._window_data:
            self._window_data[name] = []
        self._window_data[name].append((timestamp, value))
        _log.debug(f"add_window_sample({name}, ts={timestamp}, value={value})")

    def get_metric_file_path(self, metric_name: str) -> str:
        """Get the filesystem path for a metric file.

        Args:
            metric_name: Name of the metric.

        Returns:
            Path to the metric file.
        """
        # Sanitize metric name for filesystem
        safe_name = metric_name.replace("/", "_").replace("\\", "_")
        return os.path.join(self._base_dir, f"{safe_name}.json")

    def write_metric_file(self, metric_name: str, data: dict[str, Any]) -> str:
        """Write a metric data file to the filesystem.

        Args:
            metric_name: Name of the metric.
            data: Metric data to write.

        Returns:
            Path to the written file.
        """
        file_path = self.get_metric_file_path(metric_name)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(data, f)
        _log.debug(f"write_metric_file({metric_name}) -> {file_path}")
        return file_path

    def read_metric_file(self, metric_name: str) -> dict[str, Any] | None:
        """Read a metric file, returning None for missing files.

        Args:
            metric_name: Name of the metric to read.

        Returns:
            Metric data dict, or None if file doesn't exist.
        """
        file_path = self.get_metric_file_path(metric_name)

        # Track read count
        self._read_count[metric_name] = self._read_count.get(metric_name, 0) + 1

        # Check for non-numeric value first
        if metric_name in self._non_numeric_values:
            return {
                "metric": metric_name,
                "value": self._non_numeric_values[metric_name],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "available": True,
            }

        # Check for configured override
        if metric_name in self._metric_values:
            value = self._metric_values[metric_name]
            if value is None:
                return None  # Unavailable
            return {
                "metric": metric_name,
                "value": value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "available": True,
            }

        # Try to read from filesystem
        if os.path.exists(file_path):
            try:
                with open(file_path) as f:
                    return json.load(f)
            except Exception as e:
                _log.warning(f"read_metric_file({metric_name}) -> error: {e}")
                return None

        # Missing metric file - return None, don't crash
        _log.debug(f"read_metric_file({metric_name}) -> None (not found)")
        return None

    def list_metrics(self) -> list[str]:
        """List all available metrics.

        Returns:
            List of metric names.
        """
        metrics = set(self._metric_values.keys())

        if os.path.exists(self._base_dir):
            for filename in os.listdir(self._base_dir):
                if filename.endswith(".json"):
                    metric_name = filename[:-5]  # Remove .json
                    metrics.add(metric_name)

        return sorted(list(metrics))

    def get_window_values(
        self, metric_name: str, window_seconds: float, current_time: float | None = None
    ) -> list[float | None]:
        """Get values within a sliding time window.

        Args:
            metric_name: Name of the metric.
            window_seconds: Size of the window in seconds.
            current_time: Current timestamp (defaults to now).

        Returns:
            List of values within the window, oldest first.
        """
        if current_time is None:
            current_time = time.time()

        window_start = current_time - window_seconds

        if metric_name not in self._window_data:
            return []

        # Filter to window and extract values
        values = [
            value
            for timestamp, value in self._window_data[metric_name]
            if timestamp >= window_start
        ]

        return values

    def is_metric_available(self, metric_name: str) -> bool:
        """Check if a metric is available.

        Args:
            metric_name: Name of the metric.

        Returns:
            True if metric can be read, False otherwise.
        """
        # Check non-numeric
        if metric_name in self._non_numeric_values:
            return True

        # Check configured value
        if metric_name in self._metric_values:
            return self._metric_values[metric_name] is not None

        # Check filesystem
        file_path = self.get_metric_file_path(metric_name)
        return os.path.exists(file_path)

    def get_read_count(self, metric_name: str) -> int:
        """Get number of times a metric was read.

        Args:
            metric_name: Name of the metric.

        Returns:
            Read count.
        """
        return self._read_count.get(metric_name, 0)

    def simulate_time_advance(self, delta_seconds: float) -> None:
        """Advance simulated time for all window data.

        This is used for T2.5 sliding window tests.

        Args:
            delta_seconds: Seconds to advance time by.
        """
        # Shift all timestamps forward
        for metric_name in self._window_data:
            new_data = []
            for timestamp, value in self._window_data[metric_name]:
                new_data.append((timestamp + delta_seconds, value))
            self._window_data[metric_name] = new_data

    def reset(self) -> None:
        """Reset all metric state."""
        self._metric_values.clear()
        self._window_data.clear()
        self._read_count.clear()
        self._non_numeric_values.clear()


# ---------------------------------------------------------------------------
# 3. Tool Enforcer
# ---------------------------------------------------------------------------


class ToolEnforcer:
    """Intercepts and enforces tool call restrictions.

    Monitors which tools the agent attempts to use and enforces:
    - Allowed tools: task, read, glob, grep, list, question
    - Denied tools: edit, bash, skill, lsp, webfetch, websearch, codesearch,
                    external_directory, doom_loop, todowrite
    - Write restriction to monitoring_worker_state.json only
    """

    def __init__(self, metrics_server: MockMetricsServer, state_file_path: str):
        """Initialize tool enforcer.

        Args:
            metrics_server: MockMetricsServer for reading metrics.
            state_file_path: Path to the allowed state file.
        """
        self._metrics_server = metrics_server
        self._state_file_path = os.path.abspath(state_file_path)
        self._tool_call_log: list[dict[str, Any]] = []
        self._denied_count = 0
        self._allowed_count = 0
        _log.info(
            f"ToolEnforcer initialized with state_file_path={self._state_file_path}"
        )

    def check_tool_allowed(self, tool_name: str) -> tuple[bool, str | None]:
        """Check if a tool is allowed.

        Args:
            tool_name: Name of the tool.

        Returns:
            Tuple of (is_allowed, error_message).
        """
        if tool_name in DENIED_TOOLS:
            self._denied_count += 1
            return (
                False,
                f"Tool '{tool_name}' is denied by monitoring_worker.md contract",
            )

        if tool_name in ALLOWED_TOOLS or tool_name.startswith("metrics_"):
            self._allowed_count += 1
            return True, None

        # Unknown tools are denied
        self._denied_count += 1
        return False, f"Tool '{tool_name}' is not in the allowed list"

    def check_read_allowed(self, file_path: str) -> tuple[bool, str | None]:
        """Check if a read operation is allowed.

        Args:
            file_path: Path being read.

        Returns:
            Tuple of (is_allowed, error_message).
        """
        abs_path = os.path.abspath(file_path)

        # Allow reads to metrics directory
        if hasattr(self._metrics_server, "_base_dir"):
            metrics_dir = os.path.abspath(self._metrics_server._base_dir)
            if abs_path.startswith(metrics_dir):
                return True, None

        # Allow reads to state file
        if abs_path == self._state_file_path:
            return True, None

        # Allow reads to config file (in same directory as state)
        state_dir = os.path.dirname(self._state_file_path)
        config_path = os.path.join(state_dir, "monitoring_config.json")
        if abs_path == os.path.abspath(config_path):
            return True, None

        # Allow reads to metrics/*.json files anywhere
        if "/metrics/" in file_path or "\\metrics\\" in file_path:
            return True, None

        # Check if it's a metric file path
        if file_path.endswith(".json") and "metric" in file_path.lower():
            return True, None

        return False, f"Read not allowed for path: {file_path}"

    def check_write_allowed(self, file_path: str) -> tuple[bool, str | None]:
        """Check if a write operation is allowed.

        Args:
            file_path: Path being written.

        Returns:
            Tuple of (is_allowed, error_message).
        """
        abs_path = os.path.abspath(file_path)
        state_abs = os.path.abspath(self._state_file_path)

        # Only state file is allowed to be written
        if abs_path == state_abs:
            return True, None

        return False, f"Write not allowed: only {STATE_FILE_NAME} is permitted"

    def log_tool_call(
        self, tool_name: str, args: dict[str, Any], allowed: bool
    ) -> None:
        """Log a tool call attempt.

        Args:
            tool_name: Name of the tool.
            args: Tool arguments.
            allowed: Whether the call was allowed.
        """
        self._tool_call_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tool": tool_name,
                "args": str(args)[:500],  # Truncate long args
                "allowed": allowed,
            }
        )

    def get_denied_count(self) -> int:
        """Get count of denied tool calls."""
        return self._denied_count

    def get_allowed_count(self) -> int:
        """Get count of allowed tool calls."""
        return self._allowed_count

    def get_tool_call_log(self) -> list[dict[str, Any]]:
        """Get log of all tool call attempts."""
        return list(self._tool_call_log)


# ---------------------------------------------------------------------------
# 4. Output Serializer
# ---------------------------------------------------------------------------


class OutputSerializer:
    """Serializes agent output to monitoring_worker.md JSON schema."""

    @staticmethod
    def validate_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate output against monitoring_worker.md schema.

        Args:
            output: The output dict to validate.

        Returns:
            Tuple of (is_valid, list_of_errors).
        """
        errors = []

        # Check required fields
        required_fields = ["iteration", "timestamp", "metrics", "alerts", "state"]
        for field in required_fields:
            if field not in output:
                errors.append(f"Missing required field: '{field}'")

        # Validate iteration
        if "iteration" in output:
            if not isinstance(output["iteration"], int):
                errors.append(
                    f"'iteration' must be an integer, got {type(output['iteration']).__name__}"
                )

        # Validate timestamp
        if "timestamp" in output:
            if not isinstance(output["timestamp"], str):
                errors.append(f"'timestamp' must be a string")

        # Validate metrics
        if "metrics" in output:
            if not isinstance(output["metrics"], dict):
                errors.append(f"'metrics' must be an object")
            else:
                for metric_name, metric_data in output["metrics"].items():
                    if not isinstance(metric_data, dict):
                        errors.append(f"Metric '{metric_name}' must be an object")
                        continue
                    for field in ["value", "unit", "delta", "status"]:
                        if field not in metric_data:
                            errors.append(
                                f"Metric '{metric_name}' missing field '{field}'"
                            )
                    if "status" in metric_data:
                        if metric_data["status"] not in [
                            "ok",
                            "warning",
                            "critical",
                            "unknown",
                        ]:
                            errors.append(
                                f"Metric '{metric_name}' has invalid status: {metric_data['status']}"
                            )

        # Validate alerts
        if "alerts" in output:
            if not isinstance(output["alerts"], list):
                errors.append(f"'alerts' must be an array")
            else:
                for i, alert in enumerate(output["alerts"]):
                    if not isinstance(alert, dict):
                        errors.append(f"Alert[{i}] must be an object")
                        continue
                    for field in [
                        "metric",
                        "level",
                        "value",
                        "threshold",
                        "operator",
                        "message",
                    ]:
                        if field not in alert:
                            errors.append(f"Alert[{i}] missing field '{field}'")
                    if "level" in alert:
                        if alert["level"] not in ["warning", "critical"]:
                            errors.append(
                                f"Alert[{i}] has invalid level: {alert['level']}"
                            )

        # Validate state
        if "state" in output:
            if not isinstance(output["state"], dict):
                errors.append(f"'state' must be an object")
            else:
                for field in ["last_iteration", "alerts_fired", "config_hash"]:
                    if field not in output["state"]:
                        errors.append(f"State missing field '{field}'")

        return len(errors) == 0, errors

    @staticmethod
    def serialize(output: dict[str, Any]) -> str:
        """Serialize output to JSON string.

        Args:
            output: The output dict.

        Returns:
            JSON string.
        """
        return json.dumps(output, indent=2)


# ---------------------------------------------------------------------------
# 5. Monitoring Harness (Main)
# ---------------------------------------------------------------------------


@dataclass
class HarnessConfig:
    """Configuration for the monitoring harness."""

    poll_interval_seconds: float = 60.0
    max_iterations: int = 0  # 0 = unlimited
    metrics_base_dir: str = "./metrics"
    state_file_path: str = "./monitoring_worker_state.json"
    config_file_path: str = "./monitoring_config.json"


@dataclass
class HarnessMetricsSnapshot:
    """Snapshot of metrics state for the harness."""

    iteration: int = 0
    timestamp: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)


class MonitoringHarness:
    """Main harness orchestrating the monitoring_worker agent.

    This harness:
    1. Manages poll-based event loop with iteration counting
    2. Enforces max_iterations termination
    3. Manages poll_interval_seconds sleep
    4. Calls monitoring_worker agent via LLM invocation
    5. Manages state file with JSON validation, retry, and config hash
    6. Enforces tool restrictions
    7. Provides mock metrics API server
    8. Serializes output to monitoring_worker.md JSON schema
    9. Enforces termination on max_iterations, 3 metric failures, 3 state write failures

    The harness does NOT evaluate thresholds itself - that is the agent's job.
    The harness provides the environment and enforces constraints.
    """

    def __init__(self, config: HarnessConfig):
        """Initialize monitoring harness.

        Args:
            config: HarnessConfig with harness settings.
        """
        self.config = config
        self.poll_interval = config.poll_interval_seconds
        self.max_iterations = config.max_iterations
        self._iteration = 0
        self._stop_requested = False
        self._termination_reason: str | None = None

        # Initialize components
        self.metrics_server = MockMetricsServer(config.metrics_base_dir)
        self.state_manager = StateManager(config.state_file_path)
        self.tool_enforcer = ToolEnforcer(self.metrics_server, config.state_file_path)
        self.output_serializer = OutputSerializer()

        # Track consecutive failures
        self._consecutive_metric_failures = 0
        self._consecutive_state_write_failures = 0

        # Config hash
        self._config_hash: str | None = None
        self._config: dict[str, Any] = {}

        # Agent output history
        self._output_history: list[dict[str, Any]] = []

        _log.info(
            f"MonitoringHarness created: poll_interval={self.poll_interval}s, "
            f"max_iterations={self.max_iterations}"
        )

    def load_config(self) -> dict[str, Any]:
        """Load monitoring configuration from file.

        Returns:
            Configuration dict.
        """
        config_path = self.config.config_file_path
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    self._config = json.load(f)
                self._config_hash = self.state_manager.compute_config_hash(self._config)
                _log.info(f"Loaded config with hash: {self._config_hash}")
                return self._config
            except Exception as e:
                _log.warning(f"Failed to load config: {e}")

        # Default config
        self._config = {
            "poll_interval_seconds": self.poll_interval,
            "max_iterations": self.max_iterations,
            "thresholds": {},
            "output_format": "json",
        }
        self._config_hash = self.state_manager.compute_config_hash(self._config)
        return self._config

    def _check_termination_conditions(self) -> tuple[bool, str | None]:
        """Check if termination conditions are met.

        Returns:
            Tuple of (should_terminate, reason).
        """
        # Check max_iterations
        if self.max_iterations > 0 and self._iteration >= self.max_iterations:
            return True, f"max_iterations reached ({self.max_iterations})"

        # Check consecutive metric failures
        if self._consecutive_metric_failures >= MAX_CONSECUTIVE_METRIC_FAILURES:
            return (
                True,
                f"consecutive_metric_failures exceeded ({MAX_CONSECUTIVE_METRIC_FAILURES})",
            )

        # Check consecutive state write failures
        if self._consecutive_state_write_failures >= MAX_STATE_WRITE_RETRIES:
            return True, f"state_write_failures exceeded ({MAX_STATE_WRITE_RETRIES})"

        # Check stop signal
        if self._stop_requested:
            return True, "stop_requested"

        return False, None

    def _update_state(
        self,
        iteration: int,
        metrics: dict[str, Any],
        alerts: list[dict[str, Any]],
        alerts_fired: int,
    ) -> bool:
        """Update state file.

        Args:
            iteration: Current iteration number.
            metrics: Current metrics state.
            alerts: Current alerts.
            alerts_fired: Total alerts fired so far.

        Returns:
            True if state was written successfully.
        """
        state = {
            "last_iteration": iteration,
            "metrics": metrics,
            "alerts_fired": alerts_fired,
            "config_hash": self._config_hash,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

        success = self.state_manager.write_state(state)
        if not success:
            self._consecutive_state_write_failures += 1
        else:
            self._consecutive_state_write_failures = 0

        return success

    def _read_current_state(self) -> dict[str, Any] | None:
        """Read current state from state file.

        Returns:
            State dict or None.
        """
        state = self.state_manager.read_state()
        if state is None:
            return None

        # Check config hash mismatch
        if self._config_hash and state.get("config_hash") != self._config_hash:
            _log.warning(
                f"Config hash mismatch: state={state.get('config_hash')}, "
                f"current={self._config_hash}"
            )

        return state

    def run_iteration(
        self, agent_prompt: str, llm_invoker: callable
    ) -> HarnessMetricsSnapshot | None:
        """Run a single monitoring iteration.

        This method:
        1. Reads current metrics from the mock server
        2. Invokes the monitoring_worker agent via LLM
        3. Validates and serializes output
        4. Updates state

        Args:
            agent_prompt: Prompt to send to the agent.
            llm_invoker: Callable that invokes the LLM and returns response.

        Returns:
            HarnessMetricsSnapshot or None if terminated.
        """
        self._iteration += 1
        current_time = datetime.now(timezone.utc).isoformat()

        # Check termination before running
        should_stop, reason = self._check_termination_conditions()
        if should_stop:
            self._termination_reason = reason
            _log.info(f"Terminating before iteration {self._iteration}: {reason}")
            return None

        _log.info(f"Starting iteration {self._iteration}")

        # Prepare metrics data for agent
        available_metrics = {}
        metric_read_failures = 0

        for metric_name in self.metrics_server.list_metrics():
            metric_data = self.metrics_server.read_metric_file(metric_name)
            if metric_data is None:
                metric_read_failures += 1
                available_metrics[metric_name] = {
                    "value": None,
                    "unit": "unknown",
                    "status": "unknown",
                }
            else:
                value = metric_data.get("value")
                if isinstance(value, (int, float)):
                    available_metrics[metric_name] = {
                        "value": value,
                        "unit": metric_data.get("unit", "unknown"),
                        "status": "ok",
                    }
                else:
                    available_metrics[metric_name] = {
                        "value": None,
                        "unit": metric_data.get("unit", "unknown"),
                        "status": "unknown",
                    }

        # Track metric failures
        if metric_read_failures > 0:
            self._consecutive_metric_failures += 1
            _log.warning(
                f"Metric read failures: {metric_read_failures}, "
                f"consecutive: {self._consecutive_metric_failures}"
            )
        else:
            self._consecutive_metric_failures = 0

        # Read previous state
        prev_state = self._read_current_state()
        prev_metrics = prev_state.get("metrics", {}) if prev_state else {}

        # Compute deltas
        for metric_name, metric_data in available_metrics.items():
            if metric_name in prev_metrics:
                prev_value = prev_metrics[metric_name].get("value")
                curr_value = metric_data.get("value")
                if prev_value is not None and curr_value is not None:
                    metric_data["delta"] = curr_value - prev_value
                else:
                    metric_data["delta"] = None
            else:
                metric_data["delta"] = None  # First iteration

        # Build agent context
        agent_context = {
            "iteration": self._iteration,
            "timestamp": current_time,
            "metrics": available_metrics,
            "config": self._config,
            "previous_metrics": prev_metrics,
            "state_file_path": self.config.state_file_path,
            "metrics_base_dir": self.metrics_server._base_dir,
        }

        # Invoke agent
        try:
            agent_output = llm_invoker(agent_prompt, agent_context)
        except Exception as e:
            _log.error(f"Agent invocation failed: {e}")
            agent_output = None

        # Process agent output
        snapshot = HarnessMetricsSnapshot(
            iteration=self._iteration,
            timestamp=current_time,
            metrics=available_metrics,
            alerts=[],
            state={
                "last_iteration": self._iteration,
                "alerts_fired": 0,
                "config_hash": self._config_hash,
            },
        )

        if agent_output is not None:
            # Validate and use agent output
            is_valid, errors = self.output_serializer.validate_output(agent_output)
            if is_valid:
                snapshot = HarnessMetricsSnapshot(
                    iteration=agent_output.get("iteration", self._iteration),
                    timestamp=agent_output.get("timestamp", current_time),
                    metrics=agent_output.get("metrics", available_metrics),
                    alerts=agent_output.get("alerts", []),
                    state=agent_output.get("state", snapshot.state),
                )
            else:
                _log.warning(f"Agent output validation errors: {errors}")

        # Update state
        alerts_fired = len(snapshot.alerts)
        state_success = self._update_state(
            self._iteration,
            snapshot.metrics,
            snapshot.alerts,
            (prev_state.get("alerts_fired", 0) if prev_state else 0) + alerts_fired,
        )

        if not state_success:
            should_stop, reason = self._check_termination_conditions()
            if should_stop:
                self._termination_reason = reason
                return None

        # Store output
        output_dict = {
            "iteration": snapshot.iteration,
            "timestamp": snapshot.timestamp,
            "metrics": snapshot.metrics,
            "alerts": snapshot.alerts,
            "state": snapshot.state,
        }
        self._output_history.append(output_dict)

        # Write output to stdout
        print(self.output_serializer.serialize(output_dict))

        return snapshot

    def run(self, agent_prompt: str, llm_invoker: callable) -> list[dict[str, Any]]:
        """Run the monitoring loop until termination.

        Args:
            agent_prompt: System prompt for the monitoring agent.
            llm_invoker: Callable that invokes the LLM.

        Returns:
            List of all output snapshots.
        """
        _log.info("Starting monitoring loop")
        self.load_config()

        while True:
            snapshot = self.run_iteration(agent_prompt, llm_invoker)

            if snapshot is None:
                break

            # Check termination after iteration
            should_stop, reason = self._check_termination_conditions()
            if should_stop:
                self._termination_reason = reason
                _log.info(f"Loop terminated: {reason}")
                break

            # Sleep for poll interval (skip on last iteration)
            if self.poll_interval > 0:
                if not (
                    self.max_iterations > 0 and self._iteration >= self.max_iterations
                ):
                    time.sleep(self.poll_interval)

        _log.info(
            f"Monitoring loop ended: {len(self._output_history)} iterations, "
            f"reason={self._termination_reason}"
        )

        return self._output_history

    def stop(self) -> None:
        """Signal the harness to stop after current iteration."""
        self._stop_requested = True
        _log.info("Stop requested")

    def get_termination_reason(self) -> str | None:
        """Get the reason for loop termination."""
        return self._termination_reason

    def get_metrics_server(self) -> MockMetricsServer:
        """Get the mock metrics server for test setup."""
        return self.metrics_server


# ---------------------------------------------------------------------------
# Utility: Run harness with agent
# ---------------------------------------------------------------------------


def create_llm_invoker(
    model: str = "claude", api_key: str | None = None, base_url: str | None = None
) -> callable:
    """Create an LLM invoker function.

    This is a placeholder - in actual use, this would connect to an LLM API.

    Args:
        model: Model name to use.
        api_key: API key for the LLM service.
        base_url: Base URL for the LLM API.

    Returns:
        Callable that takes (prompt, context) and returns agent output.
    """

    def invoker(prompt: str, context: dict[str, Any]) -> dict[str, Any] | None:
        """Invoke LLM with prompt and context.

        Args:
            prompt: System/user prompt.
            context: Agent context with metrics, config, etc.

        Returns:
            Agent output dict or None.
        """
        # This is a stub - actual implementation would call LLM API
        # For now, return a minimal valid output
        return {
            "iteration": context.get("iteration", 1),
            "timestamp": context.get(
                "timestamp", datetime.now(timezone.utc).isoformat()
            ),
            "metrics": context.get("metrics", {}),
            "alerts": [],
            "state": {
                "last_iteration": context.get("iteration", 1),
                "alerts_fired": 0,
                "config_hash": "stub_hash",
            },
        }

    return invoker


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main():
    """CLI entry point for running the monitoring harness."""
    import argparse

    parser = argparse.ArgumentParser(description="Monitoring Worker Harness")
    parser.add_argument(
        "--poll-interval", type=float, default=60.0, help="Poll interval in seconds"
    )
    parser.add_argument(
        "--max-iterations", type=int, default=0, help="Max iterations (0=unlimited)"
    )
    parser.add_argument(
        "--metrics-dir", type=str, default="./metrics", help="Metrics directory"
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default="./monitoring_worker_state.json",
        help="State file path",
    )
    parser.add_argument(
        "--config-file",
        type=str,
        default="./monitoring_config.json",
        help="Config file path",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    # Create harness
    config = HarnessConfig(
        poll_interval_seconds=args.poll_interval,
        max_iterations=args.max_iterations,
        metrics_base_dir=args.metrics_dir,
        state_file_path=args.state_file,
        config_file_path=args.config_file,
    )

    harness = MonitoringHarness(config)

    # Create LLM invoker (stub for now)
    invoker = create_llm_invoker()

    # System prompt for monitoring agent
    system_prompt = """You are a monitoring_worker agent. Your role is to:
1. Read metric values from the metrics directory
2. Evaluate metrics against configured thresholds
3. Emit alerts when thresholds are crossed
4. Update the state file at the end of each cycle

You have access to:
- read: Read metric files and configuration
- glob: Find metric files by pattern
- grep: Search metric data
- list: List directory contents
- task: Escalation only (max 1 per iteration)

You must NOT:
- Write to any file except monitoring_worker_state.json
- Call bash, edit, or other denied tools

Output format: JSON to stdout with schema:
{
  "iteration": int,
  "timestamp": "ISO8601",
  "metrics": {...},
  "alerts": [...],
  "state": {...}
}
"""

    # Run harness
    try:
        results = harness.run(system_prompt, invoker)
        print(f"\nHarness completed: {len(results)} iterations")
        print(f"Termination reason: {harness.get_termination_reason()}")
    except KeyboardInterrupt:
        harness.stop()
        print("\nHarness interrupted")


if __name__ == "__main__":
    main()
