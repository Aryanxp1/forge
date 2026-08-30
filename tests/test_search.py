"""Tests for AND/OR query evaluation (forge.search).

All tests are deterministic and use in-memory indexes built from fixed
document sets. No filesystem or subprocess is involved.
"""

import unittest

from forge.index import InvertedIndex
from forge.search import MODE_AND, MODE_OR, search, search_and, search_or


def build_index(docs):
    """Build an index from an iterable of (doc_id, text) pairs."""
    index = InvertedIndex()
    for doc_id, text in docs:
        index.add_document(doc_id, text)
    return index


# Fixed corpus mirroring the architecture example:
#   python  -> {1, 4, 9}
#   storage -> {2, 4}
#   search  -> {1, 4, 7}
SPEC_DOCS = [
    (1, "python search"),
    (2, "storage basics"),
    (4, "python storage search"),
    (7, "search engine"),
    (9, "python language"),
]


class SearchAndTests(unittest.TestCase):
    def setUp(self):
        self.index = build_index(SPEC_DOCS)

    def test_single_term(self):
        self.assertEqual(search_and(self.index, ["python"]), [1, 4, 9])

    def test_two_terms_intersection(self):
        self.assertEqual(search_and(self.index, ["python", "search"]), [1, 4])

    def test_three_terms_narrowest_result(self):
        self.assertEqual(
            search_and(self.index, ["python", "storage", "search"]), [4]
        )

    def test_unknown_term_yields_no_results(self):
        self.assertEqual(search_and(self.index, ["python", "missing"]), [])

    def test_unknown_term_first_yields_no_results(self):
        self.assertEqual(search_and(self.index, ["missing", "python"]), [])

    def test_all_terms_unknown(self):
        self.assertEqual(search_and(self.index, ["missing", "gone"]), [])

    def test_empty_term_list(self):
        # Documented V1 semantics: no terms -> no results.
        self.assertEqual(search_and(self.index, []), [])

    def test_duplicate_terms_are_harmless(self):
        self.assertEqual(
            search_and(self.index, ["python", "python"]), [1, 4, 9]
        )

    def test_result_is_subset_of_every_posting(self):
        result = search_and(self.index, ["python", "search"])
        for term in ("python", "search"):
            self.assertTrue(set(result) <= self.index.term_documents(term))


class SearchOrTests(unittest.TestCase):
    def setUp(self):
        self.index = build_index(SPEC_DOCS)

    def test_single_term(self):
        self.assertEqual(search_or(self.index, ["storage"]), [2, 4])

    def test_union_sorted_without_duplicates(self):
        self.assertEqual(
            search_or(self.index, ["python", "storage"]), [1, 2, 4, 9]
        )

    def test_unknown_terms_contribute_nothing(self):
        self.assertEqual(
            search_or(self.index, ["missing", "search"]), [1, 4, 7]
        )

    def test_all_terms_unknown(self):
        self.assertEqual(search_or(self.index, ["missing", "gone"]), [])

    def test_empty_term_list(self):
        self.assertEqual(search_or(self.index, []), [])

    def test_duplicate_terms_are_harmless(self):
        self.assertEqual(
            search_or(self.index, ["python", "python"]), [1, 4, 9]
        )

    def test_result_is_superset_of_posting_union(self):
        result = search_or(self.index, ["python", "storage"])
        expected = (
            self.index.term_documents("python")
            | self.index.term_documents("storage")
        )
        self.assertTrue(set(result) >= expected)


class DeterminismTests(unittest.TestCase):
    def setUp(self):
        self.index = build_index(SPEC_DOCS)

    def test_repeated_calls_identical(self):
        for _ in range(25):
            self.assertEqual(
                search_and(self.index, ["python", "search"]), [1, 4]
            )
            self.assertEqual(
                search_or(self.index, ["python", "storage"]), [1, 2, 4, 9]
            )

    def test_results_sorted_and_unique(self):
        terms = ["python", "storage", "search", "missing"]
        for term in terms:
            for result in (
                search_and(self.index, [term]),
                search_or(self.index, [term]),
            ):
                self.assertEqual(result, sorted(result))
                self.assertEqual(len(set(result)), len(result))

    def test_numeric_doc_id_ordering(self):
        index = build_index(
            [
                (300, "alpha beta"),
                (5, "alpha gamma"),
                (40, "alpha delta"),
            ]
        )
        self.assertEqual(search_and(index, ["alpha"]), [5, 40, 300])
        self.assertEqual(
            search_or(index, ["beta", "gamma", "delta"]), [5, 40, 300]
        )

    def test_independent_index_builds_match(self):
        first = build_index(SPEC_DOCS)
        second = build_index(SPEC_DOCS)
        self.assertEqual(
            search_and(first, ["python", "storage"]),
            search_and(second, ["python", "storage"]),
        )
        self.assertEqual(
            search_or(first, ["python", "search"]),
            search_or(second, ["python", "search"]),
        )


class SearchTextTests(unittest.TestCase):
    """The high-level search() entry point: raw text -> tokens -> query."""

    def setUp(self):
        self.index = build_index(SPEC_DOCS)

    def test_and_mode_is_default(self):
        self.assertEqual(search(self.index, "python storage"), [4])

    def test_and_mode_explicit(self):
        self.assertEqual(search(self.index, "python search", MODE_AND), [1, 4])

    def test_or_mode(self):
        self.assertEqual(
            search(self.index, "python storage", MODE_OR), [1, 2, 4, 9]
        )

    def test_query_normalization(self):
        self.assertEqual(search(self.index, "Python, STORAGE & Search!"), [4])

    def test_uppercase_query(self):
        self.assertEqual(search(self.index, "PYTHON"), [1, 4, 9])

    def test_stopwords_removed_from_query(self):
        # "the" is a stopword; only "python" is searched.
        self.assertEqual(search(self.index, "the python"), [1, 4, 9])

    def test_stopword_only_query(self):
        self.assertEqual(search(self.index, "the of and"), [])

    def test_empty_query(self):
        self.assertEqual(search(self.index, ""), [])

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            search(self.index, "python", mode="fuzzy")


class TermContractTests(unittest.TestCase):
    """search_and/search_or expect normalized terms (index keys)."""

    def test_unnormalized_term_does_not_match(self):
        index = build_index(SPEC_DOCS)
        # "Python" (uppercase) is not an index key; callers must pass
        # tokenizer output or use search(), which normalizes.
        self.assertEqual(search_and(index, ["Python"]), [])
        self.assertEqual(search_or(index, ["Python"]), [])


if __name__ == "__main__":
    unittest.main()