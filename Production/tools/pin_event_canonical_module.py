#!/usr/bin/env python3
"""Pin a stitch bake as the canonical Event module final (EVENT_1_CANONICAL_MODULE_V1).

Copies the bake to Event_<n>/M{m}_event{n}_final.mp4 (Production Map discovery),
records lineage in production_state.json, and updates stitch job bake_path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PROD = TOOLS.parent
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))
if str(TOOLS) not in sys.path:
    sys.path.insert(1, str(TOOLS))

from lib.atomic_json_write import atomic_json_write  # noqa: E402
from lib.paths import runtime_production_root  # noqa: E402

EVENT_1_CANONICAL_MODULE_V1 = "EVENT_1_CANONICAL_MODULE_V1"


def _ffprobe_duration_ms(path: Path) -> int:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return int(float(out.stdout.strip()) * 1000)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pin_canonical_module(
    event_dir: Path,
    source_bake: Path,
    *,
    m_number: int = 1,
    event_id: str | None = None,
    stitch_state_path: Path | None = None,
    delivery_profile: str | None = None,
) -> dict:
    event_dir = event_dir.resolve()
    source_bake = source_bake.resolve()
    if not source_bake.is_file():
        raise FileNotFoundError(f"bake not found: {source_bake}")

    event_id = event_id or event_dir.name
    canonical_name = f"M{m_number}_{event_id.lower()}_final.mp4"
    canonical_path = event_dir / canonical_name
    backup_dir = event_dir / "_canonical_module_backups"
    state_path = event_dir / "production_state.json"

    if canonical_path.is_file():
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(canonical_path, backup_dir / f"{canonical_name}.{ts}.bak")

    shutil.copy2(source_bake, canonical_path)
    from video_delivery import ensure_mp4_playback_timestamps  # noqa: PLC0415

    ensure_mp4_playback_timestamps(canonical_path, delivery_profile=delivery_profile)
    dur_ms = _ffprobe_duration_ms(canonical_path)
    digest = _sha256(canonical_path)
    mtime = int(os.path.getmtime(canonical_path))
    pinned_at = datetime.now(timezone.utc).isoformat()

    try:
        rel_source = str(source_bake.relative_to(event_dir))
    except ValueError:
        rel_source = str(source_bake)

    patch = {
        EVENT_1_CANONICAL_MODULE_V1: True,
        "canonical_module_final_file": canonical_name,
        "canonical_module_final_source_bake": rel_source,
        "canonical_module_final_mtime": mtime,
        "canonical_module_final_duration_ms": dur_ms,
        "canonical_module_final_sha256": digest,
        "canonical_module_pinned_at": pinned_at,
    }

    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {"event_id": event_id}
    state.update(patch)
    state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
    atomic_json_write(state_path, state)

    stitch_path = stitch_state_path or (
        runtime_production_root(event_dir) / "tools" / "stitch_editor_state.json"
    )
    if stitch_path.is_file():
        stitch = json.loads(stitch_path.read_text(encoding="utf-8"))
        job_name = f"{event_id}_stitch"
        job = stitch.get("jobs", {}).get(job_name)
        if isinstance(job, dict):
            job["bake_path"] = str(canonical_path)
            job["bake_source"] = rel_source
            job["bake_pinned_at"] = pinned_at
            job["updated_at"] = pinned_at
            atomic_json_write(stitch_path, stitch)

    return {
        "ok": True,
        "event_id": event_id,
        "canonical_path": str(canonical_path),
        "canonical_name": canonical_name,
        "duration_ms": dur_ms,
        "sha256": digest,
        **patch,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pin stitch bake as canonical module final")
    parser.add_argument("--event-dir", type=Path, required=True)
    parser.add_argument("--bake", type=Path, required=True, help="Path to stitch bake mp4")
    parser.add_argument("--m-number", type=int, default=1)
    parser.add_argument("--event-id", default="")
    args = parser.parse_args()
    result = pin_canonical_module(
        args.event_dir,
        args.bake,
        m_number=args.m_number,
        event_id=args.event_id or None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
