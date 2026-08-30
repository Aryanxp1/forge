# FORGE

A zero-dependency local data engine that persistently stores and indexes documents for fast ranked search, detects data corruption through integrity checks, and automatically recovers committed data after crashes.

## Current Status

**Phase 5 — Index rebuild and consistency validation**

The following components are implemented:

- Binary record format with fixed-size header (MAGIC, LENGTH, CHECKSUM, DOC_ID) + variable payload
- CRC32 checksum computation and validation
- Deterministic big-endian binary encoding
- Durable Write-Ahead Log (WAL) with `flush()` + `os.fsync()` commit point
- Append-only persistent document storage (source of truth)
- Crash recovery via WAL replay (deterministic, idempotent, no forward resync)
- Storage <-> WAL consistency validation
- Subprocess crash-simulation test (committed write -> crash -> recovery)
- Deterministic V1 tokenizer (lowercase, split on non-alphanumerics, basic stopword removal, Unicode-safe)
- In-memory derived inverted index (`term -> set of doc IDs`, rebuildable from storage)
- AND / OR query evaluation with deterministic results (sorted by document ID)
- Index rebuild from storage (derived index, always reconstructible from records)
- Storage <-> index consistency validation (independent reference; detects missing/extra docs, postings, term frequencies)
- Command-line interface (`python -m forge {add,index,search,stats,check}`)
- Comprehensive test suite

## Architecture

FORGE follows a simple layered design:

```
Document
    │
    ▼
Write Request
    │
    ▼
  WAL ─────> fsync() ─────> COMMITTED
    │
    +------------------+
    |                  |
    v                  v
 STORAGE             INDEX
    |                  |
 checksum        inverted index
    |                  |
    +--------+---------+
             |
             v
           SEARCH
             |
         AND / OR
             |
         TF-IDF
             |
             v
        RESULTS
```

**Core principle:** Storage is the source of truth. The search index is derived data and can always be rebuilt from storage.

## Record Format

```
+--------+--------+----------+--------+---------+
| MAGIC  | LENGTH | CHECKSUM | DOC_ID | PAYLOAD |
+--------+--------+----------+--------+---------+
  2 B       4 B      4 B       8 B       N B
```

- **MAGIC:** 2-byte marker (0x46 0x47 = "FG")
- **LENGTH:** 4-byte uint32, payload length in bytes (big-endian)
- **CHECKSUM:** 4-byte uint32, CRC32 over DOC_ID + PAYLOAD (big-endian)
- **DOC_ID:** 8-byte uint64, unique document identifier (big-endian)
- **PAYLOAD:** N bytes, UTF-8 encoded document content

## Requirements

- Python 3.8+
- No external dependencies (standard library only)

## Project Structure

```
forge/
├── src/
│   └── forge/
│       ├── __init__.py
│       ├── records.py      # Binary record encode/decode
│       ├── checksum.py     # CRC32 utilities
│       ├── wal.py          # Durable append WAL + fsync commit point
│       ├── storage.py      # Append-only persistent storage (source of truth)
│       ├── recovery.py     # WAL replay / crash recovery + consistency
│       ├── tokenizer.py    # Deterministic V1 tokenizer
│       ├── index.py        # In-memory derived inverted index
│       ├── search.py       # AND / OR query evaluation
│       └── consistency.py    # rebuild + storage<->index validation
├── tests/
│   ├── __init__.py
│   ├── crash_helper.py     # Subprocess crash simulation helper
│   ├── test_checksum.py
│   ├── test_records.py
│   ├── test_wal.py
│   ├── test_storage.py
│   ├── test_recovery.py
│   ├── test_crash.py
│   ├── test_tokenizer.py
│   ├── test_index.py
│   ├── test_search.py
│   └── test_consistency.py
├── ARCHITECTURE.md
├── SCOPE_FINAL.md
├── WAL_FORMAT_FINAL.md
├── STDLIB_FINAL.md
└── README.md
```

## Running Tests

The `forge` package lives under `src/`, so the source tree must be on `PYTHONPATH`:

```bash
# POSIX (bash/zsh)
PYTHONPATH=src python -m unittest discover -s tests -v

# Windows (PowerShell)
$env:PYTHONPATH = 'src'; python -m unittest discover -s tests -v
```

## License

MIT
