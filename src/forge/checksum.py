"""CRC32 checksum utilities for FORGE record integrity verification.

Uses zlib.crc32 from the Python standard library.
"""

import zlib


def compute_crc32(data: bytes) -> int:
    """Compute CRC32 checksum over raw bytes.

    Args:
        data: Raw bytes to checksum.

    Returns:
        Unsigned 32-bit CRC32 value.
    """
    return zlib.crc32(data) & 0xFFFFFFFF


def validate_crc32(data: bytes, expected: int) -> bool:
    """Validate data against an expected CRC32 checksum.

    Args:
        data: Raw bytes to verify.
        expected: Expected CRC32 value.

    Returns:
        True if checksum matches, False otherwise.
    """
    return compute_crc32(data) == expected
