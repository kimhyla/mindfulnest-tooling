"""Muxed slot preview must invalidate when SFX cue geometry changes — not video_path alone."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
MUX_SIG = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchSlotMuxAudioSig.ts"


def test_stitch_slot_mux_audio_sig_helper_exists() -> None:
    src = MUX_SIG.read_text(encoding="utf-8")
    assert "STITCH_SLOT_MUX_AUDIO_SIG_V1" in src
    assert "duration_ms" in src
    assert "export function stitchSlotMuxAudioSig" in src


def test_build_slot_preview_cache_keys_on_audio_sig_not_video_path_only() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "stitchSlotMuxAudioSig" in src
    assert "audio_sig" in src
    assert "STITCH_SLOT_MUX_AUDIO_SIG_V1" in src
    block = src.split("const buildSlotPreview = async", 1)[1].split("const seekComposerTo", 1)[0]
    assert "cached.audio_sig" in block
    assert "stitchSlotLiveGeometrySig(slotData)" in block


def test_composer_remuxes_when_mux_audio_sig_changes() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "viewerMuxAudioSig" in src
    assert "buildSlotPreview(sessionSlot, { quiet: true })" in src


def test_composer_stale_while_revalidate_keeps_mux_during_remux() -> None:
    """SFX resize must not blank composer — remux in background, swap on success."""
    src = STITCHER.read_text(encoding="utf-8")
    assert "STITCH_MUX_STALE_WHILE_REVALIDATE_V1" in src
    assert "composerMuxRefreshing" in src
    assert "In-memory previewUrls stay until buildSlotPreview succeeds" in src
    build = src.split("const buildSlotPreview = async", 1)[1].split("const seekComposerTo", 1)[0]
    assert "delete next[slot]" not in build
    save = src.split("const saveJobSlots = async", 1)[1].split("const saveJobTransitions", 1)[0]
    assert "delete next[slotKey]" not in save
    assert "invalidateStitchSlotSessionSlot" not in save
    reconcile = src.split("reconcileStitchSlotSession(stitchSessionKey", 1)[0]
    assert "delete next[sd.key]" not in reconcile.split("useEffect(() => {", 1)[-1][:800]


def test_composer_never_falls_back_to_source_when_sfx_configured() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "stitchSlotRequiresMuxedPreview" in src
    assert "stitchSlotRequiresAmbientMix" in src
    assert "STITCH_SLOT_REQUIRES_MUXED_PREVIEW_V1" in src
    assert "fetchTimeoutMs: 300_000" in src
    assert "clearAllCachedStitcherPreviews" in src


def test_mix_slot_hydrates_ambient_before_ffmpeg() -> None:
    editor = (REPO / "tools" / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    server = (REPO / "tools" / "production_server.py").read_text(encoding="utf-8")
    assert "def ensure_slot_ambient_bed_path_hydrated" in editor
    assert "ensure_slot_ambient_bed_path_hydrated(self, slot)" in server
