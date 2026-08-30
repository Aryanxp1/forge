#!/usr/bin/env python3
"""Build dist/forge.pyz — a standalone, reproducible Python zipapp.

Uses ONLY the Python standard library. No pip, no setuptools, no
third-party dependencies.

Produces a single self-contained artifact that runs with:
    python dist/forge.pyz --help

Reproducible: normalizes timestamps and uses sorted entry ordering so
repeated builds are byte-identical (verified via SHA-256).
"""

import os
import shutil
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_PKG = os.path.join(ROOT, "src", "forge")
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
OUTPUT = os.path.join(DIST, "forge.pyz")

# Fixed timestamp for every archive entry (2020-01-01T00:00:00).
# This makes the build reproducible regardless of when it is run.
FIXED_TIME = (2020, 1, 1, 0, 0, 0)

ENTRY_POINT = b"""\
import sys
from forge.cli import main

if __name__ == "__main__":
    sys.exit(main())
"""

INTERPRETER = b"/usr/bin/env python3"


def clean():
    """Remove previous build artifacts."""
    for d in (BUILD, DIST):
        if os.path.exists(d):
            shutil.rmtree(d)


def copy_package():
    """Copy the forge package into the build directory."""
    dst = os.path.join(BUILD, "forge")
    shutil.copytree(SRC_PKG, dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _walk_sorted(base):
    """Yield (full_path, arcname) pairs in deterministic sorted order."""
    for root, dirs, files in os.walk(base):
        dirs.sort()
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            arcname = os.path.relpath(path, BUILD)
            yield path, arcname


def build():
    """Create the reproducible .pyz archive."""
    os.makedirs(DIST, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", compresslevel=9) as zf:
        # Entry point with shebang.
        entry = zipfile.ZipInfo("__main__.py", date_time=FIXED_TIME)
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o755 << 16
        zf.writestr(entry, b"#! " + INTERPRETER + b"\n" + ENTRY_POINT)

        # Package files in sorted order (reproducible).
        for path, arcname in _walk_sorted(os.path.join(BUILD, "forge")):
            info = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as f:
                zf.writestr(info, f.read())


def main():
    clean()
    copy_package()
    build()
    size = os.path.getsize(OUTPUT)
    print(f"Built {OUTPUT} ({size} bytes)")


if __name__ == "__main__":
    main()
