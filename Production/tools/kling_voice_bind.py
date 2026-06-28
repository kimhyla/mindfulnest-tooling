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


def active_o3_option_voice_binding(beat: dict) -> dict[str, str]:
    """Return element_id + kling_voice_id from the active O3 option row, if any."""
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    active = next((o for o in options if o.get("active")), None)
    if active is None:
        video_path = str(beat.get("kling_o3_video_path") or "").strip()
        if video_path:
            active = next(
                (o for o in options if str(o.get("video_path") or "").strip() == video_path),
                None,
            )
    binding = (active or {}).get("o3_voice_binding") or {}
    if not isinstance(binding, dict):
        return {}
    out: dict[str, str] = {}
    eid = str(binding.get("element_id") or "").strip()
    vid = str(binding.get("kling_voice_id") or "").strip()
    if eid:
        out["element_id"] = eid
    if vid:
        out["kling_voice_id"] = vid
    return out


def reconcile_o3_element_quality_for_submit(
    beat: dict,
    speaker: str,
    *,
    registry_element_id: str | None,
    registry_voice_id: str | None,
) -> bool:
    """Refresh stale ``o3_element_quality`` when registry matches the active clip bind."""
    reg_eid = str(registry_element_id or "").strip()
    reg_vid = str(registry_voice_id or "").strip()
    if not reg_eid or not reg_vid:
        return False
    active_bind = active_o3_option_voice_binding(beat)
    if (
        active_bind.get("kling_voice_id") != reg_vid
        or active_bind.get("element_id") != reg_eid
    ):
        return False
    quality = beat.get("o3_element_quality")
    if not isinstance(quality, dict):
        quality = {}
    if (
        str(quality.get("speaker") or "").strip() == str(speaker or "").strip()
        and str(quality.get("element_id") or "").strip() == reg_eid
        and str(quality.get("kling_voice_id") or "").strip() == reg_vid
        and not quality.get("pinned_from_beat_id")
    ):
        return False
    updated = dict(quality)
    updated["speaker"] = str(speaker or "").strip()
    updated["element_id"] = reg_eid
    updated["kling_voice_id"] = reg_vid
    updated["applied_at"] = _now_iso()
    updated.pop("pinned_from_beat_id", None)
    beat["o3_element_quality"] = updated
    return True


def advance_o3_element_quality_for_proven_registry(
    beat: dict,
    speaker: str,
    *,
    registry_element_id: str | None,
    registry_voice_id: str | None,
) -> bool:
    """Advance stale ``o3_element_quality`` when registry matches proven_o3_bind.

    Event-wide voice stack migrations (e.g. Lorelai Beat 18) are intentional —
    not ad-hoc drift that requires ``accept_voice_drift`` on every redo.
    """
    reg_eid = str(registry_element_id or "").strip()
    reg_vid = str(registry_voice_id or "").strip()
    if not reg_eid or not reg_vid:
        return False
    try:
        from tools import kling_character_registry as reg

        proven = reg.resolve_proven_o3_bind(reg.get_character_entry(speaker) or {}) or {}
    except Exception:
        proven = {}
    if (
        str(proven.get("element_id") or "").strip() != reg_eid
        or str(proven.get("kling_voice_id") or "").strip() != reg_vid
    ):
        return False
    quality = beat.get("o3_element_quality")
    if not isinstance(quality, dict):
        quality = {}
    if (
        str(quality.get("speaker") or "").strip() == str(speaker or "").strip()
        and str(quality.get("element_id") or "").strip() == reg_eid
        and str(quality.get("kling_voice_id") or "").strip() == reg_vid
    ):
        return False
    updated = dict(quality)
    updated["speaker"] = str(speaker or "").strip()
    updated["element_id"] = reg_eid
    updated["kling_voice_id"] = reg_vid
    updated["applied_at"] = _now_iso()
    updated["advanced_from"] = "proven_registry_migration"
    updated.pop("pinned_from_beat_id", None)
    beat["o3_element_quality"] = updated
    return True


def detect_voice_bind_drift(beat: dict, speaker: str, registry_voice_id: str | None) -> str | None:
    """Warn when registry voice_id differs from this beat's last approved O3 bind."""
    pin = beat.get("o3_voice_stack_pin")
    if isinstance(pin, dict) and str(pin.get("kling_voice_id") or "").strip():
        return None
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
