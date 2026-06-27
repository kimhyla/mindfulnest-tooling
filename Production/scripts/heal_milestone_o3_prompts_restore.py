#!/usr/bin/env python3
"""One-shot: restore Element/Omni V2 prompts on milestone speak beats (Avatar Pro pollution)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent))

import beat_generator as bg  # noqa: E402


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
    healed = 0
    skipped = 0
    for arc in (data.get("arcs") or {}).values():
        for seg in (arc.get("segments") or {}).values():
            for beat in seg.get("beats") or []:
                if not isinstance(beat, dict) or not _is_speak_beat(beat):
                    continue
                before = (beat.get("kling_o3_prompt") or "").strip()
                if not before:
                    skipped += 1
                    continue
                if dry_run:
                    would = bg.o3_prompt_is_avatar_pro_poisoned(before, beat=beat)
                    if would:
                        healed += 1
                    else:
                        skipped += 1
                    continue
                if bg.heal_avatar_pro_poisoned_o3_prompt(beat, data):
                    healed += 1
                else:
                    skipped += 1
    if not dry_run and healed:
        backup = path.with_suffix(
            f".json.bak_prompt_restore_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        )
        shutil.copy2(path, backup)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"beats_healed": healed, "beats_unchanged": skipped, "dry_run": dry_run}


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
