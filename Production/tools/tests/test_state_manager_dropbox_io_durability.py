"""StateManager Dropbox errno 11/35 cold-boot durability."""
from __future__ import annotations

import json
from pathlib import Path

import production_server as ps


def test_read_text_dropbox_durable_retries_errno11(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "storyboard.html"
    path.write_text("<html>ok</html>", encoding="utf-8")
    calls = {"n": 0}
    real_open = open

    def flaky_open(file, mode="r", *args, **kwargs):
        if Path(file) == path and "b" in mode:
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError(11, "Resource deadlock avoided")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", flaky_open)
    monkeypatch.setattr(ps.time, "sleep", lambda _s: None)
    assert ps._read_text_dropbox_durable(path) == "<html>ok</html>"
    assert calls["n"] == 2


def test_read_json_file_dropbox_durable_retries_errno11(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "production_state.json"
    path.write_text('{"event_id": "Event_1", "version": "v3"}', encoding="utf-8")
    calls = {"n": 0}
    real_open = open

    def flaky_open(file, mode="r", *args, **kwargs):
        if Path(file) == path and "b" in mode:
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError(11, "Resource deadlock avoided")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(ps, "open", flaky_open, raising=False)
    monkeypatch.setattr("builtins.open", flaky_open)
    monkeypatch.setattr(ps.time, "sleep", lambda _s: None)
    data = ps._read_json_file_dropbox_durable(path)
    assert data["event_id"] == "Event_1"
    assert calls["n"] == 2


def test_read_json_file_dropbox_durable_rejects_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    try:
        ps._read_json_file_dropbox_durable(path)
        raise AssertionError("expected JSONDecodeError on empty file")
    except json.JSONDecodeError:
        pass


def test_merge_missing_skips_empty_mirror(tmp_path: Path) -> None:
    import beat_generator as bg

    empty = tmp_path / "beat_generator_state.json"
    empty.write_text("", encoding="utf-8")
    report = bg.merge_missing_segment_beats_from_json_mirror(
        {"arcs": {}}, empty, "Event_1"
    )
    assert report == {}


def test_state_manager_lock_is_local_not_dropbox(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    (event_dir / "production_state.json").write_text(
        '{"event_id":"Event_1","version":"v3","videos":{}}', encoding="utf-8"
    )
    (event_dir / "production_spend.json").write_text(
        '{"event_id":"Event_1","budget":100,"spent":{},"total_spent":0,"budget_remaining":100}',
        encoding="utf-8",
    )
    sm = ps.StateManager(event_dir, "Event_1")
    assert ".mindfulnest" in str(sm.file_lock_path)
    assert "Event_1.state.lock" == sm.file_lock_path.name
    assert event_dir not in sm.file_lock_path.parents


def test_read_storyboard_html_falls_back_to_local_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    dropbox_html = tmp_path / "storyboard_v59_prod.html"
    dropbox_html.write_text("<html>live-dropbox</html>", encoding="utf-8")
    cache = tmp_path / "home" / ".mindfulnest" / "storyboard_cache"
    cache.mkdir(parents=True)
    cached = cache / "Event_4_storyboard_v59_prod.html"
    cached.write_text("<html>" + ("cached-fallback-body-" * 80) + "</html>", encoding="utf-8")
    assert cached.stat().st_size >= 1000

    def always_deadlock(_path, **_kwargs):
        raise OSError(11, "Resource deadlock avoided")

    monkeypatch.setattr(ps, "_read_text_dropbox_durable", always_deadlock)
    html = ps.read_storyboard_html_durable(dropbox_html, event_id="Event_4")
    assert "cached-fallback" in html


def test_merge_missing_skips_invalid_json_mirror(tmp_path: Path) -> None:
    import beat_generator as bg

    bad = tmp_path / "beat_generator_state.json"
    bad.write_text("{not-json", encoding="utf-8")
    assert bg.merge_missing_segment_beats_from_json_mirror({"arcs": {}}, bad, "Event_2") == {}
