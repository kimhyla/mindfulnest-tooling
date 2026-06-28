"""STITCH_AMBIENT_BAKE_ON_SAVE_V1 — ambient bake on save; mux only when SFX."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers.stitch_media_sig import (  # noqa: E402
    STITCH_AMBIENT_BAKE_ON_SAVE_V1,
    STITCH_SLOT_AMBIENT_MIX_FIELDS,
    compute_stitch_ambient_mix_sig_from_slot,
)


def test_stitch_slot_requires_muxed_preview_sfx_only_in_client() -> None:
    src = (TOOLS / "storyboard-v2/src/utils/stitchSlotMuxAudioSig.ts").read_text(
        encoding="utf-8",
    )
    block = src.split("export function stitchSlotRequiresMuxedPreview", 1)[1].split(
        "\nexport function", 1,
    )[0]
    assert "hasAmbient" not in block
    assert "sfx_cues" in block


def test_stitch_slot_requires_ambient_mix_helper_exists() -> None:
    src = (TOOLS / "storyboard-v2/src/utils/stitchSlotMuxAudioSig.ts").read_text(
        encoding="utf-8",
    )
    assert "stitchSlotRequiresAmbientMix" in src
    assert STITCH_AMBIENT_BAKE_ON_SAVE_V1 in src


def test_save_job_returns_built_slots() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_save_job", 1)[1].split("\ndef ", 1)[0]
    assert "built_slots" in block
    assert "rebuild_stitch_ambient_mixes_for_job" in block


def test_slot_mix_file_serve_route() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "/api/stitch_editor/slot_mix_file/" in src
    assert "_serve_stitch_slot_mix_file" in src


def test_audio_extract_speech_only_marker() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_audio_extract", 1)[1].split("\ndef ", 1)[0]
    assert STITCH_AMBIENT_BAKE_ON_SAVE_V1 in block
    assert "ambient_bed" not in block.split("mix_slot")[0].split("serve_fname", 1)[1]


def test_ambient_mix_sig_excludes_sfx() -> None:
    class _H:
        def _stitch_resolve_path(self, p: str) -> str:
            return p

    slot = {
        "video_path": "Production/Event_1/foo.mp4",
        "ambient_bed": "ambient bed pretty option2",
        "ambient_volume": 0.15,
        "sfx_cues": [{"id": "c1", "offset_ms": 1000, "source_path": "/x/sfx.mp3"}],
    }
    from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot  # noqa: E402

    amb = compute_stitch_ambient_mix_sig_from_slot(_H(), slot, video_abs_path="/tmp/foo.mp4")
    full = compute_stitch_mix_sig_from_slot(_H(), slot, video_abs_path="/tmp/foo.mp4")
    assert amb != full


def test_artifact_fields_include_ambient_mix() -> None:
    from server_handlers.stitch_media_sig import STITCH_SLOT_ARTIFACT_FIELDS  # noqa: E402

    for field in STITCH_SLOT_AMBIENT_MIX_FIELDS:
        assert field in STITCH_SLOT_ARTIFACT_FIELDS


def test_cache_sweep_preserves_referenced(tmp_path: Path) -> None:
    import os
    import time

    from server_handlers.stitch_media_artifacts import sweep_stitch_editor_cache  # noqa: E402

    project = tmp_path
    cache = project / "Production" / "stitch_editor_cache"
    cache.mkdir(parents=True)
    ref_hash = "abc123refer"
    junk_hash = "junkorphan1"
    (cache / f"se_slot_{ref_hash}.mp4").write_bytes(b"ref")
    junk = cache / f"se_slot_{junk_hash}.mp4"
    junk.write_bytes(b"junk")
    old = time.time() - 7200
    os.utime(junk, (old, old))
    state = {
        "jobs": {
            "Event_1_stitch": {
                "slots": {"phase_a": {"ambient_mix_hash": ref_hash}},
            },
        },
    }
    counts = sweep_stitch_editor_cache(project, state, max_age_s=3600.0)
    assert counts["unreferenced"] >= 1
    assert (cache / f"se_slot_{ref_hash}.mp4").is_file()
    assert not junk.is_file()


def test_load_job_persists_healed_artifact_clears() -> None:
    src = (TOOLS / "server_handlers/stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_load_job", 1)[1].split(
        "\ndef handle_stitch_serve_module_final", 1,
    )[0]
    assert "_persist_stitch_job_healed_slots" in block
    assert "artifacts_healed" in block


def test_validate_skips_md5_when_ambient_sig_matches() -> None:
    src = (TOOLS / "server_handlers/stitch_media_artifacts.py").read_text(encoding="utf-8")
    block = src.split("def validate_stitch_slot_media_artifacts", 1)[1].split(
        "\ndef persist_stitch_slot_ambient_mix_artifacts", 1,
    )[0]
    assert "stored_ambient_sig != current_ambient_sig" in block
    assert "_stitch_ambient_mix_lacks_layered_audio" in block
