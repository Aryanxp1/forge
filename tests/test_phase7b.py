"""Phase 7 Part B: subprocess invocation + recovery consistency tests.

Covers:
- `python -m forge` parity with the in-process CLI entry point.
- Recovery idempotency (re-running recover must not duplicate docs).
- Recovery followed by storage<->index consistency validation.

Stdlib + existing forge modules only.
"""

import os
import subprocess
import sys
import tempfile
import unittest

from forge.storage import Storage
from forge.wal import WalWriter
from forge.recovery import recover
from forge.consistency import rebuild_index, validate_consistency


class PythonModuleInvocationTests(unittest.TestCase):
    """`python -m forge` must behave identically to the CLI entry point."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = self.tmp.name
        self.src_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "src")
        )

    def _py(self, *argv):
        env = dict(os.environ)
        env["PYTHONPATH"] = self.src_dir
        proc = subprocess.run(
            [sys.executable, "-m", "forge", "--data-dir", self.data_dir, *argv],
            capture_output=True, text=True, env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_module_help(self):
        code, out, _err = self._py("--help")
        self.assertEqual(code, 0)
        self.assertIn("forge", out)

    def test_module_no_subcommand_exits_2(self):
        code, _out, _err = self._py()
        self.assertEqual(code, 2)

    def test_module_add_stats_search(self):
        f = os.path.join(self.data_dir, "doc.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("python subprocess module")
        code, out, _err = self._py("add", f)
        self.assertEqual(code, 0, out)
        code, out, _err = self._py("stats")
        self.assertEqual(code, 0, out)
        self.assertIn("documents: 1", out)
        code, out, _err = self._py("search", "python subprocess")
        self.assertEqual(code, 0, out)
        self.assertIn("doc 1", out)


class RecoveryConsistencyTests(unittest.TestCase):
    """Recovery idempotency + recovery-then-consistency (in-process)."""

    def test_recover_is_idempotent(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        wal = os.path.join(tmp.name, "wal.bin")
        store = os.path.join(tmp.name, "store.bin")
        with WalWriter(wal) as w:
            w.append(1, b"python one")
            w.append(2, b"python two")
        with Storage(store) as s:
            report1 = recover(wal, s)
        self.assertTrue(report1.completed)
        with Storage(store) as s:
            self.assertEqual(sorted(s.doc_ids), [1, 2])
        with Storage(store) as s:
            report2 = recover(wal, s)  # second recovery must not duplicate
        with Storage(store) as s:
            self.assertEqual(sorted(s.doc_ids), [1, 2])
            self.assertEqual(len(s), 2)

    def test_recovery_then_consistency_ok(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        wal = os.path.join(tmp.name, "wal.bin")
        store = os.path.join(tmp.name, "store.bin")
        with WalWriter(wal) as w:
            w.append(1, b"python storage search")
            w.append(2, b"storage basics")
        with Storage(store) as s:
            recover(wal, s)
        with Storage(store) as s:
            index = rebuild_index(s)
            report = validate_consistency(s, index)
        self.assertTrue(report.ok, report)


if __name__ == "__main__":
    unittest.main()
