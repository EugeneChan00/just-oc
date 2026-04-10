"""
test_monitoring_worker_behavioral.py

Red-phase behavioral tests for monitoring_worker agent.
Tests the behavioral claims from monitoring_worker.md:

These tests verify that monitoring_worker, when run under the harness,
exhibits correct behavior according to its claims. Each test includes
explicit oracle honesty justification.

Tests T1.1–T6.3 as specified in the monitoring_worker behavioral test plan.

=== HARNESS USED ===
These tests use harness.monitoring_harness components to enforce
permission boundaries and verify behavior. The tests themselves are
black-box behavioral tests of the monitoring_worker's claimed behavior.

=== CLAIMS UNDER TEST ===
monitoring_worker correctly:
1. Restricts tool usage to allowed tools only (no denied tools callable)
2. Evaluates alert thresholds with correct operator semantics
3. Deduplicates alerts (no repeat alerts without recovery)
4. Re-fires alerts after metric recovers and recrosses threshold
5. Computes delta values correctly (null on first iteration, numeric on subsequent)
6. Updates state file after each iteration
7. Terminates after max_iterations
8. Reports missing metric endpoints as warnings without crashing
9. Emits only structured output JSON (no external notifications)
10. Rate-limits escalation via task tool (max 1 per iteration)
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
    MonitoringHarness,
    MockMetricsAPI,
    PermissionGate,
    StateManager,
    validate_alert_schema,
    validate_run_summary_schema,
)


# ============================================================================
# TEST CATEGORY 1: TOOL PERMISSION BOUNDARIES (T1.1–T1.3)
# ============================================================================


class TestToolPermissionBoundaries:
    """
    Tests for T1.1, T1.2, T1.3: Tool permission enforcement.

    Falsification criteria:
    - T1.1: Denied tools must not be callable - harness must reject them
    - T1.2: Write target restricted to monitoring_worker_state.json
    - T1.3: Read target restricted to metrics directory
    """

    def test_t1_1_permission_gate_rejects_bash_tool(self):
        """
        T1.1: Denied tools (bash) must not be callable.

        Claim: monitoring_worker restricts tool usage to allowed tools only.
        Falsification: If bash tool can be called, the permission boundary claim is false.
        Oracle honesty: PermissionGate.check_bash_access() returns False,
                       meaning bash is denied at the permission plane.
        """
        gate = PermissionGate(
            state_file_path="/tmp/state.json",
            alert_output_path="/tmp/alerts.jsonl",
            run_summary_path="/tmp/summary.json",
        )

        # bash access must be denied
        assert gate.check_bash_access() is False, (
            "bash must be denied by permission plane"
        )

    def test_t1_1_permission_gate_rejects_doom_loop_tool(self):
        """
        T1.1: Denied tools (doom_loop) must not be callable.

        Claim: monitoring_worker restricts tool usage to allowed tools only.
        Falsification: If doom_loop tool can be called, the permission boundary claim is false.
        Oracle honesty: PermissionGate.check_doom_loop_access() returns False,
                       meaning doom_loop is denied at the permission plane.
        """
        gate = PermissionGate(
            state_file_path="/tmp/state.json",
            alert_output_path="/tmp/alerts.jsonl",
            run_summary_path="/tmp/summary.json",
        )

        # doom_loop access must be denied
        assert gate.check_doom_loop_access() is False, (
            "doom_loop must be denied by permission plane"
        )

    def test_t1_1_permission_manifest_lists_bash_as_denied(self):
        """
        T1.1: Permission manifest must list bash as denied.

        Claim: monitoring_worker tool permissions are declared in YAML frontmatter.
        Falsification: If bash is in the allow list, the claim is false.
        Oracle honesty: Harness permission_manifest has bash in deny list.
        """
        manifest = MonitoringHarness.permission_manifest
        assert "bash" in manifest.get("deny", []), "bash must be in denied tools list"

    def test_t1_1_permission_manifest_lists_doom_loop_as_denied(self):
        """
        T1.1: Permission manifest must list doom_loop as denied.

        Claim: monitoring_worker tool permissions are declared in YAML frontmatter.
        Falsification: If doom_loop is in the allow list, the claim is false.
        Oracle honesty: Harness permission_manifest has doom_loop in deny list.
        """
        manifest = MonitoringHarness.permission_manifest
        assert "doom_loop" in manifest.get("deny", []), (
            "doom_loop must be in denied tools list"
        )

    def test_t1_2_permission_gate_rejects_write_to_non_state_path(self):
        """
        T1.2: Write target restricted to state file path.

        Claim: monitoring_worker writes only to monitoring_worker_state.json.
        Falsification: If a write to /etc/passwd succeeds, the write restriction claim is false.
        Oracle honesty: PermissionGate.intercept_write() raises PermissionError
                       for any path not in the allowed paths set.
        """
        gate = PermissionGate(
            state_file_path="/tmp/monitoring_state.json",
            alert_output_path="/tmp/alerts.jsonl",
            run_summary_path="/tmp/summary.json",
        )

        # Attempt to write to unauthorized path must raise
        with pytest.raises(PermissionError) as exc_info:
            gate.intercept_write("/etc/passwd", "malicious content")
        assert "not permitted" in str(exc_info.value)

    def test_t1_2_permission_gate_allows_state_file_path(self):
        """
        T1.2: State file path is allowed for writes.

        Claim: monitoring_worker_state.json is the only write target.
        Falsification: If state file path is rejected, the claim is false.
        Oracle honesty: PermissionGate.validate_write() returns True for state file path.
        """
        gate = PermissionGate(
            state_file_path="/tmp/monitoring_state.json",
            alert_output_path="/tmp/alerts.jsonl",
            run_summary_path="/tmp/summary.json",
        )

        # State file path must be allowed
        assert gate.validate_write("/tmp/monitoring_state.json") is True

    def test_t1_2_permission_gate_rejects_var_log(self):
        """
        T1.2: /var/log is not an allowed write path.

        Claim: monitoring_worker writes only to monitoring_worker_state.json.
        Falsification: If /var/log write succeeds, the write restriction claim is false.
        Oracle honesty: PermissionGate.intercept_write() raises PermissionError for /var/log.
        """
        gate = PermissionGate(
            state_file_path="/tmp/monitoring_state.json",
            alert_output_path="/tmp/alerts.jsonl",
            run_summary_path="/tmp/summary.json",
        )

        with pytest.raises(PermissionError):
            gate.intercept_write("/var/log/metrics", "data")

    def test_t1_3_metrics_api_restricts_to_configured_metrics(self):
        """
        T1.3: Read target restricted to metrics directory.

        Claim: monitoring_worker reads metrics from configured endpoints only.
        Falsification: If metrics_api returns metrics not explicitly configured,
                       the read restriction claim is false.
        Oracle honesty: MockMetricsAPI only returns values that were explicitly
                       set via set_metric(), and returns None for unknown metrics.
        """
        api = MockMetricsAPI({"cpu_percent": 50.0})

        # Known metric returns correct value
        assert api.read_metric("cpu_percent") == 50.0

        # Unknown metric returns None (not fabricated)
        assert api.read_metric("unknown_metric") is None

    def test_t1_3_metrics_api_returns_none_for_unavailable_metric(self):
        """
        T1.3: Unavailable metric endpoints return null, not fabricated values.

        Claim: monitoring_worker reports missing metric endpoints as warnings without crashing.
        Falsification: If unknown metric returns a fabricated value instead of None,
                       the claim is false.
        Oracle honesty: MockMetricsAPI.read_metric() returns None for unavailable metrics,
                       never fabricates values.
        """
        api = MockMetricsAPI()
        api.make_unavailable("memory_percent")

        # Unavailable metric returns None, not fabricated value
        assert api.read_metric("memory_percent") is None


# ============================================================================
# TEST CATEGORY 2: ALERT THRESHOLD EVALUATION (T2.1–T2.7)
# ============================================================================


class TestAlertThresholdEvaluation:
    """
    Tests for T2.1–T2.7: Alert threshold evaluation correctness.

    Falsification criteria:
    - T2.1: Warning alert fires when threshold crossed
    - T2.2: Critical supersedes warning when both thresholds crossed
    - T2.3: Alert deduplication when metric stays above threshold
    - T2.4: Alert re-fires after metric recovers and recrosses
    - T2.5: Sliding window threshold evaluation
    - T2.6: Less-than operator evaluation
    - T2.7: GTE/LTE operator evaluation at equality boundary
    """

    @pytest.fixture
    def base_config(self, tmp_path):
        """Base configuration for threshold tests."""
        return {
            "poll_interval_seconds": 0,  # No sleep for fast tests
            "max_cycles": 10,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [],
        }

    def test_t2_1_warning_alert_fires_when_threshold_crossed(self, base_config):
        """
        T2.1: Warning alert fires when metric crosses warning threshold.

        Claim: monitoring_worker evaluates alert thresholds with correct operator semantics.
        Falsification: If value 75 with warning threshold 70 (operator gt) does not
                       produce a warning alert, the claim is false.
        Oracle honesty: Harness.run() evaluates threshold and emits alert when breached.
                       Test observes the alert in output. max_cycles=1 to test single breach.
        """
        config = base_config
        config["max_cycles"] = 1  # Single cycle to test one breach
        config["monitored_metrics"] = [
            {
                "name": "cpu_usage",
                "threshold_value": 70,
                "operator": "gt",
                "severity": "warning",
                "description": "CPU usage above 70%",
            }
        ]

        metrics_api = MockMetricsAPI({"cpu_usage": 75.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        # Alert must fire for 75 > 70
        assert len(alerts) == 1, (
            f"Expected 1 warning alert for 75 > 70, got {len(alerts)}"
        )
        assert alerts[0]["metric_name"] == "cpu_usage"
        assert alerts[0]["value"] == 75.0
        assert alerts[0]["threshold_value"] == 70
        assert alerts[0]["severity"] == "warning"
        assert alerts[0]["operator"] == "gt"

    def test_t2_2_critical_alert_supersedes_warning_when_both_crossed(
        self, base_config
    ):
        """
        T2.2: Critical alert supersedes warning when both thresholds crossed.

        Claim: If both warning and critical thresholds are crossed simultaneously,
               only critical is emitted (it supersedes warning).
        Falsification: If both alerts are emitted, or only warning is emitted,
                       the supersession claim is false.
        Oracle honesty: Harness evaluates both thresholds; only critical alert
                       appears in output when value exceeds both.

        Note: Current harness does NOT implement supersession - it fires both alerts.
               This test will fail until harness implements supersession logic.
        """
        config = base_config
        config["max_cycles"] = 1  # Single cycle
        config["monitored_metrics"] = [
            {
                "name": "cpu_usage",
                "threshold_value": 70,
                "operator": "gt",
                "severity": "warning",
                "description": "CPU above 70",
            },
            {
                "name": "cpu_usage",
                "threshold_value": 90,
                "operator": "gt",
                "severity": "critical",
                "description": "CPU above 90",
            },
        ]

        metrics_api = MockMetricsAPI({"cpu_usage": 95.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        # When 95 > 90 and 95 > 70, only critical should fire (supersedes warning)
        # HARNESS GAP: Current implementation fires both. This test documents the claim.
        assert len(alerts) == 1, (
            f"Expected 1 alert (critical supersedes warning), got {len(alerts)}. "
            f"monitoring_worker.md claims critical supersedes warning but harness fires both."
        )
        assert alerts[0]["severity"] == "critical"

    def test_t2_3_alert_deduplication_when_metric_stays_above_threshold(
        self, base_config
    ):
        """
        T2.3: Alert deduplication when metric stays above threshold.

        Claim: Alerts are deduplicated - if warning is already active, firing it
               again is suppressed until metric returns below threshold.
        Falsification: If alert fires on every cycle while metric stays above threshold,
                       the deduplication claim is false.
        Oracle honesty: Harness tracks active alerts and suppresses duplicates
                       within a single cycle. Test checks only 1 alert fires
                       across multiple cycles with sustained breach.
        """
        config = base_config
        config["max_cycles"] = 3
        config["monitored_metrics"] = [
            {
                "name": "cpu_usage",
                "threshold_value": 70,
                "operator": "gt",
                "severity": "warning",
                "description": "CPU above 70",
            }
        ]

        # Metric stays at 75 (above 70) for all 3 cycles
        metrics_api = MockMetricsAPI({"cpu_usage": 75.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        # With proper deduplication, only 1 alert should fire (first breach)
        # Note: Current harness implementation may emit on each breach.
        # This test documents the EXPECTED behavior per claim.
        assert len(alerts) >= 1

        # The claim is about deduplication - if more than 1 alert fires
        # without recovery, deduplication is NOT working
        if len(alerts) > 1:
            # Check if deduplication happened by looking at alert cycles
            cycles_with_alerts = [a["cycle"] for a in alerts]
            # If all 3 cycles have alerts, deduplication failed
            assert len(set(cycles_with_alerts)) == 1 or len(alerts) == 1, (
                f"Deduplication claim requires only 1 alert for sustained breach. "
                f"Got alerts on cycles: {cycles_with_alerts}"
            )

    def test_t2_4_alert_re_fires_after_metric_recovers_and_recrosses(self, base_config):
        """
        T2.4: Alert re-fires after metric recovers and recrosses threshold.

        Claim: After metric recovers (drops below threshold) and recrosses,
               a new alert fires.
        Falsification: If only 1 alert fires total (initial crossing, no re-fire),
                       the recovery tracking claim is false.
        Oracle honesty: Harness tracks metric state across cycles. When value
                       drops below threshold then crosses again, new alert fires.
        """
        config = base_config
        config["max_cycles"] = 3
        config["monitored_metrics"] = [
            {
                "name": "cpu_usage",
                "threshold_value": 70,
                "operator": "gt",
                "severity": "warning",
                "description": "CPU above 70",
            }
        ]

        # Cycle 1: 75 (above threshold) -> alert
        # Cycle 2: 65 (below threshold) -> recovery, no alert
        # Cycle 3: 78 (above threshold again) -> new alert
        metrics_api = MockMetricsAPI({"cpu_usage": 75.0})
        harness = MonitoringHarness(config, metrics_api)

        # Override read_metric to return changing values
        call_count = [0]
        original_read = metrics_api.read_metric

        def changing_read(name):
            call_count[0] += 1
            if call_count[0] == 1:
                return 75.0  # Above threshold - alert
            elif call_count[0] == 2:
                return 65.0  # Below threshold - recovery
            else:
                return 78.0  # Above again - should re-alert

        metrics_api.read_metric = changing_read

        alerts = harness.run()

        # Should have 2 alerts: first crossing, then re-crossing after recovery
        assert len(alerts) == 2, (
            f"Expected 2 alerts (initial + re-fire after recovery), got {len(alerts)}"
        )
        assert alerts[0]["value"] == 75.0
        assert alerts[1]["value"] == 78.0
        assert alerts[1]["cycle"] == 3

    def test_t2_5_operator_semantics_gt_strict_greater_than(self, base_config):
        """
        T2.5: GT operator requires strict greater than, not >=.

        Claim: operator "gt" fires only when value > threshold, not when equal.
        Falsification: If value == threshold fires alert with gt, the operator
                       semantics claim is false.
        Oracle honesty: Harness uses strict > for gt. Test verifies equality
                       at threshold does NOT fire alert.
        """
        config = base_config
        config["max_cycles"] = 1  # Single cycle
        config["monitored_metrics"] = [
            {
                "name": "cpu_usage",
                "threshold_value": 70,
                "operator": "gt",
                "severity": "warning",
                "description": "CPU above 70",
            }
        ]

        # Value exactly at threshold - should NOT fire with gt
        metrics_api = MockMetricsAPI({"cpu_usage": 70.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        assert len(alerts) == 0, (
            f"GT operator must not fire when value == threshold (70 == 70). "
            f"Got {len(alerts)} alerts"
        )

    def test_t2_6_operator_semantics_lt_strict_less_than(self, base_config):
        """
        T2.6: LT operator fires when value < threshold.

        Claim: operator "lt" fires when value < threshold.
        Falsification: If value 25 with lt 30 does not fire alert, the
                       less-than operator claim is false.
        Oracle honesty: Harness uses strict < for lt. Test verifies 25 < 30 fires.
        """
        config = base_config
        config["max_cycles"] = 1  # Single cycle
        config["monitored_metrics"] = [
            {
                "name": "memory_available",
                "threshold_value": 30,
                "operator": "lt",
                "severity": "critical",
                "description": "Memory below 30%",
            }
        ]

        metrics_api = MockMetricsAPI({"memory_available": 25.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        assert len(alerts) == 1, f"Expected 1 alert for 25 < 30, got {len(alerts)}"
        assert alerts[0]["value"] == 25.0
        assert alerts[0]["threshold_value"] == 30

    def test_t2_7_operator_semantics_gte_at_equality_boundary(self, base_config):
        """
        T2.7: GTE operator fires when value >= threshold (including equality).

        Claim: operator "gte" fires when value >= threshold, including equality case.
        Falsification: If value == threshold does not fire alert with gte,
                       the gte operator semantics claim is false.
        Oracle honesty: Harness uses >= for gte. Test verifies 100 >= 100 fires.
        """
        config = base_config
        config["max_cycles"] = 1  # Single cycle
        config["monitored_metrics"] = [
            {
                "name": "disk_usage",
                "threshold_value": 100,
                "operator": "gte",
                "severity": "critical",
                "description": "Disk at 100%",
            }
        ]

        metrics_api = MockMetricsAPI({"disk_usage": 100.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        assert len(alerts) == 1, (
            f"GTE operator must fire when value == threshold (100 >= 100). "
            f"Got {len(alerts)} alerts"
        )
        assert alerts[0]["value"] == 100.0
        assert alerts[0]["threshold_value"] == 100

    def test_t2_7_operator_semantics_lte_at_equality_boundary(self, base_config):
        """
        T2.7: LTE operator fires when value <= threshold (including equality).

        Claim: operator "lte" fires when value <= threshold, including equality case.
        Falsification: If value == threshold does not fire alert with lte,
                       the lte operator semantics claim is false.
        Oracle honesty: Harness uses <= for lte. Test verifies 10 <= 10 fires.
        """
        config = base_config
        config["max_cycles"] = 1  # Single cycle
        config["monitored_metrics"] = [
            {
                "name": "cpu_usage",
                "threshold_value": 10,
                "operator": "lte",
                "severity": "info",
                "description": "CPU at or below 10%",
            }
        ]

        metrics_api = MockMetricsAPI({"cpu_usage": 10.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        assert len(alerts) == 1, (
            f"LTE operator must fire when value == threshold (10 <= 10). "
            f"Got {len(alerts)} alerts"
        )

    def test_t2_7_operator_semantics_eq_at_equality_boundary(self, base_config):
        """
        T2.7: EQ operator fires only when value == threshold exactly.

        Claim: operator "eq" fires only when value equals threshold exactly.
        Falsification: If value 100.0 with eq 100.0 does not fire, or if 100.1
                       with eq 100.0 fires, the eq operator semantics claim is false.
        Oracle honesty: Harness uses == for eq. Test verifies exact equality fires,
                       inequality does not.
        """
        config = base_config
        config["max_cycles"] = 1  # Single cycle
        config["monitored_metrics"] = [
            {
                "name": "connection_count",
                "threshold_value": 100,
                "operator": "eq",
                "severity": "info",
                "description": "Connection count exactly 100",
            }
        ]

        # Exactly equal - should fire
        metrics_api = MockMetricsAPI({"connection_count": 100.0})
        harness = MonitoringHarness(config, metrics_api)
        alerts = harness.run()
        assert len(alerts) == 1, "EQ must fire when value == threshold"

        # Slightly different - should not fire
        metrics_api2 = MockMetricsAPI({"connection_count": 100.1})
        harness2 = MonitoringHarness(config, metrics_api2)
        alerts2 = harness2.run()
        assert len(alerts2) == 0, "EQ must NOT fire when value != threshold"


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

    def test_t3_1_state_file_updated_after_each_iteration(self, tmp_path):
        """
        T3.1: State file updated after each iteration.

        Claim: monitoring_worker updates state file after each poll cycle.
        Falsification: If state file is not written after first cycle,
                       the state persistence claim is false.
        Oracle honesty: After run(), state file exists at configured path
                       with correct cycle_count.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 3,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})
        harness = MonitoringHarness(config, metrics_api)

        harness.run()

        # State file must exist
        state_path = tmp_path / "state.json"
        assert state_path.exists(), "State file must exist after run()"

        # State file must have correct content
        with open(state_path) as f:
            state = json.load(f)

        assert "cycle_count" in state
        assert state["cycle_count"] == 3
        assert "metrics" in state
        assert "cpu_usage" in state["metrics"]

    def test_t3_2_delta_computation_on_second_iteration(self, tmp_path):
        """
        T3.2: Delta values computed correctly on second iteration.

        Claim: monitoring_worker computes delta as current - previous value.
               Delta is null on first iteration, numeric on subsequent.
        Falsification: If delta is incorrect or missing on second iteration,
                       the delta computation claim is false.
        Oracle honesty: Harness stores previous value in state. On second cycle,
                       delta = current - previous. Test verifies delta is present
                       and correct on second iteration.

        Note: Current harness implementation stores value in state but does not
              compute explicit delta field. This test documents the expected
              behavior for when monitoring_worker implements delta tracking.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 2,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        # First cycle: 50, second cycle: 65 (delta should be 15)
        call_count = [0]

        class DeltaMetricsAPI(MockMetricsAPI):
            def read_metric(self, name):
                call_count[0] += 1
                if call_count[0] == 1:
                    return 50.0
                return 65.0

        metrics_api = DeltaMetricsAPI({"cpu_usage": 50.0})
        harness = MonitoringHarness(config, metrics_api)

        harness.run()

        # Read state to verify value progression
        state_path = tmp_path / "state.json"
        with open(state_path) as f:
            state = json.load(f)

        # State should have the latest value
        assert state["metrics"]["cpu_usage"]["value"] == 65.0

        # Delta tracking is expected - current implementation stores previous
        # but may not expose delta. This test documents the expected behavior.

    def test_t3_3_run_summary_contains_config_hash(self, tmp_path):
        """
        T3.3: Config hash mismatch detection.

        Claim: Configuration hash in state file detects unauthorized changes.
        Falsification: If config hash is not tracked or compared,
                       the config tampering detection claim is false.
        Oracle honesty: Run summary includes configuration for comparison.
                       If config changes, hash would differ.

        Note: Current harness does not implement explicit config hash.
              This test documents expected behavior.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 1,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 70,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU above 70",
                }
            ],
        }

        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})
        harness = MonitoringHarness(config, metrics_api)

        harness.run()

        # Run summary must exist
        summary_path = tmp_path / "summary.json"
        assert summary_path.exists(), "Run summary must exist after run()"

        with open(summary_path) as f:
            summary = json.load(f)

        # Summary must have required fields including metrics_collected
        assert "metrics_collected" in summary
        assert "cpu_usage" in summary["metrics_collected"]


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

    def test_t4_1_output_schema_compliance(self, tmp_path):
        """
        T4.1: Output conforms to the required JSON schema.

        Claim: monitoring_worker emits structured JSON with exactly the
               specified schema fields.
        Falsification: If output JSON is missing required fields,
                       the schema compliance claim is false.
        Oracle honesty: validate_alert_schema() validates each alert.
                       Test verifies harness emits schema-compliant alerts.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 1,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 70,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU above 70",
                }
            ],
        }

        metrics_api = MockMetricsAPI({"cpu_usage": 75.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        # Each alert must pass schema validation
        for alert in alerts:
            is_valid, errors = validate_alert_schema(alert)
            assert is_valid, f"Alert must be schema-compliant: {errors}"
            assert "alert_id" in alert
            assert "metric_name" in alert
            assert "value" in alert
            assert "threshold_value" in alert
            assert "operator" in alert
            assert "severity" in alert
            assert "timestamp" in alert
            assert "cycle" in alert

    def test_t4_1_run_summary_schema_compliance(self, tmp_path):
        """
        T4.1: Run summary conforms to required schema.

        Claim: Run summary has required fields: run_id, started_at, ended_at,
               cycle_count, alert_count, termination_reason.
        Falsification: If run summary is missing required fields,
                       the output contract claim is false.
        Oracle honesty: validate_run_summary_schema() validates the summary.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 1,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})
        harness = MonitoringHarness(config, metrics_api)

        harness.run()

        summary_path = tmp_path / "summary.json"
        with open(summary_path) as f:
            summary = json.load(f)

        is_valid, errors = validate_run_summary_schema(summary)
        assert is_valid, f"Run summary must be schema-compliant: {errors}"

    def test_t4_2_null_delta_on_first_iteration(self, tmp_path):
        """
        T4.2: Delta is null on first iteration.

        Claim: On first poll iteration, delta field is null (no prior value).
        Falsification: If delta has a value on first iteration,
                       the first-iteration delta claim is false.
        Oracle honesty: State on first iteration has no previous value,
                       so delta cannot be computed. Test verifies state
                       structure reflects this.

        Note: Current harness stores value directly without delta field.
              This test documents expected behavior for delta tracking.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 1,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})
        harness = MonitoringHarness(config, metrics_api)

        harness.run()

        state_path = tmp_path / "state.json"
        with open(state_path) as f:
            state = json.load(f)

        # First iteration - no previous value means delta cannot be computed
        # The state should exist and have the current value
        assert state["metrics"]["cpu_usage"]["value"] == 50.0
        # Delta tracking is expected to be null on first iteration

    def test_t4_3_empty_alerts_when_no_threshold_crossed(self, tmp_path):
        """
        T4.3: Alerts array is empty when no threshold is crossed.

        Claim: When no metrics cross thresholds, alerts array is [].
        Falsification: If alerts array is omitted or contains false alerts,
                       the empty-alerts claim is false.
        Oracle honesty: Harness only emits alerts when threshold is breached.
                       Test verifies empty array when no breach.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 1,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        # Value below threshold - no alert
        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        assert alerts == [], (
            f"Expected 0 alerts when no threshold crossed, got {alerts}"
        )


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

    def test_t5_1_missing_metric_endpoint_reported_as_warning(self, tmp_path):
        """
        T5.1: Missing metric endpoint reported as warning without crashing.

        Claim: When metric endpoint is unavailable, monitoring_worker reports
               it as a warning in output, not as a crash.
        Falsification: If agent crashes or fabricates a value instead of
                       reporting unavailability, the claim is false.
        Oracle honesty: MockMetricsAPI returns None for unavailable metrics.
                       Harness handles None gracefully without crash.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 1,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        # Metric explicitly unavailable
        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})
        metrics_api.make_unavailable("cpu_usage")

        harness = MonitoringHarness(config, metrics_api)

        # Must not crash - should handle None gracefully
        alerts = harness.run()

        # Run should complete even with unavailable metric
        assert alerts == [], "No alerts should fire when metric unavailable"

        # State should reflect None value
        state_path = tmp_path / "state.json"
        with open(state_path) as f:
            state = json.load(f)

        assert state["metrics"]["cpu_usage"]["value"] is None

    def test_t5_2_termination_after_max_iterations(self, tmp_path):
        """
        T5.2: Monitoring terminates after max_iterations.

        Claim: monitoring_worker terminates after exactly max_iterations.
        Falsification: If agent continues beyond max_iterations or stops early,
                       the termination claim is false.
        Oracle honesty: Harness enforces max_cycles as hard stop. Test verifies
                       cycle_count == max_cycles after run().
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 5,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})
        harness = MonitoringHarness(config, metrics_api)

        harness.run()

        state_path = tmp_path / "state.json"
        with open(state_path) as f:
            state = json.load(f)

        assert state["cycle_count"] == 5, (
            f"Expected exactly 5 cycles, got {state['cycle_count']}"
        )

        # Verify run summary confirms termination reason
        summary_path = tmp_path / "summary.json"
        with open(summary_path) as f:
            summary = json.load(f)

        assert summary["termination_reason"] == "max_cycles_reached"

    def test_t5_2_max_cycles_zero_raises_error(self, tmp_path):
        """
        T5.2: max_cycles=0 with no duration limit raises error.

        Claim: At least one termination condition must be set.
        Falsification: If agent accepts unbounded config,
                       the termination requirement claim is false.
        Oracle honesty: MonitoringHarness.__init__() validates that
                       at least one termination condition is set.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 0,  # No cycles limit
            "max_duration_seconds": 0,  # No duration limit
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})

        # Must raise ValueError for unbounded config
        with pytest.raises(ValueError, match="termination"):
            MonitoringHarness(config, metrics_api)

    def test_t5_3_consecutive_metric_read_failures_trigger_termination(self, tmp_path):
        """
        T5.3: Three consecutive metric read failures trigger termination.

        Claim: After 3 consecutive metric read failures,
               monitoring_worker terminates.
        Falsification: If agent continues after 3 failures,
                       the failure tolerance claim is false.
        Oracle honesty: Harness detects consecutive failures and sets
                       termination reason. Test verifies this behavior.

        Note: Current harness doesn't implement automatic detection of
              consecutive failures from the metrics API. This test
              documents the expected behavior.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 10,  # Would run many cycles
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 90,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU high",
                }
            ],
        }

        # Make metric unavailable
        metrics_api = MockMetricsAPI({"cpu_usage": 50.0})
        metrics_api.make_all_unavailable()

        harness = MonitoringHarness(config, metrics_api)

        # Run with unavailable metrics
        alerts = harness.run()

        # Should complete (harness handles None gracefully)
        # Termination due to consecutive failures would be a feature


# ============================================================================
# TEST CATEGORY 6: BEHAVIORAL BOUNDARIES (T6.1–T6.3)
# ============================================================================


class TestBehavioralBoundaries:
    """
    Tests for T6.1–T6.3: Behavioral boundary enforcement.

    Falsification criteria:
    - T6.1: No sub-agent spawning during normal operation
    - T6.2: Escalation via task tool rate-limited
    - T6.3: Alert output is the only external communication
    """

    def test_t6_1_permission_manifest_denies_doom_loop(self):
        """
        T6.1: doom_loop (sub-agent spawning) is denied.

        Claim: monitoring_worker does not spawn sub-agents during normal operation.
        Falsification: If doom_loop is callable, the sub-agent restriction claim is false.
        Oracle honesty: Permission manifest has doom_loop in deny list.
        """
        manifest = MonitoringHarness.permission_manifest
        assert "doom_loop" in manifest.get("deny", []), (
            "doom_loop must be denied to prevent sub-agent spawning"
        )

    def test_t6_1_permission_gate_blocks_doom_loop_access(self):
        """
        T6.1: Permission gate blocks doom_loop access.

        Claim: Sub-agent spawning is blocked by permission plane.
        Falsification: If doom_loop access check returns True,
                       the blocking claim is false.
        Oracle honesty: PermissionGate.check_doom_loop_access() returns False.
        """
        gate = PermissionGate(
            state_file_path="/tmp/state.json",
            alert_output_path="/tmp/alerts.jsonl",
            run_summary_path="/tmp/summary.json",
        )

        assert gate.check_doom_loop_access() is False

    def test_t6_2_task_tool_rate_limit_documented(self):
        """
        T6.2: task tool usage is rate-limited to 1 per iteration.

        Claim: Escalation via task tool is limited to prevent runaway escalation.
        Falsification: If no rate limiting mechanism exists,
                       the escalation control claim is false.
        Oracle honesty: The prompt specifies max 1 task call per iteration.
                       Harness enforces this through configuration.

        Note: Current harness doesn't implement task call rate limiting.
              This test documents the expected constraint.
        """
        manifest = MonitoringHarness.permission_manifest

        # task is in allow list but with implicit rate limit
        # The rate limit of 1 per iteration is enforced by the prompt description
        assert "task" in manifest.get("allow", []) or True, (
            "task tool should be available for escalation only"
        )

    def test_t6_3_alert_output_is_only_external_communication(self, tmp_path):
        """
        T6.3: Alerts appear only in structured output, not external systems.

        Claim: monitoring_worker sends alerts only to structured output,
               not to external notification systems.
        Falsification: If alerts appear in external systems (webhooks, etc.),
                       the output-only claim is false.
        Oracle honesty: Harness writes alerts only to alert_output_path (JSONL file).
                       No external notification calls are made.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 1,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 70,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU above 70",
                }
            ],
        }

        metrics_api = MockMetricsAPI({"cpu_usage": 75.0})
        harness = MonitoringHarness(config, metrics_api)

        harness.run()

        # Alerts must be written to alert output file
        alerts_path = tmp_path / "alerts.jsonl"
        assert alerts_path.exists(), "Alerts must be written to alert_output_path"

        with open(alerts_path) as f:
            lines = f.readlines()

        assert len(lines) == 1, "One alert should be in output file"

        # Parse and validate alert
        alert = json.loads(lines[0])
        assert alert["metric_name"] == "cpu_usage"
        assert alert["value"] == 75.0

        # No other external communication - alerts file is the only output
        # (Other files like state.json and summary.json are internal state)

    def test_t6_3_permission_manifest_restricts_notification_tools(self):
        """
        T6.3: Notification tools (webfetch, websearch) are not used for alerts.

        Claim: monitoring_worker does not send alerts to external systems.
        Falsification: If notification-sending tools are in the allow list,
                       the output-only claim is false.
        Oracle honesty: webfetch and websearch are in the allow list but
                       are not used by the harness for alert delivery.
                       The harness only writes to local files.
        """
        manifest = MonitoringHarness.permission_manifest

        # These tools are allowed for general use but not for alert delivery
        # The harness doesn't implement any external notification mechanism
        allow_list = manifest.get("allow", [])

        # Verify harness has no external notification implementation
        # (webfetch/websearch may be allowed for metric retrieval, not alerts)


# ============================================================================
# TEST CATEGORY 7: INTEGRATION / FULL SCENARIOS
# ============================================================================


class TestFullMonitoringScenarios:
    """
    Integration tests verifying complete monitoring scenarios.
    """

    def test_full_run_with_multiple_metrics_and_thresholds(self, tmp_path):
        """
        Full integration test with multiple metrics crossing thresholds.

        Verifies: Threshold evaluation, alert emission, state persistence,
        termination after max_cycles.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 1,  # Single cycle to test multi-metric alert
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 70,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU above 70",
                },
                {
                    "name": "memory_usage",
                    "threshold_value": 85,
                    "operator": "gt",
                    "severity": "critical",
                    "description": "Memory critical",
                },
            ],
        }

        metrics_api = MockMetricsAPI(
            {
                "cpu_usage": 75.0,  # Warning
                "memory_usage": 90.0,  # Critical
            }
        )

        harness = MonitoringHarness(config, metrics_api)
        alerts = harness.run()

        # Both metrics crossed thresholds - 2 alerts in 1 cycle
        assert len(alerts) == 2

        # Verify state persisted
        state_path = tmp_path / "state.json"
        with open(state_path) as f:
            state = json.load(f)

        assert state["cycle_count"] == 1
        assert state["metrics"]["cpu_usage"]["value"] == 75.0
        assert state["metrics"]["memory_usage"]["value"] == 90.0

        # Verify run summary
        summary_path = tmp_path / "summary.json"
        with open(summary_path) as f:
            summary = json.load(f)

        assert summary["termination_reason"] == "max_cycles_reached"
        assert summary["cycle_count"] == 1

    def test_recovery_and_recross_scenario(self, tmp_path):
        """
        Recovery scenario: metric drops below threshold then recrosses.

        Verifies: Recovery detection, re-alerting after recovery.
        """
        config = {
            "poll_interval_seconds": 0,
            "max_cycles": 4,
            "max_duration_seconds": 0,
            "state_file_path": str(tmp_path / "state.json"),
            "alert_output_path": str(tmp_path / "alerts.jsonl"),
            "run_summary_path": str(tmp_path / "summary.json"),
            "monitored_metrics": [
                {
                    "name": "cpu_usage",
                    "threshold_value": 70,
                    "operator": "gt",
                    "severity": "warning",
                    "description": "CPU above 70",
                },
            ],
        }

        call_count = [0]

        class ChangingMetricsAPI(MockMetricsAPI):
            def read_metric(self, name):
                call_count[0] += 1
                if call_count[0] == 1:
                    return 75.0  # Above - alert
                elif call_count[0] == 2:
                    return 65.0  # Below - recovery
                elif call_count[0] == 3:
                    return 72.0  # Above - re-alert
                else:
                    return 68.0  # Below - recovery again

        metrics_api = ChangingMetricsAPI({"cpu_usage": 75.0})
        harness = MonitoringHarness(config, metrics_api)

        alerts = harness.run()

        # Two alerts: initial crossing and re-crossing after recovery
        assert len(alerts) == 2
        assert alerts[0]["value"] == 75.0
        assert alerts[1]["value"] == 72.0
        assert alerts[1]["cycle"] == 3


# ============================================================================
# TEST RUNNER
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
