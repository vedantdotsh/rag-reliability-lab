"""Compare two saved-answer reports without trusting their stored scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from raglab.saved_eval import (
    _json_equal,
    _load_json,
    _same_file,
    _validate_generated_run,
    _validate_record,
    score_record,
    write_report,
)


def load_report(path: Path) -> dict[str, dict[str, Any]]:
    try:
        report = _load_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError(f"{path}: expected saved_eval schema_version 1 report")
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path}: cases must be a non-empty array")

    records = {}
    seen_ids: set[str] = set()
    for number, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            raise TypeError(f"{path}: case {number}: expected a JSON object")
        fields = {"id", "input", "response", "expected", "scorer"}
        missing = fields - case.keys()
        if missing:
            raise ValueError(
                f"{path}: case {number}: missing field(s): {', '.join(sorted(missing))}"
            )
        record = {key: case[key] for key in fields}
        for optional in ("category", "tolerance", "generation"):
            if optional in case:
                record[optional] = case[optional]
        try:
            record = _validate_record(record, number, seen_ids)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{path}: case {error}") from error
        records[record["id"]] = record
    _validate_generated_run(list(records.values()), path)
    return records


def _scope(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "input": record["input"],
        "expected": record["expected"],
        "scorer": record["scorer"],
        "category": record["category"],
        "tolerance": record.get("tolerance", 0) if record["scorer"] == "numeric" else None,
    }


def compare(
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
    baseline_label: str,
    candidate_label: str,
) -> dict[str, Any]:
    if baseline.keys() != candidate.keys():
        missing = sorted(baseline.keys() - candidate.keys())
        extra = sorted(candidate.keys() - baseline.keys())
        details = []
        if missing:
            details.append(f"missing from candidate: {', '.join(missing)}")
        if extra:
            details.append(f"only in candidate: {', '.join(extra)}")
        raise ValueError("case IDs differ (" + "; ".join(details) + ")")

    rows = []
    categories: dict[str, dict[str, int]] = {}
    improvements, regressions, unchanged_failures = [], [], []
    for case_id, left in baseline.items():
        right = candidate[case_id]
        left_scope, right_scope = _scope(left), _scope(right)
        mismatches = [
            field
            for field in left_scope
            if not _json_equal(left_scope[field], right_scope[field])
        ]
        if mismatches:
            raise ValueError(f"case {case_id!r} differs in: {', '.join(mismatches)}")
        left_passed, left_reason = score_record(left)
        right_passed, right_reason = score_record(right)
        category = left["category"]
        counts = categories.setdefault(
            category, {"total": 0, "baseline_passed": 0, "candidate_passed": 0, "delta": 0}
        )
        counts["total"] += 1
        counts["baseline_passed"] += left_passed
        counts["candidate_passed"] += right_passed
        counts["delta"] = counts["candidate_passed"] - counts["baseline_passed"]
        if not left_passed and right_passed:
            improvements.append(case_id)
        elif left_passed and not right_passed:
            regressions.append(case_id)
        elif not left_passed:
            unchanged_failures.append(case_id)
        rows.append(
            {
                "id": case_id,
                "category": category,
                "baseline_passed": left_passed,
                "candidate_passed": right_passed,
                "baseline_reason": left_reason,
                "candidate_reason": right_reason,
            }
        )

    baseline_passed = sum(row["baseline_passed"] for row in rows)
    candidate_passed = sum(row["candidate_passed"] for row in rows)
    return {
        "schema_version": 1,
        "kind": "saved_eval_comparison",
        "baseline": baseline_label,
        "candidate": candidate_label,
        "summary": {
            "total": len(rows),
            "baseline_passed": baseline_passed,
            "candidate_passed": candidate_passed,
            "delta": candidate_passed - baseline_passed,
            "improvements": len(improvements),
            "regressions": len(regressions),
            "unchanged_failures": len(unchanged_failures),
        },
        "categories": categories,
        "improvements": improvements,
        "regressions": regressions,
        "unchanged_failures": unchanged_failures,
        "cases": rows,
    }


def print_comparison(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Saved-answer comparison: {report['baseline']} -> {report['candidate']}")
    print(
        f"Cases: {summary['total']} | Passed: {summary['baseline_passed']} -> "
        f"{summary['candidate_passed']} ({summary['delta']:+d})"
    )
    print("\nBy category:")
    for category, counts in sorted(report["categories"].items()):
        print(
            f"  {category}: {counts['baseline_passed']}/{counts['total']} -> "
            f"{counts['candidate_passed']}/{counts['total']} ({counts['delta']:+d})"
        )
    for title, key in (
        ("Improvements", "improvements"),
        ("Regressions", "regressions"),
        ("Unchanged failures", "unchanged_failures"),
    ):
        values = report[key]
        print(f"\n{title}: {', '.join(values) if values else 'none'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two saved-answer JSON reports")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, help="Optionally save a JSON comparison")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.output and (
            _same_file(args.baseline, args.output) or _same_file(args.candidate, args.output)
        ):
            raise ValueError("output must not overwrite an input report")
        report = compare(
            load_report(args.baseline),
            load_report(args.candidate),
            args.baseline.stem,
            args.candidate.stem,
        )
        print_comparison(report)
        if args.output:
            write_report(report, args.output)
            print(f"\nJSON saved: {args.output}")
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))
    if report["regressions"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
