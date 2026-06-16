"""Regression gates for Kling LipSync URL hosting and failure messaging."""
from __future__ import annotations

from pathlib import Path

import lipsync_sender

TOOLS = Path(__file__).resolve().parent.parent


def test_upload_to_hosting_prefers_filebin_and_requires_preflight(monkeypatch, tmp_path) -> None:
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"video-bytes")
    calls: list[str] = []

    def fake_filebin(path: Path) -> str:
        calls.append("filebin-upload")
        assert path == sample
        return "https://filebin.net/bin/sample.mp4"

    def fake_preflight(path: Path, url: str, *, host: str) -> dict:
        calls.append(f"{host}-preflight")
        assert path == sample
        assert url == "https://filebin.net/bin/sample.mp4"
        return {
            "host": host,
            "submitted_url": "https://storage.filebin.net/raw-presigned",
            "landing_url": url,
            "bytes": sample.stat().st_size,
            "sha256": "abc",
        }

    monkeypatch.setattr(lipsync_sender, "_upload_to_filebin", fake_filebin)
    monkeypatch.setattr(lipsync_sender, "_upload_to_catbox", lambda path: calls.append("catbox-upload") or None)
    monkeypatch.setattr(lipsync_sender, "_upload_to_uguu", lambda path: calls.append("uguu-upload") or None)
    monkeypatch.setattr(lipsync_sender, "_preflight_download_url", fake_preflight)

    proof = lipsync_sender.upload_to_hosting(sample)

    assert proof["host"] == "filebin.net"
    assert proof["submitted_url"] == "https://storage.filebin.net/raw-presigned"
    assert calls == ["filebin-upload", "filebin.net-preflight"]


def test_upload_to_hosting_fails_closed_when_preflight_rejects_all(monkeypatch, tmp_path) -> None:
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"video-bytes")

    monkeypatch.setattr(lipsync_sender, "_upload_to_filebin", lambda path: "https://filebin.net/bin/sample.mp4")
    monkeypatch.setattr(lipsync_sender, "_upload_to_catbox", lambda path: "https://files.catbox.moe/sample.mp4")
    monkeypatch.setattr(lipsync_sender, "_upload_to_uguu", lambda path: None)
    monkeypatch.setattr(lipsync_sender, "_preflight_download_url", lambda path, url, *, host: None)

    try:
        lipsync_sender.upload_to_hosting(sample)
    except lipsync_sender.LipsyncHostingError as exc:
        assert "No lipsync input host returned byte-complete public files" in str(exc)
        assert "filebin.net: preflight failed" in str(exc)
        assert "catbox.moe: preflight failed" in str(exc)
    else:
        raise AssertionError("upload_to_hosting should fail closed when no preflight passes")


def test_url_submit_uses_preflight_submitted_urls(monkeypatch, tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    audio = tmp_path / "line.mp3"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    submitted: dict = {}

    def fake_upload(path: Path) -> dict:
        kind = "video" if path == video else "audio"
        return {
            "host": "filebin.net",
            "submitted_url": f"https://storage.filebin.net/{kind}",
            "landing_url": f"https://filebin.net/bin/{path.name}",
            "bytes": path.stat().st_size,
            "sha256": kind,
        }

    def fake_curl_json(self, method: str, url: str, body: dict | None = None, timeout: int = 60) -> dict:
        submitted["method"] = method
        submitted["url"] = url
        submitted["body"] = body
        return {"data": {"id": "job_123", "urls": {"get": "https://poll/job_123"}}}

    monkeypatch.setattr(lipsync_sender, "upload_to_hosting", fake_upload)
    monkeypatch.setattr(lipsync_sender.LipSyncClient, "_curl_json", fake_curl_json)

    client = lipsync_sender.LipSyncClient("test-key")
    job_id = client.submit(video, audio, transport="url")

    assert job_id == "job_123"
    assert submitted["body"] == {
        "video": "https://storage.filebin.net/video",
        "audio": "https://storage.filebin.net/audio",
    }
    assert client.last_url_transport_preflight["video"]["landing_url"].endswith("clip.mp4")


def test_wavespeed_lipsync_contract_records_no_resolution_parameter() -> None:
    contract = lipsync_sender.LIPSYNC_PROVIDER_CONTRACT
    assert contract["model"] == "kwaivgi/kling-lipsync/audio-to-video"
    assert contract["has_output_resolution_parameter"] is False
    assert "reject" in contract["quality_invariant"].lower()


def test_ui_failure_copy_does_not_promise_low_quality_fallback() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "Data-URI fallback is disabled because it returns sub-720p output" in src
    assert "We retry with embedded data when possible" not in src


def test_ui_active_o3_jobs_reconciles_from_server_truth() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "setActiveO3Jobs(collectActiveO3JobsFromBeats(initialBeats));" in src
    assert "setActiveO3Jobs(collectActiveO3JobsFromBeats(nextBeats));" in src
    assert "...collectActiveO3JobsFromBeats(initialBeats), ...prev" not in src
    assert "...collectActiveO3JobsFromBeats(nextBeats), ...prev" not in src
    assert "o3JobStatusContract" in src
    contract = (TOOLS / "storyboard-v2" / "src" / "o3JobStatusContract.ts").read_text(encoding="utf-8")
    assert "'o3_running'" in contract
