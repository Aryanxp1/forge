# FORGE — ARCHITECTURE.md

## 1. System overview

FORGE is a zero-dependency local data engine that:

- persistently stores documents;
- creates a derived inverted index;
- supports fast AND/OR search;
- ranks results with TF-IDF;
- detects corruption using per-record checksums;
- recovers committed data after crashes using a Write-Ahead Log (WAL);
- validates/rebuilds the derived index when necessary.

### Core principle

> **Storage is the source of truth. The search index is derived data.**

If the index is ever inconsistent, we can rebuild it from persistent storage.

---

# 2. High-level architecture

```text
                         USER
                          │
                          ▼
                    ┌──────────┐
                    │   CLI    │
                    └────┬─────┘
                         │
              ┌──────────┴──────────┐
              │                     │
             ADD                  SEARCH
              │                     │
              ▼                     ▼
        ┌───────────┐        ┌────────────┐
        │  STORAGE  │        │   SEARCH   │
        │   ENGINE  │        │   ENGINE   │
        └─────┬─────┘        └──────┬─────┘
              │                     │
              ▼                     ▼
             WAL              Inverted Index
              │                     │
              ▼                     ▼
          Persistent             Matching
           Records                  │
              │                  Ranking
              │                (TF-IDF)
              │                     │
              └──────────┬──────────┘
                         ▼
                      RESULTS


                 CRASH / RESTART
                         │
                         ▼
                    WAL REPLAY
                         │
                         ▼
                Recover committed data
                         │
                         ▼
                Validate / rebuild index
                         │
                         ▼
                  CONSISTENCY PASS
```

---

# 3. Main components

## 3.1 CLI

The CLI is the user's entry point.

Initial commands:

```text
forge add <file>
forge index <directory>
forge search "query"
forge stats
forge check
```

Keep the CLI small and predictable.

The CLI should call the engine modules rather than contain storage/search logic itself.

---

# 4. Storage engine

## Responsibility

The storage engine is responsible for:

- persistent document records;
- append-only writes;
- reading records;
- document IDs;
- record parsing;
- checksums;
- WAL interaction.

### Conceptual flow

```text
Document
   │
   ▼
Serialize record
   │
   ▼
Append to WAL
   │
   ▼
flush + fsync
   │
   ▼
Committed
   │
   ▼
Persistent storage
```

### V1 rule

Documents are immutable/add-only.

No update/delete/transaction support in the initial version.

---

# 5. WAL

## Responsibility

The Write-Ahead Log protects committed writes from process crashes.

### Write path

```text
Write request
     │
     ▼
Construct WAL record
     │
     ▼
Append to WAL
     │
     ▼
fsync()
     │
     ▼
COMMITTED
     │
     ├───────────────┐
     ▼               ▼
 Storage           Index
```

The durable commit point is the successful WAL `fsync`.

### Recovery path

```text
Process crashes
       │
       ▼
Process restarts
       │
       ▼
Open WAL
       │
       ▼
Read records sequentially
       │
       ▼
Validate record
       │
   ┌───┴────┐
 valid     invalid/incomplete
   │             │
   ▼             ▼
replay        stop at tail
   │
   ▼
Recover committed state
```

Do not implement clever forward resynchronization after an invalid tail.

---

# 6. Record integrity

Each persistent/WAL record contains integrity information.

Conceptually:

```text
+--------+--------+----------+--------+---------+
| MAGIC  | LENGTH | CHECKSUM | DOC_ID | PAYLOAD |
+--------+--------+----------+--------+---------+
```

The checksum allows FORGE to detect corruption.

### Important claim

FORGE:

> **detects corruption**

It does NOT claim to automatically reconstruct arbitrary corrupted data.

CRC32 can be implemented using Python's `zlib.crc32`.

---

# 7. Persistent storage

The storage file is append-oriented.

Conceptually:

```text
[Record 1][Record 2][Record 3][Record 4]...
```

Records can be scanned sequentially.

The storage layer should expose simple operations such as:

```text
add(document)
get(document_id)
scan()
```

Exact Python interfaces are finalized during implementation.

---

# 8. Search pipeline

The search engine operates on the derived index.

```text
Query
  │
  ▼
Tokenize
  │
  ▼
Normalize
  │
  ▼
Find matching terms
  │
  ▼
Candidate documents
  │
  ▼
AND / OR filtering
  │
  ▼
TF-IDF scoring
  │
  ▼
Rank
  │
  ▼
Results
```

---

# 9. Tokenizer

V1 tokenizer:

1. lowercase input;
2. split on non-alphanumeric characters;
3. remove basic stopwords;
4. return normalized tokens.

Example:

```text
"Python, Storage & Search!"
              ↓
["python", "storage", "search"]
```

No advanced NLP is required.

---

# 10. Inverted index

The index maps terms to documents containing those terms.

Example:

```text
python   → {1, 4, 9}
storage  → {2, 4}
search   → {1, 4, 7}
```

This avoids scanning every stored document for every search.

### Important architectural rule

The index is **derived data**.

Storage is the source of truth.

Therefore:

```text
Persistent storage
        │
        ▼
   rebuild index
        │
        ▼
   searchable index
```

---

# 11. Query processing

### AND

For:

```text
python AND storage
```

Conceptually:

```text
python  → {1,4,9}
storage → {2,4}

intersection
     ↓
   {4}
```

### OR

For:

```text
python OR storage
```

Conceptually:

```text
python  → {1,4,9}
storage → {2,4}

union
 ↓
{1,2,4,9}
```

---

# 12. Ranking

After matching candidate documents, FORGE can rank results using TF-IDF.

```text
Query
  ↓
Matching documents
  ↓
TF-IDF score
  ↓
Sort descending
  ↓
Ranked results
```

TF-IDF is Tier 2 and should only be added after the basic search/recovery system is stable.

BM25 is intentionally out of scope.

---

# 13. Crash recovery and consistency

Recovery must preserve the invariant:

> **Every acknowledged/committed write remains recoverable after a process crash.**

After WAL replay:

```text
Recovered storage
       │
       ▼
Rebuild / validate index
       │
       ▼
Consistency check
       │
   ┌───┴────┐
 PASS      FAIL
   │         │
   ▼         ▼
 Ready     Rebuild
```

The exact implementation of validation/rebuild is decided during the hackathon.

---

# 14. Testing architecture

Testing has several levels.

## Unit tests

Test individual components:

```text
record encoding
checksum
tokenizer
index
query parsing
TF-IDF
```

## Integration tests

Test complete flows:

```text
add → store → index → search
```

## Recovery tests

Test:

```text
write → crash → restart → recover
```

## Consistency tests

Test:

```text
storage ↔ index
```

## Crash fuzzing

Tier 2:

```text
random write point
       ↓
kill process
       ↓
restart
       ↓
recover
       ↓
validate
```

---

# 15. Benchmark architecture

Benchmarks should measure actual system behavior.

Potential measurements:

- indexing time;
- query latency;
- dataset size;
- memory usage;
- recovery time.

Potential comparisons:

```text
FORGE
grep
SQLite FTS5
```

The comparison must be fair and reproducible.

---

# 16. Module boundaries

Recommended conceptual modules:

```text
CLI
 │
 ▼
ENGINE
 ├───────────────┐
 ▼               ▼
STORAGE         SEARCH
 │               │
 ├── WAL         ├── Tokenizer
 ├── Records     ├── Index
 ├── Checksums   └── Ranking
 │
 ▼
RECOVERY
 │
 ├── WAL replay
 ├── Consistency validation
 └── Index rebuild
```

The exact folder/file structure is intentionally left flexible until kickoff.

---

# 17. Data flow

## Add document

```text
User
 ↓
CLI
 ↓
Engine
 ↓
WAL
 ↓
fsync
 ↓
Committed
 ↓
Storage
 ↓
Tokenizer
 ↓
Index
```

## Search

```text
User query
 ↓
CLI
 ↓
Engine
 ↓
Tokenizer
 ↓
Inverted index
 ↓
AND / OR matching
 ↓
TF-IDF ranking
 ↓
Results
```

## Crash recovery

```text
Crash
 ↓
Restart
 ↓
Read WAL
 ↓
Validate records
 ↓
Replay valid committed records
 ↓
Storage state
 ↓
Rebuild/validate index
 ↓
Consistency PASS
```

---

# 18. Design principles

### Principle 1 — Correctness before features

A working core is more valuable than a large broken feature list.

### Principle 2 — Storage is truth

The index can be rebuilt.

### Principle 3 — Simple recovery

Prefer deterministic recovery over clever recovery.

### Principle 4 — No unnecessary complexity

No distributed systems, replication, SQL, transactions, compression, or automatic corruption reconstruction.

### Principle 5 — Standard library only

Runtime implementation should use Python's standard library.

### Principle 6 — Prove claims

Use automated tests, crash fuzzing, consistency checks, and benchmarks to support claims.

---

# 19. Explicit non-goals

FORGE v1 will NOT implement:

- BM25
- cold-data compression
- automatic corruption reconstruction
- snapshots/restore
- SQL-like query language
- updates/deletes
- transactions
- distributed storage
- replication
- custom filesystem
- directory watching

These are intentionally excluded to keep the 72-hour implementation stable.

---

# 20. Final architecture in one sentence

> **FORGE writes documents durably through a WAL, stores them in an append-oriented format, builds a derived inverted index for search, ranks matches with TF-IDF, and recovers committed data after crashes while validating index consistency.**
