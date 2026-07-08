"""PHASE_B_SEGMENTED_BASE_AUTHORITY_V1 — resume must not swap v6→v4 mid-job."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from phase_b_kling_pause_aligned_segments import PHASE_B_CEDRIC_BASE_15S_CLIP_ID  # noqa: E402
from phase_b_kling_segmented_lipsync import (  # noqa: E402
    PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY,
    PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED,
    PHASE_B_V6_BASE_DURATION_S,
    infer_phase_b_segmented_base_clip,
    resolve_phase_b_segmented_base_clip,
)


def test_legacy_v6_not_swapped_to_v4_when_both_present(tmp_path: Path):
    bases = tmp_path / "bases"
    bases.mkdir()
    v6 = bases / "cedric_idle_newstyle_v6.mp4"
    v4 = bases / f"{PHASE_B_CEDRIC_BASE_15S_CLIP_ID}.mp4"
    v6.write_bytes(b"v6")
    v4.write_bytes(b"v4")
    got = resolve_phase_b_segmented_base_clip(
        bases, "cedric_idle_newstyle_v6",
        strategy=PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY,
    )
    assert got == v6


def test_pause_aligned_v4_selected_uses_v4(tmp_path: Path):
    bases = tmp_path / "bases"
    bases.mkdir()
    v6 = bases / "cedric_idle_newstyle_v6.mp4"
    v4 = bases / f"{PHASE_B_CEDRIC_BASE_15S_CLIP_ID}.mp4"
    v6.write_bytes(b"v6")
    v4.write_bytes(b"v4")
    got = resolve_phase_b_segmented_base_clip(
        bases, PHASE_B_CEDRIC_BASE_15S_CLIP_ID,
        strategy=PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED,
    )
    assert got == v4


def test_infer_base_from_seg0_meta_v6(tmp_path: Path):
    bases = tmp_path / "bases"
    bases.mkdir()
    v6 = bases / "cedric_idle_newstyle_v6.mp4"
    v4 = bases / f"{PHASE_B_CEDRIC_BASE_15S_CLIP_ID}.mp4"
    v6.write_bytes(b"v6")
    v4.write_bytes(b"v4")
    work = tmp_path / "work"
    work.mkdir()
    (work / "seg_0_meta.json").write_text(json.dumps({
        "prep": {"base_duration_s": PHASE_B_V6_BASE_DURATION_S},
    }))
    got = infer_phase_b_segmented_base_clip(
        bases, "cedric_idle_newstyle_v6", work,
    )
    assert got == v6
