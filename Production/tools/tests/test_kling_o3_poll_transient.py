"""WaveSpeed O3 poll transient gateway retry + redo failure restore."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402
import kling_o3_client as o3  # noqa: E402


def test_poll_until_done_retries_transient_502(monkeypatch):
    calls = {"n": 0}

    def fake_curl(method, url, api_key, payload=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return 502, {"raw": "<html>502 Bad Gateway</html>"}
        return 200, {"data": {"status": "completed", "outputs": ["https://example.com/out.mp4"]}}

    monkeypatch.setattr(o3, "curl_json", fake_curl)
    monkeypatch.setattr(o3, "POLL_INTERVAL_S", 0)
    monkeypatch.setattr(o3, "POLL_TRANSIENT_BACKOFF_S", (0, 0, 0))
    monkeypatch.setattr(o3, "POLL_TRANSIENT_MAX_RETRIES", 5)

    result = o3.poll_until_done("task-502", "key", timeout_s=30, retry_on_timeout=False)
    assert result["status"] == "completed"
    assert calls["n"] == 3


def test_poll_until_done_raises_after_transient_retries_exhausted(monkeypatch):
    def fake_curl(method, url, api_key, payload=None):
        return 502, {"raw": "<html>502 Bad Gateway</html>"}

    monkeypatch.setattr(o3, "curl_json", fake_curl)
    monkeypatch.setattr(o3, "POLL_INTERVAL_S", 0)
    monkeypatch.setattr(o3, "POLL_TRANSIENT_BACKOFF_S", (0,))
    monkeypatch.setattr(o3, "POLL_TRANSIENT_MAX_RETRIES", 2)

    with pytest.raises(RuntimeError, match="Poll HTTP 502"):
        o3.poll_until_done("task-fail", "key", timeout_s=5, retry_on_timeout=False)


def test_restore_active_kling_o3_after_failed_redo(tmp_path: Path):
    clip = tmp_path / "prior_delivery.mp4"
    clip.write_bytes(b"mp4")
    beat = {
        "beat_id": "bg_test_beat_01",
        "status": "o3_element_running",
        "kling_o3_status": "submitted",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [
            {
                "key": "opt1",
                "video_path": str(clip),
                "active": True,
                "source": "prior_kling_o3_redo",
            },
        ],
    }
    assert bg.restore_active_kling_o3_after_failed_redo(beat) is True
    assert beat["kling_o3_status"] == "approved"
    assert beat["status"] == "approved"
    assert beat["kling_o3_video_path"] == str(clip)
    assert beat.get("kling_o3_voice_fix_status") == "approved"
    assert "kling_o3_voice_fix_error" not in beat


def test_run_beat_generation_returns_retry_safe_on_poll_gateway_error(monkeypatch):
    monkeypatch.setattr(o3, "submit_reference_to_video", lambda *a, **k: ("task-abc", "pro"))
    monkeypatch.setattr(
        o3,
        "poll_until_done",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Poll HTTP 502: {'raw': 'bad gateway'}")),
    )
    result = o3.run_beat_generation("key", "prompt", "/c.png", "/b.png", Path("/out.mp4"), speaker="Arlo")
    assert result["ok"] is False
    assert result["task_id"] == "task-abc"
    assert result["retry_safe"] is True
    assert result["status"] == "poll_gateway_error"


def test_o3_element_pipeline_prefers_runtime_prod_script():
    text = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    block = text.split("def handle_bg_submit_arlo_o3_voice")[1].split("\ndef handle_bg_poll_arlo_o3_voice_status")[0]
    prod_first = block.index('script = prod / "tools" / "kling_o3_element_beat_pipeline.py"')
    fallback = block.index("script = _PSERVER_TOOLS_DIR")
    assert prod_first < fallback
