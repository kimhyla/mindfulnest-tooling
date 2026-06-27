"""LINKED_VIDEO_MATCH_AUDIO_V1 — Beat Gen + Phase playback banding guards."""
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
SB = TOOLS / "storyboard-v2/src"


def test_playback_video_policy_exported() -> None:
    src = (SB / "utils/playbackVideoPolicy.ts").read_text(encoding="utf-8")
    assert "PLAYBACK_VIDEO_ANTI_BANDING_CLASS" in src
    assert "linkedMediaSameFilename" in src


def test_beat_gen_kling_preview_videos_use_anti_banding_class() -> None:
    storyboard = (SB / "components/StoryboardTab.tsx").read_text(encoding="utf-8")
    composite = (SB / "components/BeatCompositePreview.tsx").read_text(encoding="utf-8")
    bg = (SB / "components/BgTab.tsx").read_text(encoding="utf-8")
    assert "PLAYBACK_VIDEO_ANTI_BANDING_CLASS" in storyboard
    assert "PLAYBACK_VIDEO_ANTI_BANDING_CLASS" in composite
    assert "PLAYBACK_VIDEO_ANTI_BANDING_CLASS" in bg
    assert "class={PLAYBACK_VIDEO_ANTI_BANDING_CLASS}" in bg or "class={`" in bg


def test_waveform_linked_video_match_audio_auto_detect() -> None:
    ws = (SB / "components/phase/WaveformTimeline.tsx").read_text(encoding="utf-8")
    assert "useSharedLinkedMedia" in ws
    assert "setMediaElement" in ws


def test_durability_script_guards_playback_policy() -> None:
    script = (TOOLS.parent / "scripts/verify_phase_producer_durability.sh").read_text(
        encoding="utf-8"
    )
    assert "mn-playback-video-stable" in script
    assert "PLAYBACK_VIDEO_ANTI_BANDING_CLASS" in script
