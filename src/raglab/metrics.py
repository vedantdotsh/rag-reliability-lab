from __future__ import annotations

import re

from raglab.answering import _sentences
from raglab.models import Document, EvalCase

CITATION_PATTERN = re.compile(r"\[([a-z0-9-]+)\]")
_CITE_SPLIT = re.compile(r"(\[[a-z0-9-]+\])")


def hit_at_k(retrieved_ids: list[str], expected_ids: tuple[str, ...], k: int = 3) -> float:
    return float(bool(set(retrieved_ids[:k]) & set(expected_ids)))


def reciprocal_rank(retrieved_ids: list[str], expected_ids: tuple[str, ...]) -> float:
    expected = set(expected_ids)
    for rank, document_id in enumerate(retrieved_ids, 1):
        if document_id in expected:
            return 1.0 / rank
    return 0.0


def required_phrase_coverage(answer: str, case: EvalCase) -> float:
    """Literal required-phrase presence, not semantic correctness.

    A fact counts when it appears as a case-insensitive substring of the answer.
    Negation and paraphrase are not interpreted. Empty required_facts returns 0.0
    so unanswerable cases are not scored as perfect answers.
    """
    if not case.required_facts:
        return 0.0
    answer_lower = answer.lower()
    found = sum(fact.lower() in answer_lower for fact in case.required_facts)
    return found / len(case.required_facts)


def citation_correctness(answer: str, retrieved_ids: list[str]) -> float:
    """Share of [document-id] citations whose IDs appear in retrieved_ids.

    Checks citation IDs only, not whether the surrounding claim is supported.
    IDs must be lowercase letters, digits, or hyphens. No citations scores 0.0.
    """
    citations = CITATION_PATTERN.findall(answer.lower())
    if not citations:
        return 0.0
    retrieved = set(retrieved_ids)
    return sum(citation in retrieved for citation in citations) / len(citations)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _claim_units(answer: str) -> list[tuple[str, str | None]]:
    units: list[tuple[str, str | None]] = []
    pieces = _CITE_SPLIT.split(answer.lower())
    index = 0
    while index < len(pieces):
        piece = pieces[index]
        if CITATION_PATTERN.fullmatch(piece):
            units.append(("", piece[1:-1]))
            index += 1
            continue
        cited = index + 1 < len(pieces) and CITATION_PATTERN.fullmatch(pieces[index + 1])
        sentences = _sentences(piece)
        if cited:
            citation = pieces[index + 1][1:-1]
            if sentences:
                units.extend((sentence, None) for sentence in sentences[:-1])
                units.append((sentences[-1], citation))
            else:
                units.append(("", citation))
            index += 2
            continue
        units.extend((sentence, None) for sentence in sentences)
        index += 1
    return units


def faithfulness(answer: str, documents: list[Document]) -> float:
    """Exact-source support over all answer content, not just cited sentences.

    A unit is grounded only when it is cited and the normalized claim is a
    substring of that cited document's text. Case and whitespace are normalized.
    Uncited sentences, trailing fragments, and citation-only pieces count as
    unsupported. This is not NLI: contradicted or paraphrased text fails unless
    it occurs verbatim in the cited source.
    """
    source_by_id = {document.id: _normalize(document.text) for document in documents}
    units = _claim_units(answer)
    if not units:
        return 0.0
    grounded = 0
    for claim, document_id in units:
        if document_id is None:
            continue
        normalized_claim = _normalize(claim)
        if normalized_claim and normalized_claim in source_by_id.get(document_id, ""):
            grounded += 1
    return grounded / len(units)
