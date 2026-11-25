from __future__ import annotations

import argparse
import json
from pathlib import Path

from raglab import testgen_api
from raglab.data import load_cases, load_documents
from raglab.evaluation import (
    check_gate,
    compare_many,
    evaluate,
    format_metric,
    generate_rag,
    write_json_report,
)
from raglab.settings import (
    DEFAULT_CASES,
    DEFAULT_CORPUS,
    DEFAULT_THRESHOLDS,
)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path}")
    return value


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _config_summary(config: dict) -> str:
    return "/".join(
        str(config[key]) for key in ("retriever", "generator", "model", "source")
        if config.get(key)
    )


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
    evaluate_command.add_argument("--thresholds", type=Path, default=None)
    evaluate_command.add_argument("--report", type=Path, help="Optionally save JSON results")
    evaluate_command.add_argument("--top-k", type=int, default=3, choices=range(1, 11))
    evaluate_command.add_argument("--gate", action="store_true")
    generation = evaluate_command.add_mutually_exclusive_group()
    generation.add_argument("--model", help="Opt-in API generation; default is the baseline")
    generation.add_argument("--generations", type=Path, help="Replay recorded model responses")
    evaluate_command.add_argument("--provider", choices=tuple(testgen_api.PROVIDERS), default=None)
    evaluate_command.add_argument("--base-url")
    evaluate_command.add_argument("--api-key-env")
    evaluate_command.add_argument("--api-options", type=Path)

    generate_command = commands.add_parser("generate", help="Record model responses for replay")
    generate_command.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    generate_command.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    generate_command.add_argument("--top-k", type=int, default=3, choices=range(1, 11))
    generate_command.add_argument("--model", required=True)
    generate_command.add_argument(
        "--provider", choices=tuple(testgen_api.PROVIDERS), default="openai")
    generate_command.add_argument("--base-url")
    generate_command.add_argument("--api-key-env")
    generate_command.add_argument("--api-options", type=Path)
    generate_command.add_argument("--output", type=Path, required=True)

    compare_command = commands.add_parser("compare", help="Detect metric regression")
    compare_command.add_argument("baseline", type=Path)
    compare_command.add_argument("candidate", type=Path, nargs="+")
    compare_command.add_argument("--max-drop", type=float, default=0.02)
    compare_command.add_argument("--output", type=Path, help="Optionally save comparison JSON")
    return parser


def _run(args: argparse.Namespace) -> None:
    if args.command == "evaluate":
        if (args.model is not None or args.generations is not None) and args.thresholds is None:
            raise ValueError("Model runs require explicit --thresholds; "
                             "default latency policy is for the baseline")
        thresholds_path = args.thresholds or DEFAULT_THRESHOLDS
        thresholds = _load_json(thresholds_path)
        check_gate({}, thresholds)
        api_flags = (args.provider, args.base_url, args.api_key_env, args.api_options)
        inputs = {args.corpus.resolve(), args.cases.resolve(), thresholds_path.resolve()}
        if args.generations:
            inputs.add(args.generations.resolve())
        if args.api_options:
            inputs.add(args.api_options.resolve())
        if args.report is not None and args.report.resolve() in inputs:
            raise ValueError(f"--report must not overwrite input file: {args.report}")
        documents = load_documents(args.corpus)
        cases = load_cases(args.cases)
        if args.generations is not None:
            if any(value is not None for value in api_flags):
                raise ValueError("API options require --model")
            if args.report is not None and args.report.exists():
                raise ValueError(f"Refusing to overwrite existing file: {args.report}")
            rows = _load_jsonl(args.generations)
            report = evaluate(documents, cases, top_k=args.top_k, generations=rows)
        elif args.model is not None:
            if args.report is None:
                raise ValueError("--model requires --report so generated evidence is kept")
            generations_path = args.report.with_suffix(".generations.jsonl")
            for path in (args.report, generations_path):
                if path.resolve() in inputs:
                    raise ValueError(f"Output must not overwrite input file: {path}")
                if path.exists():
                    raise ValueError(f"Refusing to overwrite existing file: {path}")
            api_config = testgen_api.configuration(
                args.provider or "openai", args.base_url, args.api_key_env,
                _load_json(args.api_options) if args.api_options else None,
            )
            failures = generate_rag(
                documents, cases, generations_path, args.model, api_config, top_k=args.top_k)
            if failures:
                raise ValueError(
                    f"{failures} generation(s) failed; evidence kept in {generations_path}")
            report = evaluate(
                documents, cases, top_k=args.top_k,
                generations=_load_jsonl(generations_path),
            )
        elif any(value is not None for value in api_flags):
            raise ValueError("API options require --model")
        else:
            report = evaluate(documents, cases, top_k=args.top_k)
        gate = check_gate(report.metrics, thresholds)
        if args.report:
            write_json_report(report, args.report, gate)
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
        failures = [case for case in report.cases if case.issues]
        if failures:
            print(f"\nCases needing review ({len(failures)}):")
            for case in failures:
                print(f"  {case.id}: {', '.join(case.issues)}")
        if args.report:
            print(f"\nJSON saved: {args.report}")
        if args.gate and not gate["passed"]:
            raise SystemExit(1)
    elif args.command == "compare":
        comparison = compare_many(
            _load_json(args.baseline),
            [_load_json(path) for path in args.candidate],
            names=[str(path.resolve()) for path in args.candidate],
            max_drop=args.max_drop,
        )
        baseline_label = _config_summary(comparison["baseline_config"])
        print(f"Baseline: {args.baseline.resolve()}"
              + (f" ({baseline_label})" if baseline_label else ""))
        for candidate in comparison["candidates"]:
            marker = "PASS" if candidate["passed"] else "FAIL"
            label = _config_summary(candidate["config"])
            print(f"{marker} {candidate['name']}" + (f" ({label})" if label else ""))
            for row in candidate["metrics"]:
                marker = "PASS" if row["passed"] else "FAIL"
                delta = ("unavailable/invalid" if row["delta"] is None
                         else f"{row['delta']:+.4f}")
                print(f"  {marker} {row['metric']}: baseline {format_metric(row['baseline'])} "
                      f"candidate {format_metric(row['candidate'])} delta {delta}")
            for change in candidate["case_changes"]:
                details = [change["disposition"]] if change["disposition"] else []
                details += [
                    f"{key.replace('_', ' ')}: {', '.join(change[key])}"
                    for key in ("lost_phrases", "gained_phrases",
                                "lost_citations", "gained_citations")
                    if change[key]
                ]
                print(f"  case {change['id']}: " + "; ".join(details))
        print("Latency is checked by evaluate --gate, not by the regression comparison.")
        if args.output is not None:
            inputs = {args.baseline.resolve(),
                      *(path.resolve() for path in args.candidate)}
            if args.output.resolve() in inputs:
                raise ValueError(f"--output must not overwrite input file: {args.output}")
            if args.output.exists():
                raise ValueError(f"Refusing to overwrite existing file: {args.output}")
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(comparison, indent=2, allow_nan=False) + "\n")
        if not comparison["passed"]:
            raise SystemExit(1)
    elif args.command == "generate":
        inputs = {args.corpus.resolve(), args.cases.resolve()}
        if args.api_options:
            inputs.add(args.api_options.resolve())
        if args.output.resolve() in inputs:
            raise ValueError(f"Output must not overwrite input file: {args.output}")
        api_config = testgen_api.configuration(
            args.provider, args.base_url, args.api_key_env,
            _load_json(args.api_options) if args.api_options else None,
        )
        failures = generate_rag(
            load_documents(args.corpus), load_cases(args.cases),
            args.output, args.model, api_config, top_k=args.top_k,
        )
        if failures:
            raise SystemExit(1)
        print(f"Recorded generations: {args.output}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        _run(args)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
