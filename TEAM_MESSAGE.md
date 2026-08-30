Hey guys, I think we should lock our project now so we don't keep changing the idea.

Our final project is a zero-dependency local data/search engine.

In simple terms:
- Users can add/store documents locally.
- We store them persistently using our own append-only storage + WAL.
- Each record has an integrity checksum so corruption can be detected.
- We build an inverted index for fast search.
- Users can search using AND/OR terms.
- We'll add TF-IDF ranking after the core is stable.
- If the process crashes during a write, the WAL is replayed on restart and committed data is recovered.
- We validate that the storage and search index are consistent and can rebuild the index if needed.

Core demo:
1. Add/index documents
2. Search and show ranked results
3. Show stats
4. Kill the process during a write
5. Restart → WAL recovery
6. Search again and verify the data is still there
7. Show tests/benchmark results

Important: Python standard library only — no pip runtime dependencies.

For scope, we're NOT doing BM25, compression, snapshots, SQL, transactions, distributed/replication stuff, directory watching, or corruption reconstruction. If the core isn't rock-solid, we don't add extra features.

Before kickoff, let's only finalize architecture, module ownership, test cases, CLI/API design and docs. We won't write project implementation code before kickoff.
