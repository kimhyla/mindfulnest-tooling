"""Phase B Avatar Pro contract tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from phase_b_avatar_lipsync import (
    AVATAR_PRO_PROHIBIT,
    AVATAR_USD_PER_SEC,
    CANONICAL_CEDRIC_STILL_REL,
    PHASE_B_LIPSYNC_METHOD_AVATAR,
    PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
    STATIC_BG_PROMPT,
    estimate_avatar_pro_usd,
    resolve_phase_b_cedric_still,
)


def test_estimate_avatar_pro_usd_matches_measured_job():
    # Event_2 chunk-0: $2.9257 / 26.074467s
    assert AVATAR_USD_PER_SEC == pytest.approx(0.1122, rel=1e-3)
    assert estimate_avatar_pro_usd(26.074467) == pytest.approx(2.9257, rel=0.01)
    assert estimate_avatar_pro_usd(123.82) == pytest.approx(13.89, rel=0.02)


def test_resolve_phase_b_cedric_still(tmp_path: Path):
    still = tmp_path / CANONICAL_CEDRIC_STILL_REL
    still.parent.mkdir(parents=True, exist_ok=True)
    still.write_bytes(b"\x89PNG\r\n\x1a\n")
    got = resolve_phase_b_cedric_still(tmp_path)
    assert got == still.resolve()


def test_resolve_phase_b_cedric_still_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_phase_b_cedric_still(tmp_path)


def test_phase_b_lipsync_method_constant():
    assert PHASE_B_LIPSYNC_METHOD_AVATAR == "kling_avatar_pro_v1"
    assert PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM == "single_full_stem_v1"


def test_static_bg_prompt_includes_avatar_pro_prohibit():
    import hashlib

    from phase_b_avatar_lipsync import PHASE_B_STATIC_BG_PROMPT_SHA256

    assert hashlib.sha256(STATIC_BG_PROMPT.encode()).hexdigest() == PHASE_B_STATIC_BG_PROMPT_SHA256
    assert AVATAR_PRO_PROHIBIT in STATIC_BG_PROMPT
    assert "no Chinese characters" in STATIC_BG_PROMPT
    assert "no subtitles" in STATIC_BG_PROMPT
    assert "AUDIO-TO-TEXT PROHIBIT" in STATIC_BG_PROMPT
    assert "baked into the input still" in STATIC_BG_PROMPT
    assert "TRIPOD LOCK" in STATIC_BG_PROMPT
    assert "wooden mug" in STATIC_BG_PROMPT
    assert "subtle breathing" in STATIC_BG_PROMPT
    assert "small hand gestures" in STATIC_BG_PROMPT
    assert "Do NOT animate steam" in STATIC_BG_PROMPT
    assert "lively storyteller energy" not in STATIC_BG_PROMPT
    assert "Generous upper-body" not in STATIC_BG_PROMPT
    assert "firelit" in STATIC_BG_PROMPT.lower()


def test_full_stem_runner_supports_resume_task_id_flag():
    src = (Path(__file__).resolve().parent.parent / "run_phase_b_avatar_full_stem_production.py").read_text(
        encoding="utf-8",
    )
    assert "--resume-task-id" in src
    assert "resume poll task_id" in src
