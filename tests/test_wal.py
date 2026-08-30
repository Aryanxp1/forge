"""Tests for the FORGE Write-Ahead Log."""

import os
import struct
import tempfile
import unittest

from forge.records import MAGIC, decode_record, encode_record
from forge.wal import WalWriter, scan_wal, truncate_tail


class WalTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.wal = os.path.join(self.tempdir.name, 'wal.bin')


class TestWalWriter(WalTestCase):
    """Tests for WAL append + scan round trips."""

    def test_roundtrip_single(self):
        """Append one record and read it back."""
        with WalWriter(self.wal) as w:
            w.append(42, b'hello wal')
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'ok')
        self.assertEqual(scan.records, [(42, b'hello wal')])
        self.assertEqual(scan.good_offset, scan.total)

    def test_roundtrip_multiple(self):
        """Append several records; order and content are preserved."""
        expected = [(i, f'doc {i}'.encode()) for i in range(5)]
        with WalWriter(self.wal) as w:
            for doc_id, payload in expected:
                w.append(doc_id, payload)
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'ok')
        self.assertEqual(scan.records, expected)

    def test_empty_payload(self):
        with WalWriter(self.wal) as w:
            w.append(1, b'')
        self.assertEqual(scan_wal(self.wal).records, [(1, b'')])

    def test_unicode_payload(self):
        payload = 'ünïcode ✓ payload'.encode('utf-8')
        with WalWriter(self.wal) as w:
            w.append(1, payload)
        self.assertEqual(scan_wal(self.wal).records, [(1, payload)])

    def test_persistence_after_reopen(self):
        """A record written in one instance is visible to a fresh reader."""
        with WalWriter(self.wal) as w:
            w.append(1, b'persist me')
        scan = scan_wal(self.wal)
        self.assertEqual(scan.records, [(1, b'persist me')])

    def test_append_returns_doc_id(self):
        with WalWriter(self.wal) as w:
            result = w.append(9, b'x')
        self.assertEqual(result, 9)

    def test_wal_bytes_match_record_format(self):
        """The WAL on disk is exactly a records.py record."""
        with WalWriter(self.wal) as w:
            w.append(7, b'raw bytes')
        with open(self.wal, 'rb') as f:
            data = f.read()
        self.assertEqual(data, encode_record(7, b'raw bytes'))
        self.assertEqual(decode_record(data), (7, b'raw bytes'))
class TestWalScanTailDetection(WalTestCase):
    """Tests for incomplete tail and corruption classification."""

    def test_scan_missing_file(self):
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'ok')
        self.assertEqual(scan.records, [])
        self.assertEqual(scan.total, 0)

    def test_scan_empty_file(self):
        open(self.wal, 'wb').close()
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'ok')
        self.assertEqual(scan.records, [])

    def test_incomplete_header_tail(self):
        """Only a fragment of a header -> incomplete tail."""
        with open(self.wal, 'wb') as f:
            f.write(MAGIC)
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'incomplete_tail')
        self.assertEqual(scan.records, [])
        self.assertEqual(scan.good_offset, 0)

    def test_incomplete_payload_tail(self):
        """A record cut off before its payload finished."""
        record = encode_record(1, b'hello world')
        with open(self.wal, 'wb') as f:
            f.write(record[: len(record) - 3])
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'incomplete_tail')
        self.assertEqual(scan.records, [])
        self.assertEqual(scan.good_offset, 0)

    def test_valid_record_then_incomplete_tail(self):
        """Valid records are kept; the partial one is classified as tail."""
        with WalWriter(self.wal) as w:
            w.append(1, b'good')
        partial = encode_record(2, b'partial')[:12]
        with open(self.wal, 'ab') as f:
            f.write(partial)
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'incomplete_tail')
        self.assertEqual(scan.records, [(1, b'good')])
        self.assertEqual(scan.good_offset, len(encode_record(1, b'good')))

    def test_invalid_magic_detected(self):
        """Non-magic bytes at a record boundary -> corruption."""
        with open(self.wal, 'wb') as f:
            f.write(b'THIS IS NOT A FORGE RECORD')
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'corruption')
        self.assertEqual(scan.records, [])

    def test_corrupt_checksum_detected(self):
        """A complete record whose payload was changed -> corruption."""
        with WalWriter(self.wal) as w:
            w.append(1, b'first')
        with open(self.wal, 'rb') as fh:
            data = bytearray(fh.read())
        data[-1] ^= 0xFF  # flip a payload byte
        with open(self.wal, 'wb') as f:
            f.write(bytes(data))
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'corruption')
        self.assertEqual(scan.records, [])

    def test_invalid_length_detected(self):
        """A length field pointing past EOF is rejected."""
        record = bytearray(encode_record(1, b'hello'))
        record[2:6] = struct.pack('>I', 0x7FFFFFFF)
        with open(self.wal, 'wb') as f:
            f.write(bytes(record))
        scan = scan_wal(self.wal)
        self.assertEqual(scan.status, 'incomplete_tail')
        self.assertEqual(scan.records, [])
        self.assertEqual(scan.good_offset, 0)
class TestWalTruncate(WalTestCase):
    """Tests for truncate_tail."""

    def test_truncate_removes_extra_bytes(self):
        with WalWriter(self.wal) as w:
            w.append(1, b'good')
        with open(self.wal, 'rb') as fh:
            clean = fh.read()
        tail = b'garbage tail bytes'
        with open(self.wal, 'ab') as f:
            f.write(tail)
        removed = truncate_tail(self.wal, len(clean))
        self.assertEqual(removed, len(tail))
        with open(self.wal, 'rb') as fh:
            self.assertEqual(fh.read(), clean)
        self.assertEqual(scan_wal(self.wal).status, 'ok')

    def test_truncate_noop_when_clean(self):
        with WalWriter(self.wal) as w:
            w.append(1, b'good')
        size = os.path.getsize(self.wal)
        self.assertEqual(truncate_tail(self.wal, size), 0)
        self.assertEqual(os.path.getsize(self.wal), size)

    def test_truncate_never_removes_committed_bytes(self):
        with WalWriter(self.wal) as w:
            for i in range(3):
                w.append(i, b'x')
        size = os.path.getsize(self.wal)
        self.assertEqual(truncate_tail(self.wal, size), 0)
        self.assertEqual(len(scan_wal(self.wal).records), 3)


class TestWalIOErrors(WalTestCase):
    """I/O errors must propagate; nothing may be silently swallowed."""

    def test_open_on_directory_raises_oserror(self):
        dirpath = os.path.join(self.tempdir.name, 'adir')
        os.makedirs(dirpath)
        with self.assertRaises(OSError):
            WalWriter(dirpath)

    def test_append_after_close_raises(self):
        w = WalWriter(self.wal)
        w.append(1, b'x')
        w.close()
        with self.assertRaises(ValueError):
            w.append(2, b'y')


if __name__ == '__main__':
    unittest.main()