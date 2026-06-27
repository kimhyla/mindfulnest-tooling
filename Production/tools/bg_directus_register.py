#!/usr/bin/env python3
"""BG_DIRECTUS_EXPORT_V1 — write-time Directus registration on Send to Stitcher.

Registers the exact clip files exported to Stitcher (active ``kling_o3_video_path``
/ trim-materialized export path per beat) plus the segment concat MP4.
No Dropbox watcher — hooks only from ``handle_bg_export_to_stitcher``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BG_DIRECTUS_EXPORT_V1 = "BG_DIRECTUS_EXPORT_V1"

_EVENT_DIR_NUM_RE = re.compile(r"^Event_(\d+)$", re.I)


def event_num_from_dir(event_dir: str | Path) -> int | None:
    """``Event_2`` → ``2`` for prod_assets.event_id FK."""
    name = Path(event_dir).name
    m = _EVENT_DIR_NUM_RE.match(name)
    if m:
        return int(m.group(1))
    return None


def _register_beat_export_clip(
    *,
    beat: dict,
    clip_path: Path,
    module_id: int,
    event_num: int | None,
    slot_key: str,
    phase: str,
) -> dict[str, Any]:
    from registered_write import approve_asset, register_asset  # noqa: PLC0415

    beat_id = str(beat.get("beat_id") or "?")
    now = datetime.now(timezone.utc).isoformat()
    out: dict[str, Any] = {
        "beat_id": beat_id,
        "clip_path": str(clip_path.resolve()),
        "asset_id": -1,
        "approved": False,
        "registered_at": now,
        "warning": None,
    }
    if not clip_path.is_file():
        out["warning"] = f"missing export clip: {clip_path}"
        return out

    selected_key = str(beat.get("kling_o3_selected_option_key") or "").strip()
    iteration = (
        f"[{now}] BG Send to Stitcher — active export clip for {beat_id}. "
        f"slot={slot_key} phase={phase} "
        f"selected_option={selected_key or 'n/a'} "
        f"source_video={beat.get('kling_o3_video_path') or 'n/a'}"
    )
    try:
        asset_id, _ = register_asset(
            file_path=str(clip_path),
            asset_type="beat_scene",
            module_id=module_id,
            event_id=event_num,
            beat_id=beat_id,
            produced_by_skill="bg_export_to_stitcher",
            iteration_notes=iteration,
            role=slot_key,
            colloquial_name=f"{beat_id} stitch export",
            tags=["beat_gen", "bg_export_to_stitcher", slot_key, phase, beat_id],
            notes=f"Materialized export clip sent to Stitcher slot {slot_key}",
        )
    except Exception as exc:
        out["warning"] = f"register_asset failed: {exc}"
        return out

    out["asset_id"] = int(asset_id)
    if asset_id > 0:
        out["approved"] = approve_asset(
            asset_id,
            "Send to Stitcher — active highlighted clip exported to stitch slot",
            alias=f"{beat_id} stitch export",
        )
    elif asset_id == -1:
        out["warning"] = "Directus offline — queued to pending_directus_writes.json"
    return out


def _register_segment_concat(
    *,
    concat_path: Path,
    module_id: int,
    event_num: int | None,
    slot_key: str,
    phase: str,
    beat_ids: list[str],
    boundaries: list[dict],
    duration_s: float,
    parent_asset_ids: list[int],
) -> dict[str, Any]:
    from registered_write import register_asset  # noqa: PLC0415

    now = datetime.now(timezone.utc).isoformat()
    out: dict[str, Any] = {
        "asset_id": -1,
        "clip_path": str(concat_path.resolve()),
        "registered_at": now,
        "warning": None,
    }
    if not concat_path.is_file():
        out["warning"] = f"missing concat: {concat_path}"
        return out

    parent_id = next((i for i in parent_asset_ids if i > 0), None)
    iteration = (
        f"[{now}] BG Send to Stitcher segment concat. slot={slot_key} phase={phase} "
        f"beats={beat_ids} duration_s={duration_s:.3f} "
        f"boundaries={len(boundaries)} parent_beat_assets={parent_asset_ids}"
    )
    try:
        asset_id, _ = register_asset(
            file_path=str(concat_path),
            asset_type="scene_concat_mp4",
            module_id=module_id,
            event_id=event_num,
            beat_id=None,
            parent_asset_id=parent_id,
            produced_by_skill="bg_export_to_stitcher",
            iteration_notes=iteration,
            role=slot_key,
            colloquial_name=f"{Path(concat_path.parent.parent.name)}_{slot_key}_bg_export",
            tags=["beat_gen", "bg_export_to_stitcher", "scene_concat", slot_key, phase],
            notes=f"Beat Gen Send to Stitcher concat for {slot_key}",
        )
        out["asset_id"] = int(asset_id)
        if asset_id == -1:
            out["warning"] = "Directus offline — queued to pending_directus_writes.json"
    except Exception as exc:
        out["warning"] = f"register_asset failed: {exc}"
    return out


def register_bg_export_to_directus(
    *,
    beats: list[dict],
    clip_paths: list[Path],
    concat_path: Path,
    module_id: int,
    event_dir: str | Path,
    slot_key: str,
    phase: str,
    boundaries: list[dict],
    duration_s: float,
) -> dict[str, Any]:
    """Register per-beat export clips + segment concat. Never raises — returns audit dict."""
    event_num = event_num_from_dir(event_dir)
    exported_at = datetime.now(timezone.utc).isoformat()
    beat_results: list[dict[str, Any]] = []
    parent_ids: list[int] = []

    if len(beats) != len(clip_paths):
        return {
            "code": BG_DIRECTUS_EXPORT_V1,
            "exported_at": exported_at,
            "error": f"beat/clip count mismatch: {len(beats)} vs {len(clip_paths)}",
            "beats": [],
            "concat": None,
        }

    for beat, clip in zip(beats, clip_paths):
        row = _register_beat_export_clip(
            beat=beat,
            clip_path=clip,
            module_id=module_id,
            event_num=event_num,
            slot_key=slot_key,
            phase=phase,
        )
        beat_results.append(row)
        aid = int(row.get("asset_id") or -1)
        if aid > 0:
            parent_ids.append(aid)

    beat_ids = [str(b.get("beat_id") or "?") for b in beats]
    concat_result = _register_segment_concat(
        concat_path=concat_path,
        module_id=module_id,
        event_num=event_num,
        slot_key=slot_key,
        phase=phase,
        beat_ids=beat_ids,
        boundaries=boundaries,
        duration_s=duration_s,
        parent_asset_ids=parent_ids,
    )

    warnings = [
        w for w in (
            [r.get("warning") for r in beat_results if r.get("warning")]
            + ([concat_result.get("warning")] if concat_result.get("warning") else [])
        )
        if w
    ]

    return {
        "code": BG_DIRECTUS_EXPORT_V1,
        "exported_at": exported_at,
        "event_num": event_num,
        "beats": beat_results,
        "concat": concat_result,
        "warnings": warnings,
        "registered_beat_count": sum(1 for r in beat_results if int(r.get("asset_id") or -1) > 0),
        "concat_asset_id": int(concat_result.get("asset_id") or -1),
    }


def persist_directus_export_on_sidecar(
    sidecar: dict,
    *,
    arc_number: int,
    event_id: str,
    phase: str,
    directus_result: dict[str, Any],
) -> None:
    """Write Directus ids onto segment beats + segment metadata (caller holds sidecar lock)."""
    import beat_generator as bg  # noqa: PLC0415

    seg = bg.get_seg_entry(sidecar, arc_number, event_id, phase)
    by_beat = {str(r.get("beat_id")): r for r in directus_result.get("beats") or []}
    for beat in seg.get("beats") or []:
        if not isinstance(beat, dict):
            continue
        bid = str(beat.get("beat_id") or "")
        row = by_beat.get(bid)
        if not row:
            continue
        aid = int(row.get("asset_id") or -1)
        if aid > 0:
            beat["directus_asset_id"] = aid
            beat["directus_registered_at"] = row.get("registered_at")
            beat["directus_export_clip_path"] = row.get("clip_path")
    concat_id = int(directus_result.get("concat_asset_id") or -1)
    if concat_id > 0:
        seg["directus_segment_concat_asset_id"] = concat_id
        seg["directus_segment_export_at"] = directus_result.get("exported_at")
