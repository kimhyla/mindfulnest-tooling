#!/usr/bin/env python3
"""Register all Beat Gen characters: ElevenLabs sample → Kling create-voice → Element.

Usage:
  python3 scripts/setup_all_kling_character_voices.py              # pending only
  python3 scripts/setup_all_kling_character_voices.py --char Chipper
  python3 scripts/setup_all_kling_character_voices.py --force        # re-register all
  python3 scripts/setup_all_kling_character_voices.py --samples-only # copy/generate MP3s only

Cost: ~$0.035 create-voice + $0.01 element per character (~$0.50 for all 11).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
TOOLS_DIR = PROD_ROOT / "tools"
if str(PROD_ROOT) not in sys.path:
    sys.path.insert(0, str(PROD_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib.credential_store import get_secret  # noqa: E402
from kling_element_voice import (  # noqa: E402
    ELEVENLABS_VOICE_ROSTER,
    ensure_voice_sample,
    setup_character_voice,
)
from kling_voice_sample_lock import validate_lock_before_register  # noqa: E402
from tools import kling_character_registry as reg  # noqa: E402


def _merge_roster_metadata(data: dict) -> None:
    """Ensure every character has elevenlabs_voice_id/name from locked roster."""
    chars = data.get("characters") or {}
    for name, roster in ELEVENLABS_VOICE_ROSTER.items():
        if name not in chars:
            continue
        chars[name]["elevenlabs_voice_id"] = roster["elevenlabs_voice_id"]
        chars[name]["elevenlabs_voice_name"] = roster["elevenlabs_voice_name"]
    data["characters"] = chars
    data["_note"] = (
        "Kling Elements + ElevenLabs create-voice registry. "
        "Setup: scripts/setup_all_kling_character_voices.py. "
        "Beat Gen requires active element_id per dialogue speaker (O3 Pro + bound voice)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup Kling Elements with ElevenLabs voices")
    parser.add_argument("--char", help="Single character only")
    parser.add_argument("--force", action="store_true", help="Re-register even if active")
    parser.add_argument("--samples-only", action="store_true", help="Only ensure kling_voice_samples/")
    parser.add_argument(
        "--skip-lock-check",
        action="store_true",
        help="Allow --force without voice_sample_lock (dev/emergency only)",
    )
    args = parser.parse_args()

    wavespeed_key = get_secret("WAVESPEED_API_KEY")
    if not wavespeed_key and not args.samples_only:
        sys.exit("FATAL: WAVESPEED_API_KEY not found")

    elevenlabs_key = get_secret("ELEVENLABS_API_KEY")

    data = reg.load_character_subjects()
    _merge_roster_metadata(data)
    chars = data.get("characters") or {}

    if args.char:
        matches = [k for k in chars if k.lower() == args.char.lower()]
        if not matches:
            sys.exit(f"Unknown character: {args.char!r}")
        targets = {matches[0]: chars[matches[0]]}
    else:
        targets = chars

    ok = failed = skipped = 0

    for char_name, cfg in targets.items():
        if char_name not in ELEVENLABS_VOICE_ROSTER:
            print(f"\nSkipping {char_name}: not in ElevenLabs roster")
            skipped += 1
            continue

        if cfg.get("status") == "active" and cfg.get("element_id") and not args.force:
            print(f"\nSkipping {char_name}: already active (element_id={cfg['element_id']})")
            skipped += 1
            continue

        print(f"\n{'='*50}\n{char_name}")

        needs_lock = not args.skip_lock_check and (
            args.force or cfg.get("status") != "active" or not cfg.get("element_id")
        )
        if needs_lock and not args.samples_only:
            lock_errors = validate_lock_before_register(char_name, cfg)
            if lock_errors:
                for err in lock_errors:
                    print(f"  BLOCKED: {err}")
                failed += 1
                continue
        elif needs_lock and args.samples_only and args.force:
            lock_errors = validate_lock_before_register(char_name, cfg)
            if lock_errors:
                for err in lock_errors:
                    print(f"  BLOCKED: {err}")
                failed += 1
                continue

        try:
            if args.samples_only:
                sample = ensure_voice_sample(
                    char_name, cfg, elevenlabs_key, force_regenerate=args.force,
                )
                rel = f"kling_voice_samples/{sample.name}"
                cfg["elevenlabs_voice_sample_path"] = rel
                cfg["elevenlabs_voice_id"] = ELEVENLABS_VOICE_ROSTER[char_name]["elevenlabs_voice_id"]
                cfg["elevenlabs_voice_name"] = ELEVENLABS_VOICE_ROSTER[char_name]["elevenlabs_voice_name"]
                chars[char_name] = cfg
                print(f"  sample: {rel}")
                ok += 1
                continue

            updated = setup_character_voice(
                char_name, cfg, wavespeed_key, elevenlabs_key, force=args.force,
            )
            chars[char_name] = updated
            data["characters"] = chars
            reg.save_character_subjects(data)
            print(f"  OK element_id={updated['element_id']} kling_voice_id={updated['kling_voice_id']}")
            ok += 1
        except Exception as exc:
            print(f"  FAIL: {exc}")
            failed += 1

    if args.samples_only:
        data["characters"] = chars
        reg.save_character_subjects(data)

    print(f"\n{'='*50}\nDone. OK={ok} skipped={skipped} failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
