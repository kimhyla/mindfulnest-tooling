"""Char/BG ref thumbnails must render for Element pose paths, not only library roots."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lib.event_library import library_image_roots, ref_image_thumb_b64, resolve_ref_image_open_path


def _write_test_png(path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    Image.new("RGB", (24, 24), color=(20, 160, 80)).save(path)


def test_library_image_roots_include_character_poses(tmp_path: Path) -> None:
    prod = tmp_path / "Production"
    event = prod / "Event_2"
    tessa_poses = prod / "Tessa" / "poses"
    tessa_poses.mkdir(parents=True)
    (event / "library" / "images" / "sources").mkdir(parents=True)

    roots = library_image_roots(event, prod)
    assert any("Tessa/poses" in r or r.endswith("poses") for r in roots)


def test_ref_image_thumb_b64_for_character_pose(tmp_path: Path) -> None:
    prod = tmp_path / "Production"
    event = prod / "Event_2"
    pose_dir = prod / "Tessa" / "poses"
    pose_dir.mkdir(parents=True)
    pose_path = pose_dir / "tessa_event1_canonical.png"
    _write_test_png(pose_path)
    (event / "library" / "images" / "sources").mkdir(parents=True)

    roots = library_image_roots(event, prod)
    resolved = resolve_ref_image_open_path(str(pose_path), roots)
    assert resolved == os.path.realpath(str(pose_path))

    thumb = ref_image_thumb_b64(str(pose_path), roots)
    assert thumb is not None
    assert thumb.startswith("data:image/jpeg;base64,")


def test_hydrate_beat_ref_images_fills_missing_thumb(tmp_path: Path, monkeypatch) -> None:
    from tools import beat_generator as bg

    prod = tmp_path / "Production"
    event = prod / "Event_2"
    pose_dir = prod / "Tessa" / "poses"
    pose_dir.mkdir(parents=True)
    pose_path = pose_dir / "tessa_event1_canonical.png"
    _write_test_png(pose_path)
    (event / "library" / "images" / "sources").mkdir(parents=True)
    roots = library_image_roots(event, prod)

    beat = {
        "reference_image": {
            "abs_path": str(pose_path),
            "key": "tessa_event1_canonical",
        },
    }
    assert bg.hydrate_beat_ref_images(beat, roots) is True
    assert beat["reference_image"]["thumb_b64"].startswith("data:image/jpeg;base64,")
