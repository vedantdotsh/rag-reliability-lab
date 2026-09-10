from __future__ import annotations

import json
import re
from pathlib import Path

from raglab.models import Document, EvalCase


def load_documents(path: str | Path) -> list[Document]:
    with Path(path).open(encoding="utf-8") as handle:
        values = json.load(handle)
    if not isinstance(values, list):
        raise TypeError(f"Expected a document array in {path}")
    try:
        documents = [Document(id=item["id"], title=item["title"], text=item["text"]) for item in values]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Each document in {path} needs id, title and text") from error
    return documents


def load_cases(path: str | Path) -> list[EvalCase]:
    cases = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}") from error
            try:
                if not all(isinstance(item[key], list) for key in ("expected_doc_ids", "required_facts")):
                    raise ValueError("expected_doc_ids and required_facts must be arrays")
                cases.append(EvalCase(
                    id=item["id"], question=item["question"],
                    expected_doc_ids=tuple(item["expected_doc_ids"]),
                    required_facts=tuple(item["required_facts"]),
                    should_abstain=item.get("should_abstain", False),
                    category=item.get("category", "standard"),
                ))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid case on line {line_number} of {path}: {error}") from error
    return cases


def validate_dataset(documents: list[Document], cases: list[EvalCase]) -> None:
    """Validate both file-loaded and directly supplied benchmark labels before scoring."""
    if not documents or not cases:
        raise ValueError("At least one document and one evaluation case are required")
    document_ids = set()
    for doc in documents:
        if not isinstance(doc.id, str) or not re.fullmatch(r"[a-z0-9-]+", doc.id):
            raise ValueError("Document IDs must use lowercase letters, digits and hyphens")
        if doc.id in document_ids:
            raise ValueError(f"Duplicate document ID: {doc.id}")
        document_ids.add(doc.id)
        if any(not isinstance(value, str) or not value.strip() for value in (doc.title, doc.text)):
            raise ValueError(f"Document {doc.id} needs nonempty title and text")
    case_ids = set()
    for case in cases:
        if any(not isinstance(value, str) or not value.strip()
               for value in (case.id, case.question, case.category)):
            raise ValueError("Every case needs nonempty id, question and category")
        if case.id in case_ids:
            raise ValueError(f"Duplicate case ID: {case.id}")
        case_ids.add(case.id)
        if not isinstance(case.should_abstain, bool):
            raise TypeError(f"Case {case.id}: should_abstain must be a boolean")
        for values in (case.expected_doc_ids, case.required_facts):
            if not isinstance(values, (list, tuple)) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"Case {case.id}: source IDs and facts must be lists of strings")
            if len(set(values)) != len(values):
                raise ValueError(f"Case {case.id}: duplicate source IDs or required facts")
        if case.should_abstain:
            if case.expected_doc_ids or case.required_facts:
                raise ValueError(f"Case {case.id}: abstention cases must have empty sources and facts")
        elif not case.expected_doc_ids or not case.required_facts:
            raise ValueError(f"Case {case.id}: answerable cases need expected sources and facts")
        if not set(case.expected_doc_ids) <= document_ids:
            raise ValueError(f"Case {case.id}: expected source does not exist in corpus")
        for fact in case.required_facts:
            if not any(fact.lower() in doc.text.lower() for doc in documents
                       if doc.id in case.expected_doc_ids):
                raise ValueError(
                    f"Case {case.id}: required phrase {fact!r} is absent from its expected sources"
                )
