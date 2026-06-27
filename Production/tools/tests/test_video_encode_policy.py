"""VIDEO_QUALITY_V1 — encode policy durability tests."""
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
CRED = TOOLS / "credentials_lib"
FF = CRED / "ffmpeg_stitch.py"
POLICY = CRED / "video_encode_policy.py"
WS = TOOLS / "storyboard-v2/src/components/phase/WaveformTimeline.tsx"
PRODUCER = TOOLS / "storyboard-v2/src/components/phase/PhaseProducer.tsx"
BG = TOOLS / "storyboard-v2/src/components/BgTab.tsx"
SERVER = TOOLS / "production_server.py"


def test_video_encode_policy_constants() -> None:
    src = POLICY.read_text(encoding="utf-8")
    assert "VIDEO_QUALITY_CRF = \"18\"" in src
    assert "VIDEO_QUALITY_GRADFUN_VF" in src
    assert "AUX_H264_ENCODER_ARGS" in src


def test_ffmpeg_stitch_imports_video_quality_policy() -> None:
    ff = FF.read_text(encoding="utf-8")
    assert "from video_encode_policy import" in ff
    assert "VIDEO_QUALITY_GRADFUN_VF" in ff
    assert '"v7"' in ff or "v7" in ff
    assert "1500k" not in ff.split("NORMALIZATION_ENCODER_ARGS")[1].split("PREVIEW_OVERLAY")[0]
    assert '"-crf", VIDEO_QUALITY_CRF' in ff


def test_waveform_shared_media_single_clock() -> None:
    ws = WS.read_text(encoding="utf-8")
    assert "useSharedLinkedMedia" in ws
    assert "setMediaElement" in ws
    assert "lastDisplaySeekMs" not in ws


def test_phase_producer_unmutes_for_shared_media() -> None:
    producer = PRODUCER.read_text(encoding="utf-8")
    assert "muted={!linkedVideoMatchesWaveformAudio}" in producer


def test_bg_magic_previews_anti_banding() -> None:
    bg = BG.read_text(encoding="utf-8")
    block = bg.split("bg-magic-preview-still", 1)[1].split("bg-magic-preview-video", 1)[0]
    assert "PLAYBACK_VIDEO_ANTI_BANDING_CLASS" in block


def test_video_delivery_bake_uses_video_quality_policy() -> None:
    vd = (TOOLS / "video_delivery.py").read_text(encoding="utf-8")
    assert "MODULE_FINAL_LEAN_DELIVERY_V3" in vd
    assert "_module_final_lean_vf" in vd
    assert "use_lean_quality_encode" in vd
    editor = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    assert "MODULE_FINAL_LEAN_DELIVERY_CURRENT" in editor
    assert "VIDEO_QUALITY_V1" in editor
