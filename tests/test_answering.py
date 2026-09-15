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

    def test_abstains_when_related_context_lacks_requested_detail(self):
        cases = [
            ("What is the phone number for 24/7 support?", "Support is available 24/7."),
            ("What is the base URL of the public API?", "The public API allows 100 requests."),
            ("What is the maximum number of exports that run simultaneously?",
             "Owners can run exports from Settings."),
            ("Which physical region hosts backups?", "Backups are stored in a separate region."),
            ("What is the documented response target for Severity 2 incidents?",
             "Severity 1 incidents receive a response within 15 minutes."),
        ]
        for question, text in cases:
            with self.subTest(question=question):
                self.assertEqual(
                    generate_extractive_answer(question, [_context("doc", text, 2.0)]),
                    ABSTENTION_ANSWER,
                )

    def test_answers_when_requested_detail_is_present(self):
        cases = [
            ("What is the phone number for support?", "The support phone number is +49 30 123456."),
            ("What is the base URL of the public API?", "The public API base URL is https://api.example.test/v1."),
            ("What is the maximum number of exports that run simultaneously?",
             "A maximum of 3 exports can run simultaneously."),
            ("Which physical region hosts backups?", "Backups are hosted in Frankfurt."),
            ("What is the documented response target for Severity 2 incidents?",
             "Severity 2 incidents receive a response within 2 hours."),
        ]
        for question, text in cases:
            with self.subTest(question=question):
                self.assertNotEqual(
                    generate_extractive_answer(question, [_context("doc", text, 2.0)]),
                    ABSTENTION_ANSWER,
                )

    def test_abstains_on_equally_scoped_conflicting_sources(self):
        contexts = [
            _context("old", "The maximum upload size is 25 MB.", 2.0),
            _context("new", "The maximum upload size is 100 MB.", 2.0),
        ]
        self.assertEqual(
            generate_extractive_answer("What is the maximum upload size?", contexts),
            ABSTENTION_ANSWER,
        )

    def test_numeric_corrections_remain_answerable(self):
        answer = generate_extractive_answer(
            "The API allows 500 requests per minute. Is that true?",
            [_context("api", "The API allows 600 requests per minute.", 2.0)],
        )
        self.assertIn("600 requests", answer)

    def test_unrelated_numeric_disagreement_does_not_block_an_answer(self):
        contexts = [
            _context("export", "Exports are delivered as a ZIP file.", 3.0),
            _context("old", "The maximum attachment upload size is 25 MB.", 2.0),
            _context("new", "The maximum attachment upload size is 100 MB.", 2.0),
        ]
        answer = generate_extractive_answer(
            "Is a workspace export delivered as a ZIP attachment?", contexts
        )
        self.assertIn("Exports are delivered as a ZIP file.", answer)

    def test_binds_requested_class_to_its_number(self):
        self.assertEqual(
            generate_extractive_answer(
                "What is the response target for Severity 2 incidents?",
                [_context("sev1", "Severity 1 incidents receive a response within 2 hours.", 2.0)],
            ),
            ABSTENTION_ANSWER,
        )

    def test_different_plan_values_are_qualified_not_conflicting(self):
        contexts = [
            _context("standard", "Application logs containing customer activity records are retained for 90 days on the Standard plan.", 2.0),
            _context("enterprise", "Application logs containing customer activity records are retained for 365 days on the Enterprise plan.", 2.0),
        ]
        self.assertNotEqual(
            generate_extractive_answer(
                "How long are application logs retained on Standard and Enterprise plans?", contexts
            ),
            ABSTENTION_ANSWER,
        )

    def test_date_is_not_a_phone_number(self):
        contexts = [
            _context("support", "Support is available 24/7.", 2.0),
            _context("terms", "Support terms were updated 2026-09-15.", 1.0),
        ]
        self.assertEqual(
            generate_extractive_answer("What is the support phone number?", contexts),
            ABSTENTION_ANSWER,
        )

    def test_unrelated_named_month_is_not_a_backup_region(self):
        text = "Backup checks happen in March. Backups are stored in a separate region."
        self.assertEqual(
            generate_extractive_answer(
                "Which physical region hosts backups?", [_context("backups", text, 2.0)]
            ),
            ABSTENTION_ANSWER,
        )


if __name__ == "__main__":
    unittest.main()
