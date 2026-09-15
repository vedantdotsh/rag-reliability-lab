import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from raglab.saved_eval import evaluate


def _case(case_id, response, expected, category="extract"):
    return {
        "id": case_id,
        "input": f"Extract {case_id}",
        "response": response,
        "expected": expected,
        "scorer": "json",
        "category": category,
    }


def _write_report(path: Path, records):
    report = evaluate(records, path.with_suffix(".jsonl"))
    path.write_text(json.dumps(report), encoding="utf-8")
    return report


def _run(baseline: Path, candidate: Path, *args: str):
    return subprocess.run(
        [sys.executable, "-m", "raglab.saved_eval_compare", str(baseline), str(candidate), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_compare_recomputes_scores_and_lists_changes(tmp_path):
    baseline_path = tmp_path / "model-a.json"
    candidate_path = tmp_path / "model-b.json"
    output = tmp_path / "comparison.json"
    baseline = _write_report(
        baseline_path,
        [
            _case("better", '{"value": 0}', {"value": 1}),
            _case("worse", '{"value": 2}', {"value": 2}),
            _case("shared", "{}", {"value": 3}, "table"),
        ],
    )
    _write_report(
        candidate_path,
        [
            _case("better", '{"value": 1}', {"value": 1}),
            _case("worse", '{"value": 0}', {"value": 2}),
            _case("shared", "{}", {"value": 3}, "table"),
        ],
    )
    baseline["cases"][0]["passed"] = True
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    result = _run(baseline_path, candidate_path, "--output", str(output))

    assert result.returncode == 1
    assert "extract: 1/2 -> 1/2 (+0)" in result.stdout
    assert "Improvements: better" in result.stdout
    assert "Regressions: worse" in result.stdout
    assert "Unchanged failures: shared" in result.stdout
    comparison = json.loads(output.read_text(encoding="utf-8"))
    assert comparison["summary"]["improvements"] == 1
    assert comparison["summary"]["regressions"] == 1


def test_compare_exits_zero_for_improvements_without_regressions(tmp_path):
    baseline = tmp_path / "before.json"
    candidate = tmp_path / "after.json"
    _write_report(baseline, [_case("fixed", "{}", {"value": 1})])
    _write_report(candidate, [_case("fixed", '{"value": 1}', {"value": 1})])

    result = _run(baseline, candidate)

    assert result.returncode == 0
    assert "Passed: 0 -> 1 (+1)" in result.stdout


def test_compare_rejects_scope_mismatch(tmp_path):
    baseline = tmp_path / "before.json"
    candidate = tmp_path / "after.json"
    report = _write_report(baseline, [_case("same", "{}", {})])
    altered = deepcopy(report)
    altered["cases"][0]["expected"] = {"different": True}
    candidate.write_text(json.dumps(altered), encoding="utf-8")

    result = _run(baseline, candidate)

    assert result.returncode == 2
    assert "case 'same' differs in: expected" in result.stderr


def test_compare_rejects_different_ids_and_output_alias(tmp_path):
    baseline = tmp_path / "before.json"
    candidate = tmp_path / "after.json"
    _write_report(baseline, [_case("left", "{}", {})])
    _write_report(candidate, [_case("right", "{}", {})])

    mismatch = _run(baseline, candidate)
    alias = _run(baseline, baseline, "--output", str(baseline))

    assert mismatch.returncode == 2
    assert "case IDs differ" in mismatch.stderr
    assert alias.returncode == 2
    assert "output must not overwrite an input report" in alias.stderr


def test_compare_rejects_a_partial_generated_report(tmp_path):
    baseline = tmp_path / "before.json"
    candidate = tmp_path / "after.json"
    generation = {
        "execution_status": "completed", "total_cases": 2, "case_index": 1,
    }
    _write_report(baseline, [{**_case("only", "{}", {}), "generation": generation}])
    _write_report(candidate, [{**_case("only", "{}", {}), "generation": generation}])

    result = _run(baseline, candidate)

    assert result.returncode == 2
    assert "generated run is partial or out of order" in result.stderr
