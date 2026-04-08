"""Tests for Evaluator — LLM judge prompt building and response parsing."""

from unittest.mock import MagicMock
from autoresearch.harness.evaluator import Evaluator


def _mock_sub_metrics():
    """9 sub-metric definitions for testing."""
    defs = []
    for i in range(1, 4):
        for j in range(1, 4):
            defs.append({
                "numeric_id": f"1.{i}.{j}",
                "metric": f"metric_{i}",
                "sub_metric": f"sub_{i}_{j}",
                "description": f"Description for 1.{i}.{j}",
                "expected_outcome": f"Expected for 1.{i}.{j}",
                "observable_behavior": f"Observable for 1.{i}.{j}",
            })
    return defs


class TestEvaluator:
    def test_build_eval_prompt_contains_response(self):
        runner = MagicMock()
        ev = Evaluator(runner)
        prompt = ev._build_eval_prompt(
            "accuracy", "test prompt", "agent said hello world",
            {"task_calls": [], "tool_calls": []}, _mock_sub_metrics()
        )
        assert "agent said hello world" in prompt

    def test_build_eval_prompt_contains_sub_metrics(self):
        runner = MagicMock()
        ev = Evaluator(runner)
        prompt = ev._build_eval_prompt(
            "accuracy", "test prompt", "response",
            {"task_calls": [], "tool_calls": []}, _mock_sub_metrics()
        )
        assert "1.1.1" in prompt
        assert "1.3.3" in prompt
        assert "Description for 1.2.1" in prompt

    def test_build_eval_prompt_contains_events(self):
        runner = MagicMock()
        ev = Evaluator(runner)
        events = {"task_calls": [{"subagent_type": "scoper_lead", "description": "test"}], "tool_calls": []}
        prompt = ev._build_eval_prompt(
            "delegation", "test prompt", "response", events, _mock_sub_metrics()
        )
        assert "scoper_lead" in prompt
        assert "Task Delegations" in prompt

    def test_parse_eval_response_valid_json(self):
        runner = MagicMock()
        ev = Evaluator(runner)
        defs = _mock_sub_metrics()
        response_text = '{"1.1.1": true, "1.1.2": false, "1.1.3": true, "1.2.1": true, "1.2.2": false, "1.2.3": true, "1.3.1": true, "1.3.2": false, "1.3.3": true}'
        result = ev._parse_eval_response(response_text, defs)
        assert result["1.1.1"]["result"] is True
        assert result["1.1.2"]["result"] is False
        assert len(result) == 9

    def test_parse_eval_response_missing_fields_default_false(self):
        runner = MagicMock()
        ev = Evaluator(runner)
        defs = _mock_sub_metrics()
        result = ev._parse_eval_response('{"1.1.1": true}', defs)
        assert result["1.1.1"]["result"] is True
        assert result["1.1.2"]["result"] is False

    def test_parse_eval_response_malformed_returns_all_false(self):
        runner = MagicMock()
        ev = Evaluator(runner)
        defs = _mock_sub_metrics()
        result = ev._parse_eval_response("not json at all", defs)
        assert all(v["result"] is False for v in result.values())
