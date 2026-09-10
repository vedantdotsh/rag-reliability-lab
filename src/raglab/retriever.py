from __future__ import annotations

import math
import re
from collections import Counter

from raglab.models import Document, RetrievedDocument

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "their", "this",
    "to", "what", "when", "which", "who", "with",
}


def _stem(token: str) -> str:
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(token) for token in tokens if token not in STOP_WORDS]


class BM25Retriever:
    """Small inspectable BM25 implementation for deterministic offline evaluation."""

    def __init__(self, documents: list[Document], *, k1: float = 1.5, b: float = 0.75):
        if not documents:
            raise ValueError("At least one document is required")
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.term_frequencies = [Counter(tokenize(f"{doc.title} {doc.text}")) for doc in documents]
        self.lengths = [sum(frequencies.values()) for frequencies in self.term_frequencies]
        self.average_length = sum(self.lengths) / len(self.lengths)
        self.document_frequency = Counter(
            token for frequencies in self.term_frequencies for token in frequencies
        )

    def search(self, query: str, *, top_k: int = 3) -> list[RetrievedDocument]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        query_terms = set(tokenize(query))
        if not query_terms:
            return []
        scored = []
        total_documents = len(self.documents)
        for index, document in enumerate(self.documents):
            frequencies = self.term_frequencies[index]
            score = 0.0
            for term in query_terms:
                term_frequency = frequencies.get(term, 0)
                if not term_frequency:
                    continue
                document_frequency = self.document_frequency[term]
                inverse_document_frequency = math.log(
                    1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                denominator = term_frequency + self.k1 * (
                    1 - self.b + self.b * self.lengths[index] / self.average_length
                )
                score += inverse_document_frequency * term_frequency * (self.k1 + 1) / denominator
            if score > 0:
                scored.append(RetrievedDocument(document=document, score=score))
        scored.sort(key=lambda item: (-item.score, item.document.id))
        return scored[:top_k]

