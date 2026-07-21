#!/usr/bin/env python3
"""Arlo wrapper for the shared layered green-screen lipsync engine."""
from __future__ import annotations

import sys
from pathlib import Path

from layered_character_lipsync import (
    ARLO_PROFILE,
    LayeredLipsyncProfile,
    resolve_production_root,
    run_layered_lipsync,
    validate_assets,
)

ARLO_LAYERED_LIPSYNC_PROFILE = ARLO_PROFILE


def validate_arlo_layered_assets(
    production_root: Path | None = None,
    *,
    event_dir: Path | None = None,
    profile: LayeredLipsyncProfile = ARLO_PROFILE,
) -> None:
    validate_assets(
        profile,
        resolve_production_root(production_root, event_dir=event_dir),
    )


def run_arlo_layered_lipsync(
    audio_path: Path,
    out_path: Path,
    *,
    api_key: str,
    production_root: Path | None = None,
    event_dir: Path | None = None,
    work_dir: Path | None = None,
    profile: LayeredLipsyncProfile = ARLO_PROFILE,
) -> dict:
    """Run isolated Arlo layered lipsync; no server route is wired here."""
    return run_layered_lipsync(
        profile,
        audio_path,
        out_path,
        api_key=api_key,
        production_root=production_root,
        event_dir=event_dir,
        work_dir=work_dir,
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-root", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()

    from credentials_lib.credentials import load_wavespeed_api_key

    try:
        api_key = load_wavespeed_api_key(
            args.production_root / "API_KEYS_MASTER.md"
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        run_arlo_layered_lipsync(
            args.audio,
            args.output,
            api_key=api_key,
            production_root=args.production_root,
            work_dir=args.work,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"[arlo_layered_lipsync] FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
