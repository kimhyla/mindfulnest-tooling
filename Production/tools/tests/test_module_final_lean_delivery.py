"""MODULE_FINAL_LEAN_DELIVERY — stitch bake final MP4 quality (VIDEO_QUALITY_V1)."""
from __future__ import annotations

from pathlib import Path

import video_delivery as vd


def test_module_final_lean_constants():
    assert vd.MODULE_FINAL_LEAN_VIDEO_BITRATE == "1050k"
    assert vd.MODULE_FINAL_LEAN_MAXRATE == "1200k"
    assert vd.MODULE_FINAL_LEAN_MAX_BITRATE_BPS == 1_200_000
    assert vd.MODULE_FINAL_LEAN_GRADFUN_VF == "gradfun=strength=1.5:radius=8"
    assert vd.MODULE_FINAL_LEAN_DELIVERY_V3 == "MODULE_FINAL_LEAN_DELIVERY_V3"
    assert vd.MODULE_FINAL_LEAN_DELIVERY_CURRENT == vd.MODULE_FINAL_LEAN_DELIVERY_V3


def test_encode_module_final_lean_wrapper_exists():
    assert callable(vd.encode_module_final_lean)


def test_stitch_bake_core_wires_single_pass_final():
    src = Path(__file__).resolve().parent.parent / "server_handlers" / "stitch_editor.py"
    text = src.read_text(encoding="utf-8")
    assert "encode_module_final_lean" in text
    assert "MODULE_FINAL_LEAN_DELIVERY_CURRENT" in text
    assert "VIDEO_QUALITY_V1" in text
    assert "_final.mp4" in text
    assert "_master.mp4" not in text.split("def _run_stitch_bake_core")[1].split("\ndef _execute_stitch_bake_job")[0]


def test_stitch_bake_core_no_master_archive_phase():
    core = _stitch_bake_core_source()
    assert "master_archive" not in core
    assert "master_bake_name" not in core


def test_encode_delivery_video_module_final_uses_crf_gradfun():
    src = Path(__file__).resolve().parent.parent / "video_delivery.py"
    text = src.read_text(encoding="utf-8")
    assert 'profile == "module_final_lean"' in text
    assert "use_lean_quality_encode" in text
    assert "_module_final_lean_vf" in text
    assert "MODULE_FINAL_LEAN_GRADFUN_VF" in text
    assert "VIDEO_QUALITY_CRF" in text
    assert "ensure_mp4_playback_timestamps" in text
    assert "STITCH_MP4_PLAYBACK_TIMESTAMPS_V1" in text


def test_load_job_hydrates_bake_path_from_canonical_module_final():
    src = Path(__file__).resolve().parent.parent / "server_handlers" / "stitch_editor.py"
    text = src.read_text(encoding="utf-8")
    block = text.split("def handle_stitch_load_job", 1)[1].split("\ndef handle_stitch_serve_module_final", 1)[0]
    assert "_canonical_module_final_bake_path" in block
    assert "bake_path_hydrated" in block


def test_stitch_bake_finalize_passes_lean_delivery_profile_for_pin():
    """Single-pass bake: timestamp heal runs in encode + pin with lean profile, not master."""
    core = _stitch_bake_core_source()
    assert 'delivery_profile="module_final_lean"' in core
    pin_src = Path(__file__).resolve().parent.parent / "pin_event_canonical_module.py"
    pin_text = pin_src.read_text(encoding="utf-8")
    assert "delivery_profile=delivery_profile" in pin_text
    vd_src = Path(__file__).resolve().parent.parent / "video_delivery.py"
    vd_text = vd_src.read_text(encoding="utf-8")
    assert "encode_module_final_lean" in vd_text
    assert "ensure_mp4_playback_timestamps" in vd_text


def _stitch_bake_core_source() -> str:
    src = Path(__file__).resolve().parent.parent / "server_handlers" / "stitch_editor.py"
    text = src.read_text(encoding="utf-8")
    start = text.index("def _run_stitch_bake_core")
    end = text.index("\ndef _execute_stitch_bake_job")
    return text[start:end]


def test_stitch_bake_master_not_gated_by_ld296_before_lean():
    """Master may exceed 1.9 Mbps; only lean delivery is SIZE_BUDGET gated."""
    core = _stitch_bake_core_source()
    lean_idx = core.index("encode_module_final_lean")
    pre_lean = core[:lean_idx]
    assert "1_900_000" not in pre_lean
    assert "SIZE_BUDGET_VIDEO_V1" not in pre_lean
    assert "SIZE_BUDGET_PER_MODULE_V1" not in pre_lean


def test_stitch_bake_lean_delivery_gated_after_encode():
    core = _stitch_bake_core_source()
    encode_idx = core.index("encode_module_final_lean")
    post_encode = core[encode_idx:]
    assert "MODULE_FINAL_LEAN_MAX_BITRATE_BPS" in post_encode
    assert "SIZE_BUDGET_PER_MODULE_V1" in post_encode
    assert "MODULE_FINAL_LEAN_BITRATE_V1" in post_encode


def test_ensure_mp4_playback_timestamps_accepts_delivery_profile():
    src = Path(__file__).resolve().parent.parent / "video_delivery.py"
    text = src.read_text(encoding="utf-8")
    assert "delivery_profile: str | None = None" in text
    assert "_ensure_delivery_playback_timestamps_capped" in text
    assert "delivery_profile=profile" in text


def test_module_final_lean_timestamp_heal_preserves_bitrate_cap():
    """Regression: timestamp heal must not blow lean past 1200k cap."""
    master = Path(
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
        "/Production/Event_2/exports/stitch_Event_2_stitch_20260621_061731_master.mp4"
    )
    if not master.is_file():
        import pytest

        pytest.skip(f"missing fixture master: {master}")
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        delivery = Path(td) / "lean_delivery.mp4"
        vd.encode_module_final_lean(master, delivery)
        bitrate = vd._probe_bitrate(delivery)
        assert bitrate > 0
        assert bitrate <= vd.MODULE_FINAL_LEAN_MAX_BITRATE_BPS
