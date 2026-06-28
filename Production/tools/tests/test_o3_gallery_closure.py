"""Gallery closure invariant — terminal done implies delivery in kling_o3_options."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg
import pytest

from o3_gallery_closure import (
    assert_gallery_closed_before_terminal,
    beat_gallery_closure_pending,
    delivery_path_in_gallery,
    refresh_beat_gallery_fields_for_finalize,
)
from o3_job_status_contract import beat_job_busy


def test_delivery_path_in_gallery_requires_selectable_option() -> None:
    delivery = "/Event_3/kling_o3_clips/beat_g1_delivery.mp4"
    assert not delivery_path_in_gallery({"kling_o3_options": []}, delivery)
    assert not delivery_path_in_gallery(
        {"kling_o3_options": [], "kling_o3_video_path": delivery},
        delivery,
    )
    assert delivery_path_in_gallery(
        {
            "kling_o3_options": [{
                "video_path": delivery,
                "source": "kling_o3_checkpoint",
            }],
        },
        delivery,
    )


def test_beat_gallery_closure_pending_when_terminal_done_without_options(tmp_path: Path) -> None:
    delivery = tmp_path / "clip_delivery.mp4"
    delivery.write_bytes(b"v")
    beat = {"beat_id": "bg_arc1_event3_pre_beat_09", "kling_o3_options": []}
    terminal = {
        "status": "done",
        "delivered": {"video_path": str(delivery)},
    }
    assert beat_gallery_closure_pending(beat, tmp_path, terminal=terminal) is True
    beat["kling_o3_options"] = [{"video_path": str(delivery), "source": "kling_o3_checkpoint"}]
    assert beat_gallery_closure_pending(beat, tmp_path, terminal=terminal) is False


def test_beat_job_busy_true_until_gallery_closed(tmp_path: Path) -> None:
    job_id = "7ab3dc40"
    event_dir = tmp_path / "Event_3"
    terminal_dir = event_dir / "arlo_o3_jobs"
    delivery = terminal_dir / "kling_o3_clips" / "clip_delivery.mp4"
    delivery.parent.mkdir(parents=True, exist_ok=True)
    delivery.write_bytes(b"v")
    terminal_path = terminal_dir / f"{job_id}_terminal.json"
    terminal_path.write_text(
        json.dumps({
            "status": "done",
            "delivered": {"video_path": str(delivery)},
        }),
        encoding="utf-8",
    )
    beat = {
        "beat_id": "bg_arc1_event3_pre_beat_09",
        "o3_current_job_id": job_id,
        "kling_o3_options": [],
        "kling_o3_status": "approved",
        "kling_o3_video_path": str(delivery),
    }
    assert beat_job_busy(beat, event_dir) is True
    beat["kling_o3_options"] = [{"video_path": str(delivery), "source": "kling_o3_checkpoint"}]
    assert beat_job_busy(beat, event_dir) is False


def test_assert_gallery_closed_before_terminal_raises(
    monkeypatch, tmp_path: Path,
) -> None:
    beat_id = "bg_arc1_event3_pre_beat_09"
    delivery = tmp_path / "clip_delivery.mp4"
    delivery.write_bytes(b"v")
    sidecar_path = tmp_path / "beat_generator_state.json"
    sidecar_path.write_text(
        json.dumps({
            "schema_version": 1,
            "arcs": {
                "arc_1": {
                    "segments": {
                        "event_3_pre": {
                            "beats": [{
                                "beat_id": beat_id,
                                "kling_o3_options": [],
                            }],
                        },
                    },
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar_path))
    with pytest.raises(RuntimeError, match="gallery not closed"):
        assert_gallery_closed_before_terminal(beat_id, tmp_path, str(delivery))


def test_refresh_beat_gallery_fields_for_finalize_uses_beat_generator_module(
    monkeypatch, tmp_path: Path,
) -> None:
    """Regression: must not import phantom beat_generator_sidecar module."""
    beat_id = "bg_arc1_event3_post_beat_03"
    delivery = tmp_path / "clip_delivery.mp4"
    delivery.write_bytes(b"v")
    sidecar = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3_post": {
                        "beats": [{
                            "beat_id": beat_id,
                            "kling_o3_options": [{
                                "video_path": str(delivery),
                                "source": "kling_o3_checkpoint",
                            }],
                        }],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(tmp_path / "sidecar.json"))
    (tmp_path / "sidecar.json").write_text(json.dumps(sidecar), encoding="utf-8")
    monkeypatch.setattr(bg, "reconcile_o3_disk_deliveries_for_beat", lambda _b, _d: False)
    monkeypatch.setattr(bg, "recover_orphan_o3_delivery", lambda *a, **k: None)
    out = refresh_beat_gallery_fields_for_finalize(beat_id, tmp_path, str(delivery))
    assert out.get("kling_o3_options")
    assert delivery_path_in_gallery({"kling_o3_options": out["kling_o3_options"]}, str(delivery))
