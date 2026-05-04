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

import base64
import concurrent.futures
import http.client
import io
import json
import os
import re
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROD_DIR = os.path.normpath(os.path.join(_TOOLS_DIR, ".."))
_PROJECT_DIR = os.path.normpath(os.path.join(_TOOLS_DIR, "..", ".."))
_SKELETON_BASE = os.path.join(_PROJECT_DIR, "Arc Skeletons")

BG_SIDECAR_PATH = os.path.join(_PROD_DIR, "beat_generator_state.json")
BG_STILLS_DIR = os.path.join(_PROD_DIR, "beat_generator_stills")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Speaker canonicalization (mirrors production_server._SPEAKER_ALIAS subset)
_BG_SPEAKER_ALIAS = {
    "chipper":       "Chipper",
    "guide bird":    "Chipper",
    "pip":           "Chipper",
    "assistant bird": "Chipper",
    "tessa":         "Tessa",
    "luna":          "Luna",
    "benson":        "Benson",
    "ember":         "Ember",
    "bork":          "Bork",
    "bramble":       "Bramble",
    "cedric":        "Cedric",
    "myrrhin":       "Cedric",
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
    "Chipper": os.path.join(_PROD_DIR, "Character_Assets", "generated_masters", "master_chipper_live-batch-2-761a7da1.png"),
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
    with _sidecar_lock:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def write_sidecar(data):
    """Atomic write (os.replace per LD-134). RLock-guarded."""
    path = os.path.abspath(BG_SIDECAR_PATH)
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()
    with _sidecar_lock:
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=d, delete=False,
                                         suffix=".tmp", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            tmp = f.name
        os.replace(tmp, path)


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
_EVENT_HEADER   = re.compile(r"^##\s+EVENT\s+([\d]+[a-z]?):\s*(.+)", re.IGNORECASE | re.MULTILINE)
_SECTION_SETUP  = re.compile(r"^###\s+Narrative Setup",              re.IGNORECASE | re.MULTILINE)
_SECTION_THERAP = re.compile(r"^###\s+Therapeutic",                  re.IGNORECASE | re.MULTILINE)
_SECTION_RES    = re.compile(r"^###\s+Resolution",                   re.IGNORECASE | re.MULTILINE)
_SECTION_TMRW   = re.compile(r"^###\s+Tomorrow Hook",                re.IGNORECASE | re.MULTILINE)
_SECTION_POST   = re.compile(r"^###\s+Post-",                        re.IGNORECASE | re.MULTILINE)
_NEXT_H3        = re.compile(r"^###",                                 re.MULTILINE)
_MODULE_MARKER  = re.compile(r"\*\*[►▶]\s*INSERT MODULE",            re.IGNORECASE)

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

    # Collect valid events in order (positions + metadata)
    valid = []
    for m in _EVENT_HEADER.finditer(text):
        event_id = m.group(1)
        rest = m.group(2).strip()
        type_m = re.search(r"\(([^)]+)\)\s*$", rest)
        event_type = type_m.group(1).strip() if type_m else "Narrative Event"
        clean_name = rest[:type_m.start()].strip() if type_m else rest
        if _SKIP_TYPES.search(f"({event_type})"):
            continue
        valid.append({"pos": m.start(), "event_id": str(event_id),
                      "event_type": event_type, "clean_name": clean_name})

    segments = []
    seg_idx = 0
    for i, ev in enumerate(valid):
        ev_end = valid[i + 1]["pos"] if i + 1 < len(valid) else len(text)
        event_text = text[ev["pos"]:ev_end]
        has_module = bool(_MODULE_MARKER.search(event_text))
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

    return beats


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
    if sidecar.get("schema_version", 1) < 2:
        sidecar["schema_version"] = 2
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
        sidecar.setdefault("migration_warnings", []).extend(migration_warnings)
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


def run_ken_burns(beat, still_path, pan_x_pct, pan_y_pct, zoom_start, zoom_end, duration, fps=24):
    out_dir = _LOCAL_STILLS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    video_path = str(out_dir / f"{beat['beat_id']}_kenburns_{ts}.mp4")
    total_frames = int(duration * fps)
    zoompan = (
        f"zoompan=z='{zoom_start}+({zoom_end}-{zoom_start})*on/{total_frames}'"
        f":x='iw*{pan_x_pct/100.0}':y='ih*{pan_y_pct/100.0}'"
        f":d={total_frames}:s=1280x720:fps={fps}"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", still_path,
        "-vf", zoompan, "-t", str(duration),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", str(fps), "-movflags", "+faststart",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-shortest", "-c:a", "aac", "-b:a", "128k",
        video_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ken_burns ffmpeg failed: {r.stderr[-500:]}")
    actual_dur = _ffprobe_duration(Path(video_path))
    if abs(actual_dur - duration) > 0.2:
        raise RuntimeError(f"ken_burns output duration {actual_dur:.2f}s, expected {duration:.2f}s ±0.2s")
    beat["local_render_params"] = {
        "method": "ken_burns", "still_path": still_path,
        "pan_x_pct": pan_x_pct, "pan_y_pct": pan_y_pct,
        "zoom_start": zoom_start, "zoom_end": zoom_end, "duration": duration,
    }
    return {"video_path": video_path, "preview_path": still_path}


def run_static_hold(beat, still_path, duration, fps=24):
    out_dir = _LOCAL_STILLS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    video_path = str(out_dir / f"{beat['beat_id']}_static_{ts}.mp4")
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", still_path,
        "-t", str(duration),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-s", "1280x720", "-r", str(fps), "-movflags", "+faststart",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-shortest", "-c:a", "aac", "-b:a", "128k",
        video_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"static_hold ffmpeg failed: {r.stderr[-500:]}")
    actual_dur = _ffprobe_duration(Path(video_path))
    if abs(actual_dur - duration) > 0.2:
        raise RuntimeError(f"static_hold duration {actual_dur:.2f}s, expected {duration:.2f}s ±0.2s")
    beat["local_render_params"] = {
        "method": "static_hold", "still_path": still_path, "duration": duration,
    }
    return {"video_path": video_path, "preview_path": still_path}


def probe_capabilities() -> dict:
    """Probe for optional dependencies. Returns dict of booleans."""
    caps = {"magic_compositor": False, "ffmpeg": False, "ffprobe": False,
            "magic_compositor_error": None}
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
