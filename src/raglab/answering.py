from __future__ import annotations

import re

from raglab.models import RetrievedDocument
from raglab.retriever import tokenize

ABSTENTION_ANSWER = "I could not find supporting context."
_NUMBER = re.compile(r"\b\d+(?::\d+)?\b")
_TIME_UNIT = r"(?:minutes?|hours?|days?|weeks?|months?|years?|business day)"


def _sentences(text: str) -> list[str]:
    # ponytail: split at sentence punctuation plus whitespace; abbreviations need a real segmenter.
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip()
    ]


def _verification_question(question: str) -> bool:
    lowered = question.strip().lower()
    return bool(
        re.match(r"(?:are|can|could|do|does|is|was|were|will)\b", lowered)
        or re.search(r"\b(?:is|was) (?:that|this|the claim) (?:accurate|allowed|correct|true)\b", lowered)
        or re.search(r"\b(?:is|does|can|are) (?:this|that|it)\b", lowered)
        or "outcome" in lowered
    )


def _conflicting_facts(question: str, candidates: list[tuple[float, int, str, str]]) -> bool:
    question_terms = set(tokenize(question))
    facts = []
    for _, _, sentence, document_id in candidates:
        numbers = tuple(_NUMBER.findall(sentence.lower()))
        if numbers:
            core = tuple(tokenize(_NUMBER.sub("", sentence)))
            facts.append((core, numbers, document_id))
    for index, (left, left_numbers, left_document) in enumerate(facts):
        for right, right_numbers, right_document in facts[index + 1:]:
            if (
                left_document != right_document
                and left == right
                and len(set(left) & question_terms) >= 2
                and left_numbers != right_numbers
            ):
                return True
    return False


def _has_phone_value(sentence: str) -> bool:
    explicit = re.search(r"\+\d[\d ().-]{6,}\d", sentence)
    if explicit:
        return True
    match = re.search(
        r"\b(?:phone|telephone|tel|call|contact)(?: number)?\b\D{0,20}"
        r"(\d[\d ().-]{6,}\d)",
        sentence,
        re.IGNORECASE,
    )
    if not match or re.fullmatch(r"\d{4}-\d{2}-\d{2}", match.group(1)):
        return False
    return len(re.sub(r"\D", "", match.group(1))) >= 7


def _supports_requested_detail(
    question: str, candidates: list[tuple[float, int, str, str]]
) -> bool:
    """Reject related passages that do not contain the kind of fact being requested."""
    lowered = question.lower()
    sentences = [sentence for _, _, sentence, _ in candidates]
    evidence = " ".join(sentences).lower()
    verification = _verification_question(question)

    if not verification:
        requested_numbers = set(_NUMBER.findall(lowered))
        if requested_numbers - set(_NUMBER.findall(evidence)):
            return False
        typed_numbers = re.findall(r"\b([a-z][a-z-]+)\s+(\d+)\b", lowered)
        if any(
            not re.search(rf"\b{re.escape(kind)}\s+{re.escape(number)}\b", evidence)
            for kind, number in typed_numbers
        ):
            return False
    if "phone number" in lowered and not any(_has_phone_value(sentence) for sentence in sentences):
        return False
    if (
        "url" in lowered
        and any(word in lowered for word in ("base", "exact", "format"))
        and not any(re.search(r"https?://\S+", sentence, re.IGNORECASE) for sentence in sentences)
    ):
        return False
    if "status code" in lowered and not re.search(r"\bhttp\s+\d{3}\b", evidence):
        return False
    if "format" in lowered and not re.search(
        r"\b(?:format|syntax|pattern|example)\b|\b(?:delivered|provided|returned) as\b",
        evidence,
    ):
        return False
    if any(phrase in lowered for phrase in ("how long", "retention duration")) and not re.search(
        rf"\b\d+(?:[- ]{_TIME_UNIT}|\s*:\s*\d+)|monday through friday", evidence
    ):
        return False
    if re.search(r"\b(?:how many|maximum number)\b", lowered) and not _NUMBER.search(evidence):
        return False
    if "simultaneously" in lowered and not re.search(
        r"\b(?:simultaneously|concurrent(?:ly)?|at (?:a time|once))\b", evidence
    ):
        return False
    if "besides" in lowered and not re.search(
        r"\b(?:besides|other|include|including|such as|for example)\b", evidence
    ):
        return False
    if "physical region" in lowered:
        named_region = any(
            re.search(
                r"\b(?:stored|hosted|located|kept)\s+(?:in|at|within)\s+"
                r"(?!a\b|an\b|the\b|another\b|separate\b)[A-Z][\w-]+",
                sentence,
            )
            or re.search(r"\bregion\s+(?:is|:)\s+[A-Z][\w-]+", sentence)
            for sentence in sentences
        )
        if not named_region and not re.search(r"\b[a-z]{2}-[a-z]+-\d\b", evidence):
            return False
    if "exact" in lowered and "header" in lowered and " that " in lowered:
        relation = set(tokenize(lowered.split(" that ", 1)[1]))
        if relation and max(
            (len(relation & set(tokenize(sentence))) / len(relation) for sentence in sentences),
            default=0,
        ) < 0.75:
            return False
    return not (
        re.search(r"\bwhich\s+(?:\w+[ -])?algorithm\b", lowered)
        and "algorithm" not in evidence
    )


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
    if not candidates or _conflicting_facts(question, candidates) or not _supports_requested_detail(
        question, candidates
    ):
        return ABSTENTION_ANSWER
    selected = candidates[:max_sentences]
    return " ".join(f"{sentence} [{document_id}]" for _, _, sentence, document_id in selected)
