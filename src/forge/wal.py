"""Write-Ahead Log (WAL) for FORGE.

The WAL is the durability anchor:

    append record -> flush() -> os.fsync() -> COMMITTED

A write is only acknowledged once fsync succeeds. After that point the
process may crash at any time; on restart the committed record MUST be
recoverable (see recovery.py).

Every WAL record uses the exact binary format from records.py:

    MAGIC(2) | LENGTH(4) | CHECKSUM(4) | DOC_ID(8) | PAYLOAD(N)
    CHECKSUM = CRC32(DOC_ID bytes + PAYLOAD), big-endian fields

This lets recovery reuse the same encode/decode routines.
"""

import os
from dataclasses import dataclass, field
from typing import List, Tuple

from .records import (
    InvalidChecksumError,
    InvalidLengthError,
    InvalidMagicError,
    TruncatedRecordError,
    encode_record,
    record_size,
    scan_records,
)


class WalError(Exception):
    """Base exception for WAL errors."""


@dataclass
class WalScanResult:
    """Result of scanning a WAL file.

    Attributes:
        records: Valid (doc_id, payload) records in file order.
        status:  'ok' | 'incomplete_tail' | 'corruption'.
        good_offset: Byte offset just past the last valid record.
        total:       Total file size in bytes.
        reason:      Human-readable detection details when not 'ok'.
    """

    records: List[Tuple[int, bytes]] = field(default_factory=list)
    status: str = 'ok'
    good_offset: int = 0
    total: int = 0
    reason: str = ''


class WalWriter:
    """Append-only, fsync-on-append WAL writer.

    The commit point is the successful os.fsync() inside append().
    """

    def __init__(self, path: str) -> None:
        self.path = os.fspath(path)
        self._file = open(self.path, 'ab')

    def append(self, doc_id: int, payload: bytes) -> int:
        """Encode, append, flush and fsync a record.

        Returns only after fsync succeeded (durable / committed).

        Raises:
            OSError: any write / flush / fsync failure is propagated,
                never swallowed. The write is NOT reported as committed
                if fsync fails.
        """
        record = encode_record(doc_id, payload)
        self._file.write(record)
        self._file.flush()
        os.fsync(self._file.fileno())
        return doc_id

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> 'WalWriter':
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def scan_wal(path: str) -> WalScanResult:
    """Read and validate WAL records sequentially.

    Stops at the first invalid or incomplete record. No forward
    resynchronization is attempted.

    Distinguishes (and keeps separate):

      - incomplete_tail: a record cut off by a crash (truncated header
        or payload). These are not committed data.
      - corruption: a complete record failed MAGIC/CHECKSUM/LENGTH
        validation. FORGE detects corruption, it does not repair it.

    Valid records are returned in order; good_offset points just past
    the last valid record so recovery can truncate an invalid tail.
    """
    path = os.fspath(path)
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        return WalScanResult()

    result = WalScanResult(total=len(data))
    try:
        for doc_id, payload, offset in scan_records(data):
            result.records.append((doc_id, payload))
            result.good_offset = offset + record_size(len(payload))
    except TruncatedRecordError as exc:
        result.status = 'incomplete_tail'
        result.reason = str(exc)
    except (InvalidMagicError, InvalidLengthError, InvalidChecksumError) as exc:
        result.status = 'corruption'
        result.reason = str(exc)
    return result


def truncate_tail(path: str, keep_bytes: int) -> int:
    """Truncate the WAL file down to keep_bytes (drop an invalid tail).

    Only the invalid/incomplete tail is ever removed; valid committed
    records are always preserved. Returns the number of bytes removed,
    or 0 if nothing was removed.
    """
    path = os.fspath(path)
    file_size = os.path.getsize(path)
    if keep_bytes >= file_size:
        return 0
    with open(path, 'r+b') as f:
        f.truncate(keep_bytes)
    return file_size - keep_bytes