"""FORGE GUI - optional zero-dependency desktop interface.

A thin tkinter/ttk front end over the existing FORGE core. It contains no
storage, WAL, tokenizer, index, search, ranking or recovery logic; every
operation delegates to the forge.* modules and commits documents through the
same path as the CLI (forge.cli._next_id + WalWriter + Storage). Runs with the
standard library only and is NOT part of the official dist/forge.pyz artifact.

Run:  python forge_gui.py [--data-dir DIR]
"""

import argparse
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_SRC):
    sys.path.insert(0, _SRC)

from forge.cli import _next_id, _paths
from forge.consistency import rebuild_index, validate_consistency
from forge.ranking import score_document, search_ranked
from forge.search import MODE_AND, MODE_OR, search as forge_search
from forge.storage import Storage
from forge.tokenizer import tokenize
from forge.wal import WalWriter, scan_wal

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = filedialog = messagebox = ttk = None

DEFAULT_DATA_DIR = os.path.join(os.getcwd(), "forge_data")


# ------------------------------------------------------------ backend
# Thin, testable wrappers over the FORGE core. No widget code lives here.

def add_files(data_dir, paths):
    """Commit each text file via the real FORGE write path (WAL then storage)."""
    store_path, wal_path, _ = _paths(data_dir)
    added = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            payload = fh.read().encode("utf-8")
        doc_id = _next_id(data_dir)
        with WalWriter(wal_path) as wal:
            wal.append(doc_id, payload)
        with Storage(store_path) as storage:
            storage.append(doc_id, payload)
        added.append((doc_id, path))
    return added


def list_documents(data_dir):
    """Return [{id, text, size}] for every stored document."""
    store_path, _, _ = _paths(data_dir)
    if not os.path.exists(store_path):
        return []
    docs = []
    with Storage(store_path) as storage:
        for doc_id, payload in storage.iter_records():
            docs.append({"id": doc_id,
                         "text": payload.decode("utf-8", errors="replace"),
                         "size": len(payload)})
    return docs


def run_search(data_dir, query, mode, ranked):
    """Search with the core engines; returns [{id, score, text}]."""
    store_path, _, _ = _paths(data_dir)
    if not os.path.exists(store_path):
        return []
    with Storage(store_path) as storage:
        index = rebuild_index(storage)
    if ranked:
        doc_ids, terms = search_ranked(index, query, mode=mode), tokenize(query)
    else:
        doc_ids, terms = forge_search(index, query, mode=mode), []
    results = []
    with Storage(store_path) as storage:
        for doc_id in doc_ids:
            results.append({
                "id": doc_id,
                "score": score_document(index, doc_id, terms) if ranked else None,
                "text": storage.get(doc_id).decode("utf-8", errors="replace"),
            })
    return results


def get_stats(data_dir):
    """Storage/WAL/index statistics (mirrors the CLI `stats` command)."""
    store_path, wal_path, id_path = _paths(data_dir)
    stats = {"docs": 0, "terms": 0, "storage_size": None,
             "wal_records": None, "wal_status": None, "next_id": None}
    if os.path.exists(store_path):
        stats["storage_size"] = os.path.getsize(store_path)
        with Storage(store_path) as storage:
            stats["docs"] = len(storage)
            stats["terms"] = rebuild_index(storage).term_count()
    if os.path.exists(wal_path):
        scan = scan_wal(wal_path)
        stats["wal_records"], stats["wal_status"] = len(scan.records), scan.status
    if os.path.exists(id_path):
        with open(id_path, "r", encoding="utf-8") as fh:
            stats["next_id"] = int(fh.read().strip() or "0")
    return stats


def run_check(data_dir):
    """Storage <-> index consistency check; returns {"ok": bool, "detail": str}."""
    store_path, _, _ = _paths(data_dir)
    if not os.path.exists(store_path):
        return {"ok": True, "detail": "no storage file yet (nothing to check)"}
    with Storage(store_path) as storage:
        index = rebuild_index(storage)
        report = validate_consistency(storage, index)
    if report.ok:
        return {"ok": True, "detail": "ok: index is consistent with storage"}
    bits = []
    if report.missing_docs:
        bits.append("missing docs %s" % sorted(report.missing_docs))
    if report.extra_docs:
        bits.append("extra docs %s" % sorted(report.extra_docs))
    if report.missing_postings:
        bits.append("%d missing postings" % len(report.missing_postings))
    if report.extra_postings:
        bits.append("%d extra postings" % len(report.extra_postings))
    if report.term_frequency_mismatches:
        bits.append("%d TF mismatches" % len(report.term_frequency_mismatches))
    if report.extra_terms:
        bits.append("%d spurious terms" % len(report.extra_terms))
    return {"ok": False, "detail": "; ".join(bits) or "index is INCONSISTENT"}


def preview(text, length=68):
    """Single-line preview of document text for table cells."""
    line = " ".join(text.split())
    return (line[:length] + "...") if len(line) > length else line


# ---------------------------------------------------------------- GUI
# Single-window ttk view; all engine work goes through the core wrappers.

class ForgeApp:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.root = tk.Tk()
        self.root.title("FORGE - Local Search Engine")
        self.root.geometry("1000x640")
        self.root.minsize(860, 560)
        self.dir_var = tk.StringVar(value=data_dir)
        self.query_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=MODE_AND)
        self.ranked_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(
            value="Ready - open a data directory, add documents, then search.")
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass
        self._build()
        self.refresh()

    # -- layout --------------------------------------------------------
    def _build(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)
        ttk.Label(root, text="FORGE", font=("TkDefaultFont", 18, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        ttk.Label(root, text="Zero-dependency local search engine - stdlib only").grid(
            row=1, column=0, sticky="w", padx=12)
        bar = ttk.Frame(root)
        bar.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Data directory:").grid(row=0, column=0, sticky="w")
        ttk.Entry(bar, textvariable=self.dir_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 4))
        ttk.Button(bar, text="Browse...", command=self._browse_dir).grid(row=0, column=2)
        ttk.Button(bar, text="Open", command=self._open_dir).grid(row=0, column=3, padx=(4, 0))
        body = ttk.Frame(root)
        body.grid(row=3, column=0, sticky="nsew", padx=12, pady=4)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_documents(body)
        self._build_search(body)
        self._build_engine_panel(root)
        tk.Label(root, textvariable=self.status_var, anchor="w", relief="sunken").grid(
            row=5, column=0, sticky="ew", padx=12, pady=(4, 10))

    def _build_documents(self, parent):
        pane = ttk.LabelFrame(parent, text="Documents", padding=4)
        pane.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        pane.columnconfigure(0, weight=1)
        pane.rowconfigure(1, weight=1)
        buttons = ttk.Frame(pane)
        buttons.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="Add files...", command=self._add_files).pack(side="left")
        ttk.Button(buttons, text="Refresh", command=self.refresh).pack(side="left", padx=(6, 0))
        self.doc_tree = ttk.Treeview(pane, columns=("id", "size", "preview"), show="headings")
        for col, label, width, anchor in (("id", "Doc", 50, "center"),
                                          ("size", "Bytes", 64, "e"),
                                          ("preview", "Preview", 380, "w")):
            self.doc_tree.heading(col, text=label)
            self.doc_tree.column(col, width=width, anchor=anchor, stretch=False)
        scroll = ttk.Scrollbar(pane, orient="vertical", command=self.doc_tree.yview)
        self.doc_tree.configure(yscrollcommand=scroll.set)
        self.doc_tree.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")

    def _build_search(self, parent):
        pane = ttk.LabelFrame(parent, text="Search", padding=4)
        pane.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        pane.columnconfigure(0, weight=1)
        pane.rowconfigure(3, weight=1)
        entry = ttk.Entry(pane, textvariable=self.query_var)
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda _event: self._search())
        ttk.Button(pane, text="Search", command=self._search).grid(row=0, column=1, padx=(4, 0))
        options = ttk.Frame(pane)
        options.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 2))
        ttk.Radiobutton(options, text="AND", value=MODE_AND, variable=self.mode_var).pack(side="left")
        ttk.Radiobutton(options, text="OR", value=MODE_OR, variable=self.mode_var).pack(
            side="left", padx=(10, 0))
        ttk.Checkbutton(options, text="TF-IDF ranked", variable=self.ranked_var).pack(
            side="left", padx=(16, 0))
        self.result_summary = ttk.Label(pane, text="")
        self.result_summary.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 2))
        self.res_tree = ttk.Treeview(pane, columns=("rank", "doc", "score", "preview"),
                                     show="headings")
        for col, label, width, anchor in (("rank", "Rank", 46, "e"),
                                          ("doc", "Doc", 52, "center"),
                                          ("score", "Score", 84, "e"),
                                          ("preview", "Preview", 380, "w")):
            self.res_tree.heading(col, text=label)
            self.res_tree.column(col, width=width, anchor=anchor, stretch=False)
        self.res_tree.column("preview", stretch=True)
        scroll = ttk.Scrollbar(pane, orient="vertical", command=self.res_tree.yview)
        self.res_tree.configure(yscrollcommand=scroll.set)
        self.res_tree.grid(row=3, column=0, sticky="nsew")
        scroll.grid(row=3, column=1, sticky="ns")

    def _build_engine_panel(self, root):
        pane = ttk.LabelFrame(root, text="Engine status", padding=6)
        pane.grid(row=4, column=0, sticky="ew", padx=12, pady=(6, 0))
        pane.columnconfigure(5, weight=1)
        fields = (("docs", "Documents"), ("terms", "Index terms"),
                  ("storage_size", "Storage"), ("wal_records", "WAL records"),
                  ("wal_status", "WAL status"), ("next_id", "Doc ID counter"))
        self.stat_labels = {}
        for index, (key, title) in enumerate(fields):
            row, col = index // 3, (index % 3) * 2
            ttk.Label(pane, text=title + ":").grid(
                row=row, column=col, sticky="w", padx=(12 if col else 0, 4))
            value = tk.Label(pane, text="-")
            value.grid(row=row, column=col + 1, sticky="w")
            self.stat_labels[key] = value
        self.check_label = tk.Label(pane, text="Consistency check: not run")
        self.check_label.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(pane, text="Run consistency check", command=self._check).grid(
            row=2, column=4, columnspan=2, sticky="e", padx=(8, 0))

    # -- actions -------------------------------------------------------
    def refresh(self):
        self._fill_documents()
        self._fill_stats()
        self.check_label.config(text="Consistency check: not run", fg="#222222")

    def _browse_dir(self):
        chosen = filedialog.askdirectory(title="Choose FORGE data directory")
        if chosen:
            self.dir_var.set(chosen)

    def _open_dir(self):
        try:
            self.data_dir = self.dir_var.get().strip() or DEFAULT_DATA_DIR
            self.refresh()
            self.status_var.set("Opened data directory: %s" % self.data_dir)
        except Exception as exc:
            self._fail("Open failed: %s" % exc)

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Add documents to the index",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not paths:
            return
        try:
            added = add_files(self.data_dir, paths)
            self.refresh()
            self.status_var.set("Added %d document(s) from %d file(s)"
                                % (len(added), len(paths)))
        except Exception as exc:
            self._fail("Add failed: %s" % exc)

    def _search(self):
        query = self.query_var.get().strip()
        mode, ranked = self.mode_var.get(), self.ranked_var.get()
        try:
            results = run_search(self.data_dir, query, mode, ranked)
        except Exception as exc:
            self._fail("Search failed: %s" % exc)
            return
        self.res_tree.delete(*self.res_tree.get_children())
        if not query:
            self.result_summary.config(text="Enter a query to search.")
            return
        op = "OR" if mode == MODE_OR else "AND"
        tag = op + (" / TF-IDF ranked" if ranked else "")
        self.result_summary.config(text="%s: %d result(s) for \"%s\"" % (tag, len(results), query))
        for rank, item in enumerate(results, 1):
            score = "%.4f" % item["score"] if ranked else ""
            self.res_tree.insert("", "end", values=(rank, item["id"], score, preview(item["text"])))
        self.status_var.set("Search %s (ranked=%s): %d match(es)" % (op, ranked, len(results)))

    def _check(self):
        try:
            report = run_check(self.data_dir)
        except Exception as exc:
            self._fail("Consistency check failed: %s" % exc)
            return
        if report["ok"]:
            self.check_label.config(text="Consistency check: %s" % report["detail"], fg="#0a7d2f")
            self.status_var.set(report["detail"])
        else:
            self.check_label.config(
                text="Consistency check FAILED: %s" % report["detail"], fg="#b00020")
            self.status_var.set("Consistency check FAILED - see Engine status")

    def _fail(self, message):
        self.status_var.set(message)
        messagebox.showerror("FORGE", message)

    def _fill_documents(self):
        self.doc_tree.delete(*self.doc_tree.get_children())
        for doc in list_documents(self.data_dir):
            self.doc_tree.insert("", "end", values=(doc["id"], doc["size"], preview(doc["text"])))

    def _fill_stats(self):
        stats = get_stats(self.data_dir)
        self.stat_labels["docs"].config(text=str(stats["docs"]))
        self.stat_labels["terms"].config(text=str(stats["terms"]))
        self.stat_labels["storage_size"].config(
            text="%d B" % stats["storage_size"] if stats["storage_size"] is not None else "-")
        self.stat_labels["wal_records"].config(
            text=str(stats["wal_records"]) if stats["wal_records"] is not None else "-")
        self.stat_labels["wal_status"].config(text=stats["wal_status"] or "-")
        self.stat_labels["next_id"].config(
            text=str(stats["next_id"]) if stats["next_id"] is not None else "-")

    def run(self):
        self.root.mainloop()


def main(argv=None):
    """GUI entry point: parse args, open the window, return an exit code."""
    parser = argparse.ArgumentParser(
        prog="forge_gui",
        description="Optional GUI for the FORGE zero-dependency local "
                    "search engine (Python standard library only).")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, metavar="DIR",
                        help="data directory to open (default: %s)" % DEFAULT_DATA_DIR)
    try:
        args = parser.parse_args(argv)
    except SystemExit as code:
        return code.code if isinstance(code.code, int) else 2
    if tk is None:
        print("error: tkinter is not available in this Python installation", file=sys.stderr)
        return 2
    try:
        app = ForgeApp(args.data_dir)
    except tk.TclError as exc:
        print("error: cannot open the GUI window: %s" % exc, file=sys.stderr)
        return 2
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())