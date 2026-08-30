"""Subprocess crash-simulation test for the FORGE durability invariant.

Invariant under test:

    WAL fsync -> COMMITTED -> artificial crash -> restart -> WAL replay
    -> the committed document is recoverable.

Two crash points are covered:
  - before_storage: crash immediately after WAL fsync (before storage I/O)
  - after_storage:  crash after the storage write already succeeded

Both must still leave the document fully recoverable and consistent.
Uses only the Python standard library (subprocess, tempfile, os).
The child simulates a hard kill via os._exit, which bypasses all
cleanup, exactly like a process crash.
"""

import os
import subprocess
import sys
import tempfile
import unittest

from forge.recovery import recover, validate_consistency
from forge.storage import Storage
from forge.wal import scan_wal

_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'crash_helper.py')


class TestCrashRecovery(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.wal = os.path.join(self.tempdir.name, 'wal.bin')
        self.store = os.path.join(self.tempdir.name, 'store.bin')

    def _run_crash(self, doc_id, payload, mode):
        """Run the crash helper, then verify the committed doc recovers."""
        env = dict(os.environ)
        env['PYTHONPATH'] = 'src' + os.pathsep + env.get('PYTHONPATH', '')
        proc = subprocess.run(
            [sys.executable, _HELPER, self.wal, self.store,
             str(doc_id), payload, mode],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 3, f'child stderr: {proc.stderr}')
        self.assertIn(f'COMMITTED:{doc_id}:{payload}', proc.stdout)
        return proc

    def test_crash_before_storage_write(self):
        """Committed WAL write + crash before storage -> still recoverable."""
        doc_id, payload = 41, 'hello before storage crash'
        self._run_crash(doc_id, payload, 'before_storage')

        self.assertEqual(scan_wal(self.wal).records, [(doc_id, payload.encode())])
        with Storage(self.store) as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.completed)
            self.assertEqual(report.records_recovered, 1)
            self.assertEqual(storage.get(doc_id), payload.encode())
            self.assertTrue(validate_consistency(self.wal, storage).ok)

    def test_crash_after_storage_write(self):
        """Crash after storage write -> recovery must not duplicate."""
        doc_id, payload = 42, 'hello after storage crash'
        self._run_crash(doc_id, payload, 'after_storage')

        with Storage(self.store) as storage:
            report = recover(self.wal, storage)
            self.assertTrue(report.completed)
            self.assertEqual(report.records_skipped, 1)  # already applied
            self.assertEqual(len(storage), 1)             # no duplicate
            self.assertEqual(storage.get(doc_id), payload.encode())
            self.assertTrue(validate_consistency(self.wal, storage).ok)


if __name__ == '__main__':
    unittest.main()