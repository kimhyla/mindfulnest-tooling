"""LINKED_VIDEO_MATCH_AUDIO_V1 — Phase A/B lipsync preview banding fix."""
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def test_waveform_timeline_auto_match_audio_from_filenames() -> None:
    src = (TOOLS / "storyboard-v2/src/components/phase/WaveformTimeline.tsx").read_text(
        encoding="utf-8"
    )
    assert "linkedVideoMatchAudio" in src
    assert "useSharedLinkedMedia" in src
    assert "setMediaElement" in src
    assert "linkedVideoFilename" in src
    assert "linkedMediaSameFilename" in src


def test_phase_producer_passes_linked_video_filename() -> None:
    producer = (TOOLS / "storyboard-v2/src/components/phase/PhaseProducer.tsx").read_text(
        encoding="utf-8"
    )
    assert "linkedVideoFilename" in producer
    assert "linkedMediaSameFilename" in producer


def test_durability_script_guards_linked_video_match_audio() -> None:
    script = (
        TOOLS.parent / "scripts/verify_phase_producer_durability.sh"
    ).read_text(encoding="utf-8")
    assert "linkedVideoMatchAudio" in script
    assert "useSharedLinkedMedia" in script
    assert "setMediaElement" in script
    assert "linkedVideoFilename" in script
