import unittest

from raglab.metrics import (
    citation_correctness,
    faithfulness,
    reciprocal_rank,
    required_phrase_coverage,
)
from raglab.models import Document, EvalCase

CASE = EvalCase("refund", "When?", ("refund",), ("within 30 days",))
EMPTY = EvalCase("unans", "Who won?", (), ())
DOCUMENTS = [Document("refund", "Refunds", "Subscriptions can be refunded within 30 days.")]
EMAIL_DOCUMENTS = [
    Document(
        "refund-policy",
        "Refunds",
        "Customers request a refund by emailing billing@example.test with the workspace ID. "
        "The public API allows 600.5 requests per minute.",
    )
]


class MetricTests(unittest.TestCase):
    def test_reciprocal_rank_rewards_earlier_result(self):
        self.assertEqual(reciprocal_rank(["other", "refund"], ("refund",)), 0.5)

    def test_required_phrase_coverage_checks_literal_presence(self):
        self.assertEqual(required_phrase_coverage("Refunds are available within 30 days.", CASE), 1.0)
        self.assertEqual(required_phrase_coverage("Not within 30 days.", CASE), 1.0)
        self.assertEqual(required_phrase_coverage("anything", EMPTY), 0.0)

    def test_citation_correctness_rejects_unknown_source(self):
        self.assertEqual(citation_correctness("Answer. [unknown]", ["refund"]), 0.0)
        self.assertEqual(citation_correctness("Invented. [refund]", ["refund"]), 1.0)

    def test_faithfulness_requires_claim_in_cited_document(self):
        answer = "Subscriptions can be refunded within 30 days. [refund]"
        self.assertEqual(faithfulness(answer, DOCUMENTS), 1.0)

    def test_faithfulness_counts_all_content(self):
        supported = "Subscriptions can be refunded within 30 days. [refund]"
        self.assertLess(faithfulness(supported + " Invented claim.", DOCUMENTS), 1.0)
        self.assertLess(faithfulness("Invented. " + supported, DOCUMENTS), 1.0)
        self.assertLess(faithfulness(supported + " trailing fragment", DOCUMENTS), 1.0)
        self.assertEqual(faithfulness("[refund]", DOCUMENTS), 0.0)
        self.assertEqual(
            faithfulness("Subscriptions cannot be refunded within 30 days. [refund]", DOCUMENTS),
            0.0,
        )

    def test_faithfulness_keeps_email_and_decimal_sentences_intact(self):
        answer = (
            "Customers request a refund by emailing billing@example.test with the workspace ID. "
            "[refund-policy]"
        )
        self.assertEqual(faithfulness(answer, EMAIL_DOCUMENTS), 1.0)
        decimal = "The public API allows 600.5 requests per minute. [refund-policy]"
        self.assertEqual(faithfulness(decimal, EMAIL_DOCUMENTS), 1.0)

    def test_faithfulness_counts_empty_citations_and_uncited_tail(self):
        answer = ("[refund][refund-policy] Subscriptions can be refunded within 30 days. "
                  "[refund] trailing uncited content.")
        self.assertEqual(faithfulness(answer, [DOCUMENTS[0], EMAIL_DOCUMENTS[0]]), 0.25)


if __name__ == "__main__":
    unittest.main()
