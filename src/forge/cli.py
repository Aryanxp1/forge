"""Command-line interface for FORGE.

For the V1 engine, the data directory holds two files plus a
generated-id counter (all optional; absent files are created on first
use):

    <data>/forge.db        - append-only persistent document storage
    <data>/forge.wal       - durable write-ahead log (fsync commit point)
    <data>/forge.next_id   - next doc-ID counter (created on first `add`)

Commands:

    add <file>     Read text from <file> and append it as a committed document.
    index <dir>    Build/rebuild an index against <dir> (report term stats).
    search "q"     Search indexed documents (AND by default; -o for OR).
    stats          Show storage + WAL statistics.
    check          Validate storage/index consistency (no writes).

Exit codes:
    0  success
    1  usage / argument error
    2  runtime / I/O / consistency error

Run:  PYTHONPATH=src python -m forge <command> ...

Only the Python standard library is used.
"""

import argparse
import os
import sys
from typing import Optional, Tuple

from .index import InvertedIndex
from .storage import Storage, StorageError
from .wal import WalWriter, scan_wal
from .recovery import recover
from .consistency import rebuild_index, validate_consistency, IndexConsistencyReport
from .search import search, MODE_AND, MODE_OR
from .ranking import search_ranked, score_document
from .tokenizer import tokenize

DEFAULT_DATA_DIR = os.path.join(os.getcwd(), "forge_data")
STORAGE_FILE = "forge.db"
WAL_FILE = "forge.wal"
NEXT_ID_FILE = "forge.next_id"


class CliError(Exception):
    """Raised on user-facing command failures (exits with code 1)."""


def _paths(data_dir: str) -> Tuple[str, str, str]:
    """Resolve the three well-known file paths for a data directory."""
    return (
        os.path.join(data_dir, STORAGE_FILE),
        os.path.join(data_dir, WAL_FILE),
        os.path.join(data_dir, NEXT_ID_FILE),
    )


def _next_id(data_dir: str) -> int:
    """Return the next doc ID, allocating atomically via a counter file.

    The counter is incremented and persisted as a single line so repeated
    `add` invocations yield monotonically increasing IDs even across
    restarts. The file is created on first use.
    """
    store_path, wal_path, id_path = _paths(data_dir)
    if os.path.exists(id_path):
        with open(id_path, "r", encoding="utf-8") as f:
            cur = int(f.read().strip() or "0")
    else:
        cur = 0
    nxt = cur + 1
    os.makedirs(data_dir, exist_ok=True)
    tmp = id_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(str(nxt))
    try:
        os.replace(tmp, id_path)
    except OSError:
        if os.path.exists(tmp):
            os.replace(tmp, id_path)
    return nxt


def _read_text(path: str) -> str:
    """Read a file as UTF-8 text."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_index(data_dir: str) -> InvertedIndex:
    """Rebuild the in-memory index from storage (derived data)."""
    store_path, _, _ = _paths(data_dir)
    if not os.path.exists(store_path):
        return InvertedIndex()
    with Storage(store_path) as storage:
        return rebuild_index(storage)


def _print_report(label: str, report) -> None:
    """Print a dataclass-style report one key per line."""
    print(label)
    if hasattr(report, "_asdict"):
        items = report._asdict()
    elif hasattr(report, "__dict__"):
        items = {k: v for k, v in report.__dict__.items() if not k.startswith("_")}
    else:
        items = {"": report}
    for k, v in items.items():
        print(f"  {k}: {v}")
    print()


def cmd_add(args: argparse.Namespace) -> int:
    """Add a document file as a new committed storage record."""
    data_dir = args.data_dir
    file_path = args.file
    if not os.path.isfile(file_path):
        raise CliError(f"file not found: {file_path}")
    try:
        text = _read_text(file_path)
    except OSError as exc:
        raise CliError(f"cannot read {file_path}: {exc}") from exc

    store_path, wal_path, _ = _paths(data_dir)
    doc_id = _next_id(data_dir)
    payload = text.encode("utf-8")

    # 1) WAL: durable commit point. MUST fsync before the storage write.
    try:
        with WalWriter(wal_path) as wal:
            wal.append(doc_id, payload)
    except OSError as exc:
        raise CliError(f"WAL write failed for doc {doc_id}: {exc}") from exc

    # 2) Storage: derived-side write (WAL is the durable copy).
    try:
        with Storage(store_path) as storage:
            storage.append(doc_id, payload)
    except StorageError as exc:
        raise CliError(f"storage write failed for doc {doc_id}: {exc}") from exc

    print(f"added doc {doc_id} ({len(payload)} bytes) from {file_path}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    """Build/rebuild the index from storage and report term stats."""
    data_dir = args.data_dir
    store_path, _, _ = _paths(data_dir)
    if not os.path.exists(store_path):
        print("no documents indexed yet (storage file does not exist)")
        return 0
    with Storage(store_path) as storage:
        index = rebuild_index(storage)
    print(f"indexed {index.document_count()} documents, {index.term_count()} terms")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Search indexed documents (AND by default; -o for OR).

    With --ranked, results are ordered by descending TF-IDF score with
    document ID as the tie-breaker, and a score column is shown.
    """
    data_dir = args.data_dir
    store_path, _, _ = _paths(data_dir)
    if not os.path.exists(store_path):
        print("no documents indexed (storage file does not exist)")
        return 1
    index = _load_index(data_dir)
    mode = MODE_OR if args.or_mode else MODE_AND
    op = "OR" if mode == MODE_OR else "AND"

    if args.ranked:
        results = search_ranked(index, args.query, mode=mode)
        print(f"{op} ranked results for: {args.query!r}")
        if not results:
            print("  (no matches)")
            return 0
        terms = tokenize(args.query)
        print(f"  {'Rank':<6}{'Score':<12}Document")
        with Storage(store_path) as storage:
            for rank, doc_id in enumerate(results, 1):
                score = score_document(index, doc_id, terms)
                try:
                    payload = storage.get(doc_id)
                except StorageError:
                    payload = b""
                preview = payload.decode("utf-8", errors="replace")[:80]
                print(f"  {rank:<6}{score:<12.4f}doc {doc_id}: {preview}")
        return 0

    # Unranked path (default): deterministic doc-ID order, unchanged.
    results = search(index, args.query, mode=mode)
    print(f"{op} results for: {args.query!r}")
    if not results:
        print("  (no matches)")
    else:
        with Storage(store_path) as storage:
            for doc_id in results:
                try:
                    payload = storage.get(doc_id)
                except StorageError:
                    payload = b""
                preview = payload.decode("utf-8", errors="replace")[:120]
                print(f"  doc {doc_id}: {preview}")
    return 0



def cmd_stats(args: argparse.Namespace) -> int:
    """Print storage + WAL statistics."""
    data_dir = args.data_dir
    store_path, wal_path, _ = _paths(data_dir)
    print("FORGE statistics")

    if os.path.exists(store_path):
        store_size = os.path.getsize(store_path)
        with Storage(store_path) as storage:
            doc_count = len(storage)
            doc_ids = sorted(storage.doc_ids)
            if doc_ids:
                min_id, max_id = doc_ids[0], doc_ids[-1]
            else:
                min_id = max_id = None
        print(f"  storage: {store_path}")
        print(f"    size: {store_size} bytes")
        print(f"    documents: {doc_count}")
        print(f"    doc id range: {min_id} .. {max_id}")
    else:
        print(f"  storage: {store_path} (not created)")
        print("    documents: 0")

    if os.path.exists(wal_path):
        wal_size = os.path.getsize(wal_path)
        scan = scan_wal(wal_path)
        print(f"  wal: {wal_path}")
        print(f"    size: {wal_size} bytes")
        print(f"    valid records: {len(scan.records)}")
        print(f"    status: {scan.status}")
    else:
        print(f"  wal: {wal_path} (not created)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Validate storage/index consistency (no writes performed)."""
    data_dir = args.data_dir
    store_path, _, _ = _paths(data_dir)
    if not os.path.exists(store_path):
        print("no storage to check (storage file does not exist)")
        return 0
    with Storage(store_path) as storage:
        index = rebuild_index(storage)
        report: IndexConsistencyReport = validate_consistency(storage, index)
    _print_report("Consistency report (storage <-> index):", report)
    if report.ok:
        print("ok: index is consistent with storage")
        return 0
    print("FAIL: index is INCONSISTENT with storage")
    return 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Zero-dependency local data engine: durable storage, "
        "WAL crash recovery, and derived-index search.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  add <file>   Append a file's text content as a committed document.\n"
            "  index <dir>  Build/rebuild the derived index from storage.\n"
            "  search \"q\"   Search indexed documents (AND by default; -o for OR).\n"
            "  stats        Show storage + WAL statistics.\n"
            "  check        Validate storage/index consistency (no writes).\n"
            "\nExit codes: 0 success, 1 usage/argument error, 2 runtime error.\n"
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help="data directory (default: ./forge_data)",
    )
    sub = parser.add_subparsers(dest="command", metavar="command", required=True)

    p_add = sub.add_parser(
        "add", help="Append a file's text content as a committed document."
    )
    p_add.add_argument("file", metavar="FILE", help="path to a text file to index")
    p_add.set_defaults(func=cmd_add)

    p_idx = sub.add_parser(
        "index",
        help="Build/rebuild the derived index from storage and report term stats.",
    )
    p_idx.set_defaults(func=cmd_index)

    p_search = sub.add_parser(
        "search", help="Search indexed documents (AND by default; use -o for OR)."
    )
    p_search.add_argument("query", metavar="QUERY", help="search query text")
    p_search.add_argument(
        "-o",
        "--or",
        dest="or_mode",
        action="store_true",
        help="use OR semantics instead of the default AND",
    )
    p_search.add_argument(
        "--ranked",
        action="store_true",
        help="rank results by TF-IDF score (higher is better)",
    )
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser("stats", help="Show storage + WAL statistics.")
    p_stats.set_defaults(func=cmd_stats)

    p_check = sub.add_parser(
        "check", help="Validate storage/index consistency (no writes)."
    )
    p_check.set_defaults(func=cmd_check)
    return parser


def main(argv: Optional[list] = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.func(args)
    except SystemExit as code:
        # argparse raises SystemExit on --help (0) and on argument errors (2).
        # Translate it into a status code so callers (and tests) get a plain
        # return value instead of an exception propagating through main().
        status = code.code if isinstance(code.code, int) else 2
        if isinstance(code.code, int) and status != 0:
            print(f"error: invalid usage", file=sys.stderr)
        return status
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except StorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc.filename or exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
