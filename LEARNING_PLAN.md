# FORGE — Team Learning Plan

## Goal

We are four equal teammates building FORGE: a zero-dependency local data/search engine.

Before kickoff, **do not write project implementation code**. Use this time to understand the system, make design notes, and prepare.

> **Everyone learns the whole system. Each person then goes deeper into one area.**

---

# 1. Read these first

Everyone must read:

1. `SCOPE.md`
2. `WAL_FORMAT.md`
3. `STDLIB.md`
4. `ARCHITECTURE.md` when created
5. This file

Everyone should be able to explain:
- What FORGE does
- Why we are building it
- What the user can do
- How storage works
- How search works
- Why we use a WAL
- What happens during a crash
- How corruption is detected
- Why the index can be rebuilt
- What we are NOT building
- Why we use only the Python standard library

---

# 2. Common topics — EVERYONE studies these

## 2.1 Append-only storage

Learn:
- Persistent storage
- Append-only records
- Record layout
- DOC_ID, LENGTH, PAYLOAD, CHECKSUM
- Sequential file writes/reads
- Why v1 documents are immutable

Questions you must answer:
- Why not modify records in place?
- Why are documents immutable?
- How do we find the next record?

---

## 2.2 WAL — Write-Ahead Log ⭐⭐⭐⭐⭐

This is the most important common topic.

Learn:
- What a WAL is
- Why the WAL is written before main storage
- `flush()` vs `fsync()`
- The commit point
- Torn/incomplete writes
- WAL replay
- Recovery after a crash
- Why recovery stops at an invalid/incomplete tail

Be able to draw:

```text
WRITE
  ↓
WAL
  ↓
fsync()
  ↓
COMMITTED
  ↓
Storage + Index

CRASH
  ↓
Restart
  ↓
WAL replay
  ↓
Recover committed records
  ↓
Validate
```

---

## 2.3 Checksums / CRC32

Learn:
- What corruption means
- What a checksum does
- How verification works
- CRC32 conceptually
- Detection vs repair

FORGE only claims:

> Detect corruption through checksums.

We do **not** claim to reconstruct arbitrary corrupted data.

---

## 2.4 Tokenization

Learn:
- What tokens are
- Lowercasing
- Splitting on non-alphanumeric characters
- Basic stopword removal
- Important edge cases

Example:

```text
"Python, Storage & Search!"
          ↓
["python", "storage", "search"]
```

Do not study advanced NLP; it is outside our scope.

---

## 2.5 Inverted index ⭐⭐⭐⭐⭐

Learn:
- What an inverted index is
- Term → document IDs
- Posting lists
- Why it is faster than scanning every document
- AND queries
- OR queries
- Why the index is derived data
- Why it can be rebuilt

Example:

```text
python   → {1, 4, 9}
storage  → {2, 4}
search   → {1, 4, 7}
```

---

## 2.6 Search

Learn:
- Exact term matching
- AND / OR queries
- Multiple terms
- Unknown terms
- Empty queries
- Result ordering
- Query validation

Understand:

```text
MATCHING  → finds candidate documents
RANKING   → decides which candidates appear first
```

---

## 2.7 TF-IDF

Everyone should understand this, even if one teammate implements it.

Learn:
- Term Frequency
- Inverse Document Frequency
- Why common terms matter less
- Why rare terms matter more
- How document scores are calculated
- How results are ranked

Do **not** study BM25 for implementation; it is intentionally out of scope.

---

## 2.8 Crash recovery + consistency ⭐⭐⭐⭐⭐

Everyone must understand:

```text
Crash
 ↓
Open WAL
 ↓
Read records
 ↓
Validate
 ↓
Recover committed records
 ↓
Storage becomes source of truth
 ↓
Rebuild/validate index
 ↓
Consistency PASS
```

Learn:
- What a crash can interrupt
- What "committed" means
- What an incomplete WAL record means
- Why the index is rebuildable
- Storage vs derived index
- Consistency checks

---

## 2.9 Testing

Everyone should understand:
- Unit tests
- Integration tests
- Regression tests
- Edge cases
- Assertions
- Temporary test data
- Failure testing
- Reproducibility

The goal is:

> "We can repeatedly prove it works."

---

## 2.10 Crash fuzzing

Understand the concept:

```text
Start process
    ↓
Perform writes
    ↓
Kill at random point
    ↓
Restart
    ↓
Recover
    ↓
Validate
    ↓
Check acknowledged writes
```

Learn:
- Why random crash points matter
- What must always remain true
- What counts as failure
- Why this is stronger evidence than one manual crash

Do not implement it before kickoff.

---

## 2.11 Benchmarking

Everyone should understand:
- What a benchmark measures
- Indexing time
- Query latency
- Dataset size
- Memory usage
- Fair comparisons
- Reproducible measurements

Possible comparisons:
- FORGE
- `grep`
- SQLite FTS5

We report actual measurements; we do not cherry-pick claims.

---

## 2.12 Python standard library

Everyone should know what these are for:

### Files/storage
- `pathlib`
- `open`
- `os`
- `seek`
- `tell`
- `flush`
- `os.fsync`
- `struct`

### Integrity
- `zlib.crc32`
- `hashlib` conceptually, but CRC32 is not from `hashlib`

### Text/search
- strings
- `re`
- `collections`
- `math`

### CLI
- `argparse`

### Testing/processes
- `unittest`
- `tempfile`
- `subprocess`

### Other
- `logging`
- `json`
- `time`
- `random`

You do not need to memorize APIs. Understand their purpose and know where to look up exact signatures.

---

# 3. Specialization

Everyone studies everything above.

Then each person goes deeper into one area.

## Person 1 — Storage + WAL

Study deeply:
- Binary record layouts
- File offsets
- Sequential writes
- `flush()` vs `fsync()`
- WAL durability
- Torn writes
- Record parsing
- Recovery semantics
- Checkpointing conceptually

Create:

`LEARNING/01_STORAGE_WAL.md`

---

## Person 2 — Search + Index

Study deeply:
- Tokenization
- Inverted indexes
- Posting lists
- AND/OR queries
- Search complexity
- TF-IDF
- Ranking
- Search edge cases

Create:

`LEARNING/02_SEARCH_INDEX.md`

---

## Person 3 — Recovery + Testing

Study deeply:
- Failure scenarios
- Recovery invariants
- Storage/index consistency
- Unit/integration testing
- Crash testing
- Fuzzing concepts
- `subprocess`
- `tempfile`

Create:

`LEARNING/03_RECOVERY_TESTING.md`

---

## Person 4 — Standard Library + Benchmarks + Integration

Study deeply:
- Standard-library alternatives
- CLI with `argparse`
- Benchmark methodology
- `time.perf_counter`
- Memory measurement concepts
- Reproducibility
- Clean-environment testing
- How all modules connect

Create:

`LEARNING/04_STDLIB_BENCHMARKS.md`

This person is NOT merely the documentation person. They must understand the whole architecture too.

---

# 4. Format for every learning MD

Each specialization file should contain:

```markdown
# Topic

## 1. What is it?
Explain it in your own words.

## 2. Why does FORGE need it?
Explain its role in our project.

## 3. How does it work?
Explain the mechanism.

## 4. FORGE architecture
Draw a diagram.

## 5. Example
Give a simple example.

## 6. Python stdlib involved
List relevant modules/APIs.

## 7. Edge cases
What can go wrong?

## 8. Common mistakes
What should we avoid?

## 9. Questions I should be able to answer
Write and answer at least 5.

## 10. Resources
Add useful documentation/tutorials.

## 11. What I still don't understand
Be honest.
```

---

# 5. How to learn

Do not simply copy tutorials.

For each topic:

### Step 1 — Learn
Prefer:
1. Official Python documentation
2. High-quality technical documentation
3. Good engineering articles/videos

### Step 2 — Explain
Close the resource and explain it in your own words.

### Step 3 — Draw
Make a diagram. If you cannot draw the flow, learn it again.

### Step 4 — Apply
Before kickoff, stick to design/pseudocode and other explicitly allowed preparation. Do not turn learning into project implementation code.

### Step 5 — Teach
Explain the topic to the other three teammates.

---

# 6. Team teaching sessions

After notes are finished:

### Session 1 — Storage/WAL
Person 1 teaches:
> "What happens when we write a document?"

### Session 2 — Search
Person 2 teaches:
> "How does FORGE find and rank documents?"

### Session 3 — Recovery/testing
Person 3 teaches:
> "What happens if FORGE crashes halfway through a write?"

### Session 4 — Stdlib/benchmarks
Person 4 teaches:
> "How do we build and measure this using only the standard library?"

Everyone asks questions.

---

# 7. Final team exam

Before kickoff, every teammate should answer these without looking at notes.

### Architecture
1. What exactly are we building?
2. What is the user workflow?
3. What are the major modules?
4. Why is storage the source of truth?
5. Why is the index derived data?

### Storage
6. What is append-only storage?
7. What is our record format?
8. What does the checksum detect?
9. What does `fsync()` do?
10. What is the WAL commit point?

### Recovery
11. What happens during a crash?
12. What is a torn WAL record?
13. What happens when checksum validation fails?
14. Why do we stop at an invalid/incomplete WAL tail?
15. How do we validate consistency?

### Search
16. What is an inverted index?
17. Why is it faster than scanning every document?
18. How does AND search work?
19. How does OR search work?
20. What is matching vs ranking?

### Ranking
21. What is TF?
22. What is IDF?
23. Why do rare terms get more weight?
24. Why are we using TF-IDF instead of BM25?

### Quality
25. What is a unit test?
26. What is an integration test?
27. What is crash fuzzing?
28. What do our benchmarks measure?
29. What does zero-dependency mean?
30. What features are explicitly out of scope?

If someone cannot answer something, add it to the learning notes and teach it.

---

# 8. Definition of ready

Before kickoff:

- [ ] All four read `SCOPE.md`
- [ ] All four read `WAL_FORMAT.md`
- [ ] All four understand the complete architecture
- [ ] All four finish the common topics
- [ ] All four complete their specialization MD
- [ ] Each person teaches their specialization
- [ ] Everyone can answer the 30-question check
- [ ] Module ownership is agreed
- [ ] CLI commands are agreed
- [ ] Test cases are agreed
- [ ] No project implementation code has been written before kickoff

---

# 9. Learning folder

Create this in `forge-planning`:

```text
LEARNING/
│
├── README.md
├── 01_STORAGE_WAL.md
├── 02_SEARCH_INDEX.md
├── 03_RECOVERY_TESTING.md
└── 04_STDLIB_BENCHMARKS.md
```

`LEARNING/README.md` should track:
- Topic owner
- Progress
- Resources
- Date completed
- Questions remaining

---

# 10. Core architecture everyone must understand

```text
                 DOCUMENT
                    │
                    ▼
                  WAL
                    │
                 fsync
                    │
               COMMITTED
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
       STORAGE              INDEX
          │                   │
      checksum          inverted index
          │                   │
          └─────────┬─────────┘
                    ▼
                  SEARCH
                    │
                 TF-IDF
                    │
                    ▼
                RESULTS

                 💥 CRASH
                    │
                    ▼
                WAL REPLAY
                    │
                    ▼
          RECOVER COMMITTED DATA
                    │
                    ▼
             VALIDATE INDEX
```

The final goal is simple:

> **All four teammates should understand the whole system well enough to explain it, review it, and help debug it. Specialization means deeper knowledge, not exclusive knowledge.**
