"""Operator workbench authority — single resolver + write path per Beat Gen concept.

See Production/docs/BG_OPERATOR_WORKBENCH_AUTHORITY_SPEC_v1.md
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import beat_generator as bg


def resolve_beat_still_scene_abs_path(beat: dict) -> Path | None:
    """PNG/JPEG still for still_insert — library, gpt, flux, then ref dicts."""
    existing = bg.resolve_still_source_abs_path(beat)
    if existing is not None:
        return existing
    for opt in beat.get("flux_options") or []:
        if not isinstance(opt, dict):
            continue
        for key in ("local_path", "abs_path"):
            ap = str(opt.get(key) or "").strip()
            if ap and Path(ap).is_file():
                return Path(ap).resolve()
    return None


def _ref_thumb(abs_path: str, approved_roots: list[str] | None) -> str | None:
    if not abs_path or not approved_roots:
        return None
    try:
        from lib.event_library import ref_image_thumb_b64

        return ref_image_thumb_b64(abs_path, approved_roots)
    except Exception:
        return None


def _ref_dict_with_thumb(
    base: dict | None,
    abs_path: str,
    approved_roots: list[str] | None,
) -> dict:
    out = dict(base) if isinstance(base, dict) else {}
    out["abs_path"] = abs_path
    if not out.get("key"):
        out["key"] = Path(abs_path).stem
    if not out.get("thumb_b64"):
        thumb = _ref_thumb(abs_path, approved_roots)
        if thumb:
            out["thumb_b64"] = thumb
    return out


def resolve_beat_still_scene_ref(
    beat: dict,
    approved_roots: list[str] | None = None,
) -> dict | None:
    """Display-ready still scene ref for still_insert UI."""
    ap = resolve_beat_still_scene_abs_path(beat)
    if ap is None:
        return None
    abs_str = str(ap)
    lib = beat.get("accepted_library_ref") or {}
    if isinstance(lib, dict) and str(lib.get("abs_path") or "").strip() == abs_str:
        return _ref_dict_with_thumb(lib, abs_str, approved_roots)
    bg_ref = beat.get("bg_ref_image") or {}
    if isinstance(bg_ref, dict) and str(bg_ref.get("abs_path") or "").strip() == abs_str:
        return _ref_dict_with_thumb(bg_ref, abs_str, approved_roots)
    for opt in (beat.get("gpt_options") or []) + (beat.get("flux_options") or []):
        if not isinstance(opt, dict):
            continue
        for key in ("local_path", "abs_path"):
            if str(opt.get(key) or "").strip() == abs_str:
                return _ref_dict_with_thumb(opt, abs_str, approved_roots)
    return _ref_dict_with_thumb(None, abs_str, approved_roots)


def resolve_beat_char_ref_display(
    beat: dict,
    approved_roots: list[str] | None = None,
) -> dict | None:
    stored = beat.get("reference_image") if isinstance(beat.get("reference_image"), dict) else None
    stored_path = str(stored.get("abs_path") or "").strip() if stored else ""
    if stored_path and Path(stored_path).is_file():
        return _ref_dict_with_thumb(stored, stored_path, approved_roots)
    path = bg.resolve_beat_char_ref_path(beat)
    if not path:
        return None
    if stored and stored_path == path:
        return _ref_dict_with_thumb(stored, path, approved_roots)
    return _ref_dict_with_thumb(None, path, approved_roots)


def resolve_beat_bg_ref_display(
    beat: dict,
    event_id: str,
    phase: str,
    approved_roots: list[str] | None = None,
) -> dict | None:
    path = bg.resolve_beat_bg_ref_path(beat, event_id, phase)
    if not path:
        return None
    stored = beat.get("bg_ref_image") if isinstance(beat.get("bg_ref_image"), dict) else None
    if stored and str(stored.get("abs_path") or "").strip() == path:
        return _ref_dict_with_thumb(stored, path, approved_roots)
    return _ref_dict_with_thumb(None, path, approved_roots)


def write_still_scene_source(
    beat: dict,
    *,
    key: str,
    filename: str,
    abs_path: str,
    slot_index: int = 0,
    thumb_b64: str | None = None,
    source: str = "library_drop",
) -> None:
    """Atomic still-scene write — library drop, ref slot, and render read same fields."""
    beat["accepted_library_ref"] = {
        "key": key,
        "filename": filename,
        "abs_path": abs_path,
        "slot_index": slot_index,
    }
    beat["accepted_image_key"] = key
    beat["status"] = "lib_chosen"
    option_entry: dict[str, Any] = {
        "key": key,
        "source": source,
        "local_path": abs_path,
        "filename": filename,
    }
    if thumb_b64:
        option_entry["thumb_b64"] = thumb_b64
    opts = list(beat.get("gpt_options") or [])
    while len(opts) < slot_index:
        opts.append(None)
    if slot_index < len(opts) and isinstance(opts[slot_index], dict):
        opts[slot_index] = {**opts[slot_index], **option_entry}
    elif slot_index == len(opts):
        opts.append(option_entry)
    else:
        while len(opts) <= slot_index:
            opts.append(None)
        opts[slot_index] = option_entry
    beat["gpt_options"] = opts
    bg_ref: dict[str, Any] = {
        "key": key,
        "abs_path": abs_path,
        "filename": filename,
    }
    if thumb_b64:
        bg_ref["thumb_b64"] = thumb_b64
    beat["bg_ref_image"] = bg_ref


def migrate_operator_workbench_beat(beat: dict, *, heal_char_ref: bool = True) -> bool:
    """Persist one-time operator workbench heals (not GET overlay).

    ``heal_char_ref=False`` skips speaker/@Image1 hashing. That heal walks
    Element images through Dropbox and must not run under sidecar_file_lock
    (startup migrate held the lock for tens of minutes and hung every scope
    swap — 2026-07-26). Callers that hold the lock use False and schedule a
    deferred per-beat heal instead.
    """
    changed = False
    if bg.normalize_still_insert_approval_status(beat):
        changed = True
    if bg.heal_still_insert_option_keys(beat):
        changed = True
    if bg.beat_is_still_insert(beat):
        lib = beat.get("accepted_library_ref") or {}
        if isinstance(lib, dict) and lib.get("abs_path") and not beat.get("bg_ref_image"):
            ap = str(lib["abs_path"])
            if Path(ap).is_file():
                write_still_scene_source(
                    beat,
                    key=str(lib.get("key") or Path(ap).stem),
                    filename=str(lib.get("filename") or Path(ap).name),
                    abs_path=ap,
                    slot_index=int(lib.get("slot_index") or 0),
                    source="library_drop",
                )
                changed = True
        if not (beat.get("gpt_options") or []) and (beat.get("flux_options") or []):
            beat["gpt_options"] = [
                dict(o) for o in beat.get("flux_options") or [] if isinstance(o, dict)
            ]
            changed = True
    if not beat.get("generation_mode"):
        mode = bg.resolve_beat_generation_mode(beat, {})
        beat["generation_mode"] = mode
        changed = True
    if heal_char_ref and bg.heal_speaker_char_ref_mismatch(beat):
        changed = True
    return changed


def migrate_operator_workbench_sidecar(
    sidecar: dict, *, heal_char_ref: bool = True,
) -> bool:
    changed = False
    for arc in sidecar.get("arcs", {}).values():
        for seg in arc.get("segments", {}).values():
            for beat in seg.get("beats", []):
                if migrate_operator_workbench_beat(beat, heal_char_ref=heal_char_ref):
                    changed = True
    return changed


def materialize_char_ref_abs_path(beat: dict, body_abs_path: str = "") -> str:
    """Resolve absolute char-ref path for Element mutation handlers (persisted > body > implicit)."""
    explicit = (body_abs_path or "").strip()
    if explicit and os.path.isfile(explicit):
        return os.path.normpath(explicit)
    ref = beat.get("reference_image")
    if isinstance(ref, dict):
        stored = (ref.get("abs_path") or "").strip()
        if stored and os.path.isfile(stored):
            return os.path.normpath(stored)
    resolved = bg.resolve_beat_char_ref_path(beat)
    return os.path.normpath(resolved) if resolved else ""


def resolve_beat_element_char_ref_gate(beat: dict) -> tuple[bool, str | None]:
    """Read-only char-ref gate — ELEMENT_CHAR_REF_SUBMIT_PARITY_V1 (same as O3 intent commit)."""
    if bg._beat_pipeline_operator_busy(beat):
        return True, None
    speaker = str(beat.get("speaker") or "").strip()
    try:
        from tools import kling_character_registry as reg

        if not speaker or not reg.is_speaker_voice_ready(speaker):
            return True, None
    except Exception:
        return True, None
    char_path = bg.resolve_beat_char_ref_path(beat)
    if not char_path:
        return False, f"Missing character reference image for {speaker!r}"
    try:
        from tools import kling_character_registry as reg

        aligned, detail = reg.char_ref_aligned_for_intent_commit(char_path, speaker)
        if aligned:
            return True, None
        return False, detail or "Char ref does not match Element submit authority"
    except Exception as exc:
        return False, str(exc)


def resolve_beat_generation_gate(beat: dict, sidecar: dict) -> dict[str, Any]:
    """Shared operator generation gate for session GET, poll, submit preflight, and UI."""
    mode = bg.resolve_beat_generation_mode(beat, sidecar)
    if mode == bg.PIPELINE_MODE_STILL:
        ok, err = True, None
        can_generate = bool(resolve_beat_still_scene_abs_path(beat))
    elif not bg.element_char_ref_required_for_beat(beat, sidecar):
        char_path = bg.resolve_beat_char_ref_path(beat) or ""
        ok = bool(char_path and os.path.isfile(char_path))
        err = None if ok else "Missing character reference image"
        can_generate = ok
    else:
        ok, err = resolve_beat_element_char_ref_gate(beat)
        can_generate = ok
    return {
        "generation_mode": mode,
        "element_char_ref_ok": ok,
        "element_char_ref_error": err,
        "can_generate": can_generate,
    }


def materialize_o3_submit_refs(
    body: dict,
    beat: dict,
    *,
    event_id: str,
    phase: str,
    approved_roots: list[str] | None = None,
) -> tuple[dict | None, dict | None]:
    """Resolve char + BG refs for O3 submit; materialize implicit server paths."""
    from o3_generation_intent import resolve_o3_submit_refs

    char_ref, bg_ref = resolve_o3_submit_refs(body, beat)
    if char_ref is None:
        char_ref = resolve_beat_char_ref_display(beat, approved_roots)
    elif not str(char_ref.get("abs_path") or "").strip():
        mat = resolve_beat_char_ref_display(beat, approved_roots)
        if mat:
            char_ref = {**mat, **{k: v for k, v in char_ref.items() if v not in (None, "")}}
    if bg_ref is None:
        bg_ref = resolve_beat_bg_ref_display(beat, event_id, phase, approved_roots)
    elif not str(bg_ref.get("abs_path") or "").strip():
        mat = resolve_beat_bg_ref_display(beat, event_id, phase, approved_roots)
        if mat:
            bg_ref = {**mat, **{k: v for k, v in bg_ref.items() if v not in (None, "")}}
    return char_ref, bg_ref


def enrich_beat_operator_derived(
    beat: dict,
    sidecar: dict,
    *,
    event_id: str,
    phase: str,
    event_dir: str | Path | None = None,
    approved_roots: list[str] | None = None,
) -> dict[str, Any]:
    """Read-only derived block for session GET — never mutates beat operator fields."""
    gate = resolve_beat_generation_gate(beat, sidecar)
    display_prompt = bg.active_beat_prompt_for_generation_mode(beat, gate["generation_mode"])
    option_slots = bg.normalize_kling_o3_option_slots(beat, sidecar)
    derived: dict[str, Any] = {
        **gate,
        "display_prompt": display_prompt,
        "still_scene_display": resolve_beat_still_scene_ref(beat, approved_roots),
        "char_ref_display": resolve_beat_char_ref_display(beat, approved_roots),
        "bg_ref_display": resolve_beat_bg_ref_display(beat, event_id, phase, approved_roots),
        "option_slots": option_slots,
    }
    if event_dir is not None:
        from kling_stitch_readiness import beat_stitch_export_derived_fields  # noqa: PLC0415

        derived.update(beat_stitch_export_derived_fields(beat, event_dir))
    return derived


def enrich_beats_for_session_response(
    beats: list[dict],
    sidecar: dict,
    *,
    event_id: str,
    phase: str,
    approved_roots: list[str] | None,
    production_state: dict | None,
    video_role: str,
    event_dir: str | Path,
) -> list[dict]:
    """Build session GET beat list: disk fields + enrichments + _derived (no prompt overlay)."""
    out: list[dict] = []
    for beat in beats:
        row = copy.deepcopy(beat)
        row = bg.merge_storyboard_magic_into_bg_beat(
            row, production_state, video_role, sidecar, event_dir=None,
        )
        row = bg.enrich_beat_kling_o3_pinned(row, event_dir, session_read=True)
        row["_derived"] = enrich_beat_operator_derived(
            beat,
            sidecar,
            event_id=event_id,
            phase=phase,
            event_dir=event_dir,
            approved_roots=approved_roots,
        )
        row["generation_mode"] = row["_derived"]["generation_mode"]
        derived = row["_derived"]
        if derived.get("element_char_ref_ok") is not None:
            row["element_char_ref_ok"] = derived["element_char_ref_ok"]
        if derived.get("element_char_ref_error"):
            row["element_char_ref_error"] = derived["element_char_ref_error"]
        # Recompute mismatch/active-clip pipeline on read — stale sidecar flags
        # must not survive pipeline toggle + delivery import (session GET is read-only).
        bg.sync_o3_selection_pipeline_fields(row, sidecar)
        out.append(row)
    return out
