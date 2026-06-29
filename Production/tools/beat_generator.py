#!/usr/bin/env python3
"""
beat_generator.py — Beat extraction from arc skeletons + FLUX Kontext still generation.

Implements the Beat Generator tab backend (HANDOFF_BEAT_GENERATOR_TAB_COMPLETE.md §3-§4).
Imported by production_server.py. Not a standalone script.

Key design (per handoff §0):
- FLUX Kontext stills only (BFL api.bfl.ai). NO Kling. NO motion prompts.
- build_motion_prompt() runs on-demand in Storyboard tab. Not called here.
- Sidecar at Production/beat_generator_state.json, keyed arc+seg, RLock-guarded.
- Fresh SSL per BFL API call (LD-137: ssl.OP_NO_TICKET).
- No kling_prompt field in sidecar schema (Kim correction 2026-04-23).
"""

from __future__ import annotations

from lib.ffmpeg_io import (
    commit_local_file_to_dest as _commit_local_file_to_dest,
    copy_file_durable,
    ffmpeg_failure_transient,
    local_staging_temp_path as _local_staging_temp_path_impl,
    path_is_cloud_storage_backed as _path_is_cloud_storage_backed,
    run_ffmpeg_to_dest,
    sidecar_io_transient,
)
from lib.event_media_cache import ensure_local_media

import concurrent.futures
import contextlib
import copy
import fcntl
import hashlib
import http.client
import io
import json
import os
import re
import ssl
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Paths (LD-505 Phase C — runtime-resolved via init_bg_paths(event_dir))
# ---------------------------------------------------------------------------
#
# These module-level constants are populated at server startup by
# init_bg_paths(event_dir). Before init runs (e.g. unit tests, module
# import in isolation), they fall back to __file__-derived values which
# work for tests using fixtures. The runtime server MUST call init_bg_paths
# in run_server() before serving requests (see production_server.py:run_server).
#
# Pre-Phase-C bug: constants derived from __file__ pointed at the tooling
# tree when CODE was in tooling and DATA was in Dropbox (LD-505), causing
# 8 user-visible features to silently fail (audit C1-1..C1-13).

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROD_DIR = os.path.normpath(os.path.join(_TOOLS_DIR, ".."))
_PROJECT_DIR = os.path.normpath(os.path.join(_TOOLS_DIR, "..", ".."))
_SKELETON_BASE = os.path.join(_PROJECT_DIR, "Arc Skeletons")

BG_SIDECAR_PATH = os.path.join(_PROD_DIR, "beat_generator_state.json")
BG_SIDECAR_MIRROR_PATH = BG_SIDECAR_PATH
BG_STILLS_DIR = os.path.join(_PROD_DIR, "beat_generator_stills")
# Milestone Beat Gen uses an isolated JSON sidecar — never the global SQLite beat store.
_MILESTONE_SIDECAR_JSON_ONLY = False
_MILESTONE_SKELETON_REF: dict | None = None
# Sticky milestone bind — bare init_bg_paths(event_dir) must not tear JSON authority mid-session.
_MILESTONE_SCOPE_BIND: tuple[str, str] | None = None  # (milestone_dir, library_event_dir)
_BG_EVENT_DIR: str | None = None
# BG_SCOPE_ACTIVATION_COLD_BOOT_ONLY_V1 — cold boot runs once per scope key, not per HTTP GET.
_BG_ACTIVE_SCOPE_KEY: str | None = None
# ThreadingHTTPServer + module-level init_bg_paths — serialize path rebinding + sidecar I/O.
_BG_SCOPE_LOCK = threading.RLock()


@contextlib.contextmanager
def bg_scope_lock():
    """Serialize init_bg_paths and sidecar read/write (see milestone_scope.production_bg_scope_lock)."""
    _BG_SCOPE_LOCK.acquire()
    try:
        yield
    finally:
        _BG_SCOPE_LOCK.release()


def _sidecar_use_sqlite() -> bool:
    if _MILESTONE_SIDECAR_JSON_ONLY:
        return False
    # Torn init_bg_paths can leave Milestones/*.json path with SQLite flag — never read global DB.
    path = os.path.abspath(BG_SIDECAR_PATH or "")
    if path and _is_milestone_sidecar_path(path):
        return False
    return sqlite_authority_enabled()


def set_milestone_skeleton_ref(skeleton_ref: dict | None) -> None:
    """Bind skeleton segment identity for milestone sidecar isolation."""
    global _MILESTONE_SKELETON_REF
    _MILESTONE_SKELETON_REF = dict(skeleton_ref) if skeleton_ref else None


def _is_milestone_sidecar_path(path: str) -> bool:
    return "/Milestones/" in path.replace("\\", "/")


def _assert_milestone_sidecar_write_path() -> None:
    if not _MILESTONE_SIDECAR_JSON_ONLY:
        return
    path = os.path.abspath(BG_SIDECAR_PATH)
    if not _is_milestone_sidecar_path(path):
        raise RuntimeError(
            f"milestone Beat Gen sidecar write blocked — path is not under Milestones/: {path}"
        )


def _maybe_isolate_milestone_sidecar(sidecar: dict) -> None:
    if not _MILESTONE_SIDECAR_JSON_ONLY or not _MILESTONE_SKELETON_REF:
        return
    from lib.milestone_store import isolate_milestone_sidecar

    isolate_milestone_sidecar(sidecar, _MILESTONE_SKELETON_REF)


def ensure_milestone_sidecar_isolated(*, persist: bool = True) -> bool:
    """Repair milestone sidecar when global Event segments leaked into Milestones/."""
    if not _MILESTONE_SIDECAR_JSON_ONLY or not _MILESTONE_SKELETON_REF:
        return False
    if not _is_milestone_sidecar_path(os.path.abspath(BG_SIDECAR_PATH)):
        print(
            "[milestone] sidecar isolation skipped — BG_SIDECAR_PATH is not under Milestones/",
            flush=True,
        )
        return False
    from lib.milestone_store import isolate_milestone_sidecar, milestone_sidecar_is_polluted

    sidecar = read_sidecar()
    if not milestone_sidecar_is_polluted(sidecar, _MILESTONE_SKELETON_REF):
        return False
    if persist:
        def _repair(sc: dict) -> None:
            isolate_milestone_sidecar(sc, _MILESTONE_SKELETON_REF)

        mutate_sidecar_locked(_repair)
    else:
        isolate_milestone_sidecar(sidecar, _MILESTONE_SKELETON_REF)
    return True


def milestone_scope_bind() -> tuple[Path, Path] | None:
    """Active milestone (mdir, library_event_dir) when JSON-only scope is bound."""
    raw = _MILESTONE_SCOPE_BIND
    if not raw:
        return None
    return Path(raw[0]).expanduser().resolve(), Path(raw[1]).expanduser().resolve()


def resolve_o3_lifecycle_event_dir_candidates(
    beat_id: str,
    *,
    server_event_dir: str | Path | None = None,
) -> list[Path]:
    """Process-local O3 job/clip dirs — honors sticky milestone bind + migration fallbacks."""
    from o3_generation_intent import resolve_o3_job_event_dir_candidates

    server = (
        Path(server_event_dir).expanduser().resolve()
        if server_event_dir is not None
        else Path(_PROD_DIR) / "Event_1"
    )
    bind = milestone_scope_bind()
    if bind is not None:
        _mdir, library = bind
        return resolve_o3_job_event_dir_candidates(
            beat_id,
            server_event_dir=server,
            library_event_dir=library,
            scope_type="milestone",
        )
    return resolve_o3_job_event_dir_candidates(
        beat_id,
        server_event_dir=server,
        library_event_dir=None,
        scope_type="event",
    )


def _compute_bg_scope_key(
    event_dir,
    *,
    milestone_dir=None,
    library_event_dir=None,
) -> str:
    """Stable id for bound Beat Gen paths — warm init skips cold boot when unchanged."""
    if milestone_dir is not None:
        md = str(Path(milestone_dir).expanduser().resolve())
        lib = str(Path(library_event_dir or event_dir).expanduser().resolve())
        return f"milestone:{md}|lib:{lib}"
    return f"event:{Path(event_dir).expanduser().resolve()}"


def reset_bg_paths_activation_for_tests() -> None:
    """Clear warm-init scope key and restore default tooling prod root between unit tests."""
    global _BG_ACTIVE_SCOPE_KEY, _MILESTONE_SCOPE_BIND, _MILESTONE_SIDECAR_JSON_ONLY, _BG_EVENT_DIR, _PROD_DIR
    _BG_ACTIVE_SCOPE_KEY = None
    _MILESTONE_SCOPE_BIND = None
    _MILESTONE_SIDECAR_JSON_ONLY = False
    _BG_EVENT_DIR = None
    default_event = Path(__file__).resolve().parent.parent / "Event_e2e_fixture"
    if default_event.is_dir():
        _PROD_DIR = str(default_event.parent)
        _BG_EVENT_DIR = str(default_event.resolve())
        try:
            from tools import kling_character_registry as _reg

            _reg.set_prod_root(_PROD_DIR)
        except Exception:
            pass


def init_bg_paths(
    event_dir,
    *,
    milestone_dir=None,
    library_event_dir=None,
    clear_milestone_scope: bool = False,
    cold_boot: bool = False,
) -> None:
    """Rebind every module-level path constant from the runtime event_dir.

    Called by run_server() at startup. Replaces the original PR #73 manual
    override of just BG_STILLS_DIR + BG_SIDECAR_PATH with a complete pass
    over all 11 path constants + the two character-pose dicts (which were
    baked at module-import time).

    Milestone scope: pass ``milestone_dir`` + ``library_event_dir`` for an
    isolated sidecar under ``Milestones/<id>/`` and per-event image library.

    ``clear_milestone_scope=True`` on explicit event/load — drops sticky bind.
    Bare ``init_bg_paths(event_dir)`` while milestone bind is active is redirected
    to preserve JSON-only sidecar authority (orphan recovery class).

    Cold boot (SQLite bootstrap + JSON mirror union) runs once per scope key.
    Repeated HTTP GET scope activation is a warm no-op — see
    TECH_SPEC_BG_SCOPE_ACTIVATION_COLD_BOOT_ONLY_V1.md.

    See Production/lib/paths.py for the canonical resolver and audit
    finding C1-5..C1-9 for the bugs this closes.
    """
    with bg_scope_lock():
        if (
            milestone_dir is None
            and not clear_milestone_scope
            and _MILESTONE_SCOPE_BIND is not None
        ):
            _mdir, _lib = _MILESTONE_SCOPE_BIND
            print(
                f"[beatgen_store] init_bg_paths bare event_dir ignored — "
                f"preserving milestone bind {_mdir}",
                flush=True,
            )
            _init_bg_paths_unlocked(
                _lib,
                milestone_dir=_mdir,
                library_event_dir=_lib,
                cold_boot=cold_boot,
            )
            return
        _init_bg_paths_unlocked(
            event_dir,
            milestone_dir=milestone_dir,
            library_event_dir=library_event_dir,
            clear_milestone_scope=clear_milestone_scope,
            cold_boot=cold_boot,
        )


def _run_bg_paths_cold_boot(event_dir) -> None:
    """SQLite bootstrap + JSON mirror union — startup / scope change only (I8)."""
    if not _MILESTONE_SIDECAR_JSON_ONLY:
        bootstrap_sqlite_sidecar_from_json()
        bootstrap_sqlite_from_legacy_global_db(event_dir)
        if not os.environ.get("MN_BEATGEN_DB_PATH", "").strip():
            print(
                "[beatgen_store] WARN: MN_BEATGEN_DB_PATH unset — legacy global beatgen.db "
                "(cross-event collision risk). Re-run install_production_server_launchagent.sh Event_N.",
                flush=True,
            )
        reconcile_sqlite_segment_beats_from_json_mirror(event_dir)
    _cleanup_stale_dropbox_sidecar_lock_file()
    if _sidecar_use_sqlite():
        store = _beatgen_store()
        print(
            f"[beatgen_store] authority=sqlite db={store.db_path} "
            f"beats={store.beat_count()} integrity={store.integrity_check()} "
            f"mirror={BG_SIDECAR_MIRROR_PATH}",
            flush=True,
        )
    else:
        print(f"[beatgen_store] authority=json path={BG_SIDECAR_PATH}", flush=True)


def _init_bg_paths_unlocked(
    event_dir,
    *,
    milestone_dir=None,
    library_event_dir=None,
    clear_milestone_scope: bool = False,
    cold_boot: bool = False,
) -> None:
    global _TOOLS_DIR, _PROD_DIR, _PROJECT_DIR, _SKELETON_BASE
    global BG_SIDECAR_PATH, BG_STILLS_DIR, BG_SIDECAR_MIRROR_PATH
    global _PROD_CHARS, _CREATURE_REFS, _CREATURE_REFS_BY_EMOTION
    global _CANON_BASE, _LOCAL_STILLS_DIR, _MILESTONE_SIDECAR_JSON_ONLY, _MILESTONE_SKELETON_REF
    global _MILESTONE_SCOPE_BIND, _BG_EVENT_DIR, _BG_ACTIVE_SCOPE_KEY

    # Import here (not at module top) so beat_generator.py can be imported
    # standalone for tests without requiring lib/paths to be on sys.path.
    import sys as _sys
    _lib_parent = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    if _lib_parent not in _sys.path:
        _sys.path.insert(0, _lib_parent)
    from Production.lib.paths import bg_paths as _bg_paths, milestone_bg_paths, character_pose_paths as _cpp, event_sidecar_mirror_path

    if milestone_dir is not None:
        lib = library_event_dir or event_dir
        bp = milestone_bg_paths(milestone_dir, lib)
        pose_root = lib
        _MILESTONE_SIDECAR_JSON_ONLY = True
        _MILESTONE_SCOPE_BIND = (
            str(Path(milestone_dir).expanduser().resolve()),
            str(Path(lib).expanduser().resolve()),
        )
    else:
        bp = _bg_paths(event_dir)
        pose_root = event_dir
        _MILESTONE_SIDECAR_JSON_ONLY = False
        _MILESTONE_SKELETON_REF = None
        if clear_milestone_scope:
            _MILESTONE_SCOPE_BIND = None
    _PROD_DIR = str(bp.prod_root)
    _PROJECT_DIR = str(bp.project_root)
    _SKELETON_BASE = str(bp.skeleton_base)
    BG_SIDECAR_PATH = str(bp.sidecar_path)
    if milestone_dir is not None:
        BG_SIDECAR_MIRROR_PATH = BG_SIDECAR_PATH
    else:
        BG_SIDECAR_MIRROR_PATH = str(event_sidecar_mirror_path(event_dir))
        os.makedirs(os.path.dirname(BG_SIDECAR_MIRROR_PATH), exist_ok=True)
    BG_STILLS_DIR = str(bp.stills_dir)
    _PROD_CHARS = str(bp.project_root)  # poses live at <project_root>/Production/<Char>/poses/
    _CANON_BASE = str(bp.canon_base)
    _LOCAL_STILLS_DIR = Path(bp.local_stills_dir)
    _BG_EVENT_DIR = str(Path(pose_root).expanduser().resolve())

    if _is_milestone_sidecar_path(os.path.abspath(BG_SIDECAR_PATH)):
        _MILESTONE_SIDECAR_JSON_ONLY = True

    scope_key = _compute_bg_scope_key(
        event_dir,
        milestone_dir=milestone_dir,
        library_event_dir=library_event_dir,
    )
    if (
        not cold_boot
        and _BG_ACTIVE_SCOPE_KEY is not None
        and scope_key == _BG_ACTIVE_SCOPE_KEY
    ):
        return

    _BG_ACTIVE_SCOPE_KEY = scope_key
    _run_bg_paths_cold_boot(event_dir)

    try:
        from tools import kling_character_registry as _reg

        _reg.set_prod_root(_PROD_DIR)
    except Exception:
        pass

    # Rebuild the two character-pose dicts that were baked at import time
    # with the (now stale) tooling-anchored _PROD_CHARS. Keys + per-emotion
    # structure preserved exactly per beat_generator.py:127-172.
    _CREATURE_REFS = _cpp(pose_root)

    # _CREATURE_REFS_BY_EMOTION: rebuild with same per-emotion logic as
    # original literal (lines 141-172). All Tessa emotion paths reuse the
    # base creature_ref or a poses/<expr>.png variant; Luna uses single
    # master for every emotion.
    tessa_poses = os.path.join(str(bp.prod_root), "Tessa", "poses")
    luna_master = os.path.join(str(bp.prod_root), "Luna", "Luna v2 Master 4.png")
    _CREATURE_REFS_BY_EMOTION = {
        "Tessa": {
            "default":          os.path.join(tessa_poses, "tessa_neutral.png"),
            "neutral":          os.path.join(tessa_poses, "tessa_neutral.png"),
            "happy_excited":    os.path.join(tessa_poses, "tessa_neutral.png"),  # smiling 3/4
            "sad_disappointed": os.path.join(tessa_poses, "tessa_concerned.png"),
            "concerned":        os.path.join(tessa_poses, "tessa_concerned.png"),
            "upset_shocked":    os.path.join(tessa_poses, "tessa_shocked.png"),
            "shocked":          os.path.join(tessa_poses, "tessa_shocked.png"),
            "scared":           os.path.join(tessa_poses, "tessa_scared.png"),
            "afraid":           os.path.join(tessa_poses, "tessa_scared.png"),
        },
        "Luna": {k: luna_master for k in (
            "default", "neutral", "alert", "happy_excited", "explaining",
            "teaching", "thinking", "curious", "peaceful", "calm",
            "upset_shocked", "shocked", "surprised", "sad_disappointed",
        )},
    }

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Speaker canonicalization (mirrors production_server._SPEAKER_ALIAS subset)
_BG_SPEAKER_ALIAS = {
    "chipper":       "Arlo",
    "guide bird":    "Arlo",
    "pip":           "Arlo",
    "assistant bird": "Arlo",
    "luna":          "Lorelai",
    "tessa":         "Tessa",
    "benson":        "Benson",
    "ember":         "Ember",
    "bork":          "Bork",
    "bramble":       "Bramble",
    "cedric":        "Cedric",
    "myrrhin":       "Cedric",
    "grizzle":       "Grizzle",
    "willow":        "Willow",
    "oliver":        "Oliver",
    "mountain king": "Mountain King",
    "king":          "Mountain King",
    "narrator":      "Narrator",
    "narration":     "Narrator",
}

VALID_EMOTIONS = {"happy_excited", "upset_shocked", "sad_disappointed", "neutral"}

# Outfit/accessory reminders injected into GPT prompts to prevent model from dropping details
# that may not be dominant in every panel of the master reference sheet.
_CREATURE_OUTFIT = {
    # Outfit details injected directly into the character clause so gpt-image-2 treats them
    # as hard constraints, not optional style notes.
    "Luna":    "wearing round wire-frame glasses and a large overstuffed scholar backpack "
               "packed with books, scrolls, and a ruler (visible in ALL panels of the reference)",
    "Lorelai": "raccoon archaeologist with round glasses and overstuffed scholar backpack "
               "(visible in ALL panels of the reference)",
    "Tessa":   "",  # orange shell is the character, no added accessories
    "Benson":  "",
    "Ember":   "",
    "Bork":    "",
    "Bramble": "",
    "Chipper": "",
}

# Per-species description for FLUX still prompts
SPECIES_DESC = {
    "Tessa":   "cartoon turtle with a warm orange shell and gentle eyes, Pixar 3D animated style",
    "Luna":    "cartoon owl with big round scholarly eyes and ruffled feathers, Pixar 3D animated style",
    "Lorelai": "cartoon raccoon scholar with bright eyes, soft fur, and scholarly glasses, Pixar 3D animated style",
    "Benson":  "cartoon bunny with soft grey fur and a kind anxious expression, Pixar 3D animated style",
    "Ember":   "cartoon fox with bright auburn fur and a lively curious expression, Pixar 3D animated style",
    "Bork":    "cartoon firefly with bioluminescent glow and tiny insect wings, Pixar 3D animated style",
    "Bramble": "cartoon bear with mossy brown fur and a gentle giant presence, Pixar 3D animated style",
    "Chipper": "cartoon small colorful bird with bright feathers and an energetic pose, Pixar 3D animated style",
    "Cedric":  "wise old wizard with flowing robes and long white beard, Pixar 3D animated style",
    "Narrator": "magical Everdale forest landscape, no character, cinematic establishing shot",
}

EMOTION_VISUAL = {
    "happy_excited":    "expression bright and joyful, eyes wide, upbeat open energy",
    "upset_shocked":    "expression troubled and worried, brows furrowed, tense closed posture",
    "sad_disappointed": "expression sad and downcast, eyes soft, slightly hunched",
    "neutral":          "expression calm and attentive, natural relaxed posture",
}

_EMOTION_KEYWORDS = {
    "happy_excited": [
        "smile", "grin", "laugh", "happy", "excited", "joy", "wow", "amazing",
        "great", "wonderful", "love it", "cheer", "hooray", "finally",
    ],
    "upset_shocked": [
        "crash", "hurt", "pain", "wrong", "cry", "sob", "shock", "oh no",
        "tears", "upset", "scared", "afraid", "worry", "ow",
    ],
    "sad_disappointed": [
        "sorry", "sad", "clumsy", "should have", "my fault", "disappointed",
        "failed", "can't", "nothing", "hopeless", "sniff",
    ],
}

# Creature reference image paths (for FLUX/GPT identity preservation).
# One canonical pose per character from their poses/ folder.
# Kim can always drag-override per beat via reference_image in the sidecar.
_PROD_CHARS = os.path.normpath(os.path.join(_PROD_DIR, ".."))  # project root
_CREATURE_REFS = {
    # NOTE: Tessa pre-emotion-map default updated 2026-04-27 — was master_tessa_mid-cap-override.png
    # which turned out to be a 1×1 placeholder (LD-431 root-cause discovery). Now points at the
    # real ChatGPT-generated neutral pose. Per-emotion lookup via _CREATURE_REFS_BY_EMOTION below.
    "Tessa":   os.path.join(_PROD_CHARS, "Production", "Tessa",   "poses", "tessa_neutral.png"),
    "Chipper": os.path.join(_PROD_CHARS, "Production", "Chipper", "poses", "chipper_canonical_neutral.png"),
    "Luna":    os.path.join(_PROD_CHARS, "Production", "Luna",    "Luna v2 Master 4.png"),
    "Benson":  os.path.join(_PROD_CHARS, "Production", "Benson",  "poses", "benson_kontext_swap_v1.png"),
    "Ember":   os.path.join(_PROD_CHARS, "Production", "Ember",   "poses", "ember_HERO.png"),
    "Bork":    os.path.join(_PROD_CHARS, "Production", "Bork",    "poses", "bork_pose_neutral.png"),
    "Bramble": os.path.join(_PROD_CHARS, "Production", "Bramble", "poses", "bramble_HERO.png"),
    "Cedric":  os.path.join(_PROD_DIR, "Character_Assets", "MYRRHIN_MASTER_STILL_v1.png"),
}

# Per-emotion creature reference mapping (added 2026-04-27 per LD-431 follow-up).
# Tessa + Luna currently mapped (4 + 7 ChatGPT-generated poses, asset_ids 57-67).
# Other creatures fall through to single-pose _CREATURE_REFS above until pose sheets are produced.
# Resolver: _resolve_creature_ref(speaker, emotion) — picks closest match by emotion field.
_CREATURE_REFS_BY_EMOTION = {
    "Tessa": {
        "default":          os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_neutral.png"),
        "neutral":          os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_neutral.png"),
        "happy_excited":    os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_neutral.png"),  # smiling 3/4
        "sad_disappointed": os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_concerned.png"),
        "concerned":        os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_concerned.png"),
        "upset_shocked":    os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_shocked.png"),
        "shocked":          os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_shocked.png"),
        "scared":           os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_scared.png"),
        "afraid":           os.path.join(_PROD_CHARS, "Production", "Tessa", "poses", "tessa_scared.png"),
    },
    "Luna": {
        # All emotions use Luna v2 Master 4.png — the canonical design sheet with backpack.
        # Individual pose files in poses/ were generated without accessories; v2 master is source of truth.
        # Text-based pose instructions (emotion_body) drive the specific pose; master drives appearance.
        "default":          os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "neutral":          os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "alert":            os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "happy_excited":    os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "explaining":       os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "teaching":         os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "thinking":         os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "curious":          os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "peaceful":         os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "calm":             os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "upset_shocked":    os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "shocked":          os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "surprised":        os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
        "sad_disappointed": os.path.join(_PROD_CHARS, "Production", "Luna", "Luna v2 Master 4.png"),
    },
}


def _resolve_creature_ref(speaker, emotion=None):
    """Pick the best reference image for `speaker` given the beat's `emotion`.

    Lookup chain:
      1. _CREATURE_REFS_BY_EMOTION[speaker][emotion] (exact match)
      2. _CREATURE_REFS_BY_EMOTION[speaker][<keyword fuzzy match>] (scared/shock/happy/sad/etc.)
      3. _CREATURE_REFS_BY_EMOTION[speaker]["default"]
      4. _CREATURE_REFS[speaker] (legacy single-pose fallback for unmapped creatures)

    Returns absolute file path or None if no ref found.
    """
    refs = _CREATURE_REFS_BY_EMOTION.get(speaker)
    if refs:
        # Step 1: exact emotion key match
        if emotion and emotion in refs:
            return refs[emotion]
        # Step 2: keyword fuzzy match on free-form emotion text
        emo_low = (emotion or "").lower()
        if emo_low:
            if any(k in emo_low for k in ("scared", "afraid", "fear", "fright")):
                return refs.get("scared") or refs.get("default")
            if any(k in emo_low for k in ("shock", "shocked", "stun")):
                return refs.get("shocked") or refs.get("upset_shocked") or refs.get("default")
            if any(k in emo_low for k in ("surpris", "gasp", "astonish")):
                return refs.get("surprised") or refs.get("upset_shocked") or refs.get("default")
            if any(k in emo_low for k in ("happy", "smil", "joy", "excit", "cheer")):
                return refs.get("happy_excited") or refs.get("default")
            if any(k in emo_low for k in ("sad", "disappoint", "concern", "worri", "down")):
                return refs.get("sad_disappointed") or refs.get("concerned") or refs.get("default")
            if any(k in emo_low for k in ("explain", "teach", "tell", "say")):
                return refs.get("explaining") or refs.get("default")
            if any(k in emo_low for k in ("think", "ponder", "wonder")):
                return refs.get("thinking") or refs.get("default")
            if any(k in emo_low for k in ("curious", "inquir", "look")):
                return refs.get("curious") or refs.get("default")
            if any(k in emo_low for k in ("peaceful", "calm", "rest", "asleep", "closed")):
                return refs.get("peaceful") or refs.get("default")
        # Step 3: emotion-mapped default
        return refs.get("default")
    # Step 4: legacy single-pose fallback
    return _CREATURE_REFS.get(speaker)

# ---------------------------------------------------------------------------
# LD-431 cost kill switch + fallback telemetry (Phase 0 preflight 168 mitigations)
#
# Counter-4 mitigation: process-level USD budget ceiling. Default $1.00 protects
# integration tests from runaway loops. Set GPT_IMAGE_BUDGET_USD env var to raise
# for full-event/arc regen runs (per Phase 0 synthesis requirement).
#
# Counter-3 mitigation: log every primary→fallback event to prod_activity_log so
# silent degradation cannot hide behind the source_label field.
# ---------------------------------------------------------------------------

_GPT_KILL_CEILING_USD = float(os.environ.get("GPT_IMAGE_BUDGET_USD", "5.00"))
_GPT_RUN_TOTAL_USD = 0.0
_GPT_BUDGET_LOCK = threading.RLock()

_LD431_TASK_ID = "beat_generator_responses_api_wiring_20260427T161726"


class GPTBudgetExceededError(RuntimeError):
    """Raised when projected spend would exceed _GPT_KILL_CEILING_USD.

    Halts the current beat's option loop. Caller should treat this as a
    pipeline-level halt rather than retrying — the ceiling exists precisely
    to stop runaway loops from auto-recharging the OpenAI account.
    """


def _gpt_budget_charge(estimated_cost):
    """Atomically check + increment the process-level USD spend counter.
    Raises GPTBudgetExceededError if estimated_cost would push the running
    total past the ceiling. LD-431 Counter-4 mitigation."""
    global _GPT_RUN_TOTAL_USD
    with _GPT_BUDGET_LOCK:
        projected = _GPT_RUN_TOTAL_USD + estimated_cost
        if projected > _GPT_KILL_CEILING_USD:
            raise GPTBudgetExceededError(
                f"GPT spend ceiling: charging ${estimated_cost:.2f} would push total "
                f"${projected:.2f} over ${_GPT_KILL_CEILING_USD:.2f}. "
                f"Set GPT_IMAGE_BUDGET_USD env var to raise."
            )
        _GPT_RUN_TOTAL_USD = projected


def _gpt_log_fallback_to_directus(beat_id, opt_idx, primary_err, fell_back_to, latency_ms=0):
    """Best-effort log to prod_activity_log on fallback events. Swallows all
    errors silently so a Directus outage does not break the still pipeline.
    LD-431 Counter-3 mitigation."""
    try:
        import sys as _sys
        if _PROJECT_DIR not in _sys.path:
            _sys.path.insert(0, _PROJECT_DIR)
        try:
            from Production.lib.directus_admin_client import DirectusAdminClient  # type: ignore
        except Exception:
            _sys.path.insert(0, os.path.join(_PROJECT_DIR, "Production"))
            from lib.directus_admin_client import DirectusAdminClient  # type: ignore
        c = DirectusAdminClient()
        c.post_item("prod_activity_log", {
            "action": "gpt_responses_api_fallback",
            "details": {
                "beat_id": beat_id,
                "opt_idx": opt_idx,
                "primary_error": (primary_err or "")[:200],
                "fell_back_to": fell_back_to,
                "latency_ms": latency_ms,
                "task_id": _LD431_TASK_ID,
            },
        })
    except Exception as exc:
        print(f"[GPT] (non-fatal) Directus fallback log failed: "
              f"{type(exc).__name__}: {str(exc)[:80]}")


# ---------------------------------------------------------------------------
# Sidecar management
# ---------------------------------------------------------------------------

_sidecar_lock = threading.RLock()

_EMPTY_SIDECAR = lambda: {
    "schema_version": 1,
    "active_context": None,
    "arcs": {},
    "_last_updated": None,
}

# Dropbox/FUSE can return EAGAIN/EDEADLK (errno 11/35) on read/replace during sync.
_SIDECAR_IO_TRANSIENT_ERRNOS = frozenset({11, 35})
_SIDECAR_IO_MAX_ATTEMPTS = 12
_SIDECAR_LOCK_WAIT_LOG_INTERVAL_S = 5.0
SIDECAR_LOCK_DEFAULT_TIMEOUT_S = 45.0
SIDECAR_LOCK_HOLD_WARN_S = 10.0
SIDECAR_LOCK_TIMEOUT_BEAT_PATCH_S = 45.0


def _sidecar_io_backoff_s(attempt: int) -> float:
    return min(4.0, 0.15 * (2 ** attempt))


def _copy_file_chunked(src: str, dst: str, *, chunk_size: int = 1024 * 1024) -> None:
    """Byte copy without macOS fcopyfile — Dropbox errno 11 hits shutil.copy2."""
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            chunk = fin.read(chunk_size)
            if not chunk:
                break
            fout.write(chunk)


def _local_staging_temp_path(*, suffix: str, prefix: str) -> str:
    return str(_local_staging_temp_path_impl(suffix=suffix, prefix=prefix))


def _read_json_file_durable(path: str) -> dict:
    """Read JSON from Dropbox-backed paths without failing on transient errno 11/35.

    Copies to a temp file via chunked read/write (not shutil.copy2 / fcopyfile)
    so we never json.load() a partially-replaced sidecar.
    """
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return _EMPTY_SIDECAR()
    last_err: OSError | None = None
    for attempt in range(_SIDECAR_IO_MAX_ATTEMPTS):
        tmp_path: str | None = None
        try:
            with _sidecar_lock:
                fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="mn_sidecar_read_")
                os.close(fd)
                _copy_file_chunked(path, tmp_path)
                with open(tmp_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except OSError as exc:
            last_err = exc
            if exc.errno not in _SIDECAR_IO_TRANSIENT_ERRNOS or attempt >= _SIDECAR_IO_MAX_ATTEMPTS - 1:
                raise
            time.sleep(_sidecar_io_backoff_s(attempt))
        finally:
            if tmp_path:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
    if last_err:
        raise last_err
    return _EMPTY_SIDECAR()


def sqlite_authority_enabled() -> bool:
    from lib.beatgen_store import sqlite_authority_enabled as _enabled

    return _enabled()


def _beatgen_store():
    from lib.beatgen_store import BeatgenStore

    return BeatgenStore.get()


def _filter_sidecar_dict_for_event(data: dict, event_dir: str | Path) -> dict:
    """Keep only segments belonging to ``Event_N`` when sharding per-event SQLite DBs."""
    evt = normalize_bg_event_id(Path(event_dir).name)
    out = dict(data)
    arcs_out: dict = {}
    for arc_key, arc in (data.get("arcs") or {}).items():
        if not isinstance(arc, dict):
            continue
        segs_out: dict = {}
        for seg_key, seg in (arc.get("segments") or {}).items():
            m = re.match(r"^event_(.+)_(pre|post|full|main)$", str(seg_key))
            if m and m.group(1) == evt:
                segs_out[seg_key] = seg
        if segs_out:
            arcs_out[arc_key] = {"segments": segs_out}
    out["arcs"] = arcs_out
    ctx = dict(data.get("active_context") or {})
    if ctx.get("event_id") not in (evt, f"Event_{evt}"):
        out["active_context"] = {"arc_number": 1, "event_id": evt, "phase": "pre"}
    return out


def _bootstrap_import_is_event_scoped() -> bool:
    scoped = os.environ.get("MN_BEATGEN_DB_PATH", "").strip()
    if not scoped:
        return False
    legacy = Path.home() / ".mindfulnest" / "state" / "beatgen.db"
    return Path(scoped).expanduser().resolve() != legacy.resolve()


def expected_beatgen_db_basename(event_id: str) -> str:
    """LaunchAgent convention: Event_3 → beatgen_event3.db."""
    slug = "".join(str(event_id or "").split("_")).lower()
    return f"beatgen_{slug}.db"


def assert_beatgen_db_path_matches_event(event_id: str) -> None:
    """Dedicated-server guard — refuse startup when SQLite path ≠ served event."""
    db_path = os.environ.get("MN_BEATGEN_DB_PATH", "").strip()
    if not db_path or not str(event_id or "").strip():
        return
    expected = expected_beatgen_db_basename(event_id)
    actual = Path(db_path).expanduser().name
    if actual != expected:
        raise RuntimeError(
            f"[FATAL] MN_BEATGEN_DB_PATH={db_path!r} does not match event_id={event_id!r} "
            f"(expected basename {expected!r}). "
            "Re-run install_production_server_launchagent.sh Event_N."
        )


def bootstrap_sqlite_sidecar_from_json() -> int:
    """One-time import JSON → SQLite when DB empty (migration / first boot)."""
    if os.environ.get("MN_SIDECAR_SQLITE_AUTHORITY", "").strip().lower() in ("0", "false", "no"):
        return 0
    store = _beatgen_store()
    import sqlite3

    try:
        existing = store.beat_count()
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
        print(
            f"[beatgen_store] SQLite unreadable during bootstrap — recovering: {exc}",
            flush=True,
        )
        store.recover_corrupt_database()
        existing = 0
    if existing > 0:
        return existing
    path = os.path.abspath(BG_SIDECAR_PATH)
    if not os.path.isfile(path):
        return 0
    data = _read_json_file_durable(path)
    if _bootstrap_import_is_event_scoped() and _BG_EVENT_DIR:
        data = _filter_sidecar_dict_for_event(data, _BG_EVENT_DIR)
    count = store.import_from_dict(data, replace=True)
    print(
        f"[beatgen_store] bootstrapped SQLite from JSON beats={count} path={store.db_path}",
        flush=True,
    )
    return count


def _schedule_sidecar_mirror_export() -> None:
    if not sqlite_authority_enabled():
        return
    try:
        from lib.sidecar_mirror import schedule_mirror_export

        mirror_path = os.path.abspath(BG_SIDECAR_MIRROR_PATH)
        schedule_mirror_export(
            mirror_path,
            assemble=_beatgen_store().assemble_sidecar_dict,
            write_atomic=lambda d, p=mirror_path: _write_sidecar_json_mirror(d, p),
        )
    except Exception as exc:
        print(f"[beatgen_store] mirror schedule failed: {exc}", flush=True)


def flush_sidecar_mirror_export() -> bool:
    try:
        from lib.sidecar_mirror import flush_mirror_export

        mirror_path = os.path.abspath(BG_SIDECAR_MIRROR_PATH)
        return flush_mirror_export(
            assemble=_beatgen_store().assemble_sidecar_dict,
            write_atomic=lambda d: _write_sidecar_json_mirror(d, mirror_path),
            mirror_path=mirror_path,
        )
    except Exception:
        return False


def _union_segment_dict_for_mirror_export(existing_seg: dict, incoming_seg: dict) -> dict:
    """Monotonic mirror export — never drop beat_ids present in durable mirror file."""
    existing_seg = dict(existing_seg or {})
    incoming_seg = dict(incoming_seg or {})
    out = dict(incoming_seg)
    existing_beats = [
        dict(b) for b in (existing_seg.get("beats") or []) if isinstance(b, dict) and b.get("beat_id")
    ]
    incoming_beats = [
        dict(b) for b in (incoming_seg.get("beats") or []) if isinstance(b, dict) and b.get("beat_id")
    ]
    if not existing_beats:
        out["beats"] = incoming_beats
        return out
    if not incoming_beats:
        out["beats"] = existing_beats
        return out
    sidecar_stub: dict = {"arcs": {"arc_1": {"segments": {"_export": {"beats": incoming_beats}}}}}
    merged_beats = list(incoming_beats)
    live_ids = {str(b.get("beat_id")) for b in merged_beats if b.get("beat_id")}
    for row in existing_beats:
        bid = str(row.get("beat_id") or "")
        if not bid or bid in live_ids:
            continue
        idx = _insert_index_from_preserved_order(merged_beats, existing_beats, bid)
        merged_beats.insert(idx, row)
        live_ids.add(bid)
    out["beats"] = merged_beats
    for key, val in existing_seg.items():
        if key == "beats":
            continue
        if key not in out or out.get(key) in (None, "", {}, []):
            out[key] = val
    return out


def _merge_event_scoped_mirror(data: dict, path: str) -> dict:
    """Per-event SQLite DBs export only one event — merge into global JSON mirror."""
    global_sidecar = os.path.join(_PROD_DIR, "beat_generator_state.json")
    if os.path.abspath(path) != os.path.abspath(global_sidecar):
        # PARALLEL_EVENT_ISOLATION_V1 — local per-event mirror; no Dropbox merge read.
        return data
    if not _bootstrap_import_is_event_scoped() or not _BG_EVENT_DIR:
        return data
    if not os.path.isfile(path):
        return data
    try:
        existing = _read_json_file_durable(path)
    except OSError:
        return data
    evt = normalize_bg_event_id(Path(_BG_EVENT_DIR).name)
    merged = dict(existing)
    merged_arcs = dict(existing.get("arcs") or {})
    for arc_key, arc in (data.get("arcs") or {}).items():
        if not isinstance(arc, dict):
            continue
        dst_arc = dict(merged_arcs.get(arc_key) or {})
        dst_segs = dict(dst_arc.get("segments") or {})
        src_segs = existing.get("arcs", {}).get(arc_key, {}).get("segments") or {}
        for seg_key, seg in (arc.get("segments") or {}).items():
            m = re.match(r"^event_(.+)_(pre|post|full|main)$", str(seg_key))
            if m and m.group(1) == evt:
                dst_segs[seg_key] = _union_segment_dict_for_mirror_export(
                    src_segs.get(seg_key) or {}, seg,
                )
        dst_arc["segments"] = dst_segs
        merged_arcs[arc_key] = dst_arc
    merged["arcs"] = merged_arcs
    if data.get("active_context"):
        merged["active_context"] = data["active_context"]
    return merged


def _write_sidecar_json_mirror(data: dict, path: str) -> None:
    """Dropbox mirror only — never called on SQLite hot write path except export worker."""
    if _is_milestone_sidecar_path(path):
        print(
            f"[beatgen_store] mirror export skipped for milestone sidecar: {path}",
            flush=True,
        )
        return
    data = _merge_event_scoped_mirror(dict(data), path)
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    last_err: OSError | None = None
    for attempt in range(_SIDECAR_IO_MAX_ATTEMPTS):
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=d, delete=False, suffix=".tmp", encoding="utf-8",
            ) as f:
                json.dump(data, f, indent=2)
                tmp = f.name
            os.replace(tmp, path)
            try:
                from lib.production_snapshot import notify_state_write

                notify_state_write(path)
            except Exception:
                pass
            return
        except OSError as exc:
            last_err = exc
            with contextlib.suppress(OSError):
                if "tmp" in locals():
                    os.unlink(tmp)
            if exc.errno not in _SIDECAR_IO_TRANSIENT_ERRNOS or attempt >= _SIDECAR_IO_MAX_ATTEMPTS - 1:
                raise
            time.sleep(_sidecar_io_backoff_s(attempt))
    if last_err:
        raise last_err


def _count_sidecar_beats(data: dict) -> int:
    total = 0
    for arc in (data.get("arcs") or {}).values():
        if not isinstance(arc, dict):
            continue
        for seg in (arc.get("segments") or {}).values():
            if isinstance(seg, dict):
                total += len(seg.get("beats") or [])
    return total


def _assert_sidecar_replace_full_safe(store, incoming: dict) -> None:
    """Block any net beat loss on SQLite replace_full (restore scripts override only)."""
    if os.environ.get("MN_SIDECAR_ALLOW_FULL_REPLACE", "").strip().lower() in ("1", "true", "yes"):
        return
    existing = store.beat_count()
    if existing == 0:
        return
    incoming_count = _count_sidecar_beats(incoming)
    if incoming_count < existing:
        raise RuntimeError(
            f"SQLite sidecar replace_full blocked: would drop beats from {existing} to "
            f"{incoming_count}. Set MN_SIDECAR_ALLOW_FULL_REPLACE=1 to override (restore scripts only)."
        )


def read_sidecar():
    if _sidecar_use_sqlite():
        with bg_scope_lock():
            return _beatgen_store().assemble_sidecar_dict()
    path = os.path.abspath(BG_SIDECAR_PATH)
    return _read_json_file_durable(path)


def write_sidecar(data):
    """Atomic write (os.replace per LD-134). SQLite authority → local DB + mirror export."""
    if _sidecar_use_sqlite():
        with bg_scope_lock():
            _write_sidecar_unlocked(data)
        return
    _write_sidecar_unlocked(data)


def _write_sidecar_unlocked(data):
    _assert_milestone_sidecar_write_path()
    if _sidecar_use_sqlite():
        store = _beatgen_store()
        with _sidecar_lock:
            _assert_sidecar_replace_full_safe(store, data)
            store.replace_full(data)
        _schedule_sidecar_mirror_export()
        return
    path = os.path.abspath(BG_SIDECAR_PATH)
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()
    with _sidecar_lock:
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        last_err: OSError | None = None
        for attempt in range(_SIDECAR_IO_MAX_ATTEMPTS):
            try:
                with tempfile.NamedTemporaryFile(
                    "w", dir=d, delete=False, suffix=".tmp", encoding="utf-8",
                ) as f:
                    json.dump(data, f, indent=2)
                    tmp = f.name
                os.replace(tmp, path)
                try:
                    from lib.production_snapshot import notify_state_write
                    notify_state_write(path)
                except Exception:
                    pass
                return
            except OSError as exc:
                last_err = exc
                with contextlib.suppress(OSError):
                    if "tmp" in locals():
                        os.unlink(tmp)
                if exc.errno not in _SIDECAR_IO_TRANSIENT_ERRNOS or attempt >= _SIDECAR_IO_MAX_ATTEMPTS - 1:
                    raise
                time.sleep(_sidecar_io_backoff_s(attempt))
        if last_err:
            raise last_err


def _cleanup_stale_dropbox_sidecar_lock_file() -> None:
    """Remove legacy flock file after SQLite cutover — it must not block operators."""
    lock_path = os.path.abspath(BG_SIDECAR_PATH) + ".lock"
    if not os.path.isfile(lock_path):
        return
    try:
        os.unlink(lock_path)
        print(f"[beatgen_store] removed stale Dropbox sidecar lock {lock_path}", flush=True)
    except OSError as exc:
        print(f"[beatgen_store] stale lock cleanup skipped: {exc}", flush=True)


@contextlib.contextmanager
def _legacy_json_sidecar_file_lock(*, timeout_s: float):
    """Dropbox flock — rollback path only (MN_SIDECAR_SQLITE_AUTHORITY=0)."""
    import errno

    path = os.path.abspath(BG_SIDECAR_PATH)
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    acquired_at: float | None = None
    with open(lock_path, "a+", encoding="utf-8") as lock_fh:
        fd = lock_fh.fileno()
        deadline = time.monotonic() + float(timeout_s)
        last_log = 0.0
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"sidecar lock timeout after {timeout_s}s ({lock_path})"
                    ) from exc
                now = time.monotonic()
                if now - last_log >= _SIDECAR_LOCK_WAIT_LOG_INTERVAL_S:
                    print(
                        f"[sidecar_lock] waiting for {lock_path} "
                        f"(>{int(now - (deadline - timeout_s))}s)",
                        flush=True,
                    )
                    last_log = now
                time.sleep(0.05)
        acquired_at = time.monotonic()
        try:
            yield
        finally:
            if acquired_at is not None:
                held_s = time.monotonic() - acquired_at
                if held_s >= SIDECAR_LOCK_HOLD_WARN_S:
                    print(
                        f"[sidecar_lock] held {lock_path} for {held_s:.1f}s",
                        flush=True,
                    )
            fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def sidecar_file_lock(*, timeout_s: float | None = None):
    """Cross-process lock for Beat Gen sidecar read/modify/write cycles.

    ``_sidecar_lock`` protects threads inside one Python process only. O3 voice
    subprocesses and the storyboard server must coordinate on the same lock file,
    otherwise whole-file writes can erase fields from a concurrent beat job.

    When ``timeout_s`` is set, waits up to that many seconds instead of blocking
    forever — O3 delivery checkpoint must not stall behind a long session-state GET.

    Default acquire timeout is ``SIDECAR_LOCK_DEFAULT_TIMEOUT_S`` so one handler
    cannot block O3 subprocess checkpoints indefinitely.

    With SQLite authority, uses in-process ``_sidecar_lock`` only (no Dropbox flock).
    """
    if sqlite_authority_enabled():
        acquired_at: float | None = None
        with _sidecar_lock:
            acquired_at = time.monotonic()
            try:
                yield
            finally:
                if acquired_at is not None:
                    held_s = time.monotonic() - acquired_at
                    if held_s >= SIDECAR_LOCK_HOLD_WARN_S:
                        print(
                            f"[sidecar_lock] held sqlite session for {held_s:.1f}s",
                            flush=True,
                        )
        return
    if timeout_s is None:
        timeout_s = SIDECAR_LOCK_DEFAULT_TIMEOUT_S
    with _legacy_json_sidecar_file_lock(timeout_s=timeout_s):
        yield


def read_sidecar_locked():
    with sidecar_file_lock():
        return read_sidecar()


def read_sidecar_for_poll_snapshot(*, lock_timeout_s: float = 5.0) -> dict:
    """Read sidecar for O3 poll UI patches — locked when possible, else best-effort.

    Poll runs every 3s per active job; with JSON authority concurrent subprocess
    checkpoints and session-state GET can hold the lock file 30–120s. With SQLite
    authority this is a fast local read.
    """
    if _sidecar_use_sqlite():
        return read_sidecar()
    try:
        with sidecar_file_lock(timeout_s=lock_timeout_s):
            return read_sidecar()
    except TimeoutError:
        print(
            f"[sidecar] poll snapshot: lock timeout after {lock_timeout_s}s — "
            "best-effort unlocked read",
            flush=True,
        )
        path = os.path.abspath(BG_SIDECAR_PATH)
        return _read_json_file_durable(path)


def write_sidecar_atomic_locked(data):
    with sidecar_file_lock():
        write_sidecar(data)


def mutate_sidecar_locked(
    mutator: Callable[[dict], Any],
    *,
    timeout_s: float | None = None,
    migrate: bool = False,
    scope=None,
    caller: str = "mutate_sidecar_locked",
) -> dict:
    """Atomic read-modify-write for multi-beat / segment sidecar edits.

    Prefer ``update_beat_locked`` for single-beat patches (cheaper SQLite path).
    Truth Stack Layer 1: optional ``scope`` binds partition authority for logging.
    """
    from beatgen_scope import log_beatgen_mutation, scope_from_current_globals  # noqa: PLC0415

    active_scope = scope if scope is not None else scope_from_current_globals(__import__(__name__))
    log_beatgen_mutation(
        operation="mutate_sidecar_locked",
        beat_id="",
        scope=active_scope,
        caller=caller,
    )
    with sidecar_file_lock(timeout_s=timeout_s):
        sidecar = read_sidecar()
        if migrate:
            sidecar = _migrate_sidecar(sidecar)
        _maybe_isolate_milestone_sidecar(sidecar)
        mutator(sidecar)
        write_sidecar(sidecar)
        return sidecar


def delete_beat_locked(
    beat_id: str,
    *,
    scope=None,
    caller: str = "delete_beat_locked",
    migrate: bool = False,
) -> bool:
    """Atomically remove one beat — targeted SQLite DELETE, not replace_full.

    JSON mirror path uses mutate_sidecar_locked (no replace_full guard).
    """
    from beatgen_scope import (  # noqa: PLC0415
        assert_beat_id_matches_scope,
        assert_db_path_matches_beat,
        assert_direct_write_allowed,
        event_id_from_beat_id,
        log_beatgen_mutation,
        scope_from_current_globals,
    )

    active_scope = scope if scope is not None else scope_from_current_globals(__import__(__name__))
    if event_id_from_beat_id(str(beat_id)):
        assert_beat_id_matches_scope(str(beat_id), active_scope)
        assert_db_path_matches_beat(str(beat_id))
    assert_direct_write_allowed(beat_id=str(beat_id), caller=caller)
    log_beatgen_mutation(
        operation="delete_beat_locked",
        beat_id=str(beat_id),
        scope=active_scope,
        caller=caller,
    )
    if _sidecar_use_sqlite():
        with _sidecar_lock:
            ok = _beatgen_store().delete_beat(beat_id)
        if ok:
            _schedule_sidecar_mirror_export()
        return ok

    def _delete(sidecar: dict) -> None:
        for arc in sidecar.get("arcs", {}).values():
            for seg in arc.get("segments", {}).values():
                seg["beats"] = [
                    b for b in seg.get("beats", []) if b.get("beat_id") != beat_id
                ]

    with sidecar_file_lock():
        sidecar = read_sidecar()
        if migrate:
            sidecar = _migrate_sidecar(sidecar)
        _maybe_isolate_milestone_sidecar(sidecar)
        before = _count_sidecar_beats(sidecar)
        _delete(sidecar)
        if _count_sidecar_beats(sidecar) >= before:
            return False
        write_sidecar(sidecar)
    return True


def update_beat_locked(
    beat_id,
    mutator,
    expected_attempt_id=None,
    *,
    scope=None,
    caller: str = "update_beat_locked",
    skip_single_writer_gate: bool = False,
):
    """Atomically patch one beat under the cross-process sidecar lock.

    ``mutator(beat, sidecar)`` may mutate the target beat in place. If
    ``expected_attempt_id`` is set and the current beat has a different
    ``kling_o3_voice_fix_attempt_id``, the update is skipped and ``(False, beat)``
    is returned so stale subprocesses cannot overwrite newer attempts.

    Truth Stack: optional ``scope`` validates partition; production beats require
    server writer unless ``skip_single_writer_gate`` (internal subprocess paths).
    """
    from beatgen_scope import (  # noqa: PLC0415
        assert_beat_id_matches_scope,
        assert_db_path_matches_beat,
        assert_direct_write_allowed,
        event_id_from_beat_id,
        log_beatgen_mutation,
        scope_from_current_globals,
    )

    active_scope = scope if scope is not None else scope_from_current_globals(__import__(__name__))
    if event_id_from_beat_id(str(beat_id)):
        assert_beat_id_matches_scope(str(beat_id), active_scope)
        assert_db_path_matches_beat(str(beat_id))
    if not skip_single_writer_gate:
        assert_direct_write_allowed(beat_id=str(beat_id), caller=caller)
    log_beatgen_mutation(
        operation="update_beat_locked",
        beat_id=str(beat_id),
        scope=active_scope,
        caller=caller,
    )
    if _sidecar_use_sqlite():
        with _sidecar_lock:
            ok, beat = _beatgen_store().patch_beat(
                beat_id,
                mutator,
                expected_attempt_id=expected_attempt_id,
            )
        if ok:
            _schedule_sidecar_mirror_export()
        return ok, beat
    last_err: OSError | None = None
    lock_timeout_s = 120.0
    for attempt in range(_SIDECAR_IO_MAX_ATTEMPTS):
        try:
            with sidecar_file_lock(timeout_s=lock_timeout_s):
                sidecar = read_sidecar()
                _seg, beat = find_beat(sidecar, beat_id)
                if not beat:
                    return False, None
                if expected_attempt_id is not None and beat.get("kling_o3_voice_fix_attempt_id") != expected_attempt_id:
                    return False, beat
                mutator(beat, sidecar)
                write_sidecar(sidecar)
                return True, beat
        except OSError as exc:
            last_err = exc
            if not sidecar_io_transient(exc) or attempt >= _SIDECAR_IO_MAX_ATTEMPTS - 1:
                raise
            time.sleep(_sidecar_io_backoff_s(attempt))
    if last_err:
        raise last_err
    return False, None


def normalize_bg_event_id(event_id: str) -> str:
    """Strip storyboard-scope prefix from event_id so it matches sidecar segment keys.

    The storyboard passes scope as "Event_1" (from activeScope.value.event_id) while
    the BG sidecar stores segments under keys like "event_1_post" (numeric id only).
    This mismatch caused get_seg_entry to create ghost key "event_Event_1_post" instead
    of looking up the real "event_1_post" segment.

    Examples:
        normalize_bg_event_id("Event_1")  -> "1"
        normalize_bg_event_id("event_2")  -> "2"
        normalize_bg_event_id("1")        -> "1"
    """
    import re as _re
    return _re.sub(r'^event_', '', str(event_id), flags=_re.IGNORECASE)


def get_seg_entry(sidecar, arc_number, event_id, phase="full"):
    """Return (and create if missing) the segment dict for arc_N/event_{id}_{phase}."""
    arc_key = f"arc_{arc_number}"
    seg_key = f"event_{event_id}_{phase}"
    return (sidecar.setdefault("arcs", {})
                   .setdefault(arc_key, {"segments": {}})
                   .setdefault("segments", {})
                   .setdefault(seg_key, {"name": "", "beats": []}))


def find_beat(sidecar, beat_id):
    """Return (seg_dict, beat_dict) or (None, None)."""
    for arc in sidecar.get("arcs", {}).values():
        for seg in arc.get("segments", {}).values():
            for beat in seg.get("beats", []):
                if beat.get("beat_id") == beat_id:
                    return seg, beat
    return None, None


def segment_phase_for_beat(sidecar, beat_id: str) -> str | None:
    """Return BG segment phase (e.g. ``post``, ``pre``) for a beat_id, or None."""
    for arc in (sidecar.get("arcs") or {}).values():
        for seg_key, seg in (arc.get("segments") or {}).items():
            for beat in seg.get("beats") or []:
                if beat.get("beat_id") == beat_id:
                    m = re.match(r"^event_\d+_(.+)$", seg_key)
                    return m.group(1) if m else None
    return None


def segment_key_for_beat(sidecar, beat_id: str) -> str | None:
    """Return BG segment dict key (e.g. ``event_2_pre``) for a beat_id."""
    for arc in (sidecar.get("arcs") or {}).values():
        for seg_key, seg in (arc.get("segments") or {}).items():
            for beat in seg.get("beats") or []:
                if beat.get("beat_id") == beat_id:
                    return seg_key
    return None


def beat_has_spoken_dialogue(beat: dict) -> bool:
    """True when beat carries operator dialogue for voice-first Generate."""
    if (beat.get("dialogue_text") or "").strip():
        return True
    spoken = extract_spoken_dialogue_from_kling_prompt(beat.get("kling_o3_prompt") or "")
    return bool((spoken or "").strip())


def beatgen_avatar_pro_disabled(env: dict | None = None) -> bool:
    """True when Beat Gen must not route Generate to Avatar Pro (Omni restore pin)."""
    import os

    env = env or os.environ
    if (env.get("MN_BEATGEN_AVATAR_ALLOWED") or "").strip() == "1":
        return False
    if (env.get("MN_BEATGEN_AVATAR_DISABLED") or "").strip() == "1":
        return True
    forced = (env.get("MN_O3_GENERATE_MODE") or "").strip().lower()
    if forced in (O3_GENERATE_MODE_ELEMENT_NATIVE, O3_GENERATE_MODE_VOICE_FIRST):
        return True
    return True


def resolve_o3_generate_mode(
    beat: dict,
    sidecar: dict,
    *,
    env: dict | None = None,
) -> str:
    """Route O3 Generate subprocess: ``element_native`` (default), ``voice_first``, or ``avatar_pro``."""
    import os

    env = env or os.environ
    forced = (env.get("MN_O3_GENERATE_MODE") or "").strip().lower()
    if forced in O3_SPEAK_GENERATE_MODES:
        mode = forced
    else:
        mode = ""
        bid = str(beat.get("beat_id") or "")
        seg_key = segment_key_for_beat(sidecar, bid)
        if seg_key:
            for arc in (sidecar.get("arcs") or {}).values():
                seg = (arc.get("segments") or {}).get(seg_key) or {}
                seg_mode = (seg.get("o3_generate_mode") or "").strip().lower()
                if seg_mode in O3_SPEAK_GENERATE_MODES:
                    mode = seg_mode
                    break

        if not mode:
            beat_mode = (beat.get("o3_generate_mode") or "").strip().lower()
            if beat_mode in O3_SPEAK_GENERATE_MODES:
                mode = beat_mode

        if not mode:
            if beat_has_spoken_dialogue(beat):
                mode = O3_GENERATE_MODE_ELEMENT_NATIVE
            else:
                mode = O3_GENERATE_MODE_ELEMENT_NATIVE

    if mode == O3_GENERATE_MODE_AVATAR and beatgen_avatar_pro_disabled(env):
        return O3_GENERATE_MODE_ELEMENT_NATIVE
    return mode


def element_char_ref_required_for_beat(beat: dict, sidecar: dict | None = None) -> bool:
    """Element pose registration gate — element_native + voice_first only, not Avatar Pro."""
    if beat_is_still_insert(beat):
        return False
    sc = sidecar
    if sc is None:
        try:
            sc = read_sidecar()
        except Exception:
            sc = {}
    mode = resolve_o3_generate_mode(beat, sc)
    return mode in (O3_GENERATE_MODE_ELEMENT_NATIVE, O3_GENERATE_MODE_VOICE_FIRST)


def o3_bg_ref_required_for_beat(beat: dict, sidecar: dict | None = None) -> bool:
    """BG ref slot required for silent O3 (char+bg composite) — not Avatar Pro portrait still."""
    return element_char_ref_required_for_beat(beat, sidecar)


_CANONICAL_LEAD_BEAT_MARKERS = ("_o3_canonical",)


def is_canonical_lead_beat(beat_id: str) -> bool:
    """Validation / orphan beats that must lead the segment (e.g. Tessa O3 canonical)."""
    bid = (beat_id or "").strip()
    return any(marker in bid for marker in _CANONICAL_LEAD_BEAT_MARKERS)


def segment_beat_order_key(beat: dict) -> tuple:
    """Stable segment order: canonical leads → numbered beats → other orphans.

    Sorting by ``beat_id`` string alone is unsafe — ``…_beat_13`` sorts before
    ``…_tessa_o3_canonical``, which silently demotes validation beats to the end.
    """
    bid = (beat.get("beat_id") or "").strip()
    if is_canonical_lead_beat(bid):
        return (0, 0, bid)
    m = re.search(r"_beat_(\d+)$", bid)
    if m:
        return (1, int(m.group(1)), bid)
    return (2, 0, bid)


def normalize_segment_beat_order(beats: list[dict]) -> list[dict]:
    """Return beats in canonical segment order without dropping any rows."""
    if not beats:
        return []
    return sorted(beats, key=segment_beat_order_key)


# ---------------------------------------------------------------------------
# Intro canonical tail beats (Suggest beats, phase=pre only)
# ---------------------------------------------------------------------------

INTRO_BEAT_ROLE_SEMI_CANONICAL = "semi_canonical_transition_prompt"
INTRO_BEAT_ROLE_CANONICAL_MIRROR = "canonical_mirror_video"
INTRO_DIALOGUE_PLACEHOLDER = "ENTER TEXT HERE"
# ~22 spoken words — local estimate fits 12s bucket without cramming (beat 24 class).
ARLO_SEMI_CANONICAL_COMPACT_DIALOGUE = (
    "OK, Kiddo. Lorelai's our best chance. She knows the MindfulNest! "
    "But she's stressed. Let's see if the Wizard can teach you a calming spell."
)

# Sidecar merge + stitch export durability (LD Kling O3 trim persist).
# Trims saved via Apply Trim MUST survive re-extract/import and MUST be applied
# on Send to Stitcher via _kling_o3_export_clip_path → materialize_kling_o3_trimmed_clip.
SIDECAR_MERGE_PRESERVE_FIELDS: tuple[str, ...] = (
    "flux_options", "accepted_image_key", "accepted_library_ref", "status",
    "kling_o3_prompt", "kling_o3_prompt_still", "kling_o3_duration", "kling_o3_duration_locked",
    "kling_o3_status", "kling_o3_video_path", "kling_o3_generation",
    "kling_o3_options", "kling_o3_replace_slot_index", "kling_o3_selected_option_key",
    "kling_o3_still_stitch_approved", "kling_o3_still_stitch_approved_at",
    "kling_o3_task_id", "kling_o3_trim_start", "kling_o3_trim_back",
    "kling_o3_cut_start_s", "kling_o3_cut_end_s",
    "kling_o3_baked_path", "kling_o3_baked_token",
    "kling_o3_actual_duration_s", "kling_o3_completed_at",
    "reference_image", "bg_ref_image", "reference_image_locked",
    "bg_ref_image_locked", "start_frame_image_locked", "end_frame_image_locked",
    "element_char_ref_ok", "element_char_ref_error",
    "o3_prompt_box_law", "o3_prompt_box_law_at",
    "pipeline",
    "o3_generate_mode",
    "kling_o3_selection_pipeline_mismatch",
    "kling_o3_active_clip_pipeline",
    "intro_beat_role", "canonical_intro_tail",
    "magic_manual_path", "magic_video_path", "magic_path_authored_against",
    "storyboard_clip_import",
    "start_frame_image", "end_frame_image", "kling_o3_mode",
    "magic_still_path",
    "directus_asset_id",
    "directus_registered_at",
    "directus_export_clip_path",
    "audio_file",
    "still_tts_source_text",
    "kling_o3_voice_fix_ui_job_id",
    "kling_o3_voice_fix_job_log_path",
    "kling_o3_voice_fix_phase",
    "kling_o3_voice_fix_job_pid",
    "kling_o3_voice_fix_job_started_at",
    "o3_active_intent_id",
    "o3_active_intent_job_id",
    "o3_current_job_id",
    "kling_o3_disk_delivery_count",
    "kling_o3_element_delivery_count",
    "kling_o3_orphan_delivery_count",
    "kling_o3_clips_dir",
    "kling_o3_pinned_preserve",
    "kling_o3_disk_enrich_at",
)

# Prefix union — new o3_* / kling_o3_* sidecar fields survive merge without tuple edits.
_SIDECAR_MERGE_PRESERVE_PREFIXES: tuple[str, ...] = ("kling_o3_", "o3_")


def sidecar_merge_preserve_fields(existing_beat: dict | None = None) -> tuple[str, ...]:
    """Explicit preserve tuple + dynamic prefix keys from an existing beat row."""
    fields = set(SIDECAR_MERGE_PRESERVE_FIELDS)
    if existing_beat:
        for key in existing_beat:
            if any(str(key).startswith(p) for p in _SIDECAR_MERGE_PRESERVE_PREFIXES):
                fields.add(str(key))
    return tuple(fields)


# Extract-beats /approve must replace draft Kling prompts — not preserve stale sidecar text.
_EXTRACT_APPROVE_MERGE_PRESERVE: tuple[str, ...] = tuple(
    f for f in SIDECAR_MERGE_PRESERVE_FIELDS
    if f not in (
        "kling_o3_prompt",
        "kling_o3_duration",
        "kling_o3_duration_locked",
        "kling_o3_status",
        "pipeline",
    )
)

# Extract approve: restore approved clip/media only — never clobber fresh author text.
_KLING_APPROVED_RESTORE_FIELDS: tuple[str, ...] = (
    "kling_o3_status",
    "kling_o3_video_path",
    "kling_o3_generation",
    "kling_o3_options",
    "kling_o3_replace_slot_index",
    "kling_o3_selected_option_key",
    "kling_o3_task_id",
    "kling_o3_trim_start",
    "kling_o3_trim_back",
    "kling_o3_actual_duration_s",
    "kling_o3_completed_at",
    "accepted_library_ref",
    "accepted_image_key",
    "audio_file",
)

_TELEPORT_INTRO_MANIFEST_REL = "Production/templates/chipper_teleport_intro/manifest.json"
# Tooling tree copy — survives init_bg_paths() pointing _PROD_DIR at Dropbox.
_TOOLING_TELEPORT_INTRO_MANIFEST = (
    Path(__file__).resolve().parent.parent / "templates" / "chipper_teleport_intro" / "manifest.json"
)
_TOOLING_ARLO_TELEPORT_INTRO_MANIFEST = (
    Path(__file__).resolve().parent.parent / "templates" / "arlo_teleport_intro" / "manifest.json"
)


def _infer_teleport_intro_guide(
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> str | None:
    """Detect guide character for intro manifest (Arlo vs Chipper)."""
    try:
        from teleport_intro_canonical import (
            default_guide_for_project,
            infer_guide_from_sidecar_segment,
        )
        from lib.paths import dropbox_root

        guide = infer_guide_from_sidecar_segment(sidecar, segment_key)
        if guide:
            return guide
        return default_guide_for_project(dropbox_root())
    except Exception:
        return None


def _teleport_intro_manifest_path(
    *,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> Path:
    if not guide:
        guide = _infer_teleport_intro_guide(sidecar, segment_key)
    env = os.environ.get("TELEPORT_INTRO_MANIFEST")
    if env:
        return Path(env)
    try:
        from teleport_intro_canonical import active_manifest_path
        from lib.paths import dropbox_root

        active = active_manifest_path(dropbox_root(), guide=guide)
        if active.is_file():
            return active
    except Exception:
        pass
    arlo_manifest = _TOOLING_ARLO_TELEPORT_INTRO_MANIFEST
    if (guide or "").strip().lower() == "arlo" and arlo_manifest.is_file():
        return arlo_manifest
    candidates = [
        _project_root() / _TELEPORT_INTRO_MANIFEST_REL,
        Path(_PROD_DIR) / "templates" / "chipper_teleport_intro" / "manifest.json",
        Path(_PROD_DIR) / "templates" / "arlo_teleport_intro" / "manifest.json",
        _TOOLING_TELEPORT_INTRO_MANIFEST,
        arlo_manifest,
    ]
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.is_file() else str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    for candidate in unique:
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(data.get("intro_canonical_beats"), dict):
                return candidate
        except (OSError, json.JSONDecodeError):
            continue
    for candidate in unique:
        if candidate.is_file():
            return candidate
    return unique[0] if unique else Path(_PROD_DIR) / "templates" / "chipper_teleport_intro" / "manifest.json"


def _load_intro_canonical_beats_manifest(
    *,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> dict[str, Any]:
    path = _teleport_intro_manifest_path(guide=guide, sidecar=sidecar, segment_key=segment_key)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    block = data.get("intro_canonical_beats")
    return block if isinstance(block, dict) else {}


INTRO_DEFAULT_PRE_PENULTIMATE_PAIR_FADE_MS = 1500
INTRO_DEFAULT_FINAL_PAIR_FADE_MS = 2800
INTRO_DEFAULT_FADE_OUT_VIDEO_TAIL_MS = 600
INTRO_DEFAULT_FADE_IN_VIDEO_HEAD_MS = 600
INTRO_DEFAULT_CANONICAL_TAIL_EXPORT_TRIM_BACK_S = 0.0
INTRO_PAIR_FADE_MS_MAX = 4000

# Beat Gen magic-on-still stitch export: play the full magic_still clip (no head/tail
# trim to speech). Inter-beat joins are hard cuts at clip boundaries — no artificial
# freeze_tail dead air between beats (that was the old 2.5s pause problem).
MAGIC_STILL_STITCH_EXPORT_FREEZE_TAIL_S = 0.0
MAGIC_STILL_TTS_EXPORT_RECIPE = "full_still_v1"
STILL_INSERT_DEFAULT_DURATION_S = 4.0
STILL_INSERT_AUDIO_TAIL_PAD_S = 0.25
STILL_INSERT_MIN_DURATION_S = 1.0
INTRO_VISUAL_FADE_MS_MAX = 1200


def _load_intro_pair_fade_ms(
    block_key: str,
    *,
    default_ms: int,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> int:
    """Load one intro export crossfade duration (ms) from teleport intro manifest."""
    path = _teleport_intro_manifest_path(guide=guide, sidecar=sidecar, segment_key=segment_key)
    if not path.is_file():
        return default_ms
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_ms
    block = data.get("intro_canonical_beats") or {}
    legacy = {"final_pair_fade_ms": data.get("intro_final_pair_fade_ms")}
    raw = block.get(block_key, legacy.get(block_key))
    if raw is None:
        return default_ms
    try:
        return max(0, min(INTRO_PAIR_FADE_MS_MAX, int(raw)))
    except (TypeError, ValueError):
        return default_ms


def _load_intro_pre_penultimate_pair_fade_ms() -> int:
    """Crossfade (ms) from 3rd-to-last intro beat into penultimate (Transition to Spell)."""
    return _load_intro_pair_fade_ms(
        "pre_penultimate_pair_fade_ms",
        default_ms=INTRO_DEFAULT_PRE_PENULTIMATE_PAIR_FADE_MS,
    )


def _load_intro_final_pair_fade_ms() -> int:
    """Crossfade duration (ms) between penultimate intro beat and canonical mirror tail."""
    return _load_intro_pair_fade_ms(
        "final_pair_fade_ms",
        default_ms=INTRO_DEFAULT_FINAL_PAIR_FADE_MS,
    )


def _load_intro_visual_fade_ms(
    block_key: str,
    *,
    default_ms: int,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> int:
    """Short video-only fade tail/head (ms) — dialogue stays fully visible until ~last word."""
    path = _teleport_intro_manifest_path(guide=guide, sidecar=sidecar, segment_key=segment_key)
    if not path.is_file():
        return default_ms
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_ms
    block = data.get("intro_canonical_beats") or {}
    raw = block.get(block_key)
    if raw is None:
        return default_ms
    try:
        return max(100, min(INTRO_VISUAL_FADE_MS_MAX, int(raw)))
    except (TypeError, ValueError):
        return default_ms


def _load_intro_fade_out_video_tail_ms() -> int:
    return _load_intro_visual_fade_ms(
        "fade_out_video_tail_ms",
        default_ms=INTRO_DEFAULT_FADE_OUT_VIDEO_TAIL_MS,
    )


def _load_intro_fade_in_video_head_ms() -> int:
    return _load_intro_visual_fade_ms(
        "fade_in_video_head_ms",
        default_ms=INTRO_DEFAULT_FADE_IN_VIDEO_HEAD_MS,
    )


def _load_intro_canonical_tail_export_trim_back_s(
    *,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> float:
    """Trailing seconds to trim from composed intro_tail on stitch export (whiteout hold)."""
    block = _load_intro_canonical_beats_manifest(
        guide=guide, sidecar=sidecar, segment_key=segment_key,
    )
    raw = block.get("canonical_tail_export_trim_back_s")
    if raw is None:
        return INTRO_DEFAULT_CANONICAL_TAIL_EXPORT_TRIM_BACK_S
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return INTRO_DEFAULT_CANONICAL_TAIL_EXPORT_TRIM_BACK_S
    return max(0.0, val)


def seed_canonical_intro_tail_export_trim(
    beat: dict,
    *,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> bool:
    """Seed export trim_back on canonical mirror row when operator has not set one."""
    if beat.get("intro_beat_role") != INTRO_BEAT_ROLE_CANONICAL_MIRROR:
        return False
    if not beat.get("canonical_intro_tail") and not _has_populated_intro_mirror_beat(beat):
        return False
    default_back = _load_intro_canonical_tail_export_trim_back_s(
        guide=guide, sidecar=sidecar, segment_key=segment_key,
    )
    back = beat.get("kling_o3_trim_back")
    if default_back <= 0.05:
        # Hold is baked into intro_tail.mp4 — drop legacy export trim metadata.
        if back is not None and float(back) > 0.05:
            beat.pop("kling_o3_trim_back", None)
            beat.pop("kling_o3_trim_end", None)
            return True
        return False
    if back is not None and float(back) > 0.05:
        return False
    beat.setdefault("kling_o3_trim_start", 0.0)
    beat["kling_o3_trim_back"] = round(default_back, 2)
    beat.pop("kling_o3_trim_end", None)
    return True


def _intro_visual_fade_out_s(pair_fade_ms: int) -> float:
    """Outgoing clip: quick video fade at tail only (audio stays full until hard cut)."""
    if pair_fade_ms <= 0:
        return 0.0
    tail_ms = min(_load_intro_fade_out_video_tail_ms(), pair_fade_ms)
    return tail_ms / 1000.0


def _intro_visual_fade_in_s(pair_fade_ms: int) -> float:
    """Incoming clip: quick video fade from black at head (audio full from cut)."""
    if pair_fade_ms <= 0:
        return 0.0
    head_ms = min(_load_intro_fade_in_video_head_ms(), pair_fade_ms)
    return head_ms / 1000.0


def _resolve_intro_manifest_asset(
    asset_key: str,
    *,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> dict | None:
    if not asset_key:
        return None
    try:
        manifest_path = _teleport_intro_manifest_path(
            guide=guide, sidecar=sidecar, segment_key=segment_key,
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rel = (manifest.get("assets") or {}).get(asset_key)
    if not rel:
        return None
    for root in (_project_root(), Path(_PROD_DIR).parent, Path(_PROD_DIR)):
        candidate = root / rel
        if candidate.is_file():
            return _ref_dict_from_path(str(candidate.resolve()))
    return None


def build_intro_semi_canonical_transition_prompt(
    dialogue_var: str | None = None,
    *,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> str:
    """Fixed Kling prompt shell for penultimate intro beat; dialogue slot is per-event."""
    cfg = _load_intro_canonical_beats_manifest(
        guide=guide, sidecar=sidecar, segment_key=segment_key,
    ).get("semi_canonical_transition") or {}
    template = (cfg.get("prompt_template") or "").strip()
    if not template:
        return ""
    placeholder = cfg.get("dialogue_placeholder") or INTRO_DIALOGUE_PLACEHOLDER
    var = (dialogue_var or "").strip()
    if not var or var == placeholder:
        return template
    if var.startswith("Alright Kiddo."):
        inner = var[len("Alright Kiddo."):].strip().lstrip(".").strip()
    else:
        inner = var.rstrip(".")
    return template.replace(placeholder, inner)


def _has_populated_intro_mirror_beat(beat: dict) -> bool:
    """True when this row is the locked canonical mirror tail (speak + burst + hold)."""
    if beat.get("intro_beat_role") != INTRO_BEAT_ROLE_CANONICAL_MIRROR:
        return False
    vp = (beat.get("kling_o3_video_path") or "").strip()
    return bool(vp) and os.path.isfile(vp)


def _intro_mirror_option_slot_ready(beat: dict) -> bool:
    """True when option slot 0 already pins the canonical intro_tail.mp4."""
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        slot_idx = opt.get("slot_index", opt.get("slot"))
        if slot_idx not in (0, "0"):
            continue
        src = str(opt.get("source") or "")
        vp = str(opt.get("video_path") or opt.get("path") or "").strip()
        if src == "canonical_intro_tail" and vp and os.path.isfile(vp):
            return True
    return False


def finalize_intro_canonical_tail_beats(
    beats: list[dict],
    event_id: str,
    phase: str,
    *,
    sidecar: dict | None = None,
) -> None:
    """Write-path: manifest defaults + intro_tail.mp4 on mirror row (not migrate-only)."""
    if phase != "pre":
        return
    segment_key = f"event_{event_id}_{phase}"
    for beat in beats or []:
        role = beat.get("intro_beat_role")
        if role in (INTRO_BEAT_ROLE_SEMI_CANONICAL, INTRO_BEAT_ROLE_CANONICAL_MIRROR):
            _apply_intro_canonical_beat_defaults(
                beat, event_id, phase, role,
                sidecar=sidecar, segment_key=segment_key,
            )
        if role == INTRO_BEAT_ROLE_CANONICAL_MIRROR:
            hydrate_intro_canonical_mirror_beat(
                beat, event_id, phase, sidecar=sidecar, segment_key=segment_key,
            )


def _single_canonical_intro_mode(
    *,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> bool:
    if not guide:
        guide = _infer_teleport_intro_guide(sidecar, segment_key)
    try:
        from lib.paths import dropbox_root
        from teleport_intro_canonical import load_registry

        return bool(load_registry(dropbox_root(), guide=guide).get("single_canonical"))
    except Exception:
        return False


def is_superseded_intro_tail_beat(beat: dict) -> bool:
    """Old transition/mirror rows replaced by canonical tail on re-extract.

    Authored intro beats 08–10 use scene_notes ``Transition to Spell`` with
    real dialogue — never treat that scene tag alone as superseded (regression:
    sidecar truncated to 7 beats and stitch fades landed on beat_07→mirror).
    """
    if is_canonical_lead_beat(beat.get("beat_id") or ""):
        return False
    if _has_populated_intro_mirror_beat(beat):
        return False
    role = beat.get("intro_beat_role")
    if role in (INTRO_BEAT_ROLE_SEMI_CANONICAL, INTRO_BEAT_ROLE_CANONICAL_MIRROR):
        return True
    scene = (beat.get("scene_notes") or "").lower()
    prompt = (beat.get("kling_o3_prompt") or "").lower()
    dialogue = (beat.get("dialogue_text") or "").strip()
    # Legacy unrole'd placeholders from pre-single-canonical re-extracts only.
    if not role and dialogue in ("", INTRO_DIALOGUE_PLACEHOLDER):
        if "transition to spell" in scene:
            return True
        if "teleport glass finale" in prompt or "teleport mirror" in scene:
            return True
    return False


def _blank_intro_canonical_beat(beat_id: str, role: str, cfg: dict) -> dict:
    placeholder = cfg.get("dialogue_placeholder") or INTRO_DIALOGUE_PLACEHOLDER
    dialogue = cfg.get("dialogue_text") if role == INTRO_BEAT_ROLE_CANONICAL_MIRROR else placeholder
    return {
        "beat_id": beat_id,
        "speaker": cfg.get("speaker") or "Chipper",
        "dialogue_text": dialogue or "",
        "scene_notes": (cfg.get("scene_notes") or "")[:200],
        "emotion": cfg.get("emotion") or "upbeat",
        "accepted_image_key": None,
        "flux_options": [],
        "status": "draft",
        "schema_version": 1,
        "pipeline": "kling_o3_omni",
        "intro_beat_role": role,
    }


def append_intro_canonical_tail_beats(
    beats: list[dict],
    beat_label: str,
    phase: str,
) -> None:
    """Append intro tail beat(s) after skeleton dialogue.

    ``single_canonical`` registry mode: one mirror tail only (no semi-canonical row).
    When a populated canonical mirror beat already exists, keep it and drop stale tails.
    """
    if phase != "pre":
        return
    manifest = _load_intro_canonical_beats_manifest()
    mirror_cfg = manifest.get("canonical_mirror_video") or {}
    if not mirror_cfg.get("prompt"):
        return

    if any(_has_populated_intro_mirror_beat(b) for b in beats):
        beats[:] = [
            b for b in beats
            if b.get("intro_beat_role") != INTRO_BEAT_ROLE_SEMI_CANONICAL
            and not is_superseded_intro_tail_beat(b)
        ]
        return

    beats[:] = [b for b in beats if not is_superseded_intro_tail_beat(b)]
    base = len(beats)
    mirror_id = f"bg_{beat_label}_beat_{base + 1:02d}"

    if _single_canonical_intro_mode():
        beats.append(_blank_intro_canonical_beat(
            mirror_id,
            INTRO_BEAT_ROLE_CANONICAL_MIRROR,
            mirror_cfg,
        ))
        return

    semi_cfg = manifest.get("semi_canonical_transition") or {}
    if not semi_cfg.get("prompt_template"):
        return
    semi = _blank_intro_canonical_beat(
        mirror_id,
        INTRO_BEAT_ROLE_SEMI_CANONICAL,
        semi_cfg,
    )
    mirror = _blank_intro_canonical_beat(
        f"bg_{beat_label}_beat_{base + 2:02d}",
        INTRO_BEAT_ROLE_CANONICAL_MIRROR,
        mirror_cfg,
    )
    beats.extend([semi, mirror])


def _apply_intro_canonical_beat_defaults(
    beat: dict,
    event_id: str,
    phase: str,
    role: str,
    *,
    guide: str | None = None,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> None:
    if not guide:
        guide = _infer_teleport_intro_guide(sidecar, segment_key) or (beat.get("speaker") or "")
    manifest = _load_intro_canonical_beats_manifest(
        guide=guide, sidecar=sidecar, segment_key=segment_key,
    )
    manifest_kw = {"guide": guide, "sidecar": sidecar, "segment_key": segment_key}
    if role == INTRO_BEAT_ROLE_CANONICAL_MIRROR:
        cfg = manifest.get("canonical_mirror_video") or {}
        beat["kling_o3_prompt"] = cfg.get("prompt") or ""
        beat["dialogue_text"] = cfg.get("dialogue_text") or beat.get("dialogue_text") or ""
        beat["speaker"] = cfg.get("speaker") or beat.get("speaker") or "Arlo"
        ref = _resolve_intro_manifest_asset(cfg.get("char_ref_asset") or "mirror_char", **manifest_kw)
        if ref:
            beat["reference_image"] = ref
        beat["reference_image_locked"] = True
        bg_ref = _resolve_intro_manifest_asset(cfg.get("bg_ref_asset") or "studio_bg", **manifest_kw)
        if bg_ref:
            beat["bg_ref_image"] = bg_ref
    elif role == INTRO_BEAT_ROLE_SEMI_CANONICAL:
        cfg = manifest.get("semi_canonical_transition") or {}
        beat["speaker"] = cfg.get("speaker") or beat.get("speaker") or "Arlo"
        existing = (beat.get("kling_o3_prompt") or "").strip()
        placeholder = cfg.get("dialogue_placeholder") or INTRO_DIALOGUE_PLACEHOLDER
        cfg_speaker = (cfg.get("speaker") or beat.get("speaker") or "").strip()
        stale_cast = bool(
            cfg_speaker
            and existing
            and cfg_speaker.lower() not in existing.lower()
        )
        if not existing or placeholder in existing or stale_cast:
            beat["kling_o3_prompt"] = build_intro_semi_canonical_transition_prompt(
                beat.get("dialogue_text"),
                guide=guide,
                sidecar=sidecar,
                segment_key=segment_key,
            )
        ref = _resolve_intro_manifest_asset(cfg.get("char_ref_asset") or "neutral_char", **manifest_kw)
        if ref and not beat.get("reference_image_locked"):
            beat["reference_image"] = ref
        if cfg.get("reference_image_locked"):
            beat["reference_image_locked"] = True
        bg_ref = _resolve_intro_manifest_asset(cfg.get("bg_ref_asset") or "studio_bg", **manifest_kw)
        if bg_ref:
            beat["bg_ref_image"] = bg_ref
        elif not beat.get("bg_ref_image"):
            bg_path = resolve_beat_bg_ref_path(beat, event_id, phase)
            if bg_path:
                beat["bg_ref_image"] = _ref_dict_from_path(bg_path)
        manifest_emo = str(cfg.get("emotion") or "").strip()
        beat_emo = str(beat.get("emotion") or "").strip().lower()
        if manifest_emo and beat_emo in ("", "upbeat", "[upbeat]"):
            beat["emotion"] = manifest_emo
    if not beat.get("kling_o3_duration_locked"):
        beat["kling_o3_duration"] = resolve_kling_o3_submit_duration(
            beat, beat.get("kling_o3_prompt") or "",
        )
    beat.setdefault("kling_o3_status", "draft")


def _intro_mirror_tail_is_stale(beat: dict, guide: str | None) -> bool:
    """Detect Chipper-template tail on Arlo guide rows (and vice versa)."""
    try:
        from teleport_intro_canonical import intro_tail_path_matches_guide
    except ImportError:
        return False
    vp = beat.get("kling_o3_video_path") or ""
    if vp and not intro_tail_path_matches_guide(vp, guide):
        return True
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        if str(opt.get("source") or "") != "canonical_intro_tail":
            continue
        ovp = opt.get("video_path") or opt.get("path") or ""
        if ovp and not intro_tail_path_matches_guide(ovp, guide):
            return True
    return False


def _clear_stale_intro_mirror_tail(beat: dict) -> None:
    """Drop wrong-template canonical tail so hydrate re-resolves from registry."""
    beat.pop("kling_o3_video_path", None)
    beat.pop("accepted_video_path", None)
    beat.pop("kling_o3_baked_path", None)
    beat.pop("kling_o3_baked_token", None)
    beat["kling_o3_options"] = [
        o for o in (beat.get("kling_o3_options") or [])
        if not (isinstance(o, dict) and str(o.get("source") or "") == "canonical_intro_tail")
    ]


def hydrate_intro_canonical_mirror_beat(
    beat: dict,
    event_id: str,
    phase: str,
    *,
    sidecar: dict | None = None,
    segment_key: str | None = None,
) -> bool:
    """Insert built intro_tail.mp4 + Arlo manifest prompts on canonical mirror row."""
    if beat.get("intro_beat_role") != INTRO_BEAT_ROLE_CANONICAL_MIRROR:
        return False
    guide = (beat.get("speaker") or _infer_teleport_intro_guide(sidecar, segment_key) or "Arlo").strip()
    _apply_intro_canonical_beat_defaults(
        beat, event_id, phase, INTRO_BEAT_ROLE_CANONICAL_MIRROR,
        guide=guide, sidecar=sidecar, segment_key=segment_key,
    )
    if _intro_mirror_tail_is_stale(beat, guide):
        _clear_stale_intro_mirror_tail(beat)
    if _has_populated_intro_mirror_beat(beat) and _intro_mirror_option_slot_ready(beat):
        if not _intro_mirror_tail_is_stale(beat, guide):
            seed_canonical_intro_tail_export_trim(
                beat, guide=guide, sidecar=sidecar, segment_key=segment_key,
            )
            return True
        _clear_stale_intro_mirror_tail(beat)
    if _has_populated_intro_mirror_beat(beat):
        tail_str = str(Path(beat["kling_o3_video_path"]).resolve())
        now = datetime.now(timezone.utc).isoformat()
        beat.setdefault("kling_o3_status", "approved")
        beat.setdefault("canonical_intro_tail", True)
        assign_kling_o3_option_to_slot(
            beat,
            0,
            video_path=tail_str,
            label="Canonical intro tail",
            source="canonical_intro_tail",
            now=now,
        )
        seed_canonical_intro_tail_export_trim(
            beat, guide=guide, sidecar=sidecar, segment_key=segment_key,
        )
        return True
    try:
        from lib.paths import dropbox_root
        from teleport_intro_canonical import resolve_canonical_tail_for_event

        tail = resolve_canonical_tail_for_event(
            str(event_id),
            dropbox_root(),
            phase=phase,
            event_id=str(event_id),
            guide=guide,
        )
    except Exception:
        tail = None
    if not tail or not tail.is_file():
        return False
    tail_str = str(tail.resolve())
    now = datetime.now(timezone.utc).isoformat()
    beat["kling_o3_video_path"] = tail_str
    from kling_stitch_readiness import finalize_kling_delivery_clip  # noqa: PLC0415

    finalize_kling_delivery_clip(beat, tail_str)
    beat["canonical_intro_tail"] = True
    assign_kling_o3_option_to_slot(
        beat,
        0,
        video_path=tail_str,
        label="Canonical intro tail",
        source="canonical_intro_tail",
        now=now,
    )
    seed_canonical_intro_tail_export_trim(
        beat, guide=guide, sidecar=sidecar, segment_key=segment_key,
    )
    return True


def merge_incoming_segment_beats(
    existing_beats: list[dict],
    incoming_beats: list[dict],
    *,
    preserve_fields: tuple[str, ...] | None = None,
) -> list[dict]:
    """Merge skeleton/import beats with sidecar orphans (canonical slots, etc.)."""
    existing_map = {b["beat_id"]: b for b in (existing_beats or []) if b.get("beat_id")}
    incoming_ids = {b["beat_id"] for b in incoming_beats if b.get("beat_id")}
    orphans = [b for b in (existing_beats or []) if b.get("beat_id") not in incoming_ids]
    merged: list[dict] = []
    for b in incoming_beats:
        beat_id = b.get("beat_id")
        saved = existing_map.get(beat_id) if beat_id else None
        if saved:
            fields = preserve_fields or sidecar_merge_preserve_fields(saved)
            for field in fields:
                val = saved.get(field)
                if val not in (None, "", [], {}):
                    b[field] = val
            if saved.get("intro_beat_role") == INTRO_BEAT_ROLE_SEMI_CANONICAL:
                saved_dlg = (saved.get("dialogue_text") or "").strip()
                if saved_dlg and saved_dlg != INTRO_DIALOGUE_PLACEHOLDER:
                    b["dialogue_text"] = saved_dlg
            if saved.get("intro_beat_role") == INTRO_BEAT_ROLE_CANONICAL_MIRROR:
                for field in (
                    "kling_o3_generation", "kling_o3_video_path", "kling_o3_task_id",
                ):
                    val = saved.get(field)
                    if val not in (None, "", [], {}):
                        b[field] = val
        merged.append(b)
    merged.extend(orphans)
    return normalize_segment_beat_order(merged)


def apply_segment_beat_reorder(
    beats: list[dict],
    beat_ids: list[str],
    *,
    allow_partial: bool = False,
) -> tuple[list[dict] | None, list[str]]:
    """Reorder beats by ``beat_ids``; never silently drop rows unless ``allow_partial``."""
    beat_map = {b["beat_id"]: b for b in beats if b.get("beat_id")}
    missing = [bid for bid in beat_ids if bid not in beat_map]
    if missing:
        return None, [f"unknown beat_id: {bid}" for bid in missing]
    omitted = [b["beat_id"] for b in beats if b["beat_id"] not in beat_ids]
    if omitted and not allow_partial:
        return None, [
            f"reorder would drop {len(omitted)} beat(s): {', '.join(omitted)}"
        ]
    reordered = [beat_map[bid] for bid in beat_ids]
    if allow_partial and omitted:
        extras = [beat_map[bid] for bid in omitted if bid in beat_map]
        reordered = normalize_segment_beat_order(reordered + extras)
    return reordered, []


# ---------------------------------------------------------------------------
# Arc skeleton parsing
# ---------------------------------------------------------------------------

def _skeleton_path(arc_number):
    n = str(arc_number).zfill(2)
    return os.path.join(_SKELETON_BASE, f"ARC_{n}_SKELETON_FINAL.md")


# Events that produce no video beats — skip them
_SKIP_TYPES = re.compile(
    r"\((?:interactive|map landing|map|avatar creation|no video|phase b|ui only|data|non-video)\)",
    re.IGNORECASE,
)

# Regex patterns for skeleton structure
_EVENT_HEADER_H2 = re.compile(
    r"^##\s+EVENT\s+([\d]+[a-z]?):\s*(.+)", re.IGNORECASE | re.MULTILINE,
)
_EVENT_HEADER_UNDERLINE = re.compile(
    r"^EVENT\s+([\d]+[a-z]?):\s*(.+?)\s*\n[-=]{3,}",
    re.IGNORECASE | re.MULTILINE,
)
# Arc 2+ post-section events: ``EVENT 5\n-------`` with title on following lines.
_EVENT_HEADER_PLAIN = re.compile(
    r"^EVENT\s+([\d]+[a-z]?)\s*\n[-=]{3,}",
    re.IGNORECASE | re.MULTILINE,
)
_EVENT_HEADER = _EVENT_HEADER_H2
_SKELETON_METADATA_LINE = re.compile(
    r"\*\*Creature:\s*(.+?)\s*\|\s*Domain:\s*(.+?)\s*\|\s*Technique:\s*(.+?)"
    r"\s*\|\s*Spell Name:\s*(.+?)\s*(?:\||\*\*)",
    re.IGNORECASE | re.DOTALL,
)
_SECTION_SETUP = re.compile(
    r"^###\s+(?:Narrative Setup|Intro Video(?:\s*---\s*Narrative Setup)?|Video Intro)",
    re.IGNORECASE | re.MULTILINE,
)
_SECTION_SETUP_BOLD = re.compile(r"^\*\*Video Intro\*\*", re.IGNORECASE | re.MULTILINE)
_SECTION_THERAP = re.compile(r"^###\s+Therapeutic", re.IGNORECASE | re.MULTILINE)
_SECTION_RES = re.compile(
    r"^###\s+(?:Resolution|Video Resolution)", re.IGNORECASE | re.MULTILINE,
)
_SECTION_TMRW = re.compile(r"^###\s+Tomorrow Hook", re.IGNORECASE | re.MULTILINE)
_SECTION_POST = re.compile(r"^###\s+Post-", re.IGNORECASE | re.MULTILINE)
_NEXT_H3 = re.compile(r"^###", re.MULTILINE)
_MODULE_MARKER = re.compile(
    r"(?:\*\*)?[►▶]\s*INSERT MODULE|^INSERT MODULE\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_M_NUMBER_IN_TITLE = re.compile(r"\(M(\d+)\)", re.IGNORECASE)

# Dialogue line patterns (most specific first)
_DIALOGUE_PATS = [
    re.compile(r"^>\s*\*\*([A-Za-z][A-Za-z ]{1,30}?)\*\*:\s*\"([^\"]+)\"",  re.MULTILINE),
    re.compile(r"^>\s*([A-Za-z][A-Za-z ]{1,30}?):\s*\"([^\"]+)\"",           re.MULTILINE),
    re.compile(r"^\*\*([A-Za-z][A-Za-z ]{1,30}?)\*\*:\s*\"([^\"]+)\"",       re.MULTILINE),
    re.compile(r"^([A-Z][A-Za-z ]{2,25}):\s*\"([^\"]+)\"",                   re.MULTILINE),
    # Parens format: Character: (action) "text"
    re.compile(r"^([A-Z][A-Za-z ]{2,25}):\s*\([^)]+\)\s*\"([^\"]+)\"",       re.MULTILINE),
    # Apostrophe + optional pre-colon tag: Tessa's voice (narrating): "text"
    re.compile(r"^([A-Z][A-Za-z' ]+?)(?:\s*\([^)]+\))?:\s*\"([^\"]+)\"",     re.MULTILINE),
]

# Headers / annotations that look like speaker names — reject these
_REJECT_SPEAKERS = re.compile(
    r"^(Production Note|Data|Trigger|Format|Duration|Visual Style|Pacing|"
    r"Technique|Clinical|Tomorrow Hook|Win |Map State|Narrative|Resolution|"
    r"Creature|Domain|Spell|Type|Classification|Why |How |What |Level |"
    r"Emotional|Guide Bird's|Kim's)$",
    re.IGNORECASE,
)


def _canon_speaker(raw):
    if not raw:
        return ""
    try:
        from tools import kling_character_registry as reg

        return reg.normalize_beat_speaker_for_sidecar(raw)
    except Exception:
        return _BG_SPEAKER_ALIAS.get(raw.strip().lower(), raw.strip())


def _infer_emotion(dialogue, scene=""):
    combined = (dialogue + " " + scene).lower()
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return emotion
    return "neutral"


def _parse_event_header_rest(rest: str) -> tuple[str, str]:
    type_m = re.search(r"\(([^)]+)\)\s*$", rest)
    event_type = type_m.group(1).strip() if type_m else "Narrative Event"
    clean_name = rest[: type_m.start()].strip() if type_m else rest
    return event_type, clean_name


def _title_from_plain_event_block(event_text: str) -> str:
    """First bold title line after plain ``EVENT N\\n---`` header."""
    for line in event_text.splitlines()[1:8]:
        line = line.strip()
        if line.startswith("**") and line.endswith("**"):
            return line.strip("*").strip()
    return ""


def _normalize_skeleton_metadata_text(event_text: str) -> str:
    return (event_text or "").replace("\\|", "|")


def parse_skeleton_module_metadata_from_text(event_text: str) -> dict:
    """Parse ``**Creature: … | Domain: … | Technique: … | Spell Name: …**`` line."""
    normalized = _normalize_skeleton_metadata_text(event_text)
    m = _SKELETON_METADATA_LINE.search(normalized)
    if not m:
        return {}
    return {
        "creature": m.group(1).strip(),
        "domain": m.group(2).strip(),
        "technique": m.group(3).strip(),
        "spell_name": m.group(4).strip(),
    }


def m_number_from_event_block(block: dict) -> int | None:
    """Resolve creature M-number from an event block (title, metadata, or body)."""
    meta = parse_skeleton_module_metadata_from_text(block.get("event_text") or "")
    for src in (
        block.get("clean_name") or "",
        block.get("event_text") or "",
    ):
        m_marker = _M_NUMBER_IN_TITLE.search(src)
        if m_marker:
            return int(m_marker.group(1))
    return None


def _collect_event_blocks(text: str) -> list[dict]:
    """Collect event blocks from skeleton text (Arc 1 ## headers + Arc 2 underline)."""
    markers: list[tuple[int, str, str]] = []
    for m in _EVENT_HEADER_H2.finditer(text):
        markers.append((m.start(), str(m.group(1)), m.group(2).strip()))
    for m in _EVENT_HEADER_UNDERLINE.finditer(text):
        markers.append((m.start(), str(m.group(1)), m.group(2).strip()))
    underline_starts = {m.start() for m in _EVENT_HEADER_UNDERLINE.finditer(text)}
    h2_starts = {m.start() for m in _EVENT_HEADER_H2.finditer(text)}
    for m in _EVENT_HEADER_PLAIN.finditer(text):
        if m.start() in underline_starts or m.start() in h2_starts:
            continue
        markers.append((m.start(), str(m.group(1)), ""))
    markers.sort(key=lambda t: t[0])
    # Dedupe same event_id at same position (prefer first)
    seen_pos: set[int] = set()
    unique: list[tuple[int, str, str]] = []
    for pos, eid, rest in markers:
        if pos in seen_pos:
            continue
        seen_pos.add(pos)
        unique.append((pos, eid, rest))

    blocks: list[dict] = []
    for i, (pos, event_id, rest) in enumerate(unique):
        end = unique[i + 1][0] if i + 1 < len(unique) else len(text)
        event_text = text[pos:end]
        if rest:
            event_type, clean_name = _parse_event_header_rest(rest)
        else:
            plain_title = _title_from_plain_event_block(event_text)
            event_type, clean_name = _parse_event_header_rest(plain_title or rest)
        if _SKIP_TYPES.search(f"({event_type})"):
            continue
        blocks.append({
            "pos": pos,
            "event_id": event_id,
            "event_type": event_type,
            "clean_name": clean_name,
            "event_text": event_text,
            "has_module": bool(_MODULE_MARKER.search(event_text)),
        })
    return blocks


def _find_intro_section_start(event_text: str) -> tuple[int, str, str] | None:
    """Return (start_pos, label, method) for intro body within an event block."""
    for pat, label, method in (
        (_SECTION_SETUP, "Narrative Setup", "regex_setup"),
        (_SECTION_SETUP_BOLD, "Video Intro", "regex_bold_intro"),
    ):
        m = pat.search(event_text)
        if m:
            return m.end(), label, method
    return None


def slice_skeleton_section(arc_number, event_id, phase="full") -> dict:
    """
    Return one skeleton section blob for Beat Gen segment scope.

    Returns dict with keys: text, section_label, slice_method, event_name,
    m_number, arc_number, event_id, phase, char_count.
    Empty text when event/section not found.
    """
    path = _skeleton_path(arc_number)
    result: dict = {
        "arc_number": int(arc_number),
        "event_id": str(event_id),
        "phase": str(phase),
        "text": "",
        "section_label": "",
        "slice_method": "not_found",
        "event_name": "",
        "m_number": None,
        "char_count": 0,
    }
    if not os.path.exists(path):
        return result
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    event_id = str(event_id)
    blocks = _collect_event_blocks(text)
    event_block = next((b for b in blocks if b["event_id"] == event_id), None)
    if not event_block:
        return result

    event_text = event_block["event_text"]
    result["event_name"] = event_block["clean_name"]
    header_line = event_text.splitlines()[0] if event_text else ""
    m_m = _M_NUMBER_IN_TITLE.search(header_line) or _M_NUMBER_IN_TITLE.search(event_block["clean_name"])
    if m_m:
        result["m_number"] = int(m_m.group(1))

    phase = str(phase)
    if phase in ("pre", "full"):
        intro = _find_intro_section_start(event_text)
        if intro:
            start, label, method = intro
            body = _slice_section(
                event_text, start,
                [_SECTION_THERAP, _SECTION_RES, _NEXT_H3],
            )
            mod_m = _MODULE_MARKER.search(body)
            if mod_m and phase == "pre":
                body = body[: mod_m.start()]
            result.update({
                "text": body.strip(),
                "section_label": label,
                "slice_method": method,
                "char_count": len(body.strip()),
            })
            return result
        if phase == "full" and not event_block["has_module"]:
            result.update({
                "text": event_text.strip(),
                "section_label": "full event",
                "slice_method": "full_event",
                "char_count": len(event_text.strip()),
            })
            return result

    if phase in ("post", "full"):
        res_m = _SECTION_RES.search(event_text)
        if res_m:
            body = _slice_section(
                event_text, res_m.end(),
                [_SECTION_TMRW, _SECTION_POST, _NEXT_H3],
            )
            result.update({
                "text": body.strip(),
                "section_label": "Resolution",
                "slice_method": "regex_resolution",
                "char_count": len(body.strip()),
            })
            return result

    if phase == "full":
        result.update({
            "text": event_text.strip(),
            "section_label": "full event fallback",
            "slice_method": "full_event_fallback",
            "char_count": len(event_text.strip()),
        })
    return result


def get_segments(arc_number):
    """
    Return list of video-producing segments from ARC_0N_SKELETON_FINAL.md.
    Events containing a module marker are split into two rows:
      phase="pre"  → "EVENT N: NAME — Intro"
      phase="post" → "EVENT N: NAME — Resolution"
    Events without a module marker emit one row with phase="full".
    Each item: { segment_index, name, event_id, event_type, phase }
    """
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    valid = _collect_event_blocks(text)

    segments = []
    seg_idx = 0
    for ev in valid:
        has_module = ev["has_module"]
        base = {"event_id": ev["event_id"], "event_type": ev["event_type"]}

        if has_module:
            segments.append({**base, "segment_index": seg_idx,
                              "name": f"EVENT {ev['event_id']}: {ev['clean_name']} \u2014 Intro",
                              "phase": "pre"})
            seg_idx += 1
            segments.append({**base, "segment_index": seg_idx,
                              "name": f"EVENT {ev['event_id']}: {ev['clean_name']} \u2014 Resolution",
                              "phase": "post"})
            seg_idx += 1
        else:
            segments.append({**base, "segment_index": seg_idx,
                              "name": f"EVENT {ev['event_id']}: {ev['clean_name']}",
                              "phase": "full"})
            seg_idx += 1
    return segments


def _slice_section(event_text, section_start, end_patterns):
    """Slice event_text from section_start to the nearest end_pattern match."""
    ends = []
    for pat in end_patterns:
        m = pat.search(event_text, section_start)
        if m:
            ends.append(m.start())
    return event_text[section_start: min(ends)] if ends else event_text[section_start:]


def _extract_dialogue_from_block(block, beat_label, beat_list, stop_at_module=True):
    """Parse dialogue lines from a section block, appending to beat_list.

    beat_label: stable string used in beat_id, e.g. "arc1_event1_pre".
    stop_at_module: if True, truncate block at the first INSERT MODULE marker.
    """
    if stop_at_module:
        stop_m = _MODULE_MARKER.search(block)
        if stop_m:
            block = block[:stop_m.start()]

    found = {}  # start_pos → (speaker, dialogue, scene_note)
    for pat in _DIALOGUE_PATS:
        for m in pat.finditer(block):
            if m.start() in found:
                continue
            spk = m.group(1).strip()
            dlg = m.group(2).strip()
            # Reject non-speaker "speakers"
            if _REJECT_SPEAKERS.match(spk):
                continue
            if re.match(r"^[A-Z]{3,}$", spk) and len(spk) > 4:
                continue  # ALL CAPS heading
            # Scene note: last non-empty non-annotation line before this match
            pre = block[max(0, m.start() - 300):m.start()]
            pre_lines = [l.strip() for l in pre.splitlines()
                         if l.strip() and not l.strip().startswith(("**[", "[DATA", "**►"))]
            scene_note = pre_lines[-1] if pre_lines else ""
            found[m.start()] = (spk, dlg, scene_note)

    beat_num_start = len(beat_list) + 1
    for pos in sorted(found):
        spk, dlg, scene_note = found[pos]
        canon = _canon_speaker(spk)
        n = beat_num_start + (list(sorted(found)).index(pos))
        beat_list.append({
            "beat_id":            f"bg_{beat_label}_beat_{n:02d}",
            "speaker":            canon if canon else spk,
            "dialogue_text":      dlg,
            "scene_notes":        scene_note[:200],
            "emotion":            _infer_emotion(dlg, scene_note),
            "accepted_image_key": None,
            "flux_options":       [],
            "status":             "draft",
            "schema_version":     1,
        })


def extract_beats(arc_number, event_id, phase="full"):
    """
    Extract dialogue beats for a specific event_id and phase from ARC_0N_SKELETON_FINAL.md.

    phase="pre"  → Narrative Setup only (stops at module marker)
    phase="post" → Resolution section only (starts after module marker)
    phase="full" → both sections (backward-compat for events without a module marker)

    Returns list of beat dicts (no kling_prompt field).
    """
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # Collect valid event positions + ids (same filter as get_segments)
    valid_pos = []
    valid_ids = []
    for m in _EVENT_HEADER.finditer(text):
        eid = str(m.group(1))
        rest = m.group(2).strip()
        type_m = re.search(r"\(([^)]+)\)\s*$", rest)
        event_type = type_m.group(1).strip() if type_m else "Narrative Event"
        if _SKIP_TYPES.search(f"({event_type})"):
            continue
        valid_pos.append(m.start())
        valid_ids.append(eid)

    event_id = str(event_id)
    if event_id not in valid_ids:
        return []

    ev_i = valid_ids.index(event_id)
    seg_start = valid_pos[ev_i]
    seg_end = valid_pos[ev_i + 1] if ev_i + 1 < len(valid_pos) else len(text)
    event_text = text[seg_start:seg_end]

    beat_label = f"arc{arc_number}_event{event_id}_{phase}"
    beats = []

    if phase in ("pre", "full"):
        ns_m = _SECTION_SETUP.search(event_text)
        if ns_m:
            ns_body = _slice_section(event_text, ns_m.end(),
                                     [_SECTION_THERAP, _SECTION_RES, _NEXT_H3])
            _extract_dialogue_from_block(ns_body, beat_label, beats, stop_at_module=True)

    if phase in ("post", "full"):
        res_m = _SECTION_RES.search(event_text)
        if res_m:
            res_body = _slice_section(event_text, res_m.end(),
                                      [_SECTION_TMRW, _SECTION_POST, _NEXT_H3])
            # Resolution section is after the module marker — no need to stop at it
            _extract_dialogue_from_block(res_body, beat_label, beats, stop_at_module=False)

    # Re-number beats sequentially (avoids gaps)
    for i, beat in enumerate(beats):
        beat["beat_id"] = f"bg_{beat_label}_beat_{i+1:02d}"

    append_intro_canonical_tail_beats(beats, beat_label, phase)
    finalize_intro_canonical_tail_beats(beats, str(event_id), phase)

    return beats


# ---------------------------------------------------------------------------
# PB_2_THERAPEUTIC_SOURCES_LOAD_V1 — therapeutic source loaders for Suggest Script
#
# Extends existing skeleton-parsing infrastructure (_skeleton_path, _EVENT_HEADER,
# _SECTION_THERAP, _NEXT_H3) with two public helpers:
#   - find_event_for_module(arc_number, m_number) -> arc_event_id string or None
#   - extract_therapeutic_note(arc_number, m_number) -> Therapeutic Note section text
#   - load_technique_inventory() -> full text of latest Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_*.md
#
# Used by production_server._handle_phase_suggest_script to ground Claude API
# prompts in real authored sources instead of generic templates.
# ---------------------------------------------------------------------------

_CANON_BASE = os.path.join(_PROJECT_DIR, "Canon")

# Matches "(M<n>)" anywhere in an EVENT header title (e.g., "TESSA'S FALL (M1)")
# (pattern defined above with skeleton regex block)

# Module Structure Table: | play_order | M# | Creature | ...
_MODULE_STRUCTURE_TABLE_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*M(\d+)\s*\|",
    re.MULTILINE,
)


def _parse_module_structure_play_order_map(arc_number):
    """Return {play_order: m_number} from the skeleton Module Structure Table."""
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {}
    result = {}
    in_table = False
    for line in text.splitlines():
        if "Module Structure Table" in line:
            in_table = True
            continue
        if in_table and line.startswith("### ") and "Module Structure Table" not in line:
            break
        if not in_table:
            continue
        row = _MODULE_STRUCTURE_TABLE_ROW.match(line.strip())
        if row:
            result[int(row.group(1))] = int(row.group(2))
    return result


def _parse_prose_module_structure_play_order_map(arc_number):
    """Return {play_order: m_number} from prose ``Module structure:`` lists (Arc 2+)."""
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {}
    m = re.search(
        r"Module structure:\s*\n(.*?)(?:\n\n[A-Z][A-Z ]|\nKEY MILESTONES|\nARC PREMISE|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return {}
    section = m.group(1)
    m_numbers = [int(x) for x in re.findall(r"\(M(\d+)", section, re.IGNORECASE)]
    return {i + 1: mn for i, mn in enumerate(m_numbers)}


def find_m_number_for_play_order_event(arc_number, play_order):
    """Map skeleton play-order event # → creature M-number.

    Production ``Event_N`` folders follow skeleton **play order** (not M-number):
    Event_3 = play #3 = Ember M4, not Benson M3. Per ARC_01 skeleton Module
    Structure Table + ``## EVENT N: … (M#)`` headers.

    Returns m_number int or None when not found.
    """
    play_order = int(play_order)
    table = _parse_module_structure_play_order_map(arc_number)
    if play_order in table:
        return table[play_order]

    prose = _parse_prose_module_structure_play_order_map(arc_number)
    if play_order in prose:
        return prose[play_order]

    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None

    blocks = _collect_event_blocks(text)
    module_blocks = [b for b in blocks if b["has_module"]]
    if play_order <= len(module_blocks):
        mn = m_number_from_event_block(module_blocks[play_order - 1])
        if mn is not None:
            return mn

    for block in blocks:
        if str(block["event_id"]) != str(play_order):
            continue
        mn = m_number_from_event_block(block)
        if mn is not None:
            return mn
    return None


def find_event_for_module(arc_number, m_number):
    """Find arc-event-id whose event block matches (M<m_number>)."""
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None
    target = int(m_number)
    for block in _collect_event_blocks(text):
        if m_number_from_event_block(block) == target:
            return str(block["event_id"])
    return None


def extract_skeleton_module_metadata(arc_number, m_number):
    """Extract spell name, technique, domain, creature from the module event block."""
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {}
    target = int(m_number)
    for block in _collect_event_blocks(text):
        if m_number_from_event_block(block) != target:
            continue
        meta = parse_skeleton_module_metadata_from_text(block["event_text"])
        meta["skeleton_event_id"] = block["event_id"]
        meta["event_name"] = block["clean_name"]
        return meta
    return {}


def extract_therapeutic_note(arc_number, m_number):
    """Extract Therapeutic Note for (M<m_number>) — Arc 1 H2 + Arc 2 underline/plain."""
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return ""

    target = int(m_number)
    event_block = None
    for block in _collect_event_blocks(text):
        if m_number_from_event_block(block) == target:
            event_block = block["event_text"]
            break
    if not event_block:
        return ""

    therap_match = _SECTION_THERAP.search(event_block)
    if not therap_match:
        return ""

    next_h3 = _NEXT_H3.search(event_block, therap_match.end())
    section_end = next_h3.start() if next_h3 else len(event_block)
    return event_block[therap_match.start():section_end].strip()


def load_technique_inventory():
    """Load the highest-version Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_*.md.

    Returns the full text, or empty string if not found. The technique inventory
    is the canonical catalog of MindfulNest techniques (palm interoception,
    physiological sigh, squeeze-release, etc.) with mechanism + age suitability
    + clinical references. Injected into Suggest Script prompts so Claude
    references the canonical technique names + mechanisms rather than inventing.
    """
    import glob
    paths = glob.glob(os.path.join(_CANON_BASE, "UNIFIED_TECHNIQUE_INVENTORY_v1_*.md"))
    if not paths:
        return ""

    def _version_key(p):
        m = re.search(r"v1_(\d+)", os.path.basename(p))
        return int(m.group(1)) if m else 0

    latest = max(paths, key=_version_key)
    try:
        with open(latest, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def slice_technique_inventory_for_module(m_number, inventory_text=None):
    """Return M-number-specific inventory rows (not the full ~80k catalog)."""
    if inventory_text is None:
        inventory_text = load_technique_inventory()
    if not inventory_text:
        return ""
    m = int(m_number)
    rows: list[str] = []
    seen: set[str] = set()
    for line in inventory_text.splitlines():
        if re.match(rf"^\|\s*M{m}\s*\|", line) and line not in seen:
            rows.append(line)
            seen.add(line)
    if not rows:
        return inventory_text[:6000]
    return (
        f"Technique Inventory slice for M{m} ONLY "
        "(Arc Skeleton Spell Name wins if this conflicts):\n"
        + "\n".join(rows)
    )


def load_phase_b_research_dossier(m_number):
    """Load ``Production/M{n}_PHASE_B_RESEARCH_DOSSIER*.md`` (highest version)."""
    try:
        sys.path.insert(0, os.path.join(_TOOLS_DIR, "..", "lib"))
        from phase_b_suggest_sources import load_phase_b_research_dossier as _load  # noqa: PLC0415

        prod_dir = os.path.join(_PROJECT_DIR, "Production")
        return _load(prod_dir, int(m_number))
    except Exception:
        return {"filename": "", "path": "", "chars": 0, "text": ""}


def load_phase_b_approved_script(m_number):
    """Load ``Production/M{n}_PHASE_B_MEDITATION_SCRIPT*.md`` when on disk."""
    try:
        sys.path.insert(0, os.path.join(_TOOLS_DIR, "..", "lib"))
        from phase_b_suggest_sources import load_phase_b_approved_script as _load  # noqa: PLC0415

        prod_dir = os.path.join(_PROJECT_DIR, "Production")
        return _load(prod_dir, int(m_number))
    except Exception:
        return {"filename": "", "path": "", "chars": 0, "text": ""}


# Glob patterns for Phase B Suggest Script authoring docs under Production/.
# Highest v1_N match wins per pattern (timestamp-safe: newer version suffix
# beats older). Docs live on the Dropbox project root; resolved via init_bg_paths.
_PHASE_B_SUGGEST_SCRIPT_DOC_GLOBS = (
    ("PHASE_B_CLARITY_CHECKLIST_v1_*.md", "clarity_checklist"),
    ("PHASE_B_PRODUCTION_PROCESS_v1_*.md", "production_process"),
)

# Phase A Suggest Script — beat-purpose skeleton under Production/.
_PHASE_A_SUGGEST_SCRIPT_DOC_GLOBS = (
    ("PHASE_A_SUGGEST_SKELETON_v1_*.md", "suggest_skeleton"),
)


def _latest_versioned_production_md(pattern: str):
    """Return (absolute_path, basename) for highest v1_N under Production/."""
    import glob
    prod_dir = os.path.join(_PROJECT_DIR, "Production")
    paths = glob.glob(os.path.join(prod_dir, pattern))
    if not paths:
        return "", ""

    def _version_key(p):
        m = re.search(r"v1_(\d+)", os.path.basename(p))
        return int(m.group(1)) if m else 0

    latest = max(paths, key=_version_key)
    return latest, os.path.basename(latest)


def load_phase_b_suggest_script_docs():
    """Load highest-version Phase B authoring docs for Suggest Script.

    Returns a list of dicts with keys: key, filename, version, chars, text.
    Empty text when a doc is missing on disk (caller should warn).
    """
    docs = []
    for pattern, key in _PHASE_B_SUGGEST_SCRIPT_DOC_GLOBS:
        path, basename = _latest_versioned_production_md(pattern)
        entry = {
            "key": key,
            "filename": basename,
            "version": 0,
            "chars": 0,
            "text": "",
        }
        if not path:
            docs.append(entry)
            continue
        m = re.search(r"v1_(\d+)", basename)
        entry["version"] = int(m.group(1)) if m else 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            entry["text"] = text
            entry["chars"] = len(text)
        except Exception:
            pass
        docs.append(entry)
    return docs


def load_phase_a_suggest_script_docs():
    """Load highest-version Phase A Suggest Script authoring docs.

    Returns a list of dicts with keys: key, filename, version, chars, text.
    Empty text when a doc is missing on disk (caller should warn).
    """
    docs = []
    for pattern, key in _PHASE_A_SUGGEST_SCRIPT_DOC_GLOBS:
        path, basename = _latest_versioned_production_md(pattern)
        entry = {
            "key": key,
            "filename": basename,
            "version": 0,
            "chars": 0,
            "text": "",
        }
        if not path:
            docs.append(entry)
            continue
        m = re.search(r"v1_(\d+)", basename)
        entry["version"] = int(m.group(1)) if m else 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            entry["text"] = text
            entry["chars"] = len(text)
        except Exception:
            pass
        docs.append(entry)
    return docs


# ---------------------------------------------------------------------------
# FLUX Kontext API  (BFL api.bfl.ai)
# ---------------------------------------------------------------------------

def _bfl_api_key():
    """Read BFL key from API_KEYS_MASTER.md (line containing 'FLUX Kontext')."""
    candidates = [
        os.path.join(_PROD_DIR, "API_KEYS_MASTER.md"),
        os.path.join(_PROJECT_DIR, "Production", "API_KEYS_MASTER.md"),
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                if "FLUX Kontext" in line or "bfl_" in line:
                    # Table row: | Service | Key | Notes | → key is 2nd | field
                    parts = line.split("|")
                    if len(parts) >= 3:
                        candidate = parts[2].strip().strip("`").strip()
                        if candidate.startswith("bfl_"):
                            return candidate
    raise RuntimeError("BFL API key not found in API_KEYS_MASTER.md")


def _bfl_conn():
    """Fresh HTTPS connection + fresh SSL context per call (LD-137: OP_NO_TICKET)."""
    ctx = ssl.create_default_context()
    ctx.options |= ssl.OP_NO_TICKET
    return http.client.HTTPSConnection("api.bfl.ai", context=ctx, timeout=30)


def build_flux_still_prompt(beat, option_variation=0, bg_ref_path=None):
    """Build a FLUX Kontext still-image prompt for one beat / option slot."""
    speaker = beat.get("speaker", "character")
    emotion  = beat.get("emotion", "neutral")
    scene    = beat.get("scene_notes", "")
    dialogue = beat.get("dialogue_text", "")

    species  = SPECIES_DESC.get(speaker, f"{speaker} character in Pixar 3D animated style")
    emo_desc = EMOTION_VISUAL.get(emotion, "expression calm and attentive, natural pose")

    ctx_parts = []
    if scene:
        ctx_parts.append(scene[:120])
    if dialogue:
        ctx_parts.append(f'Dialogue: "{dialogue[:60]}{"..." if len(dialogue) > 60 else ""}"')
    scene_ctx = ". ".join(ctx_parts) if ctx_parts else "Everdale magical forest setting"

    # When a bg_ref is provided, derive a keyword hint from its filename and
    # replace the generic "forest world" with a directive to match the reference.
    if bg_ref_path:
        stem = os.path.splitext(os.path.basename(bg_ref_path))[0]
        # Convert snake_case filename to readable hint (strip version suffix like _v9)
        hint = re.sub(r'_v\d+$', '', stem).replace('_', ' ').strip()
        world_clause = (
            f"Background environment closely matches the provided reference image "
            f"({hint}). Incorporate its setting, lighting, and atmosphere."
        )
    else:
        world_clause = "Everdale magical forest world"

    variation_suffix = [
        "",
        " Slight variation in head angle and pose.",
        " Slightly warmer lighting, same character and composition.",
    ][option_variation % 3]

    return (
        f"Cartoon character illustration: {species}. "
        f"Character {emo_desc}. "
        f"Scene context: {scene_ctx}. "
        f"Pixar 3D animated style, warm soft lighting, expressive character design, "
        f"medium shot, character centered in frame, cinematic quality. "
        f"{world_clause}, no text, no UI, no watermarks."
        f"{variation_suffix}"
    )


def _build_side_by_side_composite(char_path: str, bg_path: str) -> bytes:
    """
    Returns 1536x1152 JPEG q92 bytes: char cover-fit LEFT (768x1152),
    bg cover-fit RIGHT (768x1152). RGB-flattened (handles alpha PNGs).
    Raises RuntimeError if PIL unavailable — NO silent fallback.
    Composite is built once and reused across 3 FLUX calls per beat.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            f"[BG] PIL/Pillow required for composite but not installed: {exc}"
        )
    import io as _io

    HALF_W, FULL_H = 768, 1152

    def _cover_fit(im, w, h):
        im = im.convert("RGB")
        scale = max(w / im.width, h / im.height)
        rw, rh = int(im.width * scale), int(im.height * scale)
        im = im.resize((rw, rh), Image.LANCZOS)
        left = (im.width - w) // 2
        top  = (im.height - h) // 2
        return im.crop((left, top, left + w, top + h))

    char   = _cover_fit(Image.open(char_path), HALF_W, FULL_H)
    bg     = _cover_fit(Image.open(bg_path),   HALF_W, FULL_H)
    canvas = Image.new("RGB", (HALF_W * 2, FULL_H))
    canvas.paste(char, (0, 0))
    canvas.paste(bg,   (HALF_W, 0))

    buf = _io.BytesIO()
    canvas.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def submit_flux_kontext(prompt, reference_image_path=None, reference_image_bytes=None):
    """
    Submit one FLUX Kontext Pro generation. Returns request_id string.
    Fresh SSL per call (LD-137). Accepts path OR bytes — not both.
    """
    assert not (reference_image_path and reference_image_bytes), \
        "provide reference_image_path OR reference_image_bytes, not both"
    api_key = _bfl_api_key()
    payload = {"prompt": prompt, "output_format": "png"}
    if reference_image_bytes:
        payload["input_image"] = base64.b64encode(reference_image_bytes).decode()
    elif reference_image_path and os.path.exists(reference_image_path):
        with open(reference_image_path, "rb") as f:
            payload["input_image"] = base64.b64encode(f.read()).decode()

    conn = _bfl_conn()
    try:
        conn.request(
            "POST", "/v1/flux-kontext-pro",
            body=json.dumps(payload).encode("utf-8"),
            headers={"x-key": api_key, "Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        data = json.loads(resp.read())
    finally:
        conn.close()

    if "id" not in data:
        raise RuntimeError(f"BFL submit error: {data}")
    return data["id"]


def poll_flux_result(request_id):
    """
    Poll one request. Returns URL string if ready, None if pending,
    raises RuntimeError on failure.
    """
    api_key = _bfl_api_key()
    conn = _bfl_conn()
    try:
        conn.request(
            "GET", f"/v1/get_result?id={request_id}",
            headers={"x-key": api_key},
        )
        resp = conn.getresponse()
        data = json.loads(resp.read())
    finally:
        conn.close()

    status = data.get("status", "")
    if status == "Ready":
        result = data.get("result") or {}
        url = result.get("sample") or result.get("url")
        if not url:
            raise RuntimeError(f"BFL Ready but no URL: {data}")
        return url
    if status in ("Error", "Failed", "Content Moderated"):
        raise RuntimeError(f"BFL {status}: {data}")
    return None  # still pending


def submit_beat_stills(beat):
    """Submit 3 FLUX calls for one beat. Returns [rid0, rid1, rid2].
    If both reference_image and bg_ref_image are set, composites them ONCE
    and reuses the composite bytes across all 3 calls."""
    speaker = beat.get("speaker", "")
    emotion = beat.get("emotion", "")

    # Resolve char ref: per-beat override OR creature master (emotion-mapped)
    override = beat.get("reference_image")
    if override and os.path.exists(override):
        char_ref = override
    else:
        _c = _resolve_creature_ref(speaker, emotion)
        char_ref = os.path.normpath(_c) if _c and os.path.exists(_c) else None

    # Resolve bg ref
    bg_ref = beat.get("bg_ref_image")
    if bg_ref and not os.path.exists(bg_ref):
        print(f"[BG] bg_ref_image path missing on disk, ignoring: {bg_ref}")
        bg_ref = None

    # Build composite ONCE — reused for all 3 FLUX calls
    ref_path = None
    ref_bytes = None
    if char_ref and bg_ref:
        ref_bytes = _build_side_by_side_composite(char_ref, bg_ref)
        print(f"[BG] composite built for {beat.get('beat_id')}: "
              f"{len(ref_bytes)//1024}KB JPEG, "
              f"char={os.path.basename(char_ref)}, bg={os.path.basename(bg_ref)}")
    else:
        ref_path = char_ref  # may be None — same as today

    rids = []
    for i in range(3):
        prompt = build_flux_still_prompt(beat, option_variation=i, bg_ref_path=bg_ref)
        rid = submit_flux_kontext(prompt,
                                  reference_image_path=ref_path,
                                  reference_image_bytes=ref_bytes)
        rids.append(rid)
        time.sleep(0.3)
    return rids


def poll_batch(request_ids, timeout=180):
    """
    Poll a set of request_ids in parallel until all done or timeout.
    Returns { request_id: url_or_None }.
    """
    results = {}
    pending = set(request_ids)
    deadline = time.time() + timeout

    while pending and time.time() < deadline:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(pending))) as pool:
            futures = {pool.submit(poll_flux_result, rid): rid for rid in list(pending)}
            for f in concurrent.futures.as_completed(futures, timeout=30):
                rid = futures[f]
                try:
                    url = f.result()
                    if url:
                        results[rid] = url
                        pending.discard(rid)
                except Exception as e:
                    print(f"[BG] FLUX poll error {rid}: {e}")
                    results[rid] = None
                    pending.discard(rid)
        if pending:
            time.sleep(5)

    for rid in pending:
        results[rid] = None
    return results


# ---------------------------------------------------------------------------
# OpenAI GPT-image-1.5 stills generation  (GPT-1 through GPT-12 locked decisions)
# ---------------------------------------------------------------------------

def _openai_api_key():
    """Read OpenAI key (sk-proj-...) from API_KEYS_MASTER.md."""
    candidates = [
        os.path.join(_PROD_DIR, "API_KEYS_MASTER.md"),
        os.path.join(_PROJECT_DIR, "Production", "API_KEYS_MASTER.md"),
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                if "OpenAI" in line or "sk-proj" in line:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        candidate = parts[2].strip().strip("`").strip()
                        if candidate.startswith("sk-proj-") or candidate.startswith("sk-"):
                            return candidate
    raise RuntimeError("OpenAI API key not found in API_KEYS_MASTER.md")


def _make_gpt_thumb(img_bytes):
    """Generate thumb + gallery b64 from raw PNG bytes. Returns (thumb_b64, gallery_b64)."""
    try:
        from PIL import Image as _PIL
        import io as _io
        img = _PIL.open(_io.BytesIO(img_bytes)).convert("RGB")
        # Rule 6: shortest side >= 600px
        w, h = img.size
        if min(w, h) < 600:
            scale = 600 / min(w, h)
            img = img.resize((int(w * scale), int(h * scale)), _PIL.LANCZOS)
        thumb = img.copy()
        thumb.thumbnail((200, 150), _PIL.LANCZOS)
        buf = _io.BytesIO()
        thumb.convert("RGB").save(buf, "JPEG", quality=72)
        thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        gallery = img.copy()
        gallery.thumbnail((600, 600), _PIL.LANCZOS)
        buf2 = _io.BytesIO()
        gallery.convert("RGB").save(buf2, "JPEG", quality=82)
        gallery_b64 = "data:image/jpeg;base64," + base64.b64encode(buf2.getvalue()).decode()
        return thumb_b64, gallery_b64
    except Exception as e:
        print(f"[GPT] thumb generation failed: {e}")
        return "", ""


# GPT-11/GPT-12: species identity anchors — order matters, early tokens lock identity
_GPT_SPECIES_ANCHOR = {
    "Tessa":   ("small green sea turtle",
                "pale jade shell with darker edge plates, oversized round expressive eyes, "
                "short stubby limbs, no neck wrinkles"),
    "Luna":    ("small owl",
                "dark charcoal-brown feathers, enormous round amber eyes, "
                "white facial disc, compact rounded body"),
    "Benson":  ("small bunny",
                "soft grey fur, long upright ears, wide anxious kind eyes, "
                "small pink nose, white underbelly"),
    "Ember":   ("fox kit",
                "bright auburn-orange fur, white chest and muzzle, "
                "alert triangular ears, bushy tail"),
    "Bork":    ("tiny firefly",
                "translucent wings, round glowing abdomen with warm yellow-green bioluminescence, "
                "tiny compound eyes"),
    "Bramble": ("large bear",
                "mossy dark brown fur with patches of green lichen, "
                "gentle giant proportions, small round ears, soft dark eyes"),
    "Chipper": ("small songbird",
                "warm orange-yellow plumage, round compact body, "
                "tiny black eyes, short orange beak CLOSED"),
    "Cedric":  ("old wizard",
                "long flowing blue-grey robes with star motifs, "
                "long white beard, pointed hat, wise kind expression"),
}

# GPT-12: 3 variations differ ONLY in pose/framing — never in species anchors or style
_GPT_VARIATION_POSE = [
    ("facing the viewer, centered in frame, medium shot",
     "weight evenly balanced, calm open stance"),
    ("slightly turned to three-quarter view, medium shot",
     "weight shifted, one step mid-motion"),
    ("centered in frame, medium-wide shot with more background visible",
     "natural relaxed posture"),
]


def _emotion_to_body_mechanics(emotion_raw, dialogue=""):
    """Convert free-form emotion text to visible body language (GPT-11: body mechanics over adjectives)."""
    e = (emotion_raw or "").lower()
    d = (dialogue or "").lower()
    if any(w in e for w in ["ecstatic", "spinning", "can't contain", "jumping"]):
        return "mid-spin with arms spread wide, head tilted back, eyes wide and crinkled"
    if any(w in e for w in ["shocked", "stunned", "realization"]):
        return "eyes wide open, leaning slightly back, surprised expression"
    if any(w in e for w in ["pained", "embarrassed", "ashamed"]):
        return "shoulders drawn in, eyes averted downward, body angled slightly away"
    if any(w in e for w in ["warm", "gentle", "kind", "tender"]):
        return "leaning slightly forward, gentle open posture, soft warm expression"
    if any(w in e for w in ["excited", "energetic", "bouncing"]):
        return "upright posture, slight forward lean, bright alert expression"
    if any(w in e for w in ["sad", "sorrowful", "tears"]):
        return "slightly hunched, eyes downcast, soft sad expression"
    if any(w in e for w in ["curious", "wondering", "puzzled"]):
        return "head tilted to one side, eyes bright with inquiry"
    if any(w in e for w in ["determined", "brave", "resolve"]):
        return "chin raised, shoulders back, direct forward gaze"
    if any(w in e for w in ["camera", "warmly", "to camera"]):
        return "facing directly forward, warm inviting expression, slight forward lean"
    if any(w in d for w in ["?", "what", "how", "why"]):
        return "quizzical expression, head slightly tilted"
    return "calm attentive expression, natural relaxed posture"


def build_gpt_still_prompt(beat, option_variation=0, bg_path=None):
    """Build GPT still prompt: let reference images define appearance, prompt only directs pose + placement.

    Args:
        beat: dict with speaker / emotion / text fields.
        option_variation: 0/1/2 — minimal per-option framing variation so the 3 options differ.
        bg_path: optional bg ref path; when None the bg sentence is omitted so the model
            does not hallucinate a "reference image 2" that wasn't attached.
    """
    speaker = beat.get("speaker", "Chipper")
    emotion_raw = beat.get("emotion", "")
    dialogue = beat.get("text", "") or beat.get("dialogue_text", "")

    emotion_body = _emotion_to_body_mechanics(emotion_raw, dialogue)

    # Minimal additive variation per option — does not replace the body of the prompt.
    # Restored 2026-04-28 after audit found option_variation arg was being ignored,
    # causing all 3 options to be byte-identical prompts.
    _VARIATIONS = (
        "Framing: medium shot, natural framing.",
        "Framing: slightly tighter shot, gentle angle shift.",
        "Framing: slightly wider shot, subtle pose adjustment.",
    )
    try:
        variation_clause = _VARIATIONS[int(option_variation) % len(_VARIATIONS)]
    except (TypeError, ValueError):
        variation_clause = _VARIATIONS[0]

    # Outfit: injected inline into the character clause so the model treats it as a hard
    # requirement, not a trailing style note.
    _outfit = _CREATURE_OUTFIT.get(speaker, "")
    _outfit_inline = f", {_outfit}" if _outfit else ""

    if bg_path is not None:
        char_clause = (
            f"Put this character into this background scene in the exact same art style. "
            f"Render the character consistent with the reference image — "
            f"including all their accessories and clothing{_outfit_inline}. "
            f"The background scene is the setting; place the character naturally within it."
        )
        bg_clause = ""
    else:
        char_clause = (
            f"Reproduce this exact character from the attached reference image "
            f"in the exact same art style — same design, same accessories, same clothing{_outfit_inline}."
        )
        bg_clause = ""

    # Stage direction extraction: pull (text) patterns from dialogue and inject as additional
    # pose guidance. Only parentheticals 4-50 chars are considered; purely numeric strings
    # (e.g. beat markers like "(1)") are filtered out; max 2 directions used.
    _raw_dirs = re.findall(r'\(([^)]{4,50})\)', dialogue or "")
    _stage_dirs = [d.strip() for d in _raw_dirs if d.strip() and not d.strip().isdigit()]
    if len(_stage_dirs) > 2:
        print(f"[GPT prompt] {len(_stage_dirs)} stage directions found in dialogue — "
              f"using first 2, ignoring: {_stage_dirs[2:]}")
        _stage_dirs = _stage_dirs[:2]
    # Normalize punctuation: strip trailing punct then add single period
    _stage_dirs = [d.rstrip('.,;!') for d in _stage_dirs]

    parts = [
        f"{char_clause}{bg_clause}",
        f"Character pose: {emotion_body}.",
    ]
    # Strip any empty strings from parts list
    parts = [p for p in parts if p.strip()]
    for _d in _stage_dirs:
        parts.append(f"Stage direction: {_d}.")
    parts.append(variation_clause)
    parts.append("PROHIBIT: no text, no watermarks, no second character, no humans, no extra limbs, no logos.")
    return " ".join(parts)


def _openai_responses_image_gen(api_key, char_path, bg_path, prompt, size="1024x1024"):
    """Generate character-faithful image using gpt-4o /v1/responses + image_generation tool.

    Per LD-429 (corrected) + LD-430 (verification cleared 2026-04-27) + LD-431 (this wiring).
    Primary path; on failure submit_gpt_stills falls back to _openai_images_edit_multipart().

    Request shape locked by live probe 2026-04-27 ~20:18 UTC (HTTP 200, 22.4s, 1.3 MB PNG):
        - model='gpt-4o'
        - input=[{role:user, content:[{type:input_text}, {type:input_image, image_url:data-uri}, ...]}]
        - tools=[{type:image_generation, size, quality:'high'}]  (LD-427)
        - tool_choice={type:image_generation}  (REQUIRED — auto chooses text otherwise)

    Response shape (locked from same probe):
        - top-level: status='completed', output=[...]
        - image item: type='image_generation_call', status='completed', result=<base64 PNG>

    Returns raw PNG bytes. Raises RuntimeError on any non-recoverable failure
    (caller catches Exception broadly and falls back to gpt-image-1 path).
    """
    import http.client as _hc
    import ssl as _ssl

    # Build content blocks: prompt text + char ref + (optional) bg ref
    content = [{"type": "input_text", "text": prompt}]
    if char_path and os.path.exists(char_path):
        with open(char_path, "rb") as f:
            char_b64 = base64.b64encode(f.read()).decode()
        content.append({"type": "input_image",
                        "image_url": f"data:image/png;base64,{char_b64}"})
    if bg_path and os.path.exists(bg_path):
        with open(bg_path, "rb") as f:
            bg_b64 = base64.b64encode(f.read()).decode()
        content.append({"type": "input_image",
                        "image_url": f"data:image/png;base64,{bg_b64}"})

    payload = {
        "model": "gpt-4o",
        "input": [{"role": "user", "content": content}],
        "tools": [{"type": "image_generation", "size": size, "quality": "high", "input_fidelity": "high"}],
        "tool_choice": {"type": "image_generation"},
    }

    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}
    body = json.dumps(payload).encode("utf-8")

    # Single bounded retry on 429/5xx/timeout, then propagate to caller's fallback chain.
    # LD-431 Phase 3.5 Critical-2 fix: re-charge budget on retry — caller's upfront
    # charge only covered attempt 1. The retry charge is placed BEFORE the try block
    # so GPTBudgetExceededError propagates out of the for loop directly (cannot be
    # caught by `except Exception` which would otherwise swallow it as a transport
    # error and trigger an infinite retry-against-ceiling).
    last_err = None
    for attempt in (1, 2):
        if attempt > 1:
            _gpt_budget_charge(0.20)
        try:
            ctx = _ssl.create_default_context()
            conn = _hc.HTTPSConnection("api.openai.com", context=ctx, timeout=180)
            try:
                conn.request("POST", "/v1/responses", body=body, headers=headers)
                resp = conn.getresponse()
                status = resp.status
                raw = resp.read()
            finally:
                conn.close()
        except Exception as exc:
            last_err = f"transport error: {type(exc).__name__}: {str(exc)[:120]}"
            if attempt == 1:
                time.sleep(2)
                continue
            raise RuntimeError(f"[GPT-4o] {last_err}")

        # Re-raise on auth/bad-request — fallback with same key would also fail
        if status in (400, 401, 403):
            try:
                err = json.loads(raw).get("error", {})
                code = err.get("code") or err.get("type") or "?"
                msg = (err.get("message") or "")[:200]
            except Exception:
                code = "?"
                msg = ""
            raise RuntimeError(f"[GPT-4o] HTTP {status} {code} {msg}".strip())

        # Bounded retry on transient failures
        if status == 429 or 500 <= status < 600:
            last_err = f"HTTP {status}"
            if attempt == 1:
                time.sleep(2)
                continue
            raise RuntimeError(f"[GPT-4o] {last_err} after retry")

        if status != 200:
            raise RuntimeError(f"[GPT-4o] unexpected HTTP {status}")

        # Parse JSON response
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise RuntimeError(f"[GPT-4o] response parse failed: {type(exc).__name__}")

        # Status check (per probe contract)
        if data.get("status") != "completed":
            reason = (data.get("incomplete_details") or {}).get("reason", "?")
            raise RuntimeError(f"[GPT-4o] status={data.get('status')} reason={reason}")

        # Find the image_generation_call item; defensive on field name
        for item in data.get("output", []):
            if str(item.get("type", "")).lower() != "image_generation_call":
                continue
            if item.get("status") != "completed":
                raise RuntimeError(f"[GPT-4o] image item status={item.get('status')}")
            for fname in ("result", "b64_json", "image", "b64", "data"):
                v = item.get(fname)
                if isinstance(v, str) and len(v) > 1000:
                    print(f"[GPT-4o] ✓ /v1/responses returned image ({fname}, {len(v)//1024}KB b64)")
                    return base64.b64decode(v)
            raise RuntimeError(f"[GPT-4o] image_generation_call has no recognized base64 field "
                               f"(keys={list(item.keys())})")

        # No image item found — model returned text only. Distinct telemetry signal.
        raise RuntimeError("[GPT-4o] empty: no image_generation_call in output")

    # Defensive — should not reach here
    raise RuntimeError(f"[GPT-4o] unreachable: {last_err}")


def _openai_images_edit_multipart(api_key, char_path, bg_path, prompt, size="1024x1024"):
    """Compose character + background using gpt-image-2 /v1/images/edits with multiple ref images.
    Primary: multipart POST with char_path + bg_path as image[] inputs (reference-guided).
    Fallback: /v1/images/generations text-only if no refs available."""
    import http.client as _hc
    import ssl as _ssl

    def _post_json(path_url, payload):
        ctx = _ssl.create_default_context()
        conn = _hc.HTTPSConnection("api.openai.com", context=ctx, timeout=120)
        try:
            conn.request("POST", path_url,
                body=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
            resp = conn.getresponse()
            return json.loads(resp.read())
        finally:
            conn.close()

    # ── Primary path: /v1/images/edits multipart with gpt-image-2 + reference images ──
    if char_path and os.path.exists(char_path):
        boundary = "MINDFULNEST_GPT_BOUNDARY"

        def _field(name, value):
            return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()

        def _file_field(name, path):
            data = open(path, "rb").read()
            fname = os.path.basename(path)
            ext = os.path.splitext(fname)[1].lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fname}\"\r\nContent-Type: {mime}\r\n\r\n").encode() + data + b"\r\n"

        body = b""
        body += _field("model", "gpt-image-2")
        body += _file_field("image[]", char_path)      # char ref first (high-richness slot)
        if bg_path and os.path.exists(bg_path):
            body += _file_field("image[]", bg_path)    # bg ref second
        body += _field("prompt", prompt)
        body += _field("n", "1")
        body += _field("size", size)
        body += _field("quality", "high")
        body += f"--{boundary}--\r\n".encode()

        ctx = _ssl.create_default_context()
        conn = _hc.HTTPSConnection("api.openai.com", context=ctx, timeout=360)
        try:
            conn.request("POST", "/v1/images/edits", body=body, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            })
            resp = conn.getresponse()
            edit_data = json.loads(resp.read())
        finally:
            conn.close()

        if "data" in edit_data:
            print(f"[GPT] ✓ /images/edits with {1 + bool(bg_path and os.path.exists(bg_path))} ref(s)")
            return base64.b64decode(edit_data["data"][0]["b64_json"])
        print(f"[GPT] /images/edits failed ({edit_data.get('error',{}).get('message','?')[:80]}), falling back to text generation")

    # ── Fallback: gpt-image-2 text-only via /v1/images/generations ──
    gen_data = _post_json("/v1/images/generations", {
        "model": "gpt-image-2",
        "prompt": prompt,
        "n": 1,
        "size": size,
    })
    if "data" not in gen_data:
        raise RuntimeError(f"OpenAI error: {gen_data}")
    print("[GPT] ✓ /images/generations text-only fallback")
    return base64.b64decode(gen_data["data"][0]["b64_json"])


def submit_gpt_stills(beat, num_options=3):
    """Synchronous GPT still generation via multipart /v1/images/edits.
    Returns list of result dicts, one per option.
    Each dict: {local_path, key, filename, source, cost_usd, thumb_b64, gallery_b64}
    or {error, key, source} on failure. Run in a thread for non-blocking behavior."""
    api_key = _openai_api_key()
    beat_id = beat.get("beat_id", "unknown")
    speaker = beat.get("speaker", "")
    emotion = beat.get("emotion", "")

    # Resolve character reference (per-beat override → creature master, emotion-mapped)
    override = beat.get("reference_image")
    if override and os.path.exists(override):
        char_ref = override
    else:
        _c = _resolve_creature_ref(speaker, emotion)
        char_ref = os.path.normpath(_c) if _c and os.path.exists(_c) else None
    if not char_ref:
        raise RuntimeError(
            f"[GPT] No character reference found for speaker '{speaker}'. "
            f"Check Character_Assets/{speaker.lower()}_reference_master.png"
        )

    # GPT-6: bg ref slot unchanged — Kim always drags manually, no auto-detect
    bg_ref = beat.get("bg_ref_image")
    if bg_ref and not os.path.exists(bg_ref):
        print(f"[GPT] bg_ref_image missing on disk, ignoring: {bg_ref}")
        bg_ref = None

    os.makedirs(BG_STILLS_DIR, exist_ok=True)
    results = []

    # Per LD-440 + A/B test 2026-04-28:
    # PRIMARY: gpt-image-2 /v1/images/edits — $0.08, ~215s, wins on character fidelity + bg accuracy.
    # FALLBACK: gpt-4o /v1/responses + image_generation tool — $0.20, fires on gpt-image-2 failure.
    # Per-beat short-circuit: once primary fails with systemic error, options 2+ skip to fallback.
    primary_disabled_for_beat = False

    # Extract parenthetical stage directions from dialogue (e.g. "(owl is appropriate size for nest)")
    # Same logic as build_gpt_still_prompt — up to 2 directions, 4-50 chars, non-numeric.
    _dialogue_text = beat.get('dialogue_text', '') or ''
    _raw_dirs = re.findall(r'\(([^)]{4,50})\)', _dialogue_text)
    _stage_dirs = [d.strip().rstrip('.,;!') for d in _raw_dirs
                   if d.strip() and not d.strip().isdigit()][:2]
    _stage_dir_suffix = (" " + " ".join(f"Also: {d}." for d in _stage_dirs)) if _stage_dirs else ""

    for opt_idx in range(num_options):
        # Responses API path uses a simple direct prompt — gpt-4o reasons about the images itself.
        # Don't number "reference image 1/2" — just say what each attached image is.
        if bg_ref:
            _responses_prompt = (
                f"Put this character into this background scene in the exact same art style. "
                f"Render the character consistent with the reference image — "
                f"including all their accessories and clothing. "
                f"The background scene is the setting; place the character naturally within it. "
                f"Pose: {_emotion_to_body_mechanics(beat.get('emotion',''), beat.get('dialogue_text',''))}."
                f"{_stage_dir_suffix}"
            )
        else:
            _responses_prompt = (
                f"Reproduce this exact character from the attached reference image "
                f"in the exact same art style — same design, same accessories, same clothing. "
                f"Pose: {_emotion_to_body_mechanics(beat.get('emotion',''), beat.get('dialogue_text',''))}."
                f"{_stage_dir_suffix}"
            )
        prompt = build_gpt_still_prompt(beat, option_variation=opt_idx, bg_path=bg_ref)
        key = f"bg_{beat_id}_gpt_opt{opt_idx}"
        source_label = None
        cost_usd = None
        img_bytes = None
        primary_err = None

        # ── Primary: gpt-image-2 /v1/images/edits ──
        primary_latency_ms = 0
        if not primary_disabled_for_beat:
            try:
                _gpt_budget_charge(0.08)
                _t0 = time.time()
                img_bytes = _openai_images_edit_multipart(api_key, char_ref, bg_ref, prompt)
                primary_latency_ms = int((time.time() - _t0) * 1000)
                source_label = "gpt-image-2"
                cost_usd = 0.08
            except GPTBudgetExceededError:
                raise
            except Exception as e:
                _t0_val = locals().get("_t0", time.time())
                primary_latency_ms = int((time.time() - _t0_val) * 1000)
                primary_err = str(e)[:160]
                msg = primary_err.lower()
                if (re.search(r"http\s5\d\d", msg) or "http 429" in msg or "transport error" in msg):
                    primary_disabled_for_beat = True
                print(f"[GPT] {beat_id} opt{opt_idx} primary (gpt-image-2) failed ({primary_err}); "
                      f"falling back to gpt-4o")

        # ── Fallback: gpt-4o /v1/responses + image_generation tool ──
        if img_bytes is None:
            try:
                _gpt_budget_charge(0.20)
                _t0 = time.time()
                img_bytes = _openai_responses_image_gen(api_key, char_ref, bg_ref, _responses_prompt)
                source_label = "gpt-4o-fallback" if primary_err else "gpt-4o-responses"
                cost_usd = 0.20
                if primary_err:
                    _gpt_log_fallback_to_directus(
                        beat_id=beat_id, opt_idx=opt_idx,
                        primary_err=primary_err, fell_back_to=source_label,
                        latency_ms=primary_latency_ms,
                    )
            except GPTBudgetExceededError:
                raise
            except Exception as e:
                msg = f"{primary_err} | gpt-4o: {str(e)[:160]}" if primary_err else str(e)[:160]
                print(f"[GPT] ✗ {beat_id} opt{opt_idx}: {msg}")
                results.append({"error": msg, "key": key, "source": "both-paths-failed"})
                time.sleep(0.5)
                continue

        # Success on either path — write file + thumbnail + result dict
        try:
            ts = int(time.time())
            filename = f"bg_{beat_id}_gpt_opt{opt_idx}_{ts}.png"
            local_path = os.path.join(BG_STILLS_DIR, filename)
            with open(local_path, "wb") as out:
                out.write(img_bytes)
            thumb_b64, gallery_b64 = _make_gpt_thumb(img_bytes)
            print(f"[GPT] ✓ {beat_id} opt{opt_idx} via {source_label}: {filename}")
            results.append({
                "local_path": local_path,
                "key": key,
                "filename": filename,
                "source": source_label,
                "cost_usd": cost_usd,
                "thumb_b64": thumb_b64,
                "gallery_b64": gallery_b64,
            })
        except Exception as e:
            print(f"[GPT] ✗ {beat_id} opt{opt_idx} write/thumb failed: {e}")
            results.append({"error": str(e), "key": key, "source": source_label})
        time.sleep(0.5)

    return results


def process_still_image(img_bytes, beat_id, option_idx):
    """
    Process a downloaded still: Rule 6 upscale + thumbnail.
    Returns (filename, local_path, delivery_bytes, thumb_b64, gallery_b64).
    """
    filename   = f"bg_{beat_id}_opt{option_idx}.png"
    local_path = os.path.join(BG_STILLS_DIR, filename)
    os.makedirs(BG_STILLS_DIR, exist_ok=True)

    with open(local_path, "wb") as f:
        f.write(img_bytes)

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = img.size
        # Rule 6: shortest side ≥ 600px
        if min(w, h) < 600:
            scale = 600 / min(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        # Thumbnail
        thumb = img.copy()
        thumb.thumbnail((256, 192), Image.LANCZOS)
        tbuf = io.BytesIO()
        thumb.save(tbuf, "PNG")
        thumb_b64 = "data:image/png;base64," + base64.b64encode(tbuf.getvalue()).decode()
        gallery_b64 = "data:image/png;base64," + base64.b64encode(img_bytes).decode()
    except ImportError:
        b64 = "data:image/png;base64," + base64.b64encode(img_bytes).decode()
        thumb_b64 = gallery_b64 = b64

    return filename, local_path, img_bytes, thumb_b64, gallery_b64


def process_crop(crop_bytes):
    """
    Apply Rule 6 + Rule 6.2 to a crop.
    Returns (delivery_bytes, width, height, thumb_b64, gallery_b64).
    Rule 6:   shortest side ≥ 600px
    Rule 6.2: delivery = WebP q80, long-edge ≤ 1280px
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(crop_bytes)).convert("RGB")
        w, h = img.size
        if min(w, h) < 600:
            scale = 600 / min(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size
        if max(w, h) > 1280:
            scale = 1280 / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=80)
        delivery = buf.getvalue()
        # Thumbnail 4:3
        thumb = img.copy()
        thumb.thumbnail((256, 192), Image.LANCZOS)
        tbuf = io.BytesIO()
        thumb.save(tbuf, "PNG")
        thumb_b64  = "data:image/png;base64,"  + base64.b64encode(tbuf.getvalue()).decode()
        gallery_b64 = "data:image/webp;base64," + base64.b64encode(delivery).decode()
        return delivery, w, h, thumb_b64, gallery_b64
    except ImportError:
        b64 = "data:image/png;base64," + base64.b64encode(crop_bytes).decode()
        return crop_bytes, 0, 0, b64, b64


# ============================================================================
# Stitch Groups + Local Animation Methods (added 2026-04-23)
# Adds: sidecar migration, groups CRUD, normalize/assemble, local renderers,
# capability probe. Named to match existing conventions (_sidecar_lock,
# read_sidecar, write_sidecar).
# ============================================================================

# Aliases for spec compatibility (spec uses _SIDECAR_LOCK / _load_sidecar / _save_sidecar)
_SIDECAR_LOCK = _sidecar_lock
_SIDECAR_PATH = BG_SIDECAR_PATH


def _load_sidecar():
    return read_sidecar()


def _save_sidecar(data):
    write_sidecar(data)


def _utc_now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_group_id() -> str:
    return "grp_" + uuid.uuid4().hex[:8]


def normalize_still_insert_approval_status(beat: dict) -> bool:
    """Demote legacy still renders that were auto-marked approved on build.

    Explicit operator approval via **Approve still for stitch** sets
    ``kling_o3_still_stitch_approved`` — never demote those beats.
    """
    if not beat_is_still_insert(beat):
        return False
    if beat.get("kling_o3_still_stitch_approved"):
        return False
    if str(beat.get("kling_o3_status") or "") != "approved":
        return False
    still_sources = (
        "still_insert_static_hold",
        "still_insert_ken_burns",
        "still_insert_kling_idle",
    )
    active_path = str(beat.get("kling_o3_video_path") or "")
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        if opt.get("source") in still_sources and str(opt.get("video_path") or "") == active_path:
            beat["kling_o3_status"] = "still_rendered"
            if beat.get("status") == "approved":
                beat["status"] = "draft"
            return True
    if active_path and "_still_insert_" in active_path:
        beat["kling_o3_status"] = "still_rendered"
        if beat.get("status") == "approved":
            beat["status"] = "draft"
        return True
    return False


def heal_still_insert_option_keys(beat: dict) -> bool:
    """Ensure every still-insert option row has a stable ``key`` for Approve still UI."""
    if not beat_is_still_insert(beat):
        return False
    beat_id = str(beat.get("beat_id") or "beat")
    changed = False
    for i, opt in enumerate(beat.get("kling_o3_options") or []):
        if not isinstance(opt, dict) or opt.get("key"):
            continue
        vp = str(opt.get("video_path") or "").strip()
        if not vp:
            continue
        stem = Path(vp).stem
        opt["key"] = stem or f"{beat_id}_still_{i}"
        changed = True
    return changed


def ensure_sidecar_schema_defaults(sidecar: dict) -> dict:
    """Lightweight read-path defaults — no ffprobe, registry, or prompt heals."""
    sidecar.setdefault("groups", {})
    for arc in sidecar.get("arcs", {}).values():
        for seg in arc.get("segments", {}).values():
            for beat in seg.get("beats", []):
                beat.setdefault("animation_method", "kling")
                beat.setdefault("group_id", None)
                beat.setdefault("group_order", None)
                beat.setdefault("accepted_video_path", None)
                beat.setdefault("local_render_params", None)
                beat.setdefault("reference_image", None)
                beat.setdefault("bg_ref_image", None)
                heal_still_insert_option_keys(beat)
    return sidecar


def _migrate_sidecar(
    sidecar: dict,
    *,
    heal_trim: bool = True,
    heavy_heal: bool = True,
) -> dict:
    """Add new fields to old sidecars without breaking existing state."""
    ensure_sidecar_schema_defaults(sidecar)
    if heal_trim:
        for arc in sidecar.get("arcs", {}).values():
            for seg in arc.get("segments", {}).values():
                for beat in seg.get("beats", []):
                    heal_invalid_kling_o3_trim(beat)
    if not heavy_heal:
        if sidecar.get("schema_version", 1) < 3:
            sidecar["schema_version"] = max(int(sidecar.get("schema_version", 1)), 3)
        return sidecar
    if sidecar.get("schema_version", 1) < 2:
        sidecar["schema_version"] = 2
    if sidecar.get("schema_version", 1) < 3:
        from beat_extract_policy import humanize_kling_body_parts_on_beat

        healed = 0
        for arc in sidecar.get("arcs", {}).values():
            for seg in arc.get("segments", {}).values():
                for beat in seg.get("beats", []):
                    if humanize_kling_body_parts_on_beat(beat):
                        healed += 1
        sidecar["schema_version"] = 3
        if healed:
            sidecar.setdefault("migration_notes", []).append(
                f"v3: humanized Kling gesture body parts on {healed} beat(s)",
            )
    from beat_extract_policy import (
        humanize_kling_body_parts_on_beat,
        humanize_kling_body_parts_on_plan_row,
    )

    def _migrate_skip_beat_canonical(beat: dict) -> bool:
        """Skip canonical heals that rewrite operator-owned beat fields."""
        if beat_has_stored_kling_prompt(beat):
            return True
        if o3_prompt_box_law_active(beat):
            return True
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id:
            return False
        try:
            from o3_job_status_contract import beat_o3_operator_busy

            ev = event_dir_for_beat_id(beat_id)
            return beat_o3_operator_busy(beat, ev)
        except Exception:
            return True

    for arc in sidecar.get("arcs", {}).values():
        for seg in arc.get("segments", {}).values():
            for beat in seg.get("beats", []):
                if _migrate_skip_beat_canonical(beat):
                    continue
                heal_avatar_pro_poisoned_o3_prompt(beat)
                humanize_kling_body_parts_on_beat(beat)
                from beat_extract_policy import heal_beat_kling_o3_prompt_event1_shape

                heal_beat_kling_o3_prompt_event1_shape(beat)
            draft = seg.get("beat_plan_draft") or {}
            for row in draft.get("beats_plan") or []:
                humanize_kling_body_parts_on_plan_row(row)
            for beat in seg.get("beats", []):
                if _migrate_skip_beat_canonical(beat):
                    continue
                heal_avatar_pro_poisoned_o3_prompt(beat)
                if not beat.get("reference_image_locked") and not beat_is_still_insert(beat):
                    align_beat_reference_to_element(beat)
                elif beat_is_still_insert(beat) and beat.get("reference_image"):
                    # Still inserts use library still in option 1 — not Element @Image1.
                    beat.pop("reference_image", None)
                char_path = resolve_beat_char_ref_path(beat) or ""
                locked_lib = (
                    beat.get("reference_image_locked")
                    and char_path
                    and _is_event_library_char_ref(char_path)
                    and os.path.isfile(char_path)
                )
                sync_element_char_ref_status(beat, heal_mismatch=not locked_lib)
                if beat.get("element_char_ref_ok") is False:
                    reconcile_refer_if_pose_hash_matches(beat, wavespeed_key=None)
                    sync_element_char_ref_status(beat, heal_mismatch=not locked_lib)
                heal_kling_o3_stored_duration(beat)
                heal_element_bound_voice_prompt(beat)
                heal_spoken_staging_in_voice_prompt(beat)
                heal_o3_element_submit_prompt(beat)
                heal_legacy_kling_o3_prompt_v2_shape(beat)
                if _speaker_has_element_bound_voice(str(beat.get("speaker") or "")):
                    prune_stale_o3_voice_options(beat, str(beat.get("speaker") or ""))
    for arc_key, arc in sidecar.get("arcs", {}).items():
        for seg_key, seg in arc.get("segments", {}).items():
            m = re.match(r"^event_(\d+)_(\w+)$", seg_key or "")
            if not m:
                continue
            event_id, phase = m.group(1), m.group(2)
            if phase not in ("pre", "intro"):
                continue
            guide = _infer_teleport_intro_guide(sidecar, seg_key)
            for beat in seg.get("beats", []):
                if _migrate_skip_beat_canonical(beat):
                    continue
                role = beat.get("intro_beat_role")
                if role == INTRO_BEAT_ROLE_SEMI_CANONICAL:
                    _apply_intro_canonical_beat_defaults(
                        beat, event_id, phase, role,
                        guide=guide, sidecar=sidecar, segment_key=seg_key,
                    )
                elif role == INTRO_BEAT_ROLE_CANONICAL_MIRROR:
                    hydrate_intro_canonical_mirror_beat(
                        beat, event_id, phase,
                        sidecar=sidecar, segment_key=seg_key,
                    )
            # Export trim is metadata-only — seed even when prompt heals are skipped.
            for beat in seg.get("beats", []):
                if beat.get("intro_beat_role") == INTRO_BEAT_ROLE_CANONICAL_MIRROR:
                    seed_canonical_intro_tail_export_trim(
                        beat, guide=guide, sidecar=sidecar, segment_key=seg_key,
                    )
    migration_warnings = []
    for arc_key, arc in sidecar.get("arcs", {}).items():
        for seg_key, seg in arc.get("segments", {}).items():
            for beat in seg.get("beats", []):
                if beat.get("status") == "accepted" and not beat.get("accepted_video_path"):
                    key = beat.get("accepted_image_key")
                    if key:
                        for opt in beat.get("flux_options", []) or []:
                            if not opt:
                                continue
                            if opt.get("key") == key and opt.get("filename"):
                                beat["accepted_video_path"] = opt["filename"]
                                break
                        if not beat.get("accepted_video_path"):
                            migration_warnings.append(f"{beat.get('beat_id','?')}: accepted but no video path found")
    if migration_warnings:
        # C4-10 fix (LD-pending MIGRATION_WARNINGS_DEDUP_V1, 2026-05-20):
        # _migrate_sidecar runs on EVERY sidecar read, and each run appended
        # duplicate warnings to the list. Pre-fix, the field had grown to
        # 4,125 entries with only 19 unique values. Use a stable order-
        # preserving dedup so the new warnings join the existing set without
        # introducing duplicates.
        _existing = sidecar.setdefault("migration_warnings", [])
        _seen = set(_existing)
        for _w in migration_warnings:
            if _w not in _seen:
                _existing.append(_w)
                _seen.add(_w)
        # Self-heal pre-existing duplicate bloat from prior versions of this
        # function: rebuild _existing as a unique-stable list if any dupes
        # remain after the additive merge above.
        if len(_existing) != len(set(_existing)):
            _uniq: list[str] = []
            _seen2: set[str] = set()
            for _w in _existing:
                if _w not in _seen2:
                    _uniq.append(_w)
                    _seen2.add(_w)
            sidecar["migration_warnings"] = _uniq
    try:
        from operator_workbench_contract import migrate_operator_workbench_sidecar

        migrate_operator_workbench_sidecar(sidecar)
    except Exception as exc:
        print(f"[migrate] operator workbench heal skipped: {exc}", flush=True)
    return sidecar


def _load_sidecar_migrated():
    """Read sidecar and run migration. Safe to call on every read path."""
    sc = read_sidecar()
    _migrate_sidecar(sc)
    return sc


def _index_beats(sidecar, arc_number) -> dict:
    """Return {beat_id: beat_dict_ref} across all segments of an arc."""
    out = {}
    arc = sidecar.get("arcs", {}).get(f"arc_{arc_number}", {})
    for seg_key, seg in arc.get("segments", {}).items():
        for b in seg.get("beats", []):
            out[b["beat_id"]] = b
    return out


def _compute_group_status(sidecar, group) -> str:
    beat_ids = group.get("beat_ids_ordered", [])
    if not beat_ids:
        return "empty"
    if group.get("status") in ("assembling", "assembled", "error"):
        return group["status"]
    arc_n = group.get("arc_number", 1)
    beats_by_id = _index_beats(sidecar, arc_n)
    for bid in beat_ids:
        b = beats_by_id.get(bid)
        if not b:
            return "pending"
        if b.get("status") != "accepted":
            return "pending"
        if not b.get("accepted_video_path"):
            return "pending"
    return "ready"


def create_group(sidecar, name, arc_number, beat_ids):
    gid = _new_group_id()
    now = _utc_now_iso()
    beats_by_id = _index_beats(sidecar, arc_number)
    for bid in beat_ids:
        b = beats_by_id.get(bid)
        if b and b.get("group_id") and b["group_id"] != gid:
            raise ValueError(f"beat_id {bid} already in group {b['group_id']}")
    sidecar.setdefault("groups", {})[gid] = {
        "group_id": gid,
        "name": name,
        "arc_number": arc_number,
        "beat_ids_ordered": list(beat_ids),
        "assembled_clip_path": None,
        "status": "empty",
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    for idx, bid in enumerate(beat_ids):
        b = beats_by_id.get(bid)
        if b:
            b["group_id"] = gid
            b["group_order"] = idx
    sidecar["groups"][gid]["status"] = _compute_group_status(sidecar, sidecar["groups"][gid])
    return gid


def get_group(sidecar, group_id):
    return sidecar.get("groups", {}).get(group_id)


def list_groups(sidecar, arc_number):
    return [g for g in sidecar.get("groups", {}).values()
            if g.get("arc_number") == arc_number]


def delete_group(sidecar, group_id):
    g = sidecar.get("groups", {}).pop(group_id, None)
    if not g:
        return False
    beats_by_id = _index_beats(sidecar, g.get("arc_number", 1))
    for bid in g.get("beat_ids_ordered", []):
        b = beats_by_id.get(bid)
        if b:
            b["group_id"] = None
            b["group_order"] = None
    return True


def update_group_order(sidecar, group_id, beat_ids_ordered):
    g = sidecar["groups"][group_id]
    g["beat_ids_ordered"] = list(beat_ids_ordered)
    g["updated_at"] = _utc_now_iso()
    beats_by_id = _index_beats(sidecar, g["arc_number"])
    for idx, bid in enumerate(beat_ids_ordered):
        b = beats_by_id.get(bid)
        if b:
            b["group_order"] = idx
    g["status"] = _compute_group_status(sidecar, g)
    return g["status"]


# ---- Normalization + assembly ----

NORMALIZE_ARGS = [
    "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
    "-s", "1280x720", "-r", "24",
    "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
    "-movflags", "+faststart",
]


def _normalize_clip(src: Path, dst: Path):
    cmd = ["ffmpeg", "-y", "-i", str(src)] + NORMALIZE_ARGS + [str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg normalize failed: {r.stderr[-500:]}")


def _ffprobe_ok(path: Path) -> bool:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name,width,height",
             "-of", "json", str(path)],
            capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return r.returncode == 0 and '"codec_name"' in r.stdout


def _ffprobe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True)
    except FileNotFoundError:
        return 0.0
    if r.returncode != 0:
        return 0.0
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def assemble_group(sidecar, group_id, output_dir):
    g = sidecar["groups"][group_id]
    status = _compute_group_status(sidecar, g)
    if status != "ready":
        raise ValueError(f"group not ready: status={status}")
    g["status"] = "assembling"
    g["error_message"] = None
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    norm_dir = output_dir / "normalized"
    norm_dir.mkdir(exist_ok=True)
    beats_by_id = _index_beats(sidecar, g["arc_number"])
    normalized_paths = []
    try:
        for idx, bid in enumerate(g["beat_ids_ordered"]):
            b = beats_by_id.get(bid)
            if not b:
                raise ValueError(f"beat {bid} not found in sidecar")
            src = Path(b["accepted_video_path"])
            if not src.exists():
                raise FileNotFoundError(f"beat {bid} video missing: {src}")
            dst = norm_dir / f"{group_id}_{idx:02d}_{bid}.mp4"
            _normalize_clip(src, dst)
            if not _ffprobe_ok(dst):
                raise RuntimeError(f"normalized clip failed ffprobe: {dst}")
            normalized_paths.append(dst)
        list_file = output_dir / f"{group_id}_concat.txt"
        list_file.write_text("\n".join(f"file '{p}'" for p in normalized_paths))
        final_path = output_dir / f"{group_id}_assembled.mp4"
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", str(list_file), "-c", "copy", "-movflags", "+faststart",
               str(final_path)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {r.stderr[-500:]}")
        if not _ffprobe_ok(final_path):
            raise RuntimeError("assembled file failed ffprobe")
        g["assembled_clip_path"] = str(final_path)
        g["status"] = "assembled"
        g["updated_at"] = _utc_now_iso()
        return str(final_path), _ffprobe_duration(final_path), final_path.stat().st_size
    except Exception as e:
        g["status"] = "error"
        g["error_message"] = str(e)[:500]
        raise


# ---- Local animation runners ----

_LOCAL_STILLS_DIR = Path(_PROD_DIR) / "beat_generator_stills" / "local_renders"


def run_magic_compositor(beat, background_path, path_pts, style, duration, fps=24):
    """Run MagicCompositor on a still background. Returns {video_path, preview_path}."""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from magic_compositor import MagicCompositor, STYLES
        from magic_render_contract import production_magic_compositor_kwargs
    except ImportError as e:
        raise RuntimeError(f"magic_compositor unavailable: {e}")
    if style not in STYLES:
        raise ValueError(f"style not approved — only {list(STYLES.keys())} allowed")
    out_dir = _LOCAL_STILLS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    mc = MagicCompositor(
        background_path=background_path,
        path_pts=path_pts,
        style=style,
        duration=duration,
        fps=fps,
        output_dir=str(out_dir),
        label=f"{beat['beat_id']}_magic_{ts}",
        **production_magic_compositor_kwargs(),
    )
    preview_path = mc.render_preview()
    video_path = mc.render_ld469_on_background()
    actual_dur = _ffprobe_duration(Path(video_path))
    if abs(actual_dur - duration) > 0.2:
        raise RuntimeError(f"magic_compositor output duration {actual_dur:.2f}s, expected {duration:.2f}s ±0.2s")
    beat["local_render_params"] = {
        "method": "magic_compositor",
        "background_path": background_path,
        "path_pts": path_pts,
        "style": style,
        "duration": duration,
    }
    return {"video_path": video_path, "preview_path": preview_path}


def _ken_burns_zoompan_vf(
    *,
    pan_x_pct: float,
    pan_y_pct: float,
    zoom_start: float,
    zoom_end: float,
    total_frames: int,
    out_w: int = 1280,
    out_h: int = 720,
    fps: int = 24,
    duration_s: float | None = None,
) -> str:
    """Smooth Ken Burns vf — delegates to ken_burns_render (all events / still paths)."""
    try:
        from tools import ken_burns_render as kb
    except ImportError:
        import ken_burns_render as kb  # type: ignore

    if duration_s is None:
        duration_s = total_frames / max(fps, 1)
    return kb.ken_burns_smooth_vf(
        pan_x_pct=pan_x_pct,
        pan_y_pct=pan_y_pct,
        zoom_start=zoom_start,
        zoom_end=zoom_end,
        duration_s=float(duration_s),
        out_w=out_w,
        out_h=out_h,
        fps=fps,
    )


def run_ken_burns(
    beat,
    still_path,
    pan_x_pct,
    pan_y_pct,
    zoom_start,
    zoom_end,
    duration,
    fps=24,
    *,
    out_path: str | Path | None = None,
):
    out_dir = _LOCAL_STILLS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    video_path = str(out_path) if out_path else str(out_dir / f"{beat['beat_id']}_kenburns_{ts}.mp4")
    total_frames = max(1, int(duration * fps))
    zoompan = _ken_burns_zoompan_vf(
        pan_x_pct=pan_x_pct,
        pan_y_pct=pan_y_pct,
        zoom_start=zoom_start,
        zoom_end=zoom_end,
        total_frames=total_frames,
        fps=fps,
        duration_s=float(duration),
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", still_path,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-vf", zoompan, "-t", str(duration),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", str(fps), "-movflags", "+faststart",
        "-shortest", "-c:a", "aac", "-b:a", "128k",
        video_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ken_burns ffmpeg failed: {r.stderr[-500:]}")
    actual_dur = _ffprobe_duration(Path(video_path))
    if abs(actual_dur - duration) > 0.2:
        raise RuntimeError(f"ken_burns output duration {actual_dur:.2f}s, expected {duration:.2f}s ±0.2s")
    if out_path is None:
        beat["local_render_params"] = {
            "method": "ken_burns", "still_path": still_path,
            "pan_x_pct": pan_x_pct, "pan_y_pct": pan_y_pct,
            "zoom_start": zoom_start, "zoom_end": zoom_end, "duration": duration,
        }
    return {"video_path": video_path, "preview_path": still_path}


def run_static_hold(beat, still_path, duration, fps=24, *, out_path: str | Path | None = None):
    out_dir = _LOCAL_STILLS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    video_path = str(out_path) if out_path else str(out_dir / f"{beat['beat_id']}_static_{ts}.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", still_path,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-s", "1280x720", "-r", str(fps), "-movflags", "+faststart",
        "-shortest", "-c:a", "aac", "-b:a", "128k",
        video_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"static_hold ffmpeg failed: {r.stderr[-500:]}")
    actual_dur = _ffprobe_duration(Path(video_path))
    if abs(actual_dur - duration) > 0.2:
        raise RuntimeError(f"static_hold duration {actual_dur:.2f}s, expected {duration:.2f}s ±0.2s")
    if out_path is None:
        beat["local_render_params"] = {
            "method": "static_hold", "still_path": still_path, "duration": duration,
        }
    return {"video_path": video_path, "preview_path": still_path}


def resolve_still_source_abs_path(beat: dict) -> Path | None:
    """PNG/JPEG still for still_insert Ken Burns — library drop, char ref, or BG ref."""
    lib = beat.get("accepted_library_ref") or {}
    if isinstance(lib, dict):
        ap = str(lib.get("abs_path") or "").strip()
        if ap and Path(ap).is_file():
            return Path(ap).resolve()
    for opt in beat.get("gpt_options") or []:
        if not isinstance(opt, dict):
            continue
        for key in ("local_path", "abs_path"):
            ap = str(opt.get(key) or "").strip()
            if ap and Path(ap).is_file():
                return Path(ap).resolve()
    for ref_key in ("reference_image", "bg_ref_image", "start_frame_image", "end_frame_image"):
        ref = beat.get(ref_key) or {}
        if isinstance(ref, dict):
            ap = str(ref.get("abs_path") or "").strip()
            if ap and Path(ap).is_file():
                return Path(ap).resolve()
    for opt in beat.get("flux_options") or []:
        if not isinstance(opt, dict):
            continue
        for key in ("local_path", "abs_path"):
            ap = str(opt.get(key) or "").strip()
            if ap and Path(ap).is_file():
                return Path(ap).resolve()
    return None


def beat_is_still_insert(beat: dict) -> bool:
    return (
        str(beat.get("pipeline") or "") == "still_insert"
        or str(beat.get("beat_render_mode") or "") == "still_insert"
    )


def resolve_kling_o3_video_on_disk(
    beat: dict,
    event_dir: str | Path,
) -> Path | None:
    """Resolved ``kling_o3_video_path`` when the clip exists under event_dir or abs."""
    vp = (beat.get("kling_o3_video_path") or "").strip()
    if not vp:
        return None
    event_dir = Path(event_dir)
    p = Path(vp)
    if p.is_file():
        return p.resolve()
    rel = event_dir / vp
    if rel.is_file():
        return rel.resolve()
    by_name = event_dir / p.name
    if by_name.is_file():
        return by_name.resolve()
    return None


PIPELINE_MODE_STILL = "still_insert"
PIPELINE_MODE_O3 = "kling_o3_omni"
VALID_PIPELINE_MODES = frozenset({PIPELINE_MODE_STILL, PIPELINE_MODE_O3})
O3_GENERATE_MODE_VOICE_FIRST = "voice_first"
O3_GENERATE_MODE_ELEMENT_NATIVE = "element_native"
O3_GENERATE_MODE_AVATAR = "avatar_pro"
VALID_O3_GENERATE_MODES = frozenset({
    O3_GENERATE_MODE_VOICE_FIRST,
    O3_GENERATE_MODE_ELEMENT_NATIVE,
    O3_GENERATE_MODE_AVATAR,
})
VALID_GENERATION_MODES = frozenset({
    PIPELINE_MODE_STILL,
    O3_GENERATE_MODE_VOICE_FIRST,
    O3_GENERATE_MODE_ELEMENT_NATIVE,
    O3_GENERATE_MODE_AVATAR,
})
O3_SPEAK_GENERATE_MODES = frozenset({
    O3_GENERATE_MODE_VOICE_FIRST,
    O3_GENERATE_MODE_ELEMENT_NATIVE,
    O3_GENERATE_MODE_AVATAR,
})

O3_OPTION_SOURCE_VOICE_FIRST = "kling_o3_voice_video"
O3_OPTION_SOURCE_ELEMENT = "kling_o3_element_native_voice"
O3_OPTION_SOURCE_AVATAR = "kling_o3_avatar_pro"
O3_OPTION_SOURCE_STILL = frozenset({
    "still_insert_static_hold",
    "still_insert_ken_burns",
    "still_insert_kling_idle",
})
O3_OPTION_SOURCE_POV_MOTION = "o3_pov_motion_i2v"
O3_OPTION_SOURCE_ANIMATION = frozenset({
    O3_OPTION_SOURCE_POV_MOTION,
    O3_OPTION_SOURCE_VOICE_FIRST,
    O3_OPTION_SOURCE_ELEMENT,
    O3_OPTION_SOURCE_AVATAR,
})
KLING_O3_MODE_VOICE_FIRST = "o3_voice_first_lipsync"
KLING_O3_MODE_ELEMENT_NATIVE = "o3_element_native_voice"
KLING_O3_MODE_AVATAR = "o3_avatar_pro_v1"


def infer_o3_option_pipeline_mode(option: dict | None) -> str:
    """Classify a gallery option's pipeline (source beats path for animation imports)."""
    if not isinstance(option, dict):
        return ""
    source = str(option.get("source") or "").strip().lower()
    path = str(option.get("video_path") or "").lower()
    if source == O3_OPTION_SOURCE_POV_MOTION or "_o3_i2v" in path or "_pov_" in path:
        return O3_GENERATE_MODE_ELEMENT_NATIVE
    if source in O3_OPTION_SOURCE_STILL or (
        "still_insert" in path and source not in O3_OPTION_SOURCE_ANIMATION
    ):
        return PIPELINE_MODE_STILL
    if "_avatar_pro" in path or source == O3_OPTION_SOURCE_AVATAR:
        return O3_GENERATE_MODE_AVATAR
    if "_voice_lipsync" in path:
        return O3_GENERATE_MODE_VOICE_FIRST
    if "_element_o3" in path or (
        "_element_" in path and "_voice_lipsync" not in path
    ):
        return O3_GENERATE_MODE_ELEMENT_NATIVE
    if source == O3_OPTION_SOURCE_ELEMENT:
        return O3_GENERATE_MODE_ELEMENT_NATIVE
    if source == O3_OPTION_SOURCE_VOICE_FIRST:
        return O3_GENERATE_MODE_VOICE_FIRST
    if source == O3_OPTION_SOURCE_AVATAR:
        return O3_GENERATE_MODE_AVATAR
    if source == "approved_kling_o3_video" and path:
        return infer_o3_option_pipeline_mode({"video_path": path})
    return ""


def o3_option_matches_generation_mode(option: dict, generation_mode: str) -> bool:
    """Selection/mismatch guard — voice_first vs element_native must align for export."""
    opt_mode = infer_o3_option_pipeline_mode(option)
    if not opt_mode or not generation_mode:
        return True
    if generation_mode == PIPELINE_MODE_STILL:
        return opt_mode == PIPELINE_MODE_STILL
    return opt_mode == generation_mode


def o3_option_visible_in_ui_slots(option: dict, generation_mode: str) -> bool:
    """UI shows three newest clips for the active pipeline — hide cross-pipeline history."""
    opt_mode = infer_o3_option_pipeline_mode(option)
    if generation_mode == PIPELINE_MODE_STILL:
        return opt_mode == PIPELINE_MODE_STILL
    if opt_mode == PIPELINE_MODE_STILL:
        return False
    if generation_mode in (
        O3_GENERATE_MODE_ELEMENT_NATIVE,
        O3_GENERATE_MODE_VOICE_FIRST,
        O3_GENERATE_MODE_AVATAR,
    ):
        if not opt_mode:
            return True
        return opt_mode == generation_mode
    return True


def find_active_o3_option(beat: dict) -> dict | None:
    key = beat.get("kling_o3_selected_option_key")
    path = beat.get("kling_o3_video_path")
    for o in beat.get("kling_o3_options") or []:
        if not isinstance(o, dict):
            continue
        if key and o.get("key") == key:
            return o
    if path:
        for o in beat.get("kling_o3_options") or []:
            if isinstance(o, dict) and o.get("video_path") == path:
                return o
    return None


def compute_o3_selection_pipeline_mismatch(
    beat: dict,
    sidecar: dict,
    *,
    option: dict | None = None,
) -> bool:
    """True when the active gallery clip's pipeline differs from the beat's generation mode."""
    if beat_is_still_insert(beat):
        return False
    gen_mode = resolve_beat_generation_mode(beat, sidecar)
    if gen_mode == PIPELINE_MODE_STILL:
        return False
    active = option if option is not None else find_active_o3_option(beat)
    if not active:
        return False
    return not o3_option_matches_generation_mode(active, gen_mode)


def sync_o3_selection_pipeline_fields(
    beat: dict,
    sidecar: dict,
    *,
    option: dict | None = None,
) -> bool:
    """Stamp mismatch flag + kling_o3_mode from the active gallery selection."""
    active = option if option is not None else find_active_o3_option(beat)
    opt_mode = infer_o3_option_pipeline_mode(active or {})
    mismatch = compute_o3_selection_pipeline_mismatch(beat, sidecar, option=active)
    changed = False
    if mismatch:
        if not beat.get("kling_o3_selection_pipeline_mismatch"):
            beat["kling_o3_selection_pipeline_mismatch"] = True
            changed = True
    elif beat.pop("kling_o3_selection_pipeline_mismatch", None) is not None:
        changed = True
    if opt_mode:
        if beat.get("kling_o3_active_clip_pipeline") != opt_mode:
            beat["kling_o3_active_clip_pipeline"] = opt_mode
            changed = True
        mode_map = {
            O3_GENERATE_MODE_VOICE_FIRST: KLING_O3_MODE_VOICE_FIRST,
            O3_GENERATE_MODE_ELEMENT_NATIVE: KLING_O3_MODE_ELEMENT_NATIVE,
            O3_GENERATE_MODE_AVATAR: KLING_O3_MODE_AVATAR,
        }
        expected = mode_map.get(opt_mode)
        if expected and beat.get("kling_o3_mode") != expected:
            beat["kling_o3_mode"] = expected
            changed = True
    elif beat.pop("kling_o3_active_clip_pipeline", None) is not None:
        changed = True
    return changed


def best_o3_option_for_generation_mode(beat: dict, generation_mode: str) -> dict | None:
    if generation_mode == PIPELINE_MODE_STILL:
        return None
    candidates: list[dict] = []
    for o in beat.get("kling_o3_options") or []:
        if not isinstance(o, dict):
            continue
        if not (o.get("video_path") or "").strip():
            continue
        if o3_option_matches_generation_mode(o, generation_mode):
            candidates.append(o)
    if not candidates:
        return None

    def _rank(o: dict) -> tuple:
        path = str(o.get("video_path") or "")
        created = str(o.get("created_at") or "")
        gen = o.get("generation")
        pri = 1_000_000 if "_voice_lipsync" in path else (
            900_000 if "_avatar_pro" in path else (int(gen) if isinstance(gen, int) else 0)
        )
        return (pri, created)

    return max(candidates, key=_rank)


def _occupied_o3_slot_indices(options: list) -> set[int]:
    taken: set[int] = set()
    for opt in options:
        if not isinstance(opt, dict):
            continue
        si = opt.get("slot_index")
        if isinstance(si, int) and 0 <= si <= 2:
            taken.add(si)
    return taken


def _first_free_o3_slot(taken: set[int], *, skip: int | None = None) -> int | None:
    for j in range(3):
        if j == skip or j in taken:
            continue
        return j
    return None


def promote_o3_video_path_active(
    beat: dict,
    sidecar: dict,
    generation_mode: str,
) -> bool:
    """After delivery finalize, honor ``kling_o3_video_path`` over stale ``selected_option_key``."""
    if generation_mode == PIPELINE_MODE_STILL:
        return False
    path = str(beat.get("kling_o3_video_path") or "").strip()
    if not path:
        return False
    match: dict | None = None
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        if str(opt.get("video_path") or "").strip() != path:
            continue
        if not o3_option_matches_generation_mode(opt, generation_mode):
            continue
        match = opt
        break
    if not match:
        return False
    beat_id = str(beat.get("beat_id") or "beat")
    key = str(match.get("key") or _kling_o3_option_key(beat_id, path))
    now = datetime.now(timezone.utc).isoformat()
    beat["kling_o3_selected_option_key"] = key
    beat["kling_o3_selected_at"] = now
    for opt in beat.get("kling_o3_options") or []:
        if isinstance(opt, dict):
            opt["active"] = str(opt.get("video_path") or "").strip() == path or opt.get("key") == key
    gen = match.get("generation")
    if gen is None:
        gen = _kling_o3_gen_from_video_path(path)
    if gen is not None:
        beat["kling_o3_generation"] = max(int(beat.get("kling_o3_generation") or 0), int(gen))
    sync_o3_selection_pipeline_fields(beat, sidecar, option=match)
    return True


def auto_select_o3_option_for_generation_mode(beat: dict, sidecar: dict, generation_mode: str) -> bool:
    """After a pipeline toggle, re-pin the active clip to the best matching gallery option."""
    if generation_mode == PIPELINE_MODE_STILL:
        return False
    current = find_active_o3_option(beat)
    if current and o3_option_matches_generation_mode(current, generation_mode):
        return sync_o3_selection_pipeline_fields(beat, sidecar, option=current)
    best = best_o3_option_for_generation_mode(beat, generation_mode)
    if not best or not best.get("video_path"):
        sync_o3_selection_pipeline_fields(beat, sidecar, option=current)
        return False
    beat_id = str(beat.get("beat_id") or "beat")
    video_path = str(best["video_path"])
    key = str(best.get("key") or _kling_o3_option_key(beat_id, video_path))
    now = datetime.now(timezone.utc).isoformat()
    beat["kling_o3_video_path"] = video_path
    beat["kling_o3_selected_option_key"] = key
    beat["kling_o3_selected_at"] = now
    for o in beat.get("kling_o3_options") or []:
        if isinstance(o, dict):
            o["active"] = o.get("video_path") == video_path or o.get("key") == key
    sync_o3_selection_pipeline_fields(beat, sidecar, option=best)
    return True


class PipelineToggleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def beat_is_stage_direction_only(beat: dict) -> bool:
    sp = str(beat.get("speaker") or "").strip().lower()
    bt = str(beat.get("beat_type") or "").lower()
    return (
        sp in ("[stage direction]", "stage direction", "")
        or bt == "stage_direction"
    )


def resolve_beat_pipeline_mode(beat: dict) -> str:
    """Effective pipeline mode for UI routing."""
    if beat_is_still_insert(beat):
        return PIPELINE_MODE_STILL
    if beat_is_stage_direction_only(beat):
        return "stage_direction"
    return PIPELINE_MODE_O3


def classify_beat_pipeline_fields(beat: dict) -> bool:
    """Normalize pipeline-related fields on a beat. Returns True if beat was mutated."""
    if beat_is_canonical_mirror_protected(beat):
        return False
    changed = False
    if beat_is_stage_direction_only(beat):
        for field in ("pipeline", "beat_render_mode"):
            if beat.get(field) == PIPELINE_MODE_STILL:
                beat.pop(field, None)
                changed = True
        bt = str(beat.get("beat_type") or "")
        if bt in ("stage_still", ""):
            beat["beat_type"] = "stage_direction"
            changed = True
        return changed
    if beat_is_still_insert(beat):
        for field, val in (
            ("pipeline", PIPELINE_MODE_STILL),
            ("beat_render_mode", PIPELINE_MODE_STILL),
        ):
            if beat.get(field) != val:
                beat[field] = val
                changed = True
        if beat.get("beat_type") != "stage_still":
            beat["beat_type"] = "stage_still"
            changed = True
        return changed
    if beat.get("pipeline") != PIPELINE_MODE_O3:
        beat["pipeline"] = PIPELINE_MODE_O3
        changed = True
    if beat.get("beat_render_mode") == PIPELINE_MODE_STILL:
        beat.pop("beat_render_mode", None)
        changed = True
    bt = str(beat.get("beat_type") or "")
    if bt in ("stage_still", ""):
        beat["beat_type"] = "dialogue"
        changed = True
    return changed


def classify_all_sidecar_pipeline_fields(sidecar: dict) -> bool:
    """Normalize pipeline fields for every beat in the sidecar."""
    changed = False
    for arc in (sidecar.get("arcs") or {}).values():
        for seg in (arc.get("segments") or {}).values():
            for beat in seg.get("beats") or []:
                if classify_beat_pipeline_fields(beat):
                    changed = True
    return changed


_STILL_INSERT_PROMPT_MARKERS = (
    "do not submit to kling o3 element",
    "assign the still image in beat gen",
    "use pre-made gpt still from library",
    "use pre-made from library",
    "no @image1 character clip for this beat",
)


def is_still_insert_prompt_text(text: str) -> bool:
    """True when prompt body is Still+TTS instructions, not O3 motion text."""
    t = (text or "").strip()
    if not t:
        return False
    if t.upper().startswith("STILL INSERT"):
        return True
    lower = t.lower()
    return any(marker in lower for marker in _STILL_INSERT_PROMPT_MARKERS)


_KLING_O3_FLOWER_POSITIVE_RE = re.compile(
    r"\b(?:"
    r"sweet\s*[- ]?roses?|sweetroses?|blooming(?:\s+\w+){0,3}\s+(?:in\s+)?background|"
    r"rose\s+wreath|sweetrose\s+wreath|flowers?\s+in\s+(?:the\s+)?background|"
    r"full\s+garden\s+of\s+sweet"
    r")\b",
    re.IGNORECASE,
)
_KLING_O3_ADDITION_POSITIVE_RE = re.compile(
    r"\b(?:blooming|(?:sweet\s*[- ]?)?rose\s+wreath|wreath|sprouts?|blooms?\s+(?:in|around|on))\b",
    re.IGNORECASE,
)


def lint_kling_o3_prompt_contradictions(prompt: str) -> list[str]:
    """Detect self-contradictory operator prompts before verbatim O3 submit."""
    text = (prompt or "").strip()
    if not text:
        return []
    lower = text.lower()
    warnings: list[str] = []

    no_flowers = bool(re.search(r"\bno flowers\b", lower))
    flower_positive = bool(_KLING_O3_FLOWER_POSITIVE_RE.search(text))
    if no_flowers and flower_positive:
        warnings.append(
            'Prompt says "No flowers" but also describes Sweetroses/flowers/blooming — '
            "Kling follows positive visuals. Remove all flower lines from style and scene notes."
        )

    no_additions = bool(re.search(r"\bnothing additional is added\b", lower))
    if no_additions and (flower_positive or _KLING_O3_ADDITION_POSITIVE_RE.search(text)):
        warnings.append(
            'Prompt says "Nothing additional is added" but also describes blooming additions — '
            "remove conflicting style/scene-notes lines."
        )

    return warnings


def validate_o3_submit_prompt_for_mode(user_prompt: str, generation_mode: str) -> tuple[bool, str, str]:
    """Block still-insert prompt text on voice_first / element_native Generate."""
    mode = str(generation_mode or "").strip().lower()
    prompt = (user_prompt or "").strip()
    if mode in O3_SPEAK_GENERATE_MODES:
        if is_still_insert_prompt_text(prompt):
            return (
                False,
                "STILL_INSERT_PROMPT_ON_O3_MODE",
                (
                    "Still+TTS prompt cannot be submitted to O3 speak modes — "
                    "switch to Still Insert mode or paste the portrait / motion prompt."
                ),
            )
        contradictions = lint_kling_o3_prompt_contradictions(prompt)
        if contradictions:
            return (
                False,
                "PROMPT_SELF_CONTRADICTORY",
                " ".join(contradictions),
            )
    return True, "", ""


def stamp_o3_delivery_pipeline_coherence(
    beat: dict,
    sidecar: dict,
    *,
    generation_mode: str,
) -> None:
    """After delivery finalize, align mode fields + active clip pipeline metadata."""
    mode = str(generation_mode or "").strip().lower()
    if mode not in O3_SPEAK_GENERATE_MODES:
        return
    beat["o3_generate_mode"] = mode
    beat["kling_o3_generate_mode"] = mode
    classify_beat_pipeline_fields(beat)
    if not promote_o3_video_path_active(beat, sidecar, mode):
        auto_select_o3_option_for_generation_mode(beat, sidecar, mode)
    sync_o3_selection_pipeline_fields(beat, sidecar)


def resolve_beat_still_prompt(beat: dict) -> str:
    """Persisted Still+TTS prompt (separate from O3 motion prompt)."""
    stored = (beat.get("kling_o3_prompt_still") or "").strip()
    if stored:
        return stored
    legacy = (beat.get("kling_o3_prompt") or "").strip()
    if is_still_insert_prompt_text(legacy):
        beat["kling_o3_prompt_still"] = legacy
        return legacy
    return ""


def resolve_beat_o3_prompt(beat: dict) -> str:
    """O3 motion prompt — shared by voice_first and element_native."""
    legacy = (beat.get("kling_o3_prompt") or "").strip()
    if legacy and not is_still_insert_prompt_text(legacy):
        return legacy
    return ""


def set_beat_still_prompt(beat: dict, text: str) -> None:
    beat["kling_o3_prompt_still"] = (text or "").strip()


def set_beat_o3_prompt(beat: dict, text: str) -> None:
    beat["kling_o3_prompt"] = (text or "").strip()


def active_beat_prompt_for_generation_mode(beat: dict, mode: str) -> str:
    if mode == PIPELINE_MODE_STILL:
        still = resolve_beat_still_prompt(beat)
        if still:
            return still
        from beat_extract_policy import build_still_insert_prompt

        return build_still_insert_prompt(beat)
    return resolve_beat_o3_prompt(beat)


def persist_and_load_prompts_for_generation_mode(
    beat: dict,
    old_mode: str,
    new_mode: str,
    *,
    event_id: str,
    phase: str,
) -> bool:
    """Swap prompt textarea when crossing Still ↔ O3; voice_first ↔ element_native share O3 text."""
    changed = False
    display = (beat.get("kling_o3_prompt") or "").strip()

    if old_mode == PIPELINE_MODE_STILL:
        if display:
            set_beat_still_prompt(beat, display)
            changed = True
    elif old_mode in O3_SPEAK_GENERATE_MODES:
        if display and not is_still_insert_prompt_text(display):
            set_beat_o3_prompt(beat, display)
            changed = True

    if new_mode == PIPELINE_MODE_STILL:
        still = resolve_beat_still_prompt(beat)
        if not still:
            from beat_extract_policy import build_still_insert_prompt

            still = build_still_insert_prompt(beat)
            set_beat_still_prompt(beat, still)
            changed = True
        if beat.get("kling_o3_prompt") != still:
            beat["kling_o3_prompt"] = still
            changed = True
    elif old_mode == PIPELINE_MODE_STILL:
        o3 = resolve_beat_o3_prompt(beat)
        if not o3:
            apply_kling_o3_defaults_to_beat(beat, event_id, phase)
            o3 = resolve_beat_o3_prompt(beat)
            if not o3:
                set_beat_o3_prompt(beat, build_kling_o3_prompt(beat))
                o3 = resolve_beat_o3_prompt(beat)
            changed = True
        if o3 and beat.get("kling_o3_prompt") != o3:
            beat["kling_o3_prompt"] = o3
            changed = True
        if _scrub_still_insert_prompt_labels(beat):
            changed = True
    return changed


def apply_beat_pipeline_still_mode(beat: dict, event_id: str, phase: str) -> None:
    beat["pipeline"] = PIPELINE_MODE_STILL
    beat["beat_render_mode"] = PIPELINE_MODE_STILL
    beat["beat_type"] = "stage_still"
    if not beat.get("kling_o3_duration_locked"):
        beat["kling_o3_duration"] = 3
    beat.setdefault("kling_o3_status", "draft")


def _scrub_still_insert_prompt_labels(beat: dict) -> bool:
    """Remove still-insert header labels that block O3 submit after pipeline flip."""
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt:
        return False
    cleaned = prompt
    for pat in (
        r"\s*[—–-]\s*Still insert\s*[—–-][^\n]*",
        r"\bStill insert\s*[—–-]\s*",
        r"\bGPT still\.?\s*",
        r"^STILL INSERT[^\n]*\n?",
    ):
        cleaned = re.sub(pat, "", cleaned, flags=re.I)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if cleaned == prompt:
        return False
    beat["kling_o3_prompt"] = cleaned
    return True


def apply_beat_pipeline_o3_mode(beat: dict, event_id: str, phase: str) -> None:
    beat.pop("beat_render_mode", None)
    beat["pipeline"] = PIPELINE_MODE_O3
    beat["beat_type"] = "dialogue"
    apply_kling_o3_defaults_to_beat(beat, event_id, phase)
    beat.pop("kling_o3_still_stitch_approved", None)
    beat.pop("kling_o3_still_stitch_approved_at", None)
    if beat.get("kling_o3_status") == "still_rendered":
        beat["kling_o3_status"] = "draft"
    speaker = str(beat.get("speaker") or "").strip()
    if speaker and _speaker_has_element_bound_voice(speaker):
        from beat_extract_policy import kling_face_scene_notes

        scene = str(beat.get("scene_notes") or "").strip()
        healed_scene = kling_face_scene_notes(speaker, scene)
        if healed_scene != scene:
            beat["scene_notes"] = healed_scene


def segment_event_phase_for_beat(sidecar: dict, beat_id: str) -> tuple[str, str] | tuple[None, None]:
    for arc in (sidecar.get("arcs") or {}).values():
        for seg_key, seg in (arc.get("segments") or {}).items():
            for beat in seg.get("beats") or []:
                if beat.get("beat_id") == beat_id:
                    m = re.match(r"^event_(\d+)_(.+)$", seg_key)
                    if m:
                        return m.group(1), m.group(2)
    return None, None


def set_beat_pipeline_mode(
    beat: dict,
    mode: str,
    *,
    event_id: str,
    phase: str,
) -> bool:
    """Switch beat between still_insert and kling_o3_omni. Returns True if mode changed."""
    mode = str(mode or "").strip()
    if mode not in VALID_PIPELINE_MODES:
        raise PipelineToggleError(
            "INVALID_PIPELINE_MODE",
            f"pipeline must be one of {sorted(VALID_PIPELINE_MODES)}",
        )
    if beat_is_canonical_mirror_protected(beat):
        raise PipelineToggleError(
            "CANONICAL_BEAT_PROTECTED",
            "Canonical intro beats cannot change pipeline mode",
        )
    if _beat_pipeline_operator_busy(beat):
        raise PipelineToggleError(
            "INTENT_JOB_ACTIVE",
            "O3 job is running — pipeline locked until it finishes",
        )
    if beat_is_stage_direction_only(beat):
        raise PipelineToggleError(
            "STAGE_DIRECTION_BEAT",
            "Stage-direction beats cannot toggle pipeline — assign a speaker first",
        )
    current = resolve_beat_pipeline_mode(beat)
    old_gen = resolve_beat_generation_mode(beat, {})
    if current == mode:
        classify_beat_pipeline_fields(beat)
        return False
    if mode == PIPELINE_MODE_STILL:
        apply_beat_pipeline_still_mode(beat, event_id, phase)
        new_gen = PIPELINE_MODE_STILL
    else:
        apply_beat_pipeline_o3_mode(beat, event_id, phase)
        new_gen = str(beat.get("o3_generate_mode") or O3_GENERATE_MODE_VOICE_FIRST).strip().lower()
    classify_beat_pipeline_fields(beat)
    persist_and_load_prompts_for_generation_mode(
        beat, old_gen, new_gen, event_id=event_id, phase=phase,
    )
    return True


def resolve_beat_generation_mode(beat: dict, sidecar: dict) -> str:
    """Effective per-beat generation mode for UI + routing preview."""
    if beat_is_still_insert(beat):
        return PIPELINE_MODE_STILL
    return resolve_o3_generate_mode(beat, sidecar)


def heal_beat_dual_prompts(
    beat: dict,
    sidecar: dict,
    *,
    event_id: str,
    phase: str,
) -> bool:
    """Migrate poisoned still text out of kling_o3_prompt; restore O3 prompt per mode."""
    changed = False
    mode = resolve_beat_generation_mode(beat, sidecar)
    display = (beat.get("kling_o3_prompt") or "").strip()

    if is_still_insert_prompt_text(display) and not (beat.get("kling_o3_prompt_still") or "").strip():
        set_beat_still_prompt(beat, display)
        changed = True

    if mode == PIPELINE_MODE_STILL:
        still = resolve_beat_still_prompt(beat)
        if not still:
            from beat_extract_policy import build_still_insert_prompt

            still = build_still_insert_prompt(beat)
            set_beat_still_prompt(beat, still)
            changed = True
        if beat.get("kling_o3_prompt") != still:
            beat["kling_o3_prompt"] = still
            changed = True
    else:
        o3 = resolve_beat_o3_prompt(beat)
        if o3 and o3_prompt_is_avatar_pro_poisoned(o3, beat=beat):
            o3 = build_kling_o3_prompt(beat)
            clear_o3_prompt_box_law(beat)
            changed = True
        if not o3:
            apply_kling_o3_defaults_to_beat(beat, event_id, phase)
            o3 = resolve_beat_o3_prompt(beat)
            changed = True
        if o3 and beat.get("kling_o3_prompt") != o3:
            beat["kling_o3_prompt"] = o3
            changed = True
        if _scrub_still_insert_prompt_labels(beat):
            changed = True
    return changed


_O3_COMPOSITE_HEADER_RE = re.compile(
    r"(?m)^@Image1[^\n]*Scene from @Image2\.?\s*$",
    re.I,
)


def heal_beat_o3_composite_redundant_tail(beat: dict) -> bool:
    """Strip legacy redundant backdrop sentence from Element composite paragraphs."""
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt:
        return False
    try:
        from beat_extract_policy import strip_o3_element_composite_redundant_tail
    except ImportError:
        from tools.beat_extract_policy import strip_o3_element_composite_redundant_tail  # type: ignore
    cleaned = strip_o3_element_composite_redundant_tail(prompt)
    if cleaned == prompt:
        return False
    beat["kling_o3_prompt"] = cleaned
    return True


def heal_beat_o3_composite_lock(beat: dict) -> bool:
    """Inject Composite paragraph on Element O3 beats missing first-frame @Image2 lock."""
    speaker = str(beat.get("speaker") or "").strip()
    if not speaker or not _speaker_has_element_bound_voice(speaker):
        return False
    if beat_is_still_insert(beat):
        return False
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt or "@Image2" not in prompt:
        return False
    try:
        from beat_extract_policy import o3_element_composite_paragraph, prompt_has_o3_element_composite
    except ImportError:
        from tools.beat_extract_policy import (  # type: ignore
            o3_element_composite_paragraph,
            prompt_has_o3_element_composite,
        )
    if prompt_has_o3_element_composite(prompt):
        return False
    composite = o3_element_composite_paragraph(speaker)
    header_match = _O3_COMPOSITE_HEADER_RE.search(prompt)
    if header_match:
        insert_at = header_match.end()
        new_prompt = prompt[:insert_at].rstrip() + "\n\n" + composite + prompt[insert_at:]
    else:
        new_prompt = prompt.rstrip() + "\n\n" + composite
    beat["kling_o3_prompt"] = re.sub(r"\n{3,}", "\n\n", new_prompt).strip()
    return beat["kling_o3_prompt"] != prompt


def heal_sidecar_o3_composite_locks(sidecar: dict) -> bool:
    """Backfill Composite lock on existing Element O3 prompts across all events/arcs."""
    changed = False
    for arc in (sidecar.get("arcs") or {}).values():
        for seg in (arc.get("segments") or {}).values():
            for beat in seg.get("beats") or []:
                if isinstance(beat, dict) and heal_beat_o3_composite_lock(beat):
                    changed = True
    return changed


def heal_sidecar_dual_prompts(sidecar: dict) -> bool:
    """One-time heal for beats where still-insert text overwrote the shared O3 prompt."""
    changed = False
    for arc in (sidecar.get("arcs") or {}).values():
        for _seg_key, seg in (arc.get("segments") or {}).items():
            for beat in seg.get("beats") or []:
                if not isinstance(beat, dict) or not beat.get("beat_id"):
                    continue
                event_id, phase = segment_event_phase_for_beat(sidecar, beat["beat_id"])
                if not event_id or not phase:
                    continue
                if heal_beat_dual_prompts(
                    beat,
                    sidecar,
                    event_id=str(event_id),
                    phase=str(phase),
                ):
                    changed = True
    return changed


def heal_sidecar_beat_continuity(sidecar: dict) -> bool:
    """BEAT_CONTINUITY_V1 — inject reaction-first prior-beat context into kling_o3_prompt."""
    from beat_extract_policy import apply_beat_continuity_chain

    changed = False
    for arc in (sidecar.get("arcs") or {}).values():
        for seg in (arc.get("segments") or {}).values():
            beats = list(seg.get("beats") or [])
            if len(beats) < 2:
                continue
            before = [
                (
                    b.get("beat_id"),
                    b.get("kling_o3_prompt"),
                    b.get("kling_o3_prior_beat_context"),
                )
                for b in beats
                if isinstance(b, dict)
            ]
            apply_beat_continuity_chain(beats)
            after = [
                (
                    b.get("beat_id"),
                    b.get("kling_o3_prompt"),
                    b.get("kling_o3_prior_beat_context"),
                )
                for b in beats
                if isinstance(b, dict)
            ]
            if before != after:
                changed = True
                seg["beats"] = beats
    return changed


def enrich_beat_generation_mode(beat: dict, sidecar: dict) -> None:
    """Stamp resolved generation_mode on beat dict for Beat Gen session-state."""
    heal_avatar_pro_poisoned_o3_prompt(beat, sidecar)
    heal_beat_o3_composite_redundant_tail(beat)
    event_id, phase = segment_event_phase_for_beat(sidecar, str(beat.get("beat_id") or ""))
    if event_id and phase:
        heal_beat_dual_prompts(
            beat,
            sidecar,
            event_id=str(event_id),
            phase=str(phase),
        )
    beat["generation_mode"] = resolve_beat_generation_mode(beat, sidecar)
    mode = beat["generation_mode"]
    active = active_beat_prompt_for_generation_mode(beat, mode)
    if active and (beat.get("kling_o3_prompt") or "").strip() != active:
        beat["kling_o3_prompt"] = active
    sync_o3_selection_pipeline_fields(beat, sidecar)


def enrich_beats_generation_mode(beats: list[dict], sidecar: dict) -> None:
    for beat in beats:
        enrich_beat_generation_mode(beat, sidecar)


def set_beat_generation_mode(
    beat: dict,
    mode: str,
    *,
    event_id: str,
    phase: str,
    sidecar: dict,
) -> bool:
    """Switch beat among still_insert, voice_first, element_native."""
    mode = str(mode or "").strip().lower()
    if mode not in VALID_GENERATION_MODES:
        raise PipelineToggleError(
            "INVALID_GENERATION_MODE",
            f"generation_mode must be one of {sorted(VALID_GENERATION_MODES)}",
        )
    if beat_is_canonical_mirror_protected(beat):
        raise PipelineToggleError(
            "CANONICAL_BEAT_PROTECTED",
            "Canonical intro beats cannot change pipeline mode",
        )
    if _beat_pipeline_operator_busy(beat):
        raise PipelineToggleError(
            "INTENT_JOB_ACTIVE",
            "O3 job is running — pipeline locked until it finishes",
        )
    if beat_is_stage_direction_only(beat):
        raise PipelineToggleError(
            "STAGE_DIRECTION_BEAT",
            "Stage-direction beats cannot toggle pipeline — assign a speaker first",
        )
    current = resolve_beat_generation_mode(beat, sidecar)
    if current == mode:
        classify_beat_pipeline_fields(beat)
        if mode == PIPELINE_MODE_STILL and beat.pop("o3_generate_mode", None) is not None:
            return True
        return False
    changed = False
    if mode == PIPELINE_MODE_STILL:
        if resolve_beat_pipeline_mode(beat) != PIPELINE_MODE_STILL:
            apply_beat_pipeline_still_mode(beat, event_id, phase)
            changed = True
        if beat.pop("o3_generate_mode", None) is not None:
            changed = True
    else:
        if resolve_beat_pipeline_mode(beat) != PIPELINE_MODE_O3:
            apply_beat_pipeline_o3_mode(beat, event_id, phase)
            changed = True
        if (beat.get("o3_generate_mode") or "").strip().lower() != mode:
            beat["o3_generate_mode"] = mode
            changed = True
    classify_beat_pipeline_fields(beat)
    if persist_and_load_prompts_for_generation_mode(
        beat, current, mode, event_id=event_id, phase=phase,
    ):
        changed = True
    if auto_select_o3_option_for_generation_mode(beat, sidecar, mode):
        changed = True
    return changed


_STILL_INSERT_SPOKEN_RE = re.compile(
    r"([A-Za-z][A-Za-z\s'-]*?)\s*(?:\[[^\]]+\])*\s*:\s*"
    r"(['\"])(.*?)\2",
    re.DOTALL,
)
_STILL_INSERT_PERFORMANCE_TAG_WORDS = frozenset({"pause", "break", "silence", "beat", "breath", "short pause"})
_STILL_INSERT_SPEAKER_ALIASES = ("Loral", "Lorelai", "Laurel", "Chipper", "Tessa", "Arlo", "Pip")
_STILL_INSERT_NON_DELIVERY_VERBS = frozenset({
    "say", "says", "speak", "speaks", "speaking", "said", "look", "looks", "turn", "turns",
})
_STILL_INSERT_PRONOUN_SPEAKERS = frozenset({
    "she", "he", "they", "it", "her", "him", "them", "their",
})
_STILL_INSERT_BOGUS_SPEAKERS = _STILL_INSERT_NON_DELIVERY_VERBS | _STILL_INSERT_PRONOUN_SPEAKERS | frozenset({
    "whispering", "whispers", "muttering", "shouting", "crying", "laughing", "awed",
    "disbelieving", "incredulous", "character",
})


def _still_insert_named_speaker_from_source(source: str) -> str:
    """First registered character name in prompt — beats pronoun extraction (``she says:``)."""
    for name in _STILL_INSERT_SPEAKER_ALIASES:
        if re.search(rf"\b{re.escape(name)}\b", source, flags=re.I):
            return _canon_speaker(name) or name
    return ""


def _resolve_still_insert_speaker(source: str, beat: dict, extracted: str | None) -> str:
    """Speaker for still TTS — beat sidecar wins over bogus colon tokens like ``whispering:``."""
    beat_sp = _canon_speaker((beat.get("speaker") or "").strip()) or (beat.get("speaker") or "").strip()
    if beat_sp and beat_sp not in ("Character", "[Stage Direction]"):
        return beat_sp
    named = _still_insert_named_speaker_from_source(source)
    if named:
        return named
    ext = (extracted or "").strip()
    if ext and ext not in ("Character", "[Stage Direction]") and ext.lower() not in _STILL_INSERT_BOGUS_SPEAKERS:
        return _canon_speaker(ext) or ext
    from beat_extract_policy import infer_speaker_from_dialogue

    inferred = infer_speaker_from_dialogue(source)
    if inferred and inferred.lower() not in _STILL_INSERT_BOGUS_SPEAKERS:
        return _canon_speaker(inferred) or inferred
    return named


def _split_still_insert_delivery_phrases(chunk: str) -> list[str]:
    """Split comma-delimited delivery prose into ElevenLabs v3 tag tokens."""
    out: list[str] = []
    for raw in re.split(r",\s*", (chunk or "").strip()):
        p = raw.strip(" .;")
        if not p:
            continue
        p = re.sub(r"^in an?\s+", "", p, flags=re.I)
        p = re.sub(r"^in\s+", "", p, flags=re.I)
        p = p.strip(" .;")
        if not p or p.lower() in {"and", "the", "a", "an"}:
            continue
        if p.lower() in _STILL_INSERT_NON_DELIVERY_VERBS:
            continue
        out.append(p)
    return out


def _dedupe_still_insert_delivery_phrases(phrases: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for phrase in phrases:
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(phrase)
    return out


def _still_insert_delivery_region(
    source: str,
    *,
    speaker: str | None,
    spoken: str,
) -> str:
    """Text between resolved speaker and opening quote — excludes scene setup prefix."""
    text = (source or "").strip()
    if not text:
        return ""
    quotes = list(re.finditer(r'"([^"]*)"', text))
    if not quotes:
        quotes = list(re.finditer(r"'([^']*)'", text))
    if quotes:
        prefix = text[: quotes[-1].start()].strip()
    else:
        colon_tail = text.rfind(":")
        prefix = text[:colon_tail].strip() if colon_tail >= 0 else text
    colon_tail = prefix.rfind(":")
    before_colon = prefix[:colon_tail].strip() if colon_tail >= 0 else prefix
    search_names = [speaker] if speaker else []
    search_names.extend(_STILL_INSERT_SPEAKER_ALIASES)
    region = before_colon
    for name in dict.fromkeys(n for n in search_names if n):
        matches = list(re.finditer(rf"\b{re.escape(name)}\b", before_colon, flags=re.I))
        if matches:
            region = before_colon[matches[-1].end() :].strip()
            break
    return region


def _extract_still_insert_delivery_phrases(
    source: str,
    *,
    speaker: str | None,
    spoken: str,
) -> list[str]:
    """Parse author delivery/emotion before quoted dialogue for ElevenLabs v3 tags."""
    region = _still_insert_delivery_region(source, speaker=speaker, spoken=spoken)
    if not region:
        return []

    phrases: list[str] = []
    for m in re.finditer(r"\[\[([^\]]+)\]\]", region):
        phrases.extend(_split_still_insert_delivery_phrases(m.group(1)))
    region_no_brackets = re.sub(r"\[\[[^\]]+\]\]", "", region)
    for m in re.finditer(r"\[([^\]]+)\]", region_no_brackets):
        inner = m.group(1).strip()
        if inner.lower() in _STILL_INSERT_PERFORMANCE_TAG_WORDS:
            continue
        phrases.extend(_split_still_insert_delivery_phrases(inner))
    prose = re.sub(r"\[[^\]]+\]", "", region_no_brackets).strip(" ,.")
    if prose.strip():
        phrases.extend(_split_still_insert_delivery_phrases(prose))
    return _dedupe_still_insert_delivery_phrases(phrases)


def build_still_insert_elevenlabs_text(delivery: list[str], spoken: str) -> str:
    """ElevenLabs v3 payload — bracket delivery tags then spoken line."""
    spoken = (spoken or "").strip()
    tags = _dedupe_still_insert_delivery_phrases([t for t in delivery if (t or "").strip()])
    if not tags:
        return spoken
    tag_inner = ", ".join(tags[:8])
    return f"[{tag_inner}] {spoken}"


_STILL_INSERT_UNTRUSTED_DELIVERY_RE = re.compile(
    r"\b(she|he|they|it)\s+says\b|\bspeaks?\s+as\s+if\b|\bwhispers?\b|\bwhispering\b",
    re.I,
)


def _still_insert_prose_delivery_is_untrusted(phrases: list[str]) -> bool:
    """Author prose like ``she says`` / ``whispers`` must not beat canonical O3 delivery lock."""
    for phrase in phrases:
        low = (phrase or "").strip().lower()
        if not low:
            continue
        if low in _STILL_INSERT_PRONOUN_SPEAKERS:
            return True
        if low in _STILL_INSERT_NON_DELIVERY_VERBS:
            return True
        if _STILL_INSERT_UNTRUSTED_DELIVERY_RE.search(low):
            return True
    return False


def still_insert_canonical_delivery_phrases(speaker: str) -> list[str]:
    """Locked delivery tags — same contract as Element O3 ``inject_locked_voice_line``."""
    try:
        from tools import kling_character_registry as reg
        from tools import kling_o3_prompt as o3p
    except ImportError:
        import kling_character_registry as reg  # type: ignore
        import kling_o3_prompt as o3p  # type: ignore

    reg_key = reg.resolve_registry_key(speaker) or _canon_speaker(speaker) or (speaker or "").strip()
    delivery = (
        o3p._DELIVERY_BY_SPEAKER.get(reg_key or "")
        or o3p._DELIVERY_BY_SPEAKER.get((speaker or "").strip())
    )
    if not delivery:
        return []
    return _split_still_insert_delivery_phrases(delivery)


def resolve_still_insert_delivery_for_tts(
    source: str,
    *,
    speaker: str,
    spoken: str,
) -> list[str]:
    """Pick ElevenLabs v3 delivery tags — canonical lock wins over bogus author prose."""
    prose = _extract_still_insert_delivery_phrases(source, speaker=speaker, spoken=spoken)
    canonical = still_insert_canonical_delivery_phrases(speaker)
    if canonical and _still_insert_prose_delivery_is_untrusted(prose):
        return canonical
    if prose:
        return prose
    return canonical


def resolve_still_insert_elevenlabs_profile(speaker: str) -> dict | None:
    """Still+TTS ElevenLabs profile from ``character_subjects`` — not Directus Luna defaults.

    Uses locked Miranda sample settings (speed 0.93 for Lorelai) so Still+TTS matches
    Beat 18 proven O3 timbre instead of Directus ``Luna`` at speed 1.3.
    """
    try:
        from tools import kling_character_registry as reg
        from tools import kling_element_voice as elv
    except ImportError:
        import kling_character_registry as reg  # type: ignore
        import kling_element_voice as elv  # type: ignore

    reg_key = reg.resolve_registry_key(speaker) or _canon_speaker(speaker) or (speaker or "").strip()
    if not reg_key:
        return None
    entry = reg.get_character_entry(reg_key)
    if not entry:
        return None
    voice_id = str(entry.get("elevenlabs_voice_id") or "").strip()
    if not voice_id:
        return None
    roster = getattr(elv, "ELEVENLABS_VOICE_ROSTER", {}) or {}
    roster_row = roster.get(reg_key) or {}
    if reg_key == "Lorelai" and not roster_row:
        roster_row = roster.get("Luna") or {}
    lock = entry.get("voice_sample_lock") if isinstance(entry.get("voice_sample_lock"), dict) else {}
    speed = lock.get("locked_speed")
    if speed is None:
        speed = entry.get("audition_speed")
    if speed is None:
        speed = roster_row.get("speed")
    profile: dict = {
        "character_name": reg_key,
        "voice_id": voice_id,
        "model": str(roster_row.get("model") or "eleven_v3"),
        "stability": float(roster_row.get("stability", 0.30)),
        "similarity_boost": float(roster_row.get("similarity_boost", 0.80)),
        "style": float(roster_row.get("style", 0.30)),
        "source": "character_subjects",
    }
    if speed is not None:
        profile["speed"] = float(speed)
    return profile


def extract_still_insert_tts(beat: dict) -> dict | None:
    """Parse still-insert TTS — spoken line + delivery/emotion for ElevenLabs v3."""
    from beat_extract_policy import extract_spoken_from_dialogue, infer_speaker_from_dialogue

    prompt = resolve_beat_still_prompt(beat) or (beat.get("kling_o3_prompt") or "").strip()
    dialogue = (beat.get("dialogue_text") or "").strip()

    # Prompt-box is law: the editable textarea drives still-insert TTS when present.
    if prompt:
        source = prompt
    elif dialogue:
        source = dialogue
    elif prompt:
        source = (beat.get("scene_notes") or "").strip() or prompt
    else:
        source = ""
    if not source:
        return None

    speaker, spoken = extract_spoken_from_dialogue(source)
    emo_only = re.match(r"^(?:\[[^\]]+\]\s*)+:\s*(.+)$", (spoken or source).strip(), re.DOTALL)
    if emo_only:
        spoken = emo_only.group(1).strip()
    if not spoken:
        return None
    spoken = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", spoken).strip()
    speaker = _resolve_still_insert_speaker(source, beat, speaker)
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            beat_sp = _canon_speaker((beat.get("speaker") or "").strip()) or (
                beat.get("speaker") or ""
            ).strip()
            if beat_sp and reg.is_speaker_voice_ready(beat_sp):
                speaker = beat_sp
            else:
                named = _still_insert_named_speaker_from_source(source)
                if named and reg.is_speaker_voice_ready(named):
                    speaker = named
    except Exception:
        pass
    if not speaker or "stage direction" in speaker.lower():
        return None
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return None
    except Exception:
        pass
    spoken = _kling_o3_normalize_spoken(spoken)
    spoken = re.sub(r"\[(?:pause|beat|breath|short pause)[^\]]*\]", " ", spoken, flags=re.I)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    if not spoken:
        return None
    delivery = resolve_still_insert_delivery_for_tts(
        source, speaker=speaker, spoken=spoken,
    )
    tts_text = build_still_insert_elevenlabs_text(delivery, spoken)
    return {
        "speaker": speaker,
        "text": spoken,
        "delivery": delivery,
        "tts_text": tts_text,
        "fingerprint": tts_text,
    }


def resolve_still_insert_render_duration_from_audio(
    audio_path: Path,
    *,
    fallback: float = STILL_INSERT_DEFAULT_DURATION_S,
) -> float:
    """Still clip length = full TTS + small tail pad (never hard-cap at 4s)."""
    audio_dur = _ffprobe_duration(audio_path)
    if audio_dur > 0:
        return max(STILL_INSERT_MIN_DURATION_S, audio_dur + STILL_INSERT_AUDIO_TAIL_PAD_S)
    return fallback


def resolve_still_insert_render_duration(
    beat: dict,
    event_dir: str | Path,
    *,
    sidecar: dict | None = None,
    production_state: dict | None = None,
    video_role: str = "intro",
    fallback: float | None = None,
) -> float:
    """Pick Ken Burns / static-hold duration from TTS when present."""
    base = STILL_INSERT_DEFAULT_DURATION_S if fallback is None else float(fallback)
    audio = resolve_bg_beat_tts_audio_path(
        event_dir,
        beat,
        sidecar=sidecar,
        production_state=production_state,
        video_role=video_role,
    )
    if audio is not None and audio.is_file():
        return resolve_still_insert_render_duration_from_audio(audio, fallback=base)
    return base


def render_still_insert_o3_clip(
    beat: dict,
    event_dir: str | Path,
    *,
    method: str = "ken_burns",
    duration: float = STILL_INSERT_DEFAULT_DURATION_S,
    slot_index: int = 0,
    sidecar: dict | None = None,
    production_state: dict | None = None,
    video_role: str = "intro",
) -> dict:
    """Ken Burns / static hold still → mp4 in kling_o3 slot (trim + magic-on-video parity)."""
    still = resolve_still_source_abs_path(beat)
    if still is None:
        raise ValueError(
            "No still image — drop a library image in option 1 or set char/BG ref first"
        )
    event_dir = Path(event_dir)
    audio = resolve_bg_beat_tts_audio_path(
        event_dir, beat, sidecar=sidecar,
        production_state=production_state, video_role=video_role,
    )
    if audio is not None and audio.is_file():
        duration = resolve_still_insert_render_duration_from_audio(
            audio, fallback=duration,
        )
    clips_dir = kling_o3_clips_dir(event_dir)
    ts = int(time.time())
    saved_trim_start = float(beat.get("kling_o3_trim_start") or 0.0)
    saved_trim_back = beat.get("kling_o3_trim_back")
    had_sidecar_trim = still_insert_sidecar_trim_pending(beat)
    silent_path = clips_dir / f"{beat['beat_id']}_still_insert_{ts}.mp4"
    if method == "static_hold":
        run_static_hold(beat, str(still), duration, out_path=silent_path)
    else:
        run_ken_burns(
            beat, str(still), 50, 50, 1.0, 1.06, duration, out_path=silent_path,
        )
    final_path = silent_path.resolve()
    tts_mixed = False
    if audio is not None and audio.is_file():
        muxed = clips_dir / f"{beat['beat_id']}_still_insert_{ts}_tts.mp4"
        fs = _ffmpeg_stitch_module()
        fs.trim_normalized(
            final_path,
            muxed,
            trim_start=0.0,
            trim_end=None,
            mix_audio_path=audio,
            audio_delay=0.0,
            freeze_tail_s=STILL_INSERT_AUDIO_TAIL_PAD_S,
        )
        final_path = muxed.resolve()
        tts_mixed = True
    opt_key = f"{beat['beat_id']}_still_insert_{ts}"
    option = {
        "key": opt_key,
        "label": "still insert clip",
        "video_path": str(final_path),
        "source": "still_insert_static_hold" if method == "static_hold" else "still_insert_ken_burns",
        "slot_index": slot_index,
        "active": True,
    }
    still_sources = (
        "still_insert_static_hold",
        "still_insert_ken_burns",
        "still_insert_kling_idle",
    )
    options = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict)
        and not (
            o.get("source") in still_sources
            and o.get("slot_index") == slot_index
        )
    ]
    options.append(option)
    now = datetime.now(timezone.utc).isoformat()
    beat["kling_o3_options"] = options
    beat["kling_o3_video_path"] = str(final_path)
    # Build still ≠ stitch approve — explicit select-o3 / Approve still sets approved.
    beat["kling_o3_status"] = "still_rendered"
    beat["status"] = "draft"
    beat.pop("kling_o3_still_stitch_approved", None)
    beat.pop("kling_o3_still_stitch_approved_at", None)
    beat["kling_o3_selected_option_key"] = opt_key
    beat["kling_o3_selected_at"] = now
    if had_sidecar_trim:
        beat["kling_o3_trim_start"] = round(saved_trim_start, 2)
        if saved_trim_back is not None:
            beat["kling_o3_trim_back"] = round(float(saved_trim_back), 2)
        baked = bake_still_insert_trim_into_clip(beat, source_path=final_path)
        final_path = Path(baked["video_path"])
        beat["kling_o3_video_path"] = str(final_path)
        option["video_path"] = str(final_path)
    else:
        clear_kling_o3_beat_trim(beat)
    for o in options:
        o["active"] = o.get("key") == opt_key or o.get("video_path") == str(final_path)
    return {
        "video_path": str(final_path),
        "option_key": opt_key,
        "method": method,
        "duration_s": duration,
        "tts_mixed": tts_mixed,
        "still_path": str(still),
        "trim_baked": had_sidecar_trim,
    }


def probe_capabilities() -> dict:
    """Probe for optional dependencies. Returns dict of booleans."""
    caps = {
        "magic_compositor": False,
        "ffmpeg": False,
        "ffprobe": False,
        "update_beat_locked": callable(globals().get("update_beat_locked")),
        "sidecar_file_lock": callable(globals().get("sidecar_file_lock")),
        "read_sidecar_for_poll_snapshot": callable(globals().get("read_sidecar_for_poll_snapshot")),
        "magic_compositor_error": None,
    }
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from magic_compositor import MagicCompositor  # noqa: F401
        caps["magic_compositor"] = True
    except Exception as e:
        caps["magic_compositor_error"] = str(e)
    try:
        caps["ffmpeg"] = subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0
    except Exception:
        caps["ffmpeg"] = False
    try:
        caps["ffprobe"] = subprocess.run(["ffprobe", "-version"], capture_output=True).returncode == 0
    except Exception:
        caps["ffprobe"] = False
    try:
        from lipsync_public_host import probe_lipsync_public_host_capabilities

        creds = None
        try:
            from credentials import load_credentials  # type: ignore
        except ImportError:
            try:
                from tools.credentials_lib.credentials import load_credentials  # type: ignore
            except ImportError:
                load_credentials = None  # type: ignore[assignment]
        if load_credentials is not None:
            try:
                creds = load_credentials()
            except Exception:
                creds = None
        caps.update(probe_lipsync_public_host_capabilities(creds=creds))
    except Exception as exc:
        caps["lipsync_public_host_ready"] = False
        caps["lipsync_public_host_message"] = str(exc)
    return caps


# ---------------------------------------------------------------------------
# Kling O3 Omni — prompt builder + ref resolution (BEAT_GEN_KLING_O3_INTEGRATION v1)
# ---------------------------------------------------------------------------

KLING_O3_CAMERA_LOCK = (
    "Camera: static locked shot, no zoom, no dolly, no pan, no camera movement, "
    "stable eye-level close-up — character is seen in close-up, seen from the torso up."
)

# Kling O3 has no API flag to disable BGM — only prompt + sound:true (dialogue TTS).
# Ambient beds are mixed in Stitcher later; clips must be voice-only.
# Kling often ignores softer wording — use explicit negatives (still not guaranteed).
KLING_O3_AUDIO_LOCK = (
    "Audio: spoken character dialogue only — absolutely no background music, "
    "no ambient bed, no forest ambience, no nature sounds, no environmental audio, "
    "no soundtrack, no score, no music of any kind. Silent world except speech."
)

KLING_O3_SOLO_SHOT_LOCK = (
    "Only @Image1 is visible in the frame. No other characters, creatures, "
    "or people on screen."
)

KLING_O3_CHIPPER_SOLO_BIRD_LOCK = (
    "Exactly one bird in the frame — @Image1 only. No companion bird, no second "
    "songbird, no duplicate character, no other creatures on screen."
)

KLING_O3_VIEWER_ADDRESS_LOCK = (
    "The child viewer watching the video is off-screen and must never appear "
    "in the frame. @Image1 may speak directly to the camera and gesture "
    "toward the lens, but no second person is visible on screen."
)

# Element-bound O3: never encourage speak-to-camera / gesture — Kling treats that
# as hyper delivery and overrides "not bubbly or hyper" on the locked voice line.
KLING_O3_ELEMENT_VIEWER_OFFSCREEN_LOCK = (
    "The child viewer is off-screen and must never appear in the frame."
)

KLING_O3_PLURAL_ADDRESSEE_LOCK = (
    "Any other addressees besides @Image1 are off-screen and must not appear "
    "in the frame."
)

_VIEWER_ADDRESS_STRONG_RE = re.compile(
    r"\b(both of you|you two|you both|you're|youre|your|newest apprentice|"
    r"young magician|our friend|dear friend|and you|yes, you|"
    r"you can help|will you|can you help|thank you for|watching)\b",
    re.IGNORECASE,
)
_VIEWER_THIRD_PARTY_QUESTION_RE = re.compile(
    r"\bdo you think\b.*\b(she|he|they)\b",
    re.IGNORECASE,
)
_PLURAL_ADDRESSEE_RE = re.compile(r"\b(both of you|you two|you both)\b", re.IGNORECASE)


def ensure_kling_o3_speech_only_prompt(prompt: str) -> str:
    """Append or upgrade speech-only audio lock (manual or auto prompts)."""
    text = (prompt or "").rstrip()
    lower = text.lower()
    if "silent world except speech" in lower or "forest ambience" in lower:
        return text
    if "no background music" in lower:
        # Upgrade legacy shorter lock to explicit anti-ambient wording.
        text = re.sub(
            r"\n\nAudio: character dialogue and voice only[^\n]*(?:\n[^\n@][^\n]*)*",
            "",
            text,
            flags=re.IGNORECASE,
        ).rstrip()
    return f"{text}\n\n{KLING_O3_AUDIO_LOCK}"


KLING_O3_IDENTITY_LOCK = (
    "Match @Image1 character appearance, proportions, and facial expression exactly. "
    "Do not change the character design from @Image1."
)

KLING_O3_LIGHTING_LOCK = (
    "Match the natural lighting on @Image1 to @Image2 exactly — same warm golden direction, "
    "same soft shadow depth, same color temperature on character and background. "
    "Character must look physically present in the scene, not pasted on or separately lit. "
    "No rim-light mismatch, no saturation jump between foreground and background."
)

_KLING_O3_IDENTITY_LOCK_LINE_RE = re.compile(
    r"Match @Image1 character appearance[^\n]*"
    r"(?:\.\s*Do not change the character design from @Image1\.)?",
    re.I,
)

# Segment-level default background PNGs (Dropbox project root filenames).
_SEGMENT_BG_DEFAULTS: dict[tuple[str, str], str] = {
    ("1", "pre"): "bg_entry_streamside.png",
    ("1", "post"): "bg_entry_streamside.png",
    ("1", "full"): "bg_entry_streamside.png",
}

# Humanoid hybrid refs at project root (June 2026). Emotion key → filename.
_HUMANOID_CHAR_REFS: dict[str, dict[str, str]] = {
    "Benson": {
        "default": "benson_neutral_ref.png",
        "neutral": "benson_neutral_ref.png",
        "happy_excited": "benson_happy_excited_ref.png",
        "sad_disappointed": "benson_scared_ref.png",
        "upset_shocked": "benson_scared_ref.png",
        "concerned": "benson_scared_ref.png",
        "scared": "benson_scared_ref.png",
        "pleased": "benson_pleased_ref.png",
    },
    "Bork": {
        "default": "bork_imperious_ref.png",
        "neutral": "bork_imperious_ref.png",
        "upset_shocked": "bork_angry_ref.png",
        "scared": "bork_angry_ref.png",
        "angry": "bork_angry_ref.png",
        "announcing_1": "bork_announcing_1_ref.png",
        "announcing_2": "bork_announcing_2_ref.png",
        "doing_a_great_service": "bork_doing_a_great_service_ref.png",
        "imperious": "bork_imperious_ref.png",
    },
    "Bramble": {
        "default": "bramble_neutral_ref.png",
        "neutral": "bramble_neutral_ref.png",
        "happy_excited": "bramble_happy_excited_ref.png",
        "sad_disappointed": "bramble_sad_disappointed_ref.png",
        "upset_shocked": "bramble_upset_shocked_ref.png",
        "concerned": "bramble_sad_disappointed_ref.png",
        "scared": "bramble_upset_shocked_ref.png",
        "angry": "bramble_angry_ref.png",
        "happy_relaxed": "bramble_happy_relaxed_ref.png",
    },
    "Chipper": {
        "default": "Production/Chipper/poses/chipper_canonical_neutral.png",
        "neutral": "Production/Chipper/poses/chipper_canonical_neutral.png",
        "happy_excited": "Production/Chipper/poses/chipper_canonical_branch.png",
        "sad_disappointed": "Production/Chipper/poses/chipper_canonical_concern.png",
        "upset_shocked": "Production/Chipper/poses/chipper_canonical_concern.png",
        "concerned": "Production/Chipper/poses/chipper_canonical_concern.png",
        "scared": "Production/Chipper/poses/chipper_canonical_concern.png",
        "considering": "Production/Chipper/poses/chipper_canonical_neutral.png",
        "explaining": "Production/Chipper/poses/chipper_canonical_branch.png",
    },
    "Ember": {
        "default": "ember_neutral_ref.png",
        "neutral": "ember_neutral_ref.png",
        "happy_excited": "ember_happy_excited_ref.png",
        "sad_disappointed": "ember_sad_disappointed_ref.png",
        "upset_shocked": "ember_upset_shocked_ref.png",
        "concerned": "ember_sad_disappointed_ref.png",
        "scared": "ember_upset_shocked_ref.png",
        "has_a_plan": "ember_has_a_plan_ref.png",
        "leadership": "ember_leadership_ref.png",
    },
    "Grizzle": {
        "default": "grizzle_neutral_ref.png",
        "neutral": "grizzle_neutral_ref.png",
        "upset_shocked": "grizzle_angry_ref.png",
        "scared": "grizzle_angry_ref.png",
        "angry": "grizzle_angry_ref.png",
        "guarding": "grizzle_guarding_ref.png",
    },
    "Luna": {
        "default": "luna_neutral_ref.png",
        "neutral": "luna_neutral_ref.png",
        "happy_excited": "luna_happy_excited_ref.png",
        "sad_disappointed": "luna_sad_disappointed_ref.png",
        "upset_shocked": "luna_sad_disappointed_ref.png",
        "concerned": "luna_sad_disappointed_ref.png",
        "scared": "luna_sad_disappointed_ref.png",
        "crazy_happy_excited": "luna_crazy_happy_excited_ref.png",
        "searching_map": "luna_searching_map_ref.png",
        "thinking": "luna_thinking_ref.png",
    },
    "Mountain King": {
        "default": "mountain_king_neutral_ref.png",
        "neutral": "mountain_king_neutral_ref.png",
        "sad_disappointed": "mountain_king_disappointed_ref.png",
        "upset_shocked": "mountain_king_angry_ref.png",
        "concerned": "mountain_king_disappointed_ref.png",
        "scared": "mountain_king_angry_ref.png",
        "angry": "mountain_king_angry_ref.png",
        "beseaching_begging": "mountain_king_beseaching_begging_ref.png",
        "disappointed": "mountain_king_disappointed_ref.png",
        "imperious": "mountain_king_imperious_ref.png",
    },
    "Oliver": {
        "default": "oliver_neutral_ref.png",
        "neutral": "oliver_neutral_ref.png",
        "happy_excited": "oliver_happy_excited_ref.png",
        "sad_disappointed": "oliver_sad_disappointed_ref.png",
        "upset_shocked": "oliver_upset_shocked_ref.png",
        "concerned": "oliver_sad_disappointed_ref.png",
        "scared": "oliver_upset_shocked_ref.png",
    },
    "Tessa": {
        "default": "tessa_neutral_ref.png",
        "neutral": "tessa_neutral_ref.png",
        "happy_excited": "tessa_happy_excited_ref.png",
        "sad_disappointed": "tessa_sad_disappointed_ref.png",
        "upset_shocked": "tessa_sad_disappointed_ref.png",
        "concerned": "tessa_sad_disappointed_ref.png",
        "scared": "tessa_sad_disappointed_ref.png",
        "happy": "tessa_happy_ref.png",
        "shy": "tessa_shy_ref.png",
        "thoughtful": "tessa_thoughtful_ref.png",
    },
    "Willow": {
        "default": "willow_neutral_ref.png",
        "neutral": "willow_neutral_ref.png",
        "sad_disappointed": "willow_sad_disappointed_ref.png",
        "upset_shocked": "willow_shocked_ref.png",
        "concerned": "willow_sad_disappointed_ref.png",
        "scared": "willow_shocked_ref.png",
        "shocked": "willow_shocked_ref.png",
        "wise_welcoming": "willow_wise_welcoming_ref.png",
    },
}


def _project_root() -> Path:
    return Path(_PROD_DIR).parent


KLING_O3_DURATION_CHOICES = (5, 6, 8, 10, 12)
KLING_O3_MIN_DURATION = 5
KLING_O3_MAX_DURATION = 12
# Post-download: keep at most this much video after last detected speech.
KLING_O3_MAX_POST_SPEECH_TAIL_S = 2.0
KLING_O3_MIN_POST_TRIM_DURATION_S = 2.5
KLING_O3_SILENCE_NOISE_DB = -32
KLING_O3_SILENCE_MIN_DURATION_S = 0.15
# Gentle kid delivery; ellipses overlap with slow speech (not full additive pauses).
_KLING_O3_WPM = 130
_KLING_O3_ELLIPSIS_S = 0.55
_KLING_O3_CUE_MARKER_S = 0.65
_KLING_O3_QUESTION_PAUSE_S = 0.15
_KLING_O3_STAGING_LEAD_S = 1.0
_KLING_O3_TAIL_S = 0.35
# Single-chunk lines at or below this word count stay in the 8s bucket max — Kling
# over-pads speech with long pauses in 10–12s buckets.
_KLING_O3_AUTO_CAP_MAX_WORDS = 30


def _ffmpeg_silence_ranges(media_path: Path) -> list[tuple[float, float]]:
    """Return [(silence_start_s, silence_end_s), ...] via ffmpeg silencedetect."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(media_path),
         "-af", (
             f"silencedetect=noise={KLING_O3_SILENCE_NOISE_DB}dB:"
             f"d={KLING_O3_SILENCE_MIN_DURATION_S}"
         ),
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    out: list[tuple[float, float]] = []
    cur_start: float | None = None
    for line in r.stderr.splitlines():
        if "silence_start:" in line:
            try:
                cur_start = float(line.split("silence_start:")[1].strip().split()[0])
            except (ValueError, IndexError):
                cur_start = None
        elif "silence_end:" in line and cur_start is not None:
            try:
                s_end = float(line.split("silence_end:")[1].strip().split()[0])
                out.append((cur_start, s_end))
            except (ValueError, IndexError):
                pass
            cur_start = None
    return out


def _kling_o3_trailing_silence_start(
    duration_s: float,
    silences: list[tuple[float, float]],
) -> float | None:
    """When clip ends in silence after speech, return when that trailing silence began."""
    if duration_s <= 0 or not silences:
        return None
    for start, end in reversed(silences):
        if end >= duration_s - 0.08 and start >= 0.25:
            return start
    return None


def trim_kling_o3_clip_post_speech(
    video_path: Path,
    *,
    max_tail_s: float = KLING_O3_MAX_POST_SPEECH_TAIL_S,
) -> dict[str, Any]:
    """Trim dead air after dialogue — keep at most `max_tail_s` after last speech.

    Replaces the file in place when trimming. Returns metadata dict for sidecar.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        return {"trimmed": False, "reason": "missing_file"}

    duration_s = _ffprobe_duration(video_path)
    if duration_s <= 0:
        return {"trimmed": False, "reason": "no_duration", "duration_s": duration_s}

    silences = _ffmpeg_silence_ranges(video_path)
    speech_end_s = _kling_o3_trailing_silence_start(duration_s, silences)
    if speech_end_s is None:
        return {
            "trimmed": False,
            "reason": "no_trailing_silence",
            "duration_s": round(duration_s, 3),
        }

    target_s = speech_end_s + max_tail_s
    if duration_s <= target_s + 0.05:
        return {
            "trimmed": False,
            "reason": "within_tail_budget",
            "duration_s": round(duration_s, 3),
            "speech_end_s": round(speech_end_s, 3),
            "max_tail_s": max_tail_s,
        }

    target_s = max(target_s, KLING_O3_MIN_POST_TRIM_DURATION_S)
    tmp = video_path.with_suffix(".trim_tmp.mp4")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-t", f"{target_s:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not tmp.is_file():
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        return {
            "trimmed": False,
            "reason": "ffmpeg_failed",
            "duration_s": round(duration_s, 3),
            "stderr": (r.stderr or "")[-500:],
        }

    new_duration_s = _ffprobe_duration(tmp)
    if new_duration_s <= 0:
        tmp.unlink(missing_ok=True)
        return {"trimmed": False, "reason": "trim_probe_failed", "duration_s": round(duration_s, 3)}

    tmp.replace(video_path)
    return {
        "trimmed": True,
        "before_s": round(duration_s, 3),
        "after_s": round(new_duration_s, 3),
        "speech_end_s": round(speech_end_s, 3),
        "max_tail_s": max_tail_s,
    }


def resolve_kling_o3_trim_window(
    beat: dict,
    *,
    video_path: str | Path | None = None,
) -> tuple[float, float, float]:
    """Return (trim_start_s, trim_end_s, raw_duration_s) for a beat Kling clip.

    trim_end_s is an absolute timestamp on the source file (not relative back-trim).
    When no trim is set, trim_end_s == raw_duration_s.
    """
    path = Path(video_path or beat.get("kling_o3_video_path") or "")
    raw_dur = _ffprobe_duration(path) if path.is_file() else 0.0
    trim_start = max(0.0, float(beat.get("kling_o3_trim_start") or 0.0))
    trim_back = beat.get("kling_o3_trim_back")
    if trim_back is not None and float(trim_back) > 0 and raw_dur > 0:
        trim_end = max(trim_start + 0.01, raw_dur - float(trim_back))
    elif beat.get("kling_o3_trim_end") is not None and raw_dur > 0:
        trim_end = float(beat["kling_o3_trim_end"])
        trim_end = max(trim_start + 0.01, min(trim_end, raw_dur))
    else:
        trim_end = raw_dur
    return trim_start, trim_end, raw_dur


def kling_o3_trim_is_active(beat: dict, *, raw_dur: float | None = None) -> bool:
    """True when beat has a non-default trim window on its Kling clip."""
    if raw_dur is None:
        path = beat.get("kling_o3_video_path") or ""
        raw_dur = _ffprobe_duration(Path(path)) if path and os.path.isfile(path) else 0.0
    if raw_dur <= 0:
        return False
    trim_start, trim_end, _ = resolve_kling_o3_trim_window(beat, video_path=beat.get("kling_o3_video_path"))
    return trim_start > 0.01 or trim_end < raw_dur - 0.05


def set_kling_o3_beat_trim(
    beat: dict,
    *,
    trim_start: float,
    trim_back: float | None,
) -> dict[str, Any]:
    """Validate and persist manual trim metadata on a Kling O3 beat."""
    path = beat.get("kling_o3_video_path") or ""
    if not path or not os.path.isfile(path):
        raise ValueError("No Kling video on beat — generate a clip before trimming")
    raw_dur = _ffprobe_duration(Path(path))
    if raw_dur <= 0:
        raise ValueError("Could not read clip duration")

    start = max(0.0, float(trim_start))
    back = None if trim_back is None else max(0.0, float(trim_back))
    if back is not None and back > 0:
        end = max(start + 0.01, raw_dur - back)
    else:
        end = raw_dur
    if end <= start:
        raise ValueError(
            f"Trim window invalid: start={start:.2f}s end={end:.2f}s raw={raw_dur:.2f}s",
        )

    beat["kling_o3_trim_start"] = round(start, 2)
    if back is not None and back > 0:
        beat["kling_o3_trim_back"] = round(back, 2)
        beat.pop("kling_o3_trim_end", None)
    else:
        beat["kling_o3_trim_back"] = None
        beat.pop("kling_o3_trim_end", None)

    effective = end - start
    return {
        "trim_start": beat["kling_o3_trim_start"],
        "trim_back": beat.get("kling_o3_trim_back"),
        "trim_end": round(end, 2),
        "raw_duration_s": round(raw_dur, 3),
        "effective_duration_s": round(effective, 3),
    }


def clear_kling_o3_beat_trim(beat: dict) -> None:
    for key in ("kling_o3_trim_start", "kling_o3_trim_back", "kling_o3_trim_end"):
        beat.pop(key, None)
    clear_o3_baked_fields(beat)


MIN_O3_CUT_S = 0.25


def clear_o3_cut_fields(target: dict) -> None:
    for key in ("cut_start_s", "cut_end_s", "kling_o3_cut_start_s", "kling_o3_cut_end_s"):
        target.pop(key, None)


def find_o3_option_by_video_path(beat: dict, video_path: str) -> dict | None:
    vp = str(video_path or "").strip()
    if not vp:
        return None
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        if str(opt.get("video_path") or "").strip() == vp:
            return opt
    return None


def is_user_selectable_o3_video(
    video_path: str | None,
    source: str | None = None,
) -> bool:
    """Match Beat Gen UI — exclude silent/base/delivery-input artifacts."""
    if source in ("still_insert_static_hold", "still_insert_ken_burns", "still_insert_kling_idle"):
        return bool(video_path)
    name = Path(video_path or "").name.lower()
    return bool(video_path) and not any(
        marker in name
        for marker in ("_silent_o3_base", "_delivery_input", "_noaudio")
    )


def build_fixed_o3_ui_slots(
    beat: dict,
    *,
    generation_mode: str | None = None,
    sidecar: dict | None = None,
) -> list[dict | None]:
    """Mirror Beat Gen ``buildFixedO3OptionSlots`` — fixed containers by ``slot_index``."""
    mode = generation_mode
    if not mode and sidecar is not None:
        mode = resolve_beat_generation_mode(beat, sidecar)
    if not mode:
        mode = resolve_beat_generation_mode(beat, {})
    slots: list[dict | None] = [None, None, None]
    o3_history = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict)
        and is_user_selectable_o3_video(
            str(o.get("video_path") or ""),
            o.get("source"),
        )
        and o3_option_visible_in_ui_slots(o, mode)
    ]
    active_path = str(beat.get("kling_o3_video_path") or "").strip()
    if not is_user_selectable_o3_video(active_path):
        active_path = ""

    placed: set[str] = set()
    for opt in o3_history:
        si = opt.get("slot_index")
        if isinstance(si, int) and 0 <= si <= 2 and slots[si] is None:
            slots[si] = opt
            placed.add(str(opt.get("video_path") or ""))

    def _gen(opt: dict) -> int:
        g = opt.get("generation")
        if isinstance(g, int):
            return g
        return _kling_o3_gen_from_video_path(str(opt.get("video_path") or "")) or 0

    unslotted = sorted(
        [o for o in o3_history if str(o.get("video_path") or "") not in placed],
        key=_gen,
        reverse=True,
    )
    for opt in unslotted:
        for si in range(3):
            if slots[si] is None:
                slots[si] = opt
                placed.add(str(opt.get("video_path") or ""))
                break

    active_listed = active_path and any(
        isinstance(s, dict) and str(s.get("video_path") or "").strip() == active_path
        for s in slots
    )
    if beat.get("kling_o3_status") == "approved" and active_path and not active_listed:
        active_opt = next(
            (
                o for o in o3_history
                if str(o.get("video_path") or "").strip() == active_path
            ),
            None,
        )
        for si in range(3):
            if slots[si] is None:
                slots[si] = active_opt or {
                    "key": f"{beat.get('beat_id')}_approved_o3_video",
                    "label": "approved O3 video",
                    "video_path": active_path,
                    "source": "approved_kling_o3_video",
                    "slot_index": si,
                }
                break
    return slots


def find_o3_option_by_slot_index(
    beat: dict,
    slot_index: int,
    *,
    video_path: str | None = None,
) -> dict | None:
    """Resolve UI container 0–2 using pin-slot layout (``slot_index`` on each option)."""
    slots = build_fixed_o3_ui_slots(beat)
    idx = max(0, min(2, int(slot_index)))
    slot_opt = slots[idx]
    if video_path:
        vp = str(video_path).strip()
        slot_vp = str((slot_opt or {}).get("video_path") or "").strip()
        if vp and slot_vp != vp:
            direct = find_o3_option_by_video_path(beat, vp)
            if direct is not None:
                return direct
            raise ValueError(f"video_path not in beat O3 options: {vp}")
    return slot_opt if isinstance(slot_opt, dict) else None


def option_has_o3_cut(opt: dict | None) -> bool:
    if not isinstance(opt, dict):
        return False
    start = float(opt.get("cut_start_s") or 0.0)
    end = float(opt.get("cut_end_s") or 0.0)
    return end > start + MIN_O3_CUT_S - 0.001


def resolve_o3_cut_window(
    beat: dict,
    *,
    video_path: str | Path | None = None,
) -> tuple[float, float, float]:
    """Return (cut_start_s, cut_end_s, raw_duration_s) — region TO REMOVE."""
    path = Path(video_path or beat.get("kling_o3_video_path") or "")
    raw_dur = _ffprobe_duration(path) if path.is_file() else 0.0
    start = float(beat.get("kling_o3_cut_start_s") or 0.0)
    end = float(beat.get("kling_o3_cut_end_s") or 0.0)
    if end <= start + 0.001:
        return 0.0, 0.0, raw_dur
    if raw_dur > 0:
        end = min(end, raw_dur)
        start = max(0.0, min(start, end - 0.01))
    return start, end, raw_dur


def o3_cut_is_active(
    beat: dict,
    *,
    raw_dur: float | None = None,
    video_path: str | Path | None = None,
) -> bool:
    path = Path(video_path or beat.get("kling_o3_video_path") or "")
    if raw_dur is None:
        raw_dur = _ffprobe_duration(path) if path.is_file() else 0.0
    if raw_dur <= 0:
        return False
    cut_start, cut_end, _ = resolve_o3_cut_window(beat, video_path=path)
    if cut_end <= cut_start + MIN_O3_CUT_S - 0.001:
        return False
    kept = cut_start + max(0.0, raw_dur - cut_end)
    return kept >= MIN_O3_CUT_S and (cut_end - cut_start) >= MIN_O3_CUT_S - 0.001


def beat_has_o3_sidecar_cut(beat: dict) -> bool:
    return o3_cut_is_active(beat)


def mirror_beat_cut_from_option(beat: dict, opt: dict | None) -> None:
    clear_o3_cut_fields(beat)
    if option_has_o3_cut(opt):
        beat["kling_o3_cut_start_s"] = round(float(opt["cut_start_s"]), 2)
        beat["kling_o3_cut_end_s"] = round(float(opt["cut_end_s"]), 2)


def hydrate_beat_cut_from_active_option(beat: dict) -> None:
    """Copy cut metadata from the active O3 option row onto the beat cache."""
    vp = beat.get("kling_o3_video_path") or ""
    opt = find_o3_option_by_video_path(beat, vp)
    mirror_beat_cut_from_option(beat, opt)


def set_o3_option_cut(
    beat: dict,
    *,
    slot_index: int,
    cut_start_s: float,
    cut_end_s: float,
    video_path: str | None = None,
) -> dict[str, Any]:
    """Validate and persist cut-out window on one O3 option row."""
    opt = find_o3_option_by_slot_index(
        beat,
        slot_index,
        video_path=video_path,
    )
    if opt is None:
        raise ValueError(f"No O3 option in slot {slot_index}")
    vp = str(video_path or opt.get("video_path") or "").strip()
    if not vp or not os.path.isfile(vp):
        raise ValueError("No Kling video on option — select a clip before cutting")
    raw_dur = _ffprobe_duration(Path(vp))
    if raw_dur <= 0:
        raise ValueError("Could not read clip duration")

    start = max(0.0, float(cut_start_s))
    end = max(start + MIN_O3_CUT_S, float(cut_end_s))
    end = min(end, raw_dur)
    if end <= start + MIN_O3_CUT_S - 0.001:
        raise ValueError(
            f"Cut region too small: start={start:.2f}s end={end:.2f}s raw={raw_dur:.2f}s",
        )
    kept = start + max(0.0, raw_dur - end)
    if kept < MIN_O3_CUT_S:
        raise ValueError(
            f"Cut would remove entire clip: start={start:.2f}s end={end:.2f}s raw={raw_dur:.2f}s",
        )

    opt["cut_start_s"] = round(start, 2)
    opt["cut_end_s"] = round(end, 2)
    if str(beat.get("kling_o3_video_path") or "").strip() == vp:
        mirror_beat_cut_from_option(beat, opt)

    effective = raw_dur - (end - start)
    return {
        "cut_start_s": opt["cut_start_s"],
        "cut_end_s": opt["cut_end_s"],
        "raw_duration_s": round(raw_dur, 3),
        "effective_duration_s": round(effective, 3),
        "video_path": vp,
        "slot_index": max(0, min(2, int(slot_index))),
    }


def clear_o3_option_cut(
    beat: dict,
    *,
    slot_index: int,
    video_path: str | None = None,
) -> None:
    opt = find_o3_option_by_slot_index(
        beat,
        slot_index,
        video_path=video_path,
    )
    if isinstance(opt, dict):
        clear_o3_cut_fields(opt)
    vp = (opt or {}).get("video_path") or ""
    if str(beat.get("kling_o3_video_path") or "").strip() == str(vp).strip():
        clear_o3_cut_fields(beat)


def option_has_o3_trim(opt: dict | None) -> bool:
    if not isinstance(opt, dict):
        return False
    start = float(opt.get("trim_start_s") or 0.0)
    back = opt.get("trim_back_s")
    back_val = float(back) if back is not None else 0.0
    return start > 0.01 or back_val > 0.05


def clear_o3_option_trim_fields(target: dict) -> None:
    for key in ("trim_start_s", "trim_back_s"):
        target.pop(key, None)
    clear_o3_baked_fields(target)


def mirror_beat_trim_from_option(beat: dict, opt: dict | None) -> None:
    clear_kling_o3_beat_trim(beat)
    clear_o3_cut_fields(beat)
    if option_has_o3_trim(opt):
        beat["kling_o3_trim_start"] = round(float(opt.get("trim_start_s") or 0.0), 2)
        back = opt.get("trim_back_s")
        if back is not None and float(back) > 0.05:
            beat["kling_o3_trim_back"] = round(float(back), 2)
        else:
            beat.pop("kling_o3_trim_back", None)


def hydrate_beat_trim_from_active_option(beat: dict) -> None:
    vp = beat.get("kling_o3_video_path") or ""
    opt = find_o3_option_by_video_path(beat, vp)
    mirror_beat_trim_from_option(beat, opt)


def migrate_o3_option_edge_cut_to_trim(opt: dict, *, raw_dur: float) -> bool:
    """Convert legacy head/tail cut-out rows to front/back trim (middle cuts unchanged)."""
    if not isinstance(opt, dict) or option_has_o3_trim(opt) or not option_has_o3_cut(opt):
        return False
    if raw_dur <= 0:
        return False
    start = float(opt.get("cut_start_s") or 0.0)
    end = float(opt.get("cut_end_s") or 0.0)
    if end <= start + MIN_O3_CUT_S - 0.001:
        return False
    changed = False
    if start <= 0.01 and end < raw_dur - 0.05:
        opt["trim_start_s"] = round(end, 2)
        clear_o3_cut_fields(opt)
        changed = True
    elif end >= raw_dur - 0.05 and start > 0.01:
        opt["trim_back_s"] = round(max(0.0, raw_dur - start), 2)
        clear_o3_cut_fields(opt)
        changed = True
    return changed


def migrate_o3_options_edge_cut_to_trim(beat: dict) -> bool:
    changed = False
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        vp = str(opt.get("video_path") or "").strip()
        raw_dur = _ffprobe_duration(Path(vp)) if vp and os.path.isfile(vp) else 0.0
        if migrate_o3_option_edge_cut_to_trim(opt, raw_dur=raw_dur):
            changed = True
    if changed:
        hydrate_beat_trim_from_active_option(beat)
        hydrate_beat_cut_from_active_option(beat)
    return changed


def _event_id_from_event_dir(event_dir: str | Path) -> str:
    name = Path(event_dir).name
    if name.startswith("Event_"):
        return name.replace("Event_", "")
    return name or "unknown"


def migrate_segment_o3_trims_for_export(beats: list[dict]) -> bool:
    """Convert edge cut-out rows to trim before Send to Stitcher materialize."""
    changed = False
    for beat in beats:
        if migrate_o3_options_edge_cut_to_trim(beat):
            changed = True
        if heal_invalid_kling_o3_trim(beat):
            changed = True
    return changed


def clear_o3_baked_fields(target: dict) -> None:
    target.pop("kling_o3_baked_path", None)
    target.pop("kling_o3_baked_token", None)


def o3_baked_export_token(beat: dict, *, video_path: str | Path | None = None) -> str:
    gen = int(beat.get("kling_o3_generation") or 0)
    vp = str(video_path or beat.get("kling_o3_video_path") or "")
    src = Path(vp) if vp else Path()
    raw_dur = _ffprobe_duration(src) if src.is_file() else 0.0
    if o3_cut_is_active(beat, raw_dur=raw_dur, video_path=src):
        cut_token = kling_o3_cut_scratch_token(beat, video_path=vp)
        return f"g{gen}_{cut_token}_baked"
    if kling_o3_trim_is_active(beat, raw_dur=raw_dur):
        return f"g{gen}_{kling_o3_trim_scratch_token(beat)}_baked"
    return f"g{gen}_full"


def bake_o3_active_export_clip(
    beat: dict,
    event_dir: str | Path,
    *,
    slot_index: int | None = None,
    video_path: str | None = None,
) -> dict[str, Any]:
    """Materialize active trim/cut to stable baked MP4 at Apply (same path as export)."""
    event_dir = Path(event_dir)
    opt = None
    if slot_index is not None:
        opt = find_o3_option_by_slot_index(beat, int(slot_index), video_path=video_path)
        if isinstance(opt, dict) and opt.get("video_path"):
            beat = copy.deepcopy(beat)
            beat["kling_o3_video_path"] = opt["video_path"]
            hydrate_beat_trim_from_active_option(beat)
            hydrate_beat_cut_from_active_option(beat)
    src = Path(video_path or beat.get("kling_o3_video_path") or "")
    if not src.is_file():
        raise ValueError(f"missing clip for bake: {src}")
    raw_dur = _ffprobe_duration(src)
    if not o3_cut_is_active(beat, raw_dur=raw_dur, video_path=src) and not kling_o3_trim_is_active(
        beat, raw_dur=raw_dur,
    ):
        clear_o3_baked_fields(beat)
        if isinstance(opt, dict):
            clear_o3_baked_fields(opt)
        return {"baked": False, "baked_path": str(src.resolve())}

    scratch_dir = event_dir / "assembled" / "_kling_o3_trim_scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    token = o3_baked_export_token(beat, video_path=src)
    dest = scratch_dir / f"{beat.get('beat_id')}_{token}.mp4"
    if kling_o3_trim_is_active(beat, raw_dur=raw_dur):
        materialize_kling_o3_trimmed_clip(
            beat, dest, source_path=src, event_dir=event_dir,
        )
    else:
        materialize_o3_cut_out_clip(
            beat, dest, source_path=src, event_dir=event_dir,
        )
    baked_path = dest
    beat["kling_o3_baked_path"] = str(baked_path.resolve())
    beat["kling_o3_baked_token"] = token
    if isinstance(opt, dict):
        opt["kling_o3_baked_path"] = beat["kling_o3_baked_path"]
        opt["kling_o3_baked_token"] = token
    return {
        "baked": True,
        "baked_path": beat["kling_o3_baked_path"],
        "baked_token": token,
        "effective_duration_s": round(_ffprobe_duration(baked_path), 3),
    }


def promote_o3_baked_trim_to_active_clip(
    beat: dict,
    *,
    baked_path: str | Path,
    slot_index: int | None = None,
    video_path: str | None = None,
) -> dict[str, Any]:
    """After Apply trim bake: make baked MP4 the active clip and clear trim metadata.

    Prevents double-trim when UI/server ffprobe sees a shorter file but trim_back
    is still relative to the pre-bake delivery duration.
    """
    baked = Path(baked_path)
    if not baked.is_file():
        raise ValueError(f"missing baked clip: {baked}")
    baked_str = str(baked.resolve())
    opt = None
    if slot_index is not None:
        opt = find_o3_option_by_slot_index(
            beat, int(slot_index), video_path=video_path,
        )
    old_vp = str(beat.get("kling_o3_video_path") or "").strip()
    beat["kling_o3_video_path"] = baked_str
    clear_kling_o3_beat_trim(beat)
    clear_o3_cut_fields(beat)
    clear_o3_baked_fields(beat)
    if isinstance(opt, dict):
        opt["video_path"] = baked_str
        clear_o3_option_trim_fields(opt)
        clear_o3_cut_fields(opt)
        clear_o3_baked_fields(opt)
    elif old_vp:
        opt_by_path = find_o3_option_by_video_path(beat, old_vp)
        if isinstance(opt_by_path, dict):
            opt_by_path["video_path"] = baked_str
            clear_o3_option_trim_fields(opt_by_path)
            clear_o3_cut_fields(opt_by_path)
            clear_o3_baked_fields(opt_by_path)
    eff = _ffprobe_duration(baked)
    return {
        "video_path": baked_str,
        "effective_duration_s": round(eff, 3) if eff > 0 else None,
        "trim_start": 0.0,
        "trim_back": None,
    }


def o3_trim_shortening_requested(
    trim_start: float,
    trim_back: float | None,
    *,
    epsilon: float = 0.05,
) -> bool:
    """True when the operator asked to remove head and/or tail (not full-clip keep)."""
    return float(trim_start) > epsilon or (
        trim_back is not None and float(trim_back) > epsilon
    )


def o3_trim_effective_is_shorter(
    raw_duration_s: float,
    effective_duration_s: float | None,
    *,
    epsilon: float = 0.05,
) -> bool:
    """True when kept duration is materially shorter than the source clip."""
    if effective_duration_s is None or raw_duration_s <= 0:
        return False
    return float(effective_duration_s) < float(raw_duration_s) - epsilon


def set_o3_option_trim(
    beat: dict,
    *,
    slot_index: int,
    trim_start: float,
    trim_back: float | None,
    video_path: str | None = None,
) -> dict[str, Any]:
    """Validate and persist front/back trim on one O3 option row (start + end crop)."""
    opt = find_o3_option_by_slot_index(
        beat,
        slot_index,
        video_path=video_path,
    )
    if opt is None:
        raise ValueError(f"No O3 option in slot {slot_index}")
    vp = str(video_path or opt.get("video_path") or "").strip()
    if not vp or not os.path.isfile(vp):
        raise ValueError("No Kling video on option — select a clip before trimming")
    raw_dur = _ffprobe_duration(Path(vp))
    if raw_dur <= 0:
        raise ValueError("Could not read clip duration")

    start = max(0.0, float(trim_start))
    back = None if trim_back is None else max(0.0, float(trim_back))
    if back is not None and back > 0:
        end = max(start + MIN_O3_CUT_S, raw_dur - back)
    else:
        end = raw_dur
    if end <= start + MIN_O3_CUT_S - 0.001:
        raise ValueError(
            f"Trim window too small: start={start:.2f}s end={end:.2f}s raw={raw_dur:.2f}s",
        )

    clear_o3_cut_fields(opt)
    opt["trim_start_s"] = round(start, 2)
    if back is not None and back > 0.05:
        opt["trim_back_s"] = round(back, 2)
    else:
        opt.pop("trim_back_s", None)

    if str(beat.get("kling_o3_video_path") or "").strip() == vp:
        mirror_beat_trim_from_option(beat, opt)

    effective = end - start
    return {
        "trim_start": opt["trim_start_s"],
        "trim_back": opt.get("trim_back_s"),
        "trim_end": round(end, 2),
        "raw_duration_s": round(raw_dur, 3),
        "effective_duration_s": round(effective, 3),
        "video_path": vp,
        "slot_index": max(0, min(2, int(slot_index))),
    }


def clear_o3_option_trim(
    beat: dict,
    *,
    slot_index: int,
    video_path: str | None = None,
) -> None:
    opt = find_o3_option_by_slot_index(
        beat,
        slot_index,
        video_path=video_path,
    )
    if isinstance(opt, dict):
        clear_o3_option_trim_fields(opt)
    vp = (opt or {}).get("video_path") or ""
    if str(beat.get("kling_o3_video_path") or "").strip() == str(vp).strip():
        clear_kling_o3_beat_trim(beat)


def heal_invalid_o3_cut(beat: dict) -> bool:
    """Clear cut when it exceeds the active clip duration."""
    path = beat.get("kling_o3_video_path") or ""
    if not path or not os.path.isfile(path):
        return False
    if not beat_has_o3_sidecar_cut(beat):
        return False
    raw_dur = _ffprobe_duration(Path(path))
    if raw_dur <= 0:
        clear_o3_cut_fields(beat)
        opt = find_o3_option_by_video_path(beat, path)
        if isinstance(opt, dict):
            clear_o3_cut_fields(opt)
        return True
    cut_start, cut_end, _ = resolve_o3_cut_window(beat, video_path=path)
    if o3_cut_is_active(beat, raw_dur=raw_dur, video_path=path):
        return False
    clear_o3_cut_fields(beat)
    opt = find_o3_option_by_video_path(beat, path)
    if isinstance(opt, dict):
        clear_o3_cut_fields(opt)
    return True


def heal_invalid_o3_cut_all_options(beat: dict) -> bool:
    """Heal cut on every option row; mirror active clip to beat cache."""
    changed = heal_invalid_o3_cut(beat)
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        vp = opt.get("video_path") or ""
        if not vp or not os.path.isfile(vp):
            if option_has_o3_cut(opt):
                clear_o3_cut_fields(opt)
                changed = True
            continue
        raw_dur = _ffprobe_duration(Path(vp))
        if raw_dur <= 0:
            continue
        start = float(opt.get("cut_start_s") or 0.0)
        end = float(opt.get("cut_end_s") or 0.0)
        if end <= start + MIN_O3_CUT_S - 0.001:
            if "cut_start_s" in opt or "cut_end_s" in opt:
                clear_o3_cut_fields(opt)
                changed = True
            continue
        kept = start + max(0.0, raw_dur - end)
        remove_len = end - start
        if kept < MIN_O3_CUT_S or remove_len < MIN_O3_CUT_S - 0.001 or end > raw_dur + 0.05:
            clear_o3_cut_fields(opt)
            changed = True
    hydrate_beat_cut_from_active_option(beat)
    return changed


def materialize_o3_cut_out_clip(
    beat: dict,
    dest: Path,
    *,
    source_path: Path | None = None,
    event_dir: str | Path | None = None,
) -> Path:
    """Remove [cut_start_s, cut_end_s) from clip; write kept A+V to dest."""
    src = source_path or Path(beat.get("kling_o3_video_path") or "")
    if not src.is_file():
        raise FileNotFoundError(f"missing clip: {src}")
    cut_start, cut_end, raw_dur = resolve_o3_cut_window(beat, video_path=src)
    if not o3_cut_is_active(beat, raw_dur=raw_dur, video_path=src):
        copy_file_durable(src, dest)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    event_id = _event_id_from_event_dir(event_dir or src.parent.parent)
    local_src = ensure_local_media(src, event_id=event_id)

    if cut_start <= 0.001:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{cut_end:.3f}",
            "-i", str(local_src),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(dest),
        ]
    elif cut_end >= raw_dur - 0.001:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-t", f"{cut_start:.3f}",
            "-i", str(local_src),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(dest),
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(local_src),
            "-filter_complex",
            (
                f"[0:v]trim=0:{cut_start:.3f},setpts=PTS-STARTPTS[v1];"
                f"[0:a]atrim=0:{cut_start:.3f},asetpts=PTS-STARTPTS[a1];"
                f"[0:v]trim={cut_end:.3f}:{raw_dur:.3f},setpts=PTS-STARTPTS[v2];"
                f"[0:a]atrim={cut_end:.3f}:{raw_dur:.3f},asetpts=PTS-STARTPTS[a2];"
                f"[v1][a1][v2][a2]concat=n=2:v=1:a=1[outv][outa]"
            ),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(dest),
        ]

    run_ffmpeg_to_dest(cmd, dest, timeout=240, error_prefix="ffmpeg cut-out failed")
    return dest


def kling_o3_cut_scratch_token(beat: dict, *, video_path: str | None = None) -> str:
    """Stable filename token for cut scratch files (gen + cut window + clip id)."""
    gen = int(beat.get("kling_o3_generation") or 0)
    start = round(float(beat.get("kling_o3_cut_start_s") or 0.0), 2)
    end = round(float(beat.get("kling_o3_cut_end_s") or 0.0), 2)
    vp = str(video_path or beat.get("kling_o3_video_path") or "")
    clip_id = hashlib.sha1(vp.encode("utf-8")).hexdigest()[:8] if vp else "noclip"
    return f"g{gen}_{clip_id}_c{start}_{end}"


def kling_o3_trim_scratch_token(beat: dict) -> str:
    """Stable filename token for trim scratch files (gen + front/back window)."""
    start = round(float(beat.get("kling_o3_trim_start") or 0.0), 2)
    back = beat.get("kling_o3_trim_back")
    back_val = round(float(back), 2) if back is not None and float(back) > 0 else 0.0
    return f"s{start}_b{back_val}"


def kling_o3_ui_trim_preview_path(
    beat_id: str,
    event_dir: str | Path,
    beat: dict,
) -> Path:
    """Scratch path for ffmpeg WYSIWYG trim/cut preview — unique per gen + window."""
    scratch = Path(event_dir) / "assembled" / "_kling_o3_trim_scratch"
    if beat_has_o3_sidecar_cut(beat):
        token = kling_o3_cut_scratch_token(beat)
        return scratch / f"{beat_id}_{token}_ui_preview.mp4"
    gen = int(beat.get("kling_o3_generation") or 0)
    token = kling_o3_trim_scratch_token(beat)
    return scratch / f"{beat_id}_g{gen}_{token}_ui_preview.mp4"


def invalidate_kling_o3_trim_scratch(beat_id: str, event_dir: str | Path) -> None:
    """Remove stale trim preview/export scratch files when trim clears or clip changes."""
    scratch = Path(event_dir) / "assembled" / "_kling_o3_trim_scratch"
    if not scratch.is_dir():
        return
    bid = str(beat_id or "").strip()
    if not bid:
        return
    for path in scratch.glob(f"{bid}_*"):
        name = path.name
        if (
            "_ui_preview" in name
            or "_export_trim" in name
            or "_export_cut" in name
            or name.endswith("_ui_trim_preview.mp4")
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def beat_has_kling_o3_sidecar_trim(beat: dict) -> bool:
    """True when sidecar holds active front/back trim or cut-out metadata."""
    if beat_has_o3_sidecar_cut(beat):
        return True
    start = float(beat.get("kling_o3_trim_start") or 0.0)
    back = beat.get("kling_o3_trim_back")
    if start > 0.01:
        return True
    if back is not None and float(back) > 0.05:
        return True
    return False


def enrich_beat_magic_video_source_path(beat: dict, event_dir: str | Path) -> None:
    """API field for magic path picker — trimmed/cut scratch path when trim/cut active."""
    vp = (beat.get("kling_o3_video_path") or "").strip()
    if not vp:
        beat.pop("kling_o3_magic_video_source_path", None)
        return
    if beat_has_kling_o3_sidecar_trim(beat):
        beat_id = str(beat.get("beat_id") or "beat").strip()
        beat["kling_o3_magic_video_source_path"] = str(
            kling_o3_ui_trim_preview_path(beat_id, event_dir, beat),
        )
    else:
        beat["kling_o3_magic_video_source_path"] = vp


def _kling_o3_trim_scratch_keep_paths(
    beat_id: str,
    event_dir: str | Path,
    beat: dict,
) -> set[Path]:
    """Preview/export scratch paths that match the beat's current trim/cut window."""
    scratch = Path(event_dir) / "assembled" / "_kling_o3_trim_scratch"
    keep: set[Path] = set()
    if beat_has_o3_sidecar_cut(beat):
        token = kling_o3_cut_scratch_token(beat)
        keep.add((scratch / f"{beat_id}_{token}_ui_preview.mp4").resolve())
        keep.add((scratch / f"{beat_id}_{token}_export_cut.mp4").resolve())
    if beat_has_kling_o3_sidecar_trim(beat) and not beat_has_o3_sidecar_cut(beat):
        gen = int(beat.get("kling_o3_generation") or 0)
        token = kling_o3_trim_scratch_token(beat)
        keep.add((scratch / f"{beat_id}_g{gen}_{token}_ui_preview.mp4").resolve())
        keep.add((scratch / f"{beat_id}_g{gen}_{token}_export_trim.mp4").resolve())
    return keep


def prune_stale_kling_o3_trim_scratch(
    beat_id: str,
    event_dir: str | Path,
    beat: dict,
) -> int:
    """Drop legacy fixed-name and wrong-token trim scratch files for one beat."""
    scratch = Path(event_dir) / "assembled" / "_kling_o3_trim_scratch"
    if not scratch.is_dir():
        return 0
    bid = str(beat_id or "").strip()
    if not bid:
        return 0
    keep = (
        _kling_o3_trim_scratch_keep_paths(bid, event_dir, beat)
        if beat_has_kling_o3_sidecar_trim(beat)
        else set()
    )
    removed = 0
    for path in scratch.glob(f"{bid}_*"):
        name = path.name
        if not (
            "_ui_preview" in name
            or "_export_trim" in name
            or "_export_cut" in name
            or name.endswith("_ui_trim_preview.mp4")
        ):
            continue
        if path.resolve() in keep:
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    return removed


def reconcile_kling_o3_trim_all_events(sidecar: dict, prod_root: str | Path | None = None) -> int:
    """Heal invalid trim metadata and purge stale scratch previews for every beat/event."""
    changed = 0
    beats: list[dict] = []
    for arc in (sidecar.get("arcs") or {}).values():
        for seg in (arc.get("segments") or {}).values():
            for beat in seg.get("beats") or []:
                if isinstance(beat, dict):
                    beats.append(beat)
    for beat in beats:
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id:
            continue
        from beatgen_scope import BeatGenScopeError  # noqa: PLC0415
        from o3_generation_intent import resolve_o3_job_event_dir  # noqa: PLC0415

        root = Path(prod_root or _PROD_DIR)
        try:
            event_dir = event_dir_for_beat_id(beat_id)
        except BeatGenScopeError:
            event_dir = resolve_o3_job_event_dir(
                beat_id,
                server_event_dir=root / "Event_1",
                library_event_dir=root / "Event_1",
            )
        if not event_dir.is_dir():
            continue
        if heal_invalid_o3_cut_all_options(beat):
            changed += 1
        elif heal_invalid_kling_o3_trim(beat):
            changed += 1
        has_trim = beat_has_kling_o3_sidecar_trim(beat)
        scratch = event_dir / "assembled" / "_kling_o3_trim_scratch"
        if not scratch.is_dir():
            continue
        has_stale = any(
            (
                "_ui_preview" in p.name
                or "_export_trim" in p.name
                or p.name.endswith("_ui_trim_preview.mp4")
            )
            for p in scratch.glob(f"{beat_id}_*")
        )
        if not has_stale:
            continue
        if not has_trim:
            invalidate_kling_o3_trim_scratch(beat_id, event_dir)
            changed += 1
        else:
            pruned = prune_stale_kling_o3_trim_scratch(beat_id, event_dir, beat)
            if pruned:
                changed += 1
    return changed


def heal_invalid_kling_o3_trim(beat: dict) -> bool:
    """Clear trim when it exceeds the active clip (e.g. g8 trim kept after g9 lands)."""
    path = beat.get("kling_o3_video_path") or ""
    if not path or not os.path.isfile(path):
        return False
    start = float(beat.get("kling_o3_trim_start") or 0.0)
    back = beat.get("kling_o3_trim_back")
    if start <= 0.01 and (back is None or float(back) <= 0.05):
        return False
    raw_dur = _ffprobe_duration(Path(path))
    if raw_dur <= 0:
        return False
    trim_start, trim_end, _ = resolve_kling_o3_trim_window(beat, video_path=path)
    effective = trim_end - trim_start
    if effective >= 0.25 and trim_end > trim_start + 0.01:
        return False
    clear_kling_o3_beat_trim(beat)
    return True


def still_insert_sidecar_trim_pending(beat: dict) -> bool:
    """True when beat has unsaved-to-file trim metadata (front/back > 0)."""
    start = float(beat.get("kling_o3_trim_start") or 0.0)
    back = beat.get("kling_o3_trim_back")
    if start > 0.01:
        return True
    if back is not None and float(back) > 0.05:
        return True
    return False


def bake_still_insert_trim_into_clip(
    beat: dict,
    *,
    source_path: Path | str | None = None,
) -> dict:
    """Materialize trim window into the active still-insert mp4; clear trim metadata."""
    src = Path(source_path or beat.get("kling_o3_video_path") or "")
    if not src.is_file():
        raise ValueError(f"missing still clip: {src}")
    raw_dur = _ffprobe_duration(src)
    if not kling_o3_trim_is_active(beat, raw_dur=raw_dur):
        return {"baked": False, "video_path": str(src.resolve())}
    stem = src.stem
    if stem.endswith("_trimmed"):
        dest = src.with_name(f"{stem}_{int(time.time())}{src.suffix}")
    else:
        dest = src.with_name(f"{stem}_trimmed{src.suffix}")
    materialize_kling_o3_trimmed_clip(beat, dest, source_path=src)
    new_path = str(dest.resolve())
    old_path = str(src.resolve())
    beat["kling_o3_video_path"] = new_path
    for o in beat.get("kling_o3_options") or []:
        if not isinstance(o, dict):
            continue
        if (o.get("video_path") or "") in (old_path, str(src)):
            o["video_path"] = new_path
    clear_kling_o3_beat_trim(beat)
    return {"baked": True, "video_path": new_path, "source_path": old_path}


def clear_kling_o3_redo_generation_slot(beat: dict, event_dir: str | Path) -> None:
    """Remove stale clip/json for the beat's current generation before a redo submit.

    Redo bumps ``kling_o3_generation`` then submits. If ``{beat_id}_g{N}.mp4`` already
    exists from a prior attempt, reconcile would mark the beat completed and batch
    submit would skip it (UI: "Redo failed: HTTP 200").
    """
    beat_id = beat.get("beat_id")
    if not beat_id:
        return
    gen = int(beat.get("kling_o3_generation") or 0)
    clips_dir = kling_o3_clips_dir(event_dir)
    for suffix in (".mp4", ".json"):
        path = clips_dir / f"{beat_id}_g{gen}{suffix}"
        if path.is_file():
            path.unlink()


def reset_kling_o3_beat_for_redo(beat: dict, event_dir: str | Path) -> None:
    """Bump generation and clear in-flight / completed fields for a fresh Kling submit."""
    beat["kling_o3_generation"] = int(beat.get("kling_o3_generation") or 0) + 1
    beat["kling_o3_status"] = "draft"
    beat["status"] = "draft"
    clear_kling_o3_beat_trim(beat)
    for key in (
        "kling_o3_video_path",
        "kling_o3_task_id",
        "kling_o3_completed_at",
        "kling_o3_error",
        "kling_o3_actual_duration_s",
        "kling_o3_post_speech_trim",
    ):
        beat.pop(key, None)
    clear_kling_o3_redo_generation_slot(beat, event_dir)


def materialize_kling_o3_trimmed_clip(
    beat: dict,
    dest: Path,
    *,
    source_path: Path | None = None,
    event_dir: str | Path | None = None,
) -> Path:
    """Write [trim_start, trim_end] window to ``dest``; returns ``dest``."""
    src = source_path or Path(beat.get("kling_o3_video_path") or "")
    if not src.is_file():
        raise FileNotFoundError(f"missing clip: {src}")
    trim_start, trim_end, raw_dur = resolve_kling_o3_trim_window(beat, video_path=src)
    if not kling_o3_trim_is_active(beat, raw_dur=raw_dur):
        copy_file_durable(src, dest)
        return dest

    duration = trim_end - trim_start
    dest.parent.mkdir(parents=True, exist_ok=True)
    event_id = _event_id_from_event_dir(event_dir or src.parent.parent)
    local_src = ensure_local_media(src, event_id=event_id)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{trim_start:.3f}",
        "-i", str(local_src),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(dest),
    ]
    run_ffmpeg_to_dest(cmd, dest, timeout=180, error_prefix="ffmpeg trim failed")
    return dest


def _kling_o3_export_clip_path(
    beat: dict,
    event_dir: str | Path,
    scratch_dir: Path,
) -> Path:
    """Resolve clip path for stitch export (cut/trim temp copy when metadata active).

    Send to Stitcher MUST call this — never concat raw ``kling_o3_video_path``
    when cut or trim metadata defines a non-default window.
    """
    src = Path(beat.get("kling_o3_video_path") or "")
    if not src.is_file():
        raise FileNotFoundError(f"missing clip for {beat.get('beat_id')}: {src}")
    raw_dur = _ffprobe_duration(src)
    beat_id = beat.get("beat_id") or "beat"
    gen = int(beat.get("kling_o3_generation") or 0)

    baked_path = beat.get("kling_o3_baked_path")
    baked_token = beat.get("kling_o3_baked_token")
    expected_token = o3_baked_export_token(beat, video_path=src)
    if baked_path and baked_token == expected_token:
        bp = Path(str(baked_path))
        if bp.is_file():
            return bp.resolve()

    if kling_o3_trim_is_active(beat, raw_dur=raw_dur):
        token = kling_o3_trim_scratch_token(beat)
        dest = scratch_dir / f"{beat_id}_g{gen}_{token}_export_trim.mp4"
        return materialize_kling_o3_trimmed_clip(
            beat, dest, source_path=src, event_dir=event_dir,
        )
    if o3_cut_is_active(beat, raw_dur=raw_dur, video_path=src):
        token = kling_o3_cut_scratch_token(beat, video_path=str(src))
        dest = scratch_dir / f"{beat_id}_{token}_export_cut.mp4"
        return materialize_o3_cut_out_clip(
            beat, dest, source_path=src, event_dir=event_dir,
        )
    return src.resolve()


def resolve_magic_video_source_path(
    beat: dict,
    event_dir: str | Path,
    requested_source: str | Path,
    *,
    scratch_dir: Path | None = None,
) -> Path:
    """FFmpeg source for magic-on-video — trim/cut when request is the beat O3 clip.

    Same contract as ``_kling_o3_export_clip_path`` / Send to Stitcher: magic must
    composite on the trimmed/cut window, never the raw Kling delivery file.
    """
    requested = Path(requested_source)
    o3 = Path(beat.get("kling_o3_video_path") or "")
    if not o3.is_file():
        try:
            return requested.resolve()
        except OSError:
            return requested
    try:
        paths_match = requested.resolve() == o3.resolve()
    except OSError:
        paths_match = str(requested) == str(o3)
    if not paths_match:
        try:
            return requested.resolve()
        except OSError:
            return requested
    scratch = scratch_dir or (Path(event_dir) / "assembled" / "_kling_o3_trim_scratch")
    return _kling_o3_export_clip_path(beat, event_dir, scratch)


def materialize_beat_export_clip_with_retry(
    beat: dict,
    event_dir: str | Path,
    scratch_dir: Path,
    *,
    event_id: str | None = None,
    max_attempts: int = _SIDECAR_IO_MAX_ATTEMPTS,
) -> Path:
    """Materialize one beat export clip with errno 11/35 + ffmpeg transient retry."""
    beat_id = str(beat.get("beat_id") or "beat")
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return resolve_beat_stitch_export_clip_path(beat, event_dir, scratch_dir)
        except (OSError, RuntimeError, FileNotFoundError) as exc:
            last_exc = exc
            err_text = str(exc)
            if (
                sidecar_io_transient(exc)
                or ffmpeg_failure_transient(err_text)
            ) and attempt < max_attempts - 1:
                time.sleep(_sidecar_io_backoff_s(attempt))
                continue
            raise RuntimeError(f"{beat_id}: {err_text}") from exc
    raise RuntimeError(
        f"{beat_id}: export materialize failed after {max_attempts} attempts: {last_exc}",
    )


def resolve_beat_stitch_export_clip_path(
    beat: dict,
    event_dir: str | Path,
    scratch_dir: Path,
) -> Path:
    """Clip for segment concat — magic on beat when present, else highlighted Kling clip."""
    event_dir = Path(event_dir)
    layer = resolve_active_magic_layer(beat, event_dir)
    if layer == "video":
        video_clip = beat_magic_video_clip_path(beat, event_dir)
        if video_clip is not None:
            return video_clip
    if layer == "still":
        magic_still = beat_magic_still_clip_path(beat, event_dir)
        if magic_still is not None:
            if resolve_bg_beat_tts_audio_path(event_dir, beat):
                return materialize_magic_still_with_tts_export(beat, event_dir, scratch_dir)
            return magic_still
    return _kling_o3_export_clip_path(beat, event_dir, scratch_dir)


def _kling_o3_trailing_unquoted_dialogue(raw: str) -> str:
    """Prose after the first closing quote on the voice line — often accidental early ``\"``."""
    text = (raw or "").strip()
    if not text:
        return ""
    m = _kling_o3_voice_block_start(text)
    if not m:
        return ""
    tail = text[m.start():]
    qm = re.search(r':\s*"([^"]*)"', tail, re.IGNORECASE)
    if not qm:
        return ""
    trailing = tail[qm.end():].strip()
    if not trailing:
        return ""
    skip_prefixes = (
        "children's illustrated",
        "match @image1",
        "audio:",
        "only @image1",
        "camera:",
    )
    parts: list[str] = []
    for line in trailing.splitlines():
        chunk = line.strip()
        if not chunk:
            continue
        low = chunk.lower()
        if any(low.startswith(p) for p in skip_prefixes):
            break
        if chunk.startswith("@") or "@image" in low:
            break
        parts.append(chunk)
    return " ".join(parts).strip()


def _kling_o3_trailing_is_voice_markup(trailing: str) -> bool:
    """True when trailing prose is another speaks/continues block, not loose dialogue."""
    return bool(
        re.search(r"\b(?:says|speaks|continues|adds)\b", trailing or "", re.IGNORECASE)
    )


def _kling_o3_voice_line_stop_prefixes() -> tuple[str, ...]:
    return (
        "children's illustrated",
        "match @image1",
        "audio:",
        "only @image1",
        "camera:",
    )


_BRACKET_TAG_DIALOGUE_RE = re.compile(
    r"(?:^|\n)\s*[A-Za-z][\w'.\-]+(?:\s+[A-Za-z][\w'.\-]+)*\s+(?:\[[^\]]+\]\s*)+:\s*",
    re.MULTILINE,
)


def _collect_spoken_after_colon(after: str) -> str:
    """Shared tail collector for speaks/says and [tag]: author delivery lines."""
    after = (after or "").strip()
    if not after:
        return ""
    if after.startswith('"') and after[0] == '"':
        return ""
    skip_prefixes = _kling_o3_voice_line_stop_prefixes()
    parts: list[str] = []
    for line in after.splitlines():
        chunk = line.strip()
        if not chunk:
            if parts:
                break
            continue
        low = chunk.lower()
        if any(low.startswith(p) for p in skip_prefixes):
            break
        if chunk.startswith("@") or "@image" in low:
            break
        if parts and re.search(r"\b(?:says|speaks|continues|adds)\b", chunk, re.I) and ":" in chunk:
            break
        if _BRACKET_TAG_DIALOGUE_RE.match(chunk):
            break
        parts.append(chunk)
    spoken_raw = " ".join(parts).strip()
    if not spoken_raw:
        return ""
    spoken_raw = re.split(
        r"\s+\[(?:Faces|Stage|Expression|Camera|Only|Match|Audio|Children|Show|Rooted)",
        spoken_raw,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    spoken_raw = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", spoken_raw).strip()
    spoken_raw = re.sub(r"\s*\[[^\]]+\]\s*$", "", spoken_raw).strip()
    if len(spoken_raw) >= 2 and spoken_raw[0] == spoken_raw[-1] and spoken_raw[0] in "'\"":
        spoken_raw = spoken_raw[1:-1].strip()
    return _kling_o3_normalize_spoken(spoken_raw) if spoken_raw else ""


def _extract_bracket_tag_dialogue(text: str) -> str:
    """Pull dialogue from author format: ``Arlo [warm, to camera]: line…``."""
    raw = (text or "").strip()
    if not raw:
        return ""
    m = _BRACKET_TAG_DIALOGUE_RE.search(raw)
    if not m:
        return ""
    return _collect_spoken_after_colon(raw[m.end():])


def _extract_unquoted_spoken_after_voice_colon(text: str) -> str:
    """Pull dialogue after speaks/says colon when Kim omits double quotes."""
    raw = (text or "").strip()
    if not raw:
        return ""
    m = _kling_o3_voice_block_start(raw)
    if not m:
        return ""
    tail = raw[m.start():]
    colon = re.search(r":\s*", tail)
    if not colon:
        return ""
    after = tail[colon.end():].strip()
    if not after:
        return ""
    if after.startswith('"') and re.search(r':\s*"', tail, re.I):
        return ""
    return _collect_spoken_after_colon(after)


def _extract_spoken_dialogue_detail(prompt: str) -> tuple[str, str | None]:
    """Return (spoken, auto_merged_trailing) from a Kling O3 prompt box."""
    text = (prompt or "").strip()
    if not text:
        return "", None

    bracket = _extract_bracket_tag_dialogue(text)
    if bracket:
        return bracket, None

    segments: list[str] = []
    for m in re.finditer(
        r"<<<voice_\d+>>>\s*(?:says|speaks|continues|adds)[^:\"]*:\s*\"([^\"]+)\"",
        text,
        re.IGNORECASE,
    ):
        segments.append(m.group(1).strip())
    if not segments:
        for m in re.finditer(
            r"\b(?:says|speaks|continues|adds)[^:\"']*:\s*\"([^\"]+)\"",
            text,
            re.IGNORECASE,
        ):
            segments.append(m.group(1).strip())
    if not segments:
        for m in re.finditer(
            r"\b(?:says|speaks|continues|adds)[^:\"']*:\s*'([^']+)'",
            text,
            re.IGNORECASE,
        ):
            segments.append(m.group(1).strip())
    if not segments:
        for m in re.finditer(r"\"([^\"]{3,})\"", text):
            segments.append(m.group(1).strip())
    if not segments:
        for m in re.finditer(r"(?<![A-Za-z])'([^']{3,})'(?![A-Za-z])", text):
            segments.append(m.group(1).strip())

    if not segments:
        unquoted = _extract_unquoted_spoken_after_voice_colon(text)
        if unquoted:
            return unquoted, None
        return "", None

    spoken = _kling_o3_normalize_spoken(" ".join(segments))
    trailing = _kling_o3_trailing_unquoted_dialogue(text)
    if (
        trailing
        and len(segments) == 1
        and not _kling_o3_trailing_is_voice_markup(trailing)
    ):
        merged = _kling_o3_normalize_spoken(f"{spoken} {trailing}")
        if merged != spoken:
            return merged, trailing
    return spoken, None


def extract_spoken_dialogue_from_kling_prompt(prompt: str) -> str:
    """Pull spoken dialogue from a Kling O3 prompt (auto-merges unquoted continuation)."""
    spoken, _ = _extract_spoken_dialogue_detail(prompt)
    return spoken


def _spoken_from_beat_dialogue(beat: dict) -> str:
    dialogue = (beat.get("dialogue_text") or "").strip()
    if not dialogue:
        return ""
    spoken = re.sub(r"\[[^\]]+\]", " ", dialogue)
    return _kling_o3_normalize_spoken(re.sub(r"\s+", " ", spoken).strip())


def _kling_o3_voice_block_start(pattern: str) -> re.Match[str] | None:
    """Locate the first voice/delivery line in a Kling O3 prompt."""
    text = (pattern or "").strip()
    if not text:
        return None
    for expr in (
        r"<<<voice_\d+>>>",
        _BRACKET_TAG_DIALOGUE_RE.pattern,
        r"\bspeaks in a\b",
        r"\bspeaks[^:\n]{0,120}:\s*",
        r"\bsays[^:\"]*:\s*",
    ):
        m = re.search(expr, text, re.IGNORECASE)
        if m:
            return m
    return None


def _kling_o3_staging_head(prompt: str) -> str:
    """Visual staging + camera lines before the first voice/speech block."""
    text = (prompt or "").strip()
    if not text:
        return ""
    m = _kling_o3_voice_block_start(text)
    if m:
        head = text[: m.start()].strip()
    else:
        head = text
    # Drop dangling @Image1 left when voice tag immediately followed the ref token.
    head = re.sub(r"@Image1\s*$", "", head).strip()
    return head


def _speaker_has_kling_element(speaker: str) -> bool:
    try:
        from tools import kling_character_registry as reg
        return reg.get_element_name(speaker or "") is not None
    except Exception:
        return False


def _kling_o3_cast_names() -> list[str]:
    try:
        from tools import kling_character_registry as reg
        data = reg.load_character_subjects()
        return sorted((data.get("characters") or {}).keys(), key=len, reverse=True)
    except Exception:
        return []


def _kling_o3_speaker_registry_keys(speaker: str) -> set[str]:
    keys = {(speaker or "").strip().lower()}
    try:
        from tools import kling_character_registry as reg
        resolved = reg.resolve_registry_key(speaker or "")
        if resolved:
            keys.add(resolved.lower())
        element = reg.get_element_name(speaker or "")
        if element:
            keys.add(element.lower())
    except Exception:
        pass
    return {k for k in keys if k}


def _kling_o3_addresses_viewer(spoken: str) -> bool:
    text = spoken or ""
    if _VIEWER_ADDRESS_STRONG_RE.search(text):
        return True
    return bool(_VIEWER_THIRD_PARTY_QUESTION_RE.search(text))


def _kling_o3_plural_addressee(spoken: str) -> bool:
    return bool(_PLURAL_ADDRESSEE_RE.search(spoken or ""))


def _kling_o3_viewer_staging_clause(spoken: str) -> str:
    if not _kling_o3_addresses_viewer(spoken):
        return ""
    return (
        " @Image1 speaks directly to the camera; the child viewer is off-screen."
    )


def _kling_o3_viewer_address_clause(spoken: str) -> str:
    if not _kling_o3_addresses_viewer(spoken):
        return ""
    return KLING_O3_VIEWER_ADDRESS_LOCK


def _kling_o3_named_addressees(speaker: str, spoken: str) -> list[str]:
    """Other cast names mentioned in dialogue (likely triggers multi-character render)."""
    text = (spoken or "").strip()
    if not text:
        return []
    self_keys = _kling_o3_speaker_registry_keys(speaker)
    found: list[str] = []
    for name in _kling_o3_cast_names():
        if name.lower() in self_keys:
            continue
        if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            found.append(name)
    return found


def _kling_o3_addressee_offscreen_clause(speaker: str, spoken: str) -> str:
    addressees = _kling_o3_named_addressees(speaker, spoken)
    if not addressees:
        return ""
    parts = [
        f"{name} is off-screen and must not appear in the frame."
        for name in addressees
    ]
    return " ".join(parts)


def normalize_kling_o3_identity_footer(prompt: str) -> str:
    """Replace drifted identity footer lines with canonical KLING_O3_IDENTITY_LOCK."""
    text = (prompt or "").strip()
    if not text or not _KLING_O3_IDENTITY_LOCK_LINE_RE.search(text):
        return text
    text = _KLING_O3_IDENTITY_LOCK_LINE_RE.sub(KLING_O3_IDENTITY_LOCK, text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def identity_footer_is_canonical(prompt: str) -> bool:
    """True when prompt has no identity footer or footer matches KLING_O3_IDENTITY_LOCK."""
    text = (prompt or "").strip()
    if not text or "match @image1 character appearance" not in text.lower():
        return True
    match = _KLING_O3_IDENTITY_LOCK_LINE_RE.search(text)
    if not match:
        return False
    found = re.sub(r"\s+", " ", match.group(0).strip())
    canonical = re.sub(r"\s+", " ", KLING_O3_IDENTITY_LOCK.strip())
    return found == canonical


def _speaker_has_element_bound_voice(speaker: str) -> bool:
    try:
        from tools import kling_character_registry as reg
    except ImportError:
        import kling_character_registry as reg  # type: ignore
    try:
        return bool(reg.is_speaker_voice_ready((speaker or "").strip()))
    except Exception:
        return False


def align_element_bound_kling_display_names(prompt: str, speaker: str) -> str:
    """Map registry speaker names to Kling Element display names (Lorelai → Loral).

    Safe under prompt-box law: rewrites staging/@Image1 labels only, never rebuilds
    voice line or quoted dialogue from sidecar canon.
    """
    text = (prompt or "").strip()
    sp = (speaker or "").strip()
    if not text or not sp or not _speaker_has_element_bound_voice(sp):
        return prompt or ""
    try:
        from tools import kling_o3_prompt as o3p
    except ImportError:
        import kling_o3_prompt as o3p  # type: ignore
    text = o3p.normalize_kling_speaker_names_in_prompt(text, sp)
    return o3p.scrub_registry_name_from_pre_voice_staging(text, sp)


def _append_kling_o3_submit_locks(
    raw: str,
    *,
    speaker: str,
    spoken: str,
    element_bound: bool | None = None,
) -> str:
    """Append solo-shot, viewer, addressee, identity, and speech-only locks once."""
    if element_bound is None:
        element_bound = _speaker_has_element_bound_voice(speaker)
    out = normalize_kling_o3_identity_footer(raw.rstrip())
    lower = out.lower()
    if "only @image1 is visible" not in lower:
        out = f"{out}\n\n{KLING_O3_SOLO_SHOT_LOCK}"
    if _kling_o3_viewer_address_clause(spoken) and "child viewer" not in lower:
        viewer = (
            KLING_O3_ELEMENT_VIEWER_OFFSCREEN_LOCK
            if element_bound
            else _kling_o3_viewer_address_clause(spoken)
        )
        out = f"{out}\n\n{viewer}"
    if _kling_o3_plural_addressee(spoken) and "any other addressees" not in lower:
        out = f"{out}\n\n{KLING_O3_PLURAL_ADDRESSEE_LOCK}"
    offscreen = _kling_o3_addressee_offscreen_clause(speaker, spoken)
    if offscreen:
        addressees = _kling_o3_named_addressees(speaker, spoken)
        if addressees and not all(
            f"{name.lower()} is off-screen" in lower for name in addressees
        ):
            out = f"{out} {offscreen}"
    if "@Image1" in out and "match @image1" not in lower:
        out = f"{out}\n\n{KLING_O3_IDENTITY_LOCK}"
    if (
        "@Image1" in out
        and "@Image2" in out
        and "natural lighting on @image1" not in lower
    ):
        out = f"{out}\n\n{KLING_O3_LIGHTING_LOCK}"
    if (speaker or "").strip() == "Chipper" and "no companion bird" not in lower:
        out = f"{out}\n\n{KLING_O3_CHIPPER_SOLO_BIRD_LOCK}"
    return ensure_kling_o3_speech_only_prompt(out).strip()


def _voice_delivery_stale(raw: str) -> bool:
    lower = (raw or "").lower()
    return any(
        token in lower
        for token in (
            "bright small",
            "songbird guide voice",
            "<<<voice_",
            "mature and sympathetic",
        )
    )


def _kling_o3_staging_stale(staging: str, beat: dict) -> bool:
    """True when preserved staging head conflicts with current beat metadata."""
    text = (staging or "").lower()
    speaker = (beat.get("speaker") or "").strip()
    scene = (beat.get("scene_notes") or "").lower()
    emotion = (beat.get("emotion") or "").lower()
    if "looking down" in text:
        return True
    if speaker == "Chipper" and (
        "discovery" in scene or any(k in emotion for k in ("upset", "concern", "shock"))
    ):
        if "not talking down" not in text:
            return True
    if _is_chipper_intro_beat(beat) and "gestures toward the lens" not in text:
        return True
    return False


def _kling_o3_element_staging_block(beat: dict, speaker: str, spoken: str) -> str:
    """Canonical visual staging + camera for Element speakers."""
    action = _kling_o3_visual_action_clause(beat, spoken)
    try:
        from tools import kling_character_registry as reg

        image1_label = reg.kling_image1_speaker_label(speaker)
    except Exception:
        image1_label = speaker
    staging = (
        f"@Image1 ({image1_label}) {action}. Scene from @Image2.\n\n"
        f"{KLING_O3_CAMERA_LOCK}"
    )
    if _is_chipper_intro_beat(beat):
        staging += f"\n\n{_kling_o3_chipper_intro_staging()}"
    return staging


def beat_has_stored_kling_prompt(beat: dict | None) -> bool:
    """True when sidecar already holds operator-authored kling_o3_prompt text."""
    if not isinstance(beat, dict):
        return False
    return bool((beat.get("kling_o3_prompt") or "").strip())


def o3_prompt_box_law_active(beat: dict | None) -> bool:
    """True when Generate sent an authoritative prompt-box payload for this submit."""
    if os.environ.get("MN_O3_PROMPT_BOX_LAW") == "1":
        return True
    if not isinstance(beat, dict):
        return False
    return bool(beat.get("o3_prompt_box_law"))


def stamp_o3_prompt_box_law(beat: dict, prompt: str) -> None:
    """Mark this beat's next O3 submit as prompt-box authoritative."""
    beat["kling_o3_prompt"] = (prompt or "").strip()
    beat["o3_prompt_box_law"] = True
    beat["o3_prompt_box_law_at"] = datetime.now(timezone.utc).isoformat()


def clear_o3_prompt_box_law(beat: dict) -> None:
    beat.pop("o3_prompt_box_law", None)
    beat.pop("o3_prompt_box_law_at", None)


def prepare_kling_o3_prompt_for_submit(beat: dict, prompt: str | None = None) -> str:
    """Return operator prompt verbatim for WaveSpeed — no rebuild, locks, or name heal."""
    return (prompt if prompt is not None else beat.get("kling_o3_prompt") or "").strip()


def apply_kling_o3_duration_floor(
    prompt: str,
    estimated: int,
    *,
    spoken: str | None = None,
) -> int:
    """Validated-recipe guard: long multi-chunk dialogue must not bucket to 5s."""
    if not spoken:
        spoken = _normalize_spoken_for_duration(
            extract_spoken_dialogue_from_kling_prompt(prompt) or "",
        )
    word_count = len(re.findall(r"\S+", spoken)) if spoken else 0
    pause_markers = len(re.findall(r"\[\s*(?:pause|break|silence)\s*\]", spoken, re.I))
    pause_markers += len(re.findall(r"\.{2,}|…+", spoken))
    if "?" in spoken or pause_markers >= 1:
        return max(estimated, 8)
    if word_count >= 12 or pause_markers >= 2:
        return max(estimated, 8)
    return estimated


def _kling_o3_has_pre_speech_staging(prompt: str) -> bool:
    """True when prompt has substantial setup before the voice/speech line."""
    text = (prompt or "").strip()
    if not text:
        return False
    m = re.search(
        r"<<<voice_\d+>>>|\b(?:speaks|says)\b",
        text,
        re.IGNORECASE,
    )
    if not m:
        return False
    head = text[: m.start()].strip()
    return len(head) >= 20


def snap_kling_o3_duration(seconds: float) -> int:
    """Round up to the nearest allowed Kling O3 duration bucket (5–12s)."""
    s = max(float(KLING_O3_MIN_DURATION), min(float(KLING_O3_MAX_DURATION), seconds))
    for bucket in KLING_O3_DURATION_CHOICES:
        if s <= bucket + 0.01:
            return bucket
    return KLING_O3_MAX_DURATION


def estimate_kling_o3_duration_from_spoken(
    spoken: str,
    *,
    has_pre_speech_staging: bool = False,
) -> int:
    """Pause-aware local estimate from dialogue text (no API calls)."""
    text = (spoken or "").strip()
    if not text:
        return KLING_O3_MIN_DURATION

    pause_s = len(re.findall(r"\[\s*(?:pause|break|silence)\s*\]", text, re.I)) * _KLING_O3_CUE_MARKER_S
    cleaned = re.sub(r"\[[^\]]+\]", " ", text)
    pause_s += len(re.findall(r"\.{2,}|…+", cleaned)) * _KLING_O3_ELLIPSIS_S
    pause_s += len(re.findall(r"\?", cleaned)) * _KLING_O3_QUESTION_PAUSE_S

    for_count = re.sub(r"\.{2,}|…+", " ", cleaned)
    for_count = re.sub(r"\s+", " ", for_count).strip()
    words = len(re.findall(r"\S+", for_count)) if for_count else 0
    speech_s = (words / _KLING_O3_WPM) * 60.0 if words else 0.0

    staging_s = _KLING_O3_STAGING_LEAD_S if has_pre_speech_staging else 0.4
    total = speech_s + pause_s + staging_s + _KLING_O3_TAIL_S
    return snap_kling_o3_duration(total)


def estimate_kling_o3_seconds_unsnapped(
    spoken: str,
    *,
    has_pre_speech_staging: bool = False,
) -> float:
    """Pause-aware seconds before bucket snap (for overflow detection)."""
    text = (spoken or "").strip()
    if not text:
        return float(KLING_O3_MIN_DURATION)

    pause_s = len(re.findall(r"\[\s*(?:pause|break|silence)\s*\]", text, re.I)) * _KLING_O3_CUE_MARKER_S
    cleaned = re.sub(r"\[[^\]]+\]", " ", text)
    pause_s += len(re.findall(r"\.{2,}|…+", cleaned)) * _KLING_O3_ELLIPSIS_S
    pause_s += len(re.findall(r"\?", cleaned)) * _KLING_O3_QUESTION_PAUSE_S

    for_count = re.sub(r"\.{2,}|…+", " ", cleaned)
    for_count = re.sub(r"\s+", " ", for_count).strip()
    words = len(re.findall(r"\S+", for_count)) if for_count else 0
    speech_s = (words / _KLING_O3_WPM) * 60.0 if words else 0.0

    staging_s = _KLING_O3_STAGING_LEAD_S if has_pre_speech_staging else 0.4
    return speech_s + pause_s + staging_s + _KLING_O3_TAIL_S


def estimate_kling_o3_duration_from_prompt(prompt: str) -> int:
    """Estimate clip length from the full Kling O3 prompt (free, local)."""
    prompt_text = (prompt or "").strip()
    if not prompt_text:
        return KLING_O3_MIN_DURATION
    spoken = _normalize_spoken_for_duration(
        extract_spoken_dialogue_from_kling_prompt(prompt_text) or "",
    )
    if not spoken:
        return KLING_O3_MIN_DURATION
    return estimate_kling_o3_duration_from_spoken(
        spoken,
        has_pre_speech_staging=_kling_o3_has_pre_speech_staging(prompt_text),
    )


def _cap_kling_o3_auto_duration(
    prompt: str,
    duration: int,
    *,
    beat: dict | None = None,
) -> int:
    """Keep concise single-chunk dialogue out of 10–12s buckets when timing fits 8s."""
    spoken = _spoken_for_duration_estimate(prompt, beat=beat)
    word_count = len(re.findall(r"\S+", spoken)) if spoken else 0
    if not word_count or word_count > _KLING_O3_AUTO_CAP_MAX_WORDS:
        return duration
    staging = _kling_o3_has_pre_speech_staging(prompt)
    unsnapped = estimate_kling_o3_seconds_unsnapped(
        spoken,
        has_pre_speech_staging=staging,
    )
    # Word-count alone is not enough — 30-word lines with [pause] can need 12s (beat #9).
    if snap_kling_o3_duration(unsnapped) <= 8:
        return min(duration, 8)
    return duration


def resolve_kling_o3_submit_duration(beat: dict, prompt: str) -> int:
    """Duration for Kling submit: manual lock wins, else prompt estimate."""
    if beat.get("kling_o3_duration_locked"):
        try:
            locked = int(beat.get("kling_o3_duration") or 0)
        except (TypeError, ValueError):
            locked = 0
        if KLING_O3_MIN_DURATION <= locked <= KLING_O3_MAX_DURATION:
            return locked
    spoken = _spoken_for_duration_estimate(prompt, beat=beat)
    staging = _kling_o3_has_pre_speech_staging(prompt)
    estimated = estimate_kling_o3_duration_from_spoken(
        spoken,
        has_pre_speech_staging=staging,
    ) if spoken else KLING_O3_MIN_DURATION
    estimated = apply_kling_o3_duration_floor(prompt, estimated, spoken=spoken)
    return _cap_kling_o3_auto_duration(prompt, estimated, beat=beat)


def validate_kling_o3_beat_for_submit(
    beat: dict,
    *,
    event_id: str = "1",
    phase: str = "full",
) -> list[dict]:
    """Pre-submit gates: Element voice ready + local duration length check.

    Returns a list of error dicts (empty = OK). Used by Beat Gen batch submit.
    """
    errors: list[dict] = []
    beat_id = beat.get("beat_id") or "unknown"
    speaker = beat.get("speaker") or ""
    stored_prompt = (beat.get("kling_o3_prompt") or "").strip()

    if not stored_prompt:
        errors.append({
            "beat_id": beat_id,
            "code": "KLING_O3_PROMPT_REQUIRED",
            "message": "Kling O3 prompt is empty — type or paste a prompt before Submit.",
        })
        return errors

    ensure_beat_element_aligned_reference(beat)

    prompt = prepare_kling_o3_prompt_for_submit(beat, stored_prompt)
    if not prompt:
        errors.append({
            "beat_id": beat_id,
            "code": "KLING_O3_PROMPT_REQUIRED",
            "message": "Kling O3 prompt is empty after submit prep.",
        })
        return errors

    submit_mode = resolve_kling_o3_submit_mode(beat)
    frame_slot_touched = any(
        isinstance(beat.get(k), dict) and (beat[k].get("abs_path") or beat[k].get("key"))
        for k in ("start_frame_image", "end_frame_image")
    )

    try:
        from tools import kling_character_registry as reg
        if not reg.is_speaker_voice_ready(speaker):
            key = reg.resolve_registry_key(speaker) or speaker
            errors.append({
                "beat_id": beat_id,
                "code": "VOICE_ELEMENT_MISSING",
                "message": (
                    f"{speaker!r} has no active Kling Element with bound ElevenLabs voice. "
                    f"Run: python3 scripts/setup_all_kling_character_voices.py --char {key}"
                ),
            })
        else:
            if re.search(r"\b(?:speaks|says)\b", stored_prompt, re.I):
                extracted = extract_spoken_dialogue_from_kling_prompt(stored_prompt)
                if not extracted:
                    errors.append({
                        "beat_id": beat_id,
                        "code": "NO_QUOTED_DIALOGUE",
                        "message": (
                            "No spoken dialogue found in the prompt voice line — "
                            "Kling would fall back to stale beat-plan dialogue."
                        ),
                    })
    except Exception as exc:
        errors.append({
            "beat_id": beat_id,
            "code": "VOICE_REGISTRY_ERROR",
            "message": str(exc),
        })

    if submit_mode == "startend" or frame_slot_touched:
        if not resolve_beat_start_frame_path(beat):
            errors.append({
                "beat_id": beat_id,
                "code": "MISSING_START_FRAME",
                "message": "Pipeline B requires a start frame — drop a still into Start frame.",
            })
        if not resolve_beat_end_frame_path(beat):
            errors.append({
                "beat_id": beat_id,
                "code": "MISSING_END_FRAME",
                "message": "Pipeline B requires an end frame — drop or generate one in End frame.",
            })
    else:
        char_path = resolve_beat_char_ref_path(beat)
        bg_path = resolve_beat_bg_ref_path(beat, str(event_id), str(phase))
        if not char_path:
            errors.append({
                "beat_id": beat_id,
                "code": "MISSING_CHAR_REF",
                "message": f"Missing character reference image for {speaker!r}",
            })
        elif speaker and element_char_ref_required_for_beat(beat):
            ok, detail = element_char_ref_gate(beat)
            if not ok:
                errors.append({
                    "beat_id": beat_id,
                    "code": "ELEMENT_VISUAL_MISMATCH",
                    "message": detail,
                    "char_ref": char_path,
                })
        if o3_bg_ref_required_for_beat(beat) and not bg_path:
            errors.append({
                "beat_id": beat_id,
                "code": "MISSING_BG_REF",
                "message": "Missing background reference image",
            })

    duration = resolve_kling_o3_submit_duration(beat, prompt)
    spoken = _spoken_for_duration_estimate(prompt, beat=beat)
    if spoken:
        staging = _kling_o3_has_pre_speech_staging(prompt)
        unsnapped = estimate_kling_o3_seconds_unsnapped(
            spoken,
            has_pre_speech_staging=staging,
        )
        # DIALOGUE_TOO_LONG is advisory only — Kling bucket cap applies at submit.

    if duration < KLING_O3_MIN_DURATION or duration > KLING_O3_MAX_DURATION:
        errors.append({
            "beat_id": beat_id,
            "code": "DURATION_OUT_OF_RANGE",
            "message": f"Submit duration {duration}s outside {KLING_O3_MIN_DURATION}–{KLING_O3_MAX_DURATION}s",
            "duration_s": duration,
        })

    return errors


def validate_kling_o3_beats_for_submit(
    beats: list[dict],
    *,
    event_id: str = "1",
    phase: str = "full",
) -> list[dict]:
    """Aggregate pre-submit validation for a batch."""
    all_errors: list[dict] = []
    for beat in beats:
        all_errors.extend(
            validate_kling_o3_beat_for_submit(beat, event_id=event_id, phase=phase),
        )
    return all_errors


def kling_o3_submit_warnings(
    beat: dict,
    raw_prompt: str,
    *,
    extracted_spoken: str | None = None,
    prepared_prompt: str | None = None,
    prepared_spoken: str | None = None,
) -> list[dict]:
    """Non-blocking submit findings — surfaced in preview modal before Kling API."""
    beat_id = beat.get("beat_id") or "unknown"
    raw = (raw_prompt or "").strip()
    detail_extracted, auto_merged = _extract_spoken_dialogue_detail(raw)
    extracted = extracted_spoken if extracted_spoken is not None else detail_extracted
    prepared = (
        prepared_prompt
        if prepared_prompt is not None
        else (prepare_kling_o3_prompt_for_submit(beat, raw) if raw else "")
    )
    prep_spoken = (
        prepared_spoken
        if prepared_spoken is not None
        else extract_spoken_dialogue_from_kling_prompt(prepared)
    )
    warnings: list[dict] = []

    if not raw:
        warnings.append({
            "beat_id": beat_id,
            "code": "PROMPT_EMPTY",
            "severity": "error",
            "message": "Prompt box is empty.",
        })
        return warnings

    if auto_merged:
        preview = auto_merged[:120] + ("…" if len(auto_merged) > 120 else "")
        warnings.append({
            "beat_id": beat_id,
            "code": "AUTO_MERGED_UNQUOTED",
            "severity": "warning",
            "message": (
                "Unquoted text after the closing quote was auto-included in the spoken line. "
                f"Merged: {preview!r}. Prefer one pair of quotes around the full line."
            ),
            "merged_text": auto_merged,
        })
    else:
        trailing = _kling_o3_trailing_unquoted_dialogue(raw)
        if trailing:
            preview = trailing[:120] + ("…" if len(trailing) > 120 else "")
            warnings.append({
                "beat_id": beat_id,
                "code": "DIALOGUE_OUTSIDE_QUOTES",
                "severity": "error",
                "message": (
                    "Text after the closing quote cannot be included. "
                    f"Move it inside the quotes: {preview!r}"
                ),
                "dropped_text": trailing,
            })

    if not extracted:
        warnings.append({
            "beat_id": beat_id,
            "code": "NO_QUOTED_DIALOGUE",
            "severity": "error",
            "message": (
                "No spoken dialogue found inside double quotes after speaks/says. "
                "Put the full line in one quoted string."
            ),
        })
    elif raw and re.search(r'"\s*[^"]+\.{2,}\s*"', raw):
        if extracted and ".." not in extracted and "…" not in extracted:
            warnings.append({
                "beat_id": beat_id,
                "code": "ELLIPSIS_NORMALIZED",
                "severity": "warning",
                "message": (
                    f"Ellipses in quotes were normalized for TTS. "
                    f"Kling will speak: {extracted!r}"
                ),
                "extracted_spoken": extracted,
            })

    if extracted and prep_spoken and extracted != prep_spoken:
        warnings.append({
            "beat_id": beat_id,
            "code": "SPOKEN_CHANGED_BY_PREP",
            "severity": "warning",
            "message": (
                f"Submit prep changed the spoken line from {extracted!r} to {prep_spoken!r}."
            ),
            "extracted_spoken": extracted,
            "prepared_spoken": prep_spoken,
        })

    if _dialogue_has_legacy_chipper_content(beat.get("dialogue_text") or ""):
        prompt_spoken = extract_spoken_dialogue_from_kling_prompt(
            beat.get("kling_o3_prompt") or raw,
        )
        if not prompt_spoken or _dialogue_has_legacy_chipper_content(prompt_spoken):
            warnings.append({
                "beat_id": beat_id,
                "code": "LEGACY_DIALOGUE_TEXT",
                "severity": "info",
                "message": (
                    "Beat dialogue_text still contains Pip/Alex locked-line names. "
                    "Kling uses the prompt box only — update dialogue_text when you can. "
                    "Auto-build from dialogue will substitute the canonical Chipper intro."
                ),
            })

    if extracted and re.search(r"\bchild\b", extracted, re.IGNORECASE):
        warnings.append({
            "beat_id": beat_id,
            "code": "CHILD_MENTIONED_IN_SPEECH",
            "severity": "info",
            "message": (
                "Spoken line mentions 'child'. This is allowed — staging keeps the "
                "child viewer off-screen. Kling may still hallucinate a second character."
            ),
        })

    if extracted and re.search(r"\b(pip|alex|apprentice)\b", extracted, re.IGNORECASE):
        warnings.append({
            "beat_id": beat_id,
            "code": "LEGACY_NAME_IN_SPOKEN",
            "severity": "warning",
            "message": (
                "Spoken line names Pip/Alex/apprentice — high risk of multi-character "
                "video. Prefer canonical Chipper intro wording."
            ),
        })

    if (beat.get("speaker") or "").strip() == "Chipper" and "continues in the same" in raw.lower():
        warnings.append({
            "beat_id": beat_id,
            "code": "CHIPPER_SPLIT_VOICE_IN_TEXTAREA",
            "severity": "warning",
            "message": (
                "Split voice blocks in the textarea will be collapsed to one Chipper "
                "voice line on submit (same as Tessa)."
            ),
        })

    spoken_for_dur = _spoken_for_duration_estimate(prepared or raw, beat=beat)
    if spoken_for_dur:
        staging = _kling_o3_has_pre_speech_staging(prepared or raw)
        unsnapped = estimate_kling_o3_seconds_unsnapped(
            spoken_for_dur,
            has_pre_speech_staging=staging,
        )
        if unsnapped > float(KLING_O3_MAX_DURATION) + 0.75:
            bucket = resolve_kling_o3_submit_duration(beat, prepared or raw)
            warnings.append({
                "beat_id": beat_id,
                "code": "DIALOGUE_TOO_LONG",
                "severity": "warning",
                "message": (
                    f"Local length estimate {unsnapped:.1f}s exceeds max bucket "
                    f"({KLING_O3_MAX_DURATION}s). Submit will use {bucket}s — "
                    "listen and trim if speech feels rushed."
                ),
                "estimated_duration_s": round(unsnapped, 2),
                "submit_duration_s": bucket,
            })

    return warnings


def preview_kling_o3_submit(
    beat: dict,
    raw_prompt: str,
    *,
    event_id: str = "1",
    phase: str = "full",
) -> dict:
    """Return what Kling will receive + non-blocking warnings for the UI confirm step."""
    raw = (raw_prompt or "").strip()
    extracted = extract_spoken_dialogue_from_kling_prompt(raw)
    prepared = prepare_kling_o3_prompt_for_submit(beat, raw) if raw else ""
    prep_spoken = extract_spoken_dialogue_from_kling_prompt(prepared) if prepared else ""
    warnings = kling_o3_submit_warnings(
        beat,
        raw,
        extracted_spoken=extracted,
        prepared_prompt=prepared,
        prepared_spoken=prep_spoken,
    )
    for finding in audit_kling_o3_beat(
        {**beat, "kling_o3_prompt": raw},
        event_id=event_id,
        phase=phase,
    ):
        code = finding.get("code")
        if code in {w.get("code") for w in warnings}:
            continue
        if finding.get("severity") == "error" and code not in {
            "MISSING_CHAR_REF",
            "MISSING_BG_REF",
            "VOICE_ELEMENT_MISSING",
            "ELEMENT_VISUAL_MISMATCH",
            "DIALOGUE_TOO_LONG",
            "DURATION_OUT_OF_RANGE",
            "KLING_O3_PROMPT_REQUIRED",
        }:
            continue
        warnings.append(finding)
    duration = (
        resolve_kling_o3_submit_duration(beat, prepared)
        if prepared
        else None
    )
    return {
        "beat_id": beat.get("beat_id"),
        "extracted_spoken": extracted,
        "prepared_spoken": prep_spoken,
        "prepared_prompt": prepared,
        "duration_s": duration,
        "warnings": warnings,
        "blocking": any(w.get("severity") == "error" for w in warnings),
    }


def audit_kling_o3_beat(beat: dict, *, event_id: str = "1", phase: str = "full") -> list[dict]:
    """Non-blocking QA findings for a beat (stored vs prepared prompt drift)."""
    beat_id = beat.get("beat_id") or "unknown"
    speaker = beat.get("speaker") or ""
    stored = (beat.get("kling_o3_prompt") or "").strip()
    prepared = prepare_kling_o3_prompt_for_submit(beat, stored)
    spoken = extract_spoken_dialogue_from_kling_prompt(prepared) or ""
    findings: list[dict] = []

    if stored and "<<<voice_" in stored:
        findings.append({
            "beat_id": beat_id,
            "code": "LEGACY_VOICE_TAGS_STORED",
            "severity": "warning",
            "message": (
                "Textarea has <<<voice_N>>> tags; prompt is submitted verbatim. "
                "Use a single Element voice line for O3 Pro + element_list."
            ),
        })
    if "<<<voice_" in prepared and _speaker_has_kling_element(speaker):
        findings.append({
            "beat_id": beat_id,
            "code": "LEGACY_VOICE_TAGS_PREPARED",
            "severity": "warning",
            "message": (
                "Prompt still contains <<<voice_N>>> and will reach the API as written. "
                "Prefer one {Element} speaks … block for Element speakers."
            ),
        })
    if spoken:
        addressees = _kling_o3_named_addressees(speaker, spoken)
        if addressees and "off-screen" not in prepared.lower():
            findings.append({
                "beat_id": beat_id,
                "code": "ADDRESSEE_ONSCREEN_RISK",
                "severity": "warning",
                "message": f"Dialogue names {addressees!r} without off-screen lock.",
                "addressees": addressees,
            })
        if addressees:
            findings.append({
                "beat_id": beat_id,
                "code": "ADDRESSEE_IN_SPOKEN_LINE",
                "severity": "warning",
                "message": (
                    f"Solo beat dialogue names other characters: {addressees!r}. "
                    "Confirm off-screen lock is present before submit."
                ),
                "addressees": addressees,
            })
    if "no background music" not in prepared.lower():
        findings.append({
            "beat_id": beat_id,
            "code": "MISSING_AUDIO_LOCK",
            "severity": "error",
            "message": "Prepared prompt missing speech-only audio lock.",
        })
    if "only @image1 is visible" not in prepared.lower():
        findings.append({
            "beat_id": beat_id,
            "code": "MISSING_SOLO_SHOT_LOCK",
            "severity": "warning",
            "message": "Prepared prompt missing solo-character lock.",
        })

    char_path = resolve_beat_char_ref_path(beat)
    if char_path and speaker:
        try:
            from tools import kling_character_registry as reg

            if reg.is_speaker_voice_ready(speaker):
                ok, detail = element_char_ref_gate(beat)
                if not ok:
                    findings.append({
                        "beat_id": beat_id,
                        "code": "ELEMENT_VISUAL_MISMATCH",
                        "severity": "error",
                        "message": detail,
                        "char_ref": char_path,
                    })
                elif beat.get("reference_image_locked"):
                    findings.append({
                        "beat_id": beat_id,
                        "code": "REFERENCE_IMAGE_LOCKED",
                        "severity": "info",
                        "message": (
                            "Char ref locked — your library still is kept; "
                            "it must still match Element poses for O3 voice."
                        ),
                    })
        except Exception as exc:
            findings.append({
                "beat_id": beat_id,
                "code": "ELEMENT_ALIGNMENT_CHECK_FAILED",
                "severity": "error",
                "message": str(exc),
            })

    submit_errors = validate_kling_o3_beat_for_submit(beat, event_id=event_id, phase=phase)
    for err in submit_errors:
        findings.append({**err, "severity": "error"})

    return findings


def audit_kling_o3_beats(
    beats: list[dict],
    *,
    event_id: str = "1",
    phase: str = "full",
) -> list[dict]:
    """Segment-wide Kling O3 QA audit."""
    out: list[dict] = []
    for beat in beats:
        out.extend(audit_kling_o3_beat(beat, event_id=event_id, phase=phase))
    return out


def suggest_kling_o3_duration(dialogue_text: str) -> int:
    """Legacy import path — dialogue-only estimate."""
    return estimate_kling_o3_duration_from_spoken(
        dialogue_text or "",
        has_pre_speech_staging=False,
    )


def _scene_notes_are_production_staging(scene: str) -> bool:
    """True when scene_notes is a short on-screen label (Discovery), not QA/dev text."""
    s = (scene or "").strip()
    if not s or len(s) > 80:
        return False
    low = s.lower()
    dev_markers = (
        "validation", "voice_a", "voice_b", "kling o3", "canonical",
        "test ", "debug", "pretending-to-be-fine", "winner,",
    )
    if any(m in low for m in dev_markers):
        return False
    return True


def _emotion_action_clause(beat: dict) -> str:
    emotion = (beat.get("emotion") or "neutral").replace("_", " ")
    scene = (beat.get("scene_notes") or "").strip()
    speaker = beat.get("speaker") or "Character"
    if scene and _scene_notes_are_production_staging(scene):
        return f"{speaker} — {scene[:120]}"
    mapping = {
        "sad disappointed": "looking up with tears barely held back, pretending to be fine",
        "happy excited": "brightening with a gentle smile",
        "upset shocked": "startled, eyes wide",
        "neutral": "calm and attentive",
    }
    return mapping.get(emotion, f"{emotion} expression")


def _strip_bracket_staging_from_spoken(text: str) -> str:
    """Remove [Faces camera…] performance blocks from spoken; keep [pause] rhythm markers."""
    s = (text or "").strip()
    if not s:
        return ""

    def _bracket_repl(match: re.Match[str]) -> str:
        if match.group(1).strip().lower() == "pause":
            return match.group(0)
        return " "

    s = re.sub(r"\[([^\]]+)\]", _bracket_repl, s)
    s = re.split(
        r"\s+\[(?:Faces|Stage|Expression|Camera|Only|Match|Audio|Children|Show|Rooted)",
        s,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    s = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", s).strip()
    s = re.sub(r"\s*\[[^\]]+\]\s*$", "", s).strip()
    return re.sub(r"\s+", " ", s).strip()


_O3_BODY_PROSE_BIAS_RE = re.compile(
    r"(?:"
    r"speaks?\s+directly\s+(?:to|at)\s+(?:the\s+)?camera"
    r"|directly\s+(?:to|at)\s+(?:the\s+)?camera"
    r"|child\s+viewer\s+is\s+off[- ]screen"
    r"|gesture\s+toward\s+the\s+lens"
    r"|warmly\s+conspiratorial"
    r"|knowing\s+and\s+warmly"
    r"|inviting\s+nod"
    r")",
    re.IGNORECASE,
)


_O3_CANONICAL_CAMERA_FRAMING_RE = re.compile(
    r"^Camera:\s*static locked shot,\s*(?:"
    r"stable eye-level close-up on @Image1"
    r"|no zoom, no dolly, no pan, no camera movement, stable eye-level close-up"
    r"|no zoom, no dolly, no pan, no camera movement, stable eye-level medium shot"
    r")",
    re.I,
)


def _prompt_body_line_has_o3_delivery_bias(line: str) -> bool:
    """Prose staging outside the voice line that biases O3 toward hyper delivery."""
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _O3_CANONICAL_CAMERA_FRAMING_RE.match(stripped):
        return False
    if re.match(r"^Camera\s*:", stripped, re.IGNORECASE):
        return True
    if _O3_BODY_PROSE_BIAS_RE.search(stripped):
        return True
    return spoken_has_performance_staging(stripped)


def _strip_o3_body_prose_bias_from_line(line: str) -> str:
    """Remove inline speak-to-camera / viewer staging from a non-voice prompt line."""
    cleaned = (line or "").strip()
    if not cleaned or _is_voice_delivery_line(cleaned):
        return cleaned
    cleaned = re.sub(
        r"\s*[;.]\s*[^.]*speaks?\s+directly\s+(?:to|at)\s+(?:the\s+)?camera[^.]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s*[;.]\s*the child viewer is off[- ]screen[^.]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s*@Image1\s+speaks?\s+directly\s+(?:to|at)\s+(?:the\s+)?camera[^.]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ;.")
    return cleaned


def spoken_has_performance_staging(text: str) -> bool:
    """True when dialogue still contains bracketed stage directions (not [pause])."""
    raw = (text or "").strip()
    if not raw:
        return False
    for match in re.finditer(r"\[([^\]]+)\]", raw):
        inner = match.group(1).strip().lower()
        if inner == "pause":
            continue
        if any(
            token in inner
            for token in (
                "faces",
                "camera",
                "rooted",
                "expression",
                "eyebrow",
                "gesture",
                "nod",
                "smile",
                "hand raised",
                "stage",
            )
        ):
            return True
    return False


def prompt_voice_quote_has_performance_staging(prompt: str) -> bool:
    """Detect author staging baked into the quoted O3 voice line."""
    text = (prompt or "").strip()
    if not text:
        return False
    for match in re.finditer(
        r"\b(?:speaks|says)[^:\"']*:\s*\"([^\"]+)\"",
        text,
        re.IGNORECASE,
    ):
        if spoken_has_performance_staging(match.group(1)):
            return True
    return False


def _is_voice_delivery_line(line: str) -> bool:
    return bool(re.search(r"\b(?:speaks|says)\b", line or "", re.I) and ":" in line)


def _find_voice_delivery_line_index(lines: list[str]) -> int | None:
    for idx, line in enumerate(lines):
        if _is_voice_delivery_line(line.strip()):
            return idx
    return None


def _minimal_element_o3_header(prompt: str, speaker: str) -> str:
    """KLING_O3_CANONICAL_PROMPT_SHAPE_V2 — @Image1 + scene ref only; no arc/beat slug."""
    try:
        import kling_character_registry as reg
    except ImportError:
        from tools import kling_character_registry as reg  # type: ignore
    label = reg.kling_image1_speaker_label(speaker) or speaker
    return f"@Image1 ({label}). Scene from @Image2."


def _kling_o3_style_line(prompt: str) -> str:
    for line in (prompt or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("children's illustrated"):
            return stripped
    return "Children's illustrated fantasy storybook style, warm golden Everdale light."


def prompt_body_has_performance_staging(prompt: str) -> bool:
    """True when performance staging sits in the prompt body before the voice line."""
    lines = (prompt or "").splitlines()
    voice_idx = _find_voice_delivery_line_index(lines)
    stop = voice_idx if voice_idx is not None else len(lines)
    for line in lines[:stop]:
        stripped = line.strip()
        if not stripped or _is_voice_delivery_line(stripped):
            continue
        if _prompt_body_line_has_o3_delivery_bias(stripped):
            return True
    return False


def _clean_prompt_body_staging_line(stripped: str) -> str:
    """Strip delivery-bias brackets/prose from one non-voice prompt line; keep safe framing."""
    if not stripped or _is_voice_delivery_line(stripped):
        return ""
    if re.match(r"^Camera\s*:", stripped, re.IGNORECASE):
        return ""
    cleaned = stripped
    while True:
        next_clean = re.sub(
            r"\s*\[[^\]]*(?:faces|camera|rooted|expression|eyebrow|gesture|nod|smile|hand raised)[^\]]*\]\s*\"?\s*",
            " ",
            cleaned,
            count=1,
            flags=re.I,
        )
        if next_clean == cleaned:
            break
        cleaned = next_clean
    cleaned = _strip_o3_body_prose_bias_from_line(cleaned)
    cleaned = cleaned.strip().strip('"').strip()
    if cleaned and not _prompt_body_line_has_o3_delivery_bias(cleaned):
        return cleaned
    return ""


def strip_performance_staging_from_kling_prompt(prompt: str) -> str:
    """Remove author performance brackets and prose bias from non-voice prompt lines."""
    lines = (prompt or "").splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if out and out[-1].strip():
                out.append("")
            continue
        if _is_voice_delivery_line(stripped):
            out.append(line)
            continue
        cleaned = _clean_prompt_body_staging_line(stripped)
        if cleaned:
            out.append(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return text


_O3_SAFE_FRAMING_STAGING_RE = re.compile(
    r"(?:"
    r"close[- ]?up"
    r"|medium\s+shot"
    r"|wide\s+shot"
    r"|full[- ]?body"
    r"|head\s+and\s+torso"
    r"|bust(?:\s+shot)?"
    r"|waist[- ]?up"
    r"|upper\s+body"
    r"|showing\s+(?:her|his|their|the)\s+(?:head|torso|face|upper)"
    r"|(?:head|face)\s+and\s+torso"
    r"|single\s+character\s+in\s+(?:the\s+)?frame"
    r")",
    re.IGNORECASE,
)


def _line_is_safe_framing_direction(line: str) -> bool:
    """True when a prompt-body line is camera/framing direction, not performance acting."""
    return bool(_O3_SAFE_FRAMING_STAGING_RE.search(line or ""))


def _extract_safe_screen_direction_from_prompt(prompt: str, speaker: str) -> str:
    """Collect safe framing/staging from prompt body when scene_notes is empty."""
    lines = (prompt or "").splitlines()
    voice_idx = _find_voice_delivery_line_index(lines)
    stop = voice_idx if voice_idx is not None else len(lines)
    kept: list[str] = []
    for line in lines[:stop]:
        stripped = line.strip()
        if not stripped or stripped.startswith("@Image"):
            continue
        if stripped.lower().startswith("children's illustrated"):
            continue
        cleaned = _clean_prompt_body_staging_line(stripped)
        if cleaned and _line_is_safe_framing_direction(cleaned):
            kept.append(cleaned)
    return " ".join(kept).strip()


def sync_beat_scene_notes_from_kling_prompt(beat: dict) -> bool:
    """When scene_notes is empty, persist safe prompt-body staging for Element-bound heals."""
    if str(beat.get("scene_notes") or "").strip():
        return False
    speaker = str(beat.get("speaker") or "").strip()
    if not speaker or not _speaker_has_element_bound_voice(speaker):
        return False
    extracted = _extract_safe_screen_direction_from_prompt(
        str(beat.get("kling_o3_prompt") or ""),
        speaker,
    )
    if not extracted:
        return False
    beat["scene_notes"] = extracted
    return True


def normalize_o3_element_bound_prompt(beat: dict, prompt: str | None = None) -> str:
    """Rebuild Element-bound O3 prompt: header + screen direction + voice + style + locks."""
    speaker = str(beat.get("speaker") or "").strip()
    raw = (prompt if prompt is not None else beat.get("kling_o3_prompt") or "").strip()
    if not raw or not speaker:
        return raw
    from beat_extract_policy import (
        humanize_kling_body_parts,
        o3_element_composite_paragraph,
        o3_element_framing_paragraph,
        prompt_has_o3_element_composite,
    )

    raw = humanize_kling_body_parts(raw, speaker=speaker)
    spoken = extract_spoken_dialogue_from_kling_prompt(raw)
    if not spoken:
        spoken = _spoken_from_beat_dialogue(beat)
    try:
        import kling_o3_prompt as o3p
    except ImportError:
        from tools import kling_o3_prompt as o3p  # type: ignore

    emotion = str(beat.get("emotion") or "").strip()
    scene_notes = str(beat.get("scene_notes") or "").strip()
    if not scene_notes:
        scene_notes = _extract_safe_screen_direction_from_prompt(raw, speaker)
    header = _minimal_element_o3_header(raw, speaker)
    screen = o3_element_framing_paragraph(speaker, scene_notes)
    style = _kling_o3_style_line(raw)
    if not spoken:
        parts = [header]
        if "@Image2" in header and not prompt_has_o3_element_composite(raw):
            parts.append(o3_element_composite_paragraph(speaker))
        if screen:
            parts.append(screen)
        if style:
            parts.append(style)
        shell = "\n\n".join(parts)
        return o3p.normalize_canonical_prompt_vocabulary(
            _append_kling_o3_submit_locks(
                shell,
                speaker=speaker,
                spoken="",
                element_bound=True,
            ),
        )
    voice_line = o3p.voice_block(speaker, spoken, emotion=emotion)
    parts = [header]
    if "@Image2" in header and not prompt_has_o3_element_composite(raw):
        parts.append(o3_element_composite_paragraph(speaker))
    if screen:
        parts.append(screen)
    parts.append(voice_line)
    parts.append(style)
    shell = "\n\n".join(parts)
    return o3p.normalize_canonical_prompt_vocabulary(
        _append_kling_o3_submit_locks(
            shell,
            speaker=speaker,
            spoken=spoken,
            element_bound=True,
        ),
    )


def _beat_dialogue_exceeds_kling_max_bucket(beat: dict, prompt: str | None = None) -> bool:
    """True when spoken line local estimate exceeds largest Kling duration bucket."""
    text = (prompt if prompt is not None else beat.get("kling_o3_prompt") or "").strip()
    spoken = _spoken_for_duration_estimate(text, beat=beat)
    if not spoken:
        return False
    staging = _kling_o3_has_pre_speech_staging(text)
    unsnapped = estimate_kling_o3_seconds_unsnapped(
        spoken,
        has_pre_speech_staging=staging,
    )
    return unsnapped > float(KLING_O3_MAX_DURATION) + 0.75


def heal_semi_canonical_arlo_voice_contract(beat: dict) -> bool:
    """Fix semi-canonical transition beat emotion/dialogue — never rewrite stored prompt."""
    if beat.get("intro_beat_role") != INTRO_BEAT_ROLE_SEMI_CANONICAL:
        return False
    if str(beat.get("speaker") or "").strip() != "Arlo":
        return False
    changed = False
    emo = str(beat.get("emotion") or "").strip().lower()
    if emo in ("", "upbeat", "[upbeat]"):
        beat["emotion"] = "warm"
        changed = True
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    compact = ARLO_SEMI_CANONICAL_COMPACT_DIALOGUE
    if _beat_dialogue_exceeds_kling_max_bucket(beat, prompt):
        if (beat.get("dialogue_text") or "").strip() != compact:
            beat["dialogue_text"] = compact
            changed = True
    return changed


def heal_legacy_kling_o3_prompt_v2_shape(beat: dict) -> bool:
    """Rebuild stored prompts that fail V2 lint — still-insert and valid V2 prompts untouched."""
    if beat_is_still_insert(beat):
        return False
    sp = (beat.get("speaker") or "").strip()
    if sp in ("[Stage Direction]", "Character", ""):
        return False
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt:
        return False
    from kling_o3_prompt import kling_o3_prompt_passes_v2_lint

    if kling_o3_prompt_passes_v2_lint(prompt):
        return False
    if is_still_insert_prompt_text(prompt):
        return False
    rebuilt = build_kling_o3_prompt(beat)
    if not rebuilt or not kling_o3_prompt_passes_v2_lint(rebuilt):
        return False
    beat["kling_o3_prompt"] = rebuilt
    return True


_AVATAR_PRO_PROMPT_POISON_MARKERS = (
    "TRIPOD LOCK",
    "Continutiy:",
    "chest-up portrait",
    "input portrait of ",
    "kling_o3_avatar_pro",
    "o3_avatar_pro_v1",
)


def o3_prompt_is_avatar_pro_poisoned(prompt: str, *, beat: dict | None = None) -> bool:
    """True when stored text carries positive Avatar Pro staging markers.

    Missing ``@Image1`` alone is not poison — operator verbatim and legacy
    stored prompts must survive ``_migrate_sidecar`` (prompt-box law).
    """
    text = (prompt or "").strip()
    if not text:
        return False
    if beat and str(beat.get("kling_o3_mode") or "").strip() == KLING_O3_MODE_AVATAR:
        return True
    lower = text.lower()
    if any(marker.lower() in lower for marker in _AVATAR_PRO_PROMPT_POISON_MARKERS):
        return True
    if text.startswith("Continuity:") and "@Image1" not in text[:200]:
        return True
    return False


def heal_avatar_pro_poisoned_o3_prompt(beat: dict, sidecar: dict | None = None) -> bool:
    """Restore Element/Omni V2 prompts after Avatar Pro pollution (not operator verbatim)."""
    if beat_is_still_insert(beat):
        return False
    sp = (beat.get("speaker") or "").strip()
    if sp in ("[Stage Direction]", "Character", ""):
        return False
    if sidecar is not None:
        mode = resolve_beat_generation_mode(beat, sidecar)
        if mode == O3_GENERATE_MODE_AVATAR and not beatgen_avatar_pro_disabled():
            return False
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt:
        return False
    from kling_o3_prompt import kling_o3_prompt_passes_v2_lint

    poisoned = o3_prompt_is_avatar_pro_poisoned(prompt, beat=beat)
    if o3_prompt_box_law_active(beat) and not poisoned:
        return False
    if not poisoned:
        if kling_o3_prompt_passes_v2_lint(prompt):
            return False
        if beat_has_stored_kling_prompt(beat):
            return False
    rebuilt = build_kling_o3_prompt(beat)
    if not rebuilt or not kling_o3_prompt_passes_v2_lint(rebuilt):
        return False
    beat["kling_o3_prompt"] = rebuilt
    if str(beat.get("kling_o3_mode") or "").strip() == KLING_O3_MODE_AVATAR:
        beat["kling_o3_mode"] = KLING_O3_MODE_ELEMENT_NATIVE
    for key in ("o3_generate_mode", "generation_mode", "kling_o3_generate_mode"):
        if (beat.get(key) or "").strip().lower() == O3_GENERATE_MODE_AVATAR:
            beat[key] = O3_GENERATE_MODE_ELEMENT_NATIVE
    clear_o3_prompt_box_law(beat)
    return True


def heal_o3_element_submit_prompt(beat: dict) -> bool:
    """Disabled — operator prompt is verbatim; no server-side prompt rebuild."""
    return False


def heal_element_bound_voice_prompt(beat: dict) -> bool:
    """Disabled — operator prompt is verbatim; no server-side voice-line upgrade."""
    return False


def _kling_o3_normalize_spoken(spoken: str) -> str:
    """Normalize dialogue for Kling TTS — ellipses and runaway dots cause drag/baby-talk."""
    s = (spoken or "").strip()
    s = _strip_bracket_staging_from_spoken(s)
    s = _strip_parenthetical_actions(s)
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"…+", ".", s)
    s = re.sub(r"\s+", " ", s).strip()
    try:
        import kling_o3_prompt as o3p
    except ImportError:
        from tools import kling_o3_prompt as o3p  # type: ignore
    return o3p.normalize_canonical_prompt_vocabulary(s)


def _strip_parenthetical_actions(text: str) -> str:
    """Remove (gestures...) / (makes eye contact...) — staging belongs outside quotes."""
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", text or "")).strip()


def _normalize_spoken_for_duration(spoken: str) -> str:
    """Spoken word count for duration math — never count () or [] stage directions."""
    s = (spoken or "").strip()
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = _strip_parenthetical_actions(s)
    return re.sub(r"\s+", " ", s).strip()


def _spoken_for_duration_estimate(prompt: str, *, beat: dict | None = None) -> str:
    """Best spoken text for duration math — longest trustworthy source wins."""
    candidates: list[str] = []
    extracted = extract_spoken_dialogue_from_kling_prompt(prompt) or ""
    if extracted:
        candidates.append(_normalize_spoken_for_duration(extracted))
    bracket = _extract_bracket_tag_dialogue(prompt)
    if bracket:
        candidates.append(_normalize_spoken_for_duration(bracket))
    if beat:
        beat_spoken = _spoken_from_beat_dialogue(beat)
        if beat_spoken:
            candidates.append(_normalize_spoken_for_duration(beat_spoken))
    if not candidates:
        return ""
    return max(candidates, key=lambda s: len(re.findall(r"\S+", s)))


def heal_kling_o3_stored_duration(beat: dict) -> bool:
    """Re-sync sidecar kling_o3_duration from prompt when not manually locked."""
    if beat.get("kling_o3_duration_locked"):
        return False
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt:
        return False
    prepared = prepare_kling_o3_prompt_for_submit(beat, prompt)
    resolved = resolve_kling_o3_submit_duration(beat, prepared)
    try:
        stored = int(beat.get("kling_o3_duration") or 0)
    except (TypeError, ValueError):
        stored = 0
    if stored != resolved:
        beat["kling_o3_duration"] = resolved
        return True
    return False


def heal_spoken_staging_in_voice_prompt(beat: dict) -> bool:
    """Disabled — operator prompt is verbatim after materialization."""
    return False


def apply_live_kling_o3_prompts(sidecar: dict, beat_prompts: dict) -> int:
    """Persist live prompt-box text from Submit/Redo before validation."""
    updated = 0
    if not beat_prompts:
        return updated
    for beat_id, prompt in beat_prompts.items():
        if not isinstance(prompt, str):
            continue
        _, beat = find_beat(sidecar, beat_id)
        if not beat:
            continue
        text = prompt.strip()
        beat["kling_o3_prompt"] = text
        sync_beat_dialogue_from_kling_prompt(beat)
        # Preserve manual duration lock — only re-estimate when unlocked.
        if not beat.get("kling_o3_duration_locked"):
            prepared = prepare_kling_o3_prompt_for_submit(beat, text)
            beat["kling_o3_duration"] = resolve_kling_o3_submit_duration(beat, prepared)
        updated += 1
    return updated


KLING_O3_CHIPPER_VOICE_DELIVERY = (
    "warm calm conversational pace, steady and natural, clear delivery, "
    "brisk but not rushed, not bubbly or hyper, not slow, not dramatic, not childlike or baby-talk"
)

KLING_O3_TESSA_VOICE_DELIVERY = (
    "warm gentle conversational pace, soft and vulnerable but clear, natural delivery, "
    "steady and not slow, not dragging, not whispered, not childlike or baby-talk"
)

# Loral (raccoon scholar; registry key Lorelai — "Loral" in voice lines for Element bind).
KLING_O3_LORELAI_VOICE_DELIVERY = (
    "warm calm conversational pace, clear and natural, measured steady cadence, "
    "not frantic or hyper, not over-emotional or melodramatic, "
    "not dragging, not childlike or baby-talk"
)

# Locked-line imports still carry pre-rename Pip/Alex copy — replace only when
# auto-building a prompt from dialogue_text (never on manual prompt-box submit).
_CHIPPER_LEGACY_DIALOGUE_MARKERS = (
    "pip",
    "alex",
    "apprentice",
    "training her",
    "magical arts",
)

_CHIPPER_LEGACY_INTRO_SPOKEN = (
    "Well maybe we can help. I'm Chipper, assistant to the Great Wizard. "
    "We can use magic to help friends who need it."
)


def _is_chipper_intro_beat(beat: dict) -> bool:
    if (beat.get("speaker") or "").strip() != "Chipper":
        return False
    scene = (beat.get("scene_notes") or "").lower()
    return "intro" in scene or "introduction" in scene


def _dialogue_has_legacy_chipper_content(text: str) -> bool:
    raw = (text or "").lower()
    return any(m in raw for m in _CHIPPER_LEGACY_DIALOGUE_MARKERS)


def sync_beat_dialogue_from_kling_prompt(beat: dict) -> bool:
    """Align ``dialogue_text`` with quoted speech in the prompt box (TTS / still path)."""
    if beat_is_still_insert(beat):
        tts = extract_still_insert_tts(beat)
        if tts and tts.get("text"):
            spoken = tts["text"]
            if (beat.get("dialogue_text") or "").strip() != spoken:
                beat["dialogue_text"] = spoken
                return True
        return False
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt:
        return False
    spoken = extract_spoken_dialogue_from_kling_prompt(prompt)
    if not spoken:
        return False
    if (beat.get("dialogue_text") or "").strip() == spoken:
        return False
    beat["dialogue_text"] = spoken
    return True


def _curated_kling_o3_spoken(beat: dict) -> str | None:
    """Return canonical intro quote when dialogue_text still has Pip/Alex locked lines."""
    if not _is_chipper_intro_beat(beat):
        return None
    if _dialogue_has_legacy_chipper_content(beat.get("dialogue_text") or ""):
        return _CHIPPER_LEGACY_INTRO_SPOKEN
    return None


def _strip_orphan_speaker_lines(text: str, speaker: str) -> str:
    """Remove stray 'Chipper' lines left from manual edits before voice block."""
    if not speaker:
        return text
    lines = (text or "").splitlines()
    out: list[str] = []
    for line in lines:
        if line.strip().lower() == speaker.strip().lower():
            continue
        out.append(line)
    return "\n".join(out).strip()


def _kling_o3_chipper_intro_staging() -> str:
    return (
        "Only @Image1 is visible in the frame. No other characters, creatures, or people "
        "on screen. Chipper speaks directly to the camera; the child viewer is off-screen "
        "and must never appear in the frame. @Image1 gestures toward the lens only — "
        "no second person visible on screen."
    )


def _kling_o3_visual_action_clause(beat: dict, spoken: str) -> str:
    speaker = (beat.get("speaker") or "").strip()
    scene = (beat.get("scene_notes") or "").lower()
    emotion = (beat.get("emotion") or "").lower()
    if speaker == "Chipper":
        if any(k in scene for k in ("intro", "introduction")):
            base = (
                "Chipper — Introduction. Perched on a branch, making welcoming eye "
                "contact with the camera; the child viewer is off-screen"
            )
        elif "discovery" in scene or any(k in emotion for k in ("upset", "concern", "shock")):
            base = (
                "Chipper — Discovery. Perched on a large branch with gentle peer-level "
                "concern toward someone off-screen (not talking down)"
            )
        else:
            base = _emotion_action_clause(beat)
        return base + _kling_o3_viewer_staging_clause(spoken)
    if speaker in ("Luna", "Lorelai"):
        label = "Loral"
        if "discovery" in scene or any(k in emotion for k in ("upset", "shock", "excited", "happy")):
            base = (
                f"{label} — Discovery. Excitable raccoon scholar with glasses and backpack, "
                "wide expressive eyes, reacting in the heartwood grove"
            )
        else:
            base = f"{label} — {_emotion_action_clause(beat)}"
        return base + _kling_o3_viewer_staging_clause(spoken)
    return _emotion_action_clause(beat) + _kling_o3_viewer_staging_clause(spoken)


def _kling_o3_voice_line_display_name(speaker: str, element_name: str | None) -> str:
    """Kling O3 voice line name — must match element_list element_name."""
    try:
        from tools import kling_character_registry as reg

        display = reg.kling_element_display_name(speaker)
        if display:
            return display
    except Exception:
        pass
    return (element_name or (speaker or "").strip() or "Character").strip()


def _kling_o3_voice_block(speaker: str, spoken: str, emotion: str = "") -> str:
    """Dialogue block for Kling native audio — delegates to kling_o3_prompt.voice_block."""
    spoken = _kling_o3_normalize_spoken(spoken)
    try:
        from tools import kling_o3_prompt as o3p

        return o3p.voice_block(speaker, spoken, emotion=emotion)
    except Exception:
        pass
    canon = (speaker or "Character").strip()
    if canon == "Tessa":
        return f'Tessa speaks in a {KLING_O3_TESSA_VOICE_DELIVERY}: "{spoken}"'
    return f'@Image1 <<<voice_1>>> speaks clearly at a natural pace: "{spoken}"'


def build_kling_o3_prompt(beat: dict) -> str:
    speaker = beat.get("speaker") or "Character"
    curated = _curated_kling_o3_spoken(beat)
    if curated:
        spoken = _kling_o3_normalize_spoken(curated)
    else:
        dialogue = (beat.get("dialogue_text") or "").strip()
        spoken = re.sub(r"\[[^\]]+\]", " ", dialogue)
        spoken = _kling_o3_normalize_spoken(re.sub(r"\s+", " ", spoken).strip())
        if not spoken:
            spoken = _kling_o3_normalize_spoken(dialogue)

    action = _kling_o3_visual_action_clause(beat, spoken)
    prior_ctx = (beat.get("kling_o3_prior_beat_context") or "").strip()
    if prior_ctx and prior_ctx not in action:
        action = f"{prior_ctx}\n\n{action}"
    voice_block = _kling_o3_voice_block(
        speaker, spoken, emotion=str(beat.get("emotion") or ""),
    )
    try:
        from tools import kling_character_registry as reg

        image1_label = reg.kling_image1_speaker_label(speaker)
    except Exception:
        image1_label = speaker
    intro_staging = ""
    if _is_chipper_intro_beat(beat):
        intro_staging = f"\n\n{_kling_o3_chipper_intro_staging()}"
    composite_block = ""
    if _speaker_has_element_bound_voice(speaker):
        from beat_extract_policy import o3_element_composite_paragraph

        composite_block = f"{o3_element_composite_paragraph(speaker)}\n\n"
    try:
        import kling_o3_prompt as o3p
    except ImportError:
        from tools import kling_o3_prompt as o3p  # type: ignore
    return o3p.normalize_canonical_prompt_vocabulary(
        _append_kling_o3_submit_locks(
            (
                f"@Image1 ({image1_label}) {action}. Scene from @Image2.\n\n"
                f"{composite_block}"
                f"{KLING_O3_CAMERA_LOCK}"
                f"{intro_staging}\n\n"
                f"{voice_block}\n\n"
                "Children's illustrated fantasy storybook style, warm golden forest light."
            ),
            speaker=speaker,
            spoken=spoken,
        ),
    )


def _ref_dict_from_path(abs_path: str) -> dict:
    return {"abs_path": abs_path, "key": Path(abs_path).stem}


BEAT_REF_LOCK_FIELDS: dict[str, str] = {
    "reference_image": "reference_image_locked",
    "bg_ref_image": "bg_ref_image_locked",
    "start_frame_image": "start_frame_image_locked",
    "end_frame_image": "end_frame_image_locked",
}


def _is_event_library_char_ref(char_path: str) -> bool:
    """True when @Image1 path is an uploaded per-event library still (not Element pose dir)."""
    if not char_path:
        return False
    norm = os.path.normpath(char_path)
    marker = f"{os.sep}library{os.sep}images{os.sep}"
    if marker not in norm:
        return False
    # Exclude paths already under Production/<Char>/poses/ (Element registration).
    if f"{os.sep}poses{os.sep}" in norm:
        return False
    return True


def heal_locked_char_ref_to_element(beat: dict) -> bool:
    """Redirect locked beat @Image1 to a registered Element pose when misaligned.

    Never writes into Event_*/library/images/sources/ — overwriting library tiles
    destroyed user uploads (neutral stills replaced by Element pose bytes).
    Sidecar pointer update only; library inventory bytes stay immutable.
    """
    if not beat.get("reference_image_locked"):
        return False
    speaker = str(beat.get("speaker") or "").strip()
    if not speaker:
        return False
    char_path = resolve_beat_char_ref_path(beat)
    if not char_path:
        ref = beat.get("reference_image")
        if isinstance(ref, dict):
            pending = str(ref.get("abs_path") or "").strip()
            if pending and _is_event_library_char_ref(pending):
                char_path = os.path.normpath(pending)
    if not char_path:
        return False
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return False
        if os.path.isfile(char_path) and reg.char_ref_matches_element_images(char_path, speaker)[0]:
            return False
        # Locked per-event library uploads: never redirect sidecar pointer when the
        # tile still exists on disk — user chose that still; gate stays false until
        # they pick an Element pose or re-upload. (Redirect only when path is broken.)
        if _is_event_library_char_ref(char_path) and os.path.isfile(char_path):
            return False
        element_paths = reg.element_image_paths(speaker)
        if not element_paths:
            return False
        chosen_str = str(_pick_element_ref_path(beat, element_paths).resolve())
        if os.path.normpath(char_path) == os.path.normpath(chosen_str):
            return False
        beat["reference_image"] = _ref_dict_from_path(chosen_str)
        return True
    except Exception:
        return False


def apply_user_beat_ref_update(beat: dict, field: str, value) -> None:
    """Apply explicit user ref drop/clear — lock so auto-align won't revert."""
    lock_field = BEAT_REF_LOCK_FIELDS.get(field)
    if lock_field is None:
        beat[field] = value
        return
    if isinstance(value, dict) and (value.get("abs_path") or value.get("key")):
        beat[field] = value
        beat[lock_field] = True
        if field == "reference_image":
            # User explicitly chose this tile — validate gate only; never rewrite library bytes.
            sync_element_char_ref_status(beat, heal_mismatch=False)
    elif value is None:
        beat[field] = None
        beat[lock_field] = False
        if field == "reference_image":
            sync_element_char_ref_status(beat)
    else:
        beat[field] = value


def hydrate_beat_ref_images(beat: dict, approved_roots: list[str]) -> bool:
    """Ensure reference_image / bg_ref_image have thumb_b64 when abs_path is set.

    Returns True when any ref dict was updated (caller may persist sidecar).
    """
    changed = False
    for field in ("reference_image", "bg_ref_image", "start_frame_image", "end_frame_image"):
        ref = beat.get(field)
        if not isinstance(ref, dict) or ref.get("thumb_b64"):
            continue
        abs_path = ref.get("abs_path") or ""
        if not abs_path:
            continue
        from lib.event_library import ref_image_thumb_b64

        thumb = ref_image_thumb_b64(abs_path, approved_roots)
        if thumb:
            ref["thumb_b64"] = thumb
            changed = True
    return changed


def _pick_element_ref_path(beat: dict, element_paths: list[Path]) -> Path:
    """Choose Element-set still closest to beat emotion (else frontal)."""
    if not element_paths:
        raise ValueError("element_paths required")
    scene = (beat.get("scene_notes") or "").lower()
    if any(k in scene for k in ("intro", "introduction")):
        for path in element_paths:
            if "branch" in path.stem.lower():
                return path
    emotion = (beat.get("emotion") or "").lower()
    keywords: list[str] = []
    if any(k in emotion for k in ("sad", "disappointed", "concern", "scared", "upset")):
        keywords = ["sad", "concern", "worried", "scared"]
    elif any(k in emotion for k in ("happy", "excited", "joy")):
        keywords = ["happy", "excited", "joy"]
    elif "neutral" in emotion:
        keywords = ["neutral", "canonical"]
    if keywords:
        for path in element_paths:
            stem = path.stem.lower()
            if any(kw in stem for kw in keywords):
                return path
    return element_paths[0]


def infer_char_ref_registry_speaker(char_path: str) -> str | None:
    """Return registry character name when @Image1 bytes belong to their Element set."""
    if not char_path or not os.path.isfile(char_path):
        return None
    try:
        from tools import kling_character_registry as reg

        data = reg.load_character_subjects()
        for name in (data.get("characters") or {}):
            if not reg.is_speaker_voice_ready(name):
                continue
            if reg.char_ref_matches_element_images(
                char_path, name, allow_pose_dir_fallback=True,
            )[0]:
                return name
    except Exception:
        return None
    return None


def realign_beat_char_ref_for_speaker_change(
    beat: dict,
    *,
    old_speaker: str = "",
) -> bool:
    """After speaker changes, drop @Image1 that belonged to the previous character."""
    speaker = str(beat.get("speaker") or "").strip()
    if not speaker:
        return False
    prev = str(old_speaker or "").strip()
    if prev and prev == speaker:
        return False
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return False
    except Exception:
        return False
    char_path = resolve_beat_char_ref_path(beat)
    if not char_path:
        return align_beat_reference_to_element(beat)
    try:
        from tools import kling_character_registry as reg

        if reg.char_ref_matches_element_images(
            char_path, speaker, allow_pose_dir_fallback=True,
        )[0]:
            return False
        if prev and reg.char_ref_matches_element_images(
            char_path, prev, allow_pose_dir_fallback=True,
        )[0]:
            beat.pop("reference_image_locked", None)
            beat.pop("reference_image", None)
            return align_beat_reference_to_element(beat)
    except Exception:
        pass
    owner = infer_char_ref_registry_speaker(char_path)
    if owner:
        try:
            from tools import kling_character_registry as reg

            owner_key = reg.resolve_registry_key(owner) or owner
            speaker_key = reg.resolve_registry_key(speaker) or speaker
        except Exception:
            owner_key, speaker_key = owner, speaker
        if owner_key != speaker_key:
            beat.pop("reference_image_locked", None)
            beat.pop("reference_image", None)
            return align_beat_reference_to_element(beat)
    if not beat.get("reference_image_locked"):
        return align_beat_reference_to_element(beat)
    return False


def heal_speaker_char_ref_mismatch(beat: dict) -> bool:
    """Persist heal when sidecar speaker and @Image1 bytes name different characters."""
    speaker = str(beat.get("speaker") or "").strip()
    char_path = resolve_beat_char_ref_path(beat)
    if not speaker or not char_path:
        return False
    if element_char_ref_gate(beat)[0]:
        return False
    owner = infer_char_ref_registry_speaker(char_path)
    if not owner:
        return False
    try:
        from tools import kling_character_registry as reg

        owner_key = reg.resolve_registry_key(owner) or owner
        speaker_key = reg.resolve_registry_key(speaker) or speaker
    except Exception:
        owner_key, speaker_key = owner, speaker
    if owner_key == speaker_key:
        return False
    beat.pop("reference_image_locked", None)
    beat.pop("reference_image", None)
    return align_beat_reference_to_element(beat)


def align_beat_reference_to_element(beat: dict) -> bool:
    """Point beat reference_image at the speaker's Element image set.

    Returns True when reference_image was created or updated.
    """
    speaker = beat.get("speaker") or ""
    if not speaker:
        return False
    if beat.get("reference_image_locked"):
        return False
    try:
        from tools import kling_character_registry as reg
        entry = reg.get_character_entry(speaker)
        if not entry or entry.get("status") != "active" or not entry.get("element_id"):
            return False
        element_paths = reg.element_image_paths(speaker)
        if not element_paths:
            return False
        chosen = _pick_element_ref_path(beat, element_paths)
        chosen_str = str(chosen.resolve())
        current = resolve_beat_char_ref_path(beat)
        if current and os.path.normpath(current) == os.path.normpath(chosen_str):
            return False
        beat["reference_image"] = _ref_dict_from_path(chosen_str)
        sync_element_char_ref_status(beat)
        return True
    except Exception:
        return False


def element_char_ref_gate(beat: dict) -> tuple[bool, str]:
    """Element O3 requires @Image1 to match registered Element pose files."""
    speaker = str(beat.get("speaker") or "").strip()
    if not speaker:
        return True, ""
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return True, ""
        char_path = resolve_beat_char_ref_path(beat)
        if not char_path:
            return False, f"Missing character reference image for {speaker!r}"
        aligned, detail = reg.char_ref_matches_element_images(
            char_path,
            speaker,
            allow_pose_dir_fallback=not bool(beat.get("reference_image_locked")),
        )
        if not aligned:
            return False, detail
        return True, ""
    except Exception as exc:
        return False, str(exc)


def beat_o3_voice_job_running(beat: dict) -> bool:
    """Legacy sidecar-cache heuristic — diagnostics only; use ``beat_o3_operator_busy`` for gates."""
    from o3_job_status_contract import beat_o3_voice_job_running as _contract_running
    return _contract_running(beat)


def _beat_pipeline_operator_busy(beat: dict) -> bool:
    from o3_job_status_contract import beat_o3_operator_busy, beat_o3_voice_job_running

    beat_id = str(beat.get("beat_id") or "").strip()
    ev = event_dir_for_beat_id(beat_id) if beat_id else None
    if beat_id and beat_o3_operator_busy(beat, ev):
        return True
    # Sidecar-cache heuristic when lifecycle pointer/terminal not resolvable (no beat_id yet).
    return beat_o3_voice_job_running(beat)


_O3_VOICE_FIX_RUNNING_STATUSES_UNUSED = frozenset({
    "o3_running",
    "job_running",
    "job_starting",
    "visual_running",
    "lipsync_running",
    "tts_ready",
})


def sync_element_char_ref_status(
    beat: dict,
    *,
    heal_mismatch: bool = True,
    sidecar: dict | None = None,
) -> bool:
    """Persist element_char_ref_ok/error on beat for UI + submit gates."""
    if not element_char_ref_required_for_beat(beat, sidecar):
        beat.pop("element_char_ref_ok", None)
        beat.pop("element_char_ref_error", None)
        return True
    if _beat_pipeline_operator_busy(beat):
        beat["element_char_ref_ok"] = True
        beat.pop("element_char_ref_error", None)
        return True
    speaker = str(beat.get("speaker") or "").strip()
    try:
        from tools import kling_character_registry as reg

        if not speaker or not reg.is_speaker_voice_ready(speaker):
            beat.pop("element_char_ref_ok", None)
            beat.pop("element_char_ref_error", None)
            return True
    except Exception:
        beat.pop("element_char_ref_ok", None)
        beat.pop("element_char_ref_error", None)
        return True
    if heal_mismatch and beat.get("reference_image_locked"):
        heal_locked_char_ref_to_element(beat)
    ok, detail = element_char_ref_gate(beat)
    beat["element_char_ref_ok"] = ok
    if ok:
        beat.pop("element_char_ref_error", None)
    else:
        beat["element_char_ref_error"] = detail
    return ok


def require_element_char_ref_for_o3(beat: dict, sidecar: dict | None = None) -> None:
    """Raise before Element O3 subprocess/API work if @Image1 is wrong."""
    if not element_char_ref_required_for_beat(beat, sidecar):
        return
    if not sync_element_char_ref_status(beat, heal_mismatch=False, sidecar=sidecar):
        detail = beat.get("element_char_ref_error") or "char ref does not match Element poses"
        raise RuntimeError(f"ELEMENT_VISUAL_MISMATCH: {detail}")



def reconcile_refer_if_pose_hash_matches(beat: dict, wavespeed_key: str | None) -> bool:
    speaker = str(beat.get("speaker") or "").strip()
    char_path = resolve_beat_char_ref_path(beat)
    if not speaker or not char_path:
        return False
    try:
        from tools import kling_character_registry as reg
        if not reg.is_speaker_voice_ready(speaker):
            return False
        if reg.char_ref_matches_element_images(char_path, speaker)[0]:
            beat.pop("element_refer_reconcile_pending", None)
            return False
        char_key = reg.resolve_registry_key(speaker) or speaker
        rel_pose = reg.find_pose_rel_by_hash(char_key, char_path)
        if not rel_pose:
            return False
        cfg = reg.get_character_entry(speaker) or {}
        if rel_pose in [str(r) for r in (cfg.get("refer_images") or [])]:
            beat.pop("element_refer_reconcile_pending", None)
            return False
        if not wavespeed_key:
            beat["element_refer_reconcile_pending"] = True
            return False
        reg.reconcile_char_ref_with_element(speaker, char_path, wavespeed_key)
        beat.pop("element_refer_reconcile_pending", None)
        sync_element_char_ref_status(beat, heal_mismatch=False)
        return True
    except Exception:
        return False

def ensure_beat_element_char_ref_for_o3(beat: dict, wavespeed_key: str) -> bool:
    """Sync Element char-ref gate; auto-reconcile on-disk pose copies before O3 submit."""
    if sync_element_char_ref_status(beat, heal_mismatch=True):
        return True
    speaker = str(beat.get("speaker") or "").strip()
    char_path = resolve_beat_char_ref_path(beat)
    if not speaker or not char_path:
        return False
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return sync_element_char_ref_status(beat, heal_mismatch=False)
    except Exception:
        return sync_element_char_ref_status(beat, heal_mismatch=False)
    if reconcile_refer_if_pose_hash_matches(beat, wavespeed_key):
        return sync_element_char_ref_status(beat, heal_mismatch=False)
    reg_result = try_register_dropped_char_ref_on_element(beat, wavespeed_key)
    if reg_result.get("ok"):
        return sync_element_char_ref_status(beat, heal_mismatch=False)
    try:
        from tools import kling_character_registry as reg

        reg.reconcile_char_ref_with_element(speaker, char_path, wavespeed_key)
    except Exception:
        return sync_element_char_ref_status(beat, heal_mismatch=False)
    return sync_element_char_ref_status(beat, heal_mismatch=False)


def try_register_dropped_char_ref_on_element(
    beat: dict,
    wavespeed_key: str,
) -> dict[str, Any]:
    """Register a dropped library char ref on the speaker's Kling Element when gate fails.

    Reconcile when bytes already exist under Production/<Char>/poses/; otherwise
    copy via add_element_pose (same as library Add to Element).
    """
    speaker = str(beat.get("speaker") or "").strip()
    char_path = resolve_beat_char_ref_path(beat) or ""
    if not speaker or not char_path or not wavespeed_key:
        return {"ok": False, "reason": "missing_inputs"}
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            return {"ok": False, "reason": "not_voice_ready"}
        if reg.char_ref_matches_element_images(
            char_path, speaker, allow_pose_dir_fallback=False,
        )[0]:
            return {"ok": True, "action": "already_matched"}
        try:
            out = reg.reconcile_char_ref_with_element(speaker, char_path, wavespeed_key)
            out["action"] = "reconciled"
            return out
        except FileNotFoundError:
            out = reg.add_element_pose(speaker, char_path, wavespeed_key)
            out["action"] = "added"
            return out
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def ensure_beat_element_aligned_reference(beat: dict) -> bool:
    """Auto-heal mismatched @Image1 before submit (unless user locked ref)."""
    return align_beat_reference_to_element(beat)


def resolve_beat_start_frame_path(beat: dict) -> str | None:
    """Beat Gen Pipeline B — explicit start frame drop slot."""
    ref = beat.get("start_frame_image")
    if isinstance(ref, dict):
        p = ref.get("abs_path") or ""
        if p and os.path.isfile(p):
            return os.path.normpath(p)
    return None


def resolve_beat_end_frame_path(beat: dict) -> str | None:
    """Beat Gen Pipeline B — explicit end frame drop slot."""
    ref = beat.get("end_frame_image")
    if isinstance(ref, dict):
        p = ref.get("abs_path") or ""
        if p and os.path.isfile(p):
            return os.path.normpath(p)
    return None


def resolve_beat_dropped_image_path(ref: dict | None) -> str | None:
    """Absolute path from an explicit Beat Gen image ref slot (no segment defaults)."""
    if isinstance(ref, dict):
        p = ref.get("abs_path") or ""
        if p and os.path.isfile(p):
            return os.path.normpath(p)
    return None


def resolve_beat_magic_still_source_path(beat: dict) -> str | None:
    """Still for Beat Gen magic_still — same priority as still_insert render (library slot before char ref)."""
    still = resolve_still_source_abs_path(beat)
    if still is not None:
        return str(still)
    for key in ("start_frame_image", "bg_ref_image", "end_frame_image", "reference_image"):
        p = resolve_beat_dropped_image_path(beat.get(key))
        if p:
            return p
    return resolve_beat_char_ref_path(beat)


def beat_magic_still_clip_path(beat: dict, event_dir: str | Path) -> Path | None:
    """Resolved on-disk path for ``magic_still_path`` when present."""
    name = beat.get("magic_still_path")
    if not name:
        return None
    p = Path(name)
    if not p.is_absolute():
        p = Path(event_dir) / name
    if p.is_file():
        return p.resolve()
    return None


def beat_has_stitch_export_clip(beat: dict, event_dir: str | Path) -> bool:
    """True when beat is ready for segment Send to Stitcher (Kling or magic-on-still)."""
    from kling_stitch_readiness import beat_kling_stitch_export_ready  # noqa: PLC0415

    return beat_kling_stitch_export_ready(beat, event_dir)


def resolve_kling_o3_submit_mode(beat: dict) -> str:
    """``reference`` (char+BG) or ``startend`` when both frame slots are filled."""
    if resolve_beat_start_frame_path(beat) and resolve_beat_end_frame_path(beat):
        return "startend"
    return "reference"


def resolve_beat_char_ref_path(beat: dict) -> str | None:
    ref = beat.get("reference_image")
    if isinstance(ref, dict):
        p = ref.get("abs_path") or ""
        if p and os.path.isfile(p):
            return os.path.normpath(p)
    speaker = beat.get("speaker") or ""
    emotion = beat.get("emotion") or ""
    humanoid = _HUMANOID_CHAR_REFS.get(speaker, {})
    if humanoid:
        fname = humanoid.get(emotion) or humanoid.get("default")
        if fname:
            candidate = _project_root() / fname
            if candidate.is_file():
                return str(candidate)
    resolved = _resolve_creature_ref(speaker, emotion)
    if resolved and os.path.isfile(resolved):
        return os.path.normpath(resolved)
    return None


def resolve_segment_bg_path(event_id: str, phase: str) -> str | None:
    beat_bg = None  # caller may pass beat-level override separately
    fname = _SEGMENT_BG_DEFAULTS.get((str(event_id), str(phase)))
    if fname:
        candidate = _project_root() / fname
        if candidate.is_file():
            return str(candidate)
    return None


def resolve_beat_bg_ref_path(beat: dict, event_id: str, phase: str) -> str | None:
    ref = beat.get("bg_ref_image")
    if isinstance(ref, dict):
        p = ref.get("abs_path") or ""
        if p and os.path.isfile(p):
            return os.path.normpath(p)
    return resolve_segment_bg_path(event_id, phase)


def apply_kling_o3_defaults_to_beat(beat: dict, event_id: str, phase: str) -> None:
    beat.setdefault("pipeline", "kling_o3_omni")
    role = beat.get("intro_beat_role")
    if role in (INTRO_BEAT_ROLE_SEMI_CANONICAL, INTRO_BEAT_ROLE_CANONICAL_MIRROR):
        _apply_intro_canonical_beat_defaults(beat, event_id, phase, role)
        if role == INTRO_BEAT_ROLE_CANONICAL_MIRROR:
            hydrate_intro_canonical_mirror_beat(beat, event_id, phase)
        return
    align_beat_reference_to_element(beat)
    if not resolve_beat_o3_prompt(beat):
        beat["kling_o3_prompt"] = build_kling_o3_prompt(beat)
    if not beat.get("kling_o3_duration_locked"):
        beat["kling_o3_duration"] = resolve_kling_o3_submit_duration(
            beat, beat.get("kling_o3_prompt") or "",
        )
    beat.setdefault("kling_o3_status", "draft")
    char_path = resolve_beat_char_ref_path(beat)
    bg_path = resolve_beat_bg_ref_path(beat, event_id, phase)
    if char_path and not beat.get("reference_image"):
        beat["reference_image"] = _ref_dict_from_path(char_path)
    if bg_path and not beat.get("bg_ref_image") and not beat.get("bg_ref_image_locked"):
        beat["bg_ref_image"] = _ref_dict_from_path(bg_path)


def apply_kling_o3_defaults_to_segment(seg: dict, event_id: str, phase: str) -> None:
    for beat in seg.get("beats") or []:
        apply_kling_o3_defaults_to_beat(beat, event_id, phase)


def create_blank_bg_beat(beat_id: str, event_id: str, phase: str) -> dict:
    """Deprecated — blank rows bypass extract materialization. Use insert-beat form API."""
    raise RuntimeError(
        "create_blank_bg_beat is removed; POST /api/bg/insert-beat with plan_row instead"
    )


def materialize_sidecar_beat_from_plan_row(
    plan_row: dict,
    *,
    beat_id: str,
    arc_number: int,
    event_id: str,
    phase: str,
    sidecar: dict,
    prompt_by_index: dict[int, str] | None = None,
    beat_plan_source: str = "operator_insert_v1",
) -> dict:
    """Single-row extract-equivalent beat via ``build_beats_from_approved_plan``."""
    from beat_extract_policy import normalize_plan_row

    normalized, _warnings = normalize_plan_row(plan_row, beat_index=99)
    built = build_beats_from_approved_plan(
        [normalized],
        prompt_by_index or {},
        arc_number=arc_number,
        event_id=str(event_id),
        phase=phase,
    )
    if len(built) != 1:
        raise ValueError(f"expected 1 beat from plan row, got {len(built)}")
    beat = built[0]
    beat["beat_id"] = beat_id
    beat["beat_plan_source"] = beat_plan_source
    beat["status"] = "draft"
    beat.pop("o3_voice_stack_pin", None)
    beat.pop("o3_prompt_box_law", None)
    speaker = str(beat.get("speaker") or "").strip()
    if speaker:
        finalize_proven_element_beat(beat, sidecar, speaker, event_id=str(event_id), phase=phase)
    return beat


def user_locked_char_ref_blocks_proven_overwrite(beat: dict) -> bool:
    """True when operator locked @Image1 to a live file — skip proven ref copy on Generate."""
    if not beat.get("reference_image_locked"):
        return False
    path = resolve_beat_char_ref_path(beat) or ""
    return bool(path and os.path.isfile(path))


def _proven_reference_image_copy(src_ref: dict) -> dict:
    """Copy proven ref without stale thumb_b64 from the source beat."""
    out = copy.deepcopy(src_ref)
    out.pop("thumb_b64", None)
    return out


def finalize_proven_element_beat(
    beat: dict,
    sidecar: dict,
    speaker: str,
    *,
    event_id: str,
    phase: str,
) -> bool:
    """Copy proven char/bg refs from ``proven_from_beat_id``; rebuild prompt when refs change."""
    try:
        from tools import kling_character_registry as reg

        proven = reg.resolve_proven_o3_bind(reg.get_character_entry(speaker))
    except Exception:
        proven = None
    if not proven:
        return False
    source_id = str(proven.get("proven_from_beat_id") or "").strip()
    if not source_id:
        return False
    _, source = find_beat(sidecar, source_id)
    if not source:
        return False
    changed = False
    src_ref = source.get("reference_image")
    if isinstance(src_ref, dict):
        src_path = str(src_ref.get("abs_path") or "").strip()
        if (
            src_path
            and os.path.isfile(src_path)
            and not user_locked_char_ref_blocks_proven_overwrite(beat)
        ):
            cur = resolve_beat_char_ref_path(beat) or ""
            if os.path.normpath(cur) != os.path.normpath(src_path):
                beat["reference_image"] = _proven_reference_image_copy(src_ref)
                beat["reference_image_locked"] = True
                changed = True
    src_bg = source.get("bg_ref_image")
    if isinstance(src_bg, dict) and not beat.get("bg_ref_image_locked"):
        if not beat.get("bg_ref_image"):
            beat["bg_ref_image"] = copy.deepcopy(src_bg)
            changed = True
    beat.pop("o3_voice_stack_pin", None)
    if not o3_prompt_box_law_active(beat):
        beat.pop("o3_prompt_box_law", None)
        if changed:
            apply_kling_o3_defaults_to_beat(beat, event_id, phase)
    sync_element_char_ref_status(beat, heal_mismatch=False)
    return changed


def maybe_auto_register_beat_char_ref(beat: dict, wavespeed_key: str) -> dict[str, Any]:
    """Sync Element gate; auto-register char ref when gate fails (same as bg_update_beat drop)."""
    sync_element_char_ref_status(beat, heal_mismatch=False)
    if beat.get("element_char_ref_ok") is not False or not wavespeed_key:
        return {"ok": True, "skipped": True}
    reg_result = try_register_dropped_char_ref_on_element(beat, wavespeed_key)
    if reg_result.get("ok"):
        sync_element_char_ref_status(beat, heal_mismatch=False)
    return reg_result


def upgrade_legacy_bg_beats_to_kling_o3(sidecar: dict) -> int:
    """Upgrade rows created before pipeline=kling_o3_omni (e.g. + Insert beat)."""
    updated = 0
    for arc in (sidecar.get("arcs") or {}).values():
        for seg_key, seg in (arc.get("segments") or {}).items():
            m = re.match(r"^event_(\d+)_(\w+)$", seg_key)
            if not m:
                continue
            event_id, phase = m.group(1), m.group(2)
            for beat in seg.get("beats") or []:
                if beat.get("pipeline") == "kling_o3_omni":
                    continue
                if "pipeline" in beat:
                    continue
                apply_kling_o3_defaults_to_beat(beat, event_id, phase)
                updated += 1
    return updated


def beat_is_kling_approved_protected(beat: dict) -> bool:
    """True when an existing beat must survive re-extract unless force=True."""
    status = (beat.get("kling_o3_status") or "").strip().lower()
    if status == "approved":
        return True
    if status == "still_rendered":
        return False
    vpath = (beat.get("kling_o3_video_path") or "").strip()
    if vpath and os.path.isfile(vpath):
        return True
    return False


def beat_is_canonical_mirror_protected(beat: dict) -> bool:
    if beat.get("intro_beat_role") == INTRO_BEAT_ROLE_CANONICAL_MIRROR:
        return True
    if beat.get("intro_beat_role") == INTRO_BEAT_ROLE_SEMI_CANONICAL:
        return True
    if is_canonical_lead_beat(beat.get("beat_id") or ""):
        return True
    return False


def build_beats_from_approved_plan(
    beats_plan: list[dict],
    prompt_by_index: dict[int, str],
    *,
    arc_number: int,
    event_id: str,
    phase: str,
) -> list[dict]:
    """Map approved plan + Claude prompts to sidecar beat rows."""
    beat_label = f"arc{arc_number}_event{event_id}_{phase}"
    beats: list[dict] = []
    for i, row in enumerate(beats_plan, start=1):
        idx = int(row.get("beat_index") or i)
        beat_type = str(row.get("beat_type") or "dialogue").lower()
        dialogue = (row.get("dialogue_text") or "").strip()
        speaker_raw = (row.get("speaker") or "Character").strip()
        from beat_extract_policy import (
            _strip_bracket_emotion,
            extract_spoken_from_dialogue,
            infer_speaker_from_dialogue,
            repair_corrupted_plan_dialogue,
        )
        if speaker_raw.lower() in ("[stage direction]", "stage direction"):
            speaker = "[Stage Direction]"
        else:
            speaker = _canon_speaker(speaker_raw) or speaker_raw
            if speaker in ("Character", ""):
                inferred = infer_speaker_from_dialogue(dialogue)
                if inferred:
                    speaker = _canon_speaker(inferred) or inferred
        if beat_type not in ("stage_still", "stage_direction"):
            speaker, dialogue = repair_corrupted_plan_dialogue(dialogue, speaker)
        emotion = _strip_bracket_emotion((row.get("emotion") or "neutral").strip() or "neutral")
        scene_notes = (row.get("scene_notes") or "").strip()[:500]
        is_still = beat_type == "stage_still"
        prompt = (prompt_by_index.get(idx) or "").strip()
        if is_still and not prompt:
            from beat_extract_policy import build_still_insert_prompt
            prompt = build_still_insert_prompt(row)
        if prompt and not is_still and "Only @Image1 is visible" not in prompt:
            _spk, spoken_only = extract_spoken_from_dialogue(dialogue)
            spoken = spoken_only or dialogue
            prompt = _append_kling_o3_submit_locks(
                prompt, speaker=speaker, spoken=_kling_o3_normalize_spoken(spoken),
            )
        pipeline = "still_insert" if is_still else "kling_o3_omni"
        beat = {
            "beat_id": f"bg_{beat_label}_beat_{idx:02d}",
            "speaker": speaker,
            "dialogue_text": dialogue,
            "scene_notes": scene_notes,
            "emotion": emotion,
            "kling_o3_prompt": prompt,
            "status": "draft",
            "pipeline": pipeline,
            "beat_type": beat_type if is_still else "dialogue",
            "flux_options": [],
            "gpt_options": [],
            "schema_version": 1,
            "beat_plan_source": "claude_extract_v1",
        }
        if is_still:
            beat["beat_render_mode"] = "still_insert"
            if not beat.get("kling_o3_duration_locked"):
                beat["kling_o3_duration"] = 3
            beat.setdefault("kling_o3_status", "draft")
        elif not prompt:
            apply_kling_o3_defaults_to_beat(beat, event_id, phase)
        else:
            align_beat_reference_to_element(beat)
            bg_path = resolve_beat_bg_ref_path(beat, event_id, phase)
            if bg_path and not beat.get("bg_ref_image"):
                beat["bg_ref_image"] = _ref_dict_from_path(bg_path)
            if not beat.get("kling_o3_duration_locked"):
                beat["kling_o3_duration"] = resolve_kling_o3_submit_duration(
                    beat, prompt,
                )
            beat.setdefault("kling_o3_status", "draft")
        beats.append(beat)
    beats.sort(key=lambda b: segment_beat_order_key(b))
    from beat_extract_policy import apply_beat_continuity_chain

    apply_beat_continuity_chain(beats)
    return beats


def apply_approved_extract_plan(
    sidecar: dict,
    arc_number: int,
    event_id: str,
    phase: str,
    story_summary: str,
    beats_plan: list[dict],
    prompt_by_index: dict[int, str],
    *,
    force: bool = False,
) -> list[dict]:
    """Write approved Claude extract plan into segment beats with merge policy."""
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    existing = list(seg.get("beats") or [])
    from beat_extract_policy import normalize_plan_row

    repaired_plan: list[dict] = []
    for i, row in enumerate(beats_plan or [], start=1):
        if not isinstance(row, dict):
            continue
        beat_index = int(row.get("beat_index") or i)
        normalized, _warnings = normalize_plan_row(row, beat_index=beat_index)
        repaired_plan.append(normalized)
    beats_plan = repaired_plan
    incoming = build_beats_from_approved_plan(
        beats_plan, prompt_by_index,
        arc_number=arc_number, event_id=event_id, phase=phase,
    )
    incoming_ids = {b["beat_id"] for b in incoming if b.get("beat_id")}

    protected: list[dict] = []
    for b in existing:
        if beat_is_canonical_mirror_protected(b):
            protected.append(b)
            continue
        if not force and beat_is_kling_approved_protected(b):
            protected.append(b)

    if force:
        kept_orphans: list[dict] = [
            b for b in protected if b.get("beat_id") not in incoming_ids
        ]
    else:
        kept_orphans = [
            b for b in protected if b.get("beat_id") not in incoming_ids
        ]
        kept_orphans.extend([
            b for b in existing
            if b.get("beat_id") not in incoming_ids
            and b not in protected
            and not beat_is_canonical_mirror_protected(b)
            and beat_is_kling_approved_protected(b)
        ])

    merged = merge_incoming_segment_beats(
        existing, incoming, preserve_fields=_EXTRACT_APPROVE_MERGE_PRESERVE,
    )
    existing_map = {b["beat_id"]: b for b in existing if b.get("beat_id")}
    for b in merged:
        saved = existing_map.get(b.get("beat_id") or "")
        if not saved or not beat_is_kling_approved_protected(saved):
            continue
        for field in _KLING_APPROVED_RESTORE_FIELDS:
            val = saved.get(field)
            if val not in (None, "", [], {}):
                b[field] = val
    merged_ids = {b.get("beat_id") for b in merged}
    for b in kept_orphans:
        if b.get("beat_id") and b["beat_id"] not in merged_ids:
            merged.append(b)
            merged_ids.add(b["beat_id"])

    beat_label = f"arc{arc_number}_event{event_id}_{phase}"
    append_intro_canonical_tail_beats(merged, beat_label, phase)
    finalize_intro_canonical_tail_beats(merged, str(event_id), phase, sidecar=sidecar)
    merged = normalize_segment_beat_order(merged)
    heal_segment_dialogue_fields(merged)
    from beat_extract_policy import apply_beat_continuity_chain

    apply_beat_continuity_chain(merged)
    seg["beats"] = merged
    seg["beat_plan_draft"] = {
        "story_summary": story_summary,
        "beats_plan": beats_plan,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "source": "approved_snapshot",
    }
    seg["beat_plan_approved_at"] = datetime.now(timezone.utc).isoformat()
    if story_summary:
        seg["beat_plan_story_summary"] = story_summary
    return merged


def persist_beat_plan_draft(
    sidecar: dict,
    arc_number: int,
    event_id: str,
    phase: str,
    story_summary: str,
    beats_plan: list[dict],
    *,
    source: str = "modal_autosave",
    extra: dict | None = None,
) -> dict:
    """Write modal/extract beat plan rows to segment beat_plan_draft (durable sidecar)."""
    from beat_extract_policy import normalize_plan_row

    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    prev = seg.get("beat_plan_draft") if isinstance(seg.get("beat_plan_draft"), dict) else {}
    repaired: list[dict] = []
    for i, row in enumerate(beats_plan or [], start=1):
        if not isinstance(row, dict):
            continue
        beat_index = int(row.get("beat_index") or i)
        normalized, _warnings = normalize_plan_row(row, beat_index=beat_index)
        repaired.append(normalized)
    now = datetime.now(timezone.utc).isoformat()
    draft: dict = {
        "story_summary": (story_summary or "").strip(),
        "beats_plan": repaired,
        "updated_at": now,
        "source": source,
    }
    for key in ("created_at", "model_used", "generation_time_ms", "section_meta"):
        if isinstance(prev, dict) and prev.get(key) is not None:
            draft[key] = prev[key]
    if extra:
        draft.update(extra)
    if source == "extract_plan" or not draft.get("created_at"):
        draft.setdefault("created_at", now)
    seg["beat_plan_draft"] = draft
    return draft


def resync_kling_author_prompts_pre_audit(beats: list[dict]) -> int:
    """Re-run deterministic author postprocess so audit matches injected staging."""
    from beat_extract_policy import postprocess_kling_author_row

    touched = 0
    for beat in beats or []:
        if not isinstance(beat, dict):
            continue
        if beat_is_still_insert(beat) or beat_is_canonical_mirror_protected(beat):
            continue
        prompt = (beat.get("kling_o3_prompt") or "").strip()
        if not prompt:
            continue
        m = re.search(r"beat_(\d+)$", str(beat.get("beat_id") or ""))
        beat_index = int(m.group(1)) if m else 0
        row = {
            "beat_index": beat_index,
            "beat_type": beat.get("beat_type") or "dialogue",
            "speaker": beat.get("speaker") or "Character",
            "dialogue_text": beat.get("dialogue_text") or "",
            "emotion": beat.get("emotion") or "neutral",
            "scene_notes": beat.get("scene_notes") or "",
        }
        merged = postprocess_kling_author_row(row, prompt)
        new_prompt = (merged.get("kling_o3_prompt") or "").strip()
        if new_prompt:
            if new_prompt != prompt:
                touched += 1
            beat["kling_o3_prompt"] = new_prompt
        if merged.get("scene_notes"):
            beat["scene_notes"] = merged["scene_notes"]
    return touched


def _emotion_reflected_in_kling_prompt(emotion: str, prompt: str) -> bool:
    """Compound plan emotions (cheerful, oblivious) may appear as [cheerful] in voice line."""
    _ACTION_EMOTION_TOKENS = frozenset({
        "wink", "winks", "nod", "nods", "shrug", "shrugs", "smile", "smiles",
        "laugh", "laughs", "grin", "grins",
    })
    emo = (emotion or "").strip().strip("[]")
    if not emo or emo.lower() == "neutral":
        return True
    lower = (prompt or "").lower()
    if emo.lower() in lower:
        return True
    # Split compound emotions on comma, slash, and em/en dash (e.g. "warm close — victory").
    parts = [p.strip().lower() for p in re.split(r"[,/]|\s*[—–]\s*", emo) if p.strip()]
    if parts and all(p in _ACTION_EMOTION_TOKENS for p in parts):
        return True
    for part in parts:
        token = part.strip().lower()
        if not token:
            continue
        if token in lower or f"[{token}]" in lower:
            return True
    return False


def _beat_ids_for_extract_plan(
    beats_plan: list[dict],
    *,
    arc_number: int,
    event_id: str,
    phase: str,
) -> set[str]:
    """Beat ids that this approve transaction authored — audit scope only."""
    beat_label = f"arc{arc_number}_event{event_id}_{phase}"
    out: set[str] = set()
    for i, row in enumerate(beats_plan or [], start=1):
        if not isinstance(row, dict):
            continue
        idx = int(row.get("beat_index") or i)
        out.add(f"bg_{beat_label}_beat_{idx:02d}")
    return out


def audit_kling_author_enrichment(
    beats: list[dict],
    *,
    scope_beat_ids: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Post-approve guard — dialogue beats must carry author emotion/staging in prompts.

    EXTRACT_APPROVE_AUDIT_SCOPE_V1: when scope_beat_ids is set, orphan beats kept
    from a shorter plan (e.g. 6-beat plan on 8-beat segment) are not audited —
    only beats this approve transaction touched are validated.
    """
    warnings: list[str] = []
    scope = frozenset(scope_beat_ids) if scope_beat_ids else None
    for b in beats or []:
        if not isinstance(b, dict):
            continue
        beat_id = b.get("beat_id") or "?"
        if scope is not None and beat_id not in scope:
            continue
        if beat_is_still_insert(b) or beat_is_canonical_mirror_protected(b):
            continue
        beat_type = str(b.get("beat_type") or "dialogue").lower()
        prompt = (b.get("kling_o3_prompt") or "").strip()
        if not prompt:
            warnings.append(f"{beat_id}: missing kling_o3_prompt after approve")
            continue
        if re.search(r"\bLuna\b", prompt) and "Lorelai" not in (b.get("speaker") or ""):
            warnings.append(f"{beat_id}: stale Luna cast leaked into prompt")
        if re.search(r"\bis a small green sea turtle\b", prompt, re.I):
            warnings.append(f"{beat_id}: species taxonomy in prompt — use @Image1 only")
        if re.search(r"\b(?:Tessa|Lorelai|Loral|Laurel|Arlo|Chipper)\s+is\s+a\s+", prompt, re.I):
            warnings.append(f"{beat_id}: species anatomy block in prompt — Event-1 shape violation")
        if "@Image1" in prompt and not identity_footer_is_canonical(prompt):
            warnings.append(f"{beat_id}: identity footer drift from KLING_O3_IDENTITY_LOCK")
        if re.search(r"\bChipper\b", prompt) and "Arlo" not in (b.get("speaker") or ""):
            warnings.append(f"{beat_id}: stale Chipper cast leaked into prompt")
        # Stage-direction beats: emotion is planner metadata, not a spoken delivery tag.
        if beat_type != "stage_direction":
            emotion = (b.get("emotion") or "").strip()
            if emotion and not _emotion_reflected_in_kling_prompt(emotion, prompt):
                warnings.append(f"{beat_id}: emotion not woven into kling_o3_prompt")
            scene = (b.get("scene_notes") or "").strip()
            if len(scene) > 12:
                from beat_extract_policy import scene_notes_reflected_in_kling_prompt

                if not scene_notes_reflected_in_kling_prompt(
                    prompt, scene, speaker=str(b.get("speaker") or ""),
                ):
                    warnings.append(f"{beat_id}: scene_notes missing from kling_o3_prompt")
    return warnings


def heal_segment_dialogue_fields(beats: list[dict]) -> int:
    """Repair corrupted dialogue_text / speaker / emotion on populated beats."""
    from beat_extract_policy import (
        _strip_bracket_emotion,
        humanize_kling_body_parts_on_beat,
        repair_corrupted_plan_dialogue,
    )

    fixed = 0
    for beat in beats or []:
        if not isinstance(beat, dict) or beat_is_still_insert(beat):
            continue
        speaker = str(beat.get("speaker") or "")
        dialogue = str(beat.get("dialogue_text") or "")
        new_speaker, new_dialogue = repair_corrupted_plan_dialogue(dialogue, speaker)
        new_emotion = _strip_bracket_emotion(str(beat.get("emotion") or "neutral"))
        changed = False
        if new_speaker and new_speaker != speaker:
            beat["speaker"] = new_speaker
            changed = True
        if new_dialogue != dialogue:
            beat["dialogue_text"] = new_dialogue
            changed = True
        if new_emotion != beat.get("emotion"):
            beat["emotion"] = new_emotion
            changed = True
        if humanize_kling_body_parts_on_beat(beat):
            changed = True
        if changed:
            fixed += 1
    return fixed


def segment_beats_to_plan_rows(beats: list[dict]) -> list[dict]:
    """Rebuild Beat Plan modal rows from populated segment beats (Review saved plan fallback)."""
    rows: list[dict] = []
    for i, beat in enumerate(beats or [], start=1):
        if not isinstance(beat, dict):
            continue
        speaker = str(beat.get("speaker") or "").strip()
        is_still = beat_is_still_insert(beat)
        is_stage = (
            is_still
            or speaker.lower() in ("[stage direction]", "stage direction", "narrator")
        )
        dialogue = str(beat.get("dialogue_text") or "")
        from beat_extract_policy import _strip_bracket_emotion, repair_corrupted_plan_dialogue
        emotion = _strip_bracket_emotion(str(beat.get("emotion") or "neutral"))
        if not is_still and not is_stage:
            speaker, dialogue = repair_corrupted_plan_dialogue(dialogue, speaker)
        rows.append({
            "beat_index": i,
            "beat_type": "stage_still" if is_still else ("stage_direction" if is_stage else "dialogue"),
            "speaker": speaker or ("[Stage Direction]" if is_stage else "Character"),
            "dialogue_text": dialogue,
            "emotion": emotion,
            "scene_notes": beat.get("scene_notes") or "",
        })
    return rows


def generate_kling_prompts_for_segment(sidecar: dict, arc_number: int, event_id: str, phase: str) -> int:
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    beats = seg.get("beats") or []
    for beat in beats:
        apply_kling_o3_defaults_to_beat(beat, event_id, phase)
    return len(beats)


def import_locked_lines_beats(
    locked_lines_path: str | Path,
    arc_number: int,
    event_id: str,
    phase: str,
) -> list[dict]:
    """Map M1E1-style locked lines JSON into sidecar beat rows."""
    rows = json.loads(Path(locked_lines_path).read_text(encoding="utf-8"))
    beats: list[dict] = []
    n = 0
    for row in rows:
        speaker_raw = (row.get("speaker") or "").strip()
        if speaker_raw.lower() in ("[stage direction]", "stage direction", "narrator"):
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        n += 1
        canon = _canon_speaker(speaker_raw) or speaker_raw
        beat = {
            "beat_id": f"bg_arc{arc_number}_event{event_id}_{phase}_beat_{n:02d}",
            "speaker": canon,
            "dialogue_text": text,
            "scene_notes": (row.get("section") or "")[:200],
            "emotion": _infer_emotion(text, row.get("section") or ""),
            "status": "draft",
            "pipeline": "kling_o3_omni",
            "flux_options": [],
            "gpt_options": [],
        }
        apply_kling_o3_defaults_to_beat(beat, event_id, phase)
        beats.append(beat)
    return beats


def kling_o3_clips_dir(event_dir: str | Path) -> Path:
    p = Path(event_dir) / "kling_o3_clips"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_beat_disk_event_dir(beat_id: str, scoped_event_dir: str | Path) -> Path:
    """Production beats → ``Event_N`` from id; milestone narrative ids use scoped folder."""
    from beatgen_scope import event_id_from_beat_id  # noqa: PLC0415

    if event_id_from_beat_id(beat_id):
        return event_dir_for_beat_id(beat_id)
    return Path(scoped_event_dir).expanduser().resolve()


def event_dir_for_beat_id(beat_id: str) -> Path:
    """``Production/Event_N`` from ``bg_arc1_event2_pre_beat_27``-style beat ids."""
    from beatgen_scope import BeatGenScopeError, event_id_from_beat_id  # noqa: PLC0415

    event_id = event_id_from_beat_id(beat_id)
    if event_id:
        return Path(_PROD_DIR) / event_id
    bound = getattr(__import__(__name__), "_BG_EVENT_DIR", None)
    if bound:
        return Path(bound).expanduser().resolve()
    raise BeatGenScopeError(
        f"cannot resolve event dir for beat_id={beat_id!r} — no Event_N token",
        beat_id=str(beat_id),
    )


def highest_o3_generation_on_disk(beat_id: str, event_dir: str | Path) -> int:
    """Max ``g{N}`` from O3 clip filenames on disk for ``beat_id`` (allocate-only slot math)."""
    bid = str(beat_id or "").strip()
    if not bid:
        return 0
    clips = kling_o3_clips_dir(event_dir)
    if not clips.is_dir():
        return 0
    best = 0
    for path in clips.iterdir():
        if not path.is_file():
            continue
        if bid not in path.name:
            continue
        gen = _kling_o3_gen_from_video_path(str(path))
        if gen is not None and gen > best:
            best = gen
    return best


def kling_o3_preserved_latest_dir(event_dir: str | Path) -> Path:
    """One rolling slot per beat_id — overwritten whenever that beat's clip is preserved."""
    return kling_o3_clips_dir(event_dir) / "_preserved" / "latest"


def kling_o3_preserved_segment_key(arc_number: int, event_id: str, phase: str) -> str:
    return f"arc{int(arc_number)}_event{event_id}_{phase}"


def kling_o3_preserved_segment_dir(
    event_dir: str | Path,
    arc_number: int,
    event_id: str,
    phase: str,
) -> Path:
    """One rolling snapshot per BG segment — overwritten on segment switch away."""
    key = kling_o3_preserved_segment_key(arc_number, event_id, phase)
    return kling_o3_clips_dir(event_dir) / "_preserved" / "segments" / key


def _strip_beat_for_preserve_json(beat: dict) -> dict:
    """Copy beat metadata for preserve sidecars; drop bulky inline thumbs."""
    out = dict(beat)
    for ref_key in ("reference_image", "bg_ref_image"):
        ref = out.get(ref_key)
        if isinstance(ref, dict) and ref.get("thumb_b64"):
            ref = dict(ref)
            ref.pop("thumb_b64", None)
            out[ref_key] = ref
    return out


def _copy_kling_o3_beat_clip_to_dir(beat: dict, dest_dir: Path) -> bool:
    beat_id = beat.get("beat_id")
    video = beat.get("kling_o3_video_path")
    if not beat_id or not video:
        return False
    src = Path(video)
    if not src.is_file():
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / f"{beat_id}.mp4")
    meta = _strip_beat_for_preserve_json(beat)
    meta["preserved_clip"] = str((dest_dir / f"{beat_id}.mp4").resolve())
    (dest_dir / f"{beat_id}.json").write_text(json.dumps(meta, indent=2))
    return True


def preserve_kling_o3_beat_slot(
    beat: dict,
    event_dir: str | Path,
    *,
    reason: str,
) -> bool:
    """Rolling preserve: one mp4+json per beat under ``kling_o3_clips/_preserved/latest/``."""
    beat_id = beat.get("beat_id")
    if not beat_id:
        return False
    dest_dir = kling_o3_preserved_latest_dir(event_dir)
    if not _copy_kling_o3_beat_clip_to_dir(beat, dest_dir):
        return False
    slot_json = dest_dir / f"{beat_id}.json"
    try:
        meta = json.loads(slot_json.read_text())
    except (OSError, json.JSONDecodeError):
        meta = _strip_beat_for_preserve_json(beat)
    meta["preserve_reason"] = reason
    meta["preserved_at"] = datetime.now(timezone.utc).isoformat()
    slot_json.write_text(json.dumps(meta, indent=2))
    return True


def _segment_beat_belongs_in_preserve_snapshot(beat: dict) -> bool:
    """Kling O3 + Still+TTS beats must survive Send-to-Stitcher preserve snapshots."""
    if beat.get("pipeline") == "kling_o3_omni":
        return True
    return beat_is_still_insert(beat)


def _load_preserved_segment_beats_ordered(
    event_dir: str | Path,
    arc_number: int,
    event_id: str,
    phase: str,
) -> list[dict]:
    """Manifest order with per-beat JSON overlays from ``beats/*.json`` when present."""
    manifest_path = kling_o3_preserved_segment_dir(
        event_dir, arc_number, event_id, phase,
    ) / "manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    manifest_beats = manifest.get("beats") or []
    by_id: dict[str, dict] = {}
    for row in manifest_beats:
        if isinstance(row, dict) and row.get("beat_id"):
            by_id[str(row["beat_id"])] = dict(row)
    beats_dir = manifest_path.parent / "beats"
    if beats_dir.is_dir():
        for jf in beats_dir.glob("*.json"):
            try:
                row = json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            bid = str(row.get("beat_id") or jf.stem)
            by_id[bid] = row
    order = [
        str(b.get("beat_id"))
        for b in manifest_beats
        if isinstance(b, dict) and b.get("beat_id")
    ]
    for bid in by_id:
        if bid not in order:
            order.append(bid)
    return [by_id[bid] for bid in order if bid in by_id]


def _insert_index_from_preserved_order(
    live_beats: list[dict],
    preserved_beats: list[dict],
    beat_id: str,
) -> int:
    order = [str(b.get("beat_id")) for b in preserved_beats if b.get("beat_id")]
    if beat_id not in order:
        return len(live_beats)
    pos = order.index(beat_id)
    live_ids = {str(b.get("beat_id")) for b in live_beats if b.get("beat_id")}
    for j in range(pos - 1, -1, -1):
        prev_id = order[j]
        if prev_id not in live_ids:
            continue
        for i, lb in enumerate(live_beats):
            if str(lb.get("beat_id")) == prev_id:
                return i + 1
    for j in range(pos + 1, len(order)):
        next_id = order[j]
        if next_id not in live_ids:
            continue
        for i, lb in enumerate(live_beats):
            if str(lb.get("beat_id")) == next_id:
                return i
    return len(live_beats)


def merge_missing_still_insert_beats_from_preserve(
    sidecar: dict,
    event_dir: str | Path,
    arc_number: int,
    event_id: str,
    phase: str,
) -> list[str]:
    """Insert Still+TTS beats present in preserve snapshot but missing from live segment."""
    preserved = _load_preserved_segment_beats_ordered(event_dir, arc_number, event_id, phase)
    if not preserved:
        return []
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    beats = list(seg.get("beats") or [])
    live_ids = {str(b.get("beat_id")) for b in beats if b.get("beat_id")}
    added: list[str] = []
    for row in preserved:
        if not beat_is_still_insert(row):
            continue
        bid = str(row.get("beat_id") or "")
        if not bid or bid in live_ids:
            continue
        idx = _insert_index_from_preserved_order(beats, preserved, bid)
        beats.insert(idx, dict(row))
        live_ids.add(bid)
        added.append(bid)
    if added:
        seg["beats"] = beats
    return added


def heal_segment_still_insert_beats_from_backup_rows(
    sidecar: dict,
    arc_number: int,
    event_id: str,
    phase: str,
    backup_beats: list[dict],
    *,
    still_insert_ids: list[str],
    remove_beat_ids: list[str] | None = None,
) -> list[str]:
    """Restore missing Still+TTS beats from a trusted backup segment list."""
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    beats = list(seg.get("beats") or [])
    remove = {str(bid) for bid in (remove_beat_ids or [])}
    beats = [b for b in beats if str(b.get("beat_id") or "") not in remove]
    backup_by_id = {
        str(b.get("beat_id")): b
        for b in backup_beats
        if isinstance(b, dict) and b.get("beat_id")
    }
    live_ids = {str(b.get("beat_id")) for b in beats if b.get("beat_id")}
    restored: list[str] = []
    for bid in still_insert_ids:
        bid = str(bid)
        if bid in live_ids or bid not in backup_by_id:
            continue
        row = dict(backup_by_id[bid])
        idx = _insert_index_from_preserved_order(beats, backup_beats, bid)
        beats.insert(idx, row)
        live_ids.add(bid)
        restored.append(bid)
    if restored or remove:
        seg["beats"] = beats
    return restored


def preserve_kling_o3_segment_beats(
    sidecar: dict,
    arc_number: int,
    event_id: str,
    phase: str,
    event_dir: str | Path,
    *,
    reason: str,
) -> int:
    """Snapshot exportable segment beats (Kling O3 + Still+TTS) — clips + manifest."""
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    seg_dir = kling_o3_preserved_segment_dir(event_dir, arc_number, event_id, phase)
    if seg_dir.is_dir():
        shutil.rmtree(seg_dir)
    beats_dir = seg_dir / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    preserved = 0
    beats_meta: list[dict] = []
    for beat in seg.get("beats") or []:
        if not _segment_beat_belongs_in_preserve_snapshot(beat):
            continue
        beats_meta.append(_strip_beat_for_preserve_json(beat))
        if _copy_kling_o3_beat_clip_to_dir(beat, beats_dir):
            preserved += 1
    manifest = {
        "arc_number": int(arc_number),
        "event_id": str(event_id),
        "phase": str(phase),
        "segment_key": kling_o3_preserved_segment_key(arc_number, event_id, phase),
        "preserve_reason": reason,
        "preserved_at": datetime.now(timezone.utc).isoformat(),
        "clip_count": preserved,
        "beat_count": len(beats_meta),
        "beats": beats_meta,
    }
    seg_dir.mkdir(parents=True, exist_ok=True)
    (seg_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return preserved


def restore_preserved_segment_beats_if_empty(
    sidecar: dict,
    event_dir: str | Path,
    arc_number: int,
    event_id: str,
    phase: str,
) -> int:
    """Hydrate a live segment from ``_preserved/segments/*/manifest.json`` when beats are missing."""
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    if seg.get("beats"):
        return 0
    manifest_path = kling_o3_preserved_segment_dir(
        event_dir, arc_number, event_id, phase,
    ) / "manifest.json"
    beats = _load_preserved_segment_beats_ordered(event_dir, arc_number, event_id, phase)
    if not beats:
        return 0
    seg["beats"] = beats
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        for key in ("name", "beat_plan_approved_at", "slice_method", "beat_plan_story_summary"):
            if manifest.get(key):
                seg[key] = manifest[key]
    return len(beats)


_O3_ARTIFACT_BEAT_ID_RE = re.compile(
    r"^(bg_arc\d+_event\d+_(?:pre|post|full|main)_beat_\d+)",
    re.I,
)
_O3_INTENT_SPEAKER_RE = re.compile(r"@Image1\s*\(([^)]+)\)", re.I)


def _speaker_from_o3_prompt_text(prompt: str) -> str:
    m = _O3_INTENT_SPEAKER_RE.search(prompt or "")
    if not m:
        return ""
    return m.group(1).strip().split(",")[0].strip()


def _segment_beat_id_prefix(arc_number: int, event_id: str, phase: str) -> str:
    evt = normalize_bg_event_id(str(event_id))
    return f"bg_arc{int(arc_number)}_event{evt}_{phase}_beat_"


def _collect_o3_artifact_beats_for_segment(
    event_dir: Path,
    arc_number: int,
    event_id: str,
    phase: str,
) -> dict[str, dict]:
    """Index latest intent/terminal rows per beat_id under ``arlo_o3_jobs/``."""
    prefix = _segment_beat_id_prefix(arc_number, event_id, phase)
    jobs_dir = event_dir / "arlo_o3_jobs"
    if not jobs_dir.is_dir():
        return {}
    by_beat: dict[str, dict] = {}
    for intent_path in jobs_dir.glob("*_intent.json"):
        try:
            intent = json.loads(intent_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        beat_id = str(intent.get("beat_id") or "").strip()
        if not beat_id.startswith(prefix):
            continue
        job_id = intent_path.name.split("_", 1)[0]
        terminal_path = jobs_dir / f"{job_id}_terminal.json"
        terminal: dict = {}
        if terminal_path.is_file():
            try:
                terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                terminal = {}
        prompt_block = intent.get("prompt") or {}
        if isinstance(prompt_block, dict):
            prompt_text = str(
                prompt_block.get("verbatim")
                or prompt_block.get("prepared_for_api")
                or "",
            ).strip()
            spoken = str(prompt_block.get("spoken_sent") or "").strip()
        else:
            prompt_text = str(prompt_block or "").strip()
            spoken = ""
        if prompt_text in ("@Image1 test", "@image1 test"):
            continue
        delivered = terminal.get("delivered") if isinstance(terminal, dict) else None
        video_path = ""
        if isinstance(delivered, dict):
            video_path = str(delivered.get("video_path") or "").strip()
        terminal_at = str(terminal.get("terminal_at") or "") if isinstance(terminal, dict) else ""
        terminal_status = str(terminal.get("status") or "") if isinstance(terminal, dict) else ""
        submitted = terminal.get("submitted") if isinstance(terminal, dict) else None
        char_ref = ""
        if isinstance(submitted, dict):
            char_ref = str(submitted.get("char_ref") or "").strip()
        row = {
            "beat_id": beat_id,
            "prompt_text": prompt_text,
            "spoken": spoken,
            "video_path": video_path,
            "terminal_status": terminal_status,
            "char_ref": char_ref,
            "_terminal_at": terminal_at,
        }
        prev = by_beat.get(beat_id)
        if prev and _o3_artifact_row_rank(prev) > _o3_artifact_row_rank(row):
            continue
        if prev and _o3_artifact_row_rank(prev) == _o3_artifact_row_rank(row):
            if (prev.get("_terminal_at") or "") > terminal_at:
                continue
        by_beat[beat_id] = row
    return by_beat


def _o3_artifact_row_rank(row: dict) -> tuple[int, int, str]:
    """Prefer done deliveries with video, then any video, then prompt-only rows."""
    status = str(row.get("terminal_status") or "")
    has_video = 1 if row.get("video_path") else 0
    done = 1 if status == "done" and has_video else 0
    failed = -1 if status == "failed" else 0
    return (done, has_video + failed, str(row.get("_terminal_at") or ""))


def _still_insert_beats_from_clips(
    event_dir: Path,
    arc_number: int,
    event_id: str,
    phase: str,
    existing_ids: set[str],
) -> list[dict]:
    """Recover still+TTS beats visible only as ``*_still_insert_*`` clips."""
    prefix = _segment_beat_id_prefix(arc_number, event_id, phase)
    clips_dir = kling_o3_clips_dir(event_dir)
    if not clips_dir.is_dir():
        return []
    still_ids: dict[str, Path] = {}
    for clip in clips_dir.glob(f"{prefix}*_still_insert_*"):
        m = _O3_ARTIFACT_BEAT_ID_RE.match(clip.name)
        if not m:
            continue
        beat_id = m.group(1)
        if beat_id in existing_ids:
            continue
        if clip.name.endswith("_tts.mp4"):
            still_ids[beat_id] = clip.resolve()
        elif beat_id not in still_ids:
            still_ids[beat_id] = clip.resolve()
    beats: list[dict] = []
    for beat_id in sorted(still_ids, key=lambda b: int(re.search(r"beat_(\d+)", b).group(1))):
        video = still_ids[beat_id]
        beat_num = int(re.search(r"beat_(\d+)", beat_id).group(1))
        audio_guess = clips_dir / f"line_{beat_num:02d}_lorelai.mp3"
        row: dict = {
            "beat_id": beat_id,
            "pipeline": "still_insert",
            "beat_render_mode": "still_insert",
            "kling_o3_status": "still_rendered",
            "kling_o3_video_path": str(video),
            "status": "video_ready",
            "speaker": "Lorelai",
        }
        if audio_guess.is_file():
            row["audio_file"] = audio_guess.name
        beats.append(row)
    return beats


def rehydrate_segment_beats_from_o3_artifacts(
    sidecar: dict,
    event_dir: str | Path,
    arc_number: int,
    event_id: str,
    phase: str,
) -> int:
    """Rebuild empty segment beats from ``arlo_o3_jobs`` intents + on-disk clips."""
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    if seg.get("beats"):
        return 0
    event_dir = Path(event_dir)
    artifacts = _collect_o3_artifact_beats_for_segment(event_dir, arc_number, event_id, phase)
    beats: list[dict] = []
    for beat_id in sorted(
        artifacts.keys(),
        key=lambda b: int(re.search(r"beat_(\d+)", b).group(1)),
    ):
        row = artifacts[beat_id]
        prompt_text = row.get("prompt_text") or ""
        speaker = _speaker_from_o3_prompt_text(prompt_text)
        beat: dict = {
            "beat_id": beat_id,
            "speaker": speaker,
            "dialogue_text": row.get("spoken") or "",
            "kling_o3_prompt": prompt_text,
            "o3_prompt_box_law": True,
            "status": "video_ready" if row.get("video_path") else "draft",
        }
        char_ref = row.get("char_ref") or ""
        if char_ref and os.path.isfile(char_ref):
            beat["reference_image"] = {"abs_path": char_ref, "source": "o3_artifact_rehydrate"}
        if row.get("video_path"):
            from kling_stitch_readiness import finalize_kling_delivery_clip  # noqa: PLC0415

            finalize_kling_delivery_clip(beat, row["video_path"])
        beats.append(beat)
    existing_ids = {b["beat_id"] for b in beats}
    beats.extend(_still_insert_beats_from_clips(event_dir, arc_number, event_id, phase, existing_ids))
    if not beats:
        return 0
    for beat in beats:
        reconcile_o3_disk_deliveries_for_beat(beat, event_dir)
    beats.sort(key=lambda b: int(re.search(r"beat_(\d+)", b.get("beat_id") or "0").group(1)))
    seg["beats"] = beats
    return len(beats)


def bootstrap_sqlite_from_legacy_global_db(event_dir: str | Path) -> int:
    """Import this event's beats from legacy shared ``beatgen.db`` when sharding DBs."""
    import sqlite3

    from lib.beatgen_store import default_db_path

    legacy = Path.home() / ".mindfulnest" / "state" / "beatgen.db"
    if not legacy.is_file() or legacy.resolve() == default_db_path().resolve():
        return 0
    store = _beatgen_store()
    if store.beat_count() > 0:
        return 0
    event_name = Path(event_dir).name
    evt_num = normalize_bg_event_id(event_name)
    try:
        conn = sqlite3.connect(str(legacy))
        rows = conn.execute(
            """
            SELECT beat_json FROM beats
            WHERE event_id=? OR beat_id LIKE ?
            ORDER BY beat_index
            """,
            (event_name, f"%event{evt_num}_%"),
        ).fetchall()
    except Exception as exc:
        print(f"[beatgen_store] legacy global import skipped: {exc}", flush=True)
        return 0
    if not rows:
        return 0
    arcs: dict = {"arc_1": {"segments": {}}}
    for row in rows:
        beat = json.loads(row[0])
        beat_id = beat.get("beat_id") or ""
        m = re.search(r"bg_arc(\d+)_event(\d+)_(pre|post|full|main)_", beat_id, re.I)
        if not m:
            continue
        seg_key = f"event_{m.group(2)}_{m.group(3)}"
        seg = arcs["arc_1"]["segments"].setdefault(seg_key, {"beats": []})
        seg.setdefault("beats", []).append(beat)
    if not arcs["arc_1"]["segments"]:
        return 0
    sidecar = {"schema_version": 3, "arcs": arcs, "active_context": {
        "arc_number": 1, "event_id": evt_num, "phase": "pre",
    }}
    count = store.import_from_dict(sidecar, replace=True)
    print(
        f"[beatgen_store] imported {count} beats from legacy global DB for {event_name}",
        flush=True,
    )
    return count


def _arc_number_from_key(arc_key: str) -> int:
    m = re.match(r"^arc_(\d+)$", str(arc_key or ""), re.I)
    return int(m.group(1)) if m else 1


def merge_missing_segment_beats_from_json_mirror(
    sidecar: dict,
    mirror_path: str | Path,
    event_id: str,
) -> dict[str, int]:
    """Union beats from durable JSON mirror when SQLite segment is missing rows.

    SQLite remains authoritative for beat_ids already present; mirror fills gaps
    only (draft extract rows with no O3 clip yet). Never removes live beats.
    """
    path = Path(mirror_path)
    if not path.is_file():
        return {}
    try:
        mirror = _read_json_file_durable(str(path))
    except OSError:
        return {}
    evt = normalize_bg_event_id(event_id)
    merged: dict[str, int] = {}
    for arc_key, arc in (mirror.get("arcs") or {}).items():
        if not isinstance(arc, dict):
            continue
        arc_number = _arc_number_from_key(str(arc_key))
        for seg_key, mirror_seg in (arc.get("segments") or {}).items():
            if not isinstance(mirror_seg, dict):
                continue
            m = re.match(r"^event_(.+)_(pre|post|full|main)$", str(seg_key))
            if not m or m.group(1) != evt:
                continue
            phase = m.group(2)
            added = _merge_missing_beats_into_segment(
                sidecar, mirror_seg, arc_number, evt, phase,
            )
            if added:
                merged[str(seg_key)] = added
    return merged


def _merge_missing_beats_into_segment(
    sidecar: dict,
    mirror_seg: dict,
    arc_number: int,
    event_id: str,
    phase: str,
) -> int:
    mirror_beats = [
        dict(b) for b in (mirror_seg.get("beats") or []) if isinstance(b, dict) and b.get("beat_id")
    ]
    if not mirror_beats:
        return 0
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    live_beats = list(seg.get("beats") or [])
    live_ids = {str(b.get("beat_id")) for b in live_beats if b.get("beat_id")}
    added = 0
    for row in mirror_beats:
        bid = str(row.get("beat_id") or "")
        if not bid or bid in live_ids:
            continue
        idx = _insert_index_from_preserved_order(live_beats, mirror_beats, bid)
        live_beats.insert(idx, row)
        live_ids.add(bid)
        added += 1
    if added:
        seg["beats"] = live_beats
    for key, val in mirror_seg.items():
        if key == "beats":
            continue
        if key not in seg or seg.get(key) in (None, "", {}, []):
            seg[key] = val
    return added


def reconcile_sqlite_segment_beats_from_json_mirror(event_dir: str | Path) -> dict[str, int]:
    """Cold boot / init: SQLite beat list must not fall below JSON mirror union."""
    if _MILESTONE_SIDECAR_JSON_ONLY or not _sidecar_use_sqlite():
        return {}
    event_dir = Path(event_dir)
    evt = normalize_bg_event_id(event_dir.name)
    mirror_path = os.path.abspath(BG_SIDECAR_PATH)
    report: dict[str, int] = {}

    def _mutate(sidecar: dict) -> None:
        nonlocal report
        report = merge_missing_segment_beats_from_json_mirror(sidecar, mirror_path, evt)
        if not report:
            from lib.production_snapshot import LATEST_DIR_NAME, snapshot_root

            snap_path = (
                snapshot_root(_PROD_DIR) / LATEST_DIR_NAME / "global" / "beat_generator_state.json"
            )
            if snap_path.is_file():
                snap_report = merge_missing_segment_beats_from_json_mirror(
                    sidecar, snap_path, evt,
                )
                if snap_report:
                    report = snap_report
                    print(
                        f"[beatgen_store] snapshot union: +{sum(snap_report.values())} beats "
                        f"segments={snap_report} snapshot={snap_path}",
                        flush=True,
                    )

    mutate_sidecar_locked(_mutate)
    if report:
        total = sum(report.values())
        print(
            f"[beatgen_store] JSON mirror union: +{total} beats segments={report} "
            f"mirror={mirror_path}",
            flush=True,
        )
    return report


def _segment_key_is_milestone_pollution(event_part: str, current_event: str) -> bool:
    """True for milestone scope leaks (``event_3b_full``), not other production events.

    Dedicated Event_N servers share one global SQLite store. Purging numeric
    ``event_3_pre`` when loading Event_2 deleted Kim's Event_3 beats on refresh.
    Only non-numeric event parts (milestone ids like ``3b``) are pollution.
    """
    if event_part == current_event:
        return False
    return not re.fullmatch(r"\d+", str(event_part or ""))


def purge_sidecar_segments_not_for_event(sidecar: dict, storyboard_event_id: str) -> list[str]:
    """Drop milestone-polluted BG segments (e.g. event_3b_full), not other Event_N rows."""
    bg_evt = normalize_bg_event_id(storyboard_event_id)
    removed: list[str] = []
    for arc_key, arc in list((sidecar.get("arcs") or {}).items()):
        if not isinstance(arc, dict):
            continue
        segs = arc.get("segments") or {}
        for seg_key in list(segs.keys()):
            m = re.match(r"^event_(.+)_(pre|post|full|main)$", str(seg_key))
            if not m:
                continue
            if not _segment_key_is_milestone_pollution(m.group(1), bg_evt):
                continue
            del segs[seg_key]
            removed.append(f"{arc_key}/{seg_key}")
    return removed


def _run_event_sidecar_reconcile_on_sidecar(
    sidecar: dict,
    event_dir: Path,
    storyboard_event_id: str,
    report: dict,
) -> None:
    """Disk-heavy event sidecar reconcile — caller must not hold sidecar lock."""
    bg_evt = normalize_bg_event_id(storyboard_event_id)
    report["removed_segments"] = purge_sidecar_segments_not_for_event(
        sidecar, storyboard_event_id,
    )
    preserved_root = kling_o3_clips_dir(event_dir) / "_preserved" / "segments"
    if preserved_root.is_dir():
        for entry in preserved_root.iterdir():
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(manifest.get("event_id", "")) != bg_evt:
                continue
            arc = int(manifest.get("arc_number") or 1)
            phase = str(manifest.get("phase") or "full")
            n = restore_preserved_segment_beats_if_empty(
                sidecar, event_dir, arc, bg_evt, phase,
            )
            if n:
                report["restored_segments"][entry.name] = n
            merged = merge_missing_still_insert_beats_from_preserve(
                sidecar, event_dir, arc, bg_evt, phase,
            )
            if merged:
                report.setdefault("merged_still_insert", {})[entry.name] = merged
    mirror_merge = merge_missing_segment_beats_from_json_mirror(
        sidecar, os.path.abspath(BG_SIDECAR_PATH), bg_evt,
    )
    if mirror_merge:
        report["merged_json_mirror"] = mirror_merge
    for phase in ("pre", "post", "full", "main"):
        n = rehydrate_segment_beats_from_o3_artifacts(
            sidecar, event_dir, 1, bg_evt, phase,
        )
        if n:
            report["restored_segments"][f"o3_artifacts_event_{bg_evt}_{phase}"] = n
    sidecar["active_context"] = {
        "arc_number": 1,
        "event_id": bg_evt,
        "phase": "pre",
    }


def reconcile_event_sidecar_after_milestone_exit(
    event_dir: str | Path,
    storyboard_event_id: str,
) -> dict:
    """EVENT_LOAD_SIDECAR_RECONCILE_V1 — purge milestone segments + restore from _preserved."""
    import copy as _copy

    event_dir = Path(event_dir)
    report: dict = {"restored_segments": {}, "removed_segments": []}
    snapshot = read_sidecar_for_poll_snapshot(lock_timeout_s=5.0)
    draft = _copy.deepcopy(snapshot)
    _run_event_sidecar_reconcile_on_sidecar(
        draft, event_dir, storyboard_event_id, report,
    )

    def _commit(sidecar: dict) -> None:
        sidecar.clear()
        sidecar.update(_copy.deepcopy(draft))

    mutate_sidecar_locked(_commit, timeout_s=30.0)
    return report


def archive_kling_o3_video_before_redo(
    beat: dict,
    event_dir: str | Path,
    *,
    reason: str,
) -> str | None:
    """Copy the beat's current approved video to ``_preserved/latest/`` before a redo overwrites it."""
    if not beat.get("kling_o3_video_path"):
        return None
    if preserve_kling_o3_beat_slot(beat, event_dir, reason=reason):
        return str(kling_o3_preserved_latest_dir(event_dir) / f"{beat.get('beat_id')}.mp4")
    return None


def resolve_proven_char_ref_source_beat_id_for_speaker(
    sidecar: dict,
    speaker: str,
) -> str | None:
    """Beat id whose @Image1 is the voice-proven extract row for ``speaker``."""
    try:
        from tools import kling_character_registry as reg

        proven = reg.resolve_proven_o3_bind(reg.get_character_entry(speaker))
        if proven:
            bid = str(proven.get("proven_from_beat_id") or "").strip()
            if bid:
                _, src = find_beat(sidecar, bid)
                if src and resolve_beat_char_ref_path(src):
                    return bid
    except Exception:
        pass
    for arc in (sidecar.get("arcs") or {}).values():
        for seg in (arc.get("segments") or {}).values():
            for row in seg.get("beats") or []:
                if str(row.get("speaker") or "").strip() != speaker:
                    continue
                if row.get("beat_plan_source") == "operator_insert_v1":
                    continue
                if resolve_beat_char_ref_path(row):
                    return str(row.get("beat_id") or "").strip() or None
    return None


def ensure_operator_insert_char_ref_parity(
    beat: dict,
    sidecar: dict,
    speaker: str,
    *,
    event_id: str,
    phase: str,
) -> bool:
    """Point manual-insert @Image1 at the proven extract char ref (voice parity)."""
    if beat.get("beat_plan_source") != "operator_insert_v1":
        return False
    source_id = resolve_proven_char_ref_source_beat_id_for_speaker(sidecar, speaker)
    if not source_id:
        return False
    _, source = find_beat(sidecar, source_id)
    if not source:
        return False
    src_ref = source.get("reference_image")
    if not isinstance(src_ref, dict):
        return False
    src_path = str(src_ref.get("abs_path") or "").strip()
    if not src_path or not os.path.isfile(src_path):
        return False
    if user_locked_char_ref_blocks_proven_overwrite(beat):
        return False
    if o3_prompt_box_law_active(beat):
        return False
    cur = resolve_beat_char_ref_path(beat) or ""
    if cur and os.path.normpath(cur) == os.path.normpath(src_path):
        return False
    beat["reference_image"] = _proven_reference_image_copy(src_ref)
    beat["reference_image_locked"] = True
    beat.pop("o3_prompt_box_law", None)
    beat.pop("o3_prompt_box_law_at", None)
    apply_kling_o3_defaults_to_beat(beat, event_id, phase)
    sync_element_char_ref_status(beat, heal_mismatch=False)
    return True


def proven_char_ref_source_beat_id(beat: dict) -> str | None:
    """Beat id to copy @Image1 from when ``o3_voice_stack_pin`` references a proven row."""
    pin = beat.get("o3_voice_stack_pin")
    if isinstance(pin, dict):
        bid = str(pin.get("pinned_from_beat_id") or "").strip()
        if bid:
            return bid
    quality = beat.get("o3_element_quality")
    if isinstance(quality, dict):
        bid = str(quality.get("pinned_from_beat_id") or "").strip()
        if bid:
            return bid
    return None


def apply_proven_char_ref_from_pin_source(beat: dict, sidecar: dict) -> bool:
    """Copy proven beat char ref onto a pinned row (Beat 18 stack for Lorelai, etc.)."""
    source_id = proven_char_ref_source_beat_id(beat)
    if not source_id:
        return False
    _, source = find_beat(sidecar, source_id)
    if not source:
        return False
    src_ref = source.get("reference_image")
    if not isinstance(src_ref, dict):
        return False
    src_path = str(src_ref.get("abs_path") or "").strip()
    if not src_path or not os.path.isfile(src_path):
        return False
    if user_locked_char_ref_blocks_proven_overwrite(beat):
        return False
    cur_path = resolve_beat_char_ref_path(beat) or ""
    if cur_path and os.path.normpath(cur_path) == os.path.normpath(src_path):
        return False
    beat["reference_image"] = _proven_reference_image_copy(src_ref)
    beat["reference_image_locked"] = True
    sync_element_char_ref_status(beat, heal_mismatch=False)
    return True


def proven_char_ref_aligned_with_pin_source(beat: dict, sidecar: dict) -> bool:
    """True when @Image1 matches the pinned proven source beat (Beat 18 path)."""
    return proven_char_ref_aligned_with_proven_source(
        beat, sidecar, str(beat.get("speaker") or "").strip(),
    )


def proven_char_ref_aligned_with_proven_source(
    beat: dict, sidecar: dict, speaker: str,
) -> bool:
    """True when @Image1 matches registry or pin proven source beat."""
    source_id = proven_char_ref_source_beat_id(beat)
    if not source_id and speaker:
        try:
            from tools import kling_character_registry as reg

            proven = reg.resolve_proven_o3_bind(reg.get_character_entry(speaker))
            if proven:
                source_id = str(proven.get("proven_from_beat_id") or "").strip() or None
        except Exception:
            source_id = None
    if not source_id:
        return False
    _, source = find_beat(sidecar, source_id)
    if not source:
        return False
    cur = resolve_beat_char_ref_path(beat)
    src = resolve_beat_char_ref_path(source)
    if not cur or not src:
        return False
    return os.path.normpath(cur) == os.path.normpath(src)



def proven_bypass_allowed_for_o3_submit(beat: dict, sidecar: dict, speaker: str) -> bool:
    if not proven_char_ref_aligned_with_proven_source(beat, sidecar, speaker):
        return False
    if not beat.get("reference_image_locked"):
        return True
    source_id = proven_char_ref_source_beat_id(beat)
    if not source_id and speaker:
        try:
            from tools import kling_character_registry as reg
            proven = reg.resolve_proven_o3_bind(reg.get_character_entry(speaker))
            if proven:
                source_id = str(proven.get("proven_from_beat_id") or "").strip() or None
        except Exception:
            source_id = None
    if not source_id:
        return True
    _, source = find_beat(sidecar, source_id)
    if not source:
        return True
    cur = resolve_beat_char_ref_path(beat)
    src = resolve_beat_char_ref_path(source)
    if cur and src and os.path.normpath(cur) != os.path.normpath(src):
        return False
    return True

def validate_proven_o3_element_submit(
    beat: dict,
    speaker: str,
    submit_element_id: str,
) -> str | None:
    """Return error text when submit element_id drifts from registry ``proven_o3_bind``."""
    try:
        from tools import kling_character_registry as reg

        proven = reg.resolve_proven_o3_bind(reg.get_character_entry(speaker))
    except Exception:
        proven = None
    if not proven:
        return None
    submit_eid = str(submit_element_id or "").strip()
    if submit_eid and submit_eid != proven["element_id"]:
        return (
            f"O3 submit element {submit_eid} != proven bind {proven['element_id']} "
            f"for {speaker!r}"
        )
    pin = beat.get("o3_voice_stack_pin")
    if isinstance(pin, dict):
        pin_eid = str(pin.get("element_id") or "").strip()
        if pin_eid and pin_eid != proven["element_id"]:
            return (
                f"beat pin element {pin_eid} != registry proven bind {proven['element_id']}"
            )
    return None


def o3_voice_stack_pin_active(beat: dict) -> bool:
    """True when beat carries an explicit proven Element+voice stack override."""
    pin = beat.get("o3_voice_stack_pin")
    if not isinstance(pin, dict):
        return False
    return bool(str(pin.get("element_id") or "").strip()) and bool(
        str(pin.get("kling_voice_id") or "").strip()
    )


def resolve_o3_element_list_entry(beat: dict, speaker: str) -> dict | None:
    """Registry proven contract first; legacy per-beat pin only when no proven bind."""
    try:
        from tools import kling_character_registry as reg

        proven_entry = reg.get_proven_element_list_entry(speaker)
        if proven_entry:
            return proven_entry
    except Exception:
        pass
    pin = beat.get("o3_voice_stack_pin")
    if isinstance(pin, dict):
        element_id = str(pin.get("element_id") or "").strip()
        voice_id = str(pin.get("kling_voice_id") or "").strip()
        if element_id and voice_id:
            element_name = str(pin.get("element_name") or "").strip()
            if not element_name:
                try:
                    from tools import kling_character_registry as reg

                    element_name = (
                        reg.kling_element_display_name(speaker)
                        or str(pin.get("element_name") or speaker).strip()
                    )
                except Exception:
                    element_name = speaker
            return {
                "element_id": element_id,
                "element_name": element_name,
                "voice_id": voice_id,
            }
    try:
        from tools import kling_character_registry as reg

        return reg.get_element_list_entry(speaker)
    except Exception:
        return None


def _o3_voice_binding_snapshot(beat: dict, speaker: str) -> dict[str, str]:
    """Capture element_id + voice_id stamped onto O3 option rows."""
    pin = beat.get("o3_voice_stack_pin")
    if isinstance(pin, dict):
        binding: dict[str, str] = {}
        if pin.get("element_id"):
            binding["element_id"] = str(pin["element_id"])
        if pin.get("kling_voice_id"):
            binding["kling_voice_id"] = str(pin["kling_voice_id"])
        if binding:
            return binding
    binding: dict[str, str] = {}
    quality = beat.get("o3_element_quality") or {}
    if quality.get("element_id"):
        binding["element_id"] = str(quality["element_id"])
    if quality.get("kling_voice_id"):
        binding["kling_voice_id"] = str(quality["kling_voice_id"])
    if binding:
        return binding
    try:
        from tools import kling_character_registry as reg

        entry = reg.get_element_list_entry(speaker) or {}
        if entry.get("element_id"):
            binding["element_id"] = str(entry["element_id"])
        vid = entry.get("voice_id") or reg.get_bound_voice_id(speaker)
        if vid:
            binding["kling_voice_id"] = str(vid)
    except Exception:
        pass
    return binding


def _find_job_log_for_delivery_path(
    event_dir: str | Path,
    beat_id: str,
    delivery_path: str | Path,
) -> Path | None:
    """Locate arlo_o3_jobs log that produced a delivery mp4."""
    jobs_dir = Path(event_dir) / "arlo_o3_jobs"
    if not jobs_dir.is_dir():
        return None
    target_name = Path(delivery_path).name
    candidates = sorted(
        jobs_dir.glob(f"*_{beat_id}.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for log_path in candidates:
        try:
            if target_name in log_path.read_text(encoding="utf-8", errors="replace"):
                return log_path
        except OSError:
            continue
    return None


def _o3_voice_binding_from_job_log(log_path: str | Path, delivery_path: str | Path) -> dict[str, str]:
    """Parse element_id + kling_voice_id from o3_submit for a finished delivery."""
    path = Path(log_path)
    if not path.is_file():
        return {}
    target = Path(delivery_path).resolve()
    submit_row: dict | None = None
    matched = False
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            row = json.loads(stripped)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("phase") == "o3_submit":
            submit_row = row
        if row.get("phase") == "delivery_encode" and row.get("dst"):
            if Path(str(row["dst"])).resolve() == target:
                matched = True
        if row.get("phase") == "done" and row.get("video"):
            if Path(str(row["video"])).resolve() == target:
                matched = True
    if not matched or not submit_row:
        return {}
    element = submit_row.get("element") or {}
    binding: dict[str, str] = {}
    eid = element.get("element_id")
    if eid:
        binding["element_id"] = str(eid)
    vid = submit_row.get("kling_voice_id") or element.get("voice_id")
    if vid:
        binding["kling_voice_id"] = str(vid)
    return binding


def list_o3_element_delivery_paths_on_disk(beat_id: str, event_dir: str | Path) -> list[Path]:
    """All paid O3 delivery mp4s for a beat (Element + Avatar Pro + POV + still), sorted by generation."""
    clips_dir = kling_o3_clips_dir(event_dir)
    if not clips_dir.is_dir():
        return []
    patterns = (
        f"{beat_id}_g*_element_o3_master_delivery.mp4",
        f"{beat_id}_g*_avatar_pro_delivery.mp4",
        f"{beat_id}_g*_pov_*_delivery.mp4",
        f"{beat_id}_still_insert_*.mp4",
    )
    seen: set[str] = set()
    paths: list[Path] = []
    for pattern in patterns:
        for path in clips_dir.glob(pattern):
            if not path.is_file():
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
    paths.sort(key=lambda p: _kling_o3_gen_from_video_path(str(p)) or 0)
    return paths


def count_o3_element_delivery_paths(disk_paths: list[Path]) -> int:
    """Element + Avatar Pro paid gens only — excludes POV/still aux deliveries."""
    count = 0
    for path in disk_paths:
        name = path.name
        if name.endswith("_element_o3_master_delivery.mp4") or name.endswith("_avatar_pro_delivery.mp4"):
            count += 1
    return count


def find_o3_video_path_for_option_key(
    beat_id: str,
    option_key: str,
    event_dirs: list[str | Path],
) -> Path | None:
    """Locate a delivery mp4 on disk when the sidecar option row is missing or stale."""
    beat_id = str(beat_id or "").strip()
    option_key = str(option_key or "").strip()
    if not beat_id or not option_key:
        return None
    seen: set[str] = set()
    for raw in event_dirs:
        clips_dir = kling_o3_clips_dir(raw)
        if not clips_dir.is_dir():
            continue
        for path in sorted(clips_dir.glob(f"{beat_id}_*.mp4")):
            if not path.is_file():
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            if _kling_o3_option_key(beat_id, resolved) == option_key:
                return path.resolve()
            if path.stem == option_key:
                return path.resolve()
    return None


def _canonical_o3_option_label(video_path: str, gen: int | None = None) -> str:
    """Stable Beat Gen label from delivery filename generation counter."""
    parsed = gen if gen is not None else _kling_o3_gen_from_video_path(video_path)
    path_l = str(video_path or "").lower()
    if parsed is not None:
        if "_avatar_pro_delivery" in path_l:
            return f"g{parsed} Avatar Pro"
        return f"g{parsed} O3 Element voice"
    if "_avatar_pro_delivery" in path_l:
        return "recovered Avatar Pro delivery"
    return "recovered O3 delivery"


def _sync_o3_option_gen_label(opt: dict) -> bool:
    """Ensure option row generation + label match the delivery filename."""
    video_path = str(opt.get("video_path") or "")
    gen = _kling_o3_gen_from_video_path(video_path)
    if gen is None:
        return False
    canonical = _canonical_o3_option_label(video_path, gen)
    changed = False
    if opt.get("generation") != gen:
        opt["generation"] = gen
        changed = True
    if opt.get("label") != canonical:
        opt["label"] = canonical
        changed = True
    return changed


def refresh_o3_ui_slot_layout(beat: dict) -> bool:
    """Sync generation labels only — does not reorder pin-slot layout."""
    options = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict) and str(o.get("video_path") or "").strip()
    ]
    if not options:
        return False
    changed = migrate_o3_options_edge_cut_to_trim(beat)
    for opt in options:
        if _sync_o3_option_gen_label(opt):
            changed = True
    beat["kling_o3_options"] = options
    return changed


def reconcile_beat_gallery_from_disk(beat: dict, event_dir: str | Path) -> bool:
    """Additive gallery repair — alias for ``reconcile_o3_disk_deliveries_for_beat``."""
    return reconcile_o3_disk_deliveries_for_beat(beat, event_dir)


def reconcile_o3_disk_deliveries_for_beat(beat: dict, event_dir: str | Path) -> bool:
    """Import every on-disk delivery into ``kling_o3_options`` (additive only, pin slots).

    Older clips remain in sidecar history and on disk under ``Event_N/kling_o3_clips/``.
    """
    beat_id = str(beat.get("beat_id") or "").strip()
    if not beat_id:
        return False
    event_dir = Path(event_dir)
    now = datetime.now(timezone.utc).isoformat()
    disk_paths = list_o3_element_delivery_paths_on_disk(beat_id, event_dir)
    if not disk_paths:
        changed = refresh_o3_ui_slot_layout(beat)
        if persist_o3_disk_enrich_on_beat(beat, event_dir, disk_paths=disk_paths):
            changed = True
        return changed

    from o3_job_status_contract import clear_o3_pointer_if_terminal

    options = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict)
    ]
    by_path = {
        str(o.get("video_path") or ""): o
        for o in options
        if str(o.get("video_path") or "").strip()
    }
    changed = clear_o3_pointer_if_terminal(beat, event_dir)
    speaker = str(beat.get("speaker") or "").strip()

    for delivery in disk_paths:
        delivery_str = str(delivery.resolve())
        gen = _kling_o3_gen_from_video_path(delivery_str)
        if delivery_str in by_path:
            opt = by_path[delivery_str]
            if _sync_o3_option_gen_label(opt):
                changed = True
            continue
        log_path = _find_job_log_for_delivery_path(event_dir, beat_id, delivery)
        binding = _o3_voice_binding_from_job_log(log_path, delivery) if log_path else {}
        if not binding and speaker:
            binding = _o3_voice_binding_snapshot(beat, speaker)
        label = _canonical_o3_option_label(delivery_str, gen)
        opt_row: dict = {
            "key": _kling_o3_option_key(beat_id, delivery_str),
            "label": label,
            "video_path": delivery_str,
            "source": "kling_o3_disk_reconcile",
            "active": delivery_str == str(beat.get("kling_o3_video_path") or ""),
            "created_at": now,
        }
        if binding:
            opt_row["o3_voice_binding"] = binding
        if gen is not None:
            opt_row["generation"] = gen
        options.append(opt_row)
        by_path[delivery_str] = opt_row
        changed = True

    if changed:
        beat["kling_o3_options"] = options
        normalize_kling_o3_option_slots(beat)
    if refresh_o3_ui_slot_layout(beat):
        changed = True
    if persist_o3_disk_enrich_on_beat(beat, event_dir, disk_paths=disk_paths):
        changed = True
    return changed


def prune_stale_o3_voice_options(beat: dict, speaker: str) -> bool:
    """Drop option rows whose delivery file is missing; never hide paid on-disk clips."""
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    if not options:
        return False
    kept: list[dict] = []
    changed = False
    for opt in options:
        path = str(opt.get("video_path") or "")
        if path and Path(path).is_file():
            kept.append(opt)
            continue
        changed = True
    if not changed:
        return False
    beat["kling_o3_options"] = kept
    if refresh_o3_ui_slot_layout(beat):
        changed = True
    return changed


def stash_prior_kling_o3_before_redo(
    beat: dict,
    event_dir: str | Path,
    *,
    reason: str,
    label: str = "previous approved O3 video",
) -> bool:
    """Archive the active clip and add it to ``kling_o3_options`` before a redo."""
    prior = beat.get("kling_o3_video_path")
    if not prior or not Path(str(prior)).is_file():
        return False
    archive_kling_o3_video_before_redo(beat, event_dir, reason=reason)
    video_path = str(prior)
    now = datetime.now(timezone.utc).isoformat()
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    options = [o for o in options if o.get("video_path") != video_path]
    beat_id = str(beat.get("beat_id") or "beat")
    digest = hashlib.sha1(video_path.encode("utf-8")).hexdigest()[:10]
    speaker = str(beat.get("speaker") or "").strip()
    binding = _o3_voice_binding_snapshot(beat, speaker)
    opt_row: dict = {
        "key": f"{beat_id}_o3_video_{digest}",
        "label": label,
        "video_path": video_path,
        "source": "prior_kling_o3_redo",
        "active": True,
        "created_at": now,
    }
    if binding:
        opt_row["o3_voice_binding"] = binding
    options.append(opt_row)
    for opt in options:
        opt["active"] = opt.get("video_path") == video_path
    beat["kling_o3_options"] = options
    refresh_o3_ui_slot_layout(beat)
    return True


def restore_active_kling_o3_after_failed_redo(beat: dict) -> bool:
    """Re-pin the last on-disk approved clip when an O3 redo fails mid-flight."""
    options = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict)
    ]
    active = next((o for o in options if o.get("active")), None)
    video_path = str((active or {}).get("video_path") or beat.get("kling_o3_video_path") or "")
    if not video_path or not Path(video_path).is_file():
        return False
    beat["kling_o3_video_path"] = video_path
    from kling_stitch_readiness import align_beat_active_delivery_clip  # noqa: PLC0415

    align_beat_active_delivery_clip(
        beat,
        video_path,
        mark_voice_fix_approved=True,
        clear_voice_fix_error=True,
    )
    for opt in options:
        opt["active"] = opt.get("video_path") == video_path
    beat["kling_o3_options"] = options
    refresh_o3_ui_slot_layout(beat)
    return True


def _kling_o3_option_key(beat_id: str, video_path: str) -> str:
    digest = hashlib.sha1(video_path.encode("utf-8")).hexdigest()[:10]
    return f"{beat_id}_o3_video_{digest}"


def normalize_kling_o3_option_slots(
    beat: dict,
    sidecar: dict | None = None,
) -> list[dict | None]:
    """Return fixed 3-slot view of ``kling_o3_options`` (index = UI container)."""
    gen_mode = resolve_beat_generation_mode(beat, sidecar or {})
    slots: list[dict | None] = [None, None, None]
    options = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict) and (o.get("video_path") or o.get("key"))
        and o3_option_visible_in_ui_slots(o, gen_mode)
    ]
    unslotted: list[dict] = []
    for opt in options:
        vp = str(opt.get("video_path") or "").strip()
        if vp:
            opt["video_path_exists"] = Path(vp).is_file()
        idx = opt.get("slot_index")
        if isinstance(idx, int) and 0 <= idx <= 2:
            if slots[idx] is None:
                slots[idx] = opt
                opt["slot_index"] = idx
            else:
                opt.pop("slot_index", None)
                unslotted.append(opt)
            continue
        unslotted.append(opt)
    for opt in unslotted:
        empty = next((j for j in range(3) if slots[j] is None), None)
        if empty is None:
            continue
        slots[empty] = opt
        opt["slot_index"] = empty
    return slots


def import_delivery_clip_to_beat(
    *,
    beat_id: str,
    delivery_mp4: str | Path,
    slot_index: int,
    label: str,
    source: str | None = None,
    make_active: bool = True,
    generation: int | None = None,
    event_dir: str | Path | None = None,
    scope=None,
    caller: str = "import_delivery_clip_to_beat",
) -> tuple[bool, dict | None]:
    """Copy delivery mp4 into ``Event_N/kling_o3_clips`` and register in sidecar."""
    from datetime import datetime, timezone

    from beatgen_scope import (  # noqa: PLC0415
        assert_clip_path_matches_scope,
        build_event_production_scope,
        scope_from_current_globals,
    )

    src = Path(delivery_mp4).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"delivery mp4 not found: {src}")

    resolved_event_dir = Path(event_dir or event_dir_for_beat_id(beat_id)).expanduser().resolve()
    active_scope = scope or scope_from_current_globals(__import__(__name__))
    if active_scope.kind != "event_production":
        active_scope = build_event_production_scope(resolved_event_dir)

    clips_dir = kling_o3_clips_dir(resolved_event_dir)
    sidecar_probe = read_sidecar()
    _, beat_probe = find_beat(sidecar_probe, beat_id)
    if not beat_probe:
        return False, None

    if generation is not None:
        gen = int(generation)
    else:
        gens = [
            _kling_o3_gen_from_video_path(str(o.get("video_path") or ""))
            for o in (beat_probe.get("kling_o3_options") or [])
            if isinstance(o, dict)
        ]
        gens = [g for g in gens if g is not None]
        gen = (max(gens) + 1) if gens else 1

    resolved_source = (source or "").strip() or None
    if not resolved_source:
        if beat_is_still_insert(beat_probe):
            resolved_source = "still_insert_kling_idle"
        else:
            resolved_source = O3_OPTION_SOURCE_POV_MOTION

    use_still_naming = (
        beat_is_still_insert(beat_probe)
        and resolved_source in O3_OPTION_SOURCE_STILL
    )

    if use_still_naming:
        ts = int(datetime.now(timezone.utc).timestamp())
        dest_name = f"{beat_id}_still_insert_{ts}_s{slot_index}_kling_idle_tts.mp4"
    else:
        dest_name = f"{beat_id}_g{gen}_delivery.mp4"
    dest_path = clips_dir / dest_name
    copy_file_durable(str(src), str(dest_path))
    assert_clip_path_matches_scope(dest_path, active_scope)

    now = datetime.now(timezone.utc).isoformat()

    def mutator(beat: dict, sidecar: dict) -> None:
        if str(beat.get("beat_id") or "") != beat_id:
            return
        assign_kling_o3_option_to_slot(
            beat,
            slot_index,
            video_path=str(dest_path.resolve()),
            label=label,
            source=resolved_source,
            now=now,
            make_active=make_active,
        )
        normalize_kling_o3_option_slots(beat, sidecar)
        sync_o3_selection_pipeline_fields(beat, sidecar)
        persist_o3_disk_enrich_on_beat(beat, resolved_event_dir)
        if beat_is_still_insert(beat) and make_active:
            from kling_stitch_readiness import finalize_kling_delivery_clip  # noqa: PLC0415

            finalize_kling_delivery_clip(beat, str(dest_path.resolve()))

    return update_beat_locked(
        beat_id,
        mutator,
        scope=active_scope,
        caller=caller,
        skip_single_writer_gate=True,
    )


def assign_kling_o3_option_to_slot(
    beat: dict,
    slot_index: int,
    *,
    video_path: str,
    label: str,
    source: str,
    now: str,
    make_active: bool = True,
    o3_voice_binding: dict | None = None,
) -> str:
    """Place a generated clip in container ``slot_index`` (0–2); returns option key."""
    slot_index = max(0, min(2, int(slot_index)))
    beat_id = str(beat.get("beat_id") or "beat")
    key = _kling_o3_option_key(beat_id, video_path)
    new_opt = {
        "key": key,
        "label": label,
        "video_path": video_path,
        "source": source,
        "active": make_active,
        "slot_index": slot_index,
        "created_at": now,
    }
    if o3_voice_binding:
        new_opt["o3_voice_binding"] = o3_voice_binding
    gen = _kling_o3_gen_from_video_path(video_path)
    if gen is not None:
        new_opt["generation"] = gen
    options = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict) and str(o.get("video_path") or "") != video_path
    ]
    for opt in options:
        if opt.get("slot_index") == slot_index:
            opt.pop("slot_index", None)
    options.append(new_opt)
    if make_active:
        for opt in options:
            opt["active"] = str(opt.get("video_path") or "") == video_path
        beat["kling_o3_video_path"] = video_path
        beat["kling_o3_selected_option_key"] = key
        if gen is not None:
            beat["kling_o3_generation"] = max(int(beat.get("kling_o3_generation") or 0), gen)
        if heal_invalid_kling_o3_trim(beat):
            invalidate_kling_o3_trim_scratch(beat_id, event_dir_for_beat_id(beat_id))
        else:
            prune_stale_kling_o3_trim_scratch(beat_id, event_dir_for_beat_id(beat_id), beat)
    beat["kling_o3_options"] = options
    for opt in options:
        _sync_o3_option_gen_label(opt)
    return key


def update_beat_locked_for_o3_paid_output(
    beat_id: str,
    mutator: Callable[[dict, dict], None],
    *,
    attempt_id: str | None = None,
    ui_job_id: str | None = None,
    paid_delivery_path: str | None = None,
) -> tuple[bool, dict | None]:
    """Attempt-guarded beat patch with job heal + paid-delivery bypass.

    Stale ``kling_o3_voice_fix_attempt_id`` (session heal, cross-store lag) must not
    drop a paid delivery row after encode. When ``paid_delivery_path`` exists on disk
    and ``MN_O3_ATTEMPT_ID`` matches this job, retry without the attempt guard.
    """
    expected = (attempt_id or "").strip() or None
    ui_job_id = (ui_job_id or "").strip() or None
    ok, live = update_beat_locked(beat_id, mutator, expected_attempt_id=expected)
    if ok or not live:
        return ok, live
    if not expected:
        return ok, live

    ui_job = str(live.get("kling_o3_voice_fix_ui_job_id") or "")
    job_match = bool(ui_job_id and ui_job == ui_job_id)
    env_attempt = (os.environ.get("MN_O3_ATTEMPT_ID") or "").strip()
    env_match = env_attempt == expected

    if job_match:
        def heal_attempt(b: dict, _sidecar: dict) -> None:
            b["kling_o3_voice_fix_attempt_id"] = expected

        update_beat_locked(beat_id, heal_attempt)
        ok, live = update_beat_locked(beat_id, mutator, expected_attempt_id=expected)
        if ok:
            return ok, live

    paid = (paid_delivery_path or "").strip()
    if paid and Path(paid).is_file() and env_match:
        ok, live = update_beat_locked(beat_id, mutator, expected_attempt_id=None)
        if ok:

            def stamp_attempt(b: dict, _sidecar: dict) -> None:
                b["kling_o3_voice_fix_attempt_id"] = expected

            update_beat_locked(beat_id, stamp_attempt)
        return ok, live

    return ok, live


def persist_o3_delivery_option_checkpoint(
    beat_id: str,
    *,
    video_path: str,
    slot_index: int,
    label: str,
    o3_voice_binding: dict | None,
    attempt_id: str | None,
    generation: int | None = None,
    ui_job_id: str | None = None,
) -> bool:
    """Write delivery option to sidecar immediately after encode — before heavy finalize."""
    now = datetime.now(timezone.utc).isoformat()

    def apply(beat: dict, _sidecar: dict) -> None:
        if str(beat.get("beat_id") or "") != beat_id:
            return
        assign_kling_o3_option_to_slot(
            beat,
            slot_index,
            video_path=video_path,
            label=label,
            source="kling_o3_element_native_voice",
            now=now,
            make_active=True,
            o3_voice_binding=o3_voice_binding,
        )
        if generation is not None:
            beat["kling_o3_generation"] = max(int(beat.get("kling_o3_generation") or 0), generation)

    ok, _ = update_beat_locked_for_o3_paid_output(
        beat_id,
        apply,
        attempt_id=attempt_id,
        ui_job_id=ui_job_id,
        paid_delivery_path=video_path,
    )
    if not ok:
        raise RuntimeError(f"sidecar checkpoint persist failed for {beat_id}")
    return True


def _delivery_path_from_o3_job_log(log_path: str | Path | None) -> str | None:
    """Return delivery mp4 path from pipeline log (delivery_encode or phase done)."""
    if not log_path:
        return None
    path = Path(log_path)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            parsed = json.loads(stripped)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        if parsed.get("phase") == "done" and parsed.get("video"):
            return str(parsed["video"])
        if parsed.get("phase") == "delivery_encode" and parsed.get("dst"):
            return str(parsed["dst"])
    return None


def preview_orphan_o3_delivery_on_beat(
    beat: dict,
    event_dir: str | Path,
    *,
    beat_id: str | None = None,
    log_path: str | Path | None = None,
    delivery_path: str | Path | None = None,
    make_active: bool = False,
) -> tuple[bool, str | None]:
    """In-memory orphan merge for session GET — no sidecar lock."""
    event_dir = Path(event_dir)
    beat_id = str(beat_id or beat.get("beat_id") or "").strip()
    if not beat_id or str(beat.get("beat_id") or "") != beat_id:
        return False, None
    resolved = str(delivery_path or "").strip() or _delivery_path_from_o3_job_log(log_path) or ""
    if not resolved or not Path(resolved).is_file():
        disk_paths = list_o3_element_delivery_paths_on_disk(beat_id, event_dir)
        if disk_paths:
            resolved = str(disk_paths[-1].resolve())
    delivery_path = resolved or None
    if not delivery_path or not Path(delivery_path).is_file():
        gen = beat.get("kling_o3_generation")
        if gen is not None:
            guess = kling_o3_clips_dir(event_dir) / (
                f"{beat_id}_g{gen}_element_o3_master_delivery.mp4"
            )
            if guess.is_file():
                delivery_path = str(guess)
    if not delivery_path or not Path(delivery_path).is_file():
        return False, None
    now = datetime.now(timezone.utc).isoformat()
    gallery_touched = False
    recovered_gen = None
    m = re.search(r"_g(\d+)_element_o3_master_delivery\.mp4$", str(delivery_path))
    if m:
        recovered_gen = int(m.group(1))
    current_gen = int(beat.get("kling_o3_generation") or 0)
    should_activate = make_active or (
        recovered_gen is not None and recovered_gen >= current_gen
    )
    speaker = str(beat.get("speaker") or "").strip()
    binding: dict[str, str] = {}
    if log_path:
        binding = _o3_voice_binding_from_job_log(log_path, delivery_path)
    if not binding and speaker:
        try:
            from tools import kling_character_registry as reg

            proven = reg.get_proven_element_list_entry(speaker)
            entry = proven or reg.get_element_list_entry(speaker) or {}
            binding = {
                "element_id": str(entry.get("element_id") or ""),
                "kling_voice_id": str(
                    entry.get("voice_id") or reg.get_bound_voice_id(speaker) or "",
                ),
            }
            binding = {k: v for k, v in binding.items() if v}
        except Exception:
            pass
    existing = {
        str(o.get("video_path") or "")
        for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict)
    }
    if delivery_path not in existing:
        slot = 0
        slots = normalize_kling_o3_option_slots(beat)
        for idx, opt in enumerate(slots):
            if opt is None:
                slot = idx
                break
        assign_kling_o3_option_to_slot(
            beat,
            slot,
            video_path=delivery_path,
            label="recovered O3 delivery",
            source="kling_o3_element_native_voice",
            now=now,
            make_active=should_activate,
            o3_voice_binding=binding or None,
        )
        gallery_touched = True
    else:
        gallery_touched = True
        if should_activate:
            ri = max(0, min(2, int(beat.get("kling_o3_replace_slot_index") or 0)))
            assign_kling_o3_option_to_slot(
                beat,
                ri,
                video_path=str(delivery_path),
                label=_canonical_o3_option_label(str(delivery_path), recovered_gen),
                source="kling_o3_element_native_voice",
                now=now,
                make_active=True,
                o3_voice_binding=binding or None,
            )
    if delivery_path in existing and should_activate:
        for opt in beat.get("kling_o3_options") or []:
            if isinstance(opt, dict) and str(opt.get("video_path") or "") == delivery_path:
                opt["active"] = True
                beat["kling_o3_video_path"] = delivery_path
                beat["kling_o3_selected_option_key"] = opt.get("key")
                beat["kling_o3_selected_at"] = now
                if recovered_gen is not None:
                    beat["kling_o3_generation"] = recovered_gen
            elif isinstance(opt, dict):
                opt["active"] = False
    if not should_activate and beat.get("kling_o3_video_path"):
        active_path = str(beat.get("kling_o3_video_path") or "")
        for opt in beat.get("kling_o3_options") or []:
            if isinstance(opt, dict):
                opt["active"] = str(opt.get("video_path") or "") == active_path
    from kling_stitch_readiness import align_beat_active_delivery_clip  # noqa: PLC0415

    align_beat_active_delivery_clip(
        beat,
        delivery_path,
        mark_voice_fix_approved=True,
        clear_voice_fix_error=True,
    )
    job_attempt = (os.environ.get("MN_O3_ATTEMPT_ID") or "").strip()
    if job_attempt:
        beat["kling_o3_voice_fix_attempt_id"] = job_attempt
    if binding:
        beat["o3_element_quality"] = {
            "speaker": speaker,
            **binding,
            "delivery_profile": "LD-284/LD-296 1280x720 H.264 <=1.9Mbps +faststart",
            "method": "O3 Pro reference-to-video + Element create-voice (no lipsync detour)",
            "applied_at": now,
            "recovered_from": "orphan_delivery_after_sidecar_io_error",
        }
    try:
        from o3_generation_intent import load_intent_visual_ref_fields_from_job_log

        beat.update(load_intent_visual_ref_fields_from_job_log(log_path, event_dir))
    except Exception:
        pass
    return gallery_touched, str(delivery_path)


def recover_orphan_o3_delivery(
    beat_id: str,
    event_dir: str | Path,
    *,
    log_path: str | Path | None = None,
    delivery_path: str | Path | None = None,
    make_active: bool = False,
) -> dict[str, Any]:
    """Sidecar-finalize recovery when Kling finished but persist hit errno 11/35.

    Finds delivery mp4 from explicit path, job log, or latest on-disk gen, upserts
    option slot, clears stuck running/failed job pointers. Idempotent when option
    already exists.

    Does not call ``init_bg_paths`` — callers (HTTP handler, O3 subprocess) must
    already have milestone/event sidecar authority bound; re-init would tear
    milestone JSON-only scope and write gallery rows to the wrong store.
    """
    event_dir = Path(event_dir)
    delivery_path = str(delivery_path or "").strip() or None

    def apply(beat: dict, _sidecar: dict) -> None:
        preview_orphan_o3_delivery_on_beat(
            beat,
            event_dir,
            beat_id=beat_id,
            log_path=log_path,
            delivery_path=delivery_path,
            make_active=make_active,
        )

    ok, beat = update_beat_locked(beat_id, apply)
    if ok and beat:
        def reconcile_apply(b: dict, _sc: dict) -> None:
            if str(b.get("beat_id") or "") != beat_id:
                return
            reconcile_o3_disk_deliveries_for_beat(b, event_dir)

        update_beat_locked(beat_id, reconcile_apply)
    resolved_delivery = str(beat.get("kling_o3_video_path") or delivery_path or "").strip() or None
    option_paths = {
        str(o.get("video_path") or "")
        for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict)
    } if beat else set()
    recovered = bool(
        ok
        and beat
        and resolved_delivery
        and Path(resolved_delivery).is_file()
        and resolved_delivery in option_paths
    )
    if recovered:
        print(
            f"[o3_orphan_recovery] beat_id={beat_id} video={resolved_delivery}",
            flush=True,
        )
    return {
        "ok": bool(ok and beat),
        "beat_id": beat_id,
        "delivery_path": resolved_delivery,
        "recovered": recovered,
    }


def kling_o3_pinned_dir(event_dir: str | Path) -> Path:
    """User-pinned preserve slot — survives auto ``latest/`` overwrites on redo."""
    return kling_o3_clips_dir(event_dir) / "_preserved" / "pinned"


_KLING_O3_PIN_RESTORE_FIELDS: tuple[str, ...] = (
    "kling_o3_video_path",
    "kling_o3_generation",
    "kling_o3_status",
    "kling_o3_duration",
    "kling_o3_duration_locked",
    "kling_o3_prompt",
    "kling_o3_actual_duration_s",
    "kling_o3_trim_start",
    "kling_o3_trim_back",
    "kling_o3_post_speech_trim",
    "status",
    "kling_o3_completed_at",
    "kling_o3_task_id",
)


def has_pinned_kling_o3_preserve(beat_id: str, event_dir: str | Path) -> bool:
    pinned = kling_o3_pinned_dir(event_dir)
    return (pinned / f"{beat_id}.mp4").is_file() and (pinned / f"{beat_id}.json").is_file()


def storyboard_beat_id_from_bg_beat(bg_beat_id: str) -> str | None:
    """Map ``bg_arc1_event1_post_beat_01`` → ``beat_01`` (suffix-only fallback)."""
    m = re.search(r"_beat_(\d+)$", bg_beat_id or "")
    if not m:
        return None
    num = m.group(1)
    return f"beat_{num.zfill(2)}" if num.isdigit() else f"beat_{num}"


def _parse_bg_beat_segment(bg_beat_id: str) -> tuple[int, str, str] | None:
    m = re.match(r"bg_arc(\d+)_event(\d+)_(\w+)_beat_", bg_beat_id or "")
    if not m:
        return None
    return int(m.group(1)), m.group(2), m.group(3)


def storyboard_beat_id_for_bg_beat(
    bg_beat_id: str,
    *,
    sidecar: dict | None = None,
    production_state: dict | None = None,
    video_role: str = "resolution",
) -> str | None:
    """Map Beat Gen row id → storyboard partition beat key.

    BG ids embed script line numbers (``beat_21``); storyboard ``display_order``
    uses sequential ``beat_01``..``beat_N``. Prefer positional mapping so magic
    writeback survives DISPLAY_ORDER_STRICT pruning.
    """
    if sidecar and production_state and bg_beat_id:
        parsed = _parse_bg_beat_segment(bg_beat_id)
        if parsed:
            arc, event_id, phase = parsed
            seg = get_seg_entry(sidecar, arc, event_id, phase)
            beats = seg.get("beats") or []
            idx = next(
                (i for i, row in enumerate(beats) if row.get("beat_id") == bg_beat_id),
                None,
            )
            if idx is not None:
                partition = (production_state.get("videos") or {}).get(video_role) or {}
                display_order = partition.get("display_order")
                if isinstance(display_order, list) and idx < len(display_order):
                    mapped = display_order[idx]
                    if isinstance(mapped, str) and mapped:
                        return mapped
    return storyboard_beat_id_from_bg_beat(bg_beat_id)


def build_storyboard_display_order_for_bg_segment(
    sidecar: dict,
    arc_number: int,
    event_id: str,
    phase: str,
) -> list[str]:
    """Sequential storyboard keys beat_01..beat_N for BG segment row order."""
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    n = len(seg.get("beats") or [])
    return [f"beat_{i + 1:02d}" for i in range(n)]


def sync_storyboard_partition_display_order_from_bg_segment(
    state_manager,
    video_role: str,
    sidecar: dict,
    arc_number: int,
    event_id: str,
    phase: str,
) -> list[str]:
    """BG_PARTITION_DISPLAY_ORDER_SYNC_V1 — align partition display_order with BG segment.

    Beat Gen owns beat rows in sidecar/sqlite; production_state partition display_order
    was only seeded on accept-beats (beats with image/video). Magic writeback targets
    partition beats — empty display_order triggers DISPLAY_ORDER_STRICT prune and drops
    magic_* fields immediately after write.
    """
    desired = build_storyboard_display_order_for_bg_segment(sidecar, arc_number, event_id, phase)
    if not desired:
        return []
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    bg_rows = seg.get("beats") or []

    def _sync(partition: dict) -> None:
        pdo = partition.get("display_order")
        if not isinstance(pdo, list):
            return
        if not pdo:
            pdo.extend(desired)
        else:
            for sb_bid in desired:
                if sb_bid not in pdo:
                    pdo.append(sb_bid)
        pbeats = partition.setdefault("beats", {})
        for i, sb_bid in enumerate(desired):
            if sb_bid not in pbeats:
                row = bg_rows[i] if i < len(bg_rows) else {}
                pbeats[sb_bid] = {
                    "speaker": (row.get("speaker") or "").strip(),
                    "text": (row.get("dialogue_text") or "").strip(),
                }

    state_manager.mutate_video_state(video_role, _sync)
    return desired


def resolve_magic_style_for_render(
    bg_beat_id: str,
    *,
    sidecar: dict | None = None,
    production_state: dict | None = None,
    video_role: str = "resolution",
    manual_path: list | None = None,
    scene_registry: dict | None = None,
    event_id: str | int | None = None,
    module_id: int = 1,
) -> str:
    """Pick compositor style — canonical approved look is tessa_ori (beat 1 resolution)."""
    try:
        from magic_render_contract import resolve_magic_style_from_registry
    except ImportError:
        resolve_magic_style_from_registry = None  # type: ignore[assignment]
    evt = event_id
    if evt is None and production_state:
        evt = production_state.get("event_id") or production_state.get("scope_event_id")
    if resolve_magic_style_from_registry is not None:
        return resolve_magic_style_from_registry(
            bg_beat_id,
            scene_registry,
            module_id=module_id,
            event_id=evt or 1,
            video_role=video_role,
        )
    return "tessa_ori"


def resolve_magic_still_render_duration(
    bg_beat_id: str,
    *,
    scene_registry: dict | None = None,
    fallback: float = 4.0,
    event_id: str | int | None = None,
    video_role: str = "resolution",
    module_id: int = 1,
) -> float:
    """Duration for magic_still compositor — scene_registry pins approved nest orbital at 6.08s."""
    try:
        from magic_render_contract import resolve_magic_still_duration_from_registry
    except ImportError:
        resolve_magic_still_duration_from_registry = None  # type: ignore[assignment]
    if resolve_magic_still_duration_from_registry is not None:
        return resolve_magic_still_duration_from_registry(
            bg_beat_id,
            scene_registry,
            module_id=module_id,
            event_id=event_id or 1,
            video_role=video_role,
            fallback=fallback,
        )
    return float(fallback)


def bg_beat_id_from_storyboard_id(
    storyboard_beat_id: str,
    event_id: str,
    phase: str,
    arc_number: int = 1,
) -> str | None:
    """Map ``beat_01`` → ``bg_arc1_event1_post_beat_01`` for Beat Gen sidecar keys."""
    m = re.search(r"beat_(\d+)$", storyboard_beat_id or "")
    if not m:
        return None
    num = m.group(1)
    num_fmt = num.zfill(2) if num.isdigit() else num
    return f"bg_arc{arc_number}_event{event_id}_{phase}_beat_{num_fmt}"


_MAGIC_SYNC_FIELDS: tuple[str, ...] = (
    "magic_still_path",
    "magic_video_path",
    "magic_manual_path",
    "magic_path_authored_against",
)

_AUDIO_SYNC_FIELDS: tuple[str, ...] = (
    "audio_file",
    "audio_duration_s",
)


def beat_magic_video_clip_path(beat: dict, event_dir: str | Path) -> Path | None:
    """Resolved on-disk path for ``magic_video_path`` when present."""
    name = beat.get("magic_video_path")
    if not name:
        return None
    p = Path(name)
    if not p.is_absolute():
        p = Path(event_dir) / name
    if p.is_file():
        return p.resolve()
    return None


def resolve_active_magic_layer(
    beat: dict,
    event_dir: str | Path | None = None,
) -> str | None:
    """Authoritative magic layer for preview + stitch when still and video may coexist.

    Orphaned ``magic_video_path`` after redoing magic-on-still must not win over a
    newer ``magic_still_path``. When both files exist on disk, the newer mtime wins.
    """
    if event_dir is not None:
        still_clip = beat_magic_still_clip_path(beat, event_dir)
        video_clip = beat_magic_video_clip_path(beat, event_dir)
        if still_clip and not video_clip:
            return "still"
        if video_clip and not still_clip:
            return "video"
        if still_clip and video_clip:
            still_m = still_clip.stat().st_mtime
            video_m = video_clip.stat().st_mtime
            if still_m > video_m:
                return "still"
            if video_m > still_m:
                return "video"
            if beat_is_still_insert(beat):
                return "still"
            return "video"
        return None
    if beat.get("magic_video_path"):
        return "video"
    if beat.get("magic_still_path"):
        return "still"
    return None


def resolve_bg_magic_canonical_kind(
    beat: dict,
    event_dir: str | Path | None = None,
) -> str | None:
    """Which magic composite is canonical for preview + stitch export."""
    return resolve_active_magic_layer(beat, event_dir)


def merge_storyboard_magic_into_bg_beat(
    beat: dict,
    production_state: dict | None,
    video_role: str,
    sidecar: dict | None = None,
    event_dir: str | Path | None = None,
) -> dict:
    """Fill missing magic/TTS fields on a BG beat from storyboard partition state."""
    out = dict(beat)
    if not production_state:
        out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out, event_dir)
        return out
    sb_id = storyboard_beat_id_for_bg_beat(
        beat.get("beat_id") or "",
        sidecar=sidecar,
        production_state=production_state,
        video_role=video_role,
    )
    if not sb_id:
        out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out, event_dir)
        return out
    out["storyboard_beat_id"] = sb_id
    sb_beat = (
        ((production_state.get("videos") or {}).get(video_role) or {})
        .get("beats") or {}
    ).get(sb_id) or {}
    for field in _MAGIC_SYNC_FIELDS:
        if sb_beat.get(field) is not None and not out.get(field):
            out[field] = sb_beat[field]
    # Storyboard partition owns TTS filenames (beat_02 → line_02_*), not BG script ids.
    for field in _AUDIO_SYNC_FIELDS:
        if sb_beat.get(field) is not None:
            out[field] = sb_beat[field]
    out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out, event_dir)
    return out


def persist_magic_fields_on_bg_sidecar(
    sidecar: dict,
    *,
    arc_number: int,
    event_id: str,
    phase: str,
    request_beat_id: str,
    fields: dict,
) -> bool:
    """Write magic_* fields onto the matching Beat Gen sidecar row."""
    bg_beat_id = (
        request_beat_id
        if str(request_beat_id).startswith("bg_")
        else bg_beat_id_from_storyboard_id(request_beat_id, str(event_id), phase, arc_number)
    )
    beat_obj = None
    if bg_beat_id:
        seg = get_seg_entry(sidecar, arc_number, str(event_id), phase)
        beat_obj = next(
            (b for b in (seg.get("beats") or []) if b.get("beat_id") == bg_beat_id),
            None,
        )
    if beat_obj is None:
        _, beat_obj = find_beat(sidecar, request_beat_id)
    if not beat_obj:
        return False
    for key, val in fields.items():
        if val is None:
            beat_obj.pop(key, None)
        else:
            beat_obj[key] = val
    return True


def resolve_bg_beat_tts_text(beat: dict) -> str:
    """Spoken line for ElevenLabs — dialogue_text first, else Kling prompt extraction."""
    dialogue = (beat.get("dialogue_text") or "").strip()
    if dialogue:
        return dialogue
    return extract_spoken_dialogue_from_kling_prompt(beat.get("kling_o3_prompt") or "")


def resolve_bg_beat_tts_audio_path(
    event_dir: str | Path,
    beat: dict,
    *,
    sidecar: dict | None = None,
    production_state: dict | None = None,
    video_role: str = "resolution",
) -> Path | None:
    """On-disk TTS mp3 for a Beat Gen beat.

    Uses storyboard ``display_order`` beat id (``beat_02``) for filename lookup,
    not the BG script suffix (``beat_21`` → ``line_21_*`` wrong clip).
    """
    event_dir = Path(event_dir)
    af = (beat.get("audio_file") or "").strip()
    sb_id = (beat.get("storyboard_beat_id") or "").strip()
    if not sb_id and sidecar and production_state:
        sb_id = storyboard_beat_id_for_bg_beat(
            beat.get("beat_id") or "",
            sidecar=sidecar,
            production_state=production_state,
            video_role=video_role,
        ) or ""
    if not sb_id:
        sb_id = storyboard_beat_id_from_bg_beat(beat.get("beat_id") or "") or ""

    def _resolve_named_file(name: str) -> Path | None:
        p = Path(name)
        if p.is_file():
            return p.resolve()
        for base in (event_dir / "story_scene_tts_v2", event_dir):
            direct = base / name
            if direct.is_file():
                return direct.resolve()
            if base.is_dir():
                for hit in sorted(base.rglob(name)):
                    if hit.is_file() and "_archive" not in str(hit):
                        return hit.resolve()
        return None

    if af:
        found = _resolve_named_file(af)
        if found is not None:
            return found
    if sb_id:
        try:
            beat_num = int(sb_id.split("_")[1])
        except (IndexError, ValueError):
            return None
        tts_root = event_dir / "story_scene_tts_v2"
        if not tts_root.is_dir():
            return None
        matches = sorted(
            p for p in tts_root.rglob(f"line_{beat_num:02d}_*.mp3")
            if p.is_file() and "_archive" not in str(p)
        )
        if matches:
            return matches[-1].resolve()
    return None


def materialize_magic_still_with_tts_export(
    beat: dict,
    event_dir: str | Path,
    scratch_dir: Path,
    *,
    freeze_tail_s: float = MAGIC_STILL_STITCH_EXPORT_FREEZE_TAIL_S,
) -> Path:
    """Mix Beat Gen TTS onto silent magic_still clip for stitch export.

    Plays the full magic_still file — never truncates video to speech end. Beat joins
    are hard cuts at each clip's natural end (no extra freeze_tail between beats).
    """
    magic_still = beat_magic_still_clip_path(beat, event_dir)
    if magic_still is None:
        raise FileNotFoundError(f"missing magic_still for {beat.get('beat_id')}")
    audio = resolve_bg_beat_tts_audio_path(event_dir, beat)
    if audio is None:
        return magic_still
    beat_id = beat.get("beat_id") or "beat"
    dest = magic_still_tts_scratch_path(beat_id, event_dir, scratch_dir)
    if dest.is_file() and dest.stat().st_mtime >= max(
        magic_still.stat().st_mtime, audio.stat().st_mtime,
    ):
        return dest.resolve()
    audio_dur = _ffprobe_duration(audio)
    still_dur = _ffprobe_duration(magic_still)
    # Full still when video covers speech; extend via tpad only when speech outlasts still.
    trim_end: float | None = None
    mix_freeze = 0.0
    if audio_dur > still_dur + 0.05:
        mix_freeze = float(freeze_tail_s)
    fs = _ffmpeg_stitch_module()
    fs.trim_normalized(
        magic_still,
        dest,
        trim_start=0.0,
        trim_end=trim_end,
        mix_audio_path=audio,
        audio_delay=0.0,
        freeze_tail_s=mix_freeze,
    )
    return dest.resolve()


def magic_still_tts_scratch_path(
    beat_id: str,
    event_dir: str | Path,
    scratch_dir: Path | None = None,
) -> Path:
    """On-disk path for silent magic_still + TTS mix used at stitch export."""
    if scratch_dir is None:
        scratch_dir = Path(event_dir) / "assembled" / "_kling_o3_trim_scratch"
    return Path(scratch_dir) / f"{beat_id}_magic_still_tts_{MAGIC_STILL_TTS_EXPORT_RECIPE}.mp4"


def invalidate_magic_still_tts_scratch(beat_id: str, event_dir: str | Path) -> None:
    """Drop cached TTS mix after magic_still redo so stitch export picks up the new clip."""
    scratch_dir = Path(event_dir) / "assembled" / "_kling_o3_trim_scratch"
    for name in (
        f"{beat_id}_magic_still_tts_{MAGIC_STILL_TTS_EXPORT_RECIPE}.mp4",
        f"{beat_id}_magic_still_tts.mp4",
    ):
        p = scratch_dir / name
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def resolve_storyboard_lipsync_clip(
    event_dir: str | Path,
    storyboard_beat_id: str,
    production_state: dict | None = None,
    video_role: str = "resolution",
) -> Path | None:
    """Prefer partition-scoped lipsync/final clip for a storyboard beat."""
    from server_handlers.clip_paths import resolve_animation_clip

    sb_beat: dict = {}
    if production_state:
        sb_beat = (
            ((production_state.get("videos") or {}).get(video_role) or {})
            .get("beats") or {}
        ).get(storyboard_beat_id) or {}

    fname = None
    final = sb_beat.get("final") or {}
    lipsync = sb_beat.get("lipsync") or {}
    if final.get("file"):
        fname = final["file"]
    elif lipsync.get("file"):
        fname = lipsync["file"]
    else:
        fname = f"{storyboard_beat_id}_lipsync.mp4"

    return resolve_animation_clip(Path(event_dir), fname, video_role)


def import_storyboard_clip_to_kling_o3(
    beat: dict,
    event_dir: str | Path,
    *,
    source_path: Path | None = None,
    storyboard_beat_id: str | None = None,
    production_state: dict | None = None,
    video_role: str = "resolution",
    generation: int = 0,
) -> dict[str, Any]:
    """Copy a storyboard lipsync clip into the Beat Gen ``kling_o3_clips`` slot."""
    bg_beat_id = beat.get("beat_id")
    if not bg_beat_id:
        raise ValueError("missing beat_id")

    sb_id = storyboard_beat_id or storyboard_beat_id_from_bg_beat(bg_beat_id)
    ev = Path(event_dir)
    if source_path is None:
        if not sb_id:
            raise ValueError("cannot resolve source without storyboard beat id")
        source_path = resolve_storyboard_lipsync_clip(
            ev, sb_id, production_state, video_role=video_role,
        )
    if source_path is None or not source_path.is_file():
        raise FileNotFoundError(
            f"storyboard clip not found for {sb_id or bg_beat_id}",
        )

    dest = kling_o3_clips_dir(ev) / f"{bg_beat_id}_g{generation}.mp4"
    shutil.copy2(source_path, dest)

    beat["kling_o3_generation"] = generation
    from kling_stitch_readiness import finalize_kling_delivery_clip  # noqa: PLC0415

    finalize_kling_delivery_clip(beat, str(dest.resolve()))
    beat["kling_o3_completed_at"] = datetime.now(timezone.utc).isoformat()
    beat.pop("kling_o3_error", None)
    beat.pop("kling_o3_task_id", None)
    beat["storyboard_clip_import"] = {
        "source_path": str(source_path.resolve()),
        "storyboard_beat_id": sb_id,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "video_role": video_role,
    }

    if production_state and sb_id and not beat.get("magic_manual_path"):
        sb_beat = (
            ((production_state.get("videos") or {}).get(video_role) or {})
            .get("beats") or {}
        ).get(sb_id) or {}
        if sb_beat.get("magic_manual_path"):
            beat["magic_manual_path"] = sb_beat["magic_manual_path"]
        if sb_beat.get("magic_path_authored_against"):
            beat["magic_path_authored_against"] = sb_beat["magic_path_authored_against"]

    return {
        "bg_beat_id": bg_beat_id,
        "storyboard_beat_id": sb_id,
        "source_path": str(source_path.resolve()),
        "dest_path": str(dest.resolve()),
        "size_bytes": dest.stat().st_size,
    }


BG_SESSION_DISK_ENRICH_V1 = "BG_SESSION_DISK_ENRICH_V1"


def materialize_o3_disk_enrich_fields(
    beat: dict,
    event_dir: str | Path,
    *,
    disk_paths: list[Path] | None = None,
) -> dict:
    """Scan disk once; return enrich fields to persist on beat or merge into API out."""
    beat_id = str(beat.get("beat_id") or "").strip()
    if not beat_id:
        return {}
    event_dir = Path(event_dir)
    if disk_paths is None:
        disk_paths = list_o3_element_delivery_paths_on_disk(beat_id, event_dir)
    option_paths = {
        str(o.get("video_path") or "")
        for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict)
    }
    fields: dict = {
        "kling_o3_pinned_preserve": has_pinned_kling_o3_preserve(beat_id, event_dir),
        "kling_o3_clips_dir": str(kling_o3_clips_dir(event_dir)),
        "kling_o3_disk_delivery_count": len(disk_paths),
        "kling_o3_element_delivery_count": count_o3_element_delivery_paths(disk_paths),
        "kling_o3_orphan_delivery_count": sum(
            1 for p in disk_paths if str(p.resolve()) not in option_paths
        ),
        "kling_o3_disk_enrich_at": datetime.now(timezone.utc).isoformat(),
    }
    o3_video = (beat.get("kling_o3_video_path") or "").strip()
    if o3_video:
        fields["kling_o3_video_path_exists"] = _kling_o3_video_path_exists(o3_video)
    options = beat.get("kling_o3_options")
    if isinstance(options, list):
        enriched_options: list[dict] = []
        for opt in options:
            if not isinstance(opt, dict):
                enriched_options.append(opt)
                continue
            opt_copy = dict(opt)
            vp = (opt_copy.get("video_path") or "").strip()
            if vp:
                opt_copy["video_path_exists"] = _kling_o3_video_path_exists(vp)
                _sync_o3_option_gen_label(opt_copy)
            enriched_options.append(opt_copy)
        fields["kling_o3_options"] = enriched_options
    magic_name = beat.get("magic_video_path")
    if magic_name:
        magic_path = Path(magic_name)
        if not magic_path.is_absolute():
            magic_path = event_dir / magic_name
        fields["magic_video_path_exists"] = magic_path.is_file()
    still_name = beat.get("magic_still_path")
    if still_name:
        still_path = Path(still_name)
        if not still_path.is_absolute():
            still_path = event_dir / still_name
        fields["magic_still_path_exists"] = still_path.is_file()
    ap = resolve_bg_beat_tts_audio_path(event_dir, beat)
    fields["audio_file_exists"] = ap is not None
    if ap is not None and not (beat.get("audio_file") or "").strip():
        fields["audio_file"] = ap.name
    return fields


def persist_o3_disk_enrich_on_beat(
    beat: dict,
    event_dir: str | Path,
    *,
    disk_paths: list[Path] | None = None,
) -> bool:
    """Write disk-derived enrich fields onto beat (SQLite authority)."""
    fields = materialize_o3_disk_enrich_fields(beat, event_dir, disk_paths=disk_paths)
    if not fields:
        return False
    changed = False
    for key, val in fields.items():
        if key == "kling_o3_options":
            beat["kling_o3_options"] = val
            changed = True
            continue
        if beat.get(key) != val:
            beat[key] = val
            changed = True
    return changed


def enrich_beat_kling_o3_pinned(
    beat: dict,
    event_dir: str | Path,
    *,
    session_read: bool = False,
) -> dict:
    """Return beat copy with transient O3 disk/enrich fields for API responses.

    ``session_read=True`` (session-state GET): no Dropbox glob/stat — uses persisted
    beat fields from ``persist_o3_disk_enrich_on_beat`` / gallery repair.
    """
    out = dict(beat)
    raw_opts = beat.get("kling_o3_options")
    if isinstance(raw_opts, list):
        out["kling_o3_options"] = [
            dict(o) if isinstance(o, dict) else o for o in raw_opts
        ]
    beat_id = beat.get("beat_id")
    if beat_id:
        if not session_read:
            refresh_o3_ui_slot_layout(out)
        if session_read:
            if not out.get("kling_o3_clips_dir"):
                out["kling_o3_clips_dir"] = str(Path(event_dir) / "kling_o3_clips")
        else:
            disk_fields = materialize_o3_disk_enrich_fields(out, event_dir)
            for key, val in disk_fields.items():
                if key == "kling_o3_options":
                    out["kling_o3_options"] = val
                else:
                    out[key] = val
            out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out, event_dir)
            enrich_beat_magic_video_source_path(out, event_dir)
            return out
    if not session_read:
        o3_video = (beat.get("kling_o3_video_path") or "").strip()
        if o3_video:
            out["kling_o3_video_path_exists"] = _kling_o3_video_path_exists(o3_video)
        options = out.get("kling_o3_options")
        if isinstance(options, list):
            enriched_options: list[dict] = []
            for opt in options:
                if not isinstance(opt, dict):
                    enriched_options.append(opt)
                    continue
                opt_copy = dict(opt)
                vp = (opt_copy.get("video_path") or "").strip()
                if vp:
                    opt_copy["video_path_exists"] = _kling_o3_video_path_exists(vp)
                enriched_options.append(opt_copy)
            out["kling_o3_options"] = enriched_options
        magic_name = beat.get("magic_video_path")
        if magic_name:
            magic_path = Path(magic_name)
            if not magic_path.is_absolute():
                magic_path = Path(event_dir) / magic_name
            out["magic_video_path_exists"] = magic_path.is_file()
        still_name = beat.get("magic_still_path")
        if still_name:
            still_path = Path(still_name)
            if not still_path.is_absolute():
                still_path = Path(event_dir) / still_name
            out["magic_still_path_exists"] = still_path.is_file()
        ap = resolve_bg_beat_tts_audio_path(event_dir, beat)
        out["audio_file_exists"] = ap is not None
        if ap is not None and not (out.get("audio_file") or "").strip():
            out["audio_file"] = ap.name
    if session_read and not out.get("magic_canonical_kind"):
        out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out, None)
    elif not session_read:
        out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out, event_dir)
    enrich_beat_magic_video_source_path(out, event_dir)
    return out


def enrich_beats_kling_o3_pinned(beats: list[dict], event_dir: str | Path) -> list[dict]:
    scoped = Path(event_dir)
    return [
        enrich_beat_kling_o3_pinned(
            b,
            resolve_beat_disk_event_dir(str(b.get("beat_id") or ""), scoped),
        )
        for b in beats
    ]


def pin_kling_o3_beat(beat: dict, event_dir: str | Path) -> tuple[bool, str | None]:
    """Manual preserve — one pinned slot per beat, overwritten on re-pin."""
    beat_id = beat.get("beat_id")
    if not beat_id:
        return False, "missing_beat_id"
    if not beat.get("kling_o3_video_path"):
        return False, "no_video"
    dest_dir = kling_o3_pinned_dir(event_dir)
    if not _copy_kling_o3_beat_clip_to_dir(beat, dest_dir):
        return False, "copy_failed"
    slot_json = dest_dir / f"{beat_id}.json"
    try:
        meta = json.loads(slot_json.read_text())
    except (OSError, json.JSONDecodeError):
        meta = _strip_beat_for_preserve_json(beat)
    meta["preserve_reason"] = "manual_pin"
    meta["preserved_at"] = datetime.now(timezone.utc).isoformat()
    slot_json.write_text(json.dumps(meta, indent=2))
    return True, None


def auto_pin_approved_kling_o3_delivery(beat: dict, event_dir: str | Path) -> bool:
    """Pin the current stitch-ready delivery so a later redo cannot lose the only good copy."""
    from kling_stitch_readiness import beat_kling_stitch_export_ready  # noqa: PLC0415

    if not beat_kling_stitch_export_ready(beat, event_dir):
        return False
    ok, _err = pin_kling_o3_beat(beat, event_dir)
    return ok


def restore_pinned_kling_o3_beat(
    beat_id: str,
    event_dir: str | Path,
    sidecar: dict,
) -> tuple[bool, str | None, dict | None]:
    """Restore sidecar + clip from pinned slot; delete superseded generation file."""
    pinned_dir = kling_o3_pinned_dir(event_dir)
    pinned_mp4 = pinned_dir / f"{beat_id}.mp4"
    pinned_json = pinned_dir / f"{beat_id}.json"
    if not pinned_mp4.is_file() or not pinned_json.is_file():
        return False, "no_pinned", None
    try:
        pinned = json.loads(pinned_json.read_text())
    except (OSError, json.JSONDecodeError):
        return False, "pinned_meta_invalid", None

    _, beat = find_beat(sidecar, beat_id)
    if not beat:
        return False, "beat_not_found", None

    current_path = beat.get("kling_o3_video_path")
    if current_path:
        cp = Path(current_path)
        pinned_target = pinned.get("kling_o3_video_path") or pinned.get("preserved_clip")
        same_clip = (
            pinned_target
            and cp.is_file()
            and str(cp.resolve()) == str(Path(pinned_target).resolve())
        )
        if cp.is_file() and not same_clip:
            try:
                cp.unlink()
            except OSError:
                pass
            meta_sibling = cp.with_suffix(".json")
            if meta_sibling.is_file():
                try:
                    meta_sibling.unlink()
                except OSError:
                    pass

    pinned_gen = int(pinned.get("kling_o3_generation") or 0)
    restore_path = kling_o3_clips_dir(event_dir) / f"{beat_id}_g{pinned_gen}.mp4"
    shutil.copy2(pinned_mp4, restore_path)
    resolved = str(restore_path.resolve())

    for key in _KLING_O3_PIN_RESTORE_FIELDS:
        if key in pinned:
            beat[key] = pinned[key]
    beat["kling_o3_video_path"] = resolved
    beat.pop("kling_o3_error", None)

    return True, None, enrich_beat_kling_o3_pinned(beat, event_dir)


def _kling_o3_gen_from_video_path(video_path: str | None) -> int | None:
    """Parse generation counter from O3 clip filenames (legacy and Element delivery)."""
    if not video_path:
        return None
    name = Path(video_path).name
    m = re.search(r"_g(\d+)(?:_(?:element|kling)|\.mp4)", name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"_g(\d+)\.mp4$", name, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _kling_o3_video_path_exists(video_path: str | None) -> bool:
    if not video_path:
        return False
    try:
        return Path(video_path).is_file()
    except OSError:
        return False


def heal_kling_o3_stitch_export_status(beat: dict) -> bool:
    """Deprecated alias — use ``sync_kling_stitch_status_from_active_clip``."""
    from kling_stitch_readiness import sync_kling_stitch_status_from_active_clip  # noqa: PLC0415

    return sync_kling_stitch_status_from_active_clip(beat)


def reconcile_kling_o3_beat(beat: dict, event_dir: str | Path) -> bool:
    """Sync sidecar Kling status with clips on disk; clear orphaned in-flight flags.

    Returns True if ``beat`` was mutated.
    """
    beat_id = beat.get("beat_id")
    if not beat_id:
        return False
    gen = int(beat.get("kling_o3_generation") or 0)
    clip_path = kling_o3_clips_dir(event_dir) / f"{beat_id}_g{gen}.mp4"
    status = beat.get("kling_o3_status") or "draft"
    stored_raw = (beat.get("kling_o3_video_path") or "").strip()
    stored_path = Path(stored_raw) if stored_raw else None

    # Element / delivery clips — never drop an on-disk approved path because gen
    # ran ahead on a failed redo.
    if stored_path and stored_path.is_file():
        changed = False
        if beat.get("kling_o3_video_path") != str(stored_path.resolve()):
            beat["kling_o3_video_path"] = str(stored_path.resolve())
            changed = True
        path_gen = _kling_o3_gen_from_video_path(stored_raw)
        if path_gen is not None and gen != path_gen:
            if beat.get("status") == "approved" or status in ("approved", "completed"):
                beat["kling_o3_generation"] = path_gen
                changed = True
        from kling_stitch_readiness import sync_kling_stitch_status_from_active_clip  # noqa: PLC0415

        if sync_kling_stitch_status_from_active_clip(beat):
            changed = True
        return changed

    if clip_path.is_file():
        resolved = str(clip_path.resolve())
        changed = False
        if beat.get("kling_o3_video_path") != resolved:
            beat["kling_o3_video_path"] = resolved
            changed = True
        from kling_stitch_readiness import sync_kling_stitch_status_from_active_clip  # noqa: PLC0415

        if sync_kling_stitch_status_from_active_clip(beat):
            changed = True
        return changed

    changed = False
    if status in ("queued", "processing"):
        # Live WaveSpeed work — do not downgrade on session-state refresh.
        if status == "processing" and beat.get("kling_o3_task_id"):
            pass
        elif status == "queued" and beat.get("kling_o3_task_id"):
            pass
        else:
            beat["kling_o3_status"] = "draft"
            beat.pop("kling_o3_error", None)
            changed = True

    # Redo increments generation before the new clip lands. Only clear the path
    # when the referenced file is actually missing — not while g{N-1} still exists.
    path_gen = _kling_o3_gen_from_video_path(stored_raw)
    if stored_raw and not _kling_o3_video_path_exists(stored_raw):
        beat.pop("kling_o3_video_path", None)
        beat.pop("kling_o3_completed_at", None)
        beat.pop("kling_o3_task_id", None)
        if beat.get("status") == "video_ready":
            beat["status"] = "draft"
        changed = True
    elif path_gen is not None and path_gen < gen and not stored_raw:
        beat.pop("kling_o3_completed_at", None)
        beat.pop("kling_o3_task_id", None)
        changed = True
    from kling_stitch_readiness import sync_kling_stitch_status_from_active_clip  # noqa: PLC0415

    if sync_kling_stitch_status_from_active_clip(beat):
        changed = True
    return changed


def refresh_kling_o3_auto_duration(beat: dict) -> bool:
    """Recompute planned submit duration from the prompt when not manually locked."""
    if beat.get("pipeline") != "kling_o3_omni":
        return False
    if beat.get("kling_o3_duration_locked"):
        return False
    prompt = (beat.get("kling_o3_prompt") or "").strip()
    if not prompt:
        return False
    prepared = prepare_kling_o3_prompt_for_submit(beat, prompt)
    new_dur = resolve_kling_o3_submit_duration(beat, prepared)
    if beat.get("kling_o3_duration") == new_dur:
        return False
    beat["kling_o3_duration"] = new_dur
    return True


def refresh_kling_o3_prepared_prompt(beat: dict) -> bool:
    """No-op — do not overwrite user prompt box on reconcile (preview API shows prep instead)."""
    return False


def reconcile_kling_o3_sidecar(sidecar: dict, event_dir: str | Path) -> int:
    """Reconcile all beats in the sidecar against ``event_dir/kling_o3_clips/``.

    Returns the number of beats updated.
    """
    updated = upgrade_legacy_bg_beats_to_kling_o3(sidecar)
    arcs = sidecar.get("arcs") or {}
    for arc in arcs.values():
        for seg in (arc.get("segments") or {}).values():
            for beat in seg.get("beats") or []:
                if beat.get("pipeline") != "kling_o3_omni":
                    continue
                beat_event_dir = resolve_beat_disk_event_dir(
                    str(beat.get("beat_id") or ""), event_dir,
                )
                if reconcile_o3_disk_deliveries_for_beat(beat, beat_event_dir):
                    updated += 1
                if reconcile_kling_o3_beat(beat, beat_event_dir):
                    updated += 1
                if align_beat_reference_to_element(beat):
                    updated += 1
                if refresh_kling_o3_prepared_prompt(beat):
                    updated += 1
                if refresh_kling_o3_auto_duration(beat):
                    updated += 1
    return updated


_PHASE_TO_STITCH_SLOT: dict[str, str] = {
    "pre": "intro",
    "intro": "intro",
    "post": "resolution",
    "resolution": "resolution",
    "phase_a": "phase_a",
    "phase_b": "phase_b",
}

_VIDEO_ROLE_TO_STITCH_SLOT: dict[str, str] = {
    "intro": "intro",
    "resolution": "resolution",
    "phase_a": "phase_a",
    "phase_b": "phase_b",
}


def stitch_slot_for_bg_phase(phase: str) -> str | None:
    return _PHASE_TO_STITCH_SLOT.get(str(phase).lower())


def stitch_slot_for_video_role(video_role: str) -> str | None:
    """Map header VideoSelector role → Stitcher slot key."""
    return _VIDEO_ROLE_TO_STITCH_SLOT.get(str(video_role or "").lower())


def resolve_bg_export_stitch_slot(*, phase: str, video_role: str | None = None) -> str | None:
    """Prefer explicit BG segment phase; fall back to active video role (intro / phase_a / …)."""
    slot = stitch_slot_for_bg_phase(phase)
    if slot:
        return slot
    if video_role:
        return stitch_slot_for_video_role(video_role)
    return None


# KLING_EXPORT_AUDIO_JOIN_V1 — PCM mono + micro fade at hard beat joins (de-click).
KLING_EXPORT_AUDIO_JOIN_V1 = "KLING_EXPORT_AUDIO_JOIN_V1"
KLING_EXPORT_AUDIO_JOIN_FADE_MS = 25


def _ffprobe_audio_lane_duration(path: Path, *, has_audio: bool) -> float:
    """Audio stream duration for join fades — format duration misaligns A/V on Kling clips."""
    if not has_audio:
        return _ffprobe_duration(path)
    fs = _ffmpeg_stitch_module()
    audio_s = fs.ffprobe_stream_duration_s(path, "a")
    if audio_s > 0:
        return audio_s
    return _ffprobe_duration(path)


def _kling_export_audio_lane_filter(
    input_label: str,
    out_label: str,
    dur_s: float,
    *,
    is_first: bool,
    is_last: bool,
) -> str:
    """Decode to PCM mono; micro fade in/out at hard-cut beat boundaries."""
    join_fade_s = KLING_EXPORT_AUDIO_JOIN_FADE_MS / 1000.0
    chain = (
        f"{input_label}aresample=44100,aformat=sample_fmts=s16:channel_layouts=mono"
    )
    if not is_first and join_fade_s > 0:
        chain += f",afade=t=in:st=0:d={join_fade_s:.6f}"
    if not is_last and dur_s > join_fade_s * 2 and join_fade_s > 0:
        chain += (
            f",afade=t=out:st={dur_s - join_fade_s:.6f}:d={join_fade_s:.6f}"
        )
    return f"{chain}[{out_label}]"


def _ffmpeg_concat_kling_clips_reencode(clip_paths: list[Path], dest: Path) -> None:
    """Concat Kling clips with re-encode — ``-c copy`` causes A/V desync across mixed encodes."""
    import shutil

    if not clip_paths:
        raise ValueError("no clips to concat")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if len(clip_paths) == 1:
        copy_file_durable(clip_paths[0], dest)
        return

    fs = _ffmpeg_stitch_module()
    has_audio = fs._has_audio_stream

    inputs: list[str] = []
    for p in clip_paths:
        inputs.extend(["-i", str(p.resolve())])
    n = len(clip_paths)
    durations = [
        _ffprobe_audio_lane_duration(p, has_audio=has_audio(p))
        for p in clip_paths
    ]

    # Magic-on-still MP4s (and some Kling clips) have no audio stream. Inject
    # trimmed anullsrc per silent clip so concat filter always sees [aN] labels.
    silent_lavfi_indices: dict[int, int] = {}
    lavfi_input_idx = n
    for i, p in enumerate(clip_paths):
        if has_audio(p):
            continue
        dur = max(durations[i], 0.04)
        inputs.extend([
            "-f", "lavfi", "-i",
            f"anullsrc=r=44100:cl=mono,atrim=duration={dur:.6f}",
        ])
        silent_lavfi_indices[i] = lavfi_input_idx
        lavfi_input_idx += 1

    v_parts = [
        (
            f"[{i}:v:0]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24[v{i}]"
        )
        for i in range(n)
    ]
    a_parts: list[str] = []
    for i in range(n):
        src = silent_lavfi_indices.get(i, i)
        a_parts.append(
            _kling_export_audio_lane_filter(
                f"[{src}:a:0]",
                f"a{i}",
                durations[i],
                is_first=(i == 0),
                is_last=(i == n - 1),
            )
        )
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
    fc = ";".join(v_parts + a_parts) + f";{concat_in}concat=n={n}:v=1:a=1[outv][outa]"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", fc,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(dest),
    ]
    run_ffmpeg_to_dest(
        cmd, dest, timeout=600, error_prefix="ffmpeg concat reencode failed",
    )


_TOOLS_DIR = Path(__file__).resolve().parent


def _ffmpeg_stitch_module():
    """Lazy import — ffmpeg_stitch lives under Production/tools/credentials_lib/."""
    libdir = str(_TOOLS_DIR / "credentials_lib")
    if libdir not in sys.path:
        sys.path.insert(0, libdir)
    import ffmpeg_stitch  # noqa: WPS433

    return ffmpeg_stitch


def _intro_export_pair_fades(
    num_clips: int,
    pre_penultimate_fade_ms: int,
    final_fade_ms: int,
) -> list[int]:
    """Intro export fades: slow dissolve into penultimate + longer dissolve into mirror tail."""
    if num_clips < 2:
        return []
    fades = [0] * (num_clips - 1)
    if num_clips >= 3 and pre_penultimate_fade_ms > 0:
        fades[num_clips - 3] = pre_penultimate_fade_ms
    if final_fade_ms > 0:
        fades[num_clips - 2] = final_fade_ms
    return fades if any(f > 0 for f in fades) else []


def _ffmpeg_concat_kling_clips_with_pair_fades(
    clip_paths: list[Path],
    dest: Path,
    pair_fades: list[int],
    scratch_dir: Path,
) -> None:
    """Concat with fade-through-black at selected boundaries (no A/V overlap).

    Each clip fades to black at its tail and/or from black at its head; clips
    are hard-joined — unlike xfade dissolve, audio and video never blend across
    beats. Video fade is a **short tail/head** (manifest ``fade_out_video_tail_ms`` /
    ``fade_in_video_head_ms``, default ~450ms) so dialogue stays fully lit until
    the last word; audio stays full level until the hard cut (``fade_audio=False``).
    """
    import shutil

    fs = _ffmpeg_stitch_module()
    expand_clips_with_black_pause_boundaries = fs.expand_clips_with_black_pause_boundaries

    if not clip_paths:
        raise ValueError("no clips to concat")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], dest)
        return
    if not pair_fades or all(f <= 0 for f in pair_fades):
        _ffmpeg_concat_kling_clips_reencode(clip_paths, dest)
        return

    body_dir = scratch_dir / "fade_black"
    body_dir.mkdir(parents=True, exist_ok=True)
    visual_out_ms = _load_intro_fade_out_video_tail_ms()
    visual_in_ms = _load_intro_fade_in_video_head_ms()
    parts = expand_clips_with_black_pause_boundaries(
        clip_paths,
        pair_fades,
        body_dir,
        visual_out_ms=visual_out_ms,
        visual_in_ms=visual_in_ms,
        fade_audio=False,
    )

    _ffmpeg_concat_kling_clips_reencode(parts, dest)


def _boundaries_for_pair_fade_concat(
    beats: list[dict],
    clip_paths: list[Path],
    pair_fades: list[int],
) -> list[dict]:
    """Timeline markers — beat bodies only; black pauses sit between markers."""
    fs = _ffmpeg_stitch_module()
    allocate_pair_fade_budget = fs.allocate_pair_fade_budget
    cursor_ms = 0
    out: list[dict] = []
    visual_out_ms = _load_intro_fade_out_video_tail_ms()
    visual_in_ms = _load_intro_fade_in_video_head_ms()
    for i, (beat, clip) in enumerate(zip(beats, clip_paths)):
        dur_ms = int(round(_ffprobe_duration(clip) * 1000))
        out.append({
            "beat_id": beat["beat_id"],
            "start_ms": cursor_ms,
            "end_ms": cursor_ms + dur_ms,
            "duration_ms": dur_ms,
        })
        cursor_ms += dur_ms
        if i < len(pair_fades) and pair_fades[i] > 0:
            _, _, black_ms = allocate_pair_fade_budget(
                pair_fades[i],
                visual_out_ms=visual_out_ms,
                visual_in_ms=visual_in_ms,
            )
            cursor_ms += black_ms
    return out


def resolve_segment_stitch_export_clip_paths(
    beats: list[dict],
    event_dir: str | Path,
    *,
    phase: str | None = None,
    event_name: str | None = None,
    event_id: str | None = None,
    progress_cb=None,
) -> tuple[list[Path], Path]:
    """Clip paths in beat order — must match ``concat_kling_o3_approved_beats`` inputs."""
    if not beats:
        raise ValueError("no beats to resolve")
    event_dir = Path(event_dir)
    out_dir = event_dir / "assembled"
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch_dir = out_dir / "_kling_o3_trim_scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    canonical_tail: Path | None = None
    phase_l = str(phase or "").lower()
    rotation_key = event_id or event_name
    if phase_l in ("pre", "intro") and rotation_key:
        try:
            from teleport_intro_canonical import resolve_canonical_tail_for_event
            from lib.paths import dropbox_root

            tail_guide = None
            if beats:
                tail_guide = (beats[-1].get("speaker") or "").strip() or None
            canonical_tail = resolve_canonical_tail_for_event(
                str(rotation_key),
                dropbox_root(),
                phase=phase,
                event_id=event_id,
                guide=tail_guide,
            )
        except Exception:
            canonical_tail = None

    clip_paths: list[Path] = []
    beat_total = len(beats)
    for i, beat in enumerate(beats):
        if progress_cb:
            progress_cb(i + 1, beat_total, str(beat.get("beat_id") or ""))
        is_last = i == len(beats) - 1
        if is_last and canonical_tail is not None:
            clip_paths.append(canonical_tail.resolve())
        else:
            raw_clip = materialize_beat_export_clip_with_retry(
                beat,
                event_dir,
                scratch_dir,
                event_id=event_id,
            )
            from server_handlers.speech_loudnorm import apply_speech_loudnorm_export_beat_clip  # noqa: PLC0415

            clip_paths.append(
                apply_speech_loudnorm_export_beat_clip(
                    raw_clip,
                    beat_id=str(beat.get("beat_id") or f"beat_{i}"),
                    scratch_dir=scratch_dir,
                ),
            )
    return clip_paths, scratch_dir


def concat_kling_o3_approved_beats(
    beats: list[dict],
    event_dir: str | Path,
    slot_key: str,
    *,
    phase: str | None = None,
    event_name: str | None = None,
    event_id: str | None = None,
    progress_cb=None,
) -> tuple[Path, list[dict], float]:
    """ffmpeg-concat approved Kling O3 clips in beat list order.

    For intro (phase pre/intro), the **last** beat clip is replaced with the
    canonical teleport tail (speak + whiteout) when canonical_registry has a
    built variant. Intro exports apply **fade-through-black** on the last two
    boundaries only (manifest ``pre_penultimate_pair_fade_ms`` and
    ``final_pair_fade_ms``): each clip fades out/in independently with hard
    cuts — no crossfade overlap. All earlier beat boundaries remain hard cuts.

    Returns (assembled_mp4_path, beat_boundaries, total_duration_s).
    """
    import subprocess

    if not beats:
        raise ValueError("no beats to export")
    migrate_segment_o3_trims_for_export(beats)
    out_dir = Path(event_dir) / "assembled"
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_paths, scratch_dir = resolve_segment_stitch_export_clip_paths(
        beats,
        event_dir,
        phase=phase,
        event_name=event_name,
        event_id=event_id,
        progress_cb=progress_cb,
    )
    fs = _ffmpeg_stitch_module()
    fs.assert_stitch_export_clips_av_aligned(clip_paths)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{slot_key}_kling_o3_{ts}.mp4"
    pair_fades: list[int] = []
    phase_l = str(phase or "").lower()
    if phase_l in ("pre", "intro") and len(clip_paths) >= 2:
        pair_fades = _intro_export_pair_fades(
            len(clip_paths),
            _load_intro_pre_penultimate_pair_fade_ms(),
            _load_intro_final_pair_fade_ms(),
        )
    if pair_fades and any(f > 0 for f in pair_fades):
        try:
            _ffmpeg_concat_kling_clips_with_pair_fades(
                clip_paths, out_path, pair_fades, scratch_dir,
            )
        except ImportError as exc:
            raise RuntimeError(
                f"intro xfade concat requires ffmpeg_stitch: {exc}",
            ) from exc
    else:
        _ffmpeg_concat_kling_clips_reencode(clip_paths, out_path)
    if not _ffprobe_ok(out_path):
        raise RuntimeError(f"assembled clip failed ffprobe: {out_path}")

    from video_delivery import ensure_mp4_playback_timestamps  # noqa: PLC0415

    ensure_mp4_playback_timestamps(out_path)

    boundaries = _boundaries_for_pair_fade_concat(beats, clip_paths, pair_fades)
    total_s = _ffprobe_duration(out_path)
    return out_path, boundaries, total_s
