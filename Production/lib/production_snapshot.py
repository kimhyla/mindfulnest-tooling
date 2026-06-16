"""Durable production-state snapshots for Beat Gen, Stitcher, Phase A/B.

Rolling ``latest/`` is updated on every hooked write (beat sidecar,
production_state, stitch_editor_state). Timestamped archives are created
at most once per ARCHIVE_INTERVAL_S (default 5 min) or on explicit backup.

Restore copies JSON/YAML state back to live paths. Media (MP3/MP4) stays on
disk under Event_N/ — snapshots preserve the metadata that points at them
(trims, voice pins, lipsync lineage, stitch slots, phase_a/b pins).

Agent workflow: when Kim says "restore the beats", run
``python3 Production/scripts/restore_production_snapshot.py --latest``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
SNAPSHOT_ROOT_NAME = ".production_snapshots"
LATEST_DIR_NAME = "latest"
ARCHIVE_DIR_NAME = "archive"

ARCHIVE_INTERVAL_S = float(os.environ.get("MN_SNAPSHOT_ARCHIVE_INTERVAL_S", "300"))
KEEP_ARCHIVES = int(os.environ.get("MN_SNAPSHOT_KEEP_ARCHIVES", "96"))

PHASE_LIPSYNC_SIDECAR_GLOB = "phase_*_lipsync_*.json"

GLOBAL_FILES = (
    "beat_generator_state.json",
    "tools/stitch_editor_state.json",
    "tools/scene_registry.yaml",
    "canonical_image_registry.json",
)

_EVENT_DIR_RE = re.compile(r"^Event_\d+$", re.I)


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_dir: Path
    manifest: dict[str, Any]
    files_copied: int


def snapshot_root(prod_root: Path | str) -> Path:
    return Path(prod_root) / SNAPSHOT_ROOT_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_event_dirs(prod_root: Path) -> list[Path]:
    out: list[Path] = []
    for child in sorted(prod_root.iterdir()):
        if child.is_dir() and _EVENT_DIR_RE.match(child.name):
            if (child / "production_state.json").is_file():
                out.append(child)
    return out


def _rel_event_path(event_dir: Path, prod_root: Path) -> str:
    return f"events/{event_dir.name}"


def _copy_file(src: Path, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return {
        "source": str(src),
        "dest": str(dest),
        "bytes": dest.stat().st_size,
        "sha256": _sha256(dest),
    }


def _collect_phase_lipsync_sidecars(event_dir: Path) -> list[Path]:
    return sorted(event_dir.glob(PHASE_LIPSYNC_SIDECAR_GLOB))


def create_snapshot(
    prod_root: Path | str,
    *,
    dest_dir: Path | None = None,
    event_dirs: list[Path] | None = None,
    label: str | None = None,
    source: str = "manual",
) -> SnapshotResult:
    """Copy all production JSON/YAML state into ``dest_dir``."""
    prod = Path(prod_root)
    events = event_dirs if event_dirs is not None else discover_event_dirs(prod)
    if dest_dir is None:
        dest_dir = snapshot_root(prod) / LATEST_DIR_NAME
    dest = Path(dest_dir)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    files_copied = 0

    for rel in GLOBAL_FILES:
        src = prod / rel
        if not src.is_file():
            continue
        meta = _copy_file(src, dest / "global" / Path(rel).name)
        meta["kind"] = "global"
        meta["rel"] = rel
        entries.append(meta)
        files_copied += 1

    for event_dir in events:
        ev_rel = _rel_event_path(event_dir, prod)
        ps = event_dir / "production_state.json"
        if ps.is_file():
            meta = _copy_file(ps, dest / ev_rel / "production_state.json")
            meta["kind"] = "production_state"
            meta["event"] = event_dir.name
            entries.append(meta)
            files_copied += 1
        sidecars = _collect_phase_lipsync_sidecars(event_dir)
        for sc in sidecars:
            meta = _copy_file(sc, dest / ev_rel / "phase_lipsync_sidecars" / sc.name)
            meta["kind"] = "phase_lipsync_sidecar"
            meta["event"] = event_dir.name
            entries.append(meta)
            files_copied += 1

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": _utc_now_iso(),
        "label": label or "",
        "source": source,
        "prod_root": str(prod),
        "events": [e.name for e in events],
        "files_copied": files_copied,
        "entries": entries,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return SnapshotResult(snapshot_dir=dest, manifest=manifest, files_copied=files_copied)


def list_archives(prod_root: Path | str) -> list[dict[str, Any]]:
    archive = snapshot_root(prod_root) / ARCHIVE_DIR_NAME
    if not archive.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted(archive.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        mf = d / "manifest.json"
        if mf.is_file():
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
        else:
            manifest = {}
        out.append({
            "id": d.name,
            "path": str(d),
            "created_at": manifest.get("created_at"),
            "label": manifest.get("label"),
            "source": manifest.get("source"),
            "files_copied": manifest.get("files_copied"),
        })
    return out


def _read_archive_meta(prod_root: Path) -> dict[str, Any]:
    meta_path = snapshot_root(prod_root) / "archive_meta.json"
    if meta_path.is_file():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _write_archive_meta(prod_root: Path, meta: dict[str, Any]) -> None:
    path = snapshot_root(prod_root) / "archive_meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def maybe_create_archive_snapshot(
    prod_root: Path | str,
    *,
    source: str = "auto",
    force: bool = False,
) -> SnapshotResult | None:
    """Create timestamped archive if interval elapsed or ``force``."""
    prod = Path(prod_root)
    meta = _read_archive_meta(prod)
    last_ts = float(meta.get("last_archive_ts") or 0.0)
    now = time.time()
    if not force and (now - last_ts) < ARCHIVE_INTERVAL_S:
        return None
    archive_dir = snapshot_root(prod) / ARCHIVE_DIR_NAME / _utc_stamp()
    result = create_snapshot(prod, dest_dir=archive_dir, source=source, label="auto")
    meta["last_archive_ts"] = now
    meta["last_archive_dir"] = str(archive_dir)
    _write_archive_meta(prod, meta)
    prune_archives(prod, keep=KEEP_ARCHIVES)
    return result


def prune_archives(prod_root: Path | str, *, keep: int = KEEP_ARCHIVES) -> int:
    archive = snapshot_root(prod_root) / ARCHIVE_DIR_NAME
    if not archive.is_dir():
        return 0
    dirs = sorted(
        [d for d in archive.iterdir() if d.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    removed = 0
    for d in dirs[keep:]:
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    return removed


def _resolve_snapshot_dir(prod_root: Path, *, latest: bool, snapshot_id: str | None) -> Path:
    root = snapshot_root(prod_root)
    if latest:
        path = root / LATEST_DIR_NAME
    elif snapshot_id:
        path = root / ARCHIVE_DIR_NAME / snapshot_id
    else:
        archives = list_archives(prod_root)
        if not archives:
            raise FileNotFoundError("no archives found")
        path = Path(archives[0]["path"])
    if not path.is_dir() or not (path / "manifest.json").is_file():
        raise FileNotFoundError(f"snapshot not found: {path}")
    return path


def restore_snapshot(
    prod_root: Path | str,
    *,
    latest: bool = True,
    snapshot_id: str | None = None,
    events: list[str] | None = None,
    dry_run: bool = False,
    pre_restore_backup: bool = True,
) -> dict[str, Any]:
    """Restore JSON/YAML state from ``latest`` or a named archive."""
    prod = Path(prod_root)
    snap_dir = _resolve_snapshot_dir(prod, latest=latest, snapshot_id=snapshot_id)
    manifest = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
    event_filter = {e if e.startswith("Event_") else f"Event_{e}" for e in (events or [])}

    pre_backup: str | None = None
    if pre_restore_backup and not dry_run:
        pre = create_snapshot(
            prod,
            dest_dir=snapshot_root(prod) / ARCHIVE_DIR_NAME / f"{_utc_stamp()}_pre_restore",
            source="pre_restore",
            label="pre_restore",
        )
        pre_backup = str(pre.snapshot_dir)

    restored: list[dict[str, Any]] = []
    skipped: list[str] = []

    global_dir = snap_dir / "global"
    if global_dir.is_dir():
        for src in global_dir.iterdir():
            if not src.is_file():
                continue
            rel = next((g for g in GLOBAL_FILES if Path(g).name == src.name), src.name)
            dest = prod / rel
            if dry_run:
                restored.append({"dest": str(dest), "source": str(src), "dry_run": True})
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                restored.append({"dest": str(dest), "source": str(src), "bytes": dest.stat().st_size})

    events_dir = snap_dir / "events"
    if events_dir.is_dir():
        for event_snap in sorted(events_dir.iterdir()):
            if not event_snap.is_dir():
                continue
            if event_filter and event_snap.name not in event_filter:
                skipped.append(event_snap.name)
                continue
            live_event = prod / event_snap.name
            ps = event_snap / "production_state.json"
            if ps.is_file():
                dest = live_event / "production_state.json"
                if dry_run:
                    restored.append({"dest": str(dest), "source": str(ps), "dry_run": True})
                else:
                    live_event.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ps, dest)
                    restored.append({"dest": str(dest), "source": str(ps)})
            sidecar_dir = event_snap / "phase_lipsync_sidecars"
            if sidecar_dir.is_dir():
                for sc in sidecar_dir.iterdir():
                    if not sc.is_file():
                        continue
                    dest = live_event / sc.name
                    if dry_run:
                        restored.append({"dest": str(dest), "source": str(sc), "dry_run": True})
                    else:
                        shutil.copy2(sc, dest)
                        restored.append({"dest": str(dest), "source": str(sc)})

    return {
        "ok": True,
        "dry_run": dry_run,
        "snapshot_dir": str(snap_dir),
        "snapshot_created_at": manifest.get("created_at"),
        "pre_restore_backup": pre_backup,
        "restored_count": len(restored),
        "restored": restored,
        "skipped_events": skipped,
    }


# ---------------------------------------------------------------------------
# Write hooks — update rolling latest + maybe archive
# ---------------------------------------------------------------------------

_last_hook_ts: dict[str, float] = {}
_HOOK_MIN_INTERVAL_S = float(os.environ.get("MN_SNAPSHOT_HOOK_MIN_INTERVAL_S", "2"))


def _hook_key(prod_root: Path, rel_path: str) -> str:
    return f"{prod_root}|{rel_path}"


def notify_state_write(written_path: Path | str, *, prod_root: Path | str | None = None) -> None:
    """Called after a production state file is written. Never raises."""
    try:
        path = Path(written_path).resolve()
        prod = Path(prod_root).resolve() if prod_root else None
        if prod is None:
            # Infer Production/ root from path shape.
            parts = path.parts
            if "Production" not in parts:
                return
            idx = parts.index("Production")
            prod = Path(*parts[: idx + 1])

        rel: str | None = None
        try:
            rel = str(path.relative_to(prod))
        except ValueError:
            return

        tracked = (
            rel == "beat_generator_state.json"
            or rel == "tools/stitch_editor_state.json"
            or rel == "tools/scene_registry.yaml"
            or rel.endswith("/production_state.json")
            or ("/Event_" in str(path) and path.name.startswith("phase_") and path.suffix == ".json")
        )
        if not tracked:
            return

        key = _hook_key(prod, rel)
        now = time.time()
        if now - _last_hook_ts.get(key, 0.0) < _HOOK_MIN_INTERVAL_S:
            return
        _last_hook_ts[key] = now

        create_snapshot(prod, source="write_hook")
        maybe_create_archive_snapshot(prod, source="write_hook")
    except Exception as exc:  # noqa: BLE001 — backup must never break writes
        print(f"[production_snapshot] WARN hook failed (non-fatal): {exc}", flush=True)
