"""PHASE_B_SEGMENTED_TIMELINE_ASSEMBLE_V1 — meta-driven chunk windows."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from phase_b_segmented_timeline_assemble import (  # noqa: E402
    PHASE_B_KLING_TIMELINE_GAP_XFADE_S,
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
    assert "PHASE_B_KLING_TIMELINE_GAP_XFADE_S" in src
    assert "_concat_segment_raws(segment_paths, concat_tmp" not in src


def test_kling_timeline_gap_xfade_disabled():
    assert PHASE_B_KLING_TIMELINE_GAP_XFADE_S == 0.0


def test_hold_only_gaps_not_duplicated(tmp_path: Path, monkeypatch):
    """gap_xfade_s=0 must append each meditation gap once (not hold + else duplicate)."""
    work = tmp_path / "work"
    work.mkdir()
    audio = tmp_path / "stem.mp3"
    audio.write_bytes(b"x")
    out = tmp_path / "out.mp4"

    windows = [
        (0, 0.58, 24.46),
        (1, 25.67, 53.63),
        (2, 58.15, 85.46),
    ]
    durs = {
        0: round(24.46 - 0.58, 3),
        1: round(53.63 - 25.67, 3),
        2: round(85.46 - 58.15, 3),
    }
    for idx, start_s, end_s in windows:
        raw = work / f"seg_{idx}_kling_raw.mp4"
        raw.write_bytes(b"\x00" * 200_000)
        (work / f"seg_{idx}_meta.json").write_text(
            json.dumps({"start_s": start_s, "end_s": end_s}) + "\n",
            encoding="utf-8",
        )

    def fake_ffprobe(path):
        name = Path(path).name
        if name == "stem.mp3":
            return 178.44
        if name.startswith("chunk_"):
            idx = int(name.split("_")[1].split(".")[0])
            return durs[idx]
        if name.startswith("gap_") or name == "timeline_video.mp4":
            return 1.0
        return 10.0

    def fake_ffmpeg(cmd, **kwargs):
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00" * 1000)

    import phase_b_segmented_timeline_assemble as mod

    monkeypatch.setattr(mod, "ffprobe_duration", fake_ffprobe)
    monkeypatch.setattr(mod, "_run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(mod, "finalize_phase_module_lipsync_delivery", lambda *a, **k: None)

    meta = mod.assemble_segmented_timeline(
        work, audio, out, gap_xfade_s=0.0, apply_delivery=False,
    )
    labels = [p["label"] for p in meta["pieces"]]
    assert labels.count("gap_0") == 1
    assert labels.count("gap_1") == 1
    assert "_body" not in "".join(labels)
