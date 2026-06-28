"""STITCH_LOAD_JOB_FAST_V1 — fast validate backfills trusted lineage pins instead of rebaking."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _make_handler(project: Path, cache: Path) -> MagicMock:
    h = MagicMock()
    h._stitch_project_root = lambda: project
    h._stitch_cache_dir = lambda: cache
    h._stitch_resolve_path = lambda raw: str((project / raw).resolve())
    return h


def test_fast_validate_backfills_ambient_lineage_pins(tmp_path: Path) -> None:
    from server_handlers.stitch_media_artifacts import validate_stitch_slot_media_artifacts

    project = tmp_path
    cache = project / "stitch_editor_cache"
    cache.mkdir(parents=True)
    video_rel = "Production/Event_1/phase_a.mp4"
    video_path = project / video_rel
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"video" * 200)
    amb_hash = "abc123def456"
    (cache / f"se_slot_{amb_hash}.mp4").write_bytes(b"mixed" * 500)

    h = _make_handler(project, cache)
    slot = {
        "video_path": video_rel,
        "video_dur_ms": 5000,
        "ambient_bed": "Phase A ambient bed",
        "ambient_bed_path": "Production/assets/sound_library/ambient/phase_a.mp3",
        "ambient_volume": 0.15,
        "ambient_mix_hash": amb_hash,
        "ambient_mix_duration_ms": 5000,
        "ambient_mix_sig": "deadbeef0001",
    }
    from server_handlers.stitch_media_sig import compute_stitch_ambient_mix_sig_from_slot

    slot["ambient_mix_sig"] = compute_stitch_ambient_mix_sig_from_slot(h, slot)

    warns = validate_stitch_slot_media_artifacts(h, slot, fast=True)
    assert slot.get("ambient_mix_hash") == amb_hash
    assert slot.get("ambient_mix_video_path") == video_rel
    assert not any("cleared" in (w or "") for w in warns)
