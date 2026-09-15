import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from raglab.saved_eval import evaluate, load_records


def _run(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "raglab.saved_eval", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _write(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_cli_scores_cases_by_category_and_writes_report(tmp_path):
    source = tmp_path / "answers.jsonl"
    output = tmp_path / "report.json"
    _write(
        source,
        [
            {
                "id": "exact-pass",
                "input": "Capital?",
                "response": "Paris",
                "expected": "Paris",
                "scorer": "exact",
                "category": "facts",
            },
            {
                "id": "number-pass",
                "input": "Estimate",
                "response": "3.14",
                "expected": 3.1,
                "scorer": "numeric",
                "tolerance": 0.05,
                "category": "math",
            },
            {
                "id": "json-pass",
                "input": "Return JSON",
                "response": '{"ok": true}',
                "expected": None,
                "scorer": "valid_json",
                "category": "format",
            },
            {
                "id": "exact-fail",
                "input": "Say yes",
                "response": "no",
                "expected": "yes",
                "scorer": "exact",
                "category": "facts",
            },
        ],
    )

    result = _run(source, "--output", str(output))

    assert result.returncode == 1
    assert "Cases: 4 | Passed: 3 | Failed: 1" in result.stdout
    assert "facts: 1/2 passed (1 failed)" in result.stdout
    assert "Input: Say yes" in result.stdout
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"] == {"total": 4, "passed": 3, "failed": 1}
    assert report["cases"][-1]["reason"] == "exact match failed"


def test_all_passing_file_exits_zero(tmp_path):
    source = tmp_path / "answers.jsonl"
    _write(
        source,
        [
            {
                "id": "pass",
                "input": "Say yes",
                "response": "yes",
                "expected": "yes",
                "scorer": "exact",
            }
        ],
    )

    result = _run(source)

    assert result.returncode == 0
    assert "Saved-answer evaluation: PASS" in result.stdout


@pytest.mark.parametrize(
    "record,message",
    [
        (
            {"id": "", "input": "x", "response": "x", "expected": "x", "scorer": "exact"},
            "id must be a non-empty string",
        ),
        (
            {
                "id": "x",
                "input": "x",
                "response": "x",
                "expected": float("inf"),
                "scorer": "numeric",
            },
            "non-finite number Infinity",
        ),
        (
            {
                "id": "x",
                "input": "x",
                "response": "x",
                "expected": 1,
                "scorer": "numeric",
                "tolerance": -1,
            },
            "tolerance must be a finite non-negative number",
        ),
        (
            {"id": "x", "input": "x", "response": "{}", "expected": {}, "scorer": "valid_json"},
            "valid_json expected must be null",
        ),
        (
            {
                "id": "x",
                "input": "x",
                "response": "x",
                "expected": "x",
                "scorer": "exact",
                "extra": True,
            },
            "unknown field(s): extra",
        ),
        (
            {"id": "x", "input": "x", "response": "x", "expected": "x", "scorer": []},
            "scorer must be one of",
        ),
        (
            {"id": "x", "input": "x", "response": "x", "expected": "x",
             "scorer": "exact", "generation": None},
            "generation must be an object",
        ),
        (
            {"id": "x", "input": "x", "response": "x", "expected": "x",
             "scorer": "exact", "generation": {"execution_status": []}},
            "generation has an invalid execution_status",
        ),
    ],
)
def test_loader_reports_actionable_line_errors(tmp_path, record, message):
    source = tmp_path / "bad.jsonl"
    source.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=re.escape(message)):
        load_records(source)


def test_duplicate_ids_are_rejected(tmp_path):
    source = tmp_path / "duplicate.jsonl"
    record = {"id": "same", "input": "x", "response": "x", "expected": "x", "scorer": "exact"}
    _write(source, [record, record])

    result = _run(source)

    assert result.returncode == 2
    assert f"{source}:2: duplicate id 'same'" in result.stderr
    assert "Traceback" not in result.stderr


def test_invalid_json_response_is_a_failed_case(tmp_path):
    source = tmp_path / "answers.jsonl"
    _write(
        source,
        [
            {
                "id": "bad-json",
                "input": "JSON",
                "response": "[1e999]",
                "expected": None,
                "scorer": "valid_json",
            }
        ],
    )

    result = _run(source)

    assert result.returncode == 1
    assert "response is not valid JSON" in result.stdout


def test_json_scorer_compares_values_not_text(tmp_path):
    source = tmp_path / "answers.jsonl"
    _write(
        source,
        [
            {
                "id": "same-value",
                "input": "JSON",
                "response": '{"count": 1.0, "items": [true, null]}',
                "expected": {"items": [True, None], "count": 1},
                "scorer": "json",
            },
            {
                "id": "different-value",
                "input": "JSON",
                "response": '{"count": true}',
                "expected": {"count": 1},
                "scorer": "json",
            },
        ],
    )

    report = evaluate(load_records(source), source)

    assert report["summary"] == {"total": 2, "passed": 1, "failed": 1}
    assert report["cases"][1]["reason"] == "JSON value does not match expected"


def test_numeric_comparison_preserves_large_integer_precision(tmp_path):
    source = tmp_path / "answers.jsonl"
    expected = 9_007_199_254_740_992
    _write(
        source,
        [
            {
                "id": "precise",
                "input": "Number",
                "response": "9007199254740993",
                "expected": expected,
                "scorer": "numeric",
            }
        ],
    )

    records = load_records(source)
    report = evaluate(records, source)

    assert report["summary"]["failed"] == 1
    assert report["cases"][0]["tolerance"] == 0


def test_numeric_overflow_is_a_failed_case(tmp_path):
    source = tmp_path / "answers.jsonl"
    _write(
        source,
        [
            {
                "id": "huge",
                "input": "Number",
                "response": "1e1000000",
                "expected": 1,
                "scorer": "numeric",
            }
        ],
    )

    report = evaluate(load_records(source), source)

    assert report["summary"]["failed"] == 1
    assert report["cases"][0]["reason"] == "response is not a finite number"


def test_output_cannot_alias_input(tmp_path):
    source = tmp_path / "answers.jsonl"
    alias = tmp_path / "alias.jsonl"
    _write(source, [{"id": "x", "input": "x", "response": "x", "expected": "x", "scorer": "exact"}])
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("hard links are unavailable")

    result = _run(source, "--output", str(alias))

    assert result.returncode == 2
    assert "output must not overwrite the input file" in result.stderr
    assert load_records(source)[0]["id"] == "x"
