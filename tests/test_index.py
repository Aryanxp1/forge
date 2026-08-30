"""Tests for the FORGE in-memory derived inverted index."""

import os
import tempfile
import unittest

from forge.index import InvertedIndex
from forge.storage import Storage


class IndexTestCase(unittest.TestCase):
    def setUp(self):
        self.index = InvertedIndex()


class TestEmptyIndex(IndexTestCase):
    """Initial state of a freshly built index."""

    def test_initial_counts(self):
        self.assertEqual(self.index.term_count(), 0)
        self.assertEqual(self.index.document_count(), 0)

    def test_initial_lookups(self):
        self.assertFalse(self.index.has_term('python'))
        self.assertEqual(self.index.term_documents('python'), frozenset())
        self.assertEqual(self.index.document_frequency('python'), 0)
        self.assertEqual(self.index.token_frequency(1, 'python'), 0)
        self.assertEqual(self.index.documents(), frozenset())
        self.assertEqual(list(self.index.terms()), [])


class TestAddDocument(IndexTestCase):
    """Adding documents and querying the postings."""

    def test_add_one_document(self):
        self.index.add_document(1, 'python storage')
        self.assertEqual(self.index.document_count(), 1)
        self.assertTrue(self.index.has_term('python'))
        self.assertTrue(self.index.has_term('storage'))
        self.assertEqual(self.index.term_documents('python'), frozenset({1}))

    def test_add_multiple_documents(self):
        self.index.add_document(1, 'python storage')
        self.index.add_document(2, 'search index')
        self.assertEqual(self.index.document_count(), 2)
        self.assertEqual(self.index.term_documents('search'), frozenset({2}))
        self.assertEqual(self.index.term_documents('index'), frozenset({2}))

    def test_same_term_in_multiple_documents(self):
        self.index.add_document(1, 'python storage')
        self.index.add_document(2, 'python search')
        self.index.add_document(3, 'storage search')
        self.assertEqual(self.index.term_documents('python'), frozenset({1, 2}))
        self.assertEqual(self.index.term_documents('storage'), frozenset({1, 3}))
        self.assertEqual(self.index.term_documents('search'), frozenset({2, 3}))
        self.assertEqual(self.index.document_frequency('python'), 2)

    def test_same_term_repeated_in_one_document(self):
        """Repeated term in one doc -> ONE document ID posting."""
        self.index.add_document(1, 'python python python')
        self.assertEqual(self.index.term_documents('python'), frozenset({1}))
        self.assertEqual(self.index.term_count(), 1)

    def test_unknown_term(self):
        self.index.add_document(1, 'python')
        self.assertEqual(self.index.term_documents('nonexistent'), frozenset())
        self.assertFalse(self.index.has_term('nonexistent'))
        self.assertEqual(self.index.document_frequency('nonexistent'), 0)

    def test_multiple_terms(self):
        self.index.add_document(1, 'alpha beta gamma')
        self.assertEqual(self.index.term_count(), 3)
        self.assertEqual(sorted(self.index.terms()), ['alpha', 'beta', 'gamma'])

    def test_document_ids(self):
        self.index.add_document(42, 'content one')
        self.index.add_document(7, 'content two')
        self.assertEqual(self.index.documents(), frozenset({42, 7}))

    def test_stopwords_are_not_indexed(self):
        self.index.add_document(1, 'the quick and the lazy')
        self.assertFalse(self.index.has_term('the'))
        self.assertFalse(self.index.has_term('and'))
        self.assertTrue(self.index.has_term('quick'))
        self.assertTrue(self.index.has_term('lazy'))

    def test_token_frequency_within_document(self):
        self.index.add_document(1, 'python python storage')
        self.assertEqual(self.index.token_frequency(1, 'python'), 2)
        self.assertEqual(self.index.token_frequency(1, 'storage'), 1)
        self.assertEqual(self.index.token_frequency(2, 'python'), 0)

    def test_document_frequency_counts_documents_not_occurrences(self):
        self.index.add_document(1, 'python python')
        self.index.add_document(2, 'python')
        self.assertEqual(self.index.document_frequency('python'), 2)

    def test_add_tokens_primitive(self):
        self.index.add_tokens(1, ['python', 'python', 'storage'])
        self.assertEqual(self.index.term_documents('python'), frozenset({1}))
        self.assertEqual(self.index.token_frequency(1, 'python'), 2)
        self.assertEqual(self.index.token_frequency(1, 'storage'), 1)

    def test_reindexing_same_doc_replaces_postings(self):
        self.index.add_document(1, 'python storage')
        self.index.add_document(1, 'search index')
        self.assertEqual(self.index.document_count(), 1)
        self.assertEqual(self.index.term_documents('python'), frozenset())
        self.assertEqual(self.index.term_documents('search'), frozenset({1}))
        self.assertEqual(self.index.term_count(), 2)


class TestIndexStatistics(IndexTestCase):
    """Index statistics used by future ranking."""

    def test_statistics(self):
        self.index.add_document(1, 'alpha beta')
        self.index.add_document(2, 'beta gamma')
        self.index.add_document(3, 'gamma alpha delta')
        self.assertEqual(self.index.document_count(), 3)
        self.assertEqual(self.index.term_count(), 4)
        self.assertEqual(self.index.document_frequency('alpha'), 2)
        self.assertEqual(self.index.document_frequency('beta'), 2)
        self.assertEqual(self.index.document_frequency('gamma'), 2)
        self.assertEqual(self.index.document_frequency('delta'), 1)
        self.assertEqual(self.index.token_frequency(3, 'gamma'), 1)
        self.assertEqual(self.index.token_frequency(3, 'delta'), 1)
class TestIndexDeterminism(unittest.TestCase):
    """Building the same index twice must produce identical state."""

    def _build(self, docs):
        index = InvertedIndex()
        for doc_id, text in sorted(docs.items()):
            index.add_document(doc_id, text)
        return index

    def test_deterministic_construction(self):
        docs = {
            1: 'python storage search',
            2: 'python index',
            3: 'storage search index',
        }
        first = self._build(docs)
        second = self._build(docs)
        self.assertEqual(first.term_count(), second.term_count())
        self.assertEqual(first.document_count(), second.document_count())
        self.assertEqual(sorted(first.terms()), sorted(second.terms()))
        for term in first.terms():
            self.assertEqual(first.term_documents(term), second.term_documents(term))


class TestIndexRebuildFromStorage(unittest.TestCase):
    """The index is DERIVED data; it must rebuild cleanly from storage."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.store_path = os.path.join(self.tempdir.name, 'store.bin')

    def _docs(self):
        return {
            1: 'python is a great language',
            2: 'storage and search engines',
            3: 'python search engine storage',
        }

    def _seed_storage(self):
        with Storage(self.store_path) as s:
            for doc_id, text in sorted(self._docs().items()):
                s.append(doc_id, text.encode('utf-8'))

    def _build_from_storage(self):
        index = InvertedIndex()
        with Storage(self.store_path) as s:
            for doc_id, payload in s.iter_records():
                index.add_document(doc_id, payload.decode('utf-8'))
        return index

    def test_rebuild_from_storage(self):
        self._seed_storage()
        index = self._build_from_storage()
        self.assertEqual(index.document_count(), 3)
        self.assertEqual(index.term_documents('python'), frozenset({1, 3}))
        self.assertEqual(index.term_documents('engine'), frozenset({3}))
        self.assertEqual(index.term_documents('engines'), frozenset({2}))
        self.assertFalse(index.has_term('the'))
        self.assertFalse(index.has_term('is'))
        self.assertFalse(index.has_term('and'))

    def test_rebuild_is_reproducible(self):
        self._seed_storage()
        first = self._build_from_storage()
        second = self._build_from_storage()
        self.assertEqual(first.term_count(), second.term_count())
        self.assertEqual(sorted(first.terms()), sorted(second.terms()))
        for term in first.terms():
            self.assertEqual(
                first.term_documents(term), second.term_documents(term)
            )


if __name__ == '__main__':
    unittest.main()