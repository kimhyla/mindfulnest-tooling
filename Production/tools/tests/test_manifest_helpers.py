# Production/tools/tests/test_manifest_helpers.py
"""
Tests for manifest_helpers.py per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.1 step 5.

Coverage:
  (a) phase_boundaries_to_manifest_form: named-object output for each of the 3 input shapes
  (b) ValueError on out-of-order boundaries
  (c) ValueError on missing required keys
  (d) compute_app_compat_content_hash: 64-char lowercase hex matching ^[a-f0-9]{64}$
  (e) FileNotFoundError on missing file
  Plus: phase_boundaries_to_segment_array_form returns 4 ordered segments,
        validate_phase_boundaries accepts valid + rejects invalid inputs.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

# Ensure the parent `Production/tools` directory is importable regardless of
# pytest invocation cwd.
_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from manifest_helpers import (  # noqa: E402  (import after sys.path tweak)
    compute_app_compat_content_hash,
    phase_boundaries_to_manifest_form,
    phase_boundaries_to_segment_array_form,
    validate_phase_boundaries,
)


HEX64_RE = re.compile(r"^[a-f0-9]{64}$")


# ---------------------------------------------------------------------------
# (a) phase_boundaries_to_manifest_form — three input shapes
# ---------------------------------------------------------------------------

def test_manifest_form_passthrough_returns_named_object():
    raw = {"story_start_ms": 0, "phase_b_start_ms": 30000, "phase_b_end_ms": 90000}
    result = phase_boundaries_to_manifest_form(raw)
    assert result == {
        "story_start_ms": 0,
        "phase_b_start_ms": 30000,
        "phase_b_end_ms": 90000,
    }


def test_legacy_camelcase_keys_snakecased():
    raw = {"storyStartMs": 0, "phaseBStartMs": 30000, "phaseBEndMs": 90000}
    result = phase_boundaries_to_manifest_form(raw)
    assert result == {
        "story_start_ms": 0,
        "phase_b_start_ms": 30000,
        "phase_b_end_ms": 90000,
    }


def test_full_module_label_form_maps_to_manifest():
    raw = {
        "intro_start_ms": 0,
        "intro_end_ms": 5000,
        "phase_a_start_ms": 5000,
        "phase_a_end_ms": 30000,
        "phase_b_start_ms": 30000,
        "phase_b_end_ms": 90000,
        "resolution_start_ms": 90000,
        "resolution_end_ms": 100000,
    }
    result = phase_boundaries_to_manifest_form(raw)
    # story_start_ms = intro_start_ms; phase_b carried through; resolution dropped.
    assert result == {
        "story_start_ms": 0,
        "phase_b_start_ms": 30000,
        "phase_b_end_ms": 90000,
    }


# ---------------------------------------------------------------------------
# (b) ValueError on out-of-order boundaries
# ---------------------------------------------------------------------------

def test_value_error_when_story_start_greater_than_phase_b_start():
    raw = {"story_start_ms": 50000, "phase_b_start_ms": 30000, "phase_b_end_ms": 90000}
    with pytest.raises(ValueError):
        phase_boundaries_to_manifest_form(raw)


def test_value_error_when_phase_b_start_greater_than_phase_b_end():
    raw = {"story_start_ms": 0, "phase_b_start_ms": 60000, "phase_b_end_ms": 30000}
    with pytest.raises(ValueError):
        phase_boundaries_to_manifest_form(raw)


def test_value_error_on_negative_value():
    raw = {"story_start_ms": -1, "phase_b_start_ms": 30000, "phase_b_end_ms": 90000}
    with pytest.raises(ValueError):
        phase_boundaries_to_manifest_form(raw)


# ---------------------------------------------------------------------------
# (c) ValueError on missing required keys
# ---------------------------------------------------------------------------

def test_value_error_on_missing_keys_unknown_shape():
    raw = {"story_start_ms": 0, "phase_b_start_ms": 30000}  # missing phase_b_end_ms
    with pytest.raises(ValueError):
        phase_boundaries_to_manifest_form(raw)


def test_value_error_on_empty_dict():
    with pytest.raises(ValueError):
        phase_boundaries_to_manifest_form({})


def test_value_error_on_non_dict_input():
    with pytest.raises(ValueError):
        phase_boundaries_to_manifest_form([0, 30000, 90000])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# phase_boundaries_to_segment_array_form
# ---------------------------------------------------------------------------

def test_segment_array_returns_four_named_segments_in_order_from_full_module():
    raw = {
        "intro_start_ms": 0,
        "intro_end_ms": 5000,
        "phase_a_start_ms": 5000,
        "phase_a_end_ms": 30000,
        "phase_b_start_ms": 30000,
        "phase_b_end_ms": 90000,
        "resolution_start_ms": 90000,
        "resolution_end_ms": 100000,
    }
    segs = phase_boundaries_to_segment_array_form(raw)
    assert [s["name"] for s in segs] == ["intro", "phase_a", "phase_b", "resolution"]
    assert segs[0] == {"name": "intro", "start_s": 0.0, "end_s": 5.0}
    assert segs[1] == {"name": "phase_a", "start_s": 5.0, "end_s": 30.0}
    assert segs[2] == {"name": "phase_b", "start_s": 30.0, "end_s": 90.0}
    assert segs[3] == {"name": "resolution", "start_s": 90.0, "end_s": 100.0}


def test_segment_array_from_manifest_form_collapses_unknown_phases():
    raw = {"story_start_ms": 0, "phase_b_start_ms": 30000, "phase_b_end_ms": 90000}
    segs = phase_boundaries_to_segment_array_form(raw)
    assert [s["name"] for s in segs] == ["intro", "phase_a", "phase_b", "resolution"]
    # phase_b duration is positive; intro/resolution are zero-duration when unknown.
    assert segs[2]["end_s"] - segs[2]["start_s"] == pytest.approx(60.0)
    assert segs[0]["start_s"] == segs[0]["end_s"]
    assert segs[3]["start_s"] == segs[3]["end_s"]


def test_segment_array_raises_when_phase_b_zero_duration():
    raw = {"story_start_ms": 0, "phase_b_start_ms": 30000, "phase_b_end_ms": 30000}
    with pytest.raises(ValueError):
        phase_boundaries_to_segment_array_form(raw)


# ---------------------------------------------------------------------------
# validate_phase_boundaries
# ---------------------------------------------------------------------------

def test_validate_accepts_valid_manifest_form():
    pb = {"story_start_ms": 0, "phase_b_start_ms": 30000, "phase_b_end_ms": 90000}
    validate_phase_boundaries(pb, total_duration_ms=100000)  # must not raise


def test_validate_rejects_phase_b_end_exceeding_total_duration():
    pb = {"story_start_ms": 0, "phase_b_start_ms": 30000, "phase_b_end_ms": 120000}
    with pytest.raises(ValueError):
        validate_phase_boundaries(pb, total_duration_ms=100000)


def test_validate_accepts_valid_segment_array():
    segs = [
        {"name": "intro", "start_s": 0.0, "end_s": 5.0},
        {"name": "phase_a", "start_s": 5.0, "end_s": 30.0},
        {"name": "phase_b", "start_s": 30.0, "end_s": 90.0},
        {"name": "resolution", "start_s": 90.0, "end_s": 100.0},
    ]
    validate_phase_boundaries(segs, total_duration_ms=100000)


def test_validate_rejects_segment_array_with_gap():
    segs = [
        {"name": "intro", "start_s": 0.0, "end_s": 5.0},
        {"name": "phase_a", "start_s": 6.0, "end_s": 30.0},  # gap from 5→6
        {"name": "phase_b", "start_s": 30.0, "end_s": 90.0},
        {"name": "resolution", "start_s": 90.0, "end_s": 100.0},
    ]
    with pytest.raises(ValueError):
        validate_phase_boundaries(segs, total_duration_ms=100000)


def test_validate_rejects_segment_array_with_wrong_name_order():
    segs = [
        {"name": "phase_a", "start_s": 0.0, "end_s": 5.0},
        {"name": "intro", "start_s": 5.0, "end_s": 30.0},
        {"name": "phase_b", "start_s": 30.0, "end_s": 90.0},
        {"name": "resolution", "start_s": 90.0, "end_s": 100.0},
    ]
    with pytest.raises(ValueError):
        validate_phase_boundaries(segs, total_duration_ms=100000)


def test_validate_rejects_wrong_segment_count():
    segs = [
        {"name": "intro", "start_s": 0.0, "end_s": 5.0},
        {"name": "phase_b", "start_s": 5.0, "end_s": 90.0},
        {"name": "resolution", "start_s": 90.0, "end_s": 100.0},
    ]
    with pytest.raises(ValueError):
        validate_phase_boundaries(segs, total_duration_ms=100000)


# ---------------------------------------------------------------------------
# (d) compute_app_compat_content_hash — hex output
# ---------------------------------------------------------------------------

def test_compute_hash_returns_64_char_lowercase_hex(tmp_path: Path):
    f = tmp_path / "asset.bin"
    f.write_bytes(b"hello world")
    digest = compute_app_compat_content_hash(f)
    assert HEX64_RE.match(digest), f"hash {digest!r} does not match ^[a-f0-9]{{64}}$"
    assert digest == hashlib.sha256(b"hello world").hexdigest()


def test_compute_hash_empty_file_returns_known_sha256(tmp_path: Path):
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    digest = compute_app_compat_content_hash(f)
    # Well-known SHA-256 of empty input.
    assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert HEX64_RE.match(digest)


def test_compute_hash_large_file_streams_correctly(tmp_path: Path):
    # Cross multi-MB read boundary inside the function.
    f = tmp_path / "big.bin"
    payload = b"\x00\x01\x02\x03" * (1024 * 1024)  # 4 MiB
    f.write_bytes(payload)
    digest = compute_app_compat_content_hash(f)
    assert digest == hashlib.sha256(payload).hexdigest()
    assert HEX64_RE.match(digest)


# ---------------------------------------------------------------------------
# (e) FileNotFoundError on missing file
# ---------------------------------------------------------------------------

def test_compute_hash_raises_file_not_found_on_missing(tmp_path: Path):
    missing = tmp_path / "does_not_exist.bin"
    with pytest.raises(FileNotFoundError):
        compute_app_compat_content_hash(missing)


def test_compute_hash_raises_file_not_found_on_directory(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        compute_app_compat_content_hash(tmp_path)
