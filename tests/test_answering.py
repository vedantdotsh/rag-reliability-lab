import unittest

from raglab.answering import ABSTENTION_ANSWER, generate_extractive_answer
from raglab.models import Document, RetrievedDocument


def _context(document_id: str, text: str, score: float) -> RetrievedDocument:
    return RetrievedDocument(Document(document_id, document_id, text), score)


class AnsweringTests(unittest.TestCase):
    def test_abstains_without_supported_overlap(self):
        contexts = [_context("a", "The sky is blue.", 2.0)]
        answer = generate_extractive_answer("How do refunds work?", contexts)
        self.assertEqual(answer, ABSTENTION_ANSWER)

    def test_ignores_nonpositive_score_contexts(self):
        text = "Subscriptions can be refunded within 30 days."
        self.assertEqual(
            generate_extractive_answer("When are refunds allowed?", [_context("a", text, 0.0)]),
            ABSTENTION_ANSWER,
        )
        self.assertEqual(
            generate_extractive_answer("When are refunds allowed?", [_context("a", text, -1.0)]),
            ABSTENTION_ANSWER,
        )

    def test_extracts_overlapping_sentence_with_citation(self):
        text = "Subscriptions can be refunded within 30 days."
        answer = generate_extractive_answer(
            "When can subscriptions be refunded?",
            [_context("refund", text, 1.5)],
        )
        self.assertEqual(answer, f"{text} [refund]")

    def test_keeps_email_sentence_together(self):
        text = (
            "Customers request a refund by emailing billing@example.test "
            "with the workspace ID and invoice number."
        )
        answer = generate_extractive_answer(
            "What email is used to request a refund?",
            [_context("refund-policy", text, 1.0)],
        )
        self.assertIn(text, answer)
        self.assertIn("[refund-policy]", answer)


if __name__ == "__main__":
    unittest.main()
