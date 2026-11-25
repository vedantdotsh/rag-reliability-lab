import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from raglab import evaluation, testgen_api
from raglab.models import Document, EvalCase

DOCS = [Document("refund", "Refund", "Refunds take 30 days.")]
CASES = [EvalCase("refund", "How long do refunds take?", ("refund",), ("30 days",))]
CONFIG = testgen_api.configuration("compatible", "http://127.0.0.1:9/v1")


def recorded(tmp_path):
    output = tmp_path / "generations.jsonl"
    with patch.object(testgen_api, "api_key", return_value="test-only-key"), patch.object(
        testgen_api, "generate_one", return_value={"raw": "Refunds take 30 days. [refund]"}
    ):
        assert evaluation.generate_rag(DOCS, CASES, output, "test-model", CONFIG) == 0
    return output, [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]


def test_generate_and_replay_are_reproducible_and_offline(tmp_path):
    output, rows = recorded(tmp_path)
    with patch.object(testgen_api, "generate_one", side_effect=AssertionError("network")), patch.object(
        testgen_api, "api_key", side_effect=AssertionError("credentials")
    ):
        first = evaluation.evaluate(DOCS, CASES, generations=rows)
        second = evaluation.evaluate(DOCS, CASES, generations=rows)
    assert first.to_dict() == second.to_dict()
    assert first.metrics["faithfulness"] == 1
    assert first.cases[0].latency_ms == rows[0]["generation"]["latency_seconds"] * 1000
    assert first.config["generator"] == "llm-replay"
    assert first.config["model"] == "test-model"
    assert "required_facts" not in rows[0]["input"]
    assert "expected_doc_ids" not in rows[0]["input"]
    with pytest.raises(FileExistsError), patch.object(testgen_api, "api_key", return_value="key"):
        evaluation.generate_rag(DOCS, CASES, output, "test-model", CONFIG)


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.clear(),
    lambda rows: rows.append(deepcopy(rows[0])),
    lambda rows: rows[0].update(id="other"),
    lambda rows: rows[0].update(input="changed prompt"),
    lambda rows: rows[0]["rag"].update(benchmark_sha256="other"),
    lambda rows: rows[0]["rag"].update(top_k=1),
    lambda rows: rows[0]["generation"].update(case_index=2),
    lambda rows: rows[0]["generation"].update(total_cases=2),
    lambda rows: rows[0]["generation"].update(dataset_sha256="other"),
    lambda rows: rows[0]["generation"].update(input_sha256="other"),
    lambda rows: rows[0]["generation"].update(latency_seconds=True),
    lambda rows: rows[0]["generation"].update(generation_error="truncated"),
    lambda rows: rows[0]["generation"].update(request={}),
    lambda rows: rows[0].update(response=""),
])
def test_replay_rejects_incomplete_or_mismatched_provenance(tmp_path, mutation):
    _, rows = recorded(tmp_path)
    mutation(rows)
    with pytest.raises((ValueError, TypeError)):
        evaluation.evaluate(DOCS, CASES, generations=rows)


def test_failed_generation_is_retained_but_not_scored_as_success(tmp_path):
    output = tmp_path / "failed.jsonl"
    with patch.object(testgen_api, "api_key", return_value="key"), patch.object(
        testgen_api, "generate_one", return_value={"raw": "answer", "generation_error": "truncated"}
    ):
        assert evaluation.generate_rag(DOCS, CASES, output, "test-model", CONFIG) == 1
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["generation"]["generation_error"] == "truncated"
    with pytest.raises(ValueError):
        evaluation.evaluate(DOCS, CASES, generations=rows)
