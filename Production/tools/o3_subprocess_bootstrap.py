"""O3 subprocess sidecar bootstrap — same store as HTTP handler (event + milestone).

Category fix: subprocess pipelines must not read raw ``beat_generator_state.json``
before ``init_bg_paths`` binds milestone sidecar / SQLite authority.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import beat_generator as bg
from arlo_o3_voice_pipeline import _find_beat
from kling_o3_element_beat_pipeline import _event_dir_for_segment, _runtime_prod_root


def _load_milestone_skeleton_ref() -> dict | None:
    raw = (os.environ.get("MN_MILESTONE_SKELETON_REF") or "").strip()
    if not raw:
        return None
    try:
        skel = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return skel if isinstance(skel, dict) and skel.get("event_id") else None


def _bootstrap_scope_from_intent_env() -> None:
    """When subprocess env lost milestone scope, restore from committed intent file."""
    if (os.environ.get("MN_MILESTONE_DIR") or "").strip():
        return
    raw = (os.environ.get("MN_O3_INTENT_PATH") or "").strip()
    if not raw:
        return
    try:
        intent = json.loads(Path(raw).expanduser().resolve().read_text(encoding="utf-8"))
    except Exception:
        return
    scope = intent.get("runtime_scope") or {}
    if not isinstance(scope, dict) or scope.get("scope_type") != "milestone":
        return
    mdir = str(scope.get("milestone_dir") or "").strip()
    lib = str(scope.get("library_event_dir") or "").strip()
    if mdir:
        os.environ["MN_MILESTONE_DIR"] = mdir
    if lib:
        os.environ["MN_BG_LIBRARY_EVENT_DIR"] = lib
        os.environ["MN_O3_EVENT_DIR"] = lib
    skel = scope.get("skeleton_ref")
    if isinstance(skel, dict) and skel.get("event_id") and not os.environ.get("MN_MILESTONE_SKELETON_REF"):
        os.environ["MN_MILESTONE_SKELETON_REF"] = json.dumps(skel)


def init_bg_paths_for_o3_subprocess(*, beat_id: str, prod_root: Path) -> Path:
    """Bind beat_generator paths; return event_dir used for job artifacts."""
    _bootstrap_scope_from_intent_env()
    milestone_raw = (os.environ.get("MN_MILESTONE_DIR") or "").strip()
    if milestone_raw:
        milestone_dir = Path(milestone_raw).expanduser().resolve()
        library_raw = (os.environ.get("MN_BG_LIBRARY_EVENT_DIR") or "").strip()
        library_event_dir = (
            Path(library_raw).expanduser().resolve()
            if library_raw
            else milestone_dir.parent.parent / "Event_1"
        )
        skel = _load_milestone_skeleton_ref()
        if skel:
            bg.set_milestone_skeleton_ref(skel)
        bg.init_bg_paths(
            library_event_dir,
            milestone_dir=milestone_dir,
            library_event_dir=library_event_dir,
        )
        return library_event_dir

    global_sidecar = prod_root / "beat_generator_state.json"
    segment_key = ""
    if global_sidecar.is_file():
        try:
            sc = json.loads(global_sidecar.read_text(encoding="utf-8"))
            found = _find_beat(sc, beat_id)
            if found:
                _, segment_key = found
        except (OSError, json.JSONDecodeError):
            pass
    if not segment_key:
        intent_raw = (os.environ.get("MN_O3_INTENT_PATH") or "").strip()
        if intent_raw:
            try:
                from o3_generation_intent import load_generation_intent

                intent = load_generation_intent(Path(intent_raw))
                segment_key = str(intent.get("segment_key") or "")
            except Exception:
                pass
    if segment_key:
        event_dir = _event_dir_for_segment(prod_root, segment_key)
    else:
        pin = (os.environ.get("MN_O3_EVENT_DIR") or "").strip()
        event_dir = Path(pin).expanduser().resolve() if pin else prod_root / "Event_1"
    bg.init_bg_paths(event_dir)
    return event_dir


def load_o3_beat_context(beat_id: str) -> tuple[dict, str, Path, Path]:
    """Return (beat, segment_key, sidecar_path, event_dir) after scoped bootstrap."""
    prod_root = _runtime_prod_root()
    event_dir = init_bg_paths_for_o3_subprocess(beat_id=beat_id, prod_root=prod_root)
    sc = bg.read_sidecar()
    found = _find_beat(sc, beat_id)
    if not found:
        raise RuntimeError(f"beat not found after init_bg_paths: {beat_id}")
    beat, segment_key = found
    sidecar_path = Path(bg.BG_SIDECAR_PATH)
    return beat, segment_key, sidecar_path, event_dir


def inject_o3_subprocess_scope_env(env: dict, app: Any) -> None:
    """Mirror HTTP handler scope in O3 subprocess env (milestone SQLite/sidecar authority)."""
    milestone_id = getattr(app, "active_milestone_id", None)
    if getattr(app, "scope_type", "event") == "milestone" and milestone_id:
        mdir = getattr(app, "milestone_dir", None)
        if mdir:
            env["MN_MILESTONE_DIR"] = str(Path(mdir).expanduser().resolve())
        lib = getattr(app, "milestone_library_event_dir", None) or getattr(app, "event_dir", None)
        if lib:
            lib_path = Path(lib).expanduser().resolve()
            env["MN_BG_LIBRARY_EVENT_DIR"] = str(lib_path)
            env["MN_O3_EVENT_DIR"] = str(lib_path)
        try:
            from lib.milestone_store import load_milestone_state, resolve_milestone_skeleton_ref

            skel = resolve_milestone_skeleton_ref(
                load_milestone_state(Path(mdir)) if mdir else {},
                str(milestone_id),
            )
            if skel:
                env["MN_MILESTONE_SKELETON_REF"] = json.dumps(skel)
        except Exception:
            pass
        return

    for key in (
        "MN_MILESTONE_DIR",
        "MN_BG_LIBRARY_EVENT_DIR",
        "MN_MILESTONE_SKELETON_REF",
    ):
        env.pop(key, None)
    ev = getattr(app, "event_dir", None)
    if ev:
        env["MN_O3_EVENT_DIR"] = str(Path(ev).expanduser().resolve())

    # O3 subprocess must write the same per-event SQLite authority as the HTTP handler.
    for key in ("MN_BEATGEN_DB_PATH", "MN_SIDECAR_SQLITE_AUTHORITY"):
        val = (os.environ.get(key) or "").strip()
        if val:
            env[key] = val
