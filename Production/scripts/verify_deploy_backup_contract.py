#!/usr/bin/env python3
"""Guard deploy-backup restores: beat_generator must export O3 sidecar API."""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REQUIRED_SYMBOLS: tuple[str, ...] = (
    "update_beat_locked",
    "sidecar_file_lock",
    "read_sidecar_locked",
    "write_sidecar_atomic_locked",
    "stash_prior_kling_o3_before_redo",
    "preserve_kling_o3_beat_slot",
    "archive_kling_o3_video_before_redo",
    "pin_kling_o3_beat",
)


def _load_module(path: Path):
    prod_dir = path.resolve().parent.parent
    tools_dir = prod_dir / "tools"
    for entry in (str(prod_dir), str(tools_dir)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    spec = importlib.util.spec_from_file_location("beat_generator_probe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--beat-generator",
        type=Path,
        default=Path("Production/tools/beat_generator.py"),
        help="Path to beat_generator.py to validate",
    )
    args = ap.parse_args()
    path = args.beat_generator.resolve()
    if not path.is_file():
        print(f"FATAL: {path} not found", file=sys.stderr)
        return 1
    mod = _load_module(path)
    missing = [name for name in REQUIRED_SYMBOLS if not callable(getattr(mod, name, None))]
    if missing:
        print(f"FATAL: {path} missing O3 contract symbols: {', '.join(missing)}", file=sys.stderr)
        return 1
    caps = mod.probe_capabilities()
    if not caps.get("update_beat_locked") or not caps.get("sidecar_file_lock"):
        print(f"FATAL: probe_capabilities() reports missing O3 API: {caps}", file=sys.stderr)
        return 1
    print(f"OK  {path} exports O3 sidecar contract ({len(REQUIRED_SYMBOLS)} symbols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
