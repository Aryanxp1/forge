# SCOPE.md — FINAL LOCKED SCOPE

## Project
Zero-dependency local data engine for persistent document storage and fast ranked search, with integrity checks and crash recovery.

## Locked pitch
> A zero-dependency local data engine that persistently stores and indexes documents for fast ranked search, detects data corruption through integrity checks, and automatically recovers committed data after crashes.

## Hard rule
If a new feature threatens the stability of the core, cut the feature — not the core.

---

## Tier 1 — MUST SHIP

1. Record format
2. Append-only persistent storage
3. Write-Ahead Log (WAL)
4. Per-record checksums for corruption detection
5. Tokenizer
6. Inverted index
7. Basic AND / OR search
8. Crash recovery through WAL replay
9. Storage/index consistency validation
10. Index rebuild from storage when validation fails
11. Unit + integration tests
12. Clean CLI: `add`, `index`, `search`, `stats`

### Tier 1 definition of done
A committed write survives a process crash, the engine recovers it on restart, the index is searchable, and consistency validation passes reproducibly.

### V1 data model
Documents are immutable/add-only.

No update, delete, or transaction support in v1.

---

## Tier 2 — ADD ONLY AFTER TIER 1 IS STABLE

1. TF-IDF ranking
2. Crash-fuzzing harness
3. Benchmark suite

### Tier 2 gate
Only start Tier 2 after the complete Tier 1 flow has been successfully demonstrated at least 3 times.

---

## Tier 3 — OPTIONAL ONLY IF FAR AHEAD

1. WAL checkpointing / compaction
2. Incremental indexing

If either feature threatens Tier 1 or Tier 2 stability, remove it immediately.

---

## Explicitly CUT

- BM25
- Cold-data compression
- Automatic corruption reconstruction
- Snapshot / restore
- SQL-like query language
- Update / delete
- Transactions
- Distributed storage
- Replication
- Custom filesystem
- Directory watching

---

## Claims discipline

Do NOT claim that the system automatically repairs arbitrary corruption.

Correct claim:
> Detects corruption through checksums and automatically recovers committed data after crashes through WAL replay.

---

## Core architecture

```text
DOCUMENT
   |
   v
WRITE REQUEST
   |
   v
  WAL -----> fsync() -----> COMMITTED
   |
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
        TF-IDF*
            |
            v
       RESULTS

CRASH
  |
  v
WAL REPLAY
  |
  v
STORAGE STATE
  |
  v
INDEX REBUILD / VALIDATION
  |
  v
CONSISTENCY PASS

* TF-IDF is Tier 2.
```

---

## Module ownership

| Module | Owner |
|---|---|
| Storage + WAL + checksums | |
| Tokenizer + inverted index + search + TF-IDF | |
| Recovery + consistency validation + tests | |
| Benchmarks + docs + CLI/demo integration | |

---

## Pre-kickoff work allowed

- Architecture/design
- Pseudocode
- Test-case design
- CLI/API specification
- Documentation templates
- Researching standard-library APIs
- Team/module planning
- AI prompt preparation

Do not write or commit project implementation code before kickoff.

---

## 72-hour checkpoints

### 0–12h
Storage + record format + WAL + checksums

### 12–24h
Tokenizer + inverted index + basic search

### 24–36h
Crash recovery + consistency validation + index rebuild

### 36–48h
Tests + crash fuzzing + TF-IDF

### 48–60h
Benchmarks + optional Tier 3 only if core is already stable

### 60–68h
README + STDLIB.md + architecture diagram + CLI polish

### 68–72h
Demo recording + clean-machine verification + final submission

The final 4 hours are a buffer, not feature-development time.
