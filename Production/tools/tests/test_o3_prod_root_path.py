"""Guard against Production/Production/ sidecar path on O3 subprocess launch."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def test_runtime_prod_root_relative_mn_prod_root_with_cwd_in_production(tmp_path: Path, monkeypatch) -> None:
    dropbox = tmp_path / "dropbox"
    prod = dropbox / "Production"
    event2 = prod / "Event_2"
    event2.mkdir(parents=True)
    sidecar = prod / "beat_generator_state.json"
    sidecar.write_text(json.dumps({"schema_version": 1, "arcs": {}}), encoding="utf-8")

    monkeypatch.chdir(prod)
    monkeypatch.setenv("MN_PROD_ROOT", "Production")

    from kling_o3_element_beat_pipeline import _runtime_prod_root

    root = _runtime_prod_root()
    assert root == prod.resolve()
    assert (root / "beat_generator_state.json").is_file()
    assert not (root / "Production" / "beat_generator_state.json").exists()


def test_runtime_prod_root_collapses_double_production_absolute(tmp_path: Path, monkeypatch) -> None:
    dropbox = tmp_path / "dropbox"
    prod = dropbox / "Production"
    nested = prod / "Production"
    event2 = nested / "Event_2"
    event2.mkdir(parents=True)
    sidecar = prod / "beat_generator_state.json"
    sidecar.write_text(json.dumps({"schema_version": 1, "arcs": {}}), encoding="utf-8")

    monkeypatch.chdir(prod)
    monkeypatch.setenv("MN_PROD_ROOT", str(nested.resolve()))

    from kling_o3_element_beat_pipeline import _runtime_prod_root

    root = _runtime_prod_root()
    assert root == prod.resolve()
    assert (root / "beat_generator_state.json").is_file()


def test_data_root_resolves_absolute_production(tmp_path: Path) -> None:
    dropbox = tmp_path / "dropbox"
    event2 = dropbox / "Production" / "Event_2"
    event2.mkdir(parents=True)

    class _App:
        event_dir = str(dropbox / "Production" / "Event_2")

    class _Handler:
        app = _App()

    from server_handlers.background import _data_root

    root = _data_root(_Handler())
    assert root == (dropbox / "Production").resolve()
    assert root.is_absolute()


def test_data_root_collapses_double_production_event_dir(tmp_path: Path) -> None:
    dropbox = tmp_path / "dropbox"
    event2 = dropbox / "Production" / "Production" / "Event_2"
    event2.mkdir(parents=True)

    class _App:
        event_dir = event2

    class _Handler:
        app = _App()

    from server_handlers.background import _data_root

    root = _data_root(_Handler())
    assert root == (dropbox / "Production").resolve()


def test_arlo_voice_pipeline_reads_mn_prod_root_not_tooling_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inserted beats live in Dropbox sidecar; voice-first subprocess must not read tooling copy."""
    dropbox = tmp_path / "dropbox" / "Production"
    event2 = dropbox / "Event_2"
    event2.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_99"
    sidecar_doc = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{"beat_id": beat_id, "speaker": "Loral"}],
                    },
                },
            },
        },
    }
    (dropbox / "beat_generator_state.json").write_text(
        json.dumps(sidecar_doc), encoding="utf-8",
    )
    tooling = tmp_path / "tooling" / "Production"
    tooling.mkdir(parents=True)
    (tooling / "beat_generator_state.json").write_text(
        json.dumps({"schema_version": 1, "arcs": {}}), encoding="utf-8",
    )

    monkeypatch.chdir(dropbox)
    monkeypatch.setenv("MN_PROD_ROOT", str(dropbox.resolve()))

    from arlo_o3_voice_pipeline import _find_beat, _runtime_prod_root

    prod_root = _runtime_prod_root()
    sc = json.loads((prod_root / "beat_generator_state.json").read_text(encoding="utf-8"))
    assert _find_beat(sc, beat_id) is not None
    assert _find_beat(
        json.loads((tooling / "beat_generator_state.json").read_text(encoding="utf-8")),
        beat_id,
    ) is None


def test_arlo_voice_pipeline_source_uses_runtime_prod_root() -> None:
    src = Path(__file__).resolve().parents[1] / "arlo_o3_voice_pipeline.py"
    text = src.read_text(encoding="utf-8")
    assert "_runtime_prod_root" in text
    assert "init_bg_paths(event_dir)" in text
    assert "beat not found after init_bg_paths" in text
    assert "mindfulnest-tooling/Production/beat_generator_state.json" not in text
