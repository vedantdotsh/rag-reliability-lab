from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    question: str
    expected_doc_ids: tuple[str, ...]
    required_facts: tuple[str, ...]
    should_abstain: bool = False
    category: str = "standard"


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    document: Document
    score: float


@dataclass(frozen=True, slots=True)
class CaseResult:
    id: str
    question: str
    retrieved_doc_ids: tuple[str, ...]
    answer: str
    hit_at_3: float | None
    reciprocal_rank: float | None
    source_recall_at_3: float | None
    required_phrase_coverage: float | None
    faithfulness: float | None
    citation_correctness: float | None
    latency_ms: float
    expected_doc_ids: tuple[str, ...]
    required_facts: tuple[str, ...]
    should_abstain: bool
    abstained: bool
    category: str
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("retrieved_doc_ids", "expected_doc_ids", "required_facts", "issues"):
            value[key] = list(value[key])
        return value


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    generated_at: str
    dataset_size: int
    config: dict[str, Any]
    metrics: dict[str, float | None]
    cases: tuple[CaseResult, ...]
    benchmark_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "benchmark_sha256": self.benchmark_sha256,
            "generated_at": self.generated_at,
            "dataset_size": self.dataset_size,
            "config": self.config,
            "metrics": self.metrics,
            "cases": [case.to_dict() for case in self.cases],
        }
