#!/usr/bin/env python3
"""Sync tagged element_sample_lines + voice_sample_lock from kling_voice_sample_lock defaults.

Preserves locked_speed and proven_o3_bind. Does not mint new kling_voice_id — run
setup_all_kling_character_voices.py --refresh-voice after this when sample text changed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD = HERE.parent
TOOLS = PROD / "tools"
sys.path.insert(0, str(PROD))
sys.path.insert(0, str(TOOLS))

from kling_voice_sample_lock import (  # noqa: E402
    DEFAULT_ELEMENT_SAMPLE_LINES,
    apply_voice_sample_lock,
    join_element_sample_lines,
    resolve_element_sample_text,
    validate_voice_onboarding_before_spend,
)
from tools import kling_character_registry as reg  # noqa: E402

SKIP_CHARS = frozenset()


def sync_character(name: str, cfg: dict, *, dry_run: bool) -> list[str]:
    if name in SKIP_CHARS:
        return [f"{name}: skipped (operator keep-as-is)"]
    if cfg.get("status") != "active" or not cfg.get("kling_voice_id"):
        return [f"{name}: skipped (not active with voice)"]
    defaults = DEFAULT_ELEMENT_SAMPLE_LINES.get(name)
    if not defaults:
        return [f"{name}: no DEFAULT_ELEMENT_SAMPLE_LINES — manual only"]

    lock = dict(cfg.get("voice_sample_lock") or {})
    locked_speed = float(lock.get("locked_speed") or cfg.get("audition_speed") or 1.0)
    audition = str(lock.get("audition_line") or cfg.get("audition_line") or defaults[0]).strip()
    session_id = str(lock.get("session_id") or f"tag_sync_{datetime.now(timezone.utc).strftime('%Y%m%d')}")

    updated = apply_voice_sample_lock(
        name,
        dict(cfg),
        locked_speed=locked_speed,
        audition_line=audition,
        element_sample_lines=list(defaults),
        session_id=session_id,
    )
    updated["element_sample_lines"] = list(defaults)
    updated["element_sample_text"] = join_element_sample_lines(defaults)
    if cfg.get("elevenlabs_voice_sample_path"):
        updated["elevenlabs_voice_sample_path"] = cfg["elevenlabs_voice_sample_path"]

    before_fp = (lock.get("sample_text_fingerprint") or "")
    after_fp = updated["voice_sample_lock"]["sample_text_fingerprint"]
    text_changed = resolve_element_sample_text(name, cfg) != resolve_element_sample_text(name, updated)

    if not dry_run:
        data = reg.load_character_subjects()
        data.setdefault("characters", {})[name] = updated
        reg.save_character_subjects(data)

    errs = validate_voice_onboarding_before_spend(name, updated)
    lines = [
        f"{name}: tagged lines synced locked_speed={locked_speed} fp {before_fp}→{after_fp}"
        + (" NEEDS_VOICE_REFRESH" if text_changed else " text_unchanged"),
    ]
    if errs:
        lines.append(f"  onboarding remaining: {errs[0]}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync tagged voice sample lines from code defaults")
    parser.add_argument("--char", action="append", help="Single character (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reg.set_prod_root(PROD)
    targets = args.char or [
        n
        for n, c in (reg.load_character_subjects().get("characters") or {}).items()
        if c.get("status") == "active" and c.get("kling_voice_id")
    ]
    for name in targets:
        cfg = reg.get_character_entry(name) or {}
        for line in sync_character(name, cfg, dry_run=args.dry_run):
            print(line)


if __name__ == "__main__":
    main()
