"""Tests for ResultsWriter — JSONL output format."""

import json
from autoresearch.harness.results_writer import ResultsWriter


def _make_results():
    """Build a sample 27-field eval result dict."""
    results = {}
    for cat in range(1, 4):
        for met in range(1, 4):
            for sub in range(1, 4):
                nid = f"{cat}.{met}.{sub}"
                results[nid] = {"description": f"sub_{cat}_{met}_{sub}", "result": True}
    return results


class TestResultsWriter:
    def test_write_creates_jsonl_file(self, tmp_path):
        writer = ResultsWriter(results_dir=tmp_path)
        writer.write("ceo", "run-001-1", _make_results())
        assert (tmp_path / "ceo" / "results.jsonl").exists()

    def test_write_appends_not_overwrites(self, tmp_path):
        writer = ResultsWriter(results_dir=tmp_path)
        writer.write("ceo", "run-001-1", _make_results())
        writer.write("ceo", "run-001-2", _make_results())
        lines = (tmp_path / "ceo" / "results.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2

    def test_record_has_immutable_keys(self, tmp_path):
        writer = ResultsWriter(results_dir=tmp_path)
        writer.write("ceo", "run-001-1", _make_results())
        record = json.loads((tmp_path / "ceo" / "results.jsonl").read_text().strip())
        assert "run_id" in record
        assert "agent_name" in record
        assert "timestamp" in record

    def test_record_has_27_eval_fields(self, tmp_path):
        writer = ResultsWriter(results_dir=tmp_path)
        writer.write("ceo", "run-001-1", _make_results())
        record = json.loads((tmp_path / "ceo" / "results.jsonl").read_text().strip())
        eval_keys = [k for k in record if "." in k]
        assert len(eval_keys) == 27

    def test_eval_field_shape(self, tmp_path):
        writer = ResultsWriter(results_dir=tmp_path)
        writer.write("ceo", "run-001-1", _make_results())
        record = json.loads((tmp_path / "ceo" / "results.jsonl").read_text().strip())
        for k, v in record.items():
            if "." in k:
                assert "description" in v
                assert "result" in v
                assert isinstance(v["result"], (bool, type(None)))

    def test_read_all_returns_written_records(self, tmp_path):
        writer = ResultsWriter(results_dir=tmp_path)
        writer.write("ceo", "run-001-1", _make_results())
        writer.write("ceo", "run-001-2", _make_results())
        records = writer.read_all("ceo")
        assert len(records) == 2

    def test_null_results_for_limited_delegation(self, tmp_path):
        writer = ResultsWriter(results_dir=tmp_path)
        results = _make_results()
        for k in results:
            if k.startswith("3.2.") or k.startswith("3.3."):
                results[k]["result"] = None
        writer.write("backend_developer_worker", "run-001-1", results)
        record = json.loads((tmp_path / "backend_developer_worker" / "results.jsonl").read_text().strip())
        assert record["3.2.1"]["result"] is None
        assert record["3.3.3"]["result"] is None
        assert record["3.1.1"]["result"] is True
