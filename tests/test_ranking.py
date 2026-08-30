"""Tests for deterministic TF-IDF ranking (forge.ranking)."""

import math
import unittest

from forge.index import InvertedIndex
from forge.ranking import (
    document_frequency,
    inverse_document_frequency,
    rank_documents,
    score_document,
    search_ranked,
    term_frequency,
)


def _build_index(docs):
    """Build an index from an iterable of (doc_id, text) pairs."""
    index = InvertedIndex()
    for doc_id, text in docs:
        index.add_document(doc_id, text)
    return index


# Fixed corpus for ranking tests:
#   doc 1: "python search"
#   doc 2: "storage basics"
#   doc 4: "python storage search"
#   doc 7: "search engine"
#   doc 9: "python language"
RANK_DOCS = [
    (1, "python search"),
    (2, "storage basics"),
    (4, "python storage search"),
    (7, "search engine"),
    (9, "python language"),
]


class TestTermFrequency(unittest.TestCase):
    def test_raw_count(self):
        index = _build_index([(1, "python python search")])
        self.assertEqual(term_frequency(index, 1, "python"), 2)
        self.assertEqual(term_frequency(index, 1, "search"), 1)

    def test_absent_term(self):
        index = _build_index([(1, "python")])
        self.assertEqual(term_frequency(index, 1, "missing"), 0)

    def test_absent_document(self):
        index = _build_index([(1, "python")])
        self.assertEqual(term_frequency(index, 99, "python"), 0)


class TestDocumentFrequency(unittest.TestCase):
    def test_shared_term(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(document_frequency(index, "python"), 3)
        self.assertEqual(document_frequency(index, "search"), 3)

    def test_unique_term(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(document_frequency(index, "engine"), 1)

    def test_unknown_term(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(document_frequency(index, "missing"), 0)


class TestInverseDocumentFrequency(unittest.TestCase):
    def test_common_vs_rare(self):
        index = _build_index(RANK_DOCS)
        idf_python = inverse_document_frequency(index, "python")
        idf_engine = inverse_document_frequency(index, "engine")
        self.assertAlmostEqual(idf_python, math.log(5 / 3))
        self.assertAlmostEqual(idf_engine, math.log(5 / 1))
        self.assertGreater(idf_engine, idf_python)

    def test_unknown_term_returns_zero(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(inverse_document_frequency(index, "missing"), 0.0)

    def test_empty_index_returns_zero(self):
        index = InvertedIndex()
        self.assertEqual(inverse_document_frequency(index, "anything"), 0.0)

    def test_empty_index_returns_zero(self):
        index = InvertedIndex()
        self.assertEqual(inverse_document_frequency(index, "anything"), 0.0)


class TestScoreDocument(unittest.TestCase):
    def test_single_term(self):
        index = _build_index(RANK_DOCS)
        expected = 1 * math.log(5 / 3)
        self.assertAlmostEqual(score_document(index, 1, ["python"]), expected)

    def test_multi_term_sum(self):
        index = _build_index(RANK_DOCS)
        expected = 1 * math.log(5 / 3) + 1 * math.log(5 / 2) + 1 * math.log(5 / 3)
        self.assertAlmostEqual(
            score_document(index, 4, ["python", "storage", "search"]), expected
        )

    def test_repeated_query_term_does_not_multiply(self):
        index = _build_index([(1, "python python search")])
        single = score_document(index, 1, ["python"])
        repeated = score_document(index, 1, ["python", "python", "python"])
        self.assertAlmostEqual(single, repeated)

    def test_unknown_term_contributes_nothing(self):
        index = _build_index([(1, "python")])
        self.assertAlmostEqual(score_document(index, 1, ["missing"]), 0.0)


class TestRankDocuments(unittest.TestCase):
    def test_empty_candidates(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(rank_documents(index, [], ["python"]), [])

    def test_empty_terms(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(rank_documents(index, [1, 4, 9], []), [])

    def test_higher_score_first(self):
        index = _build_index(RANK_DOCS)
        # doc 4 has all three terms (highest score); doc 1 has two; doc 9 has one
        result = rank_documents(index, [1, 4, 9], ["python", "storage", "search"])
        self.assertEqual(result[0], 4)
        self.assertEqual(result, [4, 1, 9])

    def test_tie_break_by_doc_id(self):
        index = _build_index([(5, "python search"), (2, "python search")])
        result = rank_documents(index, [5, 2], ["python", "search"])
        self.assertEqual(result, [2, 5])


class TestSearchRanked(unittest.TestCase):
    def test_and_ranking(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(search_ranked(index, "python search", "and"), [1, 4])

    def test_or_ranking(self):
        index = _build_index(RANK_DOCS)
        # "storage engine" OR -> docs 2, 4 (storage) and 7 (engine).
        # engine is rarer (df=1) than storage (df=2), so doc 7 ranks first.
        result = search_ranked(index, "storage engine", "or")
        self.assertEqual(result[0], 7)  # rarest term -> highest IDF -> top
        self.assertEqual(result, [7, 2, 4])

    def test_unknown_term(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(search_ranked(index, "missing", "and"), [])

    def test_stopword_only_query(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(search_ranked(index, "the of and"), [])

    def test_empty_query(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(search_ranked(index, ""), [])

    def test_case_normalization(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(
            search_ranked(index, "PYTHON SEARCH"), search_ranked(index, "python search")
        )

    def test_punctuation_normalization(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(
            search_ranked(index, "Python, Storage & Search!"),
            search_ranked(index, "python storage search"),
        )

    def test_single_document(self):
        index = _build_index([(1, "python")])
        self.assertEqual(search_ranked(index, "python"), [1])

    def test_deterministic_repeated_execution(self):
        index = _build_index(RANK_DOCS)
        first = search_ranked(index, "python storage search")
        for _ in range(25):
            self.assertEqual(search_ranked(index, "python storage search"), first)

    def test_default_mode_is_and(self):
        index = _build_index(RANK_DOCS)
        self.assertEqual(
            search_ranked(index, "python search"),
            search_ranked(index, "python search", "and"),
        )

    def test_invalid_mode_raises(self):
        index = _build_index(RANK_DOCS)
        with self.assertRaises(ValueError):
            search_ranked(index, "python", mode="fuzzy")


class TestRareTermHigherIDF(unittest.TestCase):
    def test_rare_vs_common(self):
        index = _build_index(RANK_DOCS)
        rare_score = score_document(index, 7, ["engine"])
        common_score = score_document(index, 1, ["python"])
        self.assertGreater(rare_score, common_score)


class TestExistingSearchUnchanged(unittest.TestCase):
    def test_search_returns_sorted_ids(self):
        from forge.search import search
        index = _build_index(RANK_DOCS)
        self.assertEqual(search(index, "python search"), [1, 4])
        self.assertEqual(search(index, "missing"), [])
        self.assertEqual(search(index, ""), [])


if __name__ == "__main__":
    unittest.main()
