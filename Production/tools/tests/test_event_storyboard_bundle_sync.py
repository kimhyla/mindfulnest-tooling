"""Tests for EVENT_SWITCH_STORYBOARD_BUNDLE_SYNC_V1."""
from __future__ import annotations

from pathlib import Path

from lib.event_storyboard_bundle_sync import (
    TARGET_NAME,
    sync_event_storyboard_bundle,
)


def test_sync_copies_canonical_when_missing(tmp_path: Path, monkeypatch) -> None:
    canonical = tmp_path / "dist" / "index.html"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("<html>canonical</html>", encoding="utf-8")
    event_dir = tmp_path / "Event_99"
    event_dir.mkdir()

    import lib.event_storyboard_bundle_sync as mod

    monkeypatch.setattr(mod, "_canonical_bundle_path", lambda: canonical)

    result = sync_event_storyboard_bundle(event_dir)
    assert result.ok is True
    assert result.copied is True
    assert (event_dir / TARGET_NAME).read_text(encoding="utf-8") == "<html>canonical</html>"


def test_sync_skips_when_target_fresh(tmp_path: Path, monkeypatch) -> None:
    canonical = tmp_path / "dist" / "index.html"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("<html>v1</html>", encoding="utf-8")
    event_dir = tmp_path / "Event_99"
    event_dir.mkdir()
    target = event_dir / TARGET_NAME
    target.write_text("<html>v1</html>", encoding="utf-8")

    import lib.event_storyboard_bundle_sync as mod

    monkeypatch.setattr(mod, "_canonical_bundle_path", lambda: canonical)

    result = sync_event_storyboard_bundle(event_dir)
    assert result.ok is True
    assert result.copied is False
    assert result.skipped_reason == "target_fresh"
