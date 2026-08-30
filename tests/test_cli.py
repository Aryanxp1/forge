"""Tests for the FORGE command-line interface (``python -m forge``).

All tests use an isolated temporary data directory and invoke the CLI
through the in-process ``forge.cli.main`` entry point (no subprocess
spawning), so they are fast and deterministic.
"""

import os
import tempfile
import unittest

from forge.cli import main, _paths, DEFAULT_DATA_DIR, STORAGE_FILE, WAL_FILE
from forge.storage import Storage
from forge.wal import scan_wal


class CliTestCase(unittest.TestCase):
    """Shared setup: an isolated temp data directory for each test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = self.tmp.name

    def _run(self, *argv):
        """Invoke the CLI in-process and return its exit code."""
        return main(["--data-dir", self.data_dir, *argv])

    def _docs(self, count):
        """Write `count` numbered doc files and add each via the CLI."""
        for i in range(count):
            p = os.path.join(self.data_dir, f"doc{i}.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"python doc {i}\n")
            self.assertEqual(self._run("add", p), 0)

    def _store_path(self):
        return os.path.join(self.data_dir, STORAGE_FILE)

    # ------------------------------------------------------------------ add
    def test_add_one_file(self):
        f = os.path.join(self.data_dir, "hello.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("python storage search")
        self.assertEqual(self._run("add", f), 0)
        with Storage(self._store_path()) as s:
            self.assertEqual(len(s), 1)
            payload = s.get(1)
        self.assertEqual(payload, b"python storage search")

    def test_add_assigns_monotonic_ids(self):
        self._docs(3)
        with Storage(self._store_path()) as s:
            self.assertEqual(sorted(s.doc_ids), [1, 2, 3])

    def test_add_missing_file_exits_1(self):
        self.assertEqual(self._run("add", "does_not_exist.txt"), 1)

    def test_add_invalid_command_exits_2(self):
        # argparse uses exit code 2 for invalid usage / invalid subcommand
        # choices (per the documented "Exit codes: 2 runtime/usage error").
        self.assertEqual(self._run("bogus-command"), 2)

    # ---------------------------------------------------------------- index
    def test_index_reports_stats(self):
        self._docs(2)
        self.assertEqual(self._run("index"), 0)

    def test_index_no_storage(self):
        self.assertEqual(self._run("index"), 0)

    # ---------------------------------------------------------------- search
    def test_search_and_mode(self):
        f = os.path.join(self.data_dir, "d.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("python search engine")
        with open(os.path.join(self.data_dir, "d2.txt"), "w", encoding="utf-8") as fh:
            fh.write("python language")
        self.assertEqual(self._run("add", f), 0)
        self.assertEqual(self._run("add", os.path.join(self.data_dir, "d2.txt")), 0)
        # AND: doc with both "python" and "search"
        code = self._run("search", "python search")
        self.assertEqual(code, 0)

    def test_search_or_mode(self):
        self._docs(2)
        self.assertEqual(self._run("search", "-o", "python"), 0)

    def test_search_no_storage_exits_nonzero(self):
        self.assertEqual(self._run("search", "anything"), 1)

    # ---------------------------------------------------------------- stats
    def test_stats_empty(self):
        self.assertEqual(self._run("stats"), 0)

    def test_stats_after_adds(self):
        self._docs(3)
        self.assertEqual(self._run("stats"), 0)

    # ---------------------------------------------------------------- check
    def test_check_consistent(self):
        self._docs(2)
        self.assertEqual(self._run("check"), 0)

    def test_check_no_storage(self):
        self.assertEqual(self._run("check"), 0)

    # ---------------------------------------------------------------- paths
    def test_default_data_dir(self):
        self.assertTrue(DEFAULT_DATA_DIR.endswith("forge_data"))
        store, wal, nxt = _paths(DEFAULT_DATA_DIR)
        self.assertEqual(store, os.path.join(DEFAULT_DATA_DIR, "forge.db"))
        self.assertEqual(wal, os.path.join(DEFAULT_DATA_DIR, "forge.wal"))

    # ---------------------------------------------------------------- help
    def test_help_exits_0(self):
        import sys
        from io import StringIO
        old_out = sys.stdout
        sys.stdout = StringIO()
        try:
            self.assertEqual(main(["--help"]), 0)
        finally:
            sys.stdout = old_out


if __name__ == "__main__":
    unittest.main()
