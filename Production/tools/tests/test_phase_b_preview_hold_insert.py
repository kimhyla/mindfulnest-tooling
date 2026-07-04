"""PHASE_B_PREVIEW_HOLD_INSERT_V1 — on-demand post-bake hold tool."""
from __future__ import annotations

import json
from pathlib import Path

import phase_b_preview_hold_insert as hold


def test_drift_within_gate_uses_stitch_export_threshold():
    assert hold.drift_within_gate(0.132)
    assert not hold.drift_within_gate(0.5)


def test_production_rel_path_under_dropbox():
    prod = Path("/tmp/Dropbox/Production")
    out = prod / "Event_3/preview/phase_b/foo.mp4"
    assert hold.production_rel_path(out, production_root=prod) == (
        "Production/Event_3/preview/phase_b/foo.mp4"
    )


def test_build_manifest_includes_seams_and_hold():
    payload = hold.build_manifest(
        source=Path("src.mp4"),
        output=Path("out.mp4"),
        insert_at_s=150.4,
        hold_s=3.0,
        duration_before_s=198.0,
        duration_after_s=201.0,
        seams=[hold.SeamSpec(out_s=150.4, in_s=155.175, label="cedric_150")],
        av_drift_s=0.132,
    )
    assert payload["schema_version"] == hold.PHASE_B_PREVIEW_HOLD_INSERT_V1
    assert payload["insert_at_s"] == 150.4
    assert payload["hold_s"] == 3.0
    assert payload["seams"][0]["module_join_out_s"] == 150.4
    assert payload["av_drift_s"] == 0.132


def test_dry_run_does_not_require_output_file(tmp_path: Path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    out = tmp_path / "out.mp4"
    rc = hold.main([
        "--src", str(src),
        "--out", str(out),
        "--insert-at", "150.4",
        "--hold-s", "3",
        "--dry-run",
    ])
    assert rc == 0
    assert not out.exists()


def test_script_docstring_states_on_demand_only():
    assert "ON-DEMAND" in (hold.__doc__ or "")
    assert "not wired" in (hold.__doc__ or "").lower()
