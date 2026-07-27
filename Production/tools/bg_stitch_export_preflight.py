"""BG_STITCH_EXPORT_PREFLIGHT_V1 — shared Send-to-Stitcher preflight manifest."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BG_STITCH_EXPORT_PREFLIGHT_V1 = "BG_STITCH_EXPORT_PREFLIGHT_V1"


def _resolved_clip_basename_hint(beat: dict, event_dir: Path) -> str | None:
    from beat_generator import beat_magic_still_clip_path  # noqa: PLC0415

    magic = beat_magic_still_clip_path(beat, event_dir)
    if magic and Path(magic).is_file():
        return Path(magic).name
    vp = str(beat.get("kling_o3_video_path") or "").strip()
    if vp and Path(vp).is_file():
        return Path(vp).name
    return None


def _segment_export_errors(beats: list[dict], *, event_dir: Path) -> list[dict[str, str]]:
    import beat_generator as bg  # noqa: PLC0415
    from o3_gallery_option_identity import (  # noqa: PLC0415
        O3GalleryExportAuthorityError,
        assert_beat_export_gallery_authority,
        normalize_o3_gallery_options,
    )

    segment_errors: list[dict[str, str]] = []
    beats_copy = copy.deepcopy(beats)
    _trim_changed, trim_errors = bg.prepare_beats_for_stitch_export(
        beats_copy, event_dir=event_dir,
    )
    for err in trim_errors:
        beat_id = err.split(":", 1)[0] if ":" in err else ""
        if bg.KLING_O3_DURATION_UNREADABLE_V1 in err:
            segment_errors.append(
                {
                    "code": "DURATION_UNREADABLE",
                    "beat_id": beat_id,
                    "message": err,
                    "fix_instruction": (
                        f"Clip duration unreadable for {beat_id} "
                        "(Dropbox File Provider busy). Hard-refresh Beat Gen so the "
                        "local cache warms, then retry Send to Stitcher."
                        if beat_id
                        else "Clip duration unreadable (Dropbox busy). "
                        "Hard-refresh Beat Gen, then retry Send to Stitcher."
                    ),
                }
            )
            continue
        segment_errors.append(
            {
                "code": "EXPORT_TRIM_AUTHORITY",
                "beat_id": beat_id,
                "message": err,
                "fix_instruction": (
                    f"Open {beat_id}, align option trim with beat trim (Apply Trim), "
                    "then retry Send to Stitcher."
                    if beat_id
                    else "Fix trim authority drift on the blocking beat, then retry Send to Stitcher."
                ),
            }
        )
    for beat in beats_copy:
        normalize_o3_gallery_options(beat)
        try:
            assert_beat_export_gallery_authority(beat)
        except O3GalleryExportAuthorityError as exc:
            beat_id = str(beat.get("beat_id") or "")
            segment_errors.append(
                {
                    "code": "EXPORT_GALLERY_AUTHORITY",
                    "beat_id": beat_id,
                    "message": str(exc),
                    "fix_instruction": (
                        f"Open {beat_id}, re-select the active delivery clip in the option tile, "
                        "then retry Send to Stitcher."
                        if beat_id
                        else "Fix gallery authority on the blocking beat, then retry Send to Stitcher."
                    ),
                }
            )
    return segment_errors


def build_bg_stitch_export_preflight_manifest(
    *,
    arc_number: int,
    event_id: str,
    phase: str,
    slot_key: str,
    beats: list[dict],
    event_dir: str | Path,
) -> dict[str, Any]:
    from kling_stitch_readiness import (  # noqa: PLC0415
        beat_kling_stitch_export_ready,
        beat_stitch_export_block_info,
        short_beat_label,
    )

    event_dir = Path(event_dir)
    beat_rows: list[dict[str, Any]] = []
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        beat_id = str(beat.get("beat_id") or "")
        ready = beat_kling_stitch_export_ready(beat, event_dir)
        block = beat_stitch_export_block_info(beat, event_dir) if not ready else None
        row: dict[str, Any] = {
            "beat_id": beat_id,
            "beat_label": short_beat_label(beat_id),
            "ready": ready,
            "resolved_clip_basename": _resolved_clip_basename_hint(beat, event_dir),
        }
        if block:
            row.update(block)
        beat_rows.append(row)

    segment_errors = _segment_export_errors(beats, event_dir=event_dir)
    beats_ready = all(r["ready"] for r in beat_rows) if beat_rows else False
    return {
        "code": BG_STITCH_EXPORT_PREFLIGHT_V1,
        "ready": beats_ready and not segment_errors,
        "arc_number": arc_number,
        "event_id": event_id,
        "phase": phase,
        "slot_key": slot_key,
        "beats": beat_rows,
        "segment_errors": segment_errors,
    }


def append_bg_stitch_export_preflight_audit(event_dir: str | Path, manifest: dict[str, Any]) -> None:
    event_dir = Path(event_dir)
    if not event_dir.is_dir():
        return
    path = event_dir / "_bg_stitch_export_preflight.jsonl"
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ready": manifest.get("ready"),
        "slot_key": manifest.get("slot_key"),
        "phase": manifest.get("phase"),
        "event_id": manifest.get("event_id"),
        "blocking_beats": [
            b.get("beat_id")
            for b in (manifest.get("beats") or [])
            if isinstance(b, dict) and not b.get("ready")
        ],
        "segment_error_codes": [
            e.get("code") for e in (manifest.get("segment_errors") or []) if isinstance(e, dict)
        ],
    }
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"[BG] preflight audit append failed: {exc}", flush=True)


def preflight_error_message(manifest: dict[str, Any]) -> str:
    parts: list[str] = []
    for beat in manifest.get("beats") or []:
        if not isinstance(beat, dict) or beat.get("ready"):
            continue
        fix = str(beat.get("fix_instruction") or beat.get("block_label") or "").strip()
        if fix:
            parts.append(fix)
    for err in manifest.get("segment_errors") or []:
        if not isinstance(err, dict):
            continue
        fix = str(err.get("fix_instruction") or err.get("message") or "").strip()
        if fix:
            parts.append(fix)
    return " ".join(parts) if parts else "Segment is not ready for Send to Stitcher."
