"""
Directus high-level helpers — verified writes and simple reads.

This module sits ON TOP of lib/directus_admin_client.py. Admin client handles
transport (auth, retries, urllib). This module adds semantic guarantees:

- `post_item_verified(collection, payload)` — POST + read-back + deep-equality
  verification. Closes the "silent partial write" failure class documented in
  LD POST_ITEM_VERIFIED_V1 (handoff 2026-04-21, Problem 2c).

Per CLAUDE.md Rule 18: Python urllib.request only (never curl). We reuse the
existing DirectusAdminClient for transport, which already uses urllib.

Per CLAUDE.md Rule 19 "No Shortcuts": every write that registers asset state,
decisions, or audit trail should use `post_item_verified` — a plain `post_item`
from the admin client does NOT guarantee the row was saved with the fields we
sent. Directus silently drops fields that don't match the collection schema.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Local import — directus_admin_client is a sibling in the same package.
try:
    from .directus_admin_client import DirectusAdminClient, DirectusAdminError
except ImportError:  # allow running as a script without package context
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from directus_admin_client import DirectusAdminClient, DirectusAdminError  # type: ignore


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class DirectusWriteError(Exception):
    """Raised when the POST to Directus fails with an HTTP error."""

    def __init__(self, collection: str, payload: dict, cause: Exception):
        self.collection = collection
        self.payload = payload
        self.cause = cause
        super().__init__(f"Directus write to {collection} failed: {cause}")


class DirectusReadError(Exception):
    """Raised when the read-back verification GET fails."""

    def __init__(self, collection: str, item_id: Any, cause: Exception):
        self.collection = collection
        self.item_id = item_id
        self.cause = cause
        super().__init__(
            f"Directus verification read of {collection}/{item_id} failed: {cause}"
        )


class SilentWriteFailure(Exception):
    """Raised when read-back detects a silent field mismatch.

    This is the primary failure class `post_item_verified` exists to surface:
    the write succeeded (Directus returned 200/201) but the row on disk does
    not match the payload we sent — because a field was dropped, coerced,
    permission-filtered, or schema-drifted.
    """

    def __init__(self, collection: str, item_id: Any, mismatches: list[dict]):
        self.collection = collection
        self.item_id = item_id
        self.mismatches = mismatches
        summary = "; ".join(
            f"{m['field']}: sent={m['sent']!r}, got={m['got']!r}" for m in mismatches
        )
        super().__init__(
            f"SilentWriteFailure on {collection}/{item_id}: {len(mismatches)} "
            f"mismatch(es): {summary}"
        )


# -----------------------------------------------------------------------------
# Equality helpers
# -----------------------------------------------------------------------------


# Fields that Directus auto-populates or rewrites; presence-verify only.
_AUTO_FIELDS = {
    "id",
    "date_created",
    "date_updated",
    "created_at",
    "updated_at",
    "user_created",
    "user_updated",
    "sort",
}


def _values_equal(sent: Any, got: Any) -> bool:
    """Compare a sent value against the value Directus returned on read-back.

    Rules:
    - None/missing equality is exact.
    - int/float cross-comparison OK (42 == 42.0).
    - bool is NOT considered equal to int (strict type).
    - strings compared exactly (no trim, no case-fold).
    - datetime ISO strings compared after sub-ms normalization.
    - dicts/lists compared recursively with the same rules.
    """
    # None handling
    if sent is None and got is None:
        return True
    if sent is None or got is None:
        return False

    # Bool strict — Python has bool as subclass of int; we do NOT want
    # True == 1 to be considered equal for field-fidelity purposes.
    if isinstance(sent, bool) or isinstance(got, bool):
        if type(sent) is not type(got):
            return False
        return sent == got

    # Numeric cross-type (int vs float) OK
    if isinstance(sent, (int, float)) and isinstance(got, (int, float)):
        return sent == got

    # Lists — recursive, length-sensitive, order-sensitive
    if isinstance(sent, list) and isinstance(got, list):
        if len(sent) != len(got):
            return False
        return all(_values_equal(a, b) for a, b in zip(sent, got))

    # Dicts — recursive
    if isinstance(sent, dict) and isinstance(got, dict):
        if set(sent.keys()) != set(got.keys()):
            return False
        return all(_values_equal(sent[k], got[k]) for k in sent)

    # ISO-8601 datetimes — normalize trailing Z/offset + sub-ms
    if isinstance(sent, str) and isinstance(got, str):
        if _looks_like_iso(sent) and _looks_like_iso(got):
            return _normalize_iso(sent) == _normalize_iso(got)
        return sent == got

    # Type mismatch fall-through (e.g. "42" vs 42 — should fail the check,
    # since silent type coercion is exactly what we want to catch).
    return sent == got and type(sent) is type(got)


def _looks_like_iso(s: str) -> bool:
    if not isinstance(s, str) or len(s) < 10:
        return False
    return s[4] == "-" and s[7] == "-" and (
        len(s) == 10 or (len(s) > 10 and s[10] in "T ")
    )


def _normalize_iso(s: str) -> str:
    """Normalize ISO-8601 strings so roundtrip comparisons work.

    - Strip trailing 'Z' or '+00:00' (treat as UTC either way)
    - Strip sub-millisecond digits (Directus truncates to ms)
    - Replace 'T' separator with space-agnostic marker (actually keep T)
    """
    s = s.strip()
    # Normalize UTC markers
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # If it ends with +HH:MM, keep as-is. If no tz and it's date+time, leave it.
    # Strip microseconds beyond 3 digits, and strip all-zero fractional seconds.
    if "." in s:
        head, _, tail = s.rpartition(".")
        # tail is like '123456+00:00' or '123456'
        tz = ""
        for sep in ("+", "-"):
            # skip the '-' that appears in the date portion — only consider
            # separators AFTER at least one digit
            for idx in range(1, len(tail)):
                if tail[idx] == sep:
                    tz = tail[idx:]
                    tail = tail[:idx]
                    break
            if tz:
                break
        tail = tail[:3]  # keep ms only
        # If all-zero ms, drop the fractional-second portion entirely so
        # "2026-04-21T19:30:00Z" and "2026-04-21T19:30:00.000Z" compare equal.
        if tail and int(tail.ljust(3, "0")) == 0:
            s = f"{head}{tz}"
        else:
            s = f"{head}.{tail.ljust(3, '0')}{tz}"
    return s


def _diff_payload_vs_row(payload: dict, row: dict) -> list[dict]:
    """Return a list of mismatches: {field, sent, got}. Empty list = no drift."""
    mismatches: list[dict] = []
    for field, sent_val in payload.items():
        if field in _AUTO_FIELDS:
            # Presence-verify only for auto-generated fields.
            if field not in row:
                mismatches.append({"field": field, "sent": sent_val, "got": "<missing>"})
            continue
        got_val = row.get(field, "<missing>")
        if got_val == "<missing>" and field in row:
            # Edge case — field is in row but maps to None; re-read explicitly.
            got_val = row.get(field)
        if not _values_equal(sent_val, got_val):
            mismatches.append({"field": field, "sent": sent_val, "got": got_val})
    return mismatches


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def post_item_verified(
    collection: str,
    payload: dict,
    client: Optional[DirectusAdminClient] = None,
    retry_post: bool = False,
) -> dict:
    """POST an item to Directus, read it back, and verify every field matches.

    Closes the "silent partial write" failure class (LD POST_ITEM_VERIFIED_V1,
    Problem 2c of the provenance-layer handoff 2026-04-21). Directus will
    accept a write and return 200 even when fields are silently dropped
    (schema drift, permission-filtered, type coerced). This wrapper re-reads
    the row immediately and raises SilentWriteFailure on any drift.

    Args:
        collection: Directus collection name (e.g. 'prod_activity_log').
        payload: Dict of fields to write. Do NOT include auto-generated fields
                 like 'id' or 'date_created' in the value-comparison intent —
                 those are presence-verified only (see _AUTO_FIELDS).
        client: Optional DirectusAdminClient. If None, one is constructed.
        retry_post: Passed through to the admin client. Caller opts in to POST
                    retry only for idempotent payloads (e.g. dedup-keyed rows).

    Returns:
        The Directus row as read back after write, with 'id' populated.

    Raises:
        DirectusWriteError: on HTTP error from the POST
        DirectusReadError: on HTTP error from the verification GET
        SilentWriteFailure: on any field value mismatch after write

    Performance:
        Adds one extra GET (~100-300ms) per write. Acceptable for audit-trail
        writes (LDs, preflight reviews, checkpoints). NOT for tight loops.
    """
    c = client or DirectusAdminClient()

    # 1) POST the item
    try:
        created = c.post_item(collection, payload, retry_post=retry_post)
    except DirectusAdminError as e:
        raise DirectusWriteError(collection, payload, e) from e

    if not isinstance(created, dict) or "id" not in created:
        raise DirectusWriteError(
            collection,
            payload,
            RuntimeError(f"Directus did not return an id on POST: {created!r}"),
        )

    item_id = created["id"]

    # 2) Read the row back (explicit GET, do not trust the POST response shape)
    try:
        row = c.get_item(collection, item_id)
    except DirectusAdminError as e:
        raise DirectusReadError(collection, item_id, e) from e

    if not isinstance(row, dict):
        raise DirectusReadError(
            collection,
            item_id,
            RuntimeError(f"Read-back returned non-dict: {row!r}"),
        )

    # 3) Verify every field in the payload matches the row
    mismatches = _diff_payload_vs_row(payload, row)
    if mismatches:
        raise SilentWriteFailure(collection, item_id, mismatches)

    return row


def read_item(
    collection: str,
    item_id: Any,
    client: Optional[DirectusAdminClient] = None,
) -> Optional[dict]:
    """Convenience wrapper: read a single item by id."""
    c = client or DirectusAdminClient()
    try:
        return c.get_item(collection, item_id)
    except DirectusAdminError:
        return None


# -----------------------------------------------------------------------------
# Offline-queue helpers (used by mn-context SAVE mode per feedback_desktop_no_hooks.md)
# -----------------------------------------------------------------------------


_PENDING_QUEUE_PATH = Path(__file__).resolve().parent.parent.parent / "pending_directus_writes.json"


def queue_write_offline(collection: str, payload: dict, reason: str = "offline") -> Path:
    """Append a write to pending_directus_writes.json for later replay.

    This is the fallback path when Directus is unreachable (no wifi, auth
    failure, 5xx after retries). Callers should use this instead of silently
    dropping writes per CLAUDE.md Rule 19 (no error paths left open).

    The file lives at the project root next to CLAUDE.md so session-start
    protocols can find it without knowing the lib path.
    """
    queue: list[dict] = []
    if _PENDING_QUEUE_PATH.exists():
        try:
            queue = json.loads(_PENDING_QUEUE_PATH.read_text(encoding="utf-8"))
            if not isinstance(queue, list):
                queue = []
        except (json.JSONDecodeError, OSError):
            queue = []

    queue.append(
        {
            "queued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "collection": collection,
            "payload": payload,
            "reason": reason,
        }
    )
    _PENDING_QUEUE_PATH.write_text(
        json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return _PENDING_QUEUE_PATH


def try_post_or_queue(
    collection: str,
    payload: dict,
    client: Optional[DirectusAdminClient] = None,
) -> dict:
    """Try verified write; on any connection/write failure, queue to disk.

    Returns:
        - The Directus row on success (dict with 'id').
        - A sentinel dict {"queued": True, "path": str} if queued offline.
        - A sentinel dict with browser_smoke_* flag if Phase F gate fires.

    Never raises. Used by mn-context SAVE mode which must not halt on "no
    internet" per feedback_desktop_no_hooks.md.

    Phase F mechanical gate (DS-21 / LD BROWSER_SMOKE_MECHANICAL_GATE_V1):
    rejects writes to ``prod_activity_log`` whose ``action`` ends in
    ``_COMPLETE`` unless a matching ``KIM_BROWSER_SMOKE_PASSED`` row exists.
    Override path: env ``MN_SKIP_BROWSER_SMOKE_GATE=1`` + matching
    ``BROWSER_SMOKE_DEFERRED`` audit row. Fails CLOSED on Directus error so
    a smoke-row query failure cannot silently let a COMPLETE write through.
    """
    if collection == "prod_activity_log":
        action = payload.get("action", "")
        if _is_phase_complete_action(action):
            phase_key = _extract_phase_key(action)
            override_active = os.environ.get("MN_SKIP_BROWSER_SMOKE_GATE") == "1"
            try:
                smoke_present = _smoke_row_exists(phase_key, client=client)
            except Exception as e:  # noqa: BLE001 — fail-CLOSED
                return {
                    "queued": False,
                    "browser_smoke_gate_unverifiable": True,
                    "phase_key": phase_key,
                    "error": (
                        f"Smoke-gate query failed for phase={phase_key!r}: "
                        f"{type(e).__name__}: {e}. Refusing COMPLETE write."
                    ),
                }
            if not smoke_present and not override_active:
                return {
                    "queued": False,
                    "browser_smoke_missing": True,
                    "phase_key": phase_key,
                    "error": (
                        f"Cannot write {action!r} — no KIM_BROWSER_SMOKE_PASSED "
                        f"row found for phase={phase_key!r}. Browser smoke is a "
                        f"hard prerequisite per DS-21. To override, set "
                        f"MN_SKIP_BROWSER_SMOKE_GATE=1 AND write a "
                        f"BROWSER_SMOKE_DEFERRED row first explaining why."
                    ),
                }
            if not smoke_present and override_active:
                try:
                    deferred_present = _smoke_deferred_row_exists(
                        phase_key, client=client
                    )
                except Exception as e:  # noqa: BLE001 — fail-CLOSED
                    return {
                        "queued": False,
                        "browser_smoke_gate_unverifiable": True,
                        "phase_key": phase_key,
                        "error": (
                            f"Override path: deferred-row query failed for "
                            f"phase={phase_key!r}: {type(e).__name__}: {e}. "
                            f"Refusing COMPLETE write."
                        ),
                    }
                if not deferred_present:
                    return {
                        "queued": False,
                        "override_without_audit": True,
                        "phase_key": phase_key,
                        "error": (
                            f"MN_SKIP_BROWSER_SMOKE_GATE=1 but no "
                            f"BROWSER_SMOKE_DEFERRED row exists for "
                            f"phase={phase_key!r}. Write that row first."
                        ),
                    }

    try:
        return post_item_verified(collection, payload, client=client)
    except (DirectusWriteError, DirectusReadError) as e:
        path = queue_write_offline(collection, payload, reason=f"write_error: {e}")
        return {"queued": True, "path": str(path), "error": str(e)}
    except SilentWriteFailure as e:
        # A silent-write is NOT queued (row already exists but is wrong);
        # surface a distinct flag so caller can decide whether to PATCH or alert.
        return {
            "queued": False,
            "silent_write_failure": True,
            "item_id": e.item_id,
            "mismatches": e.mismatches,
            "error": str(e),
        }
    except Exception as e:  # noqa: BLE001 — last-ditch degrade-gracefully path
        path = queue_write_offline(
            collection, payload, reason=f"unexpected: {type(e).__name__}: {e}"
        )
        return {"queued": True, "path": str(path), "error": str(e)}


def patch_item_verified(
    collection: str,
    item_id: Any,
    payload: dict,
    client: Optional[DirectusAdminClient] = None,
) -> dict:
    """PATCH an item to Directus, read it back, and verify every field matches.

    Mirror of post_item_verified for UPDATE semantics. Closes the same silent
    partial-write failure class on PATCH paths (Directus accepts a PATCH and
    returns 200 even when fields are silently dropped).

    Args:
        collection: Directus collection name.
        item_id: id of the row to PATCH.
        payload: Dict of fields to update. Auto-fields are presence-verified
                 only (see _AUTO_FIELDS).
        client: Optional DirectusAdminClient.

    Returns:
        The Directus row as read back after PATCH.

    Raises:
        DirectusWriteError: on HTTP error from PATCH
        DirectusReadError: on HTTP error from verification GET
        SilentWriteFailure: on any field value mismatch after PATCH
    """
    c = client or DirectusAdminClient()

    try:
        c.patch_item(collection, item_id, payload)
    except DirectusAdminError as e:
        raise DirectusWriteError(collection, payload, e) from e

    try:
        row = c.get_item(collection, item_id)
    except DirectusAdminError as e:
        raise DirectusReadError(collection, item_id, e) from e

    if not isinstance(row, dict):
        raise DirectusReadError(
            collection,
            item_id,
            RuntimeError(f"Read-back returned non-dict: {row!r}"),
        )

    mismatches = _diff_payload_vs_row(payload, row)
    if mismatches:
        raise SilentWriteFailure(collection, item_id, mismatches)

    return row


def try_patch_or_queue(
    collection: str,
    item_id: Any,
    payload: dict,
    client: Optional[DirectusAdminClient] = None,
) -> dict:
    """Try verified PATCH; on connection/write failure, queue to disk.

    Mirror of try_post_or_queue for UPDATE semantics. Authored 2026-05-10 as
    Phase A.6 of V59_DIRECTUS_MCP_SERVER_SPEC_v1 (cursor cross-review finding
    4A). Same return-shape contract as try_post_or_queue: never raises;
    returns row dict on success, sentinel dicts on each failure mode.

    Returns:
        - The Directus row on success (dict with 'id').
        - {queued: True, path: str} if queued offline.
        - {queued: False, silent_write_failure: True, item_id, mismatches, error}.

    Note: PATCH does NOT trigger the Phase F browser-smoke gate currently.
    The DS-21 gate fires on prod_activity_log _COMPLETE actions which are
    POSTs by definition (creating new audit-trail rows), not PATCHes. If
    governance ever needs PATCH-gated behavior, mirror the gate logic here.
    """
    queue_payload = dict(payload)
    queue_payload["__patch_target_id"] = item_id  # mark for replay tooling
    try:
        return patch_item_verified(collection, item_id, payload, client=client)
    except (DirectusWriteError, DirectusReadError) as e:
        path = queue_write_offline(
            collection, queue_payload, reason=f"patch_error: {e}"
        )
        return {"queued": True, "path": str(path), "error": str(e)}
    except SilentWriteFailure as e:
        return {
            "queued": False,
            "silent_write_failure": True,
            "item_id": e.item_id,
            "mismatches": e.mismatches,
            "error": str(e),
        }
    except Exception as e:  # noqa: BLE001
        path = queue_write_offline(
            collection,
            queue_payload,
            reason=f"unexpected_patch: {type(e).__name__}: {e}",
        )
        return {"queued": True, "path": str(path), "error": str(e)}


# -----------------------------------------------------------------------------
# Phase F gate helpers — DS-21 / LD BROWSER_SMOKE_MECHANICAL_GATE_V1
# -----------------------------------------------------------------------------


_COMPLETE_SUFFIX = "_COMPLETE"


def _is_phase_complete_action(action: str) -> bool:
    """True for action strings that end in ``_COMPLETE`` (case-sensitive).

    Examples that match: ``PHASE_A_COMPLETE``, ``S5_5C_PASS2_COMPLETE``,
    ``PHASE_F_COMPLETE``. Examples that do NOT match:
    ``KIM_BROWSER_SMOKE_PASSED``, ``BROWSER_SMOKE_DEFERRED``, ``COMPLETE``
    (suffix only, no prefix is rejected as an audit-noise guard).
    """
    if not isinstance(action, str) or not action:
        return False
    return action.endswith(_COMPLETE_SUFFIX) and len(action) > len(_COMPLETE_SUFFIX)


def _extract_phase_key(action: str) -> str:
    """Strip trailing ``_COMPLETE`` to get the phase key.

    e.g. ``S5_5C_PASS2_COMPLETE`` → ``S5_5C_PASS2``,
         ``PHASE_F_COMPLETE`` → ``PHASE_F``.
    """
    if not _is_phase_complete_action(action):
        return action
    return action[: -len(_COMPLETE_SUFFIX)]


def _smoke_row_exists(
    phase_key: str, client: Optional[DirectusAdminClient] = None
) -> bool:
    """True iff at least one ``KIM_BROWSER_SMOKE_PASSED`` row matches phase_key.

    Filters on ``action == 'KIM_BROWSER_SMOKE_PASSED'`` and
    ``details.phase == phase_key``. Raises on Directus error so the caller
    can fail-CLOSED.
    """
    return _matching_row_exists(
        "KIM_BROWSER_SMOKE_PASSED", phase_key, client=client
    )


def _smoke_deferred_row_exists(
    phase_key: str, client: Optional[DirectusAdminClient] = None
) -> bool:
    """True iff at least one ``BROWSER_SMOKE_DEFERRED`` row matches phase_key."""
    return _matching_row_exists(
        "BROWSER_SMOKE_DEFERRED", phase_key, client=client
    )


def _matching_row_exists(
    action: str,
    phase_key: str,
    client: Optional[DirectusAdminClient] = None,
) -> bool:
    """Shared body for the two phase-gated lookups above.

    Uses two complementary filter strategies because Directus's nested-JSON
    filter behavior on `details.phase` has historically been inconsistent
    across schema versions:
      1. Server-side filter on action only (always works).
      2. Client-side scan of `details.phase` on the returned rows.
    The combined approach avoids false-negatives that would let COMPLETE
    writes silently through if the nested filter failed quietly.
    """
    c = client or DirectusAdminClient()
    rows = c.get_items(
        "prod_activity_log",
        filters={"action": {"_eq": action}},
        limit=-1,
    ) or []
    for row in rows:
        details = row.get("details") or {}
        if isinstance(details, dict) and details.get("phase") == phase_key:
            return True
    return False


if __name__ == "__main__":
    # Smoke test: verify we can round-trip a tiny activity log entry.
    import os as _os

    # Doppler-canonical names first, legacy bare names accepted (LD-227 Phase 1).
    if not (_os.environ.get("DIRECTUS_ADMIN_EMAIL") or _os.environ.get("DIRECTUS_EMAIL")):
        print(
            "Run via `doppler run -- ` (Doppler project `mindfulnest`) or set "
            "DIRECTUS_ADMIN_EMAIL/DIRECTUS_ADMIN_PASSWORD (or legacy "
            "DIRECTUS_EMAIL/DIRECTUS_PASSWORD) to run smoke test."
        )
        sys.exit(0)

    payload = {
        "action": "post_item_verified_smoke_test",
        "details": {"source": "lib/directus.py __main__", "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
        "performed_by": "autonomous_build_provenance_layer",
    }
    row = post_item_verified("prod_activity_log", payload)
    print(f"OK: wrote + verified activity_log id={row['id']}")
