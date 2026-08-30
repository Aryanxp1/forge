"""Crash recovery: replay committed WAL records into storage.

Recovery is deterministic and IDEMPOTENT:

  - A WAL record whose document ID already exists in storage is SKIPPED.
    The storage write may have completed before the crash, and applying
    it again would duplicate the document.
  - A WAL record whose document ID appears more than once in the WAL is
    applied only once (first occurrence wins).

So after ANY crash point, replaying the WAL never creates duplicates.

Procedure:
  1. Scan the WAL sequentially, validating MAGIC, LENGTH, record
     boundaries, CHECKSUM and DOC_ID on every record.
  2. Apply every valid record to storage, skipping existing doc IDs.
  3. If an incomplete/corrupt tail exists, truncate it. No forward
     resynchronization is attempted.
  4. Produce a structured recovery report.

FORGE detects corruption; it never reconstructs arbitrary bad data.
"""

import os
from dataclasses import dataclass, field
from typing import List

from .storage import Storage
from .wal import scan_wal, truncate_tail


@dataclass
class RecoveryReport:
    """Structured result of a WAL recovery run."""

    wal_path: str
    records_examined: int = 0       # valid records parsed from the WAL
    records_recovered: int = 0      # valid records newly applied to storage
    records_skipped: int = 0        # valid records already present
    incomplete_tail_detected: bool = False
    corruption_detected: bool = False
    tail_truncated: bool = False
    truncated_bytes: int = 0
    completed: bool = False         # whole WAL was valid and applied
    reason: str = ''

    def __str__(self) -> str:
        return (
            f"RecoveryReport(wal={self.wal_path}, "
            f"examined={self.records_examined}, "
            f"recovered={self.records_recovered}, "
            f"skipped={self.records_skipped}, "
            f"incomplete_tail={self.incomplete_tail_detected}, "
            f"corruption={self.corruption_detected}, "
            f"tail_truncated={self.tail_truncated}, "
            f"truncated_bytes={self.truncated_bytes}, "
            f"completed={self.completed})"
        )


@dataclass
class ConsistencyReport:
    """Result of storage <-> WAL consistency validation."""

    wal_doc_count: int              # distinct doc IDs committed in the WAL
    storage_doc_count: int          # documents presently in storage
    missing_doc_ids: List[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_doc_ids


def recover(wal_path: str, storage: Storage) -> RecoveryReport:
    """Replay the WAL into storage and report what happened.

    Storage I/O errors or validation errors are propagated, never
    swallowed. If an error occurs mid-recovery nothing is truncated, so
    a later retry can resume safely.
    """
    scan = scan_wal(wal_path)

    applied = set()
    recovered = 0
    skipped = 0
    for doc_id, payload in scan.records:
        if doc_id in applied or storage.has_doc(doc_id):
            skipped += 1
            continue
        storage.append(doc_id, payload)
        applied.add(doc_id)
        recovered += 1

    tail_truncated = False
    truncated_bytes = 0
    if scan.status != 'ok':
        truncated_bytes = scan.total - scan.good_offset
        if truncated_bytes > 0:
            truncate_tail(wal_path, scan.good_offset)
            tail_truncated = True

    return RecoveryReport(
        wal_path=os.fspath(wal_path),
        records_examined=len(scan.records),
        records_recovered=recovered,
        records_skipped=skipped,
        incomplete_tail_detected=(scan.status == 'incomplete_tail'),
        corruption_detected=(scan.status == 'corruption'),
        tail_truncated=tail_truncated,
        truncated_bytes=truncated_bytes,
        completed=(scan.status == 'ok'),
        reason=scan.reason,
    )


def validate_consistency(wal_path: str, storage: Storage) -> ConsistencyReport:
    """Verify every committed WAL document is present in storage.

    Storage is the source of truth; the WAL declares every committed
    write. After a successful recovery the two must agree on doc IDs.
    Duplicate doc IDs within the WAL itself are collapsed to a single
    expected document.
    """
    scan = scan_wal(wal_path)
    wal_ids = {doc_id for doc_id, _payload in scan.records}
    missing = sorted(
        doc_id for doc_id in wal_ids if not storage.has_doc(doc_id)
    )
    return ConsistencyReport(
        wal_doc_count=len(wal_ids),
        storage_doc_count=len(storage),
        missing_doc_ids=missing,
    )