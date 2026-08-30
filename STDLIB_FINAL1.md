# STDLIB.md — STANDARD LIBRARY LOG

## Purpose

Document every meaningful third-party package we could normally use and the Python standard-library functionality we use instead.

Only document substitutions that are actually used in the final project.

## Candidate substitutions

| # | Normally used | Python stdlib / built-in | Purpose | Actual usage / trade-off |
|---|---|---|---|---|
| 1 | Click/Typer | `argparse` | CLI parsing | |
| 2 | pytest | `unittest` | Automated tests | |
| 3 | CRC package | `zlib.crc32` | Record integrity | |
| 4 | search/index library | Hand-rolled inverted index | Search indexing | |
| 5 | database/ORM | `os` / `pathlib` / `io` + custom storage | Persistent storage | |
| 6 | rich/tabulate | `str.format` / f-strings | CLI output | |
| 7 | logging package | `logging` | Diagnostics | |
| 8 | file-locking package | `fcntl` or appropriate stdlib mechanism, if actually used | Coordination | |
| 9 | benchmark framework | `time` / `time.perf_counter` | Benchmarks | |
| 10 | process/test harness package | `subprocess` | Crash-fuzzing harness | |
| 11 | tokenizer/search helper | built-in string methods / `re` | Tokenization | |
| 12 | serialization helper | `json` / `struct`, if actually used | Record encoding | |

Do not fill entries just to reach a number. The bonus evidence must reflect the actual implementation.

## Package Killer

Target package: __________________

Why it is a fair comparison:
__________________________________

What we implemented:
__________________________________

What we deliberately did NOT implement:
__________________________________

Evidence of real-world usage/downloads:
__________________________________

## Reproducible build

Build command:
```text
__________________________________
```

Clean environment:
```text
__________________________________
```

Build/run verification:
```text
__________________________________
```

## Dependency proof

Final runtime dependency list:
```text
Python standard library only
```

Verify using a clean environment before submission.
