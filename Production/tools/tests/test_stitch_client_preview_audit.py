"""STITCH_CLIENT_PREVIEW_AUDIT_V1 — slot review playback forensics."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from server_handlers import stitch_editor as se


def test_stitch_client_preview_audit_writes_jsonl(tmp_path: Path) -> None:
    h = SimpleNamespace(app=SimpleNamespace(event_dir=str(tmp_path)))
    se._stitch_client_preview_audit(
        h,
        "VIDEO_PLAY",
        slot_key="resolution",
        job_name="Event_3_stitch",
        speech_ctx_state="running",
    )
    log_path = tmp_path / "_stitch_client_preview_audit.jsonl"
    assert log_path.is_file()
    row = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert row["code"] == se.STITCH_CLIENT_PREVIEW_AUDIT_V1
    assert row["event"] == "VIDEO_PLAY"
    assert row["slot_key"] == "resolution"


def test_handle_stitch_client_preview_audit_ok(tmp_path: Path) -> None:
    sent: list[dict] = []

    class Handler:
        app = SimpleNamespace(event_dir=str(tmp_path))

        @staticmethod
        def _send_json(status: int, payload: dict) -> dict:
            sent.append({"status": status, **payload})
            return payload

    out = se.handle_stitch_client_preview_audit(
        Handler(),
        {"event": "PLAY_REJECTED", "slot_key": "resolution", "reason": "NotAllowedError"},
    )
    assert out["ok"] is True
    assert (tmp_path / "_stitch_client_preview_audit.jsonl").is_file()


def test_stitch_client_preview_audit_marker_in_client() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "storyboard-v2/src/utils/stitchClientPreviewAudit.ts"
    ).read_text(encoding="utf-8")
    assert "STITCH_CLIENT_PREVIEW_AUDIT_V1" in src
    assert "wireComposerVideoPlayGuard" in (
        Path(__file__).resolve().parents[1]
        / "storyboard-v2/src/audio/StitchSlotAudioMixEngine.ts"
    ).read_text(encoding="utf-8")
