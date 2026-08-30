# STDLIB.md — STANDARD LIBRARY LOG

## Purpose

Document every meaningful third-party package we could normally use and the Python standard-library functionality we use instead.

Only document substitutions that are actually used in the final project.

## Candidate substitutions

Every entry below reflects an actual import in `src/forge/*` or `tests/*`.
No entry is invented to reach a count.

| # | Normally used | Python stdlib / built-in | Purpose | Actual usage / trade-off |
|---|---|---|---|---|
| 1 | Click / Typer | `argparse` | CLI parsing | `forge.cli.build_parser()` — full subcommand CLI with `--help`, exit codes |
| 2 | pytest / nose | `unittest` | Automated tests | All 254 tests use `unittest.TestCase` + `tempfile` for isolation |
| 3 | crcmod / pycrc | `zlib.crc32` | Record integrity | `forge.checksum.compute_crc32()` — per-record CRC32 over DOC_ID+PAYLOAD |
| 4 | Whoosh / Lucene | Hand-rolled inverted index | Search indexing | `forge.index.InvertedIndex` — term→doc-ID postings, AND/OR matching |
| 5 | SQLite / SQLAlchemy | `os` + custom append-only storage | Persistent storage | `forge.storage.Storage` — binary append-only records, source of truth |
| 6 | rich / tabulate | `str.format` / f-strings | CLI output | Ranked results table, stats, consistency reports |
| 7 | numpy / scipy | `math.log` | TF-IDF scoring | `forge.ranking.inverse_document_frequency()` — IDF = log(N/df) |
| 8 | attrs / pydantic | `dataclasses` | Structured reports | `RecoveryReport`, `IndexConsistencyReport` — immutable result objects |
| 9 | pandas | `collections.Counter` | Term frequency | Per-document term counts, document frequency computation |
| 10 | PyInstaller / Nuitka | `zipapp` (stdlib) | Standalone artifact | `build_artifact.py` → `dist/forge.pyz`, runs with `python dist/forge.pyz` |
| 11 | NLTK / spaCy | built-in `str` methods | Tokenization | `forge.tokenizer` — lowercase, split on non-alphanumerics, stopword removal |
| 12 | ctypes / struct-lib | `struct` | Record encoding | `forge.records` — big-endian pack/unpack of fixed-size binary headers |

Do not fill entries just to reach a number. The bonus evidence must reflect the actual implementation.

## Package Killer

Target package: **Whoosh** (pure-Python search library)

Why it is a fair comparison:
Whoosh is a pure-Python full-text search and indexing library, so it sits
in the same space as FORGE rather than being a C-extension engine. That
makes it a fair "how much can you build with the standard library alone?"
comparison.

What we implemented (FORGE's own core, no Whoosh code):
- persistent append-only document storage with per-record CRC32 integrity
  via `zlib.crc32`;
- a durable Write-Ahead Log with `flush()` + `os.fsync()` commit point;
- deterministic crash recovery by WAL replay (idempotent, no forward
  resynchronization);
- a hand-rolled inverted index (`term -> set of document IDs`) with
  per-document term-frequency tracking;
- deterministic AND/OR matching;
- TF-IDF ranking using `math.log`;
- storage/index consistency validation and index rebuild from storage.

What we deliberately did NOT implement:
FORGE is NOT feature-equivalent to Whoosh. We did NOT implement:
- BM25 (Whoosh's default scoring),
- phrase, fuzzy, wildcard or prefix queries,
- stemming / lemmatization analyzers,
- incremental index updates (Whoosh supports delete/update),
- N-gram / per-field analyzers,
- index segments, commit/merge policies,
- a query-parser language (FORGE uses simple AND/OR + a `--ranked` flag).

FORGE does not claim to replace Whoosh. It demonstrates that a
meaningful, crash-safe subset — durable storage + inverted index +
deterministic search/ranking — can be built with the Python standard
library alone.

Evidence of real-world usage/downloads:
No download or usage statistics are claimed, and none are fabricated.
This section is intentionally left without numbers.

## Reproducible build

Build command:
```text
python build_artifact.py
```

This produces `dist/forge.pyz` — a standalone, reproducible zipapp built
using only the Python standard library (`zipapp` semantics via the
`zipfile` module). No pip, no setuptools at runtime.

Clean environment:
```text
Python 3.9+ on PATH, no PYTHONPATH required, no pip install required
```

Build/run verification:
```text
python dist/forge.pyz --help
python dist/forge.pyz add <file>
python dist/forge.pyz search "query"
python dist/forge.pyz search "query" --ranked
python dist/forge.pyz stats
python dist/forge.pyz check
```

### Reproducibility evidence

Two consecutive builds from the same source + same Python toolchain
(Python 3.14.6, Windows):

```text
Build A: SHA256 = 767D42A01CCC74F0380CACCE2AEC1376CB4DD1B9B4FD03622AF9B4EA6C6ABF31
Build B: SHA256 = 767D42A01CCC74F0380CACCE2AEC1376CB4DD1B9B4FD03622AF9B4EA6C6ABF31
Byte identical = YES
```

Determinism is achieved by normalizing all archive-entry timestamps to
a fixed value (2020-01-01T00:00:00) and writing zip entries in sorted
order. See `build_artifact.py`.

## Dependency proof

Final runtime dependency list:
```text
Python standard library only
```

`setuptools` is a build-time tool only (declared in `pyproject.toml`'s
`build-system.requires`). It is NOT imported at runtime. The standalone
artifact (`dist/forge.pyz`) is built with `build_artifact.py`, which uses
only the `zipfile` and `shutil` modules from the standard library.

Full dependency evidence: `deps-proof.txt` (auto-generated from the
actual source imports in `src/forge/*`).

Verify using a clean environment before submission.
