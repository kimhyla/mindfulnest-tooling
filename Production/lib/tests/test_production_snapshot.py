"""Tests for Production/lib/production_snapshot.py"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import production_snapshot as snap


# Golden beat shape distilled from live Event_2 sidecar (trim + voice + still insert).
_GOLDEN_EVENT2_BEAT = {
    "beat_id": "bg_arc1_event2_pre_beat_27",
    "speaker": "Lorelai",
    "dialogue_text": "Let's look closer at what makes this stone glow.",
    "kling_o3_status": "approved",
    "kling_o3_trim_start": 0.35,
    "kling_o3_trim_back": 1.2,
    "kling_o3_still_stitch_approved": True,
    "kling_o3_voice_fix_status": "approved",
    "kling_o3_voice_fix_lipsync_padding": {
        "tail_pad_s": 2.5,
        "head_pad_s": 0.7,
        "source_audio_duration_s": 4.82,
    },
    "magic_still_path": "library/images/still_27.png",
}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_create_and_restore_roundtrip(tmp_path: Path) -> None:
    prod = tmp_path / "Production"
    ev1 = prod / "Event_1"
    ev2 = prod / "Event_2"
    ev1.mkdir(parents=True)
    ev2.mkdir(parents=True)

    bg = {"arcs": {"arc_1": {"segments": {"event_2_pre": {"beats": [{"beat_id": "b1", "kling_o3_trim_back": 2.0}]}}}}}
    _write_json(prod / "beat_generator_state.json", bg)
    _write_json(prod / "tools" / "stitch_editor_state.json", {"version": 1, "jobs": {"Event_2_stitch": {"slots": {}}}})
    _write_json(ev2 / "production_state.json", {
        "event_id": "M2E1",
        "phase_a_lipsync_file": "phase_a_lipsync_x.mp4",
        "phase_b_script": "Breathe",
    })
    _write_json(ev2 / "phase_a_lipsync_20260101.json", {"audio_source": "phase_a_voice_stem_x.mp3"})

    result = snap.create_snapshot(prod, source="test")
    assert result.files_copied >= 4
    assert (result.snapshot_dir / "manifest.json").is_file()

    # Wipe live state
    _write_json(prod / "beat_generator_state.json", {"arcs": {}})
    _write_json(ev2 / "production_state.json", {"event_id": "M2E1", "videos": {}})

    restore = snap.restore_snapshot(prod, latest=True, pre_restore_backup=False)
    assert restore["restored_count"] >= 3

    restored_bg = json.loads((prod / "beat_generator_state.json").read_text(encoding="utf-8"))
    beats = restored_bg["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
    assert beats[0]["kling_o3_trim_back"] == 2.0

    restored_ps = json.loads((ev2 / "production_state.json").read_text(encoding="utf-8"))
    assert restored_ps["phase_b_script"] == "Breathe"
    assert (ev2 / "phase_a_lipsync_20260101.json").is_file()


def test_maybe_create_archive_respects_interval(tmp_path: Path) -> None:
    prod = tmp_path / "Production"
    ev = prod / "Event_1"
    ev.mkdir(parents=True)
    _write_json(prod / "beat_generator_state.json", {"arcs": {}})
    _write_json(ev / "production_state.json", {"event_id": "M1E1"})

    first = snap.maybe_create_archive_snapshot(prod, force=True)
    assert first is not None
    second = snap.maybe_create_archive_snapshot(prod, force=False)
    assert second is None

    archives = snap.list_archives(prod)
    assert len(archives) == 1


def test_restore_single_event_only(tmp_path: Path) -> None:
    prod = tmp_path / "Production"
    for n in (1, 2):
        ev = prod / f"Event_{n}"
        ev.mkdir(parents=True)
        _write_json(ev / "production_state.json", {"event_id": f"M{n}E1", "marker": n})

    snap.create_snapshot(prod, source="test")
    for n in (1, 2):
        _write_json(prod / f"Event_{n}" / "production_state.json", {"marker": 0})

    snap.restore_snapshot(prod, latest=True, events=["Event_2"], pre_restore_backup=False)
    assert json.loads((prod / "Event_2" / "production_state.json").read_text())["marker"] == 2
    assert json.loads((prod / "Event_1" / "production_state.json").read_text())["marker"] == 0


def test_golden_event2_beat_contract_survives_restore(tmp_path: Path) -> None:
    """Contract: trims, voice padding, still flags survive restore — user-visible fields."""
    prod = tmp_path / "Production"
    ev2 = prod / "Event_2"
    ev2.mkdir(parents=True)
    bg = {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {"beats": [dict(_GOLDEN_EVENT2_BEAT)]},
                },
            },
        },
    }
    stitch = {
        "version": 1,
        "jobs": {
            "Event_2_stitch": {
                "slots": {
                    "intro": {
                        "video_path": str(ev2 / "assembled" / "intro.mp4"),
                        "beat_boundaries": [{"start_ms": 0, "end_ms": 12000}],
                    },
                },
            },
        },
    }
    _write_json(prod / "beat_generator_state.json", bg)
    _write_json(prod / "tools/stitch_editor_state.json", stitch)
    _write_json(ev2 / "production_state.json", {
        "event_id": "M2E1",
        "phase_a_lipsync_file": "phase_a_lipsync_20260601.mp4",
        "phase_a_voice_stem_file": "phase_a_voice_stem_20260601.mp3",
        "phase_b_lipsync_file": "phase_b_lipsync_20260601.mp4",
    })
    _write_json(ev2 / "phase_a_lipsync_20260601.json", {"audio_source": "phase_a_voice_stem_20260601.mp3"})

    snap.create_snapshot(prod, source="golden")
    _write_json(prod / "beat_generator_state.json", {"arcs": {}})
    _write_json(prod / "tools/stitch_editor_state.json", {"version": 1, "jobs": {}})

    snap.restore_snapshot(prod, latest=True, pre_restore_backup=False)

    beat = json.loads((prod / "beat_generator_state.json").read_text())["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["kling_o3_trim_back"] == 1.2
    assert beat["kling_o3_trim_start"] == 0.35
    assert beat["kling_o3_voice_fix_lipsync_padding"]["tail_pad_s"] == 2.5
    assert beat["kling_o3_still_stitch_approved"] is True

    stitch_restored = json.loads((prod / "tools/stitch_editor_state.json").read_text())
    intro_slot = stitch_restored["jobs"]["Event_2_stitch"]["slots"]["intro"]
    assert intro_slot["beat_boundaries"][0]["end_ms"] == 12000

    ps = json.loads((ev2 / "production_state.json").read_text())
    assert ps["phase_a_voice_stem_file"] == "phase_a_voice_stem_20260601.mp3"
    assert json.loads((ev2 / "phase_a_lipsync_20260601.json").read_text())["audio_source"] == "phase_a_voice_stem_20260601.mp3"


def test_notify_state_write_updates_rolling_without_raising(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prod = tmp_path / "Production"
    ev = prod / "Event_2"
    ev.mkdir(parents=True)
    sidecar = prod / "beat_generator_state.json"
    _write_json(sidecar, {"arcs": {}})

    monkeypatch.setattr(snap, "_HOOK_MIN_INTERVAL_S", 0.0)
    snap.notify_state_write(sidecar, prod_root=prod)

    latest = prod / ".production_snapshots" / "latest" / "global" / "beat_generator_state.json"
    assert latest.is_file()
    assert json.loads(latest.read_text()) == {"arcs": {}}


def test_notify_state_write_never_raises_on_bad_path() -> None:
    snap.notify_state_write("/nonexistent/path/beat_generator_state.json")


def test_manifest_sha256_matches_restored_file(tmp_path: Path) -> None:
    prod = tmp_path / "Production"
    ev = prod / "Event_1"
    ev.mkdir(parents=True)
    _write_json(prod / "beat_generator_state.json", {"arcs": {"arc_1": {}}})
    _write_json(ev / "production_state.json", {"event_id": "M1E1"})

    result = snap.create_snapshot(prod, source="test")
    manifest = result.manifest
    entry = next(e for e in manifest["entries"] if e["kind"] == "global")
    dest = Path(entry["dest"])
    assert entry["sha256"] == snap._sha256(dest)
