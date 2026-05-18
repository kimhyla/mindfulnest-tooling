"""V59 Phase A — JsonStateRepository tests."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

_PRODUCTION_ROOT = Path(__file__).resolve().parents[1]
if str(_PRODUCTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_PRODUCTION_ROOT))

from lib.atomic_json_write import atomic_json_write  # noqa: E402
from lib.state_repo import JsonStateRepository  # noqa: E402


def test_read_returns_empty_dict_for_missing_file(tmp_path: Path) -> None:
    repo = JsonStateRepository(tmp_path / "production_state.json")
    assert repo.read() == {}


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    repo = JsonStateRepository(tmp_path / "production_state.json")
    payload = {"event_id": "Event_1", "version": "v3", "count": 7}
    repo.write(payload)
    assert repo.read() == payload


def test_mutate_applies_function(tmp_path: Path) -> None:
    path = tmp_path / "production_state.json"
    repo = JsonStateRepository(path)
    repo.write({"counter": 0})

    def increment(state: dict) -> dict:
        state["counter"] = state.get("counter", 0) + 1
        return state

    result = repo.mutate(increment)
    assert result["counter"] == 1
    assert repo.read()["counter"] == 1


def test_mutate_is_atomic_under_concurrent_writes(tmp_path: Path) -> None:
    path = tmp_path / "production_state.json"
    repo = JsonStateRepository(path)
    repo.write({"counter": 0})

    def increment(state: dict) -> dict:
        state["counter"] = state.get("counter", 0) + 1
        return state

    def worker() -> None:
        for _ in range(25):
            JsonStateRepository(path).mutate(increment)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(worker) for _ in range(4)]
        for fut in futures:
            fut.result()

    assert repo.read()["counter"] == 100


def test_read_field_dotted_path(tmp_path: Path) -> None:
    repo = JsonStateRepository(tmp_path / "production_state.json")
    repo.write({"beats": {"beat_05": {"text": "hello"}}})
    assert repo.read_field("beats.beat_05.text") == "hello"


def test_read_field_missing_returns_default(tmp_path: Path) -> None:
    repo = JsonStateRepository(tmp_path / "production_state.json")
    sentinel = object()
    assert repo.read_field("nonexistent.path", sentinel) is sentinel


def test_write_field_creates_intermediate_dicts(tmp_path: Path) -> None:
    repo = JsonStateRepository(tmp_path / "production_state.json")
    repo.write_field("a.b.c.d", 42)
    assert repo.read() == {"a": {"b": {"c": {"d": 42}}}}


def test_write_field_preserves_siblings(tmp_path: Path) -> None:
    repo = JsonStateRepository(tmp_path / "production_state.json")
    repo.write({"a": {"x": 10, "y": 20}})
    repo.write_field("a.z", 1)
    assert repo.read() == {"a": {"x": 10, "y": 20, "z": 1}}


def test_byte_equivalent_to_atomic_json_write(tmp_path: Path) -> None:
    repo_path = tmp_path / "via_repo.json"
    direct_path = tmp_path / "via_atomic.json"
    payload = {"event_id": "Event_1", "nested": {"k": [1, 2, 3]}}

    JsonStateRepository(repo_path).write(payload)
    atomic_json_write(str(direct_path), payload)

    assert repo_path.read_bytes() == direct_path.read_bytes()
