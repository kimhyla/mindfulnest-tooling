#!/usr/bin/env python3
"""Directus ops for MOTION_VOCABULARY_V1_IMPLEMENTATION_20260419 session.

Writes:
  - 1 prod_preflight_reviews row (Phase 0 — BEFORE Phase 1)
  - 3 prod_locked_decisions rows (MOTION_VOCABULARY_PER_CREATURE_V1,
    MOTION_TAIL_LIPSYNC_SAFE_V1, BIRD_SPEAKERS_CANONICALIZATION_FIX_V1)
  - prod_activity_log rows throughout phases

Idempotent: checks for existing task_id / decision_key before creating.
On duplicate decision_key: PATCH existing row per Rule 20.
On write failure: retry once; else append to pending_directus_writes.json.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(
    "/Users/kimberlysmith/Dropbox/Claude Mindfulnest Project Files"
)
sys.path.insert(0, str(PROJECT_ROOT / "Production" / "tools"))

from lib.credentials import load_credentials  # type: ignore
from lib.directus import DirectusClient  # type: ignore

TASK_ID = "MOTION_VOCABULARY_V1_IMPLEMENTATION_20260419"
SOURCE_DOC = "Production/tools/production_server.py"
PENDING_FILE = PROJECT_ROOT / "Production" / "pending_directus_writes.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _client() -> DirectusClient:
    creds = load_credentials()
    c = DirectusClient(creds["directus_url"], creds["directus_email"],
                       creds["directus_password"])
    c.authenticate()
    return c


def _append_pending(op: dict) -> None:
    existing = []
    if PENDING_FILE.exists():
        try:
            existing = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append({**op, "queued_at": _now_iso()})
    PENDING_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"[WARN] appended to pending_directus_writes.json: {op.get('collection')}")


def _safe_create(c: DirectusClient, collection: str, data: dict) -> dict | None:
    for attempt in (1, 2):
        try:
            return c.create(collection, data)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] create {collection} attempt {attempt} failed: {exc}")
            if attempt == 1:
                time.sleep(2.0)
    _append_pending({"op": "create", "collection": collection, "data": data})
    return None


def _safe_patch(c: DirectusClient, collection: str, item_id: int | str, data: dict) -> dict | None:
    for attempt in (1, 2):
        try:
            return c.update(collection, item_id, data)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] patch {collection}/{item_id} attempt {attempt} failed: {exc}")
            if attempt == 1:
                time.sleep(2.0)
    _append_pending({"op": "patch", "collection": collection, "id": item_id, "data": data})
    return None


def _upsert_ld(c: DirectusClient, payload: dict) -> int | None:
    """PATCH-on-duplicate-key per Rule 20."""
    key = payload["decision_key"]
    existing = c.get("prod_locked_decisions",
                     filters={"decision_key": {"_eq": key}}, limit=1)
    if existing:
        item_id = existing[0]["id"]
        print(f"[ld] PATCH {key} (id={item_id})")
        r = _safe_patch(c, "prod_locked_decisions", item_id, payload)
        return item_id if r else None
    r = _safe_create(c, "prod_locked_decisions", payload)
    return r.get("id") if r else None


def write_preflight(c: DirectusClient) -> int | None:
    existing = c.get("prod_preflight_reviews",
                     filters={"task_id": {"_eq": TASK_ID}}, limit=1)
    if existing:
        print(f"[preflight] already exists: id={existing[0]['id']}")
        return existing[0]["id"]

    payload = {
        "task_id": TASK_ID,
        "task_type": "architectural",
        "task_description": (
            "Implement per-creature, emotion-conditioned motion vocabulary in "
            "Production/tools/production_server.py::build_motion_prompt. "
            "Adds SPEAKER_MOTION_PROFILES (7 creatures x 4 emotional registers = "
            "28 vocabulary strings), LIPSYNC_SAFE_TAIL + SPRITE_IDLE_TAIL switch "
            "keyed on beat.lipsync_targeted, _canonicalize_speaker helper, and "
            "fixes the BIRD_SPEAKERS routing bug (canonical 'Chipper' per LD-183, "
            "2026-04-17 lore update, was receiving turtle constraint instead of "
            "bird constraint). Every vocabulary string verified section 8.1-8.4 "
            "compliant (no BANNED_PROMPT_WORDS, no section 8.2 forbidden phrases, "
            "no section 8.1 required-term leaks)."
        ),
        "claude_summary": (
            "(1) What: Replace build_motion_prompt with per-speaker vocabulary "
            "lookup keyed by canonical name and emotional register; add tail "
            "switching (non-motion-locking for lipsync-targeted, motion-locking "
            "for sprites); add Chipper to BIRD_SPEAKERS as belt-and-suspenders "
            "alongside _SPEAKER_ALIAS canonicalization. Signature preserved "
            "((beat: dict) -> str); all 4 call sites in production_server.py "
            "(lines 4401, 4777, 5075, 7232) remain compatible. "
            "(2) Error paths closed: invalid emotion logs WARN and falls back to "
            "neutral; missing lipsync_targeted defaults True per LD-180; unknown "
            "speaker falls through to SECTION_ACTIONS; strip() on speaker handles "
            "whitespace-only input. sanitize_prompt remains belt-and-suspenders. "
            "(3) Tests: 15 cases covering happy path, legacy alias routing "
            "(Guide Bird, Pip -> Chipper), fallback tiers, invalid emotion, "
            "missing fields, speaker edge cases (None/empty/whitespace), plus "
            "3 rule scans (banned words, section 8.2 word-boundary forbidden "
            "phrases, section 8.1 single-occurrence) across all 28 combos. "
            "(4) Scope: new vocabulary applies to legacy single-image Kling path. "
            "kling_startend_pipeline.py (section 8.3, Event_1 universal default "
            "per LD-180) uses its own DEFAULT_POSITIVE_PROMPT at line 96 and "
            "does not route through build_motion_prompt -- documented in OUTCOME."
        ),
        "agent_advocates": 5,
        "agent_counters": 5,
        "synthesis": (
            "Round 1: 7 PROCEED (A1-A5 + C1 concede + C5 proceed-with-trim), "
            "3 BLOCK (C2: smoke test regression at line 7231-7234 if default tail "
            "flips; C3: speaker edge cases None/empty/whitespace untested; "
            "C4: severity upgrade MEDIUM->HIGH on TAIL decision + LD-162 cite). "
            "Also C1 YELLOW on 'body tightening' matching naive substring 'tight'. "
            "Convergence: PROCEED with 5 mitigations baked into Phase 1: "
            "(M1) update smoke test to set lipsync_targeted=False or match new "
            "tail; (M2) test section 8.2 scan uses word-boundary regex to avoid "
            "tight/tightening false positive; (M3) _canonicalize_speaker strips "
            "whitespace + tests 13-15 for None/empty/whitespace; "
            "(M4) Row 2 MOTION_TAIL_LIPSYNC_SAFE_V1 severity HIGH with LD-162 "
            "reference; (M5) document section 8.3 kling_startend_pipeline scope "
            "gap in OUTCOME.md. All BLOCKs are addressable-in-implementation, "
            "not design rollbacks."
        ),
        "approved_to_proceed": True,
        "approved_at": _now_iso(),
    }
    r = _safe_create(c, "prod_preflight_reviews", payload)
    return r.get("id") if r else None


def write_activity(c: DirectusClient, action: str, details: dict,
                   script_version: str = "motion_vocab_v1_20260419",
                   module_id: int | None = None) -> int | None:
    """details is a JSON object (dict), not a string."""
    payload = {
        "action": action,
        "details": details,
        "performed_by": "claude",
        "script_version": script_version,
    }
    if module_id is not None:
        payload["module_id"] = module_id
    r = _safe_create(c, "prod_activity_log", payload)
    return r.get("id") if r else None


def write_ld_vocabulary(c: DirectusClient) -> int | None:
    payload = {
        "decision_key": "MOTION_VOCABULARY_PER_CREATURE_V1",
        "decision_name": "Per-creature emotion-conditioned motion vocabulary",
        "decision_text": (
            "build_motion_prompt in production_server.py now consumes "
            "SPEAKER_MOTION_PROFILES, a dict keyed by canonical speaker name "
            "with four emotional registers (happy_excited, upset_shocked, "
            "sad_disappointed, neutral). Neutral is reserved for "
            "sprite-pipeline idle loops. Each vocabulary string is Rule 8.1-8.4 "
            "compliant (no BANNED_PROMPT_WORDS, no Rule 8.2 forbidden phrases, "
            "no Rule 8.1 required-term leaks). Legacy generic SECTION_ACTIONS "
            "remains as fallback for unknown speakers. Applies to the legacy "
            "single-image Kling path (production_server.py call sites at 4401, "
            "4777, 5075, 7232). The Rule 8.3 start-end pipeline "
            "(kling_startend_pipeline.py) uses its own DEFAULT_POSITIVE_PROMPT "
            "and does NOT route through build_motion_prompt -- a known scope "
            "gap to be addressed separately."
        ),
        "source_document": SOURCE_DOC,
        "task_category": "video-production",
        "severity": "MEDIUM",
        "date_locked": "2026-04-19",
        "status": "active",
        "is_current": True,
    }
    return _upsert_ld(c, payload)


def write_ld_tail(c: DirectusClient) -> int | None:
    payload = {
        "decision_key": "MOTION_TAIL_LIPSYNC_SAFE_V1",
        "decision_name": "Non-motion-locking tail for lipsync-targeted beats",
        "decision_text": (
            "Lipsync-targeted beats (beat.lipsync_targeted=True, default for "
            "Event_1 per LD-180) now use 'no dialogue in video' as the "
            "Rule 8.1-required tail. Sprite-pipeline beats (lipsync_targeted=False) "
            "retain the motion-locking 'Silent subtle idle movement only' tail. "
            "Both are Rule 8.1-allowed alternatives. The switch removes the 'only' "
            "motion-lock for narrative content while preserving idle-loop "
            "stability for sprites. Rationale: Rule 8.2 / LD-162 "
            "(LIPSYNC_SOURCE_MUST_PRESERVE_MOUTH_MOTION, HIGH severity) requires "
            "lipsync-targeted Kling source videos to preserve per-frame mouth "
            "micro-motion. Motion-locking tails starve ByteDance LatentSync of "
            "landmark-tracking signal. This tail swap pairs with the vocabulary "
            "verbs (all motion-generative) to satisfy Rule 8.2."
        ),
        "source_document": SOURCE_DOC,
        "task_category": "video-production",
        "severity": "HIGH",
        "date_locked": "2026-04-19",
        "status": "active",
        "is_current": True,
    }
    return _upsert_ld(c, payload)


def write_ld_bird_fix(c: DirectusClient) -> int | None:
    payload = {
        "decision_key": "BIRD_SPEAKERS_CANONICALIZATION_FIX_V1",
        "decision_name": "build_motion_prompt canonicalizes speaker before BIRD_SPEAKERS check",
        "decision_text": (
            "Fixed a silent bug where beats authored with speaker='Chipper' "
            "(canonical per LD-183, 2026-04-17 lore update) received the turtle "
            "constraint ('Mouth closed, no speech.') instead of the bird "
            "constraint ('Beak closed, no speech, no lip movement.') because "
            "BIRD_SPEAKERS did raw string matching and 'Chipper' was not in the "
            "set (only 'Guide Bird' and 'Luna' were). build_motion_prompt now "
            "routes speaker through _SPEAKER_ALIAS via the new "
            "_canonicalize_speaker helper BEFORE the BIRD_SPEAKERS check. "
            "'Chipper' also added to BIRD_SPEAKERS explicitly as "
            "belt-and-suspenders. Legacy speakers 'Guide Bird' and 'Pip' "
            "continue to route correctly via _SPEAKER_ALIAS. The canonical "
            "speaker name also surfaces in the prompt text (e.g., 'Cartoon "
            "Chipper character' instead of 'Cartoon Guide Bird character') so "
            "Kling sees the current lore name."
        ),
        "source_document": SOURCE_DOC,
        "task_category": "video-production",
        "severity": "LOW",
        "date_locked": "2026-04-19",
        "status": "active",
        "is_current": True,
    }
    return _upsert_ld(c, payload)


def main() -> int:
    c = _client()
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"

    if phase in ("preflight", "all"):
        pre_id = write_preflight(c)
        print(f"[preflight] id={pre_id}")
        write_activity(
            c, action="preflight_completed",
            details={
                "task_id": TASK_ID,
                "preflight_id": pre_id,
                "phase": "Phase 0",
                "round_1_votes": {"PROCEED": 7, "BLOCK": 3},
                "convergence": "PROCEED with 5 mitigations M1-M5",
                "mitigations": {
                    "M1": "smoke test at production_server.py:7231-7234 updated",
                    "M2": "test 8.2 scan uses word-boundary regex",
                    "M3": "_canonicalize_speaker strips whitespace + tests 13-15",
                    "M4": "MOTION_TAIL_LIPSYNC_SAFE_V1 severity HIGH with LD-162 ref",
                    "M5": "8.3 kling_startend_pipeline scope gap documented in OUTCOME",
                },
            },
        )

    if phase in ("lds", "all"):
        ids = {
            "vocab": write_ld_vocabulary(c),
            "tail": write_ld_tail(c),
            "bird": write_ld_bird_fix(c),
        }
        print(f"[ld] written: {ids}")
        write_activity(
            c, action="locked_decisions_registered",
            details={
                "task_id": TASK_ID,
                "phase": "Phase 3",
                "decisions": {
                    "MOTION_VOCABULARY_PER_CREATURE_V1": {"id": ids["vocab"], "severity": "MEDIUM"},
                    "MOTION_TAIL_LIPSYNC_SAFE_V1": {"id": ids["tail"], "severity": "HIGH"},
                    "BIRD_SPEAKERS_CANONICALIZATION_FIX_V1": {"id": ids["bird"], "severity": "LOW"},
                },
            },
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
