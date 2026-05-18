"""Tests for Production/lib/v3_partition.py — v3 beat iteration helper."""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))

from Production.lib.v3_partition import _iter_v3_beats  # noqa: E402


def test_iter_v3_beats_walks_all_three_partitions():
    snap = {
        "videos": {
            "intro": {"beats": {"i1": {"id": "i1"}}},
            "resolution": {"beats": {"r1": {"id": "r1"}}},
            "standalone": {"beats": {"s1": {"id": "s1"}}},
        }
    }
    rows = list(_iter_v3_beats(snap))
    assert len(rows) == 3
    roles = {r[0] for r in rows}
    assert roles == {"intro", "resolution", "standalone"}


def test_iter_v3_beats_handles_missing_videos_key():
    snap: dict = {}
    assert list(_iter_v3_beats(snap)) == []


def test_iter_v3_beats_handles_legacy_top_level_beats():
    snap = {"beats": {"beat_01": {"phase_1": {}}}}
    rows = list(_iter_v3_beats(snap))
    assert len(rows) == 1
    assert rows[0][0] == "legacy"
    assert rows[0][1] == "beat_01"
