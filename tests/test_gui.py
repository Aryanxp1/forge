"""Tests for the optional FORGE GUI (forge_gui.py at the repository root).

The GUI is a thin tkinter/ttk view over the existing FORGE core. These
tests cover the backend wrappers (all actual engine interaction, no widget
code) plus a widget-level smoke test that skips gracefully without a display.

Standard library only: unittest, tempfile, os, sys, re.
"""

import os
import re
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import forge_gui  # noqa: E402

TEXT_A = "python storage engine"
TEXT_B = "python search index"
TEXT_C = "storage search wal"


class GuiBackendTestCase(unittest.TestCase):
    """Backend wrappers exercise the real FORGE core end to end."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = self.tmp.name
        paths = []
        for name, text in (("a.txt", TEXT_A), ("b.txt", TEXT_B), ("c.txt", TEXT_C)):
            path = os.path.join(self.tmp.name, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            paths.append(path)
        self.paths = paths

    def test_add_and_list_documents(self):
        forge_gui.add_files(self.data_dir, self.paths)
        docs = forge_gui.list_documents(self.data_dir)
        self.assertEqual([d["id"] for d in docs], [1, 2, 3])
        self.assertEqual(docs[0]["text"], TEXT_A)

    def test_search_and_vs_or(self):
        forge_gui.add_files(self.data_dir, self.paths)
        and_hits = forge_gui.run_search(self.data_dir, "python search", "and", False)
        or_hits = forge_gui.run_search(self.data_dir, "python search", "or", False)
        self.assertEqual([d["id"] for d in and_hits], [2])   # only doc 2 has both
        self.assertEqual([d["id"] for d in or_hits], [1, 2, 3])  # any of the two terms

    def test_ranked_search_scores_and_order(self):
        forge_gui.add_files(self.data_dir, self.paths)
        results = forge_gui.run_search(self.data_dir, "storage wal", "or", True)
        self.assertEqual([d["id"] for d in results], [3, 1])  # rare "wal" ranks doc 3 first
        self.assertIsNotNone(results[0]["score"])
        scores = [d["score"] for d in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_unranked_has_no_scores(self):
        forge_gui.add_files(self.data_dir, self.paths)
        results = forge_gui.run_search(self.data_dir, "storage", "and", False)
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(all(d["score"] is None for d in results))

    def test_stats_after_adds(self):
        forge_gui.add_files(self.data_dir, self.paths)
        stats = forge_gui.get_stats(self.data_dir)
        self.assertEqual(stats["docs"], 3)
        self.assertGreater(stats["terms"], 0)
        self.assertGreater(stats["storage_size"], 0)
        self.assertEqual(stats["wal_records"], 3)
        self.assertEqual(stats["wal_status"], "ok")
        self.assertEqual(stats["next_id"], 3)  # counter file holds the last allocated ID

    def test_stats_empty_directory(self):
        stats = forge_gui.get_stats(self.data_dir)
        self.assertEqual(stats["docs"], 0)
        self.assertIsNone(stats["storage_size"])
        self.assertIsNone(stats["wal_records"])

    def test_consistency_check_ok(self):
        forge_gui.add_files(self.data_dir, self.paths)
        report = forge_gui.run_check(self.data_dir)
        self.assertTrue(report["ok"])
        self.assertIn("consistent", report["detail"])

    def test_consistency_check_without_storage(self):
        report = forge_gui.run_check(self.data_dir)
        self.assertTrue(report["ok"])


class GuiImportAuditTestCase(unittest.TestCase):
    """The GUI must not introduce any third-party runtime import."""

    def test_no_third_party_imports(self):
        with open(os.path.join(_ROOT, "forge_gui.py"), encoding="utf-8") as fh:
            source = fh.read()
        roots = set()
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from "):
                roots.add(stripped.split()[1].split(".")[0])
            elif stripped.startswith("import "):
                for token in stripped[7:].split(","):
                    roots.add(token.strip().split(".")[0].split()[0])
        stdlib = set(getattr(sys, "stdlib_module_names", ())) or {
            "argparse", "os", "re", "sys", "tkinter"}
        stdlib |= {"tkinter", "forge"}
        bad = roots - stdlib
        self.assertEqual(bad, set(), "third-party imports found: %s" % sorted(bad))


class GuiWindowTestCase(unittest.TestCase):
    """Widget-level smoke tests (skip cleanly when no display is available)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = self.tmp.name
        paths = []
        for name, text in (("a.txt", TEXT_A), ("b.txt", TEXT_B), ("c.txt", TEXT_C)):
            path = os.path.join(self.tmp.name, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            paths.append(path)
        self.paths = paths
        self.app = None

    def _make_app(self):
        if forge_gui.tk is None:
            self.skipTest("tkinter is not available")
        try:
            self.app = forge_gui.ForgeApp(self.data_dir)
        except forge_gui.tk.TclError as exc:
            self.skipTest("no display available: %s" % exc)
        self.addCleanup(self.app.root.destroy)

    def test_window_title(self):
        self._make_app()
        self.assertIn("FORGE", self.app.root.title())

    def test_window_workflow(self):
        """add -> search (ranked) -> stats -> consistency check through widgets."""
        self._make_app()
        forge_gui.add_files(self.data_dir, self.paths)
        self.app.refresh()
        self.assertEqual(len(self.app.doc_tree.get_children()), 3)

        self.app.query_var.set("storage wal")
        self.app.mode_var.set("or")
        self.app.ranked_var.set(True)
        self.app._search()
        rows = self.app.res_tree.get_children()
        self.assertEqual(len(rows), 2)
        first = self.app.res_tree.item(rows[0], "values")
        self.assertEqual(first[1], "3")          # rare term ranks doc 3 first
        self.assertNotEqual(first[2], "")        # score column filled when ranked

        self.assertEqual(self.app.stat_labels["docs"].cget("text"), "3")

        self.app._check()
        self.assertIn("consistent", self.app.check_label.cget("text"))


if __name__ == "__main__":
    unittest.main()