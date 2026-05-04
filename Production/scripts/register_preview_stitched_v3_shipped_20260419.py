#!/usr/bin/env python3
"""Register the 2 shipped-LDs + activity log + preflight 98 update
for Preview Stitched V3 -- Phase B + Phase A authoring panels.

Per handoff Phase 4:
  1. LD PREVIEW_STITCHED_V3_SHIPPED_20260419  (severity MEDIUM)
  2. LD FFMPEG_WATERCOLOR_OVERLAY_A1_LINEAR_20260419  (severity MEDIUM)
  3. Update parent preflight 98 completion note
  4. prod_activity_log entry

Idempotent: duplicate decision_key returns 400; script logs + exits 0.

Run from project root:
    python3 Production/scripts/register_preview_stitched_v3_shipped_20260419.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS_LIB = _HERE.parent / "tools" / "lib"
sys.path.insert(0, str(_TOOLS_LIB))

from credentials import load_credentials  # type: ignore
from directus import DirectusClient, DirectusError  # type: ignore

TASK_ID = "preview_stitched_v3_phase_b_a_implementation_20260419"
PARENT_PREFLIGHT_ID = 98
V3_PREFLIGHT_ID = 102  # registered earlier in this session

LD1_KEY = "PREVIEW_STITCHED_V3_SHIPPED_20260419"
LD2_KEY = "FFMPEG_WATERCOLOR_OVERLAY_A1_LINEAR_20260419"


LD1_TEXT = (
    "Preview Stitched V3 shipped: Phase B (Cedric meditation) + Phase A "
    "(Chipper demo) authoring panels as storyboard extension per "
    "TECH_SPEC_PREVIEW_STITCHED_V3_PHASE_B_20260419.md. Ships with "
    "placeholder assets for Phase A (real assets arrive via parallel "
    "HANDOFF_PHASE_A_ASSET_GENERATION_20260419.md; swap via state field). "
    "Extends (does NOT supersede) LD PREVIEW_STITCHED_V2_SHIPPED_20260419.\n\n"
    "New server endpoints (4 POST + 2 GET):\n"
    "  POST /api/phase_b/regen_audio  -- ElevenLabs Cedric/Chipper TTS\n"
    "  POST /api/phase_b/mix_audio    -- ffmpeg voice + ambient amix\n"
    "  POST /api/phase_b/lipsync      -- module-level ByteDance LipSync\n"
    "  POST /api/phase_b/preview      -- watercolor overlay composition\n"
    "  GET  /api/phase_b/media/*      -- module-level audio/video streaming\n"
    "  GET  /api/phase_b/watercolor/* -- watercolor library thumbnails\n\n"
    "New state fields (27): 12 phase_b_* + 15 phase_a_* flat fields added to "
    "_V2_MODULE_ALLOWED_FIELDS with per-field validators (HIGH-1 counter fix: "
    "int coercion would have broken string/JSON fields). Cache hash includes "
    "WATERCOLOR_OVERLAY_RECIPE_HASH + frame_x + sort_keys-normalized cues JSON "
    "(MEDIUM-5 + MEDIUM-6 fixes).\n\n"
    "Parameterized overlay helper: render_watercolor_overlay(frame_x, frame_y, "
    "chromakey_for_video) serves both Phase A (frame_x=800 RIGHT) and Phase B "
    "(frame_x=40 LEFT) via a single function per C4 requirement.\n\n"
    "WaveSurfer.js v7 timeline widget: CDN-loaded with graceful fallback to "
    "plain strip on network failure. Drag watercolor thumbnails onto waveform "
    "to place cues; saves via pathappPatch(null, 'phase_X_watercolor_cues_json').\n\n"
    "Path B patcher: patch_v38_phase_b.py applied cleanly (base64 SHA256 "
    "byte-identical verified pre+post: 22 URIs, "
    "sha256=fe7aa43b055336188b934f58d193fd9f889d19d37e695cbc3eac604e0e3a9a90). "
    "Patch delta: +25,910 bytes on storyboard_v38_prod.html.\n\n"
    "Tests: 28 new in test_phase_b_panel.py, ALL GREEN. Prior suite 102 tests "
    "still green = 130/130 total. Preflight: 102 (parent 98)."
)

LD2_TEXT = (
    "ffmpeg watercolor overlay recipe locked to A1 linear filter_complex, "
    "parameterized per phase, with chromakey branch for video cues only.\n\n"
    "Per 4+4 ffmpeg overlay debate 2026-04-19 (parent preflight 98): A1 "
    "(linear filter_complex) beats A4 (Python compositor) on fidelity "
    "(sub-frame timing precision vs A4's ~41ms frame-snap at 24fps, native "
    "easing, blend modes) despite A4 being 2-3x faster. Meditation use case "
    "requires frame-accuracy over render speed; cues visibly popping mid-breath "
    "would break immersion.\n\n"
    "Implemented at Production/tools/lib/ffmpeg_stitch.py::render_watercolor_overlay. "
    "Signature: render_watercolor_overlay(base_video_path, cues, frame_x, "
    "frame_y, output_path, library_dir, chromakey_for_video=True).\n\n"
    "Parameterization (C4 requirement): one function serves Phase A (frame_x=800 "
    "RIGHT) and Phase B (frame_x=40 LEFT). Phase A/B callers in "
    "_handle_phase_b_preview dispatch frame_x via _PHASE_FRAME_X = {'b': 40, "
    "'a': 800} constant.\n\n"
    "Chromakey branch (C4 requirement): chromakey=0x00FF00:0.1:0.0 applied to "
    "cue_type=='video' AND chromakey_for_video=True. Skipped for cue_type=='png' "
    "(PNGs have native alpha; chromakey on alpha PNGs would corrupt them). This "
    "supports the Chipper green-screen fallback path when Kling native alpha "
    "channel is unavailable.\n\n"
    "Animation presets (3): fade_in (0.3s alpha fade, static x), slide_in "
    "(0.15s fade + 300px leftward slide over 0.5s), gentle_pan (0.5s fade + "
    "5px sin oscillation). Preview/render fidelity documented as +/-50ms "
    "approximation; exact parity deferred to V4 if Kim reports visual drift.\n\n"
    "Recipe hash: WATERCOLOR_OVERLAY_RECIPE_HASH, bumpable via "
    "WATERCOLOR_OVERLAY_RECIPE_VERSION constant. Included in "
    "/api/phase_b/preview cache hash (MEDIUM-6 fix) so bumping recipe "
    "invalidates all phase_{a,b}_preview caches automatically.\n\n"
    "Preflight: 102 (parent 98). Test coverage: test_render_overlay_frame_x_{40,800} "
    "+ test_render_overlay_chromakey_video_only + test_recipe_hash_deterministic."
)


PARENT_COMPLETION_NOTE = (
    "\n\n[COMPLETED 2026-04-19] Preview Stitched V3 implementation shipped via "
    f"task_id={TASK_ID} preflight_id={V3_PREFLIGHT_ID}. "
    f"New LDs: {LD1_KEY}, {LD2_KEY}. "
    "Tests 130/130 green. Counter (preflight 102) 4 HIGH + 3 MEDIUM findings "
    "resolved in-code. Kim next action: hard-reload storyboard, expand Phase B "
    "panel, test end-to-end."
)


def main() -> int:
    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"], creds["directus_email"], creds["directus_password"],
    )
    client.authenticate()
    print("[directus] authenticated")

    now = datetime.now(timezone.utc).isoformat()

    ld1_id = _register_ld(client, now, LD1_KEY,
                          "Preview Stitched V3 -- Phase B + Phase A authoring panels shipped",
                          LD1_TEXT)
    ld2_id = _register_ld(client, now, LD2_KEY,
                          "Watercolor overlay uses A1 linear ffmpeg filter_complex, parameterized per phase, chromakey branch for video cues",
                          LD2_TEXT)
    patched_parent = _append_parent_note(client)
    activity_id = _register_activity(client, now, ld1_id, ld2_id)

    print(json.dumps({
        "v3_shipped_ld_id": ld1_id,
        "ffmpeg_watercolor_a1_ld_id": ld2_id,
        "parent_preflight_updated": bool(patched_parent),
        "activity_log_id": activity_id,
    }, indent=2))
    return 0


def _register_ld(client, now, key, name, text):
    body = {
        "decision_key": key,
        "decision_name": name,
        "decision_text": text,
        "source_document": "TECH_SPEC_PREVIEW_STITCHED_V3_PHASE_B_20260419.md",
        "task_category": "production_pipeline",
        "severity": "MEDIUM",
        "date_locked": now,
        "status": "active",
    }
    try:
        r = client._request("POST", "/items/prod_locked_decisions", data=body)
        did = r.get("data", {}).get("id")
        print(f"[directus] LD {key} id={did}")
        return did
    except DirectusError as exc:
        msg = (exc.detail or "").lower()
        if "duplicate" in msg or "unique" in msg:
            print(f"[directus] LD {key} already registered (idempotent skip)")
            # Fetch existing id for return.
            r = client._request(
                "GET",
                f"/items/prod_locked_decisions?filter[decision_key][_eq]={key}&fields=id",
            )
            data = r.get("data") or []
            return data[0]["id"] if data else "already_registered"
        print(f"[directus] LD {key} failed: {exc.status} {exc.detail[:500]}",
              file=sys.stderr)
        raise


def _append_parent_note(client):
    r = client._request(
        "GET",
        f"/items/prod_preflight_reviews/{PARENT_PREFLIGHT_ID}?fields=id,claude_summary",
    )
    data = r.get("data") or {}
    if not data:
        print(f"[directus] WARN: parent preflight {PARENT_PREFLIGHT_ID} not found",
              file=sys.stderr)
        return False
    existing = data.get("claude_summary") or ""
    if PARENT_COMPLETION_NOTE.strip() in existing:
        print(f"[directus] parent preflight {PARENT_PREFLIGHT_ID} already has completion note")
        return True
    body = {"claude_summary": existing + PARENT_COMPLETION_NOTE}
    try:
        client._request("PATCH",
                        f"/items/prod_preflight_reviews/{PARENT_PREFLIGHT_ID}",
                        data=body)
        print(f"[directus] PATCHed parent preflight {PARENT_PREFLIGHT_ID} with completion note")
        return True
    except DirectusError as exc:
        print(f"[directus] parent preflight patch failed: {exc.status} "
              f"{exc.detail[:500]}", file=sys.stderr)
        return False


def _register_activity(client, now, ld1_id, ld2_id):
    body = {
        "action": "preview_stitched_v3_phase_b_a_implementation_shipped",
        "module_id": 1,
        "performed_by": "claude_autonomous_overnight",
        "details": json.dumps({
            "task_id": TASK_ID,
            "preflight_id": V3_PREFLIGHT_ID,
            "parent_preflight_id": PARENT_PREFLIGHT_ID,
            "new_locked_decisions": [LD1_KEY, LD2_KEY],
            "new_ld_ids": {"v3_shipped": ld1_id, "ffmpeg_a1": ld2_id},
            "files_modified": [
                "Production/tools/production_server.py",
                "Production/tools/lib/ffmpeg_stitch.py",
                "Production/Event_1/storyboard_v38_prod.html",
            ],
            "files_created": [
                "Production/tools/patch_v38_phase_b.py",
                "Production/tools/tests/test_phase_b_panel.py",
                "Production/assets/phase_a/placeholder_empty_desk.png",
                "Production/assets/phase_a/placeholder_chipper_flyin.mov",
                "Production/assets/phase_a/placeholder_chipper_flyout.mov",
                "Production/assets/phase_a/placeholder_chipper_sitting.mov",
                "Production/assets/lipsync_bases/placeholder_cedric_base_v1.mp4",
                "Production/assets/watercolor_library/placeholder_breath_rub.png",
                "Production/assets/watercolor_library/placeholder_gentle_wave.png",
                "Production/assets/watercolor_library/placeholder_heart_bloom.png",
                "Production/assets/ambient_library/meditation_fireplace_v1.mp3",
                "Production/assets/ambient_library/ambient_silent_60s.mp3",
            ],
            "tests_pass": "130/130",
            "tests_new": 28,
            "placeholder_assets_shipped": True,
            "real_phase_a_assets_pending": "HANDOFF_PHASE_A_ASSET_GENERATION_20260419.md",
            "counter_p0_findings_resolved": {
                "HIGH-1_int_coerce": "per-field validator dispatch",
                "HIGH-2_lipsync_cache": "cache claim dropped; preview cache gets lipsync_mtime",
                "HIGH-3_fail_loud_assets": "resolve_watercolor_asset pre-check",
                "HIGH-4_mov_vs_mp4": "qtrle .mov for alpha; helper accepts both",
                "MEDIUM-5_json_key_order": "sort_keys=True on validator re-emit",
                "MEDIUM-6_recipe_hash": "WATERCOLOR_OVERLAY_RECIPE_HASH included",
                "MEDIUM-7_rollback_scrub": "documented in completion report",
            },
            "timestamp": now,
        }),
    }
    try:
        r = client._request("POST", "/items/prod_activity_log", data=body)
        aid = r.get("data", {}).get("id")
        print(f"[directus] prod_activity_log id={aid}")
        return aid
    except DirectusError as exc:
        print(f"[directus] activity_log failed: {exc.status} {exc.detail[:500]}",
              file=sys.stderr)
        return None


if __name__ == "__main__":
    sys.exit(main())
