"""Tests for append-only FORGE document storage."""

import os
import tempfile
import unittest

from forge.records import InvalidDocumentIdError, encode_record
from forge.storage import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    Storage,
)


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = os.path.join(self.tempdir.name, 'docs.bin')


class TestStorageAppend(StorageTestCase):
    """Tests for append / get / scan."""

    def test_append_get_roundtrip(self):
        with Storage(self.path) as s:
            s.append(1, b'one')
            self.assertEqual(s.get(1), b'one')

    def test_unicode_payload(self):
        text = 'héllo wörld — ünïcode ✓'
        data = text.encode('utf-8')
        with Storage(self.path) as s:
            s.append(5, data)
        with Storage(self.path) as s:
            self.assertEqual(s.get(5), data)

    def test_empty_payload(self):
        with Storage(self.path) as s:
            s.append(3, b'')
            self.assertEqual(s.get(3), b'')

    def test_get_missing_raises(self):
        with Storage(self.path) as s:
            with self.assertRaises(DocumentNotFoundError):
                s.get(999)

    def test_doc_ids(self):
        with Storage(self.path) as s:
            for i in range(4):
                s.append(i, str(i).encode())
            self.assertEqual(s.doc_ids, frozenset({0, 1, 2, 3}))
            self.assertEqual(len(s), 4)
            self.assertTrue(s.has_doc(2))
            self.assertFalse(s.has_doc(99))

    def test_sequential_scan_order(self):
        with Storage(self.path) as s:
            for i in range(5):
                s.append(i, f'content {i}'.encode())
            records = list(s.iter_records())
        self.assertEqual([d for d, _p in records], [0, 1, 2, 3, 4])
        self.assertEqual(records[0], (0, b'content 0'))
        self.assertEqual(records[4], (4, b'content 4'))

    def test_duplicate_append_raises(self):
        with Storage(self.path) as s:
            s.append(1, b'first')
            with self.assertRaises(DuplicateDocumentError):
                s.append(1, b'second')

    def test_invalid_doc_id_raises(self):
        with Storage(self.path) as s:
            with self.assertRaises(InvalidDocumentIdError):
                s.append(-1, b'bad')
            with self.assertRaises(InvalidDocumentIdError):
                s.append(2 ** 64, b'bad')

    def test_storage_bytes_match_record_format(self):
        with Storage(self.path) as s:
            s.append(7, b'payload')
        with open(self.path, 'rb') as f:
            raw = f.read()
        self.assertEqual(raw, encode_record(7, b'payload'))

    def test_new_storage_is_empty(self):
        with Storage(self.path) as s:
            self.assertEqual(len(s), 0)
            self.assertEqual(s.doc_ids, frozenset())


class TestStoragePersistenceAndHealing(StorageTestCase):
    """Tests for persistence across opens and torn-tail healing."""

    def test_reopen_preserves_records(self):
        with Storage(self.path) as s:
            s.append(1, b'persist')
            s.append(2, b'also persist')
        with Storage(self.path) as s:
            self.assertEqual(len(s), 2)
            self.assertEqual(s.get(1), b'persist')
            self.assertEqual(s.get(2), b'also persist')

    def test_torn_tail_healed_on_open(self):
        """A crashed append leaves a torn tail; open must heal it."""
        with Storage(self.path) as s:
            s.append(1, b'first')
        torn = encode_record(2, b'second')[:10]  # partial record bytes
        with open(self.path, 'ab') as f:
            f.write(torn)
        with Storage(self.path) as s:
            self.assertEqual(len(s), 1)
            self.assertEqual(s.get(1), b'first')
        # healing physically removed the torn tail
        self.assertEqual(os.path.getsize(self.path), len(encode_record(1, b'first')))

    def test_get_recovers_appended_without_reopen(self):
        with Storage(self.path) as s:
            s.append(10, b'fresh')
            self.assertEqual(s.get(10), b'fresh')


if __name__ == '__main__':
    unittest.main()