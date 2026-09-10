from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from raglab.dashboard import DEFAULT_DATABASE, record_run, serve_dashboard
from raglab.data import load_cases, load_documents
from raglab.evaluation import (
    check_gate,
    compare_reports,
    evaluate,
    format_metric,
    write_json_report,
    write_markdown_report,
)
from raglab.settings import (
    DEFAULT_CASES,
    DEFAULT_CORPUS,
    DEFAULT_JSON_REPORT,
    DEFAULT_MARKDOWN_REPORT,
    DEFAULT_THRESHOLDS,
)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path}")
    return value


def _print_metrics(metrics: dict[str, float | None]) -> None:
    width = max(len(metric) for metric in metrics)
    for metric, value in metrics.items():
        print(f"{metric:<{width}}  {format_metric(value)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reproducible RAG evaluation and CI quality gates")
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate_command = commands.add_parser("evaluate", help="Run the golden evaluation dataset")
    evaluate_command.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    evaluate_command.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    evaluate_command.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    evaluate_command.add_argument("--report", type=Path, default=DEFAULT_JSON_REPORT)
    evaluate_command.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    evaluate_command.add_argument("--top-k", type=int, default=3, choices=range(1, 11))
    evaluate_command.add_argument("--gate", action="store_true")

    compare_command = commands.add_parser("compare", help="Detect metric regression")
    compare_command.add_argument("baseline", type=Path)
    compare_command.add_argument("candidate", type=Path)
    compare_command.add_argument("--max-drop", type=float, default=0.02)
    dashboard_command = commands.add_parser("dashboard", help="Open a local live analytics server")
    dashboard_command.add_argument("--port", type=int, default=8766)
    dashboard_command.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    return parser


def _run(args: argparse.Namespace) -> None:
    if args.command == "evaluate":
        report = evaluate(load_documents(args.corpus), load_cases(args.cases), top_k=args.top_k)
        thresholds = _load_json(args.thresholds)
        gate = check_gate(report.metrics, thresholds)
        write_json_report(report, args.report, gate)
        write_markdown_report(report, args.markdown, gate)
        record_run(args.report.parent / "runs.sqlite3", report=report.to_dict(), gate=gate)
        print(f"Evaluated {report.dataset_size} golden cases\n")
        _print_metrics(report.metrics)
        print(f"\nQuality gate: {'PASS' if gate['passed'] else 'FAIL'}")
        for check in gate["checks"]:
            marker = "PASS" if check["passed"] else "FAIL"
            print(
                f"  {marker} {check['metric']}={format_metric(check['actual'])} "
                f"{check['operator']} {check['threshold']:.4f}"
            )
            if check["reason"]:
                print(f"    {check['reason']}")
        print(f"\nReports: {args.report} and {args.markdown}")
        if args.gate and not gate["passed"]:
            raise SystemExit(1)
    elif args.command == "compare":
        comparison = compare_reports(
            _load_json(args.baseline),
            _load_json(args.candidate),
            max_drop=args.max_drop,
        )
        for row in comparison["metrics"]:
            marker = "PASS" if row["passed"] else "FAIL"
            delta = "unavailable/invalid" if row["delta"] is None else f"{row['delta']:+.4f}"
            print(f"{marker} {row['metric']}: {delta}")
        print("Latency is checked by evaluate --gate, not by the regression comparison.")
        if not comparison["passed"]:
            raise SystemExit(1)
    elif args.command == "dashboard":
        serve_dashboard(args.database, port=args.port)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        _run(args)
    except (OSError, ValueError, TypeError, sqlite3.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
