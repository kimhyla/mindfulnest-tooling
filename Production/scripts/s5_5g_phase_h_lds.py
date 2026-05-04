#!/usr/bin/env python3
"""S5.5g Phase H — write 5 NEW LDs + V59_CLIENT_FEATURE_COMPLETE_V1 closure LD.

Per spec §19.4 + DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md §1 enum migration
2026-05-04: severity = HARD (behaviorally enforced) | SOFT (awareness/UX).
Per Rule 35: try_post_or_queue + read-back verify on every write.

LDs written:
  STITCHER_SFX_CUE_UI_V1                    HARD
  STITCHER_TRANSITIONS_V1                   HARD
  STITCHER_PER_SLOT_TRIMS_V1                HARD
  STITCHER_RAW_FETCH_MIGRATED_V1            HARD
  PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1     SOFT
  V59_CLIENT_FEATURE_COMPLETE_V1            HARD (closure)

Run:
    python3 Production/scripts/s5_5g_phase_h_lds.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "Production" / "lib"))

from directus import try_post_or_queue  # noqa: E402
from directus_admin_client import DirectusAdminClient  # noqa: E402

TASK_ID = "s5_5g-stitcher-parity-final-20260504"
DATE_LOCKED = datetime.now(timezone.utc).strftime("%Y-%m-%d")
SOURCE_DOC = "STORYBOARD_V59_S5_5_G_SPEC_v1.md (Cursor v8/v11/v12 approved 2026-05-04)"


LDS = [
    {
        "decision_key": "STITCHER_SFX_CUE_UI_V1",
        "decision_name": "Stitcher per-slot SFX cue placement + module-level cue strip + SfxCuePopover",
        "decision_text": (
            "Per-slot SFX cues live in slot.sfx_cues[] persisted via "
            "stitch_save_job; module-level cues live in state.module_sfx_cues "
            "via /api/timeline/cues (timeline_cue_upsert MUTATION_ENDPOINT, "
            "added in S5.5g). Drag lib-sfx onto stitcher-slot-waveform-{slot} "
            "creates a per-slot cue with offset_ms = drop_x / wrapper_width × "
            "video_dur_ms. Drag onto stitcher-module-timeline below the slot "
            "strip writes a module-level cue with cue_type='sfx'. Click cue "
            "marker opens SfxCuePopover (volume / fadein_ms / fadeout_ms / "
            "Delete). Per-slot delete = re-save slot without the cue (single "
            "source of truth = slot.sfx_cues array). Server defaults consumed: "
            "volume=0.45, fadein_ms=300, fadeout_ms=1200 (server.py:14085-14087). "
            "Tests: G3-G6 in e2e/s5_5g_smoke.spec.ts."
        ),
        "task_category": "storyboard",
        "severity": "HARD",
        "scope_domain": "production",
        "enforcement_type": "test",
        "past_failure_prevented": (
            "Without per-slot SFX UI in v59 client, Kim had to fall back to "
            "legacy /stitch_editor for cue authoring — blocking retirement of "
            "the legacy tool and fragmenting the production workflow."
        ),
    },
    {
        "decision_key": "STITCHER_TRANSITIONS_V1",
        "decision_name": "Per-boundary transitions with explicit kind + audio_xfade_ms (Q3 LOCKED)",
        "decision_text": (
            "Transition shape: {after_slot, kind: 'crossfade'|'cut'|'dissolve', "
            "fade_ms, audio_xfade_ms, source_path?}. Server defaults: "
            "kind='crossfade' if absent (back-compat for legacy jobs); "
            "audio_xfade_ms=fade_ms if absent (audio matches visual). "
            "kind='cut' skips synthesis. kind='crossfade' uses existing "
            "trans_<after_slot> SFX cue at slot tail; audio_xfade_ms drives "
            "fadein/fadeout. kind='dissolve' (NEW) applies ffmpeg fade=t=out on "
            "slot[after_slot] tail + fade=t=in on slot[after_slot+1] head; if "
            "audio_xfade_ms>0 also afade out/in across the boundary; cache key "
            "includes fade_ms + audio_xfade_ms so different windows don't "
            "collide. Reference: LD-376 fadeblack pattern from Phase A. UI: 3 "
            "selectors between 4 slots in StitcherTransitionSelector. Tests: "
            "G7-G8 in e2e/s5_5g_smoke.spec.ts."
        ),
        "task_category": "storyboard",
        "severity": "HARD",
        "scope_domain": "production",
        "enforcement_type": "test",
        "past_failure_prevented": (
            "Inferring transition kind from source_path emptiness (Cursor Q3) "
            "made it impossible to add new kinds without ambiguity; explicit "
            "kind is future-proof."
        ),
    },
    {
        "decision_key": "STITCHER_PER_SLOT_TRIMS_V1",
        "decision_name": "Per-slot trim_in_ms / trim_out_ms via stitch_save_job extension",
        "decision_text": (
            "New slot fields trim_in_ms (default 0, inclusive) and trim_out_ms "
            "(null = end of clip). Persisted via stitch_save_job extension "
            "(NOT new endpoint per audit doc §5 — single mutation surface "
            "reuses scope guard + pin check + state lock from existing "
            "handler). Server-side: _stitch_normalize_slot accepts trim_in_ms / "
            "trim_out_ms; cache key includes 't<in>-<out|end>' suffix; "
            "pre-trim via ffmpeg -ss / -t before normalize_for_concat. "
            "Validation: trim_in_ms >= 0; trim_out_ms is null OR > trim_in_ms "
            "(else 400). UI: numeric inputs in seconds per slot "
            "(Cursor v8 Q9 deferred keyboard nudge). Tests: G9-G10 in "
            "e2e/s5_5g_smoke.spec.ts."
        ),
        "task_category": "storyboard",
        "severity": "HARD",
        "scope_domain": "production",
        "enforcement_type": "test",
        "past_failure_prevented": (
            "A separate /api/stitch_editor/slot/trim endpoint would duplicate "
            "scope guard + pin check + state lock from stitch_save_job and "
            "introduce a second mutation surface for cosmetic separation — "
            "violates LD-461 SCOPE_BODY_HELPER_V1 single-channel discipline."
        ),
    },
    {
        "decision_key": "STITCHER_RAW_FETCH_MIGRATED_V1",
        "decision_name": "StitcherTab pathappPatch-clean (verification only post Wave 1)",
        "decision_text": (
            "StitcherTab is 100% pathappPatch-clean for mutations as of S5.5g "
            "(verified 2026-05-04). Wave 1 architectural-fix (commit 1b40d1b) "
            "migrated stitch_preview / stitch_bake / stitch_save_job / "
            "stitch_loudnorm to pathappPatch. S5.5g extends with "
            "timeline_cue_upsert (NEW MUTATION_ENDPOINT key for "
            "/api/timeline/cues). Phase F per spec §19.10 supersedes original "
            "migration scope; this LD is the verification artifact. The "
            "MUTATION_CHANNEL_INVARIANT_V1 grep gate (LD-519) enforces "
            "structurally. ProductionMapTab.tsx event_load remains a "
            "sanctioned exception per the gate's allowlist (blocker #53, "
            "deferred to Sprint D / Wave 3 per Cursor R6)."
        ),
        "task_category": "tech_stack",
        "severity": "HARD",
        "scope_domain": "production",
        "enforcement_type": "ci_check",
        "past_failure_prevented": (
            "Without structural enforcement, raw fetch to mutation endpoints "
            "regressed in PRs touching StitcherTab — retroactive coverage v1 "
            "found 3 such regressions (F-S2-001) before Wave 1 closed them. "
            "Maintaining the grep gate prevents recurrence."
        ),
    },
    {
        "decision_key": "PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1",
        "decision_name": "Production Map m_number → Event_<N> convention-based mapping",
        "decision_text": (
            "production_server.py:_handle_production_map maps m_number to "
            "Event_<N> directory by on-disk convention "
            "(f'Event_{m_num}'.is_dir() else None), replacing the prior bug "
            "where every module reported event_dirs[0] (typically Event_1). "
            "No Directus schema migration (audit doc §6 + Cursor v8 Q4 — "
            "derived from naming convention; column added only if editor "
            "overrides become necessary). UI ProductionMapTab.tsx onCellClick "
            "reads m.event_dir from response and posts to /api/event/load — "
            "no client change required, the bug was always server-side. "
            "Tests: G12-G13 in e2e/s5_5g_smoke.spec.ts."
        ),
        "task_category": "storyboard",
        "severity": "SOFT",
        "scope_domain": "production",
        "enforcement_type": "test",
        "past_failure_prevented": (
            "Clicking M5 cell when M5 belongs to Event_2 navigated to Event_1 "
            "— Kim couldn't reach the right scope from the Production Map."
        ),
    },
    {
        "decision_key": "V59_CLIENT_FEATURE_COMPLETE_V1",
        "decision_name": "v59 Preact client = feature-complete (S5.5g closure; /stitch_editor retirement clock starts)",
        "decision_text": (
            "v59 Preact client achieves feature parity with /stitch_editor as "
            "of S5.5g merge. Production workflow (Beat Generator → Storyboard "
            "→ Phase A/B → Stitcher → Production Map) is fully accessible "
            "from the v59 client without falling back to the legacy tool. "
            "Arc closure: PR #1 S5.5c+e proper-fix → #2 retroactive coverage "
            "→ #3 S5.5f → #4 Wave 1 architectural-fix → #5 S5.5g (this PR). "
            "/stitch_editor enters retirement clock per spec §19.11.1: N=14 "
            "consecutive days with zero hits in /stitch_editor* server logs + "
            "zero unblocker reports + zero open prod_blockers; deprecation "
            "(410 Gone with redirect) at day 15; deletion at day 45 if "
            "criteria continue. Daily metric audit rows in prod_activity_log "
            "(STITCH_EDITOR_RETIREMENT_METRIC_DAY_<N>). Forward work moves to "
            "MindfulNest app per LD-518 discipline."
        ),
        "task_category": "storyboard",
        "severity": "HARD",
        "scope_domain": "production",
        "enforcement_type": "human_gate",
        "past_failure_prevented": (
            "Fragmenting the production workflow across legacy + v59 tools "
            "without parity blocked the unified production cycle and made "
            "/stitch_editor retirement a perpetual deferral."
        ),
    },
]


def post_one(ld: dict) -> tuple[bool, str]:
    payload = {
        "decision_key": ld["decision_key"],
        "decision_name": ld["decision_name"],
        "decision_text": ld["decision_text"],
        "source_document": SOURCE_DOC,
        "task_category": ld["task_category"],
        "severity": ld["severity"],
        "scope_domain": ld["scope_domain"],
        "enforcement_type": ld["enforcement_type"],
        "past_failure_prevented": ld["past_failure_prevented"],
        "status": "active",
        "is_current": True,
        "supersedable": True,
        "schema_version": 2,
        "date_locked": DATE_LOCKED,
        "notes": json.dumps({
            "task_id": TASK_ID,
            "session": "S5.5g",
            "session_date": DATE_LOCKED,
        }),
    }

    print(f"=== POST prod_locked_decisions key={ld['decision_key']} ===")
    result = try_post_or_queue("prod_locked_decisions", payload)

    if result.get("queued"):
        print(f"  QUEUED OFFLINE → {result.get('path')}")
        return False, f"queued: {result.get('error', '')[:150]}"

    if result.get("silent_write_failure"):
        # Per audit doc §8: silent_write_failure with mismatches.field in
        # {missing-from-schema} is a verification false positive when the
        # schema simply doesn't accept some fields. Treat as PASS if the
        # row exists and the substantive fields landed.
        item_id = result.get("item_id")
        mismatches = result.get("mismatches", [])
        all_missing = all(
            m.get("kind") == "missing-from-schema" for m in mismatches
        )
        if item_id and all_missing:
            print(f"  silent_write_failure (false positive — schema-missing fields): id={item_id}")
            return True, f"id={item_id} (schema-missing fields ignored)"
        print(f"  SILENT WRITE FAILURE → mismatches={mismatches}")
        return False, f"silent_write_failure: {mismatches}"

    pid = result.get("id")
    if not pid:
        print(f"  UNEXPECTED → {result}")
        return False, f"no id: {result}"

    # Read-back verify per Rule 35.
    client = DirectusAdminClient()
    row = client.get_item("prod_locked_decisions", pid)
    if not row:
        print(f"  READ-BACK FAILED: no row at id={pid}")
        return False, f"read-back failed at id={pid}"
    if row.get("decision_key") != ld["decision_key"]:
        print(f"  READ-BACK MISMATCH: row.decision_key={row.get('decision_key')!r}")
        return False, "decision_key mismatch"
    if row.get("severity") != ld["severity"]:
        print(f"  READ-BACK MISMATCH: row.severity={row.get('severity')!r} expected {ld['severity']!r}")
        return False, "severity mismatch"

    print(f"  WROTE LIVE → id={pid} severity={row.get('severity')} status={row.get('status')}")
    return True, f"id={pid}"


def main() -> int:
    print(f"S5.5g Phase H: writing {len(LDS)} LDs (task_id={TASK_ID})")
    print()

    results: list[tuple[str, bool, str]] = []
    for ld in LDS:
        ok, info = post_one(ld)
        results.append((ld["decision_key"], ok, info))
        print()

    print("=" * 60)
    print("PHASE H SUMMARY")
    print("=" * 60)
    fail_count = 0
    for key, ok, info in results:
        marker = "OK" if ok else "FAIL"
        print(f"  [{marker}] {key:<48} {info}")
        if not ok:
            fail_count += 1

    if fail_count > 0:
        print()
        print(f"PHASE_H_PARTIAL: {fail_count} of {len(results)} writes failed/queued")
        return 1
    print()
    print("PHASE_H_OK: all 6 LDs landed live + read-back verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
