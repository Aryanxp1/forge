# WAL_FORMAT.md — FINAL DESIGN SPEC

Design-only document. No implementation code before kickoff.

## 1. Record format

```text
+--------+--------+----------+--------+---------+
| MAGIC  | LENGTH | CHECKSUM | DOC_ID | PAYLOAD |
+--------+--------+----------+--------+---------+
  2 B       4 B      4 B       8 B       N B
```

- MAGIC: fixed marker identifying a record boundary.
- LENGTH: payload length in bytes.
- CHECKSUM: checksum over DOC_ID + PAYLOAD.
- DOC_ID: unique 64-bit document identifier.
- PAYLOAD: document content.

For Python, CRC32 can use `zlib.crc32`.

A checksum mismatch means corruption is detected. V1 does NOT repair corrupted records.

## 2. Write path

1. Receive document.
2. Serialize the record.
3. Append it to WAL.
4. Flush and `fsync` the WAL.
5. Treat the write as committed.
6. Apply the record to persistent storage.
7. Update the derived inverted index.

The durable commit point is the WAL `fsync`.

## 3. Recovery

1. Open WAL.
2. Read records sequentially.
3. Validate MAGIC, LENGTH and CHECKSUM.
4. Valid record → apply/recover it.
5. Invalid or incomplete record → stop at that point and truncate the invalid tail.
6. Do not search forward for another MAGIC marker.
7. Rebuild/validate the inverted index from storage.
8. Run consistency validation.
9. Report recovered records and discarded bytes.

## 4. Consistency rule

Storage is the source of truth.

The inverted index is derived data.

If validation finds an index mismatch:
- rebuild the index from storage;
- validate again;
- report PASS/FAIL.

## 5. Crash guarantee

A write acknowledged after WAL `fsync` must survive a process crash.

A write still in flight may be lost, but it must not corrupt previously committed records.

## 6. Checkpointing

Checkpointing is optional Tier 3.

Do not implement it until basic WAL recovery is stable.

If implemented:
1. Ensure WAL records are reflected in storage/index.
2. Validate consistency.
3. Create a new WAL.
4. Only then retire the old WAL safely.

If time runs out, an unbounded WAL is an accepted documented limitation.

## 7. Crash-fuzzing

Tier 2 test:

1. Start a fresh writer process.
2. Perform writes.
3. Kill at randomized points.
4. Restart.
5. Recover.
6. Validate consistency.
7. Verify every acknowledged write.
8. Record results.

Target report:
`N crash simulations, N successful recoveries, 0 invalid states, 0 lost committed records`

## 8. Explicit non-goals

- No corruption reconstruction
- No partial-record repair
- No update/delete in v1
- No transactions
- No distributed/replicated writers
- No search-forward resynchronization
