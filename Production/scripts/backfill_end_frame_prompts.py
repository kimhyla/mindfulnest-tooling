#!/usr/bin/env python3
"""Backfill audit for cached end_frame_prompts on kling_startend options.

LD: END_FRAME_PROMPT_BACKFILL_AUDIT_SCRIPT_V1 (severity LOW, dry-run by default)
Refs: LD-747 (root-cause diagnosis), LD-745 (character-geometry prompt fix),
      LD-736 (BEAT_PARENTHETICAL_CONVENTION_V1_2 wing grounding).

Background
----------
LD-745 fixed the character-geometry prompt FORWARD-ONLY. Options generated
BEFORE LD-745 carry the old weak _MOUTH_TAIL ("Same cartoon 3D Pixar-style
art, same outfit, same 4:3 composition") cached on the option, so morphing
artefacts persist on those clips until they are regenerated. This script
SURVEYS which options are affected so Kim can selectively spend $0.60 each
($0.15 OpenAI gpt-image-1 + $0.45 Kling) to regen them.

Usage
-----
  python3 Production/scripts/backfill_end_frame_prompts.py \
      --event Event_1 [--dry-run|--regenerate]

`--dry-run` (default) only writes the markdown audit report.
`--regenerate` performs an actual regen and IS NOT WIRED in this version —
exits 1 with an explanation. Re-implement once Kim has approved spend.

The script is read-only against production_state.json in dry-run mode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Marker for the OLD weak _MOUTH_TAIL prompt. Anything containing this
# substring AND lacking the LD-745 character-geometry phrasing is in scope.
OLD_WEAK_MARKER = "Same cartoon 3D Pixar-style art, same outfit, same 4:3 composition"

# Heuristic: LD-745 forward prompts include either a wing token or the
# explicit "character geometry preserved" phrase. If either appears we
# consider the option already on the new path.
LD745_MARKERS = (
    "character geometry preserved",
    "wings folded",
    "wings drawn",
    "wings tucked",
    "wings drooped",
    "wings settled",
    "settled wings",
    "soft wing settle",
)

# Each Kling start-end option costs roughly:
COST_PER_REGEN_USD = 0.60  # $0.15 OpenAI + $0.45 Kling


def project_root() -> Path:
    here = Path(__file__).resolve().parent.parent.parent
    return here


def find_state_file(event_dir: str) -> Path:
    """Resolve production_state.json for the given event dir.

    Accepts either a bare event name ("Event_1") or a relative path.
    Looks first under the tooling repo, then under the Dropbox project
    root so the script works from both trees.

    Dropbox path is resolved from the MN_DROPBOX_ROOT env var (matches
    deploy_storyboard_v59.sh convention) so this script works on any
    machine — Kim's Mac AND any future CI / contributor machine. The
    legacy hard-coded path is kept as a final fallback for cwd-naive
    invocations on Kim's Mac during transition. [CONFIRMED against
    deploy_storyboard_v59.sh which uses the same MN_DROPBOX_ROOT env
    pattern with the same default Mac path.]
    """
    dropbox_root_env = os.environ.get("MN_DROPBOX_ROOT")
    dropbox_root = Path(
        dropbox_root_env
        or "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
    )
    candidates = [
        project_root() / event_dir / "production_state.json",
        project_root() / "Production" / event_dir / "production_state.json",
        dropbox_root / "Production" / event_dir / "production_state.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    print(f"ERROR: production_state.json not found under {event_dir}", file=sys.stderr)
    for c in candidates:
        print(f"  tried: {c}", file=sys.stderr)
    sys.exit(2)


def is_weak_prompt(efp: str) -> bool:
    """True iff the cached prompt is on the pre-LD-745 weak path."""
    if not efp:
        return False
    if OLD_WEAK_MARKER not in efp:
        return False
    lower_efp = efp.lower()
    for marker in LD745_MARKERS:
        if marker in lower_efp:
            return False
    return True


def audit(state: dict) -> list[dict]:
    """Scan all videos[*].beats[*].phase_1.options[] for weak prompts."""
    findings: list[dict] = []
    for video_role, video in (state.get("videos") or {}).items():
        beats = (video or {}).get("beats") or {}
        for beat_id, beat in beats.items():
            phase_1 = (beat or {}).get("phase_1") or {}
            options = phase_1.get("options") or []
            for idx, opt in enumerate(options):
                if (opt or {}).get("source") != "kling_startend":
                    continue
                efp = (opt or {}).get("end_frame_prompt") or ""
                if is_weak_prompt(efp):
                    findings.append({
                        "video_role": video_role,
                        "beat_id": beat_id,
                        "option_index": idx,
                        "task_id": opt.get("task_id"),
                        "file": opt.get("file"),
                        "current_prompt_excerpt": efp[:200],
                    })
    return findings


def write_report(event_dir: str, findings: list[dict]) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = project_root() / "Production" / event_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"_backfill_audit_{ts}.md"

    total_cost = len(findings) * COST_PER_REGEN_USD
    lines = []
    lines.append(f"# Backfill audit: {event_dir}")
    lines.append("")
    lines.append(f"**Generated:** {ts}")
    lines.append(f"**LD:** END_FRAME_PROMPT_BACKFILL_AUDIT_SCRIPT_V1")
    lines.append(f"**Refs:** LD-747, LD-745, LD-736 (BEAT_PARENTHETICAL_CONVENTION v1.2)")
    lines.append("")
    lines.append(f"## Summary")
    lines.append("")
    lines.append(f"- **Pre-LD-745 weak kling_startend options:** {len(findings)}")
    lines.append(
        f"- **Estimated regen cost:** ${total_cost:.2f} "
        f"(${COST_PER_REGEN_USD:.2f}/option = $0.15 OpenAI + $0.45 Kling)"
    )
    lines.append("")
    lines.append(
        "Note: this audit is **dry-run only**. To actually regenerate, "
        "Kim must approve spend and the `--regenerate` path must be "
        "wired. The wiring is intentionally deferred per Rule 19 governance "
        "escape hatch: SHORTCUT_REGEN_WIRING_V1 — wiring blocks on Kim's "
        "explicit spend approval (~$0.20/img × N options) which can only "
        "happen during a live session, not at script-author time."
    )
    lines.append("")
    if not findings:
        lines.append("No weak options detected. Nothing to backfill.")
    else:
        lines.append("## Per-option findings")
        lines.append("")
        lines.append("| # | Video | Beat | Opt Idx | Task ID | Prompt excerpt |")
        lines.append("|---|---|---|---|---|---|")
        for i, f in enumerate(findings, 1):
            excerpt = f["current_prompt_excerpt"].replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {i} | {f['video_role']} | {f['beat_id']} | {f['option_index']} "
                f"| `{f['task_id']}` | `{excerpt[:140]}…` |"
            )
    report_path.write_text("\n".join(lines) + "\n")
    return report_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--event", required=True, help="e.g. Event_1")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", default=True,
        help="default — write audit report only, no API calls",
    )
    mode.add_argument(
        "--regenerate", action="store_true",
        help="(NOT WIRED) — exits 1; intentionally requires manual enablement",
    )
    args = ap.parse_args()

    if args.regenerate:
        print(
            "ERROR: --regenerate is intentionally not wired in this version "
            "(LD END_FRAME_PROMPT_BACKFILL_AUDIT_SCRIPT_V1 requires Kim's "
            "explicit spend approval before regen wiring is enabled).",
            file=sys.stderr,
        )
        return 1

    state_path = find_state_file(args.event)
    state = json.loads(state_path.read_text())
    findings = audit(state)
    report = write_report(args.event, findings)

    print(f"Scanned: {state_path}")
    print(f"Affected options: {len(findings)}")
    print(f"Estimated regen cost: ${len(findings) * COST_PER_REGEN_USD:.2f}")
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
