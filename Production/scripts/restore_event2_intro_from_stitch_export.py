#!/usr/bin/env python3
"""Restore Event_2 intro beat list + order to match latest Send-to-Stitcher export."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
_TOOLS = _SCRIPT.parent.parent / "tools"
_ROOT = _SCRIPT.parent.parent
for p in (_TOOLS, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import beat_generator as bg  # noqa: E402
from lib.paths import dropbox_root  # noqa: E402

PROD = dropbox_root() / "Production"
EVENT_DIR = PROD / "Event_2"
EXPORT_JOB = EVENT_DIR / "bg_export_stitcher_jobs/c7716b65-aad.json"
SESSION_TMP = PROD / "tmp23ngf_fn.tmp"
EXPORT_MP4 = EVENT_DIR / "assembled/intro_kling_o3_20260622T230816Z.mp4"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _beat_index(obj) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if isinstance(obj, dict):
        if obj.get("beat_id"):
            out[str(obj["beat_id"])] = obj
        for v in obj.values():
            out.update(_beat_index(v))
    elif isinstance(obj, list):
        for item in obj:
            out.update(_beat_index(item))
    return out


def _resolve_beat(
    beat_id: str,
    *,
    current: dict[str, dict],
    session: dict[str, dict],
) -> dict:
    if beat_id in current:
        return copy.deepcopy(current[beat_id])
    if beat_id in session:
        return copy.deepcopy(session[beat_id])
    raise KeyError(beat_id)


def main() -> int:
    if not EXPORT_JOB.is_file():
        raise SystemExit(f"missing export job: {EXPORT_JOB}")
    job = _load_json(EXPORT_JOB)
    beat_ids = list(job.get("beat_ids") or [])
    if not beat_ids:
        raise SystemExit("export job has no beat_ids")

    session_beats = _beat_index(_load_json(SESSION_TMP)) if SESSION_TMP.is_file() else {}
    bg.init_bg_paths(EVENT_DIR)
    sidecar_now = bg.read_sidecar()
    current_pre = {
        b["beat_id"]: b
        for b in sidecar_now["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
        if b.get("beat_id")
    }

    missing: list[str] = []
    ordered: list[dict] = []
    for bid in beat_ids:
        try:
            ordered.append(_resolve_beat(bid, current=current_pre, session=session_beats))
        except KeyError:
            missing.append(bid)

    if missing:
        raise SystemExit(f"missing beat rows for export order: {missing}")

    export_path = str(job.get("result", {}).get("video_path") or "")
    export_dur = float(job.get("result", {}).get("duration_s") or 0)

    def _mutator(sidecar: dict) -> None:
        seg = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]
        seg["beats"] = ordered
        sidecar["active_context"] = {"arc_number": 1, "event_id": "2", "phase": "pre"}
        runtime = sidecar.setdefault("_runtime", {})
        runtime["event2_intro_restored_from_export"] = {
            "job_id": job.get("job_id"),
            "beat_ids": beat_ids,
            "video_path": export_path,
            "duration_s": export_dur,
        }

    bg.mutate_sidecar_locked(_mutator)
    bg.flush_sidecar_mirror_export()

    print(
        json.dumps(
            {
                "ok": True,
                "beat_count": len(ordered),
                "beat_ids": beat_ids,
                "export_mp4_exists": EXPORT_MP4.is_file(),
                "export_duration_s": export_dur,
                "removed_from_segment": sorted(set(current_pre) - set(beat_ids)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
