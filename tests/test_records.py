"""Tests for FORGE binary record format."""

import struct
import unittest

from forge.records import (
    CHECKSUM,
    DOC_ID,
    LENGTH,
    MAGIC,
    HEADER_SIZE,
    InvalidChecksumError,
    InvalidDocumentIdError,
    InvalidLengthError,
    InvalidMagicError,
    TruncatedRecordError,
    decode_record,
    encode_record,
    parse_header,
    read_records,
    record_size,
)


class TestConstants(unittest.TestCase):
    """Verify record format constants."""

    def test_magic_is_two_bytes(self):
        """MAGIC must be exactly 2 bytes."""
        self.assertEqual(len(MAGIC), 2)

    def test_header_size(self):
        """HEADER_SIZE equals MAGIC + LENGTH + CHECKSUM + DOC_ID."""
        expected = len(MAGIC) + LENGTH + CHECKSUM + DOC_ID
        self.assertEqual(HEADER_SIZE, expected)

    def test_header_size_value(self):
        """HEADER_SIZE must be 18 bytes."""
        self.assertEqual(HEADER_SIZE, 18)


class TestEncodeRecord(unittest.TestCase):
    """Tests for encode_record function."""

    def test_basic_encode(self):
        """Encode a simple record."""
        payload = b'hello world'
        record = encode_record(1, payload)
        self.assertIsInstance(record, bytes)
        self.assertGreaterEqual(len(record), HEADER_SIZE)

    def test_record_starts_with_magic(self):
        """Encoded record begins with MAGIC."""
        record = encode_record(1, b'test')
        self.assertEqual(record[0:2], MAGIC)

    def test_roundtrip(self):
        """Encode then decode returns original data."""
        payload = b'test payload'
        doc_id = 42
        record = encode_record(doc_id, payload)
        decoded_id, decoded_payload = decode_record(record)
        self.assertEqual(decoded_id, doc_id)
        self.assertEqual(decoded_payload, payload)

    def test_empty_payload(self):
        """Encode record with empty payload."""
        record = encode_record(0, b'')
        decoded_id, decoded_payload = decode_record(record)
        self.assertEqual(decoded_id, 0)
        self.assertEqual(decoded_payload, b'')

    def test_unicode_payload(self):
        """Encode record with UTF-8 encoded unicode."""
        payload = 'Hello, World!'.encode('utf-8')
        record = encode_record(100, payload)
        decoded_id, decoded_payload = decode_record(record)
        self.assertEqual(decoded_payload, payload)
        self.assertEqual(decoded_payload.decode('utf-8'), 'Hello, World!')

    def test_various_document_ids(self):
        """Test encoding with various document IDs."""
        for doc_id in [0, 1, 255, 256, 1000, 2**32 - 1, 2**64 - 1]:
            record = encode_record(doc_id, b'test')
            decoded_id, _ = decode_record(record)
            self.assertEqual(decoded_id, doc_id)

    def test_negative_doc_id_raises(self):
        """Negative doc_id raises InvalidDocumentIdError."""
        with self.assertRaises(InvalidDocumentIdError):
            encode_record(-1, b'test')

    def test_too_large_doc_id_raises(self):
        """doc_id exceeding uint64 raises InvalidDocumentIdError."""
        with self.assertRaises(InvalidDocumentIdError):
            encode_record(2**64, b'test')

    def test_large_payload(self):
        """Encode record with large payload."""
        payload = b'x' * 100000
        record = encode_record(1, payload)
        decoded_id, decoded_payload = decode_record(record)
        self.assertEqual(len(decoded_payload), 100000)

    def test_deterministic_encoding(self):
        """Same inputs always produce same output."""
        record1 = encode_record(42, b'hello')
        record2 = encode_record(42, b'hello')
        self.assertEqual(record1, record2)


class TestDecodeRecord(unittest.TestCase):
    """Tests for decode_record function."""

    def test_truncated_header_raises(self):
        """Truncated header raises TruncatedRecordError."""
        with self.assertRaises(TruncatedRecordError):
            decode_record(b'\x46\x47\x00')

    def test_invalid_magic_raises(self):
        """Wrong MAGIC raises InvalidMagicError."""
        record = b'\x00\x00' + b'\x00' * (HEADER_SIZE - 2)
        with self.assertRaises(InvalidMagicError):
            decode_record(record)

    def test_corrupted_payload_detected(self):
        """Corrupted payload raises InvalidChecksumError."""
        # Encode a valid record, then corrupt the payload
        record = bytearray(encode_record(1, b'hello'))
        # Corrupt last byte of payload
        record[-1] ^= 0xFF
        with self.assertRaises(InvalidChecksumError):
            decode_record(bytes(record))

    def test_corrupted_checksum_detected(self):
        """Corrupted checksum raises InvalidChecksumError."""
        # Encode a valid record, then corrupt the checksum
        record = bytearray(encode_record(1, b'hello'))
        # Corrupt checksum byte
        record[6] ^= 0xFF
        with self.assertRaises(InvalidChecksumError):
            decode_record(bytes(record))

    def test_length_mismatch_detected(self):
        """Length field mismatch raises InvalidLengthError."""
        # Create a record where LENGTH says 10 but payload is 5 bytes
        payload = b'hello'
        header = struct.pack('>2sI', MAGIC, 10)  # Lie about length
        checksum_bytes = struct.pack('>I', 0)
        doc_id_bytes = struct.pack('>Q', 1)
        record = header + checksum_bytes + doc_id_bytes + payload
        with self.assertRaises(InvalidLengthError):
            decode_record(record)


class TestParseHeader(unittest.TestCase):
    """Tests for parse_header function."""

    def test_parse_valid_header(self):
        """Parse header from valid record."""
        record = encode_record(42, b'test')
        checksum, doc_id, length = parse_header(record)
        self.assertEqual(doc_id, 42)
        self.assertEqual(length, 4)
        self.assertIsInstance(checksum, int)

    def test_truncated_header_raises(self):
        """Truncated header raises TruncatedRecordError."""
        with self.assertRaises(TruncatedRecordError):
            parse_header(b'\x46\x47')

    def test_invalid_magic_raises(self):
        """Invalid magic raises InvalidMagicError."""
        with self.assertRaises(InvalidMagicError):
            parse_header(b'\x00\x00' + b'\x00' * 16)


class TestReadRecords(unittest.TestCase):
    """Tests for read_records function."""

    def test_single_record(self):
        """Read a single record from stream."""
        record = encode_record(1, b'hello')
        results = list(read_records(record))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], (1, b'hello'))

    def test_multiple_records(self):
        """Read multiple sequential records."""
        records = b''
        for i in range(5):
            records += encode_record(i, f'doc {i}'.encode())
        results = list(read_records(records))
        self.assertEqual(len(results), 5)
        for i, (doc_id, payload) in enumerate(results):
            self.assertEqual(doc_id, i)
            self.assertEqual(payload, f'doc {i}'.encode())

    def test_truncated_tail_raises(self):
        """Truncated record at end raises TruncatedRecordError."""
        record = encode_record(1, b'hello')
        # Cut off last 2 bytes
        truncated = record[:-2]
        with self.assertRaises(TruncatedRecordError):
            list(read_records(truncated))

    def test_empty_stream(self):
        """Empty stream yields no records."""
        results = list(read_records(b''))
        self.assertEqual(len(results), 0)


class TestRecordSize(unittest.TestCase):
    """Tests for record_size function."""

    def test_zero_payload(self):
        """Record size for empty payload."""
        self.assertEqual(record_size(0), HEADER_SIZE)

    def test_various_sizes(self):
        """Record size for various payload lengths."""
        for length in [1, 100, 1000, 65535]:
            self.assertEqual(record_size(length), HEADER_SIZE + length)


if __name__ == '__main__':
    unittest.main()
