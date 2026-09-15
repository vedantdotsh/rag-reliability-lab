"""Evaluate saved answers from a hand-authored JSONL file."""

from __future__ import annotations

import argparse
import json
import math
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

SCORERS = {"exact", "json", "numeric", "valid_json"}
REQUIRED_FIELDS = {"id", "input", "response", "expected", "scorer"}
OPTIONAL_FIELDS = {"category", "tolerance", "generation"}


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite number {value}")


def _parse_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite number {value}")
    return parsed


def _load_json(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_constant, parse_float=_parse_float)


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and Decimal(str(value)).is_finite()
    )


def _validate_record(record: Any, line: int, seen_ids: set[str]) -> dict[str, Any]:
    prefix = f"{line}: "
    if not isinstance(record, dict):
        raise TypeError(prefix + "expected a JSON object")

    fields = set(record)
    missing = REQUIRED_FIELDS - fields
    unknown = fields - REQUIRED_FIELDS - OPTIONAL_FIELDS
    if missing:
        raise ValueError(prefix + f"missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(prefix + f"unknown field(s): {', '.join(sorted(unknown))}")

    case_id = record["id"]
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError(prefix + "id must be a non-empty string")
    if case_id in seen_ids:
        raise ValueError(prefix + f"duplicate id {case_id!r}")
    seen_ids.add(case_id)

    for field in ("input", "response"):
        if not isinstance(record[field], str):
            raise TypeError(prefix + f"{field} must be a string")
    category = record.get("category", "uncategorized")
    if not isinstance(category, str) or not category.strip():
        raise ValueError(prefix + "category must be a non-empty string")

    scorer = record["scorer"]
    if not isinstance(scorer, str) or scorer not in SCORERS:
        raise ValueError(prefix + f"scorer must be one of: {', '.join(sorted(SCORERS))}")
    if scorer == "exact":
        if not isinstance(record["expected"], str):
            raise ValueError(prefix + "exact expected must be a string")
        if "tolerance" in record:
            raise ValueError(prefix + "tolerance is only allowed for the numeric scorer")
    elif scorer == "numeric":
        if not _finite_number(record["expected"]):
            raise ValueError(prefix + "numeric expected must be a finite JSON number")
        tolerance = record.get("tolerance", 0)
        if not _finite_number(tolerance) or tolerance < 0:
            raise ValueError(prefix + "tolerance must be a finite non-negative number")
    elif scorer == "valid_json":
        if record["expected"] is not None:
            raise ValueError(prefix + "valid_json expected must be null")
        if "tolerance" in record:
            raise ValueError(prefix + "tolerance is only allowed for the numeric scorer")
    elif "tolerance" in record:
        raise ValueError(prefix + "tolerance is only allowed for the numeric scorer")

    if "generation" in record:
        generation = record["generation"]
        if not isinstance(generation, dict):
            raise TypeError(prefix + "generation must be an object")
        status = generation.get("execution_status")
        if not isinstance(status, str) or status not in {
            "completed", "provider_error", "harness_error"
        }:
            raise ValueError(prefix + "generation has an invalid execution_status")
        generation_error = generation.get("generation_error")
        if generation_error is not None and (
            not isinstance(generation_error, str) or not generation_error.strip()
        ):
            raise ValueError(prefix + "generation_error must be a non-empty string")
        if (status == "completed") == bool(generation_error):
            raise ValueError(prefix + "generation status and error disagree")

    return {**record, "category": category}


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            try:
                value = _load_json(raw_line)
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            try:
                records.append(_validate_record(value, line_number, seen_ids))
            except (TypeError, ValueError) as error:
                raise ValueError(f"{path}:{error}") from error
    if not records:
        raise ValueError(f"{path}: no records found")
    _validate_generated_run(records, path)
    return records


def _validate_generated_run(records: list[dict[str, Any]], path: Path) -> None:
    generated = [record for record in records if "generation" in record]
    if generated:
        if len(generated) != len(records):
            raise ValueError(f"{path}: generated and hand-authored records cannot be mixed")
        totals = [record["generation"].get("total_cases") for record in records]
        indexes = [record["generation"].get("case_index") for record in records]
        if (
            any(type(value) is not int for value in totals + indexes)
            or totals != [len(records)] * len(records)
            or indexes != list(range(1, len(records) + 1))
        ):
            raise ValueError(f"{path}: generated run is partial or out of order")


def _json_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return Decimal(str(actual)) == Decimal(str(expected))
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            _json_equal(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _json_equal(left, right) for left, right in zip(actual, expected, strict=True)
        )
    return actual == expected


def score_record(record: dict[str, Any]) -> tuple[bool, str | None]:
    generation = record.get("generation")
    if generation and generation["execution_status"] != "completed":
        return False, "generation failed: " + generation["generation_error"]
    scorer = record["scorer"]
    response = record["response"]
    if scorer == "exact":
        passed = response == record["expected"]
        return passed, None if passed else "exact match failed"
    if scorer == "numeric":
        try:
            actual_value = _load_json(response)
        except json.JSONDecodeError:
            return False, "response is not a number"
        except ValueError:
            return False, "response is not a finite number"
        if not _finite_number(actual_value):
            return False, "response is not a number"
        actual = Decimal(response.strip())
        expected = Decimal(str(record["expected"]))
        tolerance = Decimal(str(record.get("tolerance", 0)))
        difference = abs(actual - expected)
        passed = difference <= tolerance
        reason = (
            None
            if passed
            else f"absolute difference {difference:g} exceeds tolerance {tolerance:g}"
        )
        return passed, reason
    try:
        actual = _load_json(response)
    except (json.JSONDecodeError, ValueError) as error:
        return False, f"response is not valid JSON: {error}"
    if scorer == "json":
        passed = _json_equal(actual, record["expected"])
        return passed, None if passed else "JSON value does not match expected"
    return True, None


def evaluate(records: list[dict[str, Any]], source: Path) -> dict[str, Any]:
    cases = []
    categories: dict[str, dict[str, int]] = {}
    for record in records:
        passed, reason = score_record(record)
        category = record["category"]
        counts = categories.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        counts["total"] += 1
        counts["passed" if passed else "failed"] += 1
        case = {
            "id": record["id"],
            "input": record["input"],
            "response": record["response"],
            "expected": record["expected"],
            "scorer": record["scorer"],
            "category": category,
            "passed": passed,
            "reason": reason,
        }
        if record["scorer"] == "numeric":
            case["tolerance"] = record.get("tolerance", 0)
        if "generation" in record:
            case["generation"] = record["generation"]
        cases.append(case)
    passed = sum(case["passed"] for case in cases)
    return {
        "schema_version": 1,
        "source": str(source),
        "summary": {"total": len(cases), "passed": passed, "failed": len(cases) - passed},
        "categories": categories,
        "cases": cases,
    }


def _same_file(input_path: Path, output_path: Path) -> bool:
    if input_path.resolve() == output_path.resolve():
        return True
    return output_path.exists() and input_path.samefile(output_path)


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Saved-answer evaluation: {'PASS' if summary['failed'] == 0 else 'FAIL'}")
    print(f"Cases: {summary['total']} | Passed: {summary['passed']} | Failed: {summary['failed']}")
    print("\nBy category:")
    for category, counts in sorted(report["categories"].items()):
        print(
            f"  {category}: {counts['passed']}/{counts['total']} passed ({counts['failed']} failed)"
        )
    failures = [case for case in report["cases"] if not case["passed"]]
    if failures:
        print("\nFailures:")
        for case in failures:
            print(f"  {case['id']} [{case['category']}; {case['scorer']}]")
            print(f"    Input: {case['input']}")
            print(f"    Expected: {case['expected']!r}")
            print(f"    Response: {case['response']!r}")
            print(f"    Reason: {case['reason']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate saved answers from JSONL")
    parser.add_argument("input", type=Path, help="JSONL records to evaluate")
    parser.add_argument("--output", type=Path, help="Optionally save a JSON report")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.output and _same_file(args.input, args.output):
            raise ValueError("output must not overwrite the input file")
        report = evaluate(load_records(args.input), args.input)
        if args.output:
            write_report(report, args.output)
        print_report(report)
        if args.output:
            print(f"\nJSON saved: {args.output}")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if report["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
