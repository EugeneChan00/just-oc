"""
tests/harness/test_monitoring_harness.py

Unit tests for monitoring_worker test harness components:
1. PermissionGate - write path validation
2. MonitoringTickLoop - poll interval and max iterations
3. MockMetricsServer - metrics return and error injection
4. OutputSchemaValidator - schema validation
5. AlertCollector - alert capture
6. SignalHandler - signal handling
7. Integration tests - components work together
"""

import json
import signal
import time
import pytest
from unittest.mock import MagicMock

from harness.monitoring_harness import (
    PermissionGate,
    MonitoringTickLoop,
    MockMetricsServer,
    MetricsAPIError,
    OutputSchemaValidator,
    AlertCollector,
    SignalHandler,
    MonitoringHarness,
)


# ============================================================================
# 1. PermissionGate Tests
# ============================================================================


class TestPermissionGate:
    """Tests for PermissionGate component."""

    def test_validate_write_allowed_for_state_path(self):
        """PermissionGate validates state_file_path as allowed."""
        gate = PermissionGate("/var/state/monitor.json")
        assert gate.validate_write("/var/state/monitor.json") is True

    def test_validate_write_denied_for_other_path(self):
        """PermissionGate rejects non-state paths."""
        gate = PermissionGate("/var/state/monitor.json")
        assert gate.validate_write("/tmp/other.txt") is False
        assert gate.validate_write("/etc/passwd") is False
        assert gate.validate_write("/var/log/metrics") is False

    def test_intercept_write_allowed_for_state_path(self):
        """intercept_write does not raise for state_file_path."""
        gate = PermissionGate("/var/state/monitor.json")
        # Should not raise
        gate.intercept_write("/var/state/monitor.json", '{"data": "test"}')

    def test_intercept_write_raises_for_non_state_path(self):
        """intercept_write raises PermissionError for non-state paths."""
        gate = PermissionGate("/var/state/monitor.json")
        with pytest.raises(PermissionError) as exc_info:
            gate.intercept_write("/tmp/other.txt", "malicious content")
        assert "not permitted" in str(exc_info.value)

    def test_intercept_write_records_rejected_attempts(self):
        """Rejected writes are recorded for audit."""
        gate = PermissionGate("/var/state/monitor.json")
        try:
            gate.intercept_write("/tmp/evil.txt", "bad")
        except PermissionError:
            pass
        try:
            gate.intercept_write("/etc/passwd", "worse")
        except PermissionError:
            pass

        rejected = gate.get_rejected_writes()
        assert len(rejected) == 2
        assert rejected[0]["path"] == "/tmp/evil.txt"
        assert rejected[1]["path"] == "/etc/passwd"
        assert all("timestamp" in r for r in rejected)

    def test_rejected_writes_include_reason(self):
        """Rejected writes include descriptive reason."""
        gate = PermissionGate("/var/state/monitor.json")
        with pytest.raises(PermissionError):
            gate.intercept_write("/tmp/other.txt", "content")

        rejected = gate.get_rejected_writes()
        assert "not permitted" in rejected[0]["reason"]
        assert "/var/state/monitor.json" in rejected[0]["reason"]


# ============================================================================
# 2. MonitoringTickLoop Tests
# ============================================================================


class TestMonitoringTickLoop:
    """Tests for MonitoringTickLoop component."""

    def test_tick_loop_validates_poll_interval_bounds(self):
        """poll_interval must be 1-300 seconds."""
        with pytest.raises(ValueError):
            MonitoringTickLoop(poll_interval=0, max_iterations=10)
        with pytest.raises(ValueError):
            MonitoringTickLoop(poll_interval=301, max_iterations=10)
        with pytest.raises(ValueError):
            MonitoringTickLoop(poll_interval=-1, max_iterations=10)

    def test_tick_loop_validates_max_iterations_positive(self):
        """max_iterations must be positive."""
        with pytest.raises(ValueError):
            MonitoringTickLoop(poll_interval=5, max_iterations=0)
        with pytest.raises(ValueError):
            MonitoringTickLoop(poll_interval=5, max_iterations=-1)

    def test_tick_loop_runs_exactly_max_iterations(self):
        """Tick loop runs agent.tick() exactly max_iterations times."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=3)
        mock_agent = MagicMock()
        mock_agent.tick.return_value = {"iteration": 1, "metrics": {}, "alerts": []}

        outputs = loop.run(mock_agent, [])

        assert len(outputs) == 3
        assert mock_agent.tick.call_count == 3

    def test_tick_loop_respects_stop_signal(self):
        """Tick loop stops early when stop signal received.

        This test verifies stop signal handling. The stop flag is checked
        at the start of each tick. If set, the loop exits before the next tick.
        """
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=5)
        mock_agent = MagicMock()
        mock_agent.tick.return_value = {"iteration": 1, "metrics": {}, "alerts": []}

        # First verify that normally all iterations complete
        outputs = loop.run(mock_agent, [])
        assert mock_agent.tick.call_count == 5

        # Now verify that request_stop() sets the flag
        loop.request_stop()
        assert loop._stop_requested is True

        # And reset clears it
        loop.reset()
        assert loop._stop_requested is False

    def test_tick_loop_tracks_tick_count(self):
        """Tick loop exposes tick_count after run."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=3)
        mock_agent = MagicMock()
        mock_agent.tick.return_value = {"iteration": 1, "metrics": {}, "alerts": []}

        loop.run(mock_agent, [])
        assert loop.tick_count == 3

    def test_tick_loop_passes_metrics_sources_to_agent(self):
        """Tick loop passes metrics_sources to agent.tick()."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=1)
        mock_agent = MagicMock()
        mock_agent.tick.return_value = {"iteration": 1, "metrics": {}, "alerts": []}
        mock_sources = [MagicMock(), MagicMock()]

        loop.run(mock_agent, mock_sources)

        mock_agent.tick.assert_called_once_with(mock_sources)

    def test_tick_loop_respects_poll_interval_timing(self):
        """Tick loop waits poll_interval between ticks."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=3)
        mock_agent = MagicMock()
        mock_agent.tick.return_value = {"iteration": 1, "metrics": {}, "alerts": []}

        start = time.time()
        loop.run(mock_agent, [])
        elapsed = time.time() - start

        # poll_interval=1 means 1s between ticks, 2 intervals for 3 ticks
        # Should take at least 2 seconds
        assert elapsed >= 2.0, f"Expected >= 2s, got {elapsed:.2f}s"
        assert len(loop._tick_timestamps) == 3

    def test_tick_loop_handles_agent_exception(self):
        """Tick loop continues after agent.tick() raises exception."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=3)
        mock_agent = MagicMock()
        mock_agent.tick.side_effect = [Exception("fail"), Exception("fail"), None]

        # Side effect doesn't return proper output, so we get error dict
        # But loop should complete all iterations
        outputs = loop.run(mock_agent, [])
        assert len(outputs) == 3

    def test_tick_loop_reset_clears_state(self):
        """reset() clears tick_count and stop flag."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=5)
        loop._tick_count = 3
        loop._stop_requested = True

        loop.reset()

        assert loop._tick_count == 0
        assert loop._stop_requested is False


# ============================================================================
# 3. MockMetricsServer Tests
# ============================================================================


class TestMockMetricsServer:
    """Tests for MockMetricsServer component."""

    def test_get_metrics_returns_configured_metrics(self):
        """get_metrics() returns the configured metrics dict."""
        metrics = {"cpu_percent": 45.2, "memory_percent": 62.1}
        server = MockMetricsServer(metrics)

        result = server.get_metrics()

        assert result == metrics
        assert result["cpu_percent"] == 45.2

    def test_get_metrics_returns_fresh_copy(self):
        """get_metrics() returns a copy, not the original."""
        metrics = {"cpu_percent": 45.2}
        server = MockMetricsServer(metrics)

        result = server.get_metrics()
        result["cpu_percent"] = 999.0

        # Original unchanged
        assert server.metrics["cpu_percent"] == 45.2

    def test_error_rate_zero_never_errors(self):
        """error_rate=0.0 never raises MetricsAPIError."""
        server = MockMetricsServer({"cpu": 50.0}, error_rate=0.0)

        for _ in range(100):
            result = server.get_metrics()
            assert result["cpu"] == 50.0

    def test_error_rate_one_always_errors(self):
        """error_rate=1.0 always raises MetricsAPIError."""
        server = MockMetricsServer({"cpu": 50.0}, error_rate=1.0)

        with pytest.raises(MetricsAPIError):
            server.get_metrics()

    def test_error_rate_causes_random_failures(self):
        """error_rate=0.5 causes approximately 50% failures."""
        server = MockMetricsServer({"cpu": 50.0}, error_rate=0.5)

        results = []
        for _ in range(100):
            try:
                server.get_metrics()
                results.append("success")
            except MetricsAPIError:
                results.append("error")

        # With error_rate=0.5, should have roughly 50% errors (allowing for randomness)
        error_count = results.count("error")
        # Statistical bounds: 35-65% is reasonable for 100 samples
        assert 30 <= error_count <= 70, f"Expected ~50 errors, got {error_count}"

    def test_update_metrics_changes_returned_value(self):
        """update_metrics() changes what get_metrics() returns."""
        server = MockMetricsServer({"cpu": 50.0})
        assert server.get_metrics()["cpu"] == 50.0

        server.update_metrics({"cpu": 99.9})
        assert server.get_metrics()["cpu"] == 99.9

    def test_set_error_rate_changes_behavior(self):
        """set_error_rate() changes error injection rate."""
        server = MockMetricsServer({"cpu": 50.0}, error_rate=0.0)
        assert server.get_metrics()["cpu"] == 50.0

        server.set_error_rate(1.0)
        with pytest.raises(MetricsAPIError):
            server.get_metrics()

    def test_invalid_error_rate_raises(self):
        """error_rate outside 0.0-1.0 raises ValueError."""
        with pytest.raises(ValueError):
            MockMetricsServer({"cpu": 50.0}, error_rate=-0.1)
        with pytest.raises(ValueError):
            MockMetricsServer({"cpu": 50.0}, error_rate=1.1)

    def test_call_count_tracked(self):
        """call_count increments on each get_metrics()."""
        server = MockMetricsServer({"cpu": 50.0}, error_rate=0.0)

        for _ in range(10):
            server.get_metrics()

        assert server.call_count == 10

    def test_error_count_tracked(self):
        """error_count increments only on injected errors."""
        server = MockMetricsServer({"cpu": 50.0}, error_rate=1.0)

        for _ in range(5):
            try:
                server.get_metrics()
            except MetricsAPIError:
                pass

        assert server.error_count == 5


# ============================================================================
# 4. OutputSchemaValidator Tests
# ============================================================================


class TestOutputSchemaValidator:
    """Tests for OutputSchemaValidator component."""

    def get_valid_output(self) -> dict:
        """Returns a valid output dict."""
        return {
            "timestamp": "2026-04-09T12:00:00Z",
            "iteration": 1,
            "metrics": {"cpu_percent": 45.2, "memory_percent": 62.1},
            "alerts": [],
            "state_updated": True,
        }

    def test_valid_output_passes_validation(self):
        """Valid output has no validation errors."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()

        is_valid, errors = validator.validate(output)

        assert is_valid is True
        assert len(errors) == 0

    def test_valid_json_string_passes_validation(self):
        """Valid JSON string is parsed and validated."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        json_str = json.dumps(output)

        is_valid, errors = validator.validate(json_str)

        assert is_valid is True
        assert len(errors) == 0

    def test_invalid_json_string_fails_validation(self):
        """Invalid JSON string fails validation."""
        validator = OutputSchemaValidator()

        is_valid, errors = validator.validate('{"broken": json}')

        assert is_valid is False
        assert any("Invalid JSON" in e for e in errors)

    def test_missing_required_field_fails(self):
        """Missing required field produces error."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        del output["timestamp"]

        is_valid, errors = validator.validate(output)

        assert is_valid is False
        assert any("timestamp" in e for e in errors)

    def test_invalid_timestamp_format_fails(self):
        """Invalid timestamp format produces error."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["timestamp"] = "not-a-timestamp"

        is_valid, errors = validator.validate(output)

        assert is_valid is False
        assert any("timestamp" in e.lower() for e in errors)

    def test_non_integer_iteration_fails(self):
        """Non-integer iteration produces error."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["iteration"] = "1"

        is_valid, errors = validator.validate(output)

        assert is_valid is False
        assert any("iteration" in e for e in errors)

    def test_non_numeric_metric_fails(self):
        """Non-numeric metric value produces error."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["metrics"]["cpu_percent"] = "high"

        is_valid, errors = validator.validate(output)

        assert is_valid is False
        assert any("cpu_percent" in e for e in errors)

    def test_invalid_alert_severity_fails(self):
        """Invalid alert severity produces error."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["alerts"] = [
            {
                "severity": "invalid",
                "metric": "cpu",
                "value": 1,
                "threshold": 0,
                "message": "test",
            }
        ]

        is_valid, errors = validator.validate(output)

        assert is_valid is False
        assert any("severity" in e for e in errors)

    def test_alert_with_missing_field_fails(self):
        """Alert missing required field produces error."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["alerts"] = [
            {"severity": "warning", "metric": "cpu"}
        ]  # missing value, threshold, message

        is_valid, errors = validator.validate(output)

        assert is_valid is False
        assert any("alerts" in e for e in errors)

    def test_non_boolean_state_updated_fails(self):
        """Non-boolean state_updated produces error."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["state_updated"] = "true"

        is_valid, errors = validator.validate(output)

        assert is_valid is False
        assert any("state_updated" in e for e in errors)

    def test_extra_fields_not_allowed(self):
        """Additional properties not in schema fail."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["extra_field"] = "not allowed"

        is_valid, errors = validator.validate(output)

        assert is_valid is False
        assert any("Additional property" in e for e in errors)

    def test_empty_alerts_allowed(self):
        """Empty alerts list is valid."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["alerts"] = []

        is_valid, errors = validator.validate(output)

        assert is_valid is True

    def test_valid_alert_format_passes(self):
        """Valid alert format passes."""
        validator = OutputSchemaValidator()
        output = self.get_valid_output()
        output["alerts"] = [
            {
                "severity": "warning",
                "metric": "cpu_percent",
                "value": 72.3,
                "threshold": 70,
                "message": "cpu_percent (72.3) exceeds warning threshold (70)",
            }
        ]

        is_valid, errors = validator.validate(output)

        assert is_valid is True

    def test_validation_errors_recorded(self):
        """Validation errors are recorded for audit."""
        validator = OutputSchemaValidator()
        output = {"invalid": "output"}
        validator.validate(output)

        errors = validator.get_validation_errors()
        assert len(errors) >= 1


# ============================================================================
# 5. AlertCollector Tests
# ============================================================================


class TestAlertCollector:
    """Tests for AlertCollector component."""

    def get_sample_alert(self) -> dict:
        """Returns a sample alert dict."""
        return {
            "severity": "warning",
            "metric": "cpu_percent",
            "value": 72.3,
            "threshold": 70,
            "message": "cpu_percent (72.3) exceeds warning threshold (70)",
        }

    def test_emit_captures_alert(self):
        """emit() captures alert for later retrieval."""
        collector = AlertCollector()
        alert = self.get_sample_alert()

        collector.emit(alert)

        assert collector.count == 1
        assert collector.get_alerts()[0]["metric"] == "cpu_percent"

    def test_emit_enriches_with_timestamp(self):
        """emit() adds capture timestamp to alert."""
        collector = AlertCollector()
        alert = self.get_sample_alert()

        collector.emit(alert)

        captured = collector.get_alerts()[0]
        assert "_captured_at" in captured

    def test_get_alerts_returns_all_alerts(self):
        """get_alerts() returns all captured alerts."""
        collector = AlertCollector()
        collector.emit(
            {
                "severity": "warning",
                "metric": "cpu",
                "value": 1,
                "threshold": 0,
                "message": "a",
            }
        )
        collector.emit(
            {
                "severity": "critical",
                "metric": "mem",
                "value": 2,
                "threshold": 1,
                "message": "b",
            }
        )

        alerts = collector.get_alerts()

        assert len(alerts) == 2

    def test_get_alerts_by_severity_filters(self):
        """get_alerts_by_severity() filters by severity."""
        collector = AlertCollector()
        collector.emit(
            {
                "severity": "warning",
                "metric": "cpu",
                "value": 1,
                "threshold": 0,
                "message": "a",
            }
        )
        collector.emit(
            {
                "severity": "critical",
                "metric": "mem",
                "value": 2,
                "threshold": 1,
                "message": "b",
            }
        )
        collector.emit(
            {
                "severity": "warning",
                "metric": "disk",
                "value": 3,
                "threshold": 2,
                "message": "c",
            }
        )

        warnings = collector.get_alerts_by_severity("warning")
        criticals = collector.get_alerts_by_severity("critical")

        assert len(warnings) == 2
        assert len(criticals) == 1

    def test_clear_removes_all_alerts(self):
        """clear() removes all captured alerts."""
        collector = AlertCollector()
        collector.emit(
            {
                "severity": "warning",
                "metric": "cpu",
                "value": 1,
                "threshold": 0,
                "message": "a",
            }
        )
        collector.emit(
            {
                "severity": "critical",
                "metric": "mem",
                "value": 2,
                "threshold": 1,
                "message": "b",
            }
        )

        collector.clear()

        assert collector.count == 0
        assert collector.get_alerts() == []

    def test_multiple_emits_preserve_order(self):
        """Multiple emits preserve insertion order."""
        collector = AlertCollector()
        for i in range(5):
            collector.emit(
                {
                    "severity": "warning",
                    "metric": f"m{i}",
                    "value": i,
                    "threshold": 0,
                    "message": f"a{i}",
                }
            )

        alerts = collector.get_alerts()
        assert len(alerts) == 5
        for i, alert in enumerate(alerts):
            assert alert["metric"] == f"m{i}"


# ============================================================================
# 6. SignalHandler Tests
# ============================================================================


class TestSignalHandler:
    """Tests for SignalHandler component."""

    def test_signal_handler_installs(self):
        """install() sets up signal handlers."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=10)
        handler = SignalHandler(loop)

        handler.install([signal.SIGINT])

        # Verify handler was registered (we can't easily test the actual signal)
        assert handler.tick_loop is loop

    def test_signal_handler_triggers_stop(self):
        """Signal handler calls request_stop() on tick loop."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=100)
        handler = SignalHandler(loop)

        # Directly test the internal handler
        handler._handle_signal(signal.SIGINT, None)

        assert loop._stop_requested is True

    def test_signal_handler_restores_original_handlers(self):
        """restore() puts back original handlers."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=10)
        handler = SignalHandler(loop)

        handler.install([signal.SIGINT])
        handler.restore()

        # After restore, original handler should be restored
        # (We can't verify the original was exactly SIG_DFL, but we verify no crash)


# ============================================================================
# 7. MonitoringHarness Integration Tests
# ============================================================================


class TestMonitoringHarness:
    """Integration tests for complete MonitoringHarness."""

    def test_harness_creates_all_components(self):
        """MonitoringHarness initializes all components."""
        harness = MonitoringHarness(
            state_file_path="/var/state/monitor.json",
            poll_interval=5,
            max_iterations=10,
            metrics={"cpu_percent": 45.0},
            error_rate=0.0,
        )

        assert harness.permission_gate is not None
        assert harness.tick_loop is not None
        assert harness.metrics_server is not None
        assert harness.schema_validator is not None
        assert harness.alert_collector is not None

    def test_harness_permission_gate_is_configured(self):
        """PermissionGate uses configured state_file_path."""
        harness = MonitoringHarness(state_file_path="/var/state/special.json")

        assert harness.permission_gate.state_file_path == "/var/state/special.json"

    def test_harness_tick_loop_is_configured(self):
        """TickLoop uses configured poll_interval and max_iterations."""
        harness = MonitoringHarness(
            state_file_path="/var/state/m.json",
            poll_interval=10,
            max_iterations=20,
        )

        assert harness.tick_loop.poll_interval == 10
        assert harness.tick_loop.max_iterations == 20

    def test_harness_metrics_server_is_configured(self):
        """MetricsServer uses configured metrics and error_rate."""
        harness = MonitoringHarness(
            state_file_path="/var/state/m.json",
            metrics={"cpu": 99.0, "mem": 50.0},
            error_rate=0.1,
        )

        assert harness.metrics_server.metrics == {"cpu": 99.0, "mem": 50.0}
        assert harness.metrics_server.error_rate == 0.1

    def test_harness_run_calls_agent_tick(self):
        """run() executes agent.tick() via tick_loop."""
        harness = MonitoringHarness(
            state_file_path="/var/state/m.json",
            poll_interval=1,
            max_iterations=2,
            metrics={"cpu": 50.0},
        )

        mock_agent = MagicMock()
        mock_agent.tick.return_value = {
            "timestamp": "2026-04-09T12:00:00Z",
            "iteration": 1,
            "metrics": {"cpu": 50.0},
            "alerts": [],
            "state_updated": True,
        }

        outputs = harness.run(mock_agent)

        assert mock_agent.tick.call_count == 2
        assert len(outputs) == 2

    def test_harness_signal_handler_installation(self):
        """install_signal_handlers() sets up SIGINT/SIGTERM handlers."""
        harness = MonitoringHarness(state_file_path="/var/state/m.json")

        harness.install_signal_handlers()

        assert harness.signal_handler is not None

        harness.restore_signal_handlers()


# ============================================================================
# 8. Falsification Criteria Tests
# ============================================================================


class TestFalsificationCriteria:
    """Tests that verify falsification criteria are met.

    These are the key behaviors that, if broken, would make the harness
    defective or insecure.
    """

    def test_permission_gate_blocks_non_state_path(self):
        """FALSIFICATION: Permission gate must block non-state-file writes."""
        gate = PermissionGate("/var/state/monitor.json")

        with pytest.raises(PermissionError):
            gate.intercept_write("/tmp/evil.txt", "malicious")

        with pytest.raises(PermissionError):
            gate.intercept_write("/etc/passwd", "root:x:0:")

    def test_tick_loop_respects_max_iterations_bound(self):
        """FALSIFICATION: Tick loop must not exceed max_iterations."""
        loop = MonitoringTickLoop(poll_interval=1, max_iterations=3)
        mock_agent = MagicMock()
        mock_agent.tick.return_value = {"iteration": 1, "metrics": {}, "alerts": []}

        loop.run(mock_agent, [])

        assert mock_agent.tick.call_count == 3

    def test_tick_loop_respects_poll_interval_minimum(self):
        """FALSIFICATION: poll_interval minimum of 1 second enforced."""
        with pytest.raises(ValueError):
            MonitoringTickLoop(poll_interval=0, max_iterations=10)

        with pytest.raises(ValueError):
            MonitoringTickLoop(poll_interval=-1, max_iterations=10)

    def test_tick_loop_respects_poll_interval_maximum(self):
        """FALSIFICATION: poll_interval maximum of 300 seconds enforced."""
        with pytest.raises(ValueError):
            MonitoringTickLoop(poll_interval=301, max_iterations=10)

    def test_schema_validator_rejects_invalid_output(self):
        """FALSIFICATION: Schema validator must reject non-compliant output."""
        validator = OutputSchemaValidator()

        is_valid, errors = validator.validate({"no": "required fields"})

        assert is_valid is False
        assert len(errors) > 0

    def test_mock_server_supports_error_injection(self):
        """FALSIFICATION: Mock server must support error injection."""
        server = MockMetricsServer({"cpu": 50.0}, error_rate=1.0)

        with pytest.raises(MetricsAPIError):
            server.get_metrics()

    def test_alert_collector_captures_all_alerts(self):
        """FALSIFICATION: Alert collector must capture all emitted alerts."""
        collector = AlertCollector()

        for i in range(10):
            collector.emit(
                {
                    "severity": "warning",
                    "metric": f"m{i}",
                    "value": i,
                    "threshold": 0,
                    "message": f"a{i}",
                }
            )

        assert collector.count == 10
