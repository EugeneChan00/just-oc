"""Tests for EventParser — OpenCode NDJSON parsing."""

import json
from autoresearch.harness.event_listener import EventParser

SAMPLE_TOOL_USE = json.dumps({
    "type": "tool_use", "timestamp": 1775680546408, "sessionID": "ses_X",
    "part": {"type": "tool", "tool": "bash", "callID": "call_1",
             "state": {"status": "completed", "input": {"command": "ls"}, "output": "file.py\n"}}
})

SAMPLE_TASK_CALL = json.dumps({
    "type": "tool_use", "timestamp": 1775680185108, "sessionID": "ses_X",
    "part": {"type": "tool", "tool": "task", "callID": "call_2",
             "state": {"status": "completed",
                       "input": {"description": "Scope feature", "prompt": "Identify next slice", "subagent_type": "scoper_lead"},
                       "output": "task_id: ses_Y\n<task_result>\nSlice Brief...\n</task_result>",
                       "metadata": {"sessionId": "ses_Y"}}}
})

SAMPLE_TEXT = json.dumps({
    "type": "text", "timestamp": 1775680550637, "sessionID": "ses_X",
    "part": {"type": "text", "text": "The answer is 42."}
})

SAMPLE_STEP_FINISH = json.dumps({
    "type": "step_finish", "timestamp": 1775680550672, "sessionID": "ses_X",
    "part": {"reason": "stop", "tokens": {"total": 100, "input": 50, "output": 50}}
})


class TestEventParser:
    def test_parse_empty_stdout(self):
        result = EventParser.parse("")
        assert result["text"] == ""
        assert result["task_calls"] == []
        assert result["tool_calls"] == []
        assert result["tokens"] is None
        assert result["error"] is None

    def test_parse_text_events(self):
        stdout = SAMPLE_TEXT + "\n" + json.dumps({
            "type": "text", "timestamp": 2, "sessionID": "ses_X",
            "part": {"type": "text", "text": " More text."}
        })
        result = EventParser.parse(stdout)
        assert result["text"] == "The answer is 42. More text."

    def test_parse_task_calls(self):
        result = EventParser.parse(SAMPLE_TASK_CALL)
        assert len(result["task_calls"]) == 1
        tc = result["task_calls"][0]
        assert tc["subagent_type"] == "scoper_lead"
        assert tc["description"] == "Scope feature"

    def test_parse_regular_tool_calls(self):
        result = EventParser.parse(SAMPLE_TOOL_USE)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "bash"
        assert result["task_calls"] == []

    def test_parse_mixed_stream(self):
        stdout = "\n".join([SAMPLE_TOOL_USE, SAMPLE_TASK_CALL, SAMPLE_TEXT, SAMPLE_STEP_FINISH])
        result = EventParser.parse(stdout)
        assert result["text"] == "The answer is 42."
        assert len(result["task_calls"]) == 1
        assert len(result["tool_calls"]) == 1
        assert result["tokens"] == {"total": 100, "input": 50, "output": 50}

    def test_parse_malformed_json_skipped(self):
        stdout = "not json\n" + SAMPLE_TEXT + "\n{bad json too"
        result = EventParser.parse(stdout)
        assert result["text"] == "The answer is 42."

    def test_task_call_has_required_fields(self):
        result = EventParser.parse(SAMPLE_TASK_CALL)
        tc = result["task_calls"][0]
        for field in ["subagent_type", "description", "prompt", "output", "session_id", "status"]:
            assert field in tc, f"Missing field: {field}"
