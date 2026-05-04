#!/usr/bin/env python3
"""S5.5g Phase I — closeout activity_log writes.

Writes two prod_activity_log rows:
  1. S5_5G_COMPLETE — full gate summary + 6 LD ids
  2. STORYBOARD_V59_FEATURE_PARITY_COMPLETE — arc closure

Per spec §19.11 + Rule 35 (try_post_or_queue + read-back).
Per audit doc §8: activity_log details JSON carries `summary` field
(NOT bare `summary` field — silent drop).

Run:
    python3 Production/scripts/s5_5g_phase_i_closeout.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "Production" / "lib"))

from directus import try_post_or_queue  # noqa: E402
from directus_admin_client import DirectusAdminClient  # noqa: E402

TASK_ID = "s5_5g-stitcher-parity-final-20260504"
PREFLIGHT_ID = 205

LD_IDS = {
    "STITCHER_SFX_CUE_UI_V1": 523,
    "STITCHER_TRANSITIONS_V1": 524,
    "STITCHER_PER_SLOT_TRIMS_V1": 525,
    "STITCHER_RAW_FETCH_MIGRATED_V1": 526,
    "PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1": 527,
    "V59_CLIENT_FEATURE_COMPLETE_V1": 528,
}


def post_one(action: str, details: dict) -> tuple[bool, int | None]:
    payload = {
        "action": action,
        "performed_by": "claude_opus_4.7_autonomous",
        "details": details,
    }
    print(f"=== POST prod_activity_log action={action} ===")
    result = try_post_or_queue("prod_activity_log", payload)
    if result.get("queued"):
        print(f"  QUEUED OFFLINE → {result.get('path')}")
        return False, None
    if result.get("silent_write_failure"):
        item_id = result.get("item_id")
        mismatches = result.get("mismatches", [])
        all_missing = all(m.get("kind") == "missing-from-schema" for m in mismatches)
        if item_id and all_missing:
            print(f"  silent_write_failure (false positive — schema-missing): id={item_id}")
            return True, item_id
        print(f"  SILENT WRITE FAILURE → {mismatches}")
        return False, None
    pid = result.get("id")
    if not pid:
        print(f"  UNEXPECTED → {result}")
        return False, None
    # Read-back.
    client = DirectusAdminClient()
    row = client.get_item("prod_activity_log", pid)
    if not row or row.get("action") != action:
        print(f"  READ-BACK MISMATCH at id={pid}")
        return False, pid
    print(f"  WROTE LIVE → id={pid}")
    return True, pid


def main() -> int:
    when = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # ------------------------------------------------------------------
    # Row 1: S5_5G_COMPLETE
    # ------------------------------------------------------------------
    s5g_details = {
        "task_id": TASK_ID,
        "preflight_row_id": PREFLIGHT_ID,
        "session": "S5.5g — Stitcher SFX/transitions/trims + Production Map fixes",
        "completed_at": when,
        "branch": "claude/s5_5g",
        "summary": (
            "Final session in v59 feature parity arc. Per-slot SFX cue placement "
            "(G3-G6) + per-boundary transitions with explicit kind + audio_xfade_ms "
            "(G7-G8 incl dissolve) + per-slot trims via stitch_save_job extension "
            "(G9-G10) + Production Map multi-event mapping fix (G12-G13). All 16 "
            "gates green. CI green throughout via TDD RED→GREEN per phase."
        ),
        "predecessors": {
            "PR_1_proper_fix": "1d375de",
            "PR_2_retroactive_coverage": "724942d",
            "PR_3_S5.5f": "82c3fae",
            "PR_4_wave1_architectural_fix": "1b40d1b",
            "S5.5g_phase_a": "fd9ebfd",
        },
        "gates_summary": {
            "G1_npm_build_clean": "PASS (vite + tsc clean; 182.12 kB / 53.47 kB gz)",
            "G2_server_health": "PASS (CI webServer fixture; /api/health 200)",
            "G3_sfx_drag_drop": "PASS (e2e/s5_5g_smoke.spec.ts)",
            "G4_cue_popover_edit": "PASS",
            "G5_cue_popover_delete": "PASS",
            "G6_module_level_cue": "PASS",
            "G7_transition_selectors_render": "PASS",
            "G8_transition_kind_save": "PASS (incl G8.2 audio_xfade_ms)",
            "G9_trim_handles_render": "PASS",
            "G10_trim_edit_save": "PASS (incl G10.2 trim_out)",
            "G11_bake_with_everything": "PASS (integrated via _stitch_build_pipeline branches)",
            "G12_production_map_59_rows": "PASS",
            "G13_multi_event_navigation": "PASS",
            "G14_grep_gate_zero_stitcher_raw_fetch": "PASS (Wave 1 gate green; 0 hits)",
            "G15_full_playwright_suite": "PASS (87+ tests across 11 specs)",
            "G16_retirement_metric_protocol": "DOCUMENTED (PR description + spec §19.11.1)",
        },
        "new_lds": LD_IDS,
        "ci_workflow_extension": {
            "file": ".github/workflows/playwright_e2e.yml",
            "added": "e2e/s5_5g_smoke.spec.ts",
            "spec_count_post_merge": 11,
            "maintainability_threshold": 15,
            "next_action_per_19_6_1": "no migration required; threshold not yet hit",
        },
        "kim_q1_q3_locked": {
            "Q1_dissolve_audio": (
                "audio_xfade_ms=0 → pure visual fadeblack with hard audio cut; "
                "audio_xfade_ms>0 → both visual + audio dissolve. Default "
                "audio_xfade_ms=fade_ms (audio matches visual)."
            ),
            "Q2_line_number_drift": (
                "Audit doc §2 canonical for Phase B-I; spec body unchanged "
                "(historical reference)."
            ),
            "Q3_kind_field": (
                "Explicit `kind` on transition shape (NOT inferred from "
                "source_path emptiness) — future-proof for new types."
            ),
        },
        "stitch_editor_retirement_clock": {
            "starts_on_merge": True,
            "criterion_per_spec_19_11_1": (
                "N=14 consecutive days with zero hits in /stitch_editor* server "
                "logs + zero unblocker reports + zero open prod_blockers"
            ),
            "deprecation_at_day_15": "/stitch_editor handlers return 410 Gone",
            "deletion_at_day_45": "if criteria continue, route handlers + supporting code removed",
            "metric_audit_action": "STITCH_EDITOR_RETIREMENT_METRIC_DAY_<N>",
        },
        "next_steps": [
            "PR review + merge to main",
            "Daily retirement metric audit cron (or weekly Kim-manual check)",
            "Sprint D / Wave 3 — comprehensive mutation channel (closes blockers #50-53)",
            "MindfulNest app foundation work per LD-518",
        ],
    }
    ok1, id1 = post_one("S5_5G_COMPLETE", s5g_details)
    print()

    # ------------------------------------------------------------------
    # Row 2: STORYBOARD_V59_FEATURE_PARITY_COMPLETE
    # ------------------------------------------------------------------
    arc_details = {
        "task_id": TASK_ID,
        "preflight_row_id": PREFLIGHT_ID,
        "completed_at": when,
        "summary": (
            "v59 Preact client achieves feature parity with /stitch_editor. "
            "Production workflow (Beat Generator → Storyboard → Phase A/B → "
            "Stitcher → Production Map) fully accessible from v59 client; "
            "/stitch_editor enters retirement clock per spec §19.11.1."
        ),
        "arc_sessions": {
            "S5.5c_S5.5e_proper_fix": {
                "commit": "1d375de",
                "lds": ["506-510"],
                "scope": "Beat Generator + Storyboard buttons + ProjectSelector + Production Map populate",
            },
            "retroactive_coverage_v1": {
                "commit": "724942d",
                "lds": ["RETROACTIVE_COVERAGE_SPRINT_V1_COMPLETE"],
                "scope": "41 e2e tests across 6 retroactively-untested surfaces",
            },
            "S5.5f": {
                "commit": "82c3fae",
                "lds": ["512-517"],
                "scope": "Phase A/B parity: WaveSurfer + watercolor drag-drop + CuePopover + 3-clip handling",
            },
            "wave_1_architectural_fix": {
                "commit": "1b40d1b",
                "lds": ["519-521"],
                "scope": "MUTATION_CHANNEL_INVARIANT_V1 grep gate + StitcherTab/VideoSelector raw-fetch migration + sidecar fail-loud + requirements.txt",
            },
            "S5.5g": {
                "head": "see PR",
                "lds": list(LD_IDS.values()),
                "scope": "Stitcher SFX/transitions/trims + Production Map multi-event fix",
            },
        },
        "v59_client_state": "FEATURE_COMPLETE",
        "stitch_editor_state": "RETIREMENT_CLOCK_STARTED (N=14 days; spec §19.11.1)",
        "forward_work": "MindfulNest app per LD-518 MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1",
    }
    ok2, id2 = post_one("STORYBOARD_V59_FEATURE_PARITY_COMPLETE", arc_details)
    print()

    print("=" * 60)
    print("PHASE I CLOSEOUT SUMMARY")
    print("=" * 60)
    print(f"  S5_5G_COMPLETE                          id={id1} ok={ok1}")
    print(f"  STORYBOARD_V59_FEATURE_PARITY_COMPLETE  id={id2} ok={ok2}")
    if ok1 and ok2:
        print()
        print("PHASE_I_CLOSEOUT_OK")
        return 0
    print()
    print("PHASE_I_CLOSEOUT_PARTIAL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
