"""Tests for SpecReader — spec JSON loading and numeric ID mapping."""

import pytest
from autoresearch.harness.spec_reader import SpecReader, build_numeric_id, all_numeric_ids


class TestSpecReader:
    def setup_method(self):
        self.reader = SpecReader()

    def test_load_agent_specs_returns_3_categories(self):
        specs = self.reader.load_agent_specs("ceo")
        assert set(specs.keys()) == {"accuracy", "rejection", "delegation"}

    def test_get_prompts_returns_10(self):
        prompts = self.reader.get_prompts("ceo", "accuracy")
        assert len(prompts) == 10

    def test_get_prompts_have_prompt_and_rationale(self):
        prompts = self.reader.get_prompts("ceo", "accuracy")
        for p in prompts:
            assert "prompt" in p
            assert "rationale" in p

    def test_prompt_min_word_count(self):
        prompts = self.reader.get_prompts("ceo", "accuracy")
        for i, p in enumerate(prompts):
            wc = len(p["prompt"].split())
            assert wc >= 400, f"Prompt {i} has {wc} words, expected >= 400"

    def test_get_sub_metric_definitions_returns_9(self):
        defs = self.reader.get_sub_metric_definitions("ceo", "accuracy")
        assert len(defs) == 9

    def test_sub_metric_has_required_fields(self):
        defs = self.reader.get_sub_metric_definitions("ceo", "accuracy")
        for d in defs:
            for field in ["numeric_id", "metric", "sub_metric", "description", "expected_outcome", "observable_behavior"]:
                assert field in d, f"Missing field: {field}"

    def test_build_numeric_id(self):
        assert build_numeric_id("accuracy", "factual_correctness", "fact_accuracy") == "1.1.1"

    def test_build_numeric_id_delegation(self):
        assert build_numeric_id("delegation", "pipeline_adherence", "entry_point_routing") == "3.3.3"

    def test_all_27_ids_unique(self):
        ids = all_numeric_ids()
        assert len(ids) == 27
        assert len(set(ids)) == 27

    def test_missing_agent_raises(self):
        with pytest.raises(FileNotFoundError):
            self.reader.load_spec("nonexistent_agent_xyz", "accuracy")
