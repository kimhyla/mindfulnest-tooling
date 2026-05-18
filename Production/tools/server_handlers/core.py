"""Core handlers — V59 Phase 4 Pass 1 module 1.

Handlers extracted from production_server.py for:
- /api/health
- /api/state, /api/state_snapshot
- /api/admin/drain_start, /api/admin/drain_end, /api/admin/inflight_count
- /api/patch_health
- / (root storyboard serve)
- /storyboard

Each function takes the live `ProductionHandler` instance as `h` and
operates against `h.app.state` (StateManager) + h's reply helpers.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

# V59 Phase 4 cross-review fix (body_key_contract CI failure):
# missing module-level variable references that need re-import.
from tools.production_server import (  # noqa: E402
    _ASSEMBLE_JOBS,
    _GPT_JOBS,
    _MAGIC_JOBS,
)


def handle_patch_health(h, body: dict) -> None:
    """POST /api/patch_health  body: {patch: str, msg: str}

    Receives runtime invariant-violation reports from the storyboard's
    Fix-W __patchHealthcheck() and logs to prod_activity_log so the
    weekly preflight audit catches regressions.

    Implements CLAUDE.md Rule 36 PATCH_INVARIANT_PERSISTENCE_V1 §36.3.
    Phase 0 preflight 187.
    """
    patch = (body or {}).get("patch") or "unknown"
    msg = (body or {}).get("msg") or ""
    try:
        from lib.directus import try_post_or_queue
        try_post_or_queue("prod_activity_log", {
            "action": "patch_invariant_violation",
            "performed_by": "storyboard_runtime_healthcheck",
            "details": {"patch": patch, "msg": msg, "rule": "Rule 36"},
        })
    except Exception as e:
        print(f"[patch_health] WARN: activity log failed: {e}")
    print(f"[patch_health] {patch}: {msg}", flush=True)
    return h._send_json(200, {"ok": True})


def handle_state_snapshot(h, body: dict) -> None:
    """POST /api/state/snapshot  body: {event_id} -> {ok, backup_path, sha256}

    Mitigation M1 per LD-456 PATH_C_REWRITE_V1: every v59 mutation is
    preceded by a state snapshot. Writes a timestamped UTC copy of
    Production/Event_<N>/production_state.json into
    Production/Event_<N>/.backups/state/YYYY-MM-DD_HHMMSSZ.json.

    The v59 client's pathappPatch() will call this before each mutation
    once Session 2+ wires mutations through. Session 1.5 ships the
    endpoint; mutations don't fire from the client yet.
    """
    # READ-ONLY probe (M1 backup precursor — backs up state file, does
    # not mutate Event state). Per spec_v2 §5.2 + SCOPE_REQUIRED_DEFAULTS_V1
    # read-only probes keep allow_missing=True.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=True):
        return

    state_path = h.app.event_dir / "production_state.json"
    if not state_path.exists():
        return h._send_json(404, {
            "error": "production_state.json not found",
            "hint": f"expected at {state_path}",
        })

    backups_dir = h.app.event_dir / ".backups" / "state"
    try:
        backups_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return h._send_json(500, {
            "error": f"could not create backups dir: {exc}",
            "backups_dir": str(backups_dir),
        })

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
    backup_path = backups_dir / f"{ts}.json"

    # Hardlink-first (cheap, COW-friendly), copy fallback for cross-device.
    try:
        try:
            os.link(state_path, backup_path)
            method = "hardlink"
        except (OSError, NotImplementedError):
            shutil.copy2(state_path, backup_path)
            method = "copy"
    except OSError as exc:
        return h._send_json(500, {
            "error": f"snapshot write failed: {exc}",
            "backup_path": str(backup_path),
        })

    # SHA-256 the result so callers can verify integrity.
    try:
        sha = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    except OSError as exc:
        sha = f"<unreadable: {exc}>"

    size_bytes = backup_path.stat().st_size if backup_path.exists() else 0

    print(
        f"[state/snapshot] {method} -> {backup_path.relative_to(h.app.event_dir)} "
        f"({size_bytes} bytes, sha256={sha[:16]}...)",
        flush=True,
    )
    return h._send_json(200, {
        "ok": True,
        "method": method,
        "backup_path": str(backup_path),
        "backup_filename": backup_path.name,
        "size_bytes": size_bytes,
        "sha256": sha,
    })


def handle_admin_drain_start(h, body: dict | None = None) -> None:
    """POST /api/admin/drain_start — gate new work.

    Sets app.accept_new_jobs=False so subsequent decorated handlers
    return HTTP 503 immediately. Existing in-flight work continues
    until terminal completion. Returns the current inflight snapshot
    so the migration script can decide whether to abort.

    Idempotent: safe to call multiple times; second+ calls return the
    same {ok, inflight_count} shape with no state change.
    """
    h.app.accept_new_jobs = False
    # Reuse the inflight enumeration helper for consistency.
    return handle_admin_inflight_count(h, body)


def handle_admin_drain_end(h, body: dict | None = None) -> None:
    """POST /api/admin/drain_end — re-open new work.

    Sets app.accept_new_jobs=True. Idempotent.
    """
    h.app.accept_new_jobs = True
    return h._send_json(200, {
        "ok": True,
        "accept_new_jobs": True,
    })


def handle_admin_inflight_count(h, body: dict | None = None) -> None:
    """GET /api/admin/inflight_count — full enumeration of active work.

    Per v3 spec §3.7: derives count from existing module-level
    registries (_GPT_JOBS, _MAGIC_JOBS, _ASSEMBLE_JOBS) plus
    app._sync_inflight (sync handler tracking) plus a state-scan for
    lipsync (which lives in state.beats[bk].lipsync.status across all
    video role partitions: intro, resolution, standalone).

    Used by both the migration script's pre-flight abort gate and the
    E37 drain probe.
    """
    from production_server import _ASSEMBLE_JOBS, _GPT_JOBS, _MAGIC_JOBS

    active: dict[str, list] = {
        "gpt": [], "magic": [], "assemble": [], "lipsync": [], "sync": [],
    }

    # GPT jobs (running)
    for job_id, info in list(_GPT_JOBS.items()):
        if info.get("status") == "running":
            done = sum(len(v) for v in info.get("results", {}).values()) \
                if isinstance(info.get("results"), dict) else 0
            total = info.get("total") or 0
            active["gpt"].append({
                "job_id": job_id,
                "name": f"gpt-stills:{job_id}",
                "progress": f"{done}/{total}",
            })

    # Magic jobs (non-terminal)
    _MAGIC_TERMINAL = {"done", "error"}
    for job_id, info in list(_MAGIC_JOBS.items()):
        st = info.get("status")
        if st not in _MAGIC_TERMINAL:
            active["magic"].append({
                "job_id": job_id,
                "name": f"magic:{info.get('scene_key', '?')}",
                "status": st,
            })

    # Assemble jobs (running)
    for gid, info in list(_ASSEMBLE_JOBS.items()):
        if info.get("status") == "running":
            active["assemble"].append({
                "group_id": gid,
                "name": f"assemble:group={gid}",
            })

    # Lipsync — state-scan across all video role partitions
    try:
        st = h.app.state.read_state()
        for role in ("intro", "resolution", "standalone"):
            partition = ((st.get("videos") or {}).get(role) or {})
            beats = partition.get("beats") or {}
            for bk, b in beats.items():
                ls = (b or {}).get("lipsync") or {}
                if ls.get("status") in ("submitting", "polling"):
                    active["lipsync"].append({
                        "beat_id": bk,
                        "role": role,
                        "name": f"lipsync:{role}:{bk}",
                        "status": ls["status"],
                    })
    except Exception:
        # Cold-boot or read failure: treat as no lipsync in flight.
        # Drain protocol is fail-closed at the migration level (it
        # also polls 60s for sync residue), so a transient state
        # read failure here doesn't compromise correctness.
        pass

    # Sync inflight (decorator-tracked)
    with h.app._sync_inflight_lock:
        for sid in sorted(h.app._sync_inflight):
            handler, _, _ = sid.partition(":")
            active["sync"].append({"id": sid, "name": handler})

    total = sum(len(v) for v in active.values())
    return h._send_json(200, {
        "ok": True,
        "inflight_count": total,
        "accept_new_jobs": getattr(h.app, "accept_new_jobs", True),
        "active_jobs": active,
    })


def handle_health(h) -> None:
    from production_server import SERVER_VERSION

    h._send_json(200, {
        "status": "ok",
        "uptime_seconds": int(time.time() - h.app.started_at),
        "event_id": h.app.event_id,
        "version": SERVER_VERSION,
    })


def serve_storyboard(h) -> None:
    if not h.app.storyboard_path.is_file():
        return h._send_json(500, {
            "error": f"storyboard not found: {h.app.storyboard_path}"})
    html = h.app.storyboard_path.read_text(encoding="utf-8")
    nav = h._build_storyboard_nav_html()
    if "</body>" in html:
        html = html.replace("</body>", nav + "\n</body>", 1)
    else:
        html = html + nav
    body = html.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)
