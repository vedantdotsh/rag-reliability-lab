from __future__ import annotations

import re

from raglab.models import RetrievedDocument
from raglab.retriever import tokenize

ABSTENTION_ANSWER = "I could not find supporting context."


def _sentences(text: str) -> list[str]:
    # ponytail: split at sentence punctuation plus whitespace; abbreviations need a real segmenter.
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip()
    ]


def generate_extractive_answer(
    question: str,
    contexts: list[RetrievedDocument],
    *,
    max_sentences: int = 2,
) -> str:
    """Create a cited answer from source sentences that overlap the question."""
    question_terms = set(tokenize(question))
    candidates: list[tuple[float, int, str, str]] = []
    for rank, context in enumerate(contexts):
        if context.score <= 0:
            continue
        for sentence in _sentences(context.document.text):
            sentence_terms = set(tokenize(sentence))
            overlap = len(question_terms & sentence_terms)
            if not overlap:
                continue
            density = overlap / max(1, len(sentence_terms))
            score = overlap + density + context.score * 0.02 - rank * 0.05
            candidates.append((score, -rank, sentence, context.document.id))
    candidates.sort(key=lambda value: (-value[0], -value[1], value[2]))
    selected = candidates[:max_sentences]
    if not selected:
        return ABSTENTION_ANSWER
    return " ".join(f"{sentence} [{document_id}]" for _, _, sentence, document_id in selected)
