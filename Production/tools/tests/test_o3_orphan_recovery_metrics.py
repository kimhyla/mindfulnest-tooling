"""W2 — orphan recovery metrics: structured log on recovery; happy path never calls recover."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import beat_generator as bg


def test_orphan_recovery_logs_structured_tag(tmp_path: Path, monkeypatch, capsys) -> None:
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_27"
    delivery = clips / f"{beat_id}_g10_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")
    sidecar_path = tmp_path / "beat_generator_state.json"
    sidecar_path.write_text(
        json.dumps({
            "schema_version": 1,
            "arcs": {
                "arc_1": {
                    "segments": {
                        "event_2_pre": {
                            "beats": [{
                                "beat_id": beat_id,
                                "speaker": "Lorelai",
                                "kling_o3_options": [None, None, None],
                            }],
                        },
                    },
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar_path))
    log_path = event_dir / "arlo_o3_jobs" / "abc123.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        json.dumps({"phase": "done", "video": str(delivery)}) + "\n",
        encoding="utf-8",
    )

    bg.recover_orphan_o3_delivery(beat_id, event_dir, log_path=log_path, make_active=True)
    captured = capsys.readouterr()
    assert "[o3_orphan_recovery]" in captured.out


def test_element_pipeline_happy_path_checkpoint_before_orphan():
    src = (
        Path(__file__).resolve().parent.parent
        / "kling_o3_element_beat_pipeline.py"
    ).read_text(encoding="utf-8")
    block = src.split("def run_pipeline_from_intent", 1)[1].split("\ndef ", 1)[0]
    try_idx = block.index("bg_sidecar.persist_o3_delivery_option_checkpoint")
    except_idx = block.index("except Exception as exc:", try_idx)
    recover_idx = block.index("_recover_orphan", except_idx)
    assert try_idx < except_idx < recover_idx


def test_try_orphan_recovery_wrapper_logs_tag():
    bg_mod = __import__(
        "server_handlers.background",
        fromlist=["_try_orphan_o3_delivery_recovery"],
    )
    src = (
        Path(__file__).resolve().parent.parent
        / "server_handlers"
        / "background.py"
    ).read_text(encoding="utf-8")
    block = src.split("def _try_orphan_o3_delivery_recovery", 1)[1].split("\ndef ", 1)[0]
    assert "[o3_orphan_recovery]" in block
