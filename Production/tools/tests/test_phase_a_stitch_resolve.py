"""Tests for phase_a_stitch_lib pinned resolution."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from phase_a_stitch_lib import (  # noqa: E402
    resolve_phase_a_flyin,
    resolve_phase_a_flyout,
    resolve_phase_a_raw_lipsync,
)


def test_pinned_flyout_wins_over_newer_v4(tmp_path: Path) -> None:
    """closeup_match pinned in state must beat newer phase_a_flyout_v4_* glob."""
    old = tmp_path / "phase_a_flyout_closeup_match_20260607T183525Z.mp4"
    new = tmp_path / "phase_a_flyout_v4_20260420T231237Z.mp4"
    old.write_bytes(b"x")
    new.write_bytes(b"xx")
    # Make v4 newer on disk
    import os
    import time
    now = time.time()
    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now, now))

    state = {"phase_a_flyout_file": old.name}
    got = resolve_phase_a_flyout(tmp_path, state)
    assert got == old


def test_flyout_glob_includes_closeup_match_when_unpinned(tmp_path: Path) -> None:
    closeup = tmp_path / "phase_a_flyout_closeup_match_20260607T183525Z.mp4"
    closeup.write_bytes(b"x")
    state: dict = {}
    got = resolve_phase_a_flyout(tmp_path, state)
    assert got == closeup


def test_pinned_flyin_from_nested_phase_a(tmp_path: Path) -> None:
    flyin = tmp_path / "phase_a_flyin_closeup_match_20260607T183323Z.mp4"
    flyin.write_bytes(b"x")
    state = {"phase_a": {"phase_a_flyin_file": flyin.name}}
    assert resolve_phase_a_flyin(tmp_path, state) == flyin


def test_raw_lipsync_skips_withbed(tmp_path: Path) -> None:
    raw = tmp_path / "phase_a_lipsync_20260607-182528.mp4"
    bed = tmp_path / "phase_a_lipsync_20260607-182528_withbed.mp4"
    raw.write_bytes(b"x")
    bed.write_bytes(b"xx")
    import os
    import time
    now = time.time()
    os.utime(raw, (now, now))
    os.utime(bed, (now + 10, now + 10))
    assert resolve_phase_a_raw_lipsync(tmp_path) == raw
