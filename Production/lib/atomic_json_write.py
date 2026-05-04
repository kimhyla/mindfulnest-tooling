"""
Atomic JSON write with Windows/Dropbox retry.

Extracted from Production/api/stillgen_server.py's _atomic_write_json 2026-04-22
per LD WINDOWS_DROPBOX_ATOMIC_RENAME_RETRY_V1 (MEDIUM). The pattern is reusable
for any Windows+Dropbox caller that needs temp-file-plus-rename atomicity on a
synced folder.

Why the retry exists
--------------------
On Windows, `os.replace()` intermittently fails with `PermissionError: [WinError 5]
Access is denied` when the target path is briefly held open by the Dropbox sync
indexer. On macOS/Linux this code path doesn't trigger — rename is cheap and the
indexer doesn't hold the target. But the helper is cross-platform safe: it
simply no-ops the retry on platforms where the first attempt succeeds.

Backoff shape
-------------
Linear (0.1s, 0.2s, ... up to ~max_attempts × 0.1s). Not exponential — the
failure is a brief hold (~100–600 ms typical), not a cascading external
service, so exponential would over-wait for no upside. Total wait budget at
max_attempts=6 is ~2.1s, small enough to be invisible in interactive tooling.

Fallback
--------
If every attempt fails, fall back to a direct, non-atomic write of the target
path (and clean up the temp file). Logs a warning. This is a deliberate Rule 19
concession: for disk-backed caches (idempotency, cost-cap, pending-writes
queue) disk-state consistency matters more than strict atomicity. A fallback
write will never CORRUPT the target — it may only introduce a 10–100ms window
where a concurrent reader sees a partial file, which the caller's existing
JSON-decode-error fallback already handles.

Usage
-----
    from Production.lib.atomic_json_write import atomic_json_write
    atomic_json_write("/path/to/cache.json", {"k": "v"})

Raises
------
    PermissionError (or the last underlying OSError) only if ALL `max_attempts`
    AND the direct-write fallback fail. Practically unreachable on a writable
    filesystem.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any


def atomic_json_write(path: str, data: Any, max_attempts: int = 6) -> None:
    """Atomically write JSON `data` to `path`. Retries on Windows/Dropbox lock.

    Args:
        path: Absolute or relative destination path.
        data: Any JSON-serializable object. `default=str` is applied.
        max_attempts: How many times to retry os.replace before falling back
            to a direct (non-atomic) write. Default 6.
    """
    tmp = f"{path}.tmp.{uuid.uuid4().hex}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.1 * (attempt + 1))

    # Direct-write fallback.
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        print(
            f"[atomic_json_write] WARN: atomic rename failed on {path}, "
            f"used direct write after {max_attempts} retries.",
            file=sys.stderr,
        )
    except Exception:
        # Fallback also failed — surface the original rename error.
        raise last_exc if last_exc else Exception(
            "atomic_json_write: fallback failed with no original exception"
        )
