from copy import deepcopy

import pytest

from raglab import evaluation
from raglab.models import Document, EvalCase


def reports():
    docs = [Document("refund", "Refund", "Refunds take 30 days.")]
    cases = [EvalCase("refund", "How long do refunds take?", ("refund",), ("30 days",))]
    baseline = evaluation.evaluate(docs, cases).to_dict()
    same = deepcopy(baseline)
    bad = deepcopy(baseline)
    bad["cases"][0]["answer"] = "I could not find supporting context."
    bad["metrics"]["faithfulness"] = 0
    bad["metrics"]["required_phrase_coverage"] = 0
    bad["metrics"]["citation_correctness"] = 0
    return baseline, same, bad


def test_many_comparisons_reuse_pairwise_checks_and_show_case_changes():
    baseline, same, bad = reports()
    result = evaluation.compare_many(baseline, [same, bad], names=["same", "bad"])
    assert not result["passed"]
    assert result["candidates"][0]["passed"]
    assert not result["candidates"][1]["passed"]
    assert result["candidates"][0]["case_changes"] == []
    changed = result["candidates"][1]["case_changes"][0]
    assert changed["id"] == "refund"
    assert changed["disposition"] == "answer -> abstain"
    assert changed["lost_phrases"] == ["30 days"]
    assert changed["lost_citations"] == ["refund"]
    assert result["candidates"][1]["metrics"] == evaluation.compare_reports(baseline, bad)["metrics"]


@pytest.mark.parametrize("mutation", [
    lambda candidate: candidate.update(benchmark_sha256="different"),
    lambda candidate: candidate["cases"].clear(),
    lambda candidate: candidate["cases"][0].update(question="different question"),
    lambda candidate: candidate["cases"][0].update(required_facts=["different label"]),
])
def test_many_rejects_incompatible_case_evidence(mutation):
    baseline, same, _ = reports()
    mutation(same)
    with pytest.raises(ValueError):
        evaluation.compare_many(baseline, [same], names=["candidate"])


def test_many_validates_candidate_names():
    baseline, same, _ = reports()
    for candidates, names in (([], []), ([same], []), ([same, same], ["same", "same"])):
        with pytest.raises(ValueError):
            evaluation.compare_many(baseline, candidates, names=names)
