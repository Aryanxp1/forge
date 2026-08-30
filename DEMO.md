# FORGE — 5-Minute Judge Demo

All commands below run against the real submission artifact from the
repository root. No pip, no setuptools, no virtualenv, no PYTHONPATH.

## Script

### 0:00–0:30 — What FORGE is

> "FORGE is a zero-dependency local data engine. It stores documents
> durably, survives crashes, and gives deterministic AND/OR + TF-IDF
> ranked search — built with the Python standard library only.
> **Track D — Zero-Dependency Local Data Engine.**"

### 0:30–1:00 — Zero-dependency proof

Show `deps-proof.txt` (committed, auto-generated from the real imports):

```bash
Get-Content deps-proof.txt
# every runtime import is stdlib: argparse, collections, dataclasses,
# math, os, struct, sys, zlib (plus intra-package `forge.*`)
```

No `requirements.txt` exists. `STDLIB.md` documents the 12 real
substitutions (argparse↔Click, zlib↔CRC libs, math↔numpy, zipapp↔PyInstaller, …).

### 1:00–2:00 — Build and run

```powershell
# one-command build (stdlib-only build tool)
python build_artifact.py

# run the artifact
python dist/forge.pyz --help
```

Rebuild it a second time and show the SHA-256 is byte-identical
(`STDLIB.md` -> Reproducible build):

```powershell
Get-FileHash dist/forge.pyz -Algorithm SHA256
```

### 2:00–3:00 — Add documents + search

```powershell
$D = "$env:TEMP\forge_demo"
Remove-Item $D -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $D | Out-Null
"python storage engine"   | Set-Content $D\doc1.txt
"python search engine"    | Set-Content $D\doc2.txt
"storage search index"    | Set-Content $D\doc3.txt

python dist/forge.pyz --data-dir $D add $D\doc1.txt
python dist/forge.pyz --data-dir $D add $D\doc2.txt
python dist/forge.pyz --data-dir $D add $D\doc3.txt

python dist/forge.pyz --data-dir $D search "python engine"        # AND (default)
python dist/forge.pyz --data-dir $D search "python storage" --or  # OR
```

### 3:00–3:45 — Ranked TF-IDF search

```powershell
python dist/forge.pyz --data-dir $D search "python storage" --ranked
python dist/forge.pyz --data-dir $D search "python storage" --or --ranked
```

Note: scores come from `TF × log(N/df)`; e.g. a document containing both
rare query terms ranks above a document with only one.

### 3:45–4:20 — stats + consistency check

```powershell
python dist/forge.pyz --data-dir $D stats
python dist/forge.pyz --data-dir $D check
```

`check` rebuilds the index from storage and validates storage ↔ index
consistency (`ok: index is consistent with storage`).

### 4:20–5:00 — crash recovery / durability explanation

FORGE's commit point is the WAL: `append -> flush() -> os.fsync()` —
only then is a write acknowledged. On restart, committed records are
replayed from the WAL into storage (idempotent, no duplicates).

The existing deterministic crash test demonstrates this with a real
subprocess that hard-crashes (`os._exit(3)`) at two points:

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_crash -v
```

This starts a child process. tests/crash_helper.py:
1. writes a document and fsyncs the WAL  → COMMITTED,
2. hard-crashes either BEFORE the storage write or AFTER it,
3. the parent replays the WAL and asserts the committed document is
   recovered — with `validate_consistency` passing in both cases.

---

## What to show the judge

- **Empty runtime dependency proof** — `deps-proof.txt`: every runtime
  import is the Python standard library.
- **Reproducible SHA-256** — two consecutive builds are byte-identical
  (hash published in `STDLIB.md`).
- **254 passing tests** — `PYTHONPATH=src python -m unittest discover -s tests`
- **WAL fsync commit point** — the durability guarantee is `append ->
  flush() -> fsync()`, then and only then is the write committed.
- **Crash recovery** — `tests.test_crash` kills a process mid-write and
  recovers every committed document via WAL replay.
- **Ranked search** — `python dist/forge.pyz search "…" --ranked`
  displays deterministic TF-IDF scores and doc-ID tie-breaking.