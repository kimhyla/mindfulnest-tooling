"""Offline contract tests for the profile-driven layered lipsync engine."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import arlo_layered_lipsync
import layered_character_lipsync as engine
import phase_b_path_a_pipeline as cedric


def test_profiles_are_immutable_relative_and_portable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "Production Root With Spaces"
    root.mkdir()
    monkeypatch.setenv("MN_PRODUCTION_ROOT", str(root))

    resolved = engine.resolve_production_root()
    paths = engine.profile_paths(engine.ARLO_PROFILE, resolved)
    assert resolved == root.resolve()
    assert paths["plate"] == (
        root
        / "NEW STYLE CHARACTERS/ARLO/"
        "arlo_room_plate_chair_study_1280x720_v2.png"
    )
    assert paths["idle_units"][0] == (
        root
        / "NEW STYLE CHARACTERS/ARLO/"
        "arlo_gesture_idle_full_loop_30s_green_1920x1080_v1.mp4"
    )
    assert len(paths["idle_units"]) == 1
    assert not Path(engine.ARLO_PROFILE.plate_relative_path).is_absolute()
    with pytest.raises(Exception):
        engine.ARLO_PROFILE.profile_id = "changed"  # type: ignore[misc]


def test_event_parent_is_production_root(tmp_path: Path) -> None:
    event = tmp_path / "Production With Spaces" / "Event_9"
    event.mkdir(parents=True)
    assert engine.resolve_production_root(event_dir=event) == event.parent.resolve()


def test_arlo_uses_cedric_whole_character_contract() -> None:
    profile = engine.ARLO_PROFILE
    assert profile.route_id == "PHASE_A_ARLO_LAYERED_ROUTE_V1"
    assert profile.source_size == engine.Size(1920, 1080)
    assert profile.canvas_size == engine.Size(1280, 720)
    assert profile.provider_content == "whole_character"
    assert profile.provider_crop == engine.Crop(0, 0, 1920, 1080)
    assert profile.placement_mode == "full_canvas"
    assert profile.placement == engine.Crop(0, 0, 1280, 720)
    assert profile.cutout_mode == "key_canvas"
    assert profile.cutout_relative_path.endswith("arlo_key_canvas_1280x720_v1.png")
    assert profile.plate_relative_path.endswith(
        "arlo_room_plate_chair_study_1280x720_v2.png"
    )
    assert [u.name for u in profile.idle_units] == ["full_loop_30s"]
    assert profile.idle_units[0].relative_path.endswith(
        "arlo_gesture_idle_full_loop_30s_green_1920x1080_v1.mp4"
    )
    assert profile.idle_units[0].duration == 30.0
    assert profile.idle_units[0].head_trim == 1.75
    assert profile.idle_units[0].tail_trim == 1.08
    assert profile.xfade_seconds == 0.35
    # Beat Gen voice-first face-return padding (not Cedric's short 0.5/0.5).
    assert profile.boundary_pad_start == 1.0
    assert profile.boundary_pad_end == 2.5
    assert profile.boundary_pad_end == 2.5
    engine.validate_profile(profile)

    with pytest.raises(ValueError, match="complete source"):
        engine.validate_profile(
            replace(profile, provider_crop=engine.Crop(438, 54, 1040, 580))
        )
    with pytest.raises(ValueError, match="complete output canvas"):
        engine.validate_profile(
            replace(profile, placement=engine.Crop(234, 29, 556, 310))
        )


def test_arlo_idle_is_canonical_full_loop_not_full_also() -> None:
    """Wire-up must not silently accept the rejected two-clip red-hands idle."""
    profile = engine.ARLO_PROFILE
    rel = profile.idle_units[0].relative_path.replace("\\", "/")
    assert rel == engine.ARLO_CANONICAL_IDLE_RELATIVE_PATH
    assert rel.endswith("full_loop_30s_green_1920x1080_v1.mp4")
    assert "full_also" not in rel
    assert "also_27s" not in rel
    assert len(profile.idle_units) == 1
    engine.validate_arlo_idle_contract(profile)
    engine.validate_profile(profile)

    rejected = replace(
        profile,
        idle_units=(
            engine.IdleUnit(
                "full_also_27s",
                "NEW STYLE CHARACTERS/ARLO/"
                "arlo_gesture_idle_full_also_27s_green_1920x1080_v1.mp4",
                27.791667,
                0.2,
                0.2,
            ),
        ),
    )
    with pytest.raises(ValueError, match="rejected Arlo idle|canonical"):
        engine.validate_profile(rejected)
    with pytest.raises(ValueError, match="rejected Arlo idle|full_also"):
        engine.assert_idle_path_not_rejected(
            "NEW STYLE CHARACTERS/ARLO/"
            "arlo_gesture_idle_full_also_27s_green_1920x1080_v1.mp4"
        )


def test_cut_chunks_uses_profile_provider_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(engine, "ffprobe_duration", lambda _path: 10.0)
    monkeypatch.setattr(
        engine,
        "run",
        lambda command, **_kwargs: commands.append(command)
        or SimpleNamespace(stdout=""),
    )
    durations = engine.cut_chunks(
        engine.ARLO_PROFILE,
        tmp_path / "audio.mp3",
        tmp_path / "idle.mp4",
        [],
        tmp_path,
    )
    assert durations == [10.0]
    video_command = commands[1]
    vf = video_command[video_command.index("-vf") + 1]
    assert f"crop={engine.ARLO_PROFILE.provider_crop.ffmpeg}" in vf
    assert f"scale={engine.ARLO_PROFILE.provider_input_size.ffmpeg}" in vf


def test_key_canvas_rejects_foreground_occlusion(tmp_path: Path) -> None:
    from PIL import Image

    good = tmp_path / "key.png"
    bad = tmp_path / "desk-over-key.png"
    Image.new("RGB", (20, 20), engine.ARLO_PROFILE.key_rgb).save(good)
    pixels = np.full((20, 20, 3), engine.ARLO_PROFILE.key_rgb, dtype=np.uint8)
    pixels[12:, :] = (90, 55, 25)
    Image.fromarray(pixels, mode="RGB").save(bad)

    engine.validate_key_canvas(good, engine.ARLO_PROFILE.key_rgb)
    with pytest.raises(engine.LayeredLipsyncQCError, match="non-key pixels"):
        engine.validate_key_canvas(bad, engine.ARLO_PROFILE.key_rgb)


def test_composite_pins_profile_frame_rate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        engine,
        "run",
        lambda command, **_kwargs: commands.append(command)
        or SimpleNamespace(stdout=""),
    )

    engine.composite_on_plate(
        engine.ARLO_PROFILE,
        tmp_path,
        tmp_path / "lipsync.mp4",
        tmp_path / "stem.mp3",
        tmp_path / "output.mp4",
    )

    filter_complex = commands[0][commands[0].index("-filter_complex") + 1]
    assert f"fps={engine.ARLO_PROFILE.fps}" in filter_complex


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        bytes([255]) * 8,
        bytes([0]) * 8,
        bytes([100]) * 8,
    ],
)
def test_qc_fails_closed_for_uninformative_crops(
    raw: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = engine.QCRegion(
        engine.Crop(0, 0, 2, 2),
        fps=2,
        threshold=0.4,
        min_span_seconds=0.5,
    )
    monkeypatch.setattr(
        engine,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=raw),
    )
    with pytest.raises(engine.LayeredLipsyncQCError, match="uninformative"):
        engine.qc_pupil_scan(Path("synthetic.mp4"), region)


def test_provider_dimensions_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "ffprobe_size", lambda _path: engine.Size(640, 360))
    with pytest.raises(engine.LayeredLipsyncQCError, match="provider output"):
        engine.validate_provider_output(Path("result.mp4"), engine.ARLO_PROFILE)


def test_chunking_happens_before_per_chunk_padding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    local_output = tmp_path / "work" / "composite_local.mp4"
    local_output.parent.mkdir()

    monkeypatch.setattr(engine, "validate_assets", lambda *_args: None)
    monkeypatch.setattr(engine, "ffprobe_duration", lambda _path: 60.0)
    monkeypatch.setattr(
        engine,
        "build_idle_track",
        lambda *_args: list(engine.CEDRIC_PROFILE.idle_units),
    )
    monkeypatch.setattr(engine, "qc_still_scan", lambda *_args: [])
    def fake_boundaries(_audio: Path, raw_limit: float) -> list[float]:
        assert raw_limit == 49.0
        events.append("boundaries")
        return [30.0]

    monkeypatch.setattr(engine, "detect_chunk_boundaries", fake_boundaries)

    def fake_cut(*_args):
        events.append("cut")
        return [30.0, 30.0]

    def fake_pad(*_args):
        assert events[-1] == "cut"
        events.append("pad")
        return [31.0, 31.0]

    monkeypatch.setattr(engine, "cut_chunks", fake_cut)
    monkeypatch.setattr(engine, "apply_chunk_boundary_padding", fake_pad)
    monkeypatch.setattr(
        engine,
        "submit_lipsync_chunks",
        lambda *_args, **_kwargs: {
            0: {"status": "completed", "task_id": "task-0", "outputs": ["u0"]},
            1: {"status": "completed", "task_id": "task-1", "outputs": ["u1"]},
        },
    )
    monkeypatch.setattr(engine, "validate_provider_output", lambda *_args: None)
    monkeypatch.setattr(engine, "qc_pupil_scan", lambda *_args: [])
    monkeypatch.setattr(engine, "pad_concat_lipsync", lambda *_args: None)

    def fake_composite(*_args):
        local_output.write_bytes(b"decoded-video")

    monkeypatch.setattr(engine, "composite_on_plate", fake_composite)
    monkeypatch.setattr(engine, "run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        engine,
        "source_hashes",
        lambda *_args: {"audio": "offline", "idle_units": {}},
    )
    delivered: dict = {}
    monkeypatch.setattr(
        engine,
        "atomic_deliver",
        lambda _local, _output, manifest: delivered.update(manifest),
    )

    manifest = engine.run_layered_lipsync(
        engine.CEDRIC_PROFILE,
        tmp_path / "audio.mp3",
        tmp_path / "out.mp4",
        api_key="offline",
        production_root=tmp_path,
        work_dir=local_output.parent,
    )
    assert events == ["boundaries", "cut", "pad"]
    assert manifest["lipsync"]["0"]["task_id"] == "task-0"
    assert delivered["padded_chunk_durations"] == [31.0, 31.0]
    assert delivered["plan_sha256"] == manifest["plan_sha256"]
    assert delivered["source_sha256"]["audio"] == "offline"
    assert delivered["output_sha256"] == engine.sha256_file(local_output)


def test_submissions_are_bounded_and_record_task_ids(tmp_path: Path) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    class FakeClient:
        def __init__(self, _api_key: str):
            pass

        def submit(self, _video: Path, _audio: Path, *, transport: str) -> str:
            nonlocal active, peak
            assert transport == "url"
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            return f"task-{threading.get_ident()}"

        def poll_until_done(self, task_id: str) -> dict:
            nonlocal active
            with lock:
                active -= 1
            return {"status": "completed", "outputs": [f"https://x/{task_id}"]}

        def download(self, _url: str, destination: Path) -> None:
            destination.write_bytes(b"video")

    for index in range(5):
        (tmp_path / f"chunk_{index}_video.mp4").write_bytes(b"v")
        (tmp_path / f"chunk_{index}_audio.mp3").write_bytes(b"a")
    results = engine.submit_lipsync_chunks(
        tmp_path,
        5,
        "offline",
        max_workers=2,
        client_factory=FakeClient,
    )
    assert peak <= 2
    assert len(results) == 5
    assert all(record["task_id"].startswith("task-") for record in results.values())


def test_atomic_delivery_writes_output_and_manifest(tmp_path: Path) -> None:
    local = tmp_path / "local.mp4"
    local.write_bytes(b"new-video")
    destination = tmp_path / "destination folder" / "arlo.mp4"
    manifest = {"profile": "arlo", "task": "offline"}

    sidecar = engine.atomic_deliver(local, destination, manifest)
    assert destination.read_bytes() == b"new-video"
    delivered_manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    assert delivered_manifest == {**manifest, "committed": True}


def test_atomic_delivery_installs_video_before_committed_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "local.mp4"
    local.write_bytes(b"new-video")
    destination = tmp_path / "out.mp4"
    sidecar = engine.manifest_path_for(destination)
    real_replace = os.replace
    targets: list[Path] = []

    def record_replace(source, target):
        targets.append(Path(target))
        return real_replace(source, target)

    monkeypatch.setattr(engine.os, "replace", record_replace)
    engine.atomic_deliver(local, destination, {"profile": "arlo"})

    assert targets[-2:] == [destination, sidecar]
    assert json.loads(sidecar.read_text())["committed"] is True


def test_atomic_delivery_failure_leaves_destination_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "local.mp4"
    local.write_bytes(b"new-video")
    destination = tmp_path / "out.mp4"
    destination.write_bytes(b"old-video")
    sidecar = engine.manifest_path_for(destination)
    sidecar.write_text('{"old": true}\n', encoding="utf-8")
    real_replace = os.replace

    def fail_output(source, target):
        if Path(target) == destination:
            raise OSError("simulated delivery failure")
        return real_replace(source, target)

    monkeypatch.setattr(engine.os, "replace", fail_output)
    with pytest.raises(OSError, match="simulated"):
        engine.atomic_deliver(local, destination, {"new": True})
    assert destination.read_bytes() == b"old-video"
    assert json.loads(sidecar.read_text(encoding="utf-8")) == {"old": True}


@pytest.mark.skip(reason='Cedric Path A still uses phase_b_path_a_pipeline on Mac main; shared-engine wrap is vacation tip only')
def test_cedric_wrapper_keeps_route_and_delegates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_run(profile, audio, output, **kwargs):
        captured.update(
            profile=profile,
            audio=audio,
            output=output,
            kwargs=kwargs,
        )
        return {"route": profile.route_id}

    monkeypatch.setattr(cedric, "run_layered_lipsync", fake_run)
    result = cedric.run_phase_b_path_a_lipsync(
        tmp_path / "audio.mp3",
        tmp_path / "out.mp4",
        api_key="offline",
        production_root=tmp_path,
    )
    assert result["route"] == cedric.PHASE_B_PATH_A_ROUTE_V1
    assert captured["profile"] is engine.CEDRIC_PROFILE
    assert callable(cedric.count_phase_b_path_a_chunks)
    assert callable(cedric.validate_path_a_assets)
    assert arlo_layered_lipsync.ARLO_LAYERED_LIPSYNC_PROFILE is engine.ARLO_PROFILE
