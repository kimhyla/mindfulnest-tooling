"""Regression gates for isolated Kling native lipsync experiments."""
from __future__ import annotations

import os
from pathlib import Path

import kling_native_lipsync_adapters as adapters
import kling_native_lipsync_experiment as experiment

TOOLS = Path(__file__).resolve().parent.parent


def test_route_registry_contains_only_explicit_route_ids() -> None:
    assert set(adapters.get_route_registry()) == {
        "wavespeed_kling_lipsync_baseline",
        "fal_kling_lipsync_a2v",
        "runcomfy_kling_lipsync_a2v",
        "native_kling_lip_sync_a2v",
        "native_kling_lip_sync_a2v_b64",
        "native_kling_identify_face_advanced_lipsync",
    }
    src = (TOOLS / "kling_native_lipsync_adapters.py").read_text(encoding="utf-8")
    assert "get_route_registry" in src
    assert "globals()[" not in src
    assert "eval(" not in src


def test_missing_optional_provider_credentials_classify_blocked(monkeypatch) -> None:
    for key in (
        "FAL_KEY",
        "FAL_API_KEY",
        "RUNCOMFY_API_KEY",
        "RUNCOMFY_KEY",
        "KLING_NATIVE_BASE_URL",
        "KLING_COMPAT_BASE_URL",
        "KLING_NATIVE_API_KEY",
        "KLING_COMPAT_API_KEY",
        "KLING_ACCESS_KEY",
        "KLING_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(adapters, "_resolve_fal_key", lambda: "")
    monkeypatch.setattr(adapters, "_resolve_runcomfy_key", lambda: "")
    monkeypatch.setattr(adapters, "_resolve_kling_direct_credentials", lambda: ("", "", "", ""))

    for adapter in (
        adapters.FalKlingLipSyncAdapter(),
        adapters.RunComfyKlingLipSyncAdapter(),
        adapters.NativeKlingAdvancedLipSyncAdapter(),
    ):
        try:
            adapter.submit(video_path=Path("missing.mp4"), audio_path=Path("missing.wav"), work_dir=Path("."))
        except adapters.RouteBlocked as exc:
            assert exc.code == "blocked_missing_credentials"
        else:
            raise AssertionError(f"{adapter.route_id} did not fail closed without credentials")


def test_fal_submit_uses_key_auth_and_fails_fast_on_provider_detail(monkeypatch) -> None:
    monkeypatch.setattr(adapters, "_resolve_fal_key", lambda: "fal-test-key")

    def fake_upload(path: Path) -> dict:
        return {"submitted_url": f"https://example.com/{path.name}", "host": "example.com", "bytes": 1, "sha256": "x", "content_type": "video/mp4", "status": 200}

    monkeypatch.setattr(adapters, "upload_to_hosting", fake_upload)

    captured: dict[str, str] = {}

    def fake_curl(method, url, *, api_key, body=None, timeout=120, auth_scheme="Bearer"):
        captured["auth_scheme"] = auth_scheme
        return {"detail": "User is locked. Reason: Exhausted balance."}

    monkeypatch.setattr(adapters, "_curl_json", fake_curl)

    adapter = adapters.FalKlingLipSyncAdapter()
    try:
        adapter.submit(video_path=Path("video.mp4"), audio_path=Path("audio.mp3"), work_dir=Path("."))
    except adapters.RouteBlocked as exc:
        assert exc.code == "provider_billing_or_auth_error"
        assert "Exhausted balance" in str(exc)
    else:
        raise AssertionError("Fal billing/auth errors must fail fast")
    assert captured["auth_scheme"] == "Key"


def test_native_credentials_detect_jwt_mode_from_access_and_secret(monkeypatch) -> None:
    monkeypatch.setenv("KLING_ACCESS_KEY", "access-test")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret-test")
    monkeypatch.delenv("KLING_NATIVE_API_KEY", raising=False)
    adapter = adapters.NativeKlingAdvancedLipSyncAdapter()
    cred = adapter.validate_credentials()
    assert cred["ok"] is True
    assert cred["auth_mode"] == "jwt"
    from urllib.parse import urlparse

    host = urlparse(adapter.base_url).hostname or ""
    assert host.endswith("klingai.com")


def test_gate_requires_audio_and_min_dimension_720() -> None:
    assert experiment.passes_gate({"width": 1280, "height": 720, "min_dimension": 720, "has_audio": True})
    assert not experiment.passes_gate({"width": 832, "height": 464, "min_dimension": 464, "has_audio": True})
    assert not experiment.passes_gate({"width": 720, "height": 544, "min_dimension": 544, "has_audio": True})
    assert not experiment.passes_gate({"width": 1280, "height": 720, "min_dimension": 720, "has_audio": False})


def test_experiment_field_guard_rejects_approval_fields() -> None:
    try:
        experiment.update_experiment_fields("beat_x", {"kling_o3_status": "approved"})
    except ValueError as exc:
        assert "forbidden fields" in str(exc)
    else:
        raise AssertionError("approval field write was not rejected")


def test_experiment_runner_never_writes_approval_fields_by_source_contract() -> None:
    src = (TOOLS / "kling_native_lipsync_experiment.py").read_text(encoding="utf-8")
    assert "FORBIDDEN_EXPERIMENT_FIELDS" in src
    assert '"kling_o3_status": "approved"' not in src
    assert '"status": "approved"' not in src
    assert "kling_native_lipsync_experiment_passed_gate" in src


def test_native_lipsync_request_includes_sound_end_time() -> None:
    src = (TOOLS / "kling_native_lipsync_adapters.py").read_text(encoding="utf-8")
    assert "sound_end_time" in src
    assert "_audio_duration_ms" in src


def test_due_diligence_module_defines_qa_matrix() -> None:
    src = (TOOLS / "kling_native_lipsync_due_diligence.py").read_text(encoding="utf-8")
    assert "DD-01" in src
    assert "native_kling_lip_sync_a2v_b64" in src
    assert "qa_report.json" in src


def test_browser_copy_mentions_no_approval() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "No approval. Raw provider output must pass >=720 before promotion." in src

