"""Phase B Kling base prep — auto-size from bookend loop unit."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import phase_b_kling_base_prep as prep


def test_kling_submit_bitrate_fits_22mb_for_two_minute_loop():
    bps = prep.kling_submit_video_bitrate_bps(125.0)
    implied_mb = bps * 125.0 / 8 / 1024 / 1024
    assert implied_mb <= prep.WAVESPEED_RAW_MB_CEILING


def test_phases_handler_uses_auto_base_prep():
    src = Path(__file__).resolve().parent.parent / "server_handlers" / "phases.py"
    block = src.read_text(encoding="utf-8").split("def handle_phase_b_lipsync", 1)[1]
    block = block.split("\ndef _write_phase_b_lipsync_complete", 1)[0]
    assert "prep_phase_b_kling_base_video" in block
    assert "auto_loop_bookend_unit" not in block  # strategy lives in prep module
    assert "LipSyncClient" in block


def test_prep_module_exports_auto_unit_code():
    assert prep._PREP_CODE == "PHASE_B_KLING_AUTO_BOOKEND_UNIT_V1"


def test_long_base_is_trimmed_not_looped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "long.mp4"
    base.write_bytes(b"x" * 1000)
    work = tmp_path / "work.mp4"
    monkeypatch.setattr(prep, "_ffprobe_duration", lambda p: 200.0 if p == base else 0.0)
    monkeypatch.setattr(prep, "_trim_to_duration", lambda s, d, t: d)
    monkeypatch.setattr(prep, "_fit_submit_size", lambda s, w, duration_s=0: (s, {"submit_size_mb": 1.0}))

    out, meta = prep.prep_phase_b_kling_base_video(base, 180.0, work)
    assert meta["strategy"] == "trim_long_base"
    assert out == work.with_name(f"{work.stem}_trim{work.suffix}")


def test_short_base_loops_bookend_unit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "short.mp4"
    unit = tmp_path / "cedric_idle_bookend_unit_v1.mp4"
    base.write_bytes(b"x" * 1000)
    unit.write_bytes(b"y" * 1000)
    work = tmp_path / "work.mp4"
    looped = work.with_name(f"{work.stem}_from_unit{work.suffix}")

    def fake_dur(p: Path) -> float:
        if p == base:
            return 10.0
        if p == unit:
            return 29.0
        if p == looped:
            return 183.0
        return 0.0

    monkeypatch.setattr(prep, "_ffprobe_duration", fake_dur)
    monkeypatch.setattr(prep, "resolve_phase_b_loop_unit", lambda _d: unit)
    monkeypatch.setattr(prep, "crossfade_loop_video", lambda s, d, t, xfade_s=0.7: d)
    monkeypatch.setattr(prep, "_fit_submit_size", lambda s, w, duration_s=0: (s, {"submit_size_mb": 2.0}))

    _out, meta = prep.prep_phase_b_kling_base_video(base, 183.0, work, bases_dir=tmp_path)
    assert meta["strategy"] == "auto_loop_bookend_unit"
    assert meta["loop_unit"] == unit.name
