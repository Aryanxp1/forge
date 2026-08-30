"""Phase 7 Part A: failure-case + CLI behavior tests.

Covers (deterministically, filesystem-isolated via tempfile):

- WAL write failure on a read-only file path (must surface OSError).
- Truncated storage tail healing on reopen.
- Malformed/garbage bytes after a valid record.
- Missing/non-existent data directory behavior for every subcommand.
- argparse argument errors and their documented exit codes.

Stdlib + existing forge modules only.
"""

import os
import tempfile
import unittest

from forge.cli import main as cli_main
from forge.storage import Storage
from forge.wal import WalWriter


class ReadOnlyWalFailureTests(unittest.TestCase):
    """A read-only WAL path must surface I/O failure, not be swallowed."""

    def test_wal_append_fails_on_readonly_file(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        wal_path = os.path.join(tmp.name, "wal.bin")
        with open(wal_path, "wb") as f:
            f.write(b"")
        os.chmod(wal_path, 0o444)
        try:
            with self.assertRaises(OSError):
                with WalWriter(wal_path) as w:
                    w.append(1, b"fail")
        finally:
            os.chmod(wal_path, 0o644)


class TruncatedStorageTests(unittest.TestCase):
    """Storage self-heals a torn tail on reopen (no crash, keeps valid docs)."""

    def test_reopen_heals_truncated_tail(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "docs.bin")
        with Storage(path) as s:
            s.append(1, b"first record here")
            s.append(2, b"second record here")
            s.append(3, b"third record here")
        full = os.path.getsize(path)
        with open(path, "r+b") as f:
            f.truncate(full - 10)  # cut into the last record
        with Storage(path) as s:
            self.assertEqual(sorted(s.doc_ids), [1, 2])
            self.assertEqual(s.get(1), b"first record here")
            self.assertEqual(s.get(2), b"second record here")

    def test_reopen_empty_storage(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "docs.bin")
        with Storage(path) as s:
            self.assertEqual(len(s), 0)

    def test_reopen_persists_prior_records(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "docs.bin")
        with Storage(path) as s:
            s.append(1, b"persist me")
            s.append(2, b"keep me too")
        with Storage(path) as s:
            self.assertEqual(sorted(s.doc_ids), [1, 2])
            self.assertEqual(s.get(2), b"keep me too")


class MalformedStorageTests(unittest.TestCase):
    """Garbage appended after a valid record is healed, valid record kept."""

    def test_garbage_after_valid_record(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "docs.bin")
        with Storage(path) as s:
            s.append(1, b"hello world")
        with open(path, "ab") as f:
            f.write(b"THIS IS NOT A FORGE RECORD BUT IT IS LONG ENOUGH")
        with Storage(path) as s:
            self.assertEqual(sorted(s.doc_ids), [1])
            self.assertEqual(s.get(1), b"hello world")


class MissingDataDirectoryTests(unittest.TestCase):
    """Every subcommand behaves deterministically with no data dir present."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = os.path.join(self.tmp.name, "does_not_exist")

    def _run(self, *argv):
        return cli_main(["--data-dir", self.data_dir, *argv])

    def test_add_missing_file(self):
        self.assertEqual(
            self._run("add", os.path.join(self.tmp.name, "missing.txt")), 1
        )

    def test_search_no_storage(self):
        self.assertEqual(self._run("search", "anything"), 1)

    def test_index_no_storage(self):
        self.assertEqual(self._run("index"), 0)

    def test_stats_no_storage(self):
        self.assertEqual(self._run("stats"), 0)

    def test_check_no_storage(self):
        self.assertEqual(self._run("check"), 0)


class CliArgumentErrorTests(unittest.TestCase):
    """argparse-driven argument errors use the documented exit codes."""

    def test_missing_subcommand_exits_2(self):
        code = cli_main(["--data-dir", tempfile.gettempdir()])
        self.assertEqual(code, 2)

    def test_search_requires_query(self):
        code = cli_main(["search"])
        self.assertEqual(code, 2)

    def test_invalid_subcommand_exits_2(self):
        code = cli_main(
            ["--data-dir", tempfile.gettempdir(), "bogus-command"]
        )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
