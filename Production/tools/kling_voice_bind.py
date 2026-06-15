"""Voice bind lifecycle — history, rollback, drift detection.

Pose re-register (Add to Element) keeps ``kling_voice_id``.
Voice refresh (create-voice) mints a new clone and must not blind-overwrite a working bind.

Dependency order:
  1. History archive + rollback helpers (this module)
  2. CLI gates (--confirm-voice-overwrite, --refresh-poses-only)
  3. setup_character_voice uses archive before overwrite
  4. O3 submit drift warning (registry vs last approved beat quality)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def active_voice_bind(cfg: dict) -> dict[str, str]:
    """Return current active element_id + kling_voice_id from character cfg."""
    out: dict[str, str] = {}
    eid = str(cfg.get("element_id") or "").strip()
    vid = str(cfg.get("kling_voice_id") or "").strip()
    if eid:
        out["element_id"] = eid
    if vid:
        out["kling_voice_id"] = vid
    return out


def archive_voice_bind(cfg: dict, *, reason: str) -> dict:
    """Append current active bind to voice_bind_history before overwrite."""
    bind = active_voice_bind(cfg)
    if not bind:
        return cfg
    updated = dict(cfg)
    history = list(updated.get("voice_bind_history") or [])
    history.append({
        **bind,
        "archived_at": _now_iso(),
        "reason": (reason or "voice_refresh").strip(),
        "kling_voice_label": str(cfg.get("kling_voice_label") or ""),
        "wavespeed_prediction_id": str(cfg.get("wavespeed_prediction_id") or ""),
    })
    # Keep last 5 binds for rollback
    updated["voice_bind_history"] = history[-5:]
    return updated


def rollback_voice_bind(chars: dict, char_name: str) -> tuple[dict, bool]:
    """Restore previous bind from voice_bind_history. Returns (chars, changed)."""
    cfg = dict(chars.get(char_name) or {})
    history = list(cfg.get("voice_bind_history") or [])
    if not history:
        return chars, False
    prev = history.pop()
    for key in ("element_id", "kling_voice_id", "kling_voice_label", "wavespeed_prediction_id"):
        val = prev.get(key)
        if val:
            cfg[key] = val
    archived_at = prev.get("archived_at")
    if archived_at:
        cfg["created_at"] = archived_at
    cfg["status"] = "active"
    cfg["voice_bind_history"] = history
    chars = dict(chars)
    chars[char_name] = cfg
    return chars, True


def validate_voice_overwrite_allowed(cfg: dict, *, confirm: bool) -> list[str]:
    """Errors when replacing an active voice bind without explicit confirm."""
    if cfg.get("status") != "active":
        return []
    if not active_voice_bind(cfg):
        return []
    if confirm:
        return []
    return [
        "active voice bind exists — pass --confirm-voice-overwrite to replace "
        "(pose-only updates use --refresh-poses-only; see kling-voice-bind-guardrails)"
    ]


def validate_create_voice_candidate(
    *,
    previous_voice_id: str | None,
    new_voice_id: str | None,
    sample_size_bytes: int,
    min_sample_bytes: int = 1000,
) -> list[str]:
    """Minimal post-create-voice sanity before registry write."""
    errors: list[str] = []
    new_id = str(new_voice_id or "").strip()
    if not new_id:
        errors.append("create-voice returned empty voice_id")
    if sample_size_bytes < min_sample_bytes:
        errors.append(f"voice sample too small ({sample_size_bytes} bytes)")
    old_id = str(previous_voice_id or "").strip()
    if old_id and new_id and old_id == new_id:
        errors.append(
            "create-voice returned the same voice_id as the active bind — "
            "provider did not mint a new clone"
        )
    return errors


def detect_voice_bind_drift(beat: dict, speaker: str, registry_voice_id: str | None) -> str | None:
    """Warn when registry voice_id differs from this beat's last approved O3 bind."""
    quality = beat.get("o3_element_quality") or {}
    if not isinstance(quality, dict):
        return None
    if str(quality.get("speaker") or "").strip() != str(speaker or "").strip():
        return None
    approved_vid = str(quality.get("kling_voice_id") or "").strip()
    current_vid = str(registry_voice_id or "").strip()
    if not approved_vid or not current_vid or approved_vid == current_vid:
        return None
    approved_eid = str(quality.get("element_id") or "").strip()
    return (
        f"registry voice_id {current_vid} differs from this beat's last approved "
        f"bind {approved_vid}"
        + (f" (element {approved_eid})" if approved_eid else "")
        + " — redo may sound different; pass accept_voice_drift to proceed"
    )
