"""Subprocess crash helper used by tests/test_crash.py.

Simulates a hard process crash (os._exit, skipping all cleanup) either
before or after the storage write, in order to prove the durability
invariant:

    WAL fsync -> COMMITTED -> crash -> restart -> recovery -> recoverable

Usage:
    crash_helper.py <wal> <storage> <doc_id> <payload> <mode>
    mode = 'before_storage' | 'after_storage'

The process always terminates abnormally (exit code 3).
"""

import os
import sys


def main() -> None:
    wal_path, storage_path, doc_id_str, payload, mode = sys.argv[1:]
    doc_id = int(doc_id_str)
    payload_bytes = payload.encode('utf-8')

    # Make the forge package importable regardless of the parent's cwd.
    src = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'
    )
    sys.path.insert(0, src)

    from forge.storage import Storage
    from forge.wal import WalWriter

    # Write -> flush -> fsync -> COMMITTED. No storage I/O yet.
    with WalWriter(wal_path) as wal:
        wal.append(doc_id, payload_bytes)

    # Report the commit BEFORE the artificial crash, so the parent can
    # assert that this write was acknowledged as committed.
    sys.stdout.write(f'COMMITTED:{doc_id}:{payload}\n')
    sys.stdout.flush()

    if mode == 'after_storage':
        storage = Storage(storage_path)
        storage.append(doc_id, payload_bytes)
        storage.close()

    # Hard crash: bypass all Python cleanup, exactly like a process kill.
    os._exit(3)


if __name__ == '__main__':
    main()