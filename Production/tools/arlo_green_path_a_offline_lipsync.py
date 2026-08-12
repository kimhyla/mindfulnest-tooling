#!/usr/bin/env python3
"""Offline Phase A Arlo green Path A lipsync proof (scratch only — not Send).

Uses openmouth trimmed still lineage idle + full_size_3 plate.
profile_id is NOT \"arlo\" so validate_arlo_idle_contract does not force
the old full_loop_30s asset.

Build local-first under /tmp, then copy into Event_6/_proof_arlo_green_path_a/.
Never writes phase_a_lipsync_* / production_state.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from arlo_green_path_a_assets import (
    IDLE_FROM_TRIMMED_REL,
    KEY_RGB,
    PLATE_REL,
    assert_send_assets,
)
from layered_character_lipsync import (
    Crop,
    IdleUnit,
    LayeredLipsyncProfile,
    QCRegion,
    Size,
    run_layered_lipsync,
)

ROUTE_ID = "PHASE_A_ARLO_GREEN_STILL_PATH_A_OFFLINE_V1"
PROFILE_ID = "arlo_green_path_a"
KEY_CANVAS_REL = (
    "NEW STYLE CHARACTERS/ARLO/arlo_key_canvas_green_path_a_1920x1080_v1.png"
)
# 0x02EA08 == KEY_RGB (2,234,8) open-mouth pin; closed archive was 0x03F105.
CHROMA = "chromakey=0x{:02X}{:02X}{:02X}:0.20:0.06".format(*KEY_RGB)


def green_path_a_profile() -> LayeredLipsyncProfile:
    """Ephemeral profile for offline proof — not registered in PROFILES yet."""
    r, g, b = KEY_RGB
    return LayeredLipsyncProfile(
        profile_id=PROFILE_ID,
        route_id=ROUTE_ID,
        method_id="layered_green_still_path_a_kling_lipsync_v1",
        provider_content="whole_character",
        placement_mode="full_canvas",
        cutout_mode="key_canvas",
        key_rgb=KEY_RGB,
        plate_relative_path=PLATE_REL,
        cutout_relative_path=KEY_CANVAS_REL,
        idle_units=(
            IdleUnit(
                "openmouth_choke_v5",
                IDLE_FROM_TRIMMED_REL,
                10.041667,
                0.35,
                0.35,
            ),
        ),
        source_size=Size(1920, 1080),
        canvas_size=Size(1920, 1080),
        provider_crop=Crop(0, 0, 1920, 1080),
        provider_input_size=Size(1920, 1080),
        provider_output_size=Size(832, 464),
        placement=Crop(0, 0, 1920, 1080),
        # Self-loop hard-joins when xfade unused; keep small for distinct units.
        xfade_seconds=0.35,
        chroma_filter=CHROMA,
        despill_filter="despill=type=green",
        post_filters="cas=0.4,eq=contrast=1.02:saturation=1.02",
        provider_eye_qc=QCRegion(Crop(350, 125, 150, 95), 6, 0.4, 0.33),
        idle_body_qc=QCRegion(Crop(650, 530, 600, 430), 12, 0.25, 0.5),
        composite_body_qc=QCRegion(Crop(648, 528, 604, 432), 12, 0.25, 0.5),
        boundary_pad_start=1.0,
        boundary_pad_end=2.5,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=None)
    args = parser.parse_args()

    from credentials_lib.credentials import load_wavespeed_api_key

    root = Path(args.production_root).expanduser().resolve()
    preflight = assert_send_assets(root)
    profile = green_path_a_profile()
    work = (
        Path(args.work).expanduser().resolve()
        if args.work
        else Path(tempfile.mkdtemp(prefix="arlo_green_path_a_lip_"))
    )
    work.mkdir(parents=True, exist_ok=True)
    local_out = work / "delivery.mp4"
    # Doppler `prd` currently injects a non-wsk WAVESPEED_API_KEY that WaveSpeed
    # rejects with 401. Prefer a real wsk_ key (env or API_KEYS_MASTER.md).
    env_key = os.environ.get("WAVESPEED_API_KEY", "").strip()
    if env_key.startswith("wsk_"):
        api_key = env_key
    else:
        if env_key:
            print(
                f"[arlo_green_path_a] ignoring non-wsk WAVESPEED_API_KEY "
                f"(len={len(env_key)}); using API_KEYS_MASTER.md",
                flush=True,
            )
            os.environ.pop("WAVESPEED_API_KEY", None)
        api_key = load_wavespeed_api_key(root / "API_KEYS_MASTER.md")
    if not api_key.startswith("wsk_"):
        raise RuntimeError(
            "WaveSpeed key must start with wsk_ "
            f"(got len={len(api_key)} prefix={api_key[:4]!r})"
        )
    print(json.dumps({"preflight": preflight, "work": str(work)}, indent=2), flush=True)

    manifest = run_layered_lipsync(
        profile,
        Path(args.audio).expanduser().resolve(),
        local_out,
        api_key=api_key,
        production_root=root,
        work_dir=work,
    )
    dest = Path(args.output).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_out, dest)
    man_path = dest.with_suffix(".json")
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(dest), "manifest": str(man_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
