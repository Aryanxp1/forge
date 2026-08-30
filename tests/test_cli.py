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

    def _run_capture(self, *argv):
        """Invoke the CLI in-process, capturing stdout.

        Returns (exit_code, stdout_text).
        """
        import sys
        from io import StringIO
        old_out = sys.stdout
        buf = StringIO()
        sys.stdout = buf
        try:
            code = main(["--data-dir", self.data_dir, *argv])
        finally:
            sys.stdout = old_out
        return code, buf.getvalue()

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

    # ------------------------------------------------------------ ranked search
    def _add(self, name, text):
        """Write a doc file and add it; return the CLI exit code."""
        p = os.path.join(self.data_dir, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return self._run("add", p)

    def test_ranked_flag_returns_0(self):
        self.assertEqual(self._add("a.txt", "python search engine"), 0)
        code, out = self._run_capture("search", "python", "--ranked")
        self.assertEqual(code, 0)
        self.assertIn("ranked", out)
        self.assertIn("Score", out)

    def test_ranked_and_shows_scores(self):
        self._add("a.txt", "python search engine")
        self._add("b.txt", "python language")
        code, out = self._run_capture("search", "python search", "--ranked")
        self.assertEqual(code, 0)
        # Score column header present and at least one numeric score
        self.assertIn("Score", out)
        self.assertRegex(out, r"\d+\s+\d+\.\d+\s+doc\s+\d+")

    def test_ranked_or_mode(self):
        self._add("a.txt", "python search engine")
        self._add("b.txt", "storage basics")
        code, out = self._run_capture(
            "search", "python storage", "--or", "--ranked"
        )
        self.assertEqual(code, 0)
        self.assertIn("OR ranked", out)
        self.assertIn("Score", out)

    def test_ranked_tie_break_by_doc_id(self):
        # Two docs with identical single-term content -> equal scores.
        # Lower doc ID must appear first (deterministic tie-breaker).
        self._add("a.txt", "python")
        self._add("b.txt", "python")
        code, out = self._run_capture("search", "python", "--ranked")
        self.assertEqual(code, 0)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        # Find the two result lines (after the header) and check doc order
        doc_lines = [ln for ln in lines if "doc" in ln and "Score" not in ln]
        self.assertGreaterEqual(len(doc_lines), 2)
        ids = []
        for ln in doc_lines[:2]:
            ids.append(int(ln.strip().split("doc")[1].split(":")[0].strip()))
        self.assertEqual(ids, sorted(ids))

    def test_unranked_search_unchanged(self):
        """Existing default search output must NOT contain 'Score'."""
        self._add("a.txt", "python search engine")
        code, out = self._run_capture("search", "python search")
        self.assertEqual(code, 0)
        self.assertIn("AND results", out)
        self.assertNotIn("Score", out)
        self.assertNotIn("ranked", out)

    def test_ranked_unknown_query(self):
        self._add("a.txt", "python search")
        code, out = self._run_capture("search", "nonexistent", "--ranked")
        self.assertEqual(code, 0)
        self.assertIn("(no matches)", out)

    def test_ranked_empty_query(self):
        self._add("a.txt", "python search")
        code, out = self._run_capture("search", "", "--ranked")
        self.assertEqual(code, 0)
        self.assertIn("(no matches)", out)

    def test_ranked_empty_and_unranked_empty_match(self):
        """Ranked and unranked both return (no matches) for empty query."""
        self._add("a.txt", "python search")
        _, ranked_out = self._run_capture("search", "", "--ranked")
        _, plain_out = self._run_capture("search", "")
        self.assertIn("(no matches)", ranked_out)
        self.assertIn("(no matches)", plain_out)


if __name__ == "__main__":
    unittest.main()
