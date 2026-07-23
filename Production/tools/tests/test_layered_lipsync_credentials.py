"""Credential isolation for the layered lipsync CLI."""
from __future__ import annotations

import pytest

from credentials_lib import credentials


def test_wavespeed_env_is_sufficient(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("WAVESPEED_API_KEY", "test-wavespeed-secret")
    monkeypatch.setattr(
        credentials,
        "_from_md_fallback",
        lambda _path=None: pytest.fail("markdown fallback must not be read"),
    )

    assert credentials.load_wavespeed_api_key() == "test-wavespeed-secret"
    captured = capsys.readouterr()
    assert "test-wavespeed-secret" not in captured.out
    assert "test-wavespeed-secret" not in captured.err


def test_wavespeed_markdown_fallback_does_not_require_directus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WAVESPEED_API_KEY", raising=False)
    monkeypatch.setenv("_CREDSTORE_FALLBACK_WARNED", "1")
    monkeypatch.setattr(
        credentials,
        "_from_md_fallback",
        lambda _path=None: {"wavespeed_key": "fallback-only"},
    )

    assert credentials.load_wavespeed_api_key("keys.md") == "fallback-only"


def test_missing_wavespeed_key_fails_without_secret_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WAVESPEED_API_KEY", raising=False)
    monkeypatch.setattr(
        credentials,
        "_from_md_fallback",
        lambda _path=None: {},
    )

    with pytest.raises(ValueError, match="Missing WAVESPEED_API_KEY"):
        credentials.load_wavespeed_api_key("keys.md")
