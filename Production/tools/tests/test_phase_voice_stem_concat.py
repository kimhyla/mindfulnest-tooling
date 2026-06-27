"""PHASE_VOICE_STEM_CONCAT_V1 — pause markers + PCM-safe stem concat."""
from __future__ import annotations

from server_handlers import phases as ph


def test_manifest_whiteout_hold_zero_is_not_falsy_default():
    from teleport_intro_kit import _manifest_whiteout_hold_s  # noqa: WPS433

    assert _manifest_whiteout_hold_s({"clip_b_whiteout_hold_s": 0}) == 0.0
    assert _manifest_whiteout_hold_s({}) == 2.5

    script = (
        "Hello world. [pause][pause] Next sentence. "
        "[silence:1.5s] After long pause."
    )
    parts = ph._parse_silence_segments(script)
    assert parts[0] == ("text", "Hello world.")
    assert parts[1] == ("pause", ph.PHASE_VOICE_STEM_PAUSE_DEFAULT_S)
    assert parts[2] == ("pause", ph.PHASE_VOICE_STEM_PAUSE_DEFAULT_S)
    assert parts[3][0] == "text"
    assert "Next sentence." in parts[3][1]
    assert parts[4] == ("timed_silence", 1.5)
    assert parts[5][0] == "text"


def test_export_to_stitcher_seeds_canonical_trim_before_concat():
    src = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "server_handlers"
        / "kling_o3.py"
    )
    text = src.read_text(encoding="utf-8")
    prepare = text.split("def _prepare_bg_export_request", 1)[1].split("\ndef ", 1)[0]
    run = text.split("def _run_bg_export_to_stitcher_core", 1)[1].split("\ndef ", 1)[0]
    assert "seed_canonical_intro_tail_export_trim" in prepare
    assert "concat_kling_o3_approved_beats" in run
