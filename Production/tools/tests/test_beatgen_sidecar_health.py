"""S5/S3 — beatgen_sidecar_health conflict + orphan helpers."""
from __future__ import annotations

from pathlib import Path

from beatgen_sidecar_health import find_orphan_kling_clips, warn_dropbox_conflict_copies


def test_warn_dropbox_conflict_copies_detects_fixture(tmp_path: Path) -> None:
    conflict = tmp_path / "beat_generator_sidecar (Kim's conflicted copy 1).json"
    conflict.write_text("{}", encoding="utf-8")
    (tmp_path / "beat_generator_sidecar.json").write_text("{}", encoding="utf-8")
    found = warn_dropbox_conflict_copies(tmp_path)
    assert len(found) == 1
    assert "conflicted copy" in found[0].lower()


def test_find_orphan_kling_clips(tmp_path: Path) -> None:
    clips = tmp_path / "kling_o3_clips"
    clips.mkdir()
    orphan = clips / "bg_arc1_event3_pre_beat_10_g1_delivery.mp4"
    known = clips / "bg_arc1_event3_pre_beat_10_g2_delivery.mp4"
    orphan.write_bytes(b"x")
    known.write_bytes(b"y")
    orphans = find_orphan_kling_clips(tmp_path, sidecar_paths={str(known.resolve())})
    assert str(orphan.resolve()) in orphans
    assert str(known.resolve()) not in orphans
