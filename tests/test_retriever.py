import unittest

from raglab.models import Document
from raglab.retriever import BM25Retriever, tokenize

DOCUMENTS = [
    Document("refund", "Refund policy", "Subscriptions can be refunded within 30 days."),
    Document("security", "Security", "SAML single sign-on is available for enterprise users."),
    Document("limits", "API limits", "The public API allows 600 requests per minute."),
]


class RetrieverTests(unittest.TestCase):
    def test_tokenizer_normalises_simple_suffixes(self):
        self.assertEqual(tokenize("refunds refunded"), ["refund", "refund"])

    def test_bm25_ranks_relevant_document_first(self):
        result = BM25Retriever(DOCUMENTS).search("How many API requests per minute?", top_k=2)
        self.assertEqual([item.document.id for item in result], ["limits"])
        self.assertGreater(result[0].score, 0)

    def test_bm25_excludes_zero_score_and_empty_queries(self):
        retriever = BM25Retriever(DOCUMENTS)
        self.assertEqual(retriever.search("xyzzy", top_k=3), [])
        self.assertEqual(retriever.search("", top_k=3), [])
        self.assertEqual(retriever.search("??? ...", top_k=3), [])
        ranked = retriever.search("API refunds", top_k=3)
        self.assertEqual({item.document.id for item in ranked}, {"limits", "refund"})
        self.assertGreater(ranked[0].score, ranked[1].score)
        self.assertTrue(all(item.score > 0 for item in ranked))

    def test_search_rejects_nonpositive_top_k(self):
        retriever = BM25Retriever(DOCUMENTS)
        for top_k in (0, -1, True, False):
            with self.assertRaises(ValueError):
                retriever.search("API", top_k=top_k)


if __name__ == "__main__":
    unittest.main()
