"""APFS ~/.mindfulnest/secrets beats Dropbox markdown for ElevenLabs."""
from __future__ import annotations

from pathlib import Path

import pytest

from credentials_lib import credentials


def _clear_elevenlabs_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ELEVENLABS_API_KEY", "ELEVENLABS_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_local_secret_beats_markdown_key_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_elevenlabs_env(monkeypatch)
    monkeypatch.setenv("_CREDSTORE_FALLBACK_WARNED", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    secret_dir = tmp_path / ".mindfulnest" / "secrets"
    secret_dir.mkdir(parents=True)
    (secret_dir / "elevenlabs_api_key").write_text("sk_local_test_secret\n", encoding="utf-8")
    monkeypatch.setattr(
        credentials,
        "_from_md_fallback",
        lambda _path=None: {
            "directus_url": "https://example.test",
            "directus_email": "ops@example.test",
            "directus_password": "x",
            "elevenlabs_key": "deadbeef" * 8,  # 64-char key ID shape
        },
    )

    creds = credentials.load_credentials()
    assert creds["elevenlabs_key"] == "sk_local_test_secret"


def test_env_beats_local_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_from_env")
    monkeypatch.setenv("HOME", str(tmp_path))
    secret_dir = tmp_path / ".mindfulnest" / "secrets"
    secret_dir.mkdir(parents=True)
    (secret_dir / "elevenlabs_api_key").write_text("sk_local_test_secret\n", encoding="utf-8")
    monkeypatch.setattr(
        credentials,
        "_from_md_fallback",
        lambda _path=None: {
            "directus_url": "https://example.test",
            "directus_email": "ops@example.test",
            "directus_password": "x",
            "elevenlabs_key": "deadbeef" * 8,
        },
    )

    creds = credentials.load_credentials()
    assert creds["elevenlabs_key"] == "sk_from_env"
