"""PHASE_B_SEGMENTED_TIMELINE_ASSEMBLE_V1 — meta-driven chunk windows."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from phase_b_segmented_timeline_assemble import (  # noqa: E402
    PHASE_B_SEGMENTED_TIMELINE_ASSEMBLE_V1,
    _load_chunk_specs,
)


def test_load_chunk_specs_from_meta_not_resegment(tmp_path: Path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    audio = tmp_path / "stem.mp3"
    audio.write_bytes(b"x")

    windows = [
        (0, 0.58, 24.46),
        (1, 25.67, 53.63),
        (2, 58.15, 85.46),
    ]
    for idx, start_s, end_s in windows:
        raw = work / f"seg_{idx}_kling_raw.mp4"
        raw.write_bytes(b"\x00" * 200_000)
        meta = work / f"seg_{idx}_meta.json"
        meta.write_text(
            json.dumps({"start_s": start_s, "end_s": end_s}) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "phase_b_segmented_timeline_assemble.ffprobe_duration",
        lambda _p: 178.44,
    )
    audio_dur, rows = _load_chunk_specs(work, audio)
    assert audio_dur == 178.44
    assert len(rows) == 3
    assert rows[1]["start_s"] == 25.67
    assert rows[1]["end_s"] == 53.63
    assert rows[2]["start_s"] == 58.15


def test_timeline_assemble_code_constant():
    assert "TIMELINE_ASSEMBLE" in PHASE_B_SEGMENTED_TIMELINE_ASSEMBLE_V1


def test_segmented_resume_wires_timeline_assemble():
    src = (TOOLS / "phase_b_kling_segmented_lipsync.py").read_text(encoding="utf-8")
    assert "assemble_segmented_timeline" in src
    assert "_concat_segment_raws(segment_paths, concat_tmp" not in src
