"""Tests for index rebuild and storage <-> index consistency (Phase 5)."""

import os
import tempfile
import unittest

from forge.consistency import rebuild_index, validate_consistency
from forge.index import InvertedIndex
from forge.search import MODE_AND, MODE_OR, search
from forge.storage import Storage

BASE_DOCS = [
    (1, b"python search"),
    (2, b"storage basics"),
    (4, b"python storage search"),
]


class _StorageBase(unittest.TestCase):
    """Shared setup: an append-only Storage in a temp directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "data.bin")
        self.storage = Storage(self.path)

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def _reopen(self, docs=None):
        """Persist nothing-or-some, then reopen storage from disk.

        Simulates "close -> restart -> reopen": the reopened object has
        no in-memory state, forcing a reload from the on-disk file.
        """
        self.storage.close()
        self.storage = Storage(self.path)
        if docs:
            for doc_id, payload in docs:
                self.storage.append(doc_id, payload)
        self.storage.close()
        self.storage = Storage(self.path)


class RebuildTestCase(_StorageBase):
    def test_empty_storage_rebuild(self):
        index = rebuild_index(self.storage)
        self.assertEqual(index.document_count(), 0)
        self.assertEqual(index.term_count(), 0)
        self.assertEqual(search(index, "python search"), [])
        self.assertTrue(validate_consistency(self.storage, index).ok)

    def test_single_document_rebuild(self):
        self._reopen([(1, b"python")])
        index = rebuild_index(self.storage)
        self.assertEqual(index.document_count(), 1)
        self.assertEqual(search(index, "python"), [1])

    def test_multiple_document_rebuild(self):
        self._reopen(BASE_DOCS)
        index = rebuild_index(self.storage)
        self.assertEqual(index.document_count(), 3)
        self.assertEqual(search(index, "python search", MODE_AND), [1, 4])
        self.assertEqual(search(index, "python storage", MODE_OR), [1, 2, 4])

    def test_unicode_document_rebuild(self):
        self._reopen([(1, "pythön language".encode("utf-8"))])
        index = rebuild_index(self.storage)
        self.assertEqual(index.term_documents("pythön"), {1})
        self.assertEqual(index.term_documents("language"), {1})

    def test_repeated_terms_no_duplicate_doc_id(self):
        self._reopen([(1, b"python python python")])
        index = rebuild_index(self.storage)
        # set semantics in postings; frequency tracked separately
        self.assertEqual(index.term_documents("python"), {1})
        self.assertEqual(index.token_frequency(1, "python"), 3)

    def test_documents_share_terms(self):
        self._reopen(BASE_DOCS)
        index = rebuild_index(self.storage)
        self.assertEqual(index.term_documents("python"), {1, 4})
        self.assertEqual(index.term_documents("search"), {1, 4})
        self.assertEqual(index.term_documents("storage"), {2, 4})

    def test_search_after_rebuild_matches(self):
        # original index -> search -> destroy -> rebuild from storage -> search
        self._reopen(BASE_DOCS)
        original = rebuild_index(self.storage)
        before = search(original, "python search")
        self.assertEqual(before, [1, 4])
        del original  # destroy the in-memory index

        rebuilt = rebuild_index(self.storage)
        after = search(rebuilt, "python search")
        self.assertEqual(after, [1, 4])
        self.assertEqual(before, after)
        self.assertTrue(validate_consistency(self.storage, rebuilt).ok)

    def test_rebuild_after_close_reopen(self):
        # persist in one handle, reopen from disk, rebuild
        self._reopen(BASE_DOCS)
        reopened = Storage(self.path)
        index = rebuild_index(reopened)
        self.assertEqual(search(index, "python search"), [1, 4])
        self.assertTrue(validate_consistency(reopened, index).ok)
        reopened.close()

    def test_rebuild_twice_produces_equivalent_indexes(self):
        self._reopen(BASE_DOCS)
        first = rebuild_index(self.storage)
        second = rebuild_index(self.storage)

        self.assertEqual(first.document_count(), second.document_count())
        self.assertEqual(first.term_count(), second.term_count())
        for term in set(first.terms()):
            self.assertEqual(
                set(first.term_documents(term)),
                set(second.term_documents(term)),
            )
        self.assertEqual(
            first.token_frequency(1, "python"),
            second.token_frequency(1, "python"),
        )
        self.assertTrue(validate_consistency(self.storage, first).ok)
        self.assertTrue(validate_consistency(self.storage, second).ok)

    def test_consistent_index_passes_validation(self):
        self._reopen(BASE_DOCS)
        index = rebuild_index(self.storage)
        r = validate_consistency(self.storage, index)
        self.assertTrue(r.ok)
        self.assertEqual(r.missing_docs, [])
        self.assertEqual(r.extra_docs, [])
        self.assertEqual(r.missing_postings, {})
        self.assertEqual(r.extra_postings, {})
        self.assertEqual(r.term_frequency_mismatches, [])
        self.assertEqual(r.extra_terms, [])


class ConsistencyDetectionTests(_StorageBase):
    """The validator must flag every category of index/storage drift."""

    def _correct_index(self):
        """Build the canonical (correct) index from BASE_DOCS storage."""
        self._reopen(BASE_DOCS)
        return rebuild_index(self.storage)

    def test_missing_document_detected(self):
        index = self._correct_index()
        # rebuild a WRONG index that omits doc 4
        wrong = InvertedIndex()
        wrong.add_document(1, "python search")
        wrong.add_document(2, "storage basics")
        r = validate_consistency(self.storage, wrong)
        self.assertIn(4, r.missing_docs)
        self.assertEqual(r.storage_doc_count, 3)
        self.assertEqual(r.index_doc_count, 2)
        self.assertFalse(r.ok)

    def test_extra_document_detected(self):
        index = self._correct_index()
        index.add_document(9, "python newterm")
        r = validate_consistency(self.storage, index)
        self.assertIn(9, r.extra_docs)
        self.assertIn("python", r.extra_postings)
        self.assertIn("newterm", r.extra_terms)
        self.assertFalse(r.ok)

    def test_missing_posting_detected(self):
        self._reopen(BASE_DOCS)
        # doc 4 indexed WITHOUT "search" -> posting for "search" is too small
        wrong = InvertedIndex()
        wrong.add_document(1, "python search")
        wrong.add_document(2, "storage basics")
        wrong.add_document(4, "python storage")
        r = validate_consistency(self.storage, wrong)
        self.assertEqual(r.missing_postings["search"], [4])
        self.assertFalse(r.ok)

    def test_extra_posting_detected(self):
        self._reopen(BASE_DOCS)
        # doc 2 indexed WITH "search" -> posting for "search" is too big
        wrong = InvertedIndex()
        wrong.add_document(1, "python search")
        wrong.add_document(2, "storage basics search")
        wrong.add_document(4, "python storage search")
        r = validate_consistency(self.storage, wrong)
        self.assertEqual(r.extra_postings["search"], [2])
        self.assertFalse(r.ok)

    def test_incorrect_posting_membership_detected(self):
        self._reopen(BASE_DOCS)
        # search posting ends up {2,4} instead of {1,4}: doc 1 missing,
        # doc 2 wrongly added -> both a missing and an extra posting member.
        wrong = InvertedIndex()
        wrong.add_document(1, "python")
        wrong.add_document(2, "storage basics search")
        wrong.add_document(4, "python storage search")
        r = validate_consistency(self.storage, wrong)
        self.assertEqual(r.missing_postings["search"], [1])
        self.assertEqual(r.extra_postings["search"], [2])
        self.assertFalse(r.ok)

    def test_document_count_mismatch_detected(self):
        index = self._correct_index()
        index.add_document(9, "python newterm")
        r = validate_consistency(self.storage, index)
        self.assertNotEqual(r.index_doc_count, r.storage_doc_count)
        self.assertFalse(r.ok)

    def test_term_frequency_mismatch_detected(self):
        docs = [(1, b"python python search"), (2, b"storage basics"),
                (4, b"python storage search")]
        self._reopen(docs)
        # correct index expects python freq 2 in doc 1; this one has freq 1.
        wrong = InvertedIndex()
        wrong.add_document(1, "python search")
        wrong.add_document(2, "storage basics")
        wrong.add_document(4, "python storage search")
        r = validate_consistency(self.storage, wrong)
        self.assertEqual(r.term_frequency_mismatches, [(1, "python", 2, 1)])
        # posting for python is still correct -> no posting drift reported
        self.assertEqual(r.missing_postings, {})
        self.assertEqual(r.extra_postings, {})
        self.assertFalse(r.ok)

    def test_correct_index_has_empty_report(self):
        index = self._correct_index()
        r = validate_consistency(self.storage, index)
        self.assertTrue(r.ok)
        self.assertEqual(r.missing_docs, [])
        self.assertEqual(r.extra_docs, [])
        self.assertEqual(r.missing_postings, {})
        self.assertEqual(r.extra_postings, {})
        self.assertEqual(r.term_frequency_mismatches, [])
        self.assertEqual(r.extra_terms, [])


if __name__ == "__main__":
    unittest.main()