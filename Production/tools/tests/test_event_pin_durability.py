"""EVENT_PIN_DURABILITY_V1 — persist last server-pinned event across restarts."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent))

from lib.event_pin import (  # noqa: E402
    read_persisted_event_pin,
    resolve_startup_event,
    write_persisted_event_pin,
)


def test_write_and_read_pin(tmp_path: Path):
    prod = tmp_path / "Production"
    prod.mkdir()
    write_persisted_event_pin(
        prod,
        event_id="Event_2",
        storyboard="storyboard_v59_prod.html",
        source="test",
    )
    pin = read_persisted_event_pin(prod)
    assert pin is not None
    assert pin["event_id"] == "Event_2"
    assert pin["storyboard"] == "storyboard_v59_prod.html"


def test_resolve_startup_uses_persisted_over_cli(tmp_path: Path, monkeypatch):
    prod = tmp_path / "Production"
    prod.mkdir()
    ev1 = prod / "Event_1"
    ev2 = prod / "Event_2"
    ev1.mkdir()
    ev2.mkdir()
    (ev1 / "storyboard_v59_prod.html").write_text("<html></html>", encoding="utf-8")
    (ev2 / "storyboard_v59_prod.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr("lib.event_pin.EVENT_DIR", lambda eid: prod / str(eid))

    write_persisted_event_pin(
        prod,
        event_id="Event_2",
        storyboard="storyboard_v59_prod.html",
    )

    resolved_dir, sb, eid, source = resolve_startup_event(
        ev1,
        "storyboard_v59_prod.html",
        "Event_1",
    )
    assert source == "persisted"
    assert eid == "Event_2"
    assert resolved_dir.name == "Event_2"
    assert sb == "storyboard_v59_prod.html"


def test_resolve_startup_cli_when_no_pin(tmp_path: Path):
    prod = tmp_path / "Production"
    prod.mkdir()
    ev1 = prod / "Event_1"
    ev1.mkdir()
    (ev1 / "storyboard_v59_prod.html").write_text("<html></html>", encoding="utf-8")

    resolved_dir, sb, eid, source = resolve_startup_event(
        ev1,
        "storyboard_v59_prod.html",
        "Event_1",
    )
    assert source == "cli"
    assert eid == "Event_1"
    assert sb == "storyboard_v59_prod.html"
    assert resolved_dir == ev1.resolve()


def test_dialogue_too_long_is_warning_not_submit_block():
    import beat_generator as bg

    long_spoken = "word " * 50 + "[pause] " + "more " * 20
    beat = {
        "beat_id": "bg_test",
        "speaker": "Arlo",
        "kling_o3_prompt": (
            "Arlo speaks in a warm calm conversational pace, steady and natural, "
            "clear delivery, brisk but not rushed, not bubbly or hyper, not slow, "
            "not dramatic, not childlike or baby-talk: "
            f'"{long_spoken}"'
        ),
        "dialogue_text": long_spoken,
    }
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, beat["kling_o3_prompt"])
    errors = bg.validate_kling_o3_beat_for_submit(beat, event_id="2", phase="pre")
    assert not any(e.get("code") == "DIALOGUE_TOO_LONG" for e in errors)

    warnings = bg.kling_o3_submit_warnings(beat, beat["kling_o3_prompt"], prepared_prompt=prepared)
    dur_warnings = [w for w in warnings if w.get("code") == "DIALOGUE_TOO_LONG"]
    assert dur_warnings
    assert all(w.get("severity") == "warning" for w in dur_warnings)
