#!/usr/bin/env python3
"""Stitch bake → canonical module final + Directus (EVENT_CANONICAL_MODULE_V1).

Category contract for every Stitcher "Bake final MP4":
  1. Keep timestamped copy under Event_<n>/exports/ (audit trail).
  2. Pin to M{m}_event_{n}_final.mp4 + production_state lineage fields.
  3. register_asset on the **canonical** path (final_atomic_mp4).
  4. approve_asset so prod_assets marks the row current for the module/event.

CLI replays the same path for an existing exports bake (e.g. operator-confirmed final).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PROD = TOOLS.parent
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))
if str(TOOLS) not in sys.path:
    sys.path.insert(1, str(TOOLS))

from lib.milestone_store import (  # noqa: E402
    load_milestone_state,
    milestone_stitch_state_path,
    save_milestone_state,
)
from lib.paths import runtime_production_root  # noqa: E402
from pin_event_canonical_module import pin_canonical_module  # noqa: E402

MILESTONE_STANDALONE_FINAL_V1 = "MILESTONE_STANDALONE_FINAL_V1"


_MNE_PATTERN = re.compile(r"M(\d+)E(\d+)", re.IGNORECASE)
_EVENT_DIR_PATTERN = re.compile(r"Event_(\d+)", re.IGNORECASE)


def resolve_m_and_event_numbers(
    event_dir: Path,
    *,
    production_state: dict | None = None,
) -> tuple[int, int]:
    """Return (m_number, event_num) for canonical filename + Directus event_id."""
    state = production_state
    if state is None:
        state_path = event_dir / "production_state.json"
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {}

    event_key = str(state.get("event_id") or "").strip()
    m_match = _MNE_PATTERN.search(event_key)
    if m_match:
        return int(m_match.group(1)), int(m_match.group(2))

    dir_match = _EVENT_DIR_PATTERN.search(event_dir.name)
    if dir_match:
        event_num = int(dir_match.group(1))
        return event_num, event_num

    raise ValueError(
        f"cannot resolve m_number/event_num from {event_dir} "
        f"(production_state.event_id={event_key!r})"
    )


def default_stitch_state_path(event_dir: Path) -> Path:
    return runtime_production_root(event_dir) / "tools" / "stitch_editor_state.json"


def _ffprobe_duration_ms(path: Path) -> int:
    import subprocess

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


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pin_milestone_standalone_final(
    milestone_dir: Path,
    source_bake: Path,
    *,
    stitch_state_path: Path | None = None,
    job_name: str | None = None,
    delivery_profile: str | None = None,
) -> dict:
    """Pin lean bake to milestone assembled/{id}_standalone_final.mp4 + state lineage."""
    import os
    import shutil
    from datetime import datetime, timezone

    from lib.atomic_json_write import atomic_json_write  # noqa: PLC0415
    from video_delivery import ensure_mp4_playback_timestamps  # noqa: PLC0415

    milestone_dir = milestone_dir.resolve()
    source_bake = source_bake.resolve()
    if not source_bake.is_file():
        raise FileNotFoundError(f"bake not found: {source_bake}")

    milestone_id = milestone_dir.name
    canonical_name = f"{milestone_id}_standalone_final.mp4"
    out_dir = milestone_dir / "assembled"
    out_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = out_dir / canonical_name
    backup_dir = milestone_dir / "_canonical_standalone_backups"
    if canonical_path.is_file():
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(canonical_path, backup_dir / f"{canonical_name}.{ts}.bak")

    shutil.copy2(source_bake, canonical_path)
    ensure_mp4_playback_timestamps(canonical_path, delivery_profile=delivery_profile)
    dur_ms = _ffprobe_duration_ms(canonical_path)
    digest = _sha256_file(canonical_path)
    mtime = int(os.path.getmtime(canonical_path))
    pinned_at = datetime.now(timezone.utc).isoformat()

    try:
        rel_source = str(source_bake.relative_to(milestone_dir))
    except ValueError:
        rel_source = str(source_bake)

    rel_canonical = str(canonical_path.relative_to(milestone_dir))
    state = load_milestone_state(milestone_dir) or {"milestone_id": milestone_id}
    videos = state.setdefault("videos", {})
    standalone = videos.setdefault("standalone", {})
    standalone["completed_mp4_path"] = rel_canonical
    state.update({
        MILESTONE_STANDALONE_FINAL_V1: True,
        "canonical_standalone_final_file": canonical_name,
        "canonical_standalone_final_source_bake": rel_source,
        "canonical_standalone_final_mtime": mtime,
        "canonical_standalone_final_duration_ms": dur_ms,
        "canonical_standalone_final_sha256": digest,
        "canonical_standalone_pinned_at": pinned_at,
        "updated_at": pinned_at,
    })
    save_milestone_state(milestone_dir, state)

    stitch_path = stitch_state_path or milestone_stitch_state_path(milestone_dir)
    stitch_job = job_name or f"milestone_{milestone_id}_stitch"
    if stitch_path.is_file():
        stitch = json.loads(stitch_path.read_text(encoding="utf-8"))
        job = stitch.setdefault("jobs", {}).setdefault(stitch_job, {})
        job["bake_path"] = str(canonical_path)
        job["bake_source"] = rel_source
        job["bake_pinned_at"] = pinned_at
        job["updated_at"] = pinned_at
        atomic_json_write(stitch_path, stitch)

    return {
        "ok": True,
        "milestone_id": milestone_id,
        "canonical_path": str(canonical_path),
        "canonical_name": canonical_name,
        "duration_ms": dur_ms,
        "sha256": digest,
        MILESTONE_STANDALONE_FINAL_V1: True,
    }


def finalize_milestone_stitch_bake(
    milestone_dir: Path,
    export_bake_path: Path,
    *,
    job_name: str | None = None,
    iteration_notes: str = "",
    notes: str = "",
    delivery_profile: str | None = None,
) -> dict:
    """Milestone bake finalize — pin assembled final only (no Event canonical / Directus)."""
    milestone_dir = milestone_dir.resolve()
    export_bake_path = export_bake_path.resolve()
    if not export_bake_path.is_file():
        raise FileNotFoundError(f"export bake not found: {export_bake_path}")

    stitch_path = milestone_stitch_state_path(milestone_dir)
    stitch_job = job_name or f"milestone_{milestone_dir.name}_stitch"
    pin_result = pin_milestone_standalone_final(
        milestone_dir,
        export_bake_path,
        stitch_state_path=stitch_path,
        job_name=stitch_job,
        delivery_profile=delivery_profile,
    )
    return {
        **pin_result,
        "ok": True,
        "directus_approved": False,
        "asset_id": -1,
        "export_bake_path": str(export_bake_path),
        "stitch_job_name": stitch_job,
        "iteration_notes": iteration_notes,
        "notes": notes,
    }


def finalize_stitch_bake(
    event_dir: Path,
    export_bake_path: Path,
    *,
    module_id: int,
    m_number: int | None = None,
    event_num: int | None = None,
    stitch_state_path: Path | None = None,
    job_name: str | None = None,
    iteration_notes: str = "",
    notes: str = "",
    approve_feedback: str = "Canonical module final pinned from stitch editor bake.",
    approve_alias: str | None = None,
    delivery_profile: str | None = None,
) -> dict:
    """Pin exports bake → canonical MP4, register + approve in Directus."""
    event_dir = event_dir.resolve()
    export_bake_path = export_bake_path.resolve()
    if not export_bake_path.is_file():
        raise FileNotFoundError(f"export bake not found: {export_bake_path}")

    if m_number is None or event_num is None:
        m_number, event_num = resolve_m_and_event_numbers(event_dir)

    event_folder_id = event_dir.name
    stitch_path = stitch_state_path or default_stitch_state_path(event_dir)
    stitch_job = job_name or f"{event_folder_id}_stitch"

    pin_result = pin_canonical_module(
        event_dir,
        export_bake_path,
        m_number=m_number,
        event_id=event_folder_id,
        stitch_state_path=stitch_path,
        delivery_profile=delivery_profile,
    )
    canonical_path = Path(pin_result["canonical_path"])

    from registered_write import approve_asset, register_asset  # noqa: PLC0415

    asset_id, registered_path = register_asset(
        file_path=str(canonical_path),
        asset_type="final_atomic_mp4",
        module_id=module_id,
        event_id=event_num,
        produced_by_skill="stitch-editor",
        iteration_notes=iteration_notes or f"Stitch bake pinned to {canonical_path.name}",
        colloquial_name=pin_result.get("canonical_name") or canonical_path.name,
        library=False,
        notes=notes or f"Canonical module final {canonical_path.name} from {export_bake_path.name}",
    )
    if asset_id == -1:
        raise RuntimeError(
            "Directus registration failed for canonical module final "
            f"(queued to pending_directus_writes.json if offline): {registered_path}"
        )

    canonical_str = str(canonical_path)
    from registered_write import _client  # noqa: PLC0415

    try:
        client = _client()
        client._request(
            "PATCH",
            f"/items/prod_assets/{asset_id}",
            data={
                "file_path": canonical_str,
                "asset_name": canonical_path.stem,
                "event_id": event_num,
                "is_current": True,
            },
        )
        # Supersede other final_atomic_mp4 rows for this module (SHA dedup skips approve scope).
        prior = client._request(
            "GET",
            "/items/prod_assets",
            params={
                "filter": json.dumps({
                    "_and": [
                        {"module_id": {"_eq": module_id}},
                        {"asset_type": {"_eq": "final_atomic_mp4"}},
                        {"id": {"_neq": asset_id}},
                        {"kim_verdict": {"_in": ["approved", "pending"]}},
                    ]
                }),
                "fields": "id,kim_verdict,is_current",
                "limit": "20",
            },
        ).get("data") or []
        for row in prior:
            client._request(
                "PATCH",
                f"/items/prod_assets/{row['id']}",
                data={
                    "kim_verdict": "superseded",
                    "superseded_by_id": asset_id,
                    "is_current": False,
                },
            )
    except Exception as patch_exc:
        raise RuntimeError(
            f"prod_assets id={asset_id} canonical metadata sync failed: {patch_exc}"
        ) from patch_exc

    alias = approve_alias or f"M{m_number} Event {event_num} final"
    directus_approved = approve_asset(
        asset_id,
        approve_feedback,
        alias=alias,
    )
    if not directus_approved:
        raise RuntimeError(
            f"Directus approve_asset failed for prod_assets id={asset_id}"
        )

    return {
        **pin_result,
        "ok": True,
        "asset_id": asset_id,
        "directus_approved": directus_approved,
        "export_bake_path": str(export_bake_path),
        "registered_path": registered_path,
        "stitch_job_name": stitch_job,
        "module_id": module_id,
        "event_num": event_num,
        "m_number": m_number,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pin stitch exports bake as canonical module final + Directus",
    )
    parser.add_argument("--event-dir", type=Path, required=True)
    parser.add_argument("--bake", type=Path, required=True, help="exports/*.mp4 bake to pin")
    parser.add_argument("--module-id", type=int, default=0, help="prod_modules.id (0=resolve from state)")
    parser.add_argument("--m-number", type=int, default=0)
    parser.add_argument("--event-num", type=int, default=0)
    parser.add_argument("--stitch-state", type=Path, default=None)
    args = parser.parse_args()

    event_dir = args.event_dir.resolve()
    bake = args.bake.resolve()
    if not bake.is_file() and (event_dir / bake).is_file():
        bake = (event_dir / bake).resolve()

    m_number = args.m_number or None
    event_num = args.event_num or None
    if m_number is None or event_num is None:
        m_number, event_num = resolve_m_and_event_numbers(event_dir)

    module_id = args.module_id
    if module_id <= 0:
        sys.path.insert(0, str(TOOLS))
        from production_server import StateManager, _resolve_module_id_for_state  # noqa: PLC0415

        module_id = _resolve_module_id_for_state(StateManager(event_dir, event_dir.name))

    result = finalize_stitch_bake(
        event_dir,
        bake,
        module_id=module_id,
        m_number=m_number,
        event_num=event_num,
        stitch_state_path=args.stitch_state,
        iteration_notes=f"CLI finalize {bake.name}",
        notes=f"Kim-confirmed canonical module final from {bake.name}",
        approve_feedback="Kim confirmed Event 1 final module MP4 (stitch bake finalize CLI).",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
