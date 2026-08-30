"""Tests for FORGE WAL recovery and storage <-> WAL consistency."""

import os
import struct
import tempfile
import unittest

from forge.records import InvalidDocumentIdError, encode_record
from forge.recovery import recover, validate_consistency
from forge.storage import Storage
from forge.wal import WalWriter, scan_wal


class RecoveryTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.wal = os.path.join(self.tempdir.name, 'wal.bin')
        self.store = os.path.join(self.tempdir.name, 'store.bin')

    def _storage(self):
        return Storage(self.store)


class TestRecoveryReplay(RecoveryTestCase):
    """Tests for replaying WAL records into storage."""

    def test_replay_into_empty_storage(self):
        with WalWriter(self.wal) as w:
            for i in range(3):
                w.append(i, f'doc {i}'.encode())
        with self._storage() as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.completed)
            self.assertEqual(report.records_examined, 3)
            self.assertEqual(report.records_recovered, 3)
            self.assertEqual(report.records_skipped, 0)
            self.assertEqual(len(storage), 3)
            self.assertEqual(storage.get(2), b'doc 2')

    def test_replay_when_storage_already_contains_record(self):
        """Storage may already hold the doc (written before a crash)."""
        with WalWriter(self.wal) as w:
            w.append(1, b'first')
        with self._storage() as storage:
            storage.append(1, b'first')
            report = recover(self.wal, storage)
            self.assertEqual(report.records_recovered, 0)
            self.assertEqual(report.records_skipped, 1)
            self.assertEqual(len(storage), 1)
            self.assertEqual(report.records_examined, 1)

    def test_no_duplicate_when_wal_has_duplicate_doc_ids(self):
        with WalWriter(self.wal) as w:
            w.append(1, b'v1')
            w.append(1, b'v1')  # duplicate doc ID in WAL
        with self._storage() as storage:
            report = recover(self.wal, storage)
            self.assertEqual(report.records_examined, 2)
            self.assertEqual(report.records_recovered, 1)
            self.assertEqual(report.records_skipped, 1)
            self.assertEqual(len(storage), 1)
            self.assertEqual(storage.get(1), b'v1')

    def test_recovery_is_idempotent(self):
        """Running recovery twice never duplicates documents."""
        with WalWriter(self.wal) as w:
            w.append(1, b'doc')
        with self._storage() as storage:
            first = recover(self.wal, storage)
            second = recover(self.wal, storage)
            self.assertTrue(first.completed)
            self.assertTrue(second.completed)
            self.assertEqual(second.records_recovered, 0)
            self.assertEqual(second.records_skipped, 1)
            self.assertEqual(len(storage), 1)

    def test_invalid_doc_id_propagates_as_validation_error(self):
        """Invalid doc IDs are rejected by encode_record, not swallowed."""
        with self.assertRaises(InvalidDocumentIdError):
            with self._storage() as storage:
                storage.append(-1, b'bad')
class TestRecoveryTailDetection(RecoveryTestCase):
    """Recovery must stop at incomplete/corrupt tails and truncate them."""

    def test_truncated_tail_detected_and_truncated(self):
        with WalWriter(self.wal) as w:
            w.append(1, b'good')
        partial = encode_record(2, b'partial')[:13]
        with open(self.wal, 'ab') as f:
            f.write(partial)
        with self._storage() as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.incomplete_tail_detected)
            self.assertFalse(report.corruption_detected)
            self.assertFalse(report.completed)
            self.assertTrue(report.tail_truncated)
            self.assertGreater(report.truncated_bytes, 0)
            self.assertEqual(storage.get(1), b'good')
            self.assertFalse(storage.has_doc(2))
        # the WAL is clean again after recovery
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'ok')
        self.assertEqual([d for d, _p in scan.records], [1])

    def test_corrupt_wal_checksum_detected(self):
        with WalWriter(self.wal) as w:
            w.append(1, b'good')
            w.append(2, b'to be corrupted')
        with open(self.wal, 'rb') as fh:
            data = bytearray(fh.read())
        data[-1] ^= 0xFF  # corrupt the last payload byte
        with open(self.wal, 'wb') as f:
            f.write(bytes(data))
        with self._storage() as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.corruption_detected)
            self.assertFalse(report.incomplete_tail_detected)
            self.assertFalse(report.completed)
            self.assertEqual(storage.get(1), b'good')
            self.assertFalse(storage.has_doc(2))

    def test_invalid_magic_detected(self):
        with WalWriter(self.wal) as w:
            w.append(1, b'good')
        # >= 18 bytes of garbage gives a complete-looking header with a
        # bad MAGIC, so this is corruption (not a truncated tail).
        with open(self.wal, 'ab') as f:
            f.write(b'THIS IS NOT A FORGE RECORD')
        with self._storage() as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.corruption_detected)
            self.assertFalse(report.completed)
            self.assertEqual(storage.get(1), b'good')
            self.assertEqual(report.records_examined, 1)

    def test_invalid_length_truncated(self):
        record = bytearray(encode_record(1, b'hello'))
        record[2:6] = struct.pack('>I', 0x7FFFFFFF)
        with open(self.wal, 'wb') as f:
            f.write(bytes(record))
        with self._storage() as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.incomplete_tail_detected)
            self.assertEqual(report.records_examined, 0)
            self.assertEqual(len(storage), 0)
        self.assertEqual(os.path.getsize(self.wal), 0)

    def test_corruption_stops_recovery_no_forward_resync(self):
        """Records after a corrupt one are NOT recovered (no resync)."""
        with WalWriter(self.wal) as w:
            w.append(1, b'good')
            w.append(2, b'corrupt this')
            w.append(3, b'after the corruption')
        with open(self.wal, 'rb') as fh:
            data = bytearray(fh.read())
        # flip a byte inside record 2's payload (recompute its range)
        first = len(encode_record(1, b'good'))
        second = encode_record(2, b'corrupt this')
        data[first + len(second) - 1] ^= 0xFF
        with open(self.wal, 'wb') as f:
            f.write(bytes(data))
        with self._storage() as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.corruption_detected)
            self.assertEqual(len(storage), 1)
            self.assertEqual(list(storage.doc_ids), [1])


class TestRecoveryEndToEndAndConsistency(RecoveryTestCase):
    """Full-flow and storage <-> WAL consistency tests."""

    def test_end_to_end_commit_survives_simulated_crash(self):
        """write -> WAL fsync (COMMITTED) -> crash before storage write."""
        with WalWriter(self.wal) as w:
            w.append(7, b'committed before crash')
        with self._storage() as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.completed)
            self.assertEqual(report.records_recovered, 1)
            self.assertEqual(storage.get(7), b'committed before crash')

    def test_end_to_end_full_flow(self):
        """add -> WAL fsync -> storage append -> recovery keeps one copy."""
        with WalWriter(self.wal) as w:
            w.append(7, b'full flow')
        with self._storage() as storage:
            storage.append(7, b'full flow')  # normal post-commit apply
            report = recover(self.wal, storage)
            self.assertTrue(report.completed)
            self.assertEqual(report.records_skipped, 1)
            self.assertEqual(len(storage), 1)
            self.assertTrue(validate_consistency(self.wal, storage).ok)

    def test_consistency_validates_after_recovery(self):
        with WalWriter(self.wal) as w:
            for i in range(4):
                w.append(i, f'doc {i}'.encode())
        with self._storage() as storage:
            recover(self.wal, storage)
            report = validate_consistency(self.wal, storage)
            self.assertEqual(report.wal_doc_count, 4)
            self.assertEqual(report.storage_doc_count, 4)
            self.assertEqual(report.missing_doc_ids, [])
            self.assertTrue(report.ok)

    def test_consistency_flags_missing_doc(self):
        with WalWriter(self.wal) as w:
            for i in range(3):
                w.append(i, f'doc {i}'.encode())
        with self._storage() as storage:
            storage.append(0, b'doc 0')  # only one doc recovered so far
            report = validate_consistency(self.wal, storage)
            self.assertFalse(report.ok)
            self.assertEqual(report.missing_doc_ids, [1, 2])

    def test_recovery_report_is_structured(self):
        with WalWriter(self.wal) as w:
            w.append(1, b'x')
        with self._storage() as storage:
            report = recover(self.wal, storage)
            text = str(report)
            self.assertIn('recovered=1', text)
            self.assertIn('completed=True', text)


if __name__ == '__main__':
    unittest.main()