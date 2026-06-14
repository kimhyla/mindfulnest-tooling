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

import base64
import concurrent.futures
import contextlib
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
from typing import Any

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
BG_STILLS_DIR = os.path.join(_PROD_DIR, "beat_generator_stills")


def init_bg_paths(event_dir) -> None:
    """Rebind every module-level path constant from the runtime event_dir.

    Called by run_server() at startup. Replaces the original PR #73 manual
    override of just BG_STILLS_DIR + BG_SIDECAR_PATH with a complete pass
    over all 11 path constants + the two character-pose dicts (which were
    baked at module-import time).

    See Production/lib/paths.py for the canonical resolver and audit
    finding C1-5..C1-9 for the bugs this closes.
    """
    global _TOOLS_DIR, _PROD_DIR, _PROJECT_DIR, _SKELETON_BASE
    global BG_SIDECAR_PATH, BG_STILLS_DIR
    global _PROD_CHARS, _CREATURE_REFS, _CREATURE_REFS_BY_EMOTION
    global _CANON_BASE, _LOCAL_STILLS_DIR

    # Import here (not at module top) so beat_generator.py can be imported
    # standalone for tests without requiring lib/paths to be on sys.path.
    import sys as _sys
    _lib_parent = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    if _lib_parent not in _sys.path:
        _sys.path.insert(0, _lib_parent)
    from Production.lib.paths import bg_paths as _bg_paths, character_pose_paths as _cpp

    bp = _bg_paths(event_dir)
    _PROD_DIR = str(bp.prod_root)
    _PROJECT_DIR = str(bp.project_root)
    _SKELETON_BASE = str(bp.skeleton_base)
    BG_SIDECAR_PATH = str(bp.sidecar_path)
    BG_STILLS_DIR = str(bp.stills_dir)
    _PROD_CHARS = str(bp.project_root)  # poses live at <project_root>/Production/<Char>/poses/
    _CANON_BASE = str(bp.canon_base)
    _LOCAL_STILLS_DIR = Path(bp.local_stills_dir)

    try:
        from tools import kling_character_registry as _reg

        _reg.set_prod_root(_PROD_DIR)
    except Exception:
        pass

    # Rebuild the two character-pose dicts that were baked at import time
    # with the (now stale) tooling-anchored _PROD_CHARS. Keys + per-emotion
    # structure preserved exactly per beat_generator.py:127-172.
    _CREATURE_REFS = _cpp(event_dir)

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
    "Lorelai": "lemur archaeologist with round glasses and overstuffed scholar backpack "
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
    "Lorelai": "cartoon lemur archaeologist with bright eyes, soft fur, and scholarly glasses, Pixar 3D animated style",
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


def read_sidecar():
    path = os.path.abspath(BG_SIDECAR_PATH)
    if not os.path.exists(path):
        return _EMPTY_SIDECAR()
    last_err: OSError | None = None
    for attempt in range(5):
        try:
            with _sidecar_lock:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except OSError as exc:
            last_err = exc
            if exc.errno not in (11, 35) or attempt >= 4:
                raise
            time.sleep(0.15 * (attempt + 1))
    if last_err:
        raise last_err
    return _EMPTY_SIDECAR()


def write_sidecar(data):
    """Atomic write (os.replace per LD-134). RLock-guarded."""
    path = os.path.abspath(BG_SIDECAR_PATH)
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()
    with _sidecar_lock:
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        last_err: OSError | None = None
        for attempt in range(5):
            try:
                with tempfile.NamedTemporaryFile(
                    "w", dir=d, delete=False, suffix=".tmp", encoding="utf-8",
                ) as f:
                    json.dump(data, f, indent=2)
                    tmp = f.name
                os.replace(tmp, path)
                return
            except OSError as exc:
                last_err = exc
                if exc.errno not in (11, 35) or attempt >= 4:
                    raise
                time.sleep(0.15 * (attempt + 1))
        if last_err:
            raise last_err


@contextlib.contextmanager
def sidecar_file_lock():
    """Cross-process lock for Beat Gen sidecar read/modify/write cycles.

    ``_sidecar_lock`` protects threads inside one Python process only. O3 voice
    subprocesses and the storyboard server must coordinate on the same lock file,
    otherwise whole-file writes can erase fields from a concurrent beat job.
    """
    path = os.path.abspath(BG_SIDECAR_PATH)
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def read_sidecar_locked():
    with sidecar_file_lock():
        return read_sidecar()


def write_sidecar_atomic_locked(data):
    with sidecar_file_lock():
        write_sidecar(data)


def update_beat_locked(beat_id, mutator, expected_attempt_id=None):
    """Atomically patch one beat under the cross-process sidecar lock.

    ``mutator(beat, sidecar)`` may mutate the target beat in place. If
    ``expected_attempt_id`` is set and the current beat has a different
    ``kling_o3_voice_fix_attempt_id``, the update is skipped and ``(False, beat)``
    is returned so stale subprocesses cannot overwrite newer attempts.
    """
    with sidecar_file_lock():
        sidecar = read_sidecar()
        _seg, beat = find_beat(sidecar, beat_id)
        if not beat:
            return False, None
        if expected_attempt_id is not None and beat.get("kling_o3_voice_fix_attempt_id") != expected_attempt_id:
            return False, beat
        mutator(beat, sidecar)
        write_sidecar(sidecar)
        return True, beat


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

# Sidecar merge + stitch export durability (LD Kling O3 trim persist).
# Trims saved via Apply Trim MUST survive re-extract/import and MUST be applied
# on Send to Stitcher via _kling_o3_export_clip_path → materialize_kling_o3_trimmed_clip.
SIDECAR_MERGE_PRESERVE_FIELDS: tuple[str, ...] = (
    "flux_options", "accepted_image_key", "accepted_library_ref", "status",
    "kling_o3_prompt", "kling_o3_duration", "kling_o3_duration_locked",
    "kling_o3_status", "kling_o3_video_path", "kling_o3_generation",
    "kling_o3_options", "kling_o3_replace_slot_index", "kling_o3_selected_option_key",
    "kling_o3_task_id", "kling_o3_trim_start", "kling_o3_trim_back",
    "kling_o3_actual_duration_s", "kling_o3_completed_at",
    "reference_image", "bg_ref_image", "reference_image_locked",
    "bg_ref_image_locked", "start_frame_image_locked", "end_frame_image_locked",
    "element_char_ref_ok", "element_char_ref_error",
    "pipeline",
    "intro_beat_role", "canonical_intro_tail",
    "magic_manual_path", "magic_video_path", "magic_path_authored_against",
    "storyboard_clip_import",
    "start_frame_image", "end_frame_image", "kling_o3_mode",
    "magic_still_path",
)

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
    if not beat.get("kling_o3_duration_locked"):
        beat["kling_o3_duration"] = resolve_kling_o3_submit_duration(
            beat, beat.get("kling_o3_prompt") or "",
        )
    beat.setdefault("kling_o3_status", "draft")


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
    if _has_populated_intro_mirror_beat(beat):
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
    beat["kling_o3_status"] = "approved"
    beat["canonical_intro_tail"] = True
    beat["status"] = "video_ready"
    assign_kling_o3_option_to_slot(
        beat,
        0,
        video_path=tail_str,
        label="Canonical intro tail",
        source="canonical_intro_tail",
        now=now,
    )
    return True


def merge_incoming_segment_beats(
    existing_beats: list[dict],
    incoming_beats: list[dict],
    *,
    preserve_fields: tuple[str, ...] = SIDECAR_MERGE_PRESERVE_FIELDS,
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
            for field in preserve_fields:
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
_EVENT_HEADER = _EVENT_HEADER_H2
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


def _collect_event_blocks(text: str) -> list[dict]:
    """Collect event blocks from skeleton text (Arc 1 ## headers + Arc 2 underline)."""
    markers: list[tuple[int, str, str]] = []
    for m in _EVENT_HEADER_H2.finditer(text):
        markers.append((m.start(), str(m.group(1)), m.group(2).strip()))
    for m in _EVENT_HEADER_UNDERLINE.finditer(text):
        markers.append((m.start(), str(m.group(1)), m.group(2).strip()))
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
        event_type, clean_name = _parse_event_header_rest(rest)
        if _SKIP_TYPES.search(f"({event_type})"):
            continue
        event_text = text[pos:end]
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


def find_event_for_module(arc_number, m_number):
    """Find arc-event-id whose ## EVENT header title contains (M<m_number>).

    Returns the arc-event-id string (e.g., '1', '3b', '5') or None if not found.
    Per Arc 1 skeleton convention: play order differs from M-number; the M-marker
    in the event title is the canonical mapping (e.g., 'EVENT 5: ... (M3)' = M3).
    """
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None
    for m in _EVENT_HEADER.finditer(text):
        title = m.group(2) or ""
        m_marker = _M_NUMBER_IN_TITLE.search(title)
        if m_marker and int(m_marker.group(1)) == int(m_number):
            return str(m.group(1))
    return None


def extract_therapeutic_note(arc_number, m_number):
    """Extract the '### Therapeutic Note —' section for the event matching (M<m_number>).

    Returns the section text (from the Therapeutic Note H3 to the next H3 within
    the event block) as a stripped string. Empty string if not found.

    Used by Phase A and Phase B Suggest Script handlers to ground Claude prompts
    in the authored therapeutic content for the module.
    """
    path = _skeleton_path(arc_number)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return ""

    # Locate the event whose title carries the (M<m_number>) marker
    event_start = None
    for m in _EVENT_HEADER.finditer(text):
        title = m.group(2) or ""
        m_marker = _M_NUMBER_IN_TITLE.search(title)
        if m_marker and int(m_marker.group(1)) == int(m_number):
            event_start = m.start()
            break
    if event_start is None:
        return ""

    # Find event end (next ## EVENT header or EOF)
    next_event = _EVENT_HEADER.search(text, event_start + 1)
    event_end = next_event.start() if next_event else len(text)
    event_block = text[event_start:event_end]

    # Find the Therapeutic Note H3 within this event block
    therap_match = _SECTION_THERAP.search(event_block)
    if not therap_match:
        return ""

    # End of section = next H3 within the event block (or end of block)
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
    """Demote legacy still renders that were auto-marked approved on build."""
    if not beat_is_still_insert(beat):
        return False
    if str(beat.get("kling_o3_status") or "") != "approved":
        return False
    still_sources = ("still_insert_static_hold", "still_insert_ken_burns")
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


def _migrate_sidecar(sidecar: dict) -> dict:
    """Add new fields to old sidecars without breaking existing state."""
    sidecar.setdefault("groups", {})
    for arc_key, arc in sidecar.get("arcs", {}).items():
        for seg_key, seg in arc.get("segments", {}).items():
            for beat in seg.get("beats", []):
                beat.setdefault("animation_method", "kling")
                beat.setdefault("group_id", None)
                beat.setdefault("group_order", None)
                beat.setdefault("accepted_video_path", None)
                beat.setdefault("local_render_params", None)
                beat.setdefault("reference_image", None)
                beat.setdefault("bg_ref_image", None)
                normalize_still_insert_approval_status(beat)
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

    for arc in sidecar.get("arcs", {}).values():
        for seg in arc.get("segments", {}).values():
            for beat in seg.get("beats", []):
                humanize_kling_body_parts_on_beat(beat)
                from beat_extract_policy import heal_beat_kling_o3_prompt_event1_shape

                heal_beat_kling_o3_prompt_event1_shape(beat)
            draft = seg.get("beat_plan_draft") or {}
            for row in draft.get("beats_plan") or []:
                humanize_kling_body_parts_on_plan_row(row)
            for beat in seg.get("beats", []):
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
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True)
    return r.returncode == 0 and '"codec_name"' in r.stdout


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True)
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
    )
    preview_path = mc.render_preview()
    video_path = mc.render_video()
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
    total_frames = int(duration * fps)
    zoompan = (
        f"zoompan=z='{zoom_start}+({zoom_end}-{zoom_start})*on/{total_frames}'"
        f":x='iw*{pan_x_pct/100.0}':y='ih*{pan_y_pct/100.0}'"
        f":d={total_frames}:s=1280x720:fps={fps}"
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
    return None


def beat_is_still_insert(beat: dict) -> bool:
    return (
        str(beat.get("pipeline") or "") == "still_insert"
        or str(beat.get("beat_render_mode") or "") == "still_insert"
    )


_STILL_INSERT_SPOKEN_RE = re.compile(
    r"([A-Za-z][A-Za-z\s'-]*?)\s*(?:\[[^\]]+\])*\s*:\s*"
    r"(['\"])(.*?)\2",
    re.DOTALL,
)


def extract_still_insert_tts(beat: dict) -> dict | None:
    """Parse spoken line for still-insert TTS — quoted dialogue only, not scene setup."""
    from beat_extract_policy import extract_spoken_from_dialogue, infer_speaker_from_dialogue

    prompt = (beat.get("kling_o3_prompt") or "").strip()
    dialogue = (beat.get("dialogue_text") or "").strip()

    # Prompt-box is law: the editable textarea drives still-insert TTS when present.
    if prompt and not prompt.startswith("STILL INSERT"):
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
    if not speaker or speaker in ("Character", "[Stage Direction]"):
        speaker = infer_speaker_from_dialogue(source) or (beat.get("speaker") or "").strip()
    speaker = _canon_speaker(speaker) or speaker
    try:
        from tools import kling_character_registry as reg

        if not reg.is_speaker_voice_ready(speaker):
            beat_sp = _canon_speaker((beat.get("speaker") or "").strip()) or (
                beat.get("speaker") or ""
            ).strip()
            if beat_sp and reg.is_speaker_voice_ready(beat_sp):
                speaker = beat_sp
    except Exception:
        pass
    if not speaker or "stage direction" in speaker.lower():
        return None
    spoken = _kling_o3_normalize_spoken(spoken)
    spoken = re.sub(r"\[(?:pause|beat|breath|short pause)[^\]]*\]", " ", spoken, flags=re.I)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    if not spoken:
        return None
    return {"speaker": speaker, "text": spoken}


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
            beat, str(still), 20, 20, 1.0, 1.15, duration, out_path=silent_path,
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
    still_sources = ("still_insert_static_hold", "still_insert_ken_burns")
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
    return caps


# ---------------------------------------------------------------------------
# Kling O3 Omni — prompt builder + ref resolution (BEAT_GEN_KLING_O3_INTEGRATION v1)
# ---------------------------------------------------------------------------

KLING_O3_CAMERA_LOCK = (
    "Camera: static locked shot, no zoom, no dolly, no pan, no camera movement, "
    "stable eye-level medium shot."
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
) -> Path:
    """Write [trim_start, trim_end] window to ``dest``; returns ``dest``."""
    src = source_path or Path(beat.get("kling_o3_video_path") or "")
    if not src.is_file():
        raise FileNotFoundError(f"missing clip: {src}")
    trim_start, trim_end, raw_dur = resolve_kling_o3_trim_window(beat, video_path=src)
    if not kling_o3_trim_is_active(beat, raw_dur=raw_dur):
        shutil.copy2(src, dest)
        return dest

    duration = trim_end - trim_start
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".trim_tmp.mp4")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{trim_start:.3f}",
        "-i", str(src),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not tmp.is_file():
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg trim failed: {(r.stderr or '')[-500:]}")
    tmp.replace(dest)
    return dest


def _kling_o3_export_clip_path(
    beat: dict,
    event_dir: str | Path,
    scratch_dir: Path,
) -> Path:
    """Resolve clip path for stitch export (trimmed temp copy when trim active).

    Send to Stitcher MUST call this — never concat raw ``kling_o3_video_path``
    when ``kling_o3_trim_start`` / ``kling_o3_trim_back`` define a non-default window.
    """
    src = Path(beat.get("kling_o3_video_path") or "")
    if not src.is_file():
        raise FileNotFoundError(f"missing clip for {beat.get('beat_id')}: {src}")
    raw_dur = _ffprobe_duration(src)
    if not kling_o3_trim_is_active(beat, raw_dur=raw_dur):
        return src.resolve()
    beat_id = beat.get("beat_id") or "beat"
    gen = int(beat.get("kling_o3_generation") or 0)
    dest = scratch_dir / f"{beat_id}_g{gen}_export_trim.mp4"
    return materialize_kling_o3_trimmed_clip(beat, dest, source_path=src)


def resolve_beat_stitch_export_clip_path(
    beat: dict,
    event_dir: str | Path,
    scratch_dir: Path,
) -> Path:
    """Clip for segment concat — magic-on-video, magic-on-still (+TTS), or Kling."""
    event_dir = Path(event_dir)
    if beat.get("kling_o3_status") == "approved":
        mv = beat.get("magic_video_path")
        if mv:
            mp = Path(mv)
            if not mp.is_absolute():
                mp = event_dir / mv
            if mp.is_file():
                return mp.resolve()
    magic_still = beat_magic_still_clip_path(beat, event_dir)
    if magic_still is not None:
        if resolve_bg_beat_tts_audio_path(event_dir, beat):
            return materialize_magic_still_with_tts_export(beat, event_dir, scratch_dir)
        return magic_still
    mv = beat.get("magic_video_path")
    if mv:
        mp = Path(mv)
        if not mp.is_absolute():
            mp = event_dir / mv
        if mp.is_file():
            return mp.resolve()
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
        parts.append(chunk)
    spoken_raw = " ".join(parts).strip()
    if not spoken_raw:
        return ""
    spoken_raw = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", spoken_raw).strip()
    spoken_raw = re.sub(r"\s*\[[^\]]+\]\s*$", "", spoken_raw).strip()
    if len(spoken_raw) >= 2 and spoken_raw[0] == spoken_raw[-1] and spoken_raw[0] in "'\"":
        spoken_raw = spoken_raw[1:-1].strip()
    return _kling_o3_normalize_spoken(spoken_raw) if spoken_raw else ""


def _extract_spoken_dialogue_detail(prompt: str) -> tuple[str, str | None]:
    """Return (spoken, auto_merged_trailing) from a Kling O3 prompt box."""
    text = (prompt or "").strip()
    if not text:
        return "", None

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
        for m in re.finditer(r"'([^']{3,})'", text):
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


def _append_kling_o3_submit_locks(raw: str, *, speaker: str, spoken: str) -> str:
    """Append solo-shot, viewer, addressee, identity, and speech-only locks once."""
    out = normalize_kling_o3_identity_footer(raw.rstrip())
    lower = out.lower()
    if "only @image1 is visible" not in lower:
        out = f"{out}\n\n{KLING_O3_SOLO_SHOT_LOCK}"
    viewer = _kling_o3_viewer_address_clause(spoken)
    if viewer and "child viewer" not in lower:
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
    staging = (
        f"@Image1 ({speaker}) {action}. Scene from @Image2.\n\n"
        f"{KLING_O3_CAMERA_LOCK}"
    )
    if _is_chipper_intro_beat(beat):
        staging += f"\n\n{_kling_o3_chipper_intro_staging()}"
    return staging


def prepare_kling_o3_prompt_for_submit(beat: dict, prompt: str | None = None) -> str:
    """Prepare beat prompt immediately before WaveSpeed submit.

    Prompt-box is law: the textarea / ``beat['kling_o3_prompt']`` body is sent
    verbatim to Kling. Submit prep only appends missing safety locks (solo shot,
    identity, speech-only audio, viewer/addressee guards) — it never rewrites
    staging, camera, voice delivery, or quoted dialogue.

    Empty prompt returns "" (validation blocks submit).
    """
    raw = (prompt if prompt is not None else beat.get("kling_o3_prompt") or "").strip()
    if not raw:
        return ""

    speaker = beat.get("speaker") or "Character"
    from beat_extract_policy import humanize_kling_body_parts

    raw = humanize_kling_body_parts(raw, speaker=speaker)
    spoken = extract_spoken_dialogue_from_kling_prompt(raw)
    return _append_kling_o3_submit_locks(raw, speaker=speaker, spoken=spoken or "")


def apply_kling_o3_duration_floor(prompt: str, estimated: int) -> int:
    """Validated-recipe guard: long multi-chunk dialogue must not bucket to 5s."""
    spoken = _normalize_spoken_for_duration(
        extract_spoken_dialogue_from_kling_prompt(prompt) or "",
    )
    word_count = len(re.findall(r"\S+", spoken)) if spoken else 0
    pause_markers = len(re.findall(r"\[\s*(?:pause|break|silence)\s*\]", spoken, re.I))
    pause_markers += len(re.findall(r"\.{2,}|…+", spoken))
    if word_count >= 12 or pause_markers >= 2:
        return max(estimated, 8)
    return estimated


def _kling_o3_has_pre_speech_staging(prompt: str) -> bool:
    """True when prompt has substantial setup before the voice/speech line."""
    text = (prompt or "").strip()
    if not text:
        return False
    m = re.search(r"<<<voice_\d+>>>|\bsays\b", text, re.IGNORECASE)
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


def _cap_kling_o3_auto_duration(prompt: str, duration: int) -> int:
    """Keep concise single-chunk dialogue out of 10–12s buckets."""
    spoken = _spoken_for_duration_estimate(prompt)
    word_count = len(re.findall(r"\S+", spoken)) if spoken else 0
    if word_count and word_count <= _KLING_O3_AUTO_CAP_MAX_WORDS:
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
    estimated = estimate_kling_o3_duration_from_prompt(prompt)
    estimated = apply_kling_o3_duration_floor(prompt, estimated)
    return _cap_kling_o3_auto_duration(prompt, estimated)


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
            from tools import kling_o3_prompt as o3p

            for msg in o3p.validate_element_bound_voice_prompt(speaker, stored_prompt):
                errors.append({
                    "beat_id": beat_id,
                    "code": "ELEMENT_VOICE_PROMPT",
                    "message": msg,
                })
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
        elif speaker:
            ok, detail = element_char_ref_gate(beat)
            if not ok:
                errors.append({
                    "beat_id": beat_id,
                    "code": "ELEMENT_VISUAL_MISMATCH",
                    "message": detail,
                    "char_ref": char_path,
                })
        if not bg_path:
            errors.append({
                "beat_id": beat_id,
                "code": "MISSING_BG_REF",
                "message": "Missing background reference image",
            })

    duration = resolve_kling_o3_submit_duration(beat, prompt)
    spoken = _spoken_for_duration_estimate(prompt)
    if spoken:
        staging = _kling_o3_has_pre_speech_staging(prompt)
        unsnapped = estimate_kling_o3_seconds_unsnapped(
            spoken,
            has_pre_speech_staging=staging,
        )
        # Block only when estimate clearly exceeds the largest Kling bucket.
        if unsnapped > float(KLING_O3_MAX_DURATION) + 0.75:
            errors.append({
                "beat_id": beat_id,
                "code": "DIALOGUE_TOO_LONG",
                "message": (
                    f"Local length estimate {unsnapped:.1f}s exceeds max bucket "
                    f"({KLING_O3_MAX_DURATION}s). Shorten dialogue or split the beat."
                ),
                "estimated_duration_s": round(unsnapped, 2),
            })

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


def _kling_o3_normalize_spoken(spoken: str) -> str:
    """Normalize dialogue for Kling TTS — ellipses and runaway dots cause drag/baby-talk."""
    s = (spoken or "").strip()
    s = _strip_parenthetical_actions(s)
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"…+", ".", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_parenthetical_actions(text: str) -> str:
    """Remove (gestures...) / (makes eye contact...) — staging belongs outside quotes."""
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", text or "")).strip()


def _normalize_spoken_for_duration(spoken: str) -> str:
    """Spoken word count for duration math — never count () or [] stage directions."""
    s = (spoken or "").strip()
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = _strip_parenthetical_actions(s)
    return re.sub(r"\s+", " ", s).strip()


def _spoken_for_duration_estimate(prompt: str) -> str:
    """Duration validation uses quoted dialogue from the prompt box only."""
    return _normalize_spoken_for_duration(
        extract_spoken_dialogue_from_kling_prompt(prompt) or "",
    )


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

# Laurel (lemur scholar; registry key Lorelai — "Laurel" in voice lines for TTS pronunciation).
KLING_O3_LORELAI_VOICE_DELIVERY = (
    "warm excited conversational pace, clear scholarly delivery, measured deliberate cadence, "
    "slower steady rhythm, not rushed or frantic, not hyper or sputtering, "
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
        if "discovery" in scene or any(k in emotion for k in ("upset", "shock", "excited", "happy")):
            base = (
                "Lorelai — Discovery. Excitable lemur scholar with glasses and backpack, "
                "wide expressive eyes, reacting in the heartwood grove"
            )
        else:
            base = f"Lorelai — {_emotion_action_clause(beat)}"
        return base + _kling_o3_viewer_staging_clause(spoken)
    return _emotion_action_clause(beat) + _kling_o3_viewer_staging_clause(spoken)


def _kling_o3_voice_line_display_name(speaker: str, element_name: str | None) -> str:
    """Spoken-name in O3 voice lines — Laurel not Lorelai for clone pronunciation."""
    canon = (speaker or "").strip()
    if canon in ("Lorelai", "Laurel"):
        return "Laurel"
    return (element_name or canon or "Character").strip()


def _kling_o3_voice_block(speaker: str, spoken: str) -> str:
    """Dialogue block for Kling native audio.

    When character has an active Element with bound voice_id (Option C),
    use the element name naturally — voice comes from Element registration.
    Otherwise fall back to <<<voice_1>>> prompt tags (generic Kling audio).
    """
    spoken = _kling_o3_normalize_spoken(spoken)
    canon = (speaker or "Character").strip()

    try:
        from tools import kling_character_registry as reg
        element_name = reg.get_element_name(canon)
        if element_name:
            voice_name = _kling_o3_voice_line_display_name(canon, element_name)
            if canon == "Tessa":
                return (
                    f'{voice_name} speaks in a {KLING_O3_TESSA_VOICE_DELIVERY}: "{spoken}"'
                )
            if canon == "Chipper":
                return (
                    f'{voice_name} speaks in a {KLING_O3_CHIPPER_VOICE_DELIVERY}: "{spoken}"'
                )
            if canon in ("Lorelai", "Laurel"):
                return (
                    f'{voice_name} speaks in a {KLING_O3_LORELAI_VOICE_DELIVERY}: "{spoken}"'
                )
            return f'{voice_name} says: "{spoken}"'
    except Exception:
        pass

    if canon == "Chipper":
        return (
            f'@Image1 <<<voice_1>>> speaks in a {KLING_O3_CHIPPER_VOICE_DELIVERY}: "{spoken}"'
        )

    if canon == "Tessa":
        return (
            f'@Image1 <<<voice_1>>> speaks in a {KLING_O3_TESSA_VOICE_DELIVERY}: "{spoken}"'
        )

    if canon in ("Lorelai", "Laurel"):
        return (
            f'Laurel speaks in a {KLING_O3_LORELAI_VOICE_DELIVERY}: "{spoken}"'
        )

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
    voice_block = _kling_o3_voice_block(speaker, spoken)
    intro_staging = ""
    if _is_chipper_intro_beat(beat):
        intro_staging = f"\n\n{_kling_o3_chipper_intro_staging()}"
    return _append_kling_o3_submit_locks(
        (
            f"@Image1 ({speaker}) {action}. Scene from @Image2.\n\n"
            f"{KLING_O3_CAMERA_LOCK}"
            f"{intro_staging}\n\n"
            f"{voice_block}\n\n"
            "Children's illustrated fantasy storybook style, warm golden forest light."
        ),
        speaker=speaker,
        spoken=spoken,
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
        aligned, detail = reg.char_ref_matches_element_images(char_path, speaker)
        if not aligned:
            return False, detail
        return True, ""
    except Exception as exc:
        return False, str(exc)


def sync_element_char_ref_status(beat: dict, *, heal_mismatch: bool = True) -> bool:
    """Persist element_char_ref_ok/error on beat for UI + submit gates."""
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


def require_element_char_ref_for_o3(beat: dict) -> None:
    """Raise before any Element O3 subprocess/API work if @Image1 is wrong."""
    if not sync_element_char_ref_status(beat, heal_mismatch=False):
        detail = beat.get("element_char_ref_error") or "char ref does not match Element poses"
        raise RuntimeError(f"ELEMENT_VISUAL_MISMATCH: {detail}")


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
    """Still for Beat Gen magic_still — any of the four drop slots, then char auto-ref."""
    for key in (
        "start_frame_image",
        "reference_image",
        "end_frame_image",
        "bg_ref_image",
    ):
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
    if beat_magic_still_clip_path(beat, event_dir):
        return True
    st = beat.get("kling_o3_status") or beat.get("status")
    vp = beat.get("kling_o3_video_path")
    if st == "approved" and vp and os.path.isfile(vp):
        return True
    return False


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
    beat["kling_o3_prompt"] = build_kling_o3_prompt(beat)
    if not beat.get("kling_o3_duration_locked"):
        beat["kling_o3_duration"] = resolve_kling_o3_submit_duration(
            beat, beat["kling_o3_prompt"],
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
    """Blank Beat Gen row with full Kling O3 pipeline fields (Submit/Redo/Duration)."""
    beat = {
        "beat_id": beat_id,
        "speaker": "",
        "dialogue_text": "",
        "emotion": "",
        "scene_notes": "",
        "status": "new",
        "pipeline": "kling_o3_omni",
        "flux_options": [],
        "gpt_options": [],
    }
    apply_kling_o3_defaults_to_beat(beat, str(event_id), phase)
    return beat


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
    for b in merged:
        role = b.get("intro_beat_role")
        if role in (INTRO_BEAT_ROLE_SEMI_CANONICAL, INTRO_BEAT_ROLE_CANONICAL_MIRROR):
            _apply_intro_canonical_beat_defaults(b, event_id, phase, role)
    merged = normalize_segment_beat_order(merged)
    heal_segment_dialogue_fields(merged)
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


def audit_kling_author_enrichment(beats: list[dict]) -> list[str]:
    """Post-approve guard — dialogue beats must carry author emotion/staging in prompts."""
    warnings: list[str] = []
    for b in beats or []:
        if not isinstance(b, dict):
            continue
        beat_id = b.get("beat_id") or "?"
        if beat_is_still_insert(b) or beat_is_canonical_mirror_protected(b):
            continue
        prompt = (b.get("kling_o3_prompt") or "").strip()
        if not prompt:
            warnings.append(f"{beat_id}: missing kling_o3_prompt after approve")
            continue
        if re.search(r"\bLuna\b", prompt) and "Lorelai" not in (b.get("speaker") or ""):
            warnings.append(f"{beat_id}: stale Luna cast leaked into prompt")
        if re.search(r"\bis a small green sea turtle\b", prompt, re.I):
            warnings.append(f"{beat_id}: species taxonomy in prompt — use @Image1 only")
        if re.search(r"\b(?:Tessa|Lorelai|Laurel|Arlo|Chipper)\s+is\s+a\s+", prompt, re.I):
            warnings.append(f"{beat_id}: species anatomy block in prompt — Event-1 shape violation")
        if "@Image1" in prompt and not identity_footer_is_canonical(prompt):
            warnings.append(f"{beat_id}: identity footer drift from KLING_O3_IDENTITY_LOCK")
        if re.search(r"\bChipper\b", prompt) and "Arlo" not in (b.get("speaker") or ""):
            warnings.append(f"{beat_id}: stale Chipper cast leaked into prompt")
        emotion = (b.get("emotion") or "").strip()
        if emotion and emotion.lower() not in ("neutral", "[neutral]"):
            emo_key = emotion.strip("[]").lower()
            if "[" not in prompt and emo_key not in prompt.lower():
                warnings.append(f"{beat_id}: emotion not woven into kling_o3_prompt")
        scene = (b.get("scene_notes") or "").strip()
        if len(scene) > 12:
            snippet = scene[:24].lower()
            if snippet not in prompt.lower() and "rooted in place" not in prompt.lower():
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


def preserve_kling_o3_segment_beats(
    sidecar: dict,
    arc_number: int,
    event_id: str,
    phase: str,
    event_dir: str | Path,
    *,
    reason: str,
) -> int:
    """Snapshot all Kling O3 beats for a segment (clips + manifest). Overwrites prior snapshot."""
    seg = get_seg_entry(sidecar, arc_number, event_id, phase)
    seg_dir = kling_o3_preserved_segment_dir(event_dir, arc_number, event_id, phase)
    if seg_dir.is_dir():
        shutil.rmtree(seg_dir)
    beats_dir = seg_dir / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    preserved = 0
    beats_meta: list[dict] = []
    for beat in seg.get("beats") or []:
        if beat.get("pipeline") != "kling_o3_omni":
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
    options.append({
        "key": f"{beat_id}_o3_video_{digest}",
        "label": label,
        "video_path": video_path,
        "source": "prior_kling_o3_redo",
        "active": True,
        "created_at": now,
    })
    for opt in options:
        opt["active"] = opt.get("video_path") == video_path
    beat["kling_o3_options"] = options[:3]
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
    beat["kling_o3_status"] = "approved"
    beat["status"] = "approved"
    for opt in options:
        opt["active"] = opt.get("video_path") == video_path
    beat["kling_o3_options"] = options[:3]
    return True


def _kling_o3_option_key(beat_id: str, video_path: str) -> str:
    digest = hashlib.sha1(video_path.encode("utf-8")).hexdigest()[:10]
    return f"{beat_id}_o3_video_{digest}"


def normalize_kling_o3_option_slots(beat: dict) -> list[dict | None]:
    """Return fixed 3-slot view of ``kling_o3_options`` (index = UI container)."""
    slots: list[dict | None] = [None, None, None]
    options = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict) and (o.get("video_path") or o.get("key"))
    ]
    for i, opt in enumerate(options):
        idx = opt.get("slot_index")
        if not isinstance(idx, int) or idx < 0 or idx > 2:
            idx = i if i < 3 else None
        if idx is None:
            continue
        if slots[idx] is None:
            slots[idx] = opt
            opt["slot_index"] = idx
            continue
        for j in range(3):
            if slots[j] is None:
                slots[j] = opt
                opt["slot_index"] = j
                break
    return slots


def assign_kling_o3_option_to_slot(
    beat: dict,
    slot_index: int,
    *,
    video_path: str,
    label: str,
    source: str,
    now: str,
    make_active: bool = True,
) -> str:
    """Place a generated clip in container ``slot_index`` (0–2); returns option key."""
    slot_index = max(0, min(2, int(slot_index)))
    beat_id = str(beat.get("beat_id") or "beat")
    key = _kling_o3_option_key(beat_id, video_path)
    slots = normalize_kling_o3_option_slots(beat)
    new_opt = {
        "key": key,
        "label": label,
        "video_path": video_path,
        "source": source,
        "active": make_active,
        "slot_index": slot_index,
        "created_at": now,
    }
    slots[slot_index] = new_opt
    for opt in slots:
        if opt:
            opt["active"] = bool(make_active and opt.get("video_path") == video_path)
    beat["kling_o3_options"] = [o for o in slots if o is not None]
    if make_active:
        beat["kling_o3_video_path"] = video_path
        beat["kling_o3_selected_option_key"] = key
    return key


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


def resolve_magic_style_for_render(
    bg_beat_id: str,
    *,
    sidecar: dict | None = None,
    production_state: dict | None = None,
    video_role: str = "resolution",
    manual_path: list | None = None,
    scene_registry: dict | None = None,
) -> str:
    """Pick compositor style — canonical approved look is tessa_ori (beat 1 resolution)."""
    if scene_registry:
        for key in (
            f"m1_e1_res_{bg_beat_id}",
            f"m1_e1_res_{bg_beat_id.replace('bg_arc1_event1_post_', '')}",
        ):
            style = (scene_registry.get(key) or {}).get("style")
            if isinstance(style, str) and style in ("tessa_ori", "wide_ori"):
                # Production default: tessa_ori sparkle river (beat 1 approved look).
                # wide_ori remains opt-in via explicit scene_registry only.
                return style if style == "wide_ori" and (scene_registry.get(key) or {}).get("force_wide_ori") else "tessa_ori"
    return "tessa_ori"


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


def resolve_bg_magic_canonical_kind(beat: dict) -> str | None:
    """Which magic composite is canonical for preview + stitch export.

    O3-approved beats with magic_video use magic-on-video (beat 1 resolution).
    Still-only beats use magic_still + ElevenLabs TTS at stitch export.
    """
    if beat.get("kling_o3_status") == "approved" and beat.get("magic_video_path"):
        return "video"
    if beat.get("magic_still_path"):
        return "still"
    if beat.get("magic_video_path"):
        return "video"
    return None


def merge_storyboard_magic_into_bg_beat(
    beat: dict,
    production_state: dict | None,
    video_role: str,
    sidecar: dict | None = None,
) -> dict:
    """Fill missing magic/TTS fields on a BG beat from storyboard partition state."""
    out = dict(beat)
    if not production_state:
        out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out)
        return out
    sb_id = storyboard_beat_id_for_bg_beat(
        beat.get("beat_id") or "",
        sidecar=sidecar,
        production_state=production_state,
        video_role=video_role,
    )
    if not sb_id:
        out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out)
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
    out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out)
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
        if val is not None:
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
    beat["kling_o3_video_path"] = str(dest.resolve())
    beat["kling_o3_status"] = "completed"
    beat["kling_o3_completed_at"] = datetime.now(timezone.utc).isoformat()
    beat.pop("kling_o3_error", None)
    beat.pop("kling_o3_task_id", None)
    if beat.get("status") not in ("approved",):
        beat["status"] = "video_ready"
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


def enrich_beat_kling_o3_pinned(beat: dict, event_dir: str | Path) -> dict:
    """Return beat copy with transient ``kling_o3_pinned_preserve`` for API responses."""
    out = dict(beat)
    beat_id = beat.get("beat_id")
    if beat_id:
        out["kling_o3_pinned_preserve"] = has_pinned_kling_o3_preserve(beat_id, event_dir)
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
    out["magic_canonical_kind"] = resolve_bg_magic_canonical_kind(out)
    ap = resolve_bg_beat_tts_audio_path(event_dir, beat)
    out["audio_file_exists"] = ap is not None
    if ap is not None and not (out.get("audio_file") or "").strip():
        out["audio_file"] = ap.name
    return out


def enrich_beats_kling_o3_pinned(beats: list[dict], event_dir: str | Path) -> list[dict]:
    return [enrich_beat_kling_o3_pinned(b, event_dir) for b in beats]


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
    """Pin the current approved delivery so a later redo cannot lose the only good copy."""
    if str(beat.get("kling_o3_status") or "") != "approved":
        return False
    if not beat.get("kling_o3_video_path"):
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
    if not video_path:
        return None
    m = re.search(r"_g(\d+)\.mp4$", Path(video_path).name, re.IGNORECASE)
    return int(m.group(1)) if m else None


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

    if clip_path.is_file():
        resolved = str(clip_path.resolve())
        target_status = "approved" if beat.get("status") == "approved" else "completed"
        changed = False
        if beat.get("kling_o3_video_path") != resolved:
            beat["kling_o3_video_path"] = resolved
            changed = True
        if status not in ("completed", "approved"):
            beat["kling_o3_status"] = target_status
            changed = True
        if beat.get("status") not in ("approved",) and target_status == "completed":
            beat["status"] = "video_ready"
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

    # Redo increments generation before the new clip lands. If the in-flight
    # job dies (refresh, server restart), sidecar can still point at g{N-1}.
    path_gen = _kling_o3_gen_from_video_path(beat.get("kling_o3_video_path"))
    if path_gen is not None and path_gen < gen:
        beat.pop("kling_o3_video_path", None)
        beat.pop("kling_o3_completed_at", None)
        beat.pop("kling_o3_task_id", None)
        if beat.get("status") == "video_ready":
            beat["status"] = "draft"
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
                if reconcile_kling_o3_beat(beat, event_dir):
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


def _ffmpeg_concat_kling_clips_reencode(clip_paths: list[Path], dest: Path) -> None:
    """Concat Kling clips with re-encode — ``-c copy`` causes A/V desync across mixed encodes."""
    import shutil

    if not clip_paths:
        raise ValueError("no clips to concat")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], dest)
        return

    fs = _ffmpeg_stitch_module()
    has_audio = fs._has_audio_stream

    inputs: list[str] = []
    for p in clip_paths:
        inputs.extend(["-i", str(p.resolve())])
    n = len(clip_paths)
    durations = [_ffprobe_duration(p) for p in clip_paths]

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
            f"[{src}:a:0]aresample=44100,aformat=channel_layouts=stereo[a{i}]"
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
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg concat reencode failed: {(r.stderr or '')[-500:]}")


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


def concat_kling_o3_approved_beats(
    beats: list[dict],
    event_dir: str | Path,
    slot_key: str,
    *,
    phase: str | None = None,
    event_name: str | None = None,
    event_id: str | None = None,
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
    out_dir = Path(event_dir) / "assembled"
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
    for i, beat in enumerate(beats):
        is_last = i == len(beats) - 1
        if is_last and canonical_tail is not None:
            clip_paths.append(canonical_tail.resolve())
        else:
            clip_paths.append(
                resolve_beat_stitch_export_clip_path(beat, event_dir, scratch_dir),
            )
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{slot_key}_kling_o3_{ts}.mp4"
    pair_fades: list[int] = []
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

    boundaries = _boundaries_for_pair_fade_concat(beats, clip_paths, pair_fades)
    total_s = _ffprobe_duration(out_path)
    return out_path, boundaries, total_s
