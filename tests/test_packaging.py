"""Smoke tests for FORGE packaging (pyproject.toml / install verification).

These tests verify that the package is properly importable and that the
console-script entry point resolves after installation. They do NOT
require PYTHONPATH — they assume `pip install .` (or `-e .`) has been run.
"""

import importlib
import importlib.metadata
import subprocess
import sys
import unittest

from forge import __version__


class TestPackageImport(unittest.TestCase):
    """The forge package must be importable without PYTHONPATH."""

    def test_import_forge(self):
        importlib.import_module("forge")

    def test_import_all_modules(self):
        """Every source module imports cleanly (no missing deps)."""
        for mod in [
            "forge.cli",
            "forge.records",
            "forge.checksum",
            "forge.wal",
            "forge.storage",
            "forge.recovery",
            "forge.tokenizer",
            "forge.index",
            "forge.search",
            "forge.ranking",
            "forge.consistency",
        ]:
            importlib.import_module(mod)

    def test_version(self):
        self.assertEqual(__version__, "0.1.0")
        # Package metadata (from pyproject.toml) must match.
        self.assertEqual(importlib.metadata.version("forge"), "0.1.0")


class TestEntryPoint(unittest.TestCase):
    """The `forge` console script must resolve and run."""

    def test_console_script_help(self):
        """`forge --help` must succeed without PYTHONPATH."""
        result = subprocess.run(
            [sys.executable, "-m", "forge", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("forge", result.stdout.lower())

    def test_console_script_ranked_flag(self):
        """`forge search --help` must advertise --ranked."""
        result = subprocess.run(
            [sys.executable, "-m", "forge", "search", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--ranked", result.stdout)


if __name__ == "__main__":
    unittest.main()
