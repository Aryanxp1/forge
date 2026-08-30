"""Binary record format for FORGE persistent storage.

Record layout (all fields big-endian):
    +--------+--------+----------+--------+---------+
    | MAGIC  | LENGTH | CHECKSUM | DOC_ID | PAYLOAD |
    +--------+--------+----------+--------+---------+
      2 B       4 B      4 B       8 B       N B

- MAGIC:  2-byte marker (0x46 0x47 = "FG")
- LENGTH: 4-byte uint32, payload length in bytes
- CHECKSUM: 4-byte uint32, CRC32 over (DOC_ID + PAYLOAD)
- DOC_ID: 8-byte uint64, unique document identifier
- PAYLOAD: N bytes, UTF-8 encoded document content

Checksum is computed over the concatenation: DOC_ID bytes + PAYLOAD bytes.
"""

import struct
from typing import Iterator

from .checksum import compute_crc32

# Record constants
MAGIC = b'\x46\x47'  # "FG" in ASCII
HEADER_SIZE = 2 + 4 + 4 + 8  # MAGIC + LENGTH + CHECKSUM + DOC_ID = 18 bytes

# Field sizes (bytes)
LENGTH = 4    # payload length
CHECKSUM = 4  # CRC32 checksum
DOC_ID = 8    # document id

# Struct formats (big-endian)
_UINT32_BE = '>I'
_UINT64_BE = '>Q'


class RecordError(Exception):
    """Base exception for record encoding/decoding errors."""
    pass


class InvalidMagicError(RecordError):
    """Record has an invalid MAGIC marker."""
    pass


class InvalidLengthError(RecordError):
    """Record LENGTH field does not match actual payload size."""
    pass


class InvalidChecksumError(RecordError):
    """Record CHECKSUM does not match computed CRC32."""
    pass


class TruncatedRecordError(RecordError):
    """Record data is truncated/incomplete."""
    pass


class InvalidDocumentIdError(RecordError):
    """Document ID is out of valid range."""
    pass
def encode_record(doc_id: int, payload: bytes) -> bytes:
    """Encode a document into a binary record.

    Args:
        doc_id: Unique 64-bit document identifier (0 to 2^64 - 1).
        payload: Document content as raw bytes.

    Returns:
        Complete binary record as bytes.

    Raises:
        InvalidDocumentIdError: If doc_id is negative or exceeds uint64 range.
    """
    if doc_id < 0 or doc_id > 0xFFFFFFFFFFFFFFFF:
        raise InvalidDocumentIdError(
            f"doc_id must be in range [0, 2^64-1], got {doc_id}"
        )

    doc_id_bytes = struct.pack(_UINT64_BE, doc_id)
    checksum = compute_crc32(doc_id_bytes + payload)

    header = struct.pack('>2sI', MAGIC, len(payload))
    checksum_bytes = struct.pack(_UINT32_BE, checksum)

    return header + checksum_bytes + doc_id_bytes + payload


def decode_record(data: bytes) -> tuple[int, bytes]:
    """Decode a complete binary record.

    Args:
        data: Complete record bytes (HEADER + PAYLOAD).

    Returns:
        Tuple of (doc_id, payload).

    Raises:
        TruncatedRecordError: If data is too short for a valid record.
        InvalidMagicError: If MAGIC marker is incorrect.
        InvalidLengthError: If LENGTH does not match actual payload.
        InvalidChecksumError: If CRC32 validation fails.
    """
    if len(data) < HEADER_SIZE:
        raise TruncatedRecordError(
            f"Record too short: {len(data)} bytes, minimum {HEADER_SIZE}"
        )

    magic = data[0:2]
    if magic != MAGIC:
        raise InvalidMagicError(
            f"Invalid MAGIC: expected {MAGIC!r}, got {magic!r}"
        )

    length = struct.unpack(_UINT32_BE, data[2:6])[0]
    checksum = struct.unpack(_UINT32_BE, data[6:10])[0]
    doc_id = struct.unpack(_UINT64_BE, data[10:18])[0]

    payload = data[18:]

    if len(payload) != length:
        raise InvalidLengthError(
            f"LENGTH field says {length} bytes, but payload is {len(payload)} bytes"
        )

    doc_id_bytes = data[10:18]
    expected_checksum = compute_crc32(doc_id_bytes + payload)
    if checksum != expected_checksum:
        raise InvalidChecksumError(
            f"Checksum mismatch: stored {checksum:#010x}, "
            f"computed {expected_checksum:#010x}"
        )

    return doc_id, payload
def parse_header(data: bytes) -> tuple[int, int, int]:
    """Parse record header fields without validating payload.

    Args:
        data: At least HEADER_SIZE bytes.

    Returns:
        Tuple of (checksum, doc_id, payload_length).

    Raises:
        TruncatedRecordError: If data is too short.
        InvalidMagicError: If MAGIC marker is incorrect.
    """
    if len(data) < HEADER_SIZE:
        raise TruncatedRecordError(
            f"Header too short: {len(data)} bytes, need {HEADER_SIZE}"
        )

    magic = data[0:2]
    if magic != MAGIC:
        raise InvalidMagicError(
            f"Invalid MAGIC: expected {MAGIC!r}, got {magic!r}"
        )

    length = struct.unpack(_UINT32_BE, data[2:6])[0]
    checksum = struct.unpack(_UINT32_BE, data[6:10])[0]
    doc_id = struct.unpack(_UINT64_BE, data[10:18])[0]

    return checksum, doc_id, length


def scan_records(stream: bytes) -> Iterator[tuple[int, bytes, int]]:
    """Iterate valid records in a byte stream, yielding byte offsets.

    Stops at the first invalid or incomplete record.
    Does NOT attempt forward resynchronization.

    Args:
        stream: Byte stream containing sequential records.

    Yields:
        Tuples of (doc_id, payload, offset) where offset is the byte
        offset of the record header within the stream.

    Raises:
        TruncatedRecordError: If a record header or payload is incomplete.
        InvalidMagicError / InvalidLengthError / InvalidChecksumError:
            If a complete record fails validation.
    """
    offset = 0
    while offset < len(stream):
        if offset + HEADER_SIZE > len(stream):
            raise TruncatedRecordError(
                f"Incomplete header at offset {offset}: "
                f"{len(stream) - offset} bytes remaining, need {HEADER_SIZE}"
            )

        _, _, length = parse_header(stream[offset:])

        total_record_size = HEADER_SIZE + length
        if offset + total_record_size > len(stream):
            raise TruncatedRecordError(
                f"Incomplete payload at offset {offset}: "
                f"expected {length} bytes, got {len(stream) - offset - HEADER_SIZE}"
            )

        record_data = stream[offset:offset + total_record_size]
        decoded_doc_id, payload = decode_record(record_data)

        yield decoded_doc_id, payload, offset
        offset += total_record_size


def read_records(stream: bytes) -> Iterator[tuple[int, bytes]]:
    """Read multiple sequential records from a byte stream.

    Stops at the first invalid or incomplete record.
    Does NOT attempt forward resynchronization.

    Thin wrapper around scan_records that drops the byte offsets.

    Args:
        stream: Byte stream containing sequential records.

    Yields:
        Tuples of (doc_id, payload) for each valid record.

    Raises:
        RecordError: If an invalid or incomplete record is encountered.
    """
    for doc_id, payload, _offset in scan_records(stream):
        yield doc_id, payload


def record_size(payload_length: int) -> int:
    """Calculate total record size for a given payload length.

    Args:
        payload_length: Length of payload in bytes.

    Returns:
        Total record size in bytes (HEADER + PAYLOAD).
    """
    return HEADER_SIZE + payload_length
