"""Stitch media URLs must follow the active server port (Event_2 on :5112)."""
from __future__ import annotations

from pathlib import Path


def test_stitch_editor_uses_request_origin_helper():
    src = (Path(__file__).resolve().parent.parent / "server_handlers" / "stitch_editor.py").read_text(
        encoding="utf-8",
    )
    assert "def _stitch_media_public_url" in src
    assert "_stitch_media_public_url(h," in src
    assert 'f"http://localhost:5111/api/stitch_editor/audio_file/' not in src
    assert "preview_file" in src


def test_stitch_slot_waveform_rewrites_legacy_audio_url():
    ts = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "utils"
        / "stitchSlotVideo.ts"
    ).read_text(encoding="utf-8")
    assert "resolveServerMediaUrl" in ts
    assert "localhost:5111" in ts
    wf = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "components"
        / "StitcherSlotWaveform.tsx"
    ).read_text(encoding="utf-8")
    assert "resolveServerMediaUrl(res.data.audio_url)" in wf
