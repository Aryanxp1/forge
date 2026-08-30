"""Tests for FORGE CRC32 checksum utilities."""

import unittest

from forge.checksum import compute_crc32, validate_crc32


class TestComputeCrc32(unittest.TestCase):
    """Tests for compute_crc32 function."""

    def test_empty_data(self):
        """CRC32 of empty data is 0."""
        self.assertEqual(compute_crc32(b''), 0)

    def test_known_value(self):
        """Test against a known CRC32 value."""
        # CRC32 of "hello" is well-known
        result = compute_crc32(b'hello')
        self.assertEqual(result, 0x3610a686)

    def test_different_data_different_checksum(self):
        """Different data produces different checksums."""
        crc1 = compute_crc32(b'hello')
        crc2 = compute_crc32(b'world')
        self.assertNotEqual(crc1, crc2)

    def test_deterministic(self):
        """Same input always produces same output."""
        data = b'test data for checksum'
        self.assertEqual(compute_crc32(data), compute_crc32(data))

    def test_returns_unsigned_32bit(self):
        """Result is always in unsigned 32-bit range."""
        result = compute_crc32(b'some data')
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, 0xFFFFFFFF)

    def test_binary_data(self):
        """Works with arbitrary binary data."""
        data = bytes(range(256))
        result = compute_crc32(data)
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)

    def test_concatenation(self):
        """CRC32 of concatenated data matches combined input."""
        a = b'hello'
        b = b'world'
        combined = compute_crc32(a + b)
        self.assertNotEqual(combined, compute_crc32(a))
        self.assertNotEqual(combined, compute_crc32(b))


class TestValidateCrc32(unittest.TestCase):
    """Tests for validate_crc32 function."""

    def test_valid_checksum(self):
        """Returns True for matching checksum."""
        data = b'test data'
        checksum = compute_crc32(data)
        self.assertTrue(validate_crc32(data, checksum))

    def test_invalid_checksum(self):
        """Returns False for non-matching checksum."""
        data = b'test data'
        checksum = compute_crc32(data)
        self.assertFalse(validate_crc32(data, checksum + 1))

    def test_empty_data_valid(self):
        """Validates empty data with correct checksum."""
        self.assertTrue(validate_crc32(b'', 0))

    def test_empty_data_invalid(self):
        """Rejects empty data with wrong checksum."""
        self.assertFalse(validate_crc32(b'', 1))


if __name__ == '__main__':
    unittest.main()
