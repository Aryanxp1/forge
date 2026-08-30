"""Append-only persistent document storage for FORGE.

Storage is the SOURCE OF TRUTH for document content. Storage records
use the exact same binary format as WAL records (records.py), so the
two are byte-compatible and recovery reuses a single serialization path.

Durability model:
  - The WAL fsync is the commit point (see wal.py).
  - Storage writes are flushed but intentionally NOT fsync'd here: if a
    storage write is lost or torn by a crash, WAL replay restores it.
  - On open, storage self-heals a torn tail by truncating it. Any
    record lost there is committed data whose durable copy lives in the
    WAL, so recovery rebuilds it.
"""

import os
from typing import Iterator

from .records import (
    HEADER_SIZE,
    RecordError,
    decode_record,
    encode_record,
    parse_header,
    record_size,
    scan_records,
)


class StorageError(Exception):
    """Base exception for storage errors."""


class DuplicateDocumentError(StorageError):
    """Appending a document ID that already exists."""


class DocumentNotFoundError(StorageError):
    """Requested document ID does not exist."""


class StorageCorruptedError(StorageError):
    """Stored bytes failed record validation."""


class Storage:
    """Append-only immutable document storage.

    Documents are add-only in V1: no update, no delete.
    """

    def __init__(self, path: str) -> None:
        self.path = os.fspath(path)
        # doc_id -> byte offset of the record header in the file.
        # This map is DERIVED data, rebuilt from the file on every open.
        self._offsets = {}
        self._file = None
        self._load()

    def _load(self) -> None:
        """Scan the existing file, index doc IDs, heal a torn tail.

        The file on disk is the source of truth; the doc_id -> offset
        map is a derived cache.
        """
        try:
            with open(self.path, 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            data = b''

        good_offset = 0
        try:
            for doc_id, payload, offset in scan_records(data):
                self._offsets[doc_id] = offset
                good_offset = offset + record_size(len(payload))
        except RecordError:
            # Tolerated at open: a crash mid-append may leave a partial
            # or corrupt final record. It is not committed storage data;
            # the durable copy is in the WAL, so truncating is safe and
            # recovery rebuilds anything lost.
            pass

        if good_offset < len(data):
            with open(self.path, 'r+b') as f:
                f.truncate(good_offset)

        self._file = open(self.path, 'ab')

    @property
    def doc_ids(self) -> frozenset:
        """Set of document IDs currently stored."""
        return frozenset(self._offsets)

    def __len__(self) -> int:
        return len(self._offsets)

    def has_doc(self, doc_id: int) -> bool:
        return doc_id in self._offsets

    def append(self, doc_id: int, payload: bytes) -> int:
        """Append a document record.

        Raises:
            DuplicateDocumentError: if doc_id already exists.
            InvalidDocumentIdError / OSError: propagated from
                encode_record / file I/O (never swallowed).
        """
        if doc_id in self._offsets:
            raise DuplicateDocumentError(
                f"document {doc_id} already exists in storage"
            )
        record = encode_record(doc_id, payload)
        offset = self._file.tell()
        self._file.write(record)
        self._file.flush()
        self._offsets[doc_id] = offset
        return doc_id

    def get(self, doc_id: int) -> bytes:
        """Return the payload for doc_id.

        Raises:
            DocumentNotFoundError: if doc_id does not exist.
            StorageCorruptedError: if the stored bytes fail validation.
        """
        offset = self._offsets.get(doc_id)
        if offset is None:
            raise DocumentNotFoundError(f"document {doc_id} not found")
        with open(self.path, 'rb') as f:
            f.seek(offset)
            header = f.read(HEADER_SIZE)
            if len(header) < HEADER_SIZE:
                raise StorageCorruptedError(
                    f"record header for document {doc_id} is truncated"
                )
            _, _, length = parse_header(header)
            record = header + f.read(length)
        decoded_id, payload = decode_record(record)
        if decoded_id != doc_id:
            raise StorageCorruptedError(
                f"record at offset {offset} decoded as doc {decoded_id}, "
                f"expected {doc_id}"
            )
        return payload

    def iter_records(self) -> Iterator[tuple[int, bytes]]:
        """Sequential scan yielding (doc_id, payload) for every document."""
        with open(self.path, 'rb') as f:
            data = f.read()
        try:
            for doc_id, payload, _offset in scan_records(data):
                yield doc_id, payload
        except RecordError as exc:
            raise StorageCorruptedError(str(exc)) from exc

    def close(self) -> None:
        if self._file is not None and not self._file.closed:
            self._file.close()

    def __enter__(self) -> 'Storage':
        return self

    def __exit__(self, *exc) -> None:
        self.close()