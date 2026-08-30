# FORGE

A zero-dependency local data engine that persistently stores and indexes documents for fast ranked search, detects data corruption through integrity checks, and automatically recovers committed data after crashes.

## Current Status

**V1 Complete — Reproducible Python packaging**

All Tier 1 + Tier 2 features are implemented, tested, and packaged:

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
- AND / OR query evaluation with deterministic results
- TF-IDF ranking (`--ranked` flag) with deterministic tie-breaking
- Index rebuild from storage (derived index, always reconstructible from records)
- Storage <-> index consistency validation (independent reference; detects missing/extra docs, postings, term frequencies)
- Command-line interface (`forge {add,index,search,stats,check}`, installable via `pip install .`)
- PEP 621 packaging (`pyproject.toml`) — `setuptools` build-time only, no runtime dependencies
- 249 passing tests (including 2 subprocess crash tests)

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

- Python 3.9+
- No external dependencies (standard library only at runtime)

## Build / Install

### Standalone artifact (preferred — no pip required)

```bash
python build_artifact.py
```

This produces `dist/forge.pyz` — a single self-contained executable built
using **only the Python standard library** (`zipfile`/`zipapp` semantics).
No pip, no setuptools, no virtualenv required.

Run it with:

```bash
python dist/forge.pyz --help
python dist/forge.pyz add <file>
python dist/forge.pyz search "query"
python dist/forge.pyz search "query" --ranked
python dist/forge.pyz stats
python dist/forge.pyz check
```

### pip install (alternative)

```bash
pip install .           # standard install; creates `forge` on PATH
pip install -e .        # editable (development) install
python -m forge --help  # also works via __main__.py
```

### Runtime dependencies

**Python standard library only.** `setuptools` (used only by
`pip install .`) and the `zipfile` module (used by `build_artifact.py`)
are both stdlib. No third-party packages are imported at runtime.

### Reproducible build

Two consecutive builds of `dist/forge.pyz` from the same source are
byte-identical (SHA256 verified). See `STDLIB_FINAL.md` for evidence.

## Project Structure

```
forge/
├── pyproject.toml          # PEP 621 packaging (setuptools build-time only)
├── build_artifact.py       # reproducible standalone build → dist/forge.pyz
├── deps-proof.txt          # auto-generated runtime dependency evidence
├── src/
│   └── forge/
│       ├── __init__.py
│       ├── __main__.py     # enables `python -m forge`
│       ├── cli.py          # command-line interface (add/index/search/stats/check)
│       ├── records.py      # Binary record encode/decode
│       ├── checksum.py     # CRC32 utilities
│       ├── wal.py          # Durable append WAL + fsync commit point
│       ├── storage.py      # Append-only persistent storage (source of truth)
│       ├── recovery.py     # WAL replay / crash recovery + consistency
│       ├── tokenizer.py    # Deterministic V1 tokenizer
│       ├── index.py        # In-memory derived inverted index
│       ├── search.py       # AND / OR query evaluation
│       ├── ranking.py      # TF-IDF scoring + ranking
│       └── consistency.py  # rebuild + storage<->index validation
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
│   ├── test_ranking.py
│   ├── test_consistency.py
│   └── test_cli.py
├── ARCHITECTURE.md
├── SCOPE_FINAL.md
├── WAL_FORMAT_FINAL.md
├── STDLIB_FINAL.md
└── README.md
```

## Running Tests

```bash
# After `pip install .` (or `pip install -e .`):
python -m unittest discover -s tests -v

# Without installing (development only):
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Dependency Proof

`deps-proof.txt` — auto-generated list of all runtime imports in
`src/forge/*`. Every import is a Python standard library module.
No third-party packages are imported at runtime.

## Reproducible Build

`python build_artifact.py` → `dist/forge.pyz`

Two consecutive builds from the same source are byte-identical
(SHA256 verified). See `STDLIB_FINAL.md` for the full reproducibility
evidence.

## License

MIT (see LICENSE file — **NOTE: LICENSE file must be added before
submission; the project is intended to be MIT-licensed but no LICENSE
file is present in the repository yet.**)
