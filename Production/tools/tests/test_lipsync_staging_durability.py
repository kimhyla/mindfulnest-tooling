"""Production lipsync staging — durable URL hosting for voice-first Beat Gen."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import lipsync_sender
import lipsync_staging


def test_register_and_resolve_staging_file(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video-bytes")
    token = "attempt123"

    staged = lipsync_staging.register_staging_file(event_dir, token, source)

    assert staged.is_file()
    assert staged.read_bytes() == b"video-bytes"
    resolved = lipsync_staging.resolve_staged_file(event_dir, token, staged.name)
    assert resolved == staged


def test_build_staging_public_url() -> None:
    url = lipsync_staging.build_staging_public_url(
        "http://localhost:5112",
        "abc123",
        "line.mp3",
    )
    assert url == "http://localhost:5112/api/lipsync/staging/abc123/line.mp3"


def test_upload_to_hosting_prefers_production_staging(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"video-bytes")
    calls: list[str] = []

    def fake_staging(path: Path) -> dict:
        calls.append("staging")
        assert path == sample
        return {
            "host": "production_staging",
            "submitted_url": "http://localhost:5112/api/lipsync/staging/tok/sample.mp4",
            "landing_url": "http://localhost:5112/api/lipsync/staging/tok/sample.mp4",
            "bytes": sample.stat().st_size,
            "sha256": "abc",
        }

    monkeypatch.setattr(lipsync_sender, "_upload_via_production_staging", fake_staging)
    monkeypatch.setattr(lipsync_sender, "_upload_to_r2_staging", lambda path, token: calls.append("r2") or None)
    monkeypatch.setattr(lipsync_sender, "_upload_to_filebin", lambda path: calls.append("filebin") or None)

    proof = lipsync_sender.upload_to_hosting(sample)

    assert proof["host"] == "production_staging"
    assert calls == ["staging"]


def test_upload_to_hosting_falls_through_to_filebin(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"video-bytes")

    monkeypatch.setattr(lipsync_sender, "_upload_via_production_staging", lambda path: None)
    monkeypatch.setattr(lipsync_sender, "_upload_to_r2_staging", lambda path, token: None)
    monkeypatch.setattr(lipsync_sender, "_upload_to_filebin", lambda path: "https://filebin.net/bin/sample.mp4")
    monkeypatch.setattr(lipsync_sender, "_upload_to_catbox", lambda path: None)
    monkeypatch.setattr(lipsync_sender, "_upload_to_uguu", lambda path: None)
    monkeypatch.setattr(
        lipsync_sender,
        "_preflight_download_url",
        lambda path, url, *, host: {
            "host": host,
            "submitted_url": url,
            "landing_url": url,
            "bytes": path.stat().st_size,
            "sha256": "abc",
        },
    )

    proof = lipsync_sender.upload_to_hosting(sample)

    assert proof["host"] == "filebin.net"
