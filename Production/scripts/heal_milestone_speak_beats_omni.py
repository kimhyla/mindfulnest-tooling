#!/usr/bin/env python3
"""One-shot: milestone speak beats → element_native + clear stale Avatar job busy fields."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _is_speak_beat(beat: dict) -> bool:
    sp = (beat.get("speaker") or "").strip().lower()
    if not sp or sp in ("[stage direction]", "stage direction"):
        return False
    if (beat.get("pipeline") or "").strip() == "still_insert":
        return False
    if (beat.get("beat_render_mode") or "").strip() == "still_insert":
        return False
    return True


def heal_sidecar(path: Path, *, dry_run: bool = False) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    cleared = 0
    for arc in (data.get("arcs") or {}).values():
        for seg in (arc.get("segments") or {}).values():
            for beat in seg.get("beats") or []:
                if not isinstance(beat, dict) or not _is_speak_beat(beat):
                    continue
                for key in (
                    "o3_generate_mode",
                    "generation_mode",
                    "kling_o3_generate_mode",
                ):
                    if beat.get(key) == "avatar_pro":
                        beat[key] = "element_native"
                        changed += 1
                if beat.get("kling_o3_mode") == "o3_avatar_pro_v1":
                    beat["kling_o3_mode"] = "o3_element_native_voice"
                    changed += 1
                for pop_key in (
                    "o3_current_job_id",
                    "kling_o3_voice_fix_ui_job_id",
                    "kling_o3_voice_fix_status",
                    "kling_o3_voice_fix_phase",
                    "kling_o3_voice_fix_attempt_id",
                    "kling_o3_voice_fix_job_pid",
                    "kling_o3_voice_fix_error",
                    "kling_o3_voice_fix_error_code",
                ):
                    if beat.pop(pop_key, None) is not None:
                        cleared += 1
    if not dry_run and (changed or cleared):
        backup = path.with_suffix(
            f".json.bak_omni_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        )
        shutil.copy2(path, backup)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"beats_remodeled": changed, "busy_fields_cleared": cleared, "dry_run": dry_run}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--milestone-dir",
        type=Path,
        default=Path.home()
        / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Milestones/milestone1_arc1",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sidecar = args.milestone_dir / "beat_generator_sidecar.json"
    if not sidecar.is_file():
        raise SystemExit(f"missing sidecar: {sidecar}")
    result = heal_sidecar(sidecar, dry_run=args.dry_run)
    print(json.dumps({"sidecar": str(sidecar), **result}, indent=2))


if __name__ == "__main__":
    main()
