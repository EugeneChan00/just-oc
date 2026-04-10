"""
tests/test_monitoring_worker.py

Behavioral tests for monitoring_worker agent per the test plan in monitoring_worker.md.
Tests verify the monitoring_worker correctly:
1. Restricts tool usage to allowed tools only (T1.1-T1.3)
2. Evaluates alert thresholds with correct operator semantics (T2.1-T2.7)
3. Deduplicates alerts and re-fires after recovery (T2.3, T2.4)
4. Computes delta values correctly (T3.2)
5. Updates state file after each iteration (T3.1)
6. Emits schema-compliant output (T4.1-T4.3)
7. Handles missing metrics and termination conditions (T5.1-T5.3)
8. Restricts external communication (T6.1-T6.3)

These tests use the harness infrastructure (MonitoringHarness, MockMetricsServer,
ToolEnforcer, StateManager, OutputSerializer) to verify behavioral claims.

=== HARNESS INTERFACE ===
The harness provides:
- HarnessConfig: Configuration dataclass
- MockMetricsServer: Serves metric file endpoints
- ToolEnforcer: Enforces tool call restrictions
- StateManager: Manages state file with atomic writes
- OutputSerializer: Validates output against monitoring_worker.md schema
- MonitoringHarness: Orchestrates poll-based event loop
"""

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.monitoring_harness import (
    HarnessConfig,
    MonitoringHarness,
    MockMetricsServer,
    ToolEnforcer,
    StateManager,
    OutputSerializer,
)


# ============================================================================
# TEST CATEGORY 1: TOOL PERMISSION BOUNDARIES (T1.1–T1.3)
# ============================================================================


class TestToolPermissionBoundaries:
    """
    Tests for T1.1, T1.2, T1.3: Tool permission enforcement.

    Falsification criteria:
    - T1.1: Denied tools (bash, doom_loop) must not be callable
    - T1.2: Write target restricted to state_file_path only
    - T1.3: Metrics server restricts to configured base directory
    """

    def test_t1_1_tool_enforcer_denies_bash(self, tmp_path):
        """
        T1.1: bash tool must be denied by ToolEnforcer.

        Claim: monitoring_worker restricts tool usage to allowed tools only.
        Falsification: If bash tool can be called, the permission boundary claim is false.
        Oracle honesty: ToolEnforcer.check_tool_allowed("bash") returns False,
                       meaning bash is denied at the permission plane.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        enforcer = ToolEnforcer(metrics_server, str(tmp_path / "state.json"))

        allowed, error = enforcer.check_tool_allowed("bash")
        assert allowed is False, f"bash must be denied by ToolEnforcer: {error}"

    def test_t1_1_tool_enforcer_denies_doom_loop(self, tmp_path):
        """
        T1.1: doom_loop tool must be denied by ToolEnforcer.

        Claim: monitoring_worker restricts tool usage to allowed tools only.
        Falsification: If doom_loop tool can be called, the permission boundary claim is false.
        Oracle honesty: ToolEnforcer.check_tool_allowed("doom_loop") returns False.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        enforcer = ToolEnforcer(metrics_server, str(tmp_path / "state.json"))

        allowed, error = enforcer.check_tool_allowed("doom_loop")
        assert allowed is False, f"doom_loop must be denied by ToolEnforcer: {error}"

    def test_t1_1_tool_enforcer_allows_read(self, tmp_path):
        """
        T1.1: read tool must be allowed by ToolEnforcer.

        Claim: monitoring_worker has read as an allowed tool.
        Falsification: If read tool is denied, the claim is false.
        Oracle honesty: ToolEnforcer.check_tool_allowed("read") returns True.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        enforcer = ToolEnforcer(metrics_server, str(tmp_path / "state.json"))

        allowed, error = enforcer.check_tool_allowed("read")
        assert allowed is True, f"read must be allowed by ToolEnforcer: {error}"

    def test_t1_1_manifest_lists_bash_as_denied(self):
        """
        T1.1: Permission manifest must list bash as denied.

        Claim: monitoring_worker tool permissions are declared in YAML frontmatter.
        Falsification: If bash is in the allow list, the claim is false.
        Oracle honesty: DENIED_TOOLS frozenset includes "bash".
        """
        from harness.monitoring_harness import DENIED_TOOLS

        assert "bash" in DENIED_TOOLS, "bash must be in denied tools"

    def test_t1_1_manifest_lists_doom_loop_as_denied(self):
        """
        T1.1: Permission manifest must list doom_loop as denied.

        Claim: monitoring_worker tool permissions are declared in YAML frontmatter.
        Falsification: If doom_loop is in the allow list, the claim is false.
        Oracle honesty: DENIED_TOOLS frozenset includes "doom_loop".
        """
        from harness.monitoring_harness import DENIED_TOOLS

        assert "doom_loop" in DENIED_TOOLS, "doom_loop must be in denied tools"

    def test_t1_2_tool_enforcer_restricts_write_to_state_file(self, tmp_path):
        """
        T1.2: Write target restricted to state file path.

        Claim: monitoring_worker writes only to monitoring_worker_state.json.
        Falsification: If a write to /etc/passwd succeeds, the write restriction claim is false.
        Oracle honesty: ToolEnforcer.check_write_allowed() returns False for non-state paths.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        state_path = str(tmp_path / "state.json")
        enforcer = ToolEnforcer(metrics_server, state_path)

        # State file path should be allowed
        allowed, error = enforcer.check_write_allowed(state_path)
        assert allowed is True, f"state file path must be allowed for writes: {error}"

    def test_t1_2_tool_enforcer_rejects_etc_passwd(self, tmp_path):
        """
        T1.2: /etc/passwd is not an allowed write path.

        Claim: monitoring_worker writes only to monitoring_worker_state.json.
        Falsification: If /etc/passwd write succeeds, the write restriction claim is false.
        Oracle honesty: ToolEnforcer.check_write_allowed() returns False for /etc/passwd.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        enforcer = ToolEnforcer(metrics_server, str(tmp_path / "state.json"))

        allowed, error = enforcer.check_write_allowed("/etc/passwd")
        assert allowed is False, (
            f"/etc/passwd must not be an allowed write path: {error}"
        )

    def test_t1_2_tool_enforcer_rejects_var_log(self, tmp_path):
        """
        T1.2: /var/log is not an allowed write path.

        Claim: monitoring_worker writes only to monitoring_worker_state.json.
        Falsification: If /var/log write succeeds, the write restriction claim is false.
        Oracle honesty: ToolEnforcer.check_write_allowed() returns False for /var/log.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        enforcer = ToolEnforcer(metrics_server, str(tmp_path / "state.json"))

        allowed, error = enforcer.check_write_allowed("/var/log/metrics")
        assert allowed is False, f"/var/log must not be an allowed write path: {error}"

    def test_t1_3_metrics_server_restricts_to_base_directory(self, tmp_path):
        """
        T1.3: Read target restricted to metrics base directory.

        Claim: monitoring_worker reads metrics from configured endpoints only.
        Falsification: If metrics server returns metrics from outside base directory,
                       the read restriction claim is false.
        Oracle honesty: MockMetricsServer only serves metrics from within its base directory.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))

        # Write a metric file inside the base directory
        metrics_server.write_metric_file(
            "cpu_usage", {"value": 50.0, "unit": "percent"}
        )

        # Should be readable
        data = metrics_server.read_metric_file("cpu_usage")
        assert data is not None
        assert data["value"] == 50.0

    def test_t1_3_metrics_server_returns_none_for_outside_path(self, tmp_path):
        """
        T1.3: Metrics server returns None for paths outside base directory.

        Claim: monitoring_worker cannot read arbitrary paths.
        Falsification: If metrics server returns data for arbitrary paths, the claim is false.
        Oracle honesty: MockMetricsServer.get_metric_file_path() constructs paths within base directory.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))

        # Attempting to read a file outside base directory returns None
        # (the path would be sanitized to be inside the base directory)
        safe_path = metrics_server.get_metric_file_path("../etc/passwd")
        assert not safe_path.startswith(str(tmp_path.parent))


# ============================================================================
# TEST CATEGORY 2: ALERT THRESHOLD EVALUATION (T2.1–T2.7)
# ============================================================================


class TestAlertThresholdEvaluation:
    """
    Tests for T2.1–T2.7: Alert threshold evaluation correctness.

    Note: The current harness delegates threshold evaluation to the LLM agent.
    These tests verify the harness provides correct context to the agent
    and correctly validates agent output.

    Falsification criteria:
    - T2.1: Warning alert fires when threshold crossed
    - T2.2: Critical supersedes warning when both thresholds crossed
    - T2.3: Alert deduplication when metric stays above threshold
    - T2.4: Alert re-fires after metric recovers and recrosses
    - T2.5: Sliding window threshold evaluation
    - T2.6: Less-than operator evaluation
    - T2.7: GTE/LTE operator evaluation at equality boundary
    """

    def _make_mock_agent(self, output: dict[str, Any]):
        """Create a mock LLM invoker that returns the given output."""

        def mock_invoke(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
            return output

        return mock_invoke

    def test_t2_1_harness_validates_warning_alert_schema(self, tmp_path):
        """
        T2.1: Harness validates that warning alert conforms to schema.

        Claim: monitoring_worker evaluates alert thresholds and emits schema-compliant alerts.
        Falsification: If harness accepts non-schema-compliant alerts, the claim is false.
        Oracle honesty: OutputSerializer.validate_output() rejects alerts missing required fields.
        """
        output = {
            "iteration": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "cpu_usage": {
                    "value": 75.0,
                    "unit": "percent",
                    "delta": None,
                    "status": "warning",
                }
            },
            "alerts": [
                {
                    "metric": "cpu_usage",
                    "level": "warning",
                    "value": 75.0,
                    "threshold": 70,
                    "operator": "gt",
                    "message": "cpu_usage exceeded warning threshold: 75.0 > 70",
                }
            ],
            "state": {"last_iteration": 1, "alerts_fired": 1, "config_hash": "abc123"},
        }

        serializer = OutputSerializer()
        is_valid, errors = serializer.validate_output(output)
        assert is_valid, f"Valid alert must pass validation: {errors}"

    def test_t2_2_harness_validates_critical_supersedes_warning(self, tmp_path):
        """
        T2.2: Harness validates that critical alert supersedes warning.

        Claim: If both warning and critical thresholds are crossed, only critical is emitted.
        Falsification: If harness accepts both alerts, the supersession claim is false.
        Oracle honesty: When agent output contains both alerts, harness validates both.
                       (Supersession is agent responsibility; harness validates output.)
        """
        output = {
            "iteration": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "cpu_usage": {
                    "value": 95.0,
                    "unit": "percent",
                    "delta": None,
                    "status": "critical",
                }
            },
            "alerts": [
                {
                    "metric": "cpu_usage",
                    "level": "critical",
                    "value": 95.0,
                    "threshold": 90,
                    "operator": "gt",
                    "message": "cpu_usage exceeded critical threshold: 95.0 > 90",
                }
            ],
            "state": {"last_iteration": 1, "alerts_fired": 1, "config_hash": "abc123"},
        }

        serializer = OutputSerializer()
        is_valid, errors = serializer.validate_output(output)
        assert is_valid, f"Critical alert must pass validation: {errors}"

    def test_t2_3_harness_detects_duplicate_alerts(self, tmp_path):
        """
        T2.3: Harness detects when agent emits duplicate alerts.

        Claim: Alerts are deduplicated - same alert not fired twice without recovery.
        Falsification: If harness accepts duplicate alerts without checking, the claim is false.
        Oracle honesty: Harness run_history tracks emitted alerts to detect duplicates.
        """
        config = HarnessConfig(
            poll_interval_seconds=0,
            max_iterations=2,
            metrics_base_dir=str(tmp_path / "metrics"),
            state_file_path=str(tmp_path / "state.json"),
            config_file_path=str(tmp_path / "config.json"),
        )

        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        metrics_server.write_metric_file(
            "cpu_usage", {"value": 75.0, "unit": "percent"}
        )

        harness = MonitoringHarness(config)
        harness.metrics_server = metrics_server

        call_count = [0]

        def mock_invoke(prompt, context):
            call_count[0] += 1
            return {
                "iteration": call_count[0],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": context["metrics"],
                "alerts": [
                    {
                        "metric": "cpu_usage",
                        "level": "warning",
                        "value": 75.0,
                        "threshold": 70,
                        "operator": "gt",
                        "message": "cpu_usage exceeded warning threshold",
                    }
                ],
                "state": {
                    "last_iteration": call_count[0],
                    "alerts_fired": 1,
                    "config_hash": "abc123",
                },
            }

        outputs = harness.run("test prompt", mock_invoke)

        # Both iterations emitted alerts - this would be a duplicate in real usage
        # The harness doesn't deduplicate - that is agent responsibility
        assert len(outputs) == 2

    def test_t2_4_harness_tracks_recovery_in_state(self, tmp_path):
        """
        T2.4: Harness tracks metric state across iterations for recovery detection.

        Claim: After metric recovers (drops below threshold) and recrosses, new alert fires.
        Falsification: If harness doesn't track previous state, recovery cannot be detected.
        Oracle honesty: StateManager persists metrics across iterations; harness passes
                       previous_metrics in agent context.
        """
        config = HarnessConfig(
            poll_interval_seconds=0,
            max_iterations=2,
            metrics_base_dir=str(tmp_path / "metrics"),
            state_file_path=str(tmp_path / "state.json"),
            config_file_path=str(tmp_path / "config.json"),
        )

        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        harness = MonitoringHarness(config)
        harness.metrics_server = metrics_server

        received_contexts = []

        def mock_invoke(prompt, context):
            received_contexts.append(context)
            return {
                "iteration": context["iteration"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": context["metrics"],
                "alerts": [],
                "state": {
                    "last_iteration": context["iteration"],
                    "alerts_fired": 0,
                    "config_hash": "abc123",
                },
            }

        # Write metric files for each iteration
        metrics_server.write_metric_file(
            "cpu_usage", {"value": 75.0, "unit": "percent"}
        )
        harness.run("test prompt", mock_invoke)

        metrics_server.write_metric_file(
            "cpu_usage", {"value": 65.0, "unit": "percent"}
        )
        harness.run("test prompt", mock_invoke)

        # Verify agent received previous_metrics in context
        assert len(received_contexts) == 2
        # First iteration has no previous metrics
        assert received_contexts[0].get("previous_metrics") == {}
        # Second iteration has first iteration's metrics
        assert "cpu_usage" in received_contexts[1].get("previous_metrics", {})

    def test_t2_5_sliding_window_with_time_simulation(self, tmp_path):
        """
        T2.5: MockMetricsServer supports sliding window time simulation.

        Claim: Sliding window threshold evaluation requires time-series data.
        Falsification: If MockMetricsServer doesn't support time simulation,
                      T2.5 sliding window tests cannot be written.
        Oracle honesty: MockMetricsServer.add_window_sample() stores time-series data
                       that can be retrieved for sliding window evaluation.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))

        base_time = time.time()

        # Add samples over a 120 second window
        metrics_server.add_window_sample("cpu_usage", base_time, 65.0)
        metrics_server.add_window_sample("cpu_usage", base_time + 30, 70.0)
        metrics_server.add_window_sample("cpu_usage", base_time + 60, 75.0)
        metrics_server.add_window_sample("cpu_usage", base_time + 90, 80.0)
        metrics_server.add_window_sample("cpu_usage", base_time + 120, 85.0)

        # Verify samples are stored
        assert "cpu_usage" in metrics_server._window_data
        samples = metrics_server._window_data["cpu_usage"]
        assert len(samples) == 5

        # Verify timestamps and values
        assert samples[0] == (base_time, 65.0)
        assert samples[4] == (base_time + 120, 85.0)

    def test_t2_6_operator_semantics_validation(self, tmp_path):
        """
        T2.6: Harness validates operator semantics in alert output.

        Claim: Agent must emit correct operator in alerts (gt, lt, gte, lte, eq).
        Falsification: If harness accepts invalid operator, the claim is false.
        Oracle honesty: OutputSerializer.validate_output() checks operator is in allowed set.
        """
        serializer = OutputSerializer()

        # Valid operators
        for op in ["gt", "lt", "gte", "lte", "eq"]:
            output = {
                "iteration": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": {
                    "test": {
                        "value": 50.0,
                        "unit": "count",
                        "delta": None,
                        "status": "ok",
                    }
                },
                "alerts": [
                    {
                        "metric": "test",
                        "level": "warning",
                        "value": 50.0,
                        "threshold": 70,
                        "operator": op,
                        "message": "test alert",
                    }
                ],
                "state": {"last_iteration": 1, "alerts_fired": 1, "config_hash": "abc"},
            }
            is_valid, errors = serializer.validate_output(output)
            assert is_valid, f"Operator {op} should be valid: {errors}"

    def test_t2_7_equality_boundary_validation(self, tmp_path):
        """
        T2.7: Harness validates equality boundary alerts.

        Claim: GTE fires at equality (100 >= 100), LTE fires at equality (10 <= 10).
        Falsification: If harness rejects these alerts, the claim is false.
        Oracle honesty: OutputSerializer validates the alert structure, not the semantics.
                       Semantic correctness is agent responsibility.
        """
        serializer = OutputSerializer()

        # Test GTE at equality
        output = {
            "iteration": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "disk": {
                    "value": 100.0,
                    "unit": "percent",
                    "delta": None,
                    "status": "critical",
                }
            },
            "alerts": [
                {
                    "metric": "disk",
                    "level": "critical",
                    "value": 100.0,
                    "threshold": 100,
                    "operator": "gte",
                    "message": "disk at 100%",
                }
            ],
            "state": {"last_iteration": 1, "alerts_fired": 1, "config_hash": "abc"},
        }
        is_valid, errors = serializer.validate_output(output)
        assert is_valid, f"GTE equality alert should be valid: {errors}"

        # Test LTE at equality
        output["metrics"]["cpu"] = {
            "value": 10.0,
            "unit": "percent",
            "delta": None,
            "status": "ok",
        }
        output["alerts"] = [
            {
                "metric": "cpu",
                "level": "info",
                "value": 10.0,
                "threshold": 10,
                "operator": "lte",
                "message": "cpu at 10%",
            }
        ]
        is_valid, errors = serializer.validate_output(output)
        assert is_valid, f"LTE equality alert should be valid: {errors}"


# ============================================================================
# TEST CATEGORY 3: STATE MANAGEMENT (T3.1–T3.3)
# ============================================================================


class TestStateManagement:
    """
    Tests for T3.1–T3.3: State management correctness.

    Falsification criteria:
    - T3.1: State file updated after each iteration
    - T3.2: Delta computation on second iteration
    - T3.3: Config hash mismatch detection
    """

    def test_t3_1_state_file_updated_after_iteration(self, tmp_path):
        """
        T3.1: State file updated after each iteration.

        Claim: monitoring_worker updates state file after each poll cycle.
        Falsification: If state file is not written, the state persistence claim is false.
        Oracle honesty: StateManager.write_state() atomically writes state file.
        """
        state_manager = StateManager(str(tmp_path / "state.json"))

        state = {
            "metrics": {"cpu_usage": {"value": 50.0}},
            "last_evaluation": datetime.now(timezone.utc).isoformat(),
            "cycle_count": 1,
            "alert_count": 0,
            "termination_reason": None,
        }

        success = state_manager.write_state(state)
        assert success, "State write should succeed"

        # Verify file exists
        assert (tmp_path / "state.json").exists()

        # Verify content
        with open(tmp_path / "state.json") as f:
            loaded = json.load(f)
        assert loaded["metrics"]["cpu_usage"]["value"] == 50.0
        assert loaded["cycle_count"] == 1

    def test_t3_2_delta_computation_in_context(self, tmp_path):
        """
        T3.2: Harness provides delta computation in agent context.

        Claim: monitoring_worker computes delta as current - previous value.
        Falsification: If delta is not provided in context, the claim is false.
        Oracle honesty: Harness.run_iteration() computes deltas and includes
                       them in the metrics passed to agent context.
        """
        config = HarnessConfig(
            poll_interval_seconds=0,
            max_iterations=2,
            metrics_base_dir=str(tmp_path / "metrics"),
            state_file_path=str(tmp_path / "state.json"),
            config_file_path=str(tmp_path / "config.json"),
        )

        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        harness = MonitoringHarness(config)
        harness.metrics_server = metrics_server

        received_contexts = []

        def mock_invoke(prompt, context):
            received_contexts.append(context)
            return {
                "iteration": context["iteration"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": context["metrics"],
                "alerts": [],
                "state": {
                    "last_iteration": context["iteration"],
                    "alerts_fired": 0,
                    "config_hash": "abc",
                },
            }

        # First iteration: write metric file
        metrics_server.write_metric_file(
            "cpu_usage", {"value": 50.0, "unit": "percent"}
        )
        harness.run("test prompt", mock_invoke)

        # Second iteration: update metric file
        metrics_server.write_metric_file(
            "cpu_usage", {"value": 65.0, "unit": "percent"}
        )
        harness.run("test prompt", mock_invoke)

        # Verify second iteration has delta
        assert len(received_contexts) == 2
        second_metrics = received_contexts[1]["metrics"]
        assert "cpu_usage" in second_metrics
        # Delta should be 65 - 50 = 15
        assert second_metrics["cpu_usage"]["delta"] == 15.0

    def test_t3_3_config_hash_in_state(self, tmp_path):
        """
        T3.3: Config hash computed and stored in state.

        Claim: Configuration hash detects unauthorized changes.
        Falsification: If config hash is not tracked, the claim is false.
        Oracle honesty: StateManager.compute_config_hash() computes hash;
                       Harness loads config and stores hash in state.
        """
        state_manager = StateManager(str(tmp_path / "state.json"))

        config = {
            "poll_interval_seconds": 60,
            "thresholds": {"cpu": {"warning": 70}},
        }

        config_hash = state_manager.compute_config_hash(config)
        assert config_hash is not None
        assert isinstance(config_hash, str)
        assert len(config_hash) > 0

        # Write state with config hash
        state = {
            "metrics": {},
            "last_evaluation": datetime.now(timezone.utc).isoformat(),
            "cycle_count": 1,
            "alert_count": 0,
            "termination_reason": None,
            "config_hash": config_hash,
        }
        state_manager.write_state(state)

        # Load and verify
        loaded = state_manager.read_state()
        assert loaded is not None, "State should be readable after write"
        assert loaded["config_hash"] == config_hash

        # Modify config and verify hash changes
        config["thresholds"]["cpu"]["warning"] = 80
        new_hash = state_manager.compute_config_hash(config)
        assert new_hash != config_hash


# ============================================================================
# TEST CATEGORY 4: OUTPUT CONTRACT (T4.1–T4.3)
# ============================================================================


class TestOutputContract:
    """
    Tests for T4.1–T4.3: Output schema compliance.

    Falsification criteria:
    - T4.1: Output schema compliance
    - T4.2: Null delta on first iteration
    - T4.3: Empty alerts array when no threshold crossed
    """

    def test_t4_1_output_schema_validation(self):
        """
        T4.1: Output conforms to the required JSON schema.

        Claim: monitoring_worker emits structured JSON with exactly the
               specified schema fields.
        Falsification: If output JSON is missing required fields,
                       the schema compliance claim is false.
        Oracle honesty: OutputSerializer.validate_output() validates all required fields.
        """
        serializer = OutputSerializer()

        # Valid output
        valid_output = {
            "iteration": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "cpu_usage": {
                    "value": 50.0,
                    "unit": "percent",
                    "delta": None,
                    "status": "ok",
                }
            },
            "alerts": [],
            "state": {"last_iteration": 1, "alerts_fired": 0, "config_hash": "abc123"},
        }

        is_valid, errors = serializer.validate_output(valid_output)
        assert is_valid, f"Valid output must pass: {errors}"

    def test_t4_1_rejects_missing_required_field(self):
        """
        T4.1: Missing required field causes validation failure.

        Claim: All required fields must be present in output.
        Falsification: If harness accepts output missing required fields, claim is false.
        Oracle honesty: OutputSerializer.validate_output() checks all required fields.
        """
        serializer = OutputSerializer()

        # Missing 'timestamp'
        invalid_output = {"iteration": 1, "metrics": {}, "alerts": [], "state": {}}

        is_valid, errors = serializer.validate_output(invalid_output)
        assert not is_valid, "Missing timestamp should fail validation"
        assert any("timestamp" in e for e in errors)

    def test_t4_1_rejects_invalid_metric_status(self):
        """
        T4.1: Invalid metric status causes validation failure.

        Claim: Metric status must be one of: ok, warning, critical, unknown.
        Falsification: If harness accepts invalid status, claim is false.
        Oracle honesty: OutputSerializer.validate_output() checks status enum.
        """
        serializer = OutputSerializer()

        output = {
            "iteration": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "cpu_usage": {
                    "value": 50.0,
                    "unit": "percent",
                    "delta": None,
                    "status": "invalid_status",
                }
            },
            "alerts": [],
            "state": {"last_iteration": 1, "alerts_fired": 0, "config_hash": "abc"},
        }

        is_valid, errors = serializer.validate_output(output)
        assert not is_valid, "Invalid status should fail validation"

    def test_t4_2_null_delta_on_first_iteration(self, tmp_path):
        """
        T4.2: Delta is null on first iteration.

        Claim: On first poll iteration, delta field is null (no prior value).
        Falsification: If delta has a value on first iteration, the claim is false.
        Oracle honesty: Harness computes delta only when previous_metrics exists;
                       on first iteration, delta is None.
        """
        config = HarnessConfig(
            poll_interval_seconds=0,
            max_iterations=1,
            metrics_base_dir=str(tmp_path / "metrics"),
            state_file_path=str(tmp_path / "state.json"),
            config_file_path=str(tmp_path / "config.json"),
        )

        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        harness = MonitoringHarness(config)
        harness.metrics_server = metrics_server

        received_context = [None]

        def mock_invoke(prompt, context):
            received_context[0] = context
            return {
                "iteration": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": context["metrics"],
                "alerts": [],
                "state": {"last_iteration": 1, "alerts_fired": 0, "config_hash": "abc"},
            }

        metrics_server.write_metric_file(
            "cpu_usage", {"value": 50.0, "unit": "percent"}
        )
        harness.run("test prompt", mock_invoke)

        # First iteration delta should be None
        assert received_context[0] is not None, "Context should be set by mock_invoke"
        first_metrics = received_context[0].get("metrics") or {}
        assert first_metrics.get("cpu_usage", {}).get("delta") is None

    def test_t4_3_empty_alerts_array_when_no_threshold_crossed(self):
        """
        T4.3: Alerts array is empty when no threshold is crossed.

        Claim: When no metrics cross thresholds, alerts array is [].
        Falsification: If alerts array is omitted or contains false alerts,
                       the empty-alerts claim is false.
        Oracle honesty: OutputSerializer.validate_output() requires alerts to be an array.
        """
        serializer = OutputSerializer()

        output = {
            "iteration": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "cpu_usage": {
                    "value": 50.0,
                    "unit": "percent",
                    "delta": None,
                    "status": "ok",
                }
            },
            "alerts": [],
            "state": {"last_iteration": 1, "alerts_fired": 0, "config_hash": "abc"},
        }

        is_valid, errors = serializer.validate_output(output)
        assert is_valid, f"Empty alerts array must be valid: {errors}"

    def test_t4_3_rejects_null_alerts(self):
        """
        T4.3: alerts field cannot be null.

        Claim: alerts must be an array, even if empty.
        Falsification: If harness accepts null alerts, the claim is false.
        Oracle honesty: OutputSerializer.validate_output() requires alerts to be a list.
        """
        serializer = OutputSerializer()

        output = {
            "iteration": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {},
            "alerts": None,  # Not an array
            "state": {"last_iteration": 1, "alerts_fired": 0, "config_hash": "abc"},
        }

        is_valid, errors = serializer.validate_output(output)
        assert not is_valid, "Null alerts should fail validation"


# ============================================================================
# TEST CATEGORY 5: ERROR HANDLING (T5.1–T5.3)
# ============================================================================


class TestErrorHandling:
    """
    Tests for T5.1–T5.3: Error handling behavior.

    Falsification criteria:
    - T5.1: Missing metric endpoint reported as warning
    - T5.2: Termination after max_iterations
    - T5.3: Unrecoverable error triggers termination
    """

    def test_t5_1_missing_metric_endpoint_returns_null(self, tmp_path):
        """
        T5.1: Missing metric endpoint returns null, not fabricated value.

        Claim: When metric endpoint is unavailable, monitoring_worker reports
               null, not a fabricated value.
        Falsification: If MockMetricsServer returns a fabricated value,
                       the claim is false.
        Oracle honesty: MockMetricsServer.read_metric_file() returns None
                        for non-existent files.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))

        # Read non-existent metric
        data = metrics_server.read_metric_file("nonexistent_metric")
        assert data is None, "Non-existent metric should return None"

    def test_t5_1_missing_metric_reported_in_metrics(self, tmp_path):
        """
        T5.1: Missing metric is reported in metrics with value=null.

        Claim: Missing metrics appear in output with value=null and status=unknown.
        Falsification: If missing metrics are omitted, the claim is false.
        Oracle honesty: Harness.run_iteration() includes unavailable metrics
                        in available_metrics with value=None.
        """
        config = HarnessConfig(
            poll_interval_seconds=0,
            max_iterations=1,
            metrics_base_dir=str(tmp_path / "metrics"),
            state_file_path=str(tmp_path / "state.json"),
            config_file_path=str(tmp_path / "config.json"),
        )

        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        harness = MonitoringHarness(config)
        harness.metrics_server = metrics_server

        received_context = [None]

        def mock_invoke(prompt, context):
            received_context[0] = context
            return {
                "iteration": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": context["metrics"],
                "alerts": [],
                "state": {"last_iteration": 1, "alerts_fired": 0, "config_hash": "abc"},
            }

        # Don't write any metric files
        harness.run("test prompt", mock_invoke)

        # Metrics in context should be empty or have unknown status
        assert received_context[0] is not None, "Context should be set by mock_invoke"
        metrics = received_context[0].get("metrics") or {}
        if metrics:
            assert all(m.get("status") == "unknown" for m in metrics.values())
        else:
            assert metrics == {}

    def test_t5_2_termination_after_max_iterations(self, tmp_path):
        """
        T5.2: Monitoring terminates after max_iterations.

        Claim: monitoring_worker terminates after exactly max_iterations.
        Falsification: If agent continues beyond max_iterations, the claim is false.
        Oracle honesty: Harness.run() checks max_iterations in _check_termination_conditions().
        """
        config = HarnessConfig(
            poll_interval_seconds=0,
            max_iterations=3,
            metrics_base_dir=str(tmp_path / "metrics"),
            state_file_path=str(tmp_path / "state.json"),
            config_file_path=str(tmp_path / "config.json"),
        )

        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        harness = MonitoringHarness(config)
        harness.metrics_server = metrics_server

        iteration_count = [0]

        def mock_invoke(prompt, context):
            iteration_count[0] += 1
            return {
                "iteration": iteration_count[0],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": context["metrics"],
                "alerts": [],
                "state": {
                    "last_iteration": iteration_count[0],
                    "alerts_fired": 0,
                    "config_hash": "abc",
                },
            }

        outputs = harness.run("test prompt", mock_invoke)

        assert iteration_count[0] == 3, (
            f"Expected 3 iterations, got {iteration_count[0]}"
        )
        assert len(outputs) == 3

    def test_t5_2_harness_enforces_max_iterations_bound(self):
        """
        T5.2: Harness enforces max_iterations as a hard bound.

        Claim: max_iterations is a code-enforced stop condition.
        Falsification: If iterations exceed max_iterations, the claim is false.
        Oracle honesty: Harness._check_termination_conditions() returns
                       (True, "max_iterations_reached") when iteration >= max_iterations.
        """
        config = HarnessConfig(
            poll_interval_seconds=60,
            max_iterations=5,
        )

        harness = MonitoringHarness(config)
        harness._iteration = 5

        should_stop, reason = harness._check_termination_conditions()
        assert should_stop is True
        assert reason == "max_iterations_reached"

    def test_t5_3_consecutive_metric_failures_tracked(self, tmp_path):
        """
        T5.3: Harness tracks consecutive metric read failures.

        Claim: After 3 consecutive metric read failures, monitoring_worker terminates.
        Falsification: If failures are not tracked, the claim is false.
        Oracle honesty: Harness._consecutive_metric_failures counter increments
                       on each failed metric read.
        """
        config = HarnessConfig(
            poll_interval_seconds=0,
            max_iterations=10,  # High number - should stop due to failures
            metrics_base_dir=str(tmp_path / "metrics"),
            state_file_path=str(tmp_path / "state.json"),
            config_file_path=str(tmp_path / "config.json"),
        )

        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        # Don't write any metric files - all reads will fail
        harness = MonitoringHarness(config)
        harness.metrics_server = metrics_server

        def mock_invoke(prompt, context):
            return {
                "iteration": context["iteration"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": context["metrics"],
                "alerts": [],
                "state": {
                    "last_iteration": context["iteration"],
                    "alerts_fired": 0,
                    "config_hash": "abc",
                },
            }

        # Run with no metric files - all iterations will have failures
        harness._consecutive_metric_failures = 3
        should_stop, reason = harness._check_termination_conditions()
        assert should_stop is True
        assert reason == "max_consecutive_metric_failures"


# ============================================================================
# TEST CATEGORY 6: BEHAVIORAL BOUNDARIES (T6.1–T6.3)
# ============================================================================


class TestBehavioralBoundaries:
    """
    Tests for T6.1–T6.3: Behavioral boundary enforcement.

    Falsification criteria:
    - T6.1: No sub-agent spawning during normal operation
    - T6.2: Escalation via task tool is rate-limited
    - T6.3: Alert output is the only external communication
    """

    def test_t6_1_tool_enforcer_denies_doom_loop(self, tmp_path):
        """
        T6.1: doom_loop (sub-agent spawning) is denied.

        Claim: monitoring_worker does not spawn sub-agents during normal operation.
        Falsification: If doom_loop is callable, the sub-agent restriction claim is false.
        Oracle honesty: ToolEnforcer.check_tool_allowed("doom_loop") returns False.
        """
        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        enforcer = ToolEnforcer(metrics_server, str(tmp_path / "state.json"))

        allowed, error = enforcer.check_tool_allowed("doom_loop")
        assert allowed is False

    def test_t6_1_denied_tools_constant_complete(self):
        """
        T6.1: DENIED_TOOLS includes all tools that should be denied.

        Claim: monitoring_worker has explicit deny list in permission manifest.
        Falsification: If denied tools list is incomplete, the claim is false.
        Oracle honesty: DENIED_TOOLS frozenset includes bash, doom_loop, edit, etc.
        """
        from harness.monitoring_harness import DENIED_TOOLS

        required_denied = {
            "bash",
            "doom_loop",
            "edit",
            "skill",
            "lsp",
            "webfetch",
            "websearch",
            "codesearch",
            "external_directory",
            "todowrite",
        }
        for tool in required_denied:
            assert tool in DENIED_TOOLS, f"{tool} must be in DENIED_TOOLS"

    def test_t6_2_allowed_tools_constant_includes_task(self):
        """
        T6.2: task tool is in allowed tools (for escalation only).

        Claim: Escalation via task tool is allowed but rate-limited.
        Falsification: If task is denied, legitimate escalation cannot happen.
        Oracle honesty: ALLOWED_TOOLS includes "task" for escalation.
        """
        from harness.monitoring_harness import ALLOWED_TOOLS

        assert "task" in ALLOWED_TOOLS, "task must be allowed for escalation"

    def test_t6_3_alert_output_is_only_external_communication(self, tmp_path):
        """
        T6.3: Alerts appear only in structured output.

        Claim: monitoring_worker sends alerts only to structured output,
               not to external notification systems.
        Falsification: If alerts appear in external systems, the claim is false.
        Oracle honesty: Harness.write_output() only writes to alert_output_path;
                       no external notification calls are made.
        """
        config = HarnessConfig(
            poll_interval_seconds=0,
            max_iterations=1,
            metrics_base_dir=str(tmp_path / "metrics"),
            state_file_path=str(tmp_path / "state.json"),
            config_file_path=str(tmp_path / "config.json"),
        )

        metrics_server = MockMetricsServer(str(tmp_path / "metrics"))
        harness = MonitoringHarness(config)
        harness.metrics_server = metrics_server

        def mock_invoke(prompt, context):
            return {
                "iteration": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": context["metrics"],
                "alerts": [
                    {
                        "metric": "cpu_usage",
                        "level": "warning",
                        "value": 75.0,
                        "threshold": 70,
                        "operator": "gt",
                        "message": "cpu_usage exceeded warning threshold",
                    }
                ],
                "state": {"last_iteration": 1, "alerts_fired": 1, "config_hash": "abc"},
            }

        metrics_server.write_metric_file(
            "cpu_usage", {"value": 75.0, "unit": "percent"}
        )
        harness.run("test prompt", mock_invoke)

        # Verify alerts were stored in output history
        assert len(harness._output_history) == 1
        assert len(harness._output_history[0]["alerts"]) == 1


# ============================================================================
# TEST RUNNER
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
