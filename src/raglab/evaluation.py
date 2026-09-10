from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from raglab.answering import ABSTENTION_ANSWER, generate_extractive_answer
from raglab.data import validate_dataset
from raglab.metrics import (
    citation_correctness,
    faithfulness,
    hit_at_k,
    reciprocal_rank,
    required_phrase_coverage,
)
from raglab.models import CaseResult, Document, EvalCase, EvaluationReport
from raglab.retriever import BM25Retriever


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def evaluate(
    documents: list[Document], cases: list[EvalCase], *, top_k: int = 3,
) -> EvaluationReport:
    validate_dataset(documents, cases)
    retriever = BM25Retriever(documents)
    results = []
    for case in cases:
        started = time.perf_counter()
        contexts = retriever.search(case.question, top_k=top_k)
        retrieved_ids = [context.document.id for context in contexts]
        answer = generate_extractive_answer(case.question, contexts)
        latency_ms = (time.perf_counter() - started) * 1000
        abstained = answer == ABSTENTION_ANSWER
        answerable = not case.should_abstain
        missing_sources = set(case.expected_doc_ids) - set(retrieved_ids[:3])
        missing_phrases = [fact for fact in case.required_facts if fact.lower() not in answer.lower()]
        source_score = faithfulness(answer, documents) if answerable else None
        citation_score = citation_correctness(answer, retrieved_ids) if answerable else None
        issues = []
        if case.should_abstain != abstained:
            issues.append("Expected abstention; returned an answer" if case.should_abstain
                          else "Expected an answer; abstained")
        if missing_sources:
            issues.append("Expected sources missing from top 3: " + ", ".join(sorted(missing_sources)))
        if missing_phrases:
            issues.append("Required phrases missing: " + "; ".join(missing_phrases))
        if answerable and not abstained:
            if source_score < 1:
                issues.append("Answer contains content not exactly supported by its cited source")
            if citation_score < 1:
                issues.append("Answer has missing or invalid retrieved-source citations")
        results.append(CaseResult(
            id=case.id, question=case.question, retrieved_doc_ids=tuple(retrieved_ids), answer=answer,
            hit_at_3=hit_at_k(retrieved_ids, case.expected_doc_ids, k=3) if answerable else None,
            reciprocal_rank=reciprocal_rank(retrieved_ids, case.expected_doc_ids)
            if answerable else None,
            source_recall_at_3=(1 - len(missing_sources) / len(case.expected_doc_ids))
            if answerable else None,
            required_phrase_coverage=required_phrase_coverage(answer, case) if answerable else None,
            faithfulness=source_score, citation_correctness=citation_score,
            latency_ms=latency_ms, expected_doc_ids=case.expected_doc_ids,
            required_facts=case.required_facts, should_abstain=case.should_abstain,
            abstained=abstained, category=case.category, issues=tuple(issues),
        ))
    answerable_results = [result for result in results if not result.should_abstain]
    unanswerable_results = [result for result in results if result.should_abstain]
    metrics = {}
    for name, field in (
        ("hit_rate_at_3", "hit_at_3"), ("mean_reciprocal_rank", "reciprocal_rank"),
        ("source_recall_at_3", "source_recall_at_3"),
        ("required_phrase_coverage", "required_phrase_coverage"),
        ("faithfulness", "faithfulness"), ("citation_correctness", "citation_correctness"),
    ):
        metrics[name] = (
            mean(getattr(result, field) for result in answerable_results)
            if answerable_results else None
        )
    metrics["answerable_response_rate"] = (
        mean(not result.abstained for result in answerable_results) if answerable_results else None
    )
    metrics["unanswerable_abstention_rate"] = (
        mean(result.abstained for result in unanswerable_results) if unanswerable_results else None
    )
    metrics["p95_latency_ms"] = _percentile([result.latency_ms for result in results], 0.95)
    benchmark = {
        "documents": [asdict(doc) for doc in sorted(documents, key=lambda doc: doc.id)],
        "cases": [asdict(case) for case in sorted(cases, key=lambda case: case.id)],
    }
    fingerprint = hashlib.sha256(json.dumps(benchmark, sort_keys=True).encode()).hexdigest()
    return EvaluationReport(
        generated_at=datetime.now(UTC).isoformat(), dataset_size=len(cases),
        config={"retriever": "bm25", "generator": "extractive", "top_k": top_k},
        metrics=metrics,  # Round only for display; rounding before the gate can hide small failures.
        cases=tuple(results), benchmark_sha256=fingerprint,
    )


def _valid_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def check_gate(metrics: dict[str, float | None], thresholds: dict[str, float]) -> dict[str, Any]:
    if not isinstance(thresholds, dict) or not thresholds:
        raise ValueError("At least one quality threshold is required")
    if not isinstance(metrics, dict):
        raise TypeError("Metrics must be an object")
    checks = []
    for threshold_name, threshold in thresholds.items():
        if not isinstance(threshold_name, str) or not threshold_name or not _valid_number(threshold):
            raise ValueError(f"Invalid threshold: {threshold_name!r}; expected a finite nonnegative number")
        is_maximum = threshold_name.endswith("_max")
        metric_name = threshold_name.removesuffix("_max") if is_maximum else threshold_name
        actual = metrics.get(metric_name)
        valid = _valid_number(actual)
        checks.append({
            "metric": metric_name, "actual": actual if valid else None,
            "operator": "<=" if is_maximum else ">=", "threshold": threshold,
            "passed": valid and (actual <= threshold if is_maximum else actual >= threshold),
            "reason": "" if valid else "Metric missing, unavailable or not a finite nonnegative number",
        })
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def compare_reports(
    baseline: dict[str, Any], candidate: dict[str, Any], *, max_drop: float = 0.02,
) -> dict[str, Any]:
    if not _valid_number(max_drop) or max_drop > 1:
        raise ValueError("max_drop must be a finite number between 0 and 1")
    if any(not isinstance(report, dict) or report.get("schema_version") != 2
           for report in (baseline, candidate)):
        raise ValueError("Comparison requires schema version 2 reports; rerun the old baseline")
    if (not baseline.get("benchmark_sha256")
            or baseline["benchmark_sha256"] != candidate.get("benchmark_sha256")):
        raise ValueError("Cannot compare reports from different corpora or evaluation cases")
    baseline_metrics, candidate_metrics = baseline.get("metrics"), candidate.get("metrics")
    if (not isinstance(baseline_metrics, dict) or not baseline_metrics
            or not isinstance(candidate_metrics, dict)
            or baseline_metrics.keys() != candidate_metrics.keys()):
        raise ValueError("Reports must contain the same nonempty metric set")
    rows = []
    for metric, baseline_value in baseline_metrics.items():
        if metric.endswith("latency_ms"):
            continue  # Hardware-sensitive latency is enforced by the absolute quality gate.
        candidate_value = candidate_metrics[metric]
        if baseline_value is None and candidate_value is None:
            continue  # The benchmark has no cases for this subgroup in either run.
        valid = _valid_number(baseline_value) and _valid_number(candidate_value)
        delta = candidate_value - baseline_value if valid else None
        rows.append({
            "metric": metric, "baseline": baseline_value, "candidate": candidate_value,
            "delta": round(delta, 4) if valid else None,
            "passed": valid and (delta >= -max_drop or math.isclose(delta, -max_drop, abs_tol=1e-12)),
        })
    return {"passed": bool(rows) and all(row["passed"] for row in rows),
            "max_drop": max_drop, "metrics": rows}


def write_json_report(
    report: EvaluationReport, path: str | Path, gate: dict[str, Any] | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    if gate is not None:
        payload["gate"] = gate
    target.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def format_metric(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def write_markdown_report(
    report: EvaluationReport, path: str | Path, gate: dict[str, Any] | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    answerable_count = sum(not case.should_abstain for case in report.cases)
    lines = [
        "# RAG Evaluation Report", "", f"Generated: `{report.generated_at}`  ",
        (f"Dataset: **{report.dataset_size} cases** ({answerable_count} answerable, "
         f"{report.dataset_size - answerable_count} unanswerable)  "),
        f"Pipeline: **{report.config['retriever']} retrieval + {report.config['generator']} generation**",
        f"Benchmark SHA-256: `{report.benchmark_sha256}`", "",
        ("Quality metrics average answerable cases only. Unanswerable cases are scored by their "
         "abstention rate. N/A means the benchmark has no cases for that metric."), "",
        ("Required phrase coverage is literal text matching, not semantic correctness. "
         "Faithfulness checks exact cited source text, not truth or answer relevance."), "",
        "## Aggregate metrics", "", "| Metric | Value |", "|---|---:|",
    ]
    for metric, value in report.metrics.items():
        lines.append(f"| `{metric}` | {format_metric(value)} |")
    if gate:
        lines.extend([
            "", f"## Quality gate: {'PASS' if gate['passed'] else 'FAIL'}", "",
            "| Metric | Actual | Required | Result |", "|---|---:|---:|:---:|",
        ])
        for check in gate["checks"]:
            result = "PASS" if check["passed"] else "FAIL"
            if check["reason"]:
                result += ": " + check["reason"]
            lines.append(f"| `{check['metric']}` | {format_metric(check['actual'])} | "
                         f"{check['operator']} {check['threshold']:.4f} | {result} |")
    lines.extend([
        "", "## Case details", "",
        "| Case | Category | Expected | Actual | Hit@3 | Source recall@3 | Phrase coverage | Issues |",
        "|---|---|---|---|---:|---:|---:|---|",
    ])
    for result in report.cases:
        expected = "Abstain" if result.should_abstain else "Answer"
        actual = "Abstain" if result.abstained else "Answer"
        lines.append(f"| {_markdown_cell(result.id)} | {_markdown_cell(result.category)} | {expected} | "
                     f"{actual} | {format_metric(result.hit_at_3)} | "
                     f"{format_metric(result.source_recall_at_3)} | "
                     f"{format_metric(result.required_phrase_coverage)} | "
                     f"{_markdown_cell('; '.join(result.issues)) or '—'} |")
    lines.extend(["", "## Failure evidence", ""])
    for result in report.cases:
        if result.issues:
            lines.extend([
                f"### {_markdown_cell(result.id)}", "",
                f"Question: {_markdown_cell(result.question)}", "",
                f"Answer: {_markdown_cell(result.answer)}", "",
                "Retrieved: " + ", ".join(result.retrieved_doc_ids), "",
                "Expected sources: " + (", ".join(result.expected_doc_ids) or "None (unanswerable)"),
                "", "Issues: " + _markdown_cell("; ".join(result.issues)), "",
            ])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
