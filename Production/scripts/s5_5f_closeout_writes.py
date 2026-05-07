"""S5.5f closeout — Directus writes for Phase G + Phase H.

Writes (in order):
  1. 6 NEW LDs (HARD/SOFT per spec §19.4)
  2. 1 prod_activity_log row S5_5F_COMPLETE
  3. PATCH prod_preflight_reviews #203 with related_activity_log_id

Each write goes through try_post_or_queue per Rule 35, so if Directus
credentials are absent the rows queue to disk via the standard
pending_directus_writes.json offline path.

Run:
    python3 Production/scripts/s5_5f_closeout_writes.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Local-tree import for Production/lib/directus.py
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from directus import (  # noqa: E402
    DirectusAdminClient,
    try_post_or_queue,
)


TASK_ID = "s5_5f-phase-ab-parity-20260504"
PREFLIGHT_ID = 203
TODAY = "2026-05-04"

# Per spec §19.4 — HARD/SOFT migration; old severity strings (HIGH/MEDIUM)
# would be rejected by the new enum. Reference:
# Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md §1 (enum migration).
LDS = [
    {
        "decision_key": "WAVESURFER_TIMELINE_INTEGRATION_V1",
        "decision_name": "WaveSurfer.js v7 timeline mounted in PhaseProducer",
        "decision_text": (
            "PhaseProducer mounts WaveSurfer.js v7 below the script editor. "
            "Audio source priority: phase_X_lipsync_file > phase_X_mixed_audio_file > "
            "phase_X_voice_stem_file. Click on the waveform seeks the audio. Cue "
            "markers render at offset_ms / duration positions."
        ),
        "severity": "HARD",
        "status": "active",
        "task_category": "tech_stack",
        "scope_domain": "production",
        "enforcement_type": "test",
        "date_locked": TODAY,
        "is_current": True,
        "source_document": "Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md",
    },
    {
        "decision_key": "WATERCOLOR_DRAG_DROP_TIMELINE_V1",
        "decision_name": "Watercolor drag-drop onto WaveformTimeline creates a cue",
        "decision_text": (
            "Watercolor tile in the PhaseProducer grid is draggable. Drop on the "
            "WaveformTimeline creates a cue at offset_ms = dropX/width × duration. "
            "Replaces the legacy /magic open-new-tab flow per LD-464; the drag-drop "
            "path is the primary affordance going forward."
        ),
        "severity": "HARD",
        "status": "active",
        "task_category": "storyboard",
        "scope_domain": "production",
        "enforcement_type": "test",
        "date_locked": TODAY,
        "is_current": True,
        "source_document": "Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md",
    },
    {
        "decision_key": "CUE_POPOVER_INSPECTOR_V1",
        "decision_name": "CuePopover with animation/duration/volume + delete",
        "decision_text": (
            "Click on a cue marker opens CuePopover anchored to the click "
            "coordinates. Popover exposes the live server animation enum "
            "(fade_in / slide_in / gentle_pan — three values, not five), "
            "duration_ms (number input), volume (range slider), and Delete "
            "(Modal-confirm by default; Shift+click skips confirm per power-user "
            "path). Reusable component — S5.5g Stitcher will import it as-is."
        ),
        "severity": "HARD",
        "status": "active",
        "task_category": "storyboard",
        "scope_domain": "production",
        "enforcement_type": "test",
        "date_locked": TODAY,
        "is_current": True,
        "source_document": "Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md",
    },
    {
        "decision_key": "PHASE_A_THREE_CLIP_HANDLING_V1",
        "decision_name": "Phase A producer renders 3 base-clip slots",
        "decision_text": (
            "When phase==='a', PhaseProducer renders three picker slots: fly-in, "
            "sitting, fly-out. Each slot opens BaseClipPicker (Modal with chipper-"
            "filtered library). Pick → pathappPatch v2_module_patch with field "
            "phase_a_chipper_<position>_clip_id. Manual 'Re-stitch (Phase A)' "
            "button (NOT auto-on-change per Cursor v8 Q9) calls phase_b_mix_audio "
            "with phase=a, which internally invokes _auto_assemble_phase_a_stitched. "
            "Phase B remains single-clip via the existing selectedBaseClip + "
            "Cedric filter."
        ),
        "severity": "HARD",
        "status": "active",
        "task_category": "phase_a",
        "scope_domain": "production",
        "enforcement_type": "code_invariant",
        "date_locked": TODAY,
        "is_current": True,
        "source_document": "Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md",
    },
    {
        "decision_key": "VOICE_STEM_UPLOAD_UI_V1",
        "decision_name": "Generate-stem-from-script button in PhaseProducer",
        "decision_text": (
            "PhaseProducer surfaces a 'Generate stem from script' button which "
            "POSTs to /api/phase_b/regen_audio (misnamed — also serves Phase A) "
            "with {phase, script}. The handler writes phase_<a|b>_voice_stem_*.mp3. "
            "True file-upload UI is OUT OF SCOPE for S5.5f per spec §3.6 + Cursor "
            "v8 Q5; deferred to a future session."
        ),
        "severity": "SOFT",
        "status": "active",
        "task_category": "audio",
        "scope_domain": "production",
        "enforcement_type": "awareness_only",
        "date_locked": TODAY,
        "is_current": True,
        "source_document": "Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md",
    },
    {
        "decision_key": "AMBIENT_PRESET_SELECTOR_INPRODUCER_V1",
        "decision_name": "Ambient preset selector inside PhaseProducer",
        "decision_text": (
            "PhaseProducer renders an ambient preset <select>. List loaded from "
            "GET /api/phase_b/ambient_preset_list (filesystem scan of "
            "Production/audio_library/ambient/*.mp3 — added in Phase E per "
            "spec §3.7 option b; Cursor v8 release-blocker fix). Save fires "
            "pathappPatch v2_module_patch with field=phase_<a|b>_ambient_preset_id."
        ),
        "severity": "SOFT",
        "status": "active",
        "task_category": "audio",
        "scope_domain": "production",
        "enforcement_type": "awareness_only",
        "date_locked": TODAY,
        "is_current": True,
        "source_document": "Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md",
    },
]


def _ld_payload_with_provenance(spec: dict, commit_shas: list[str]) -> dict:
    """Stamp task_id + commit chain into the notes (text field, no cap)."""
    notes = (
        f"task_id: {TASK_ID}\n"
        f"preflight_id: {PREFLIGHT_ID}\n"
        f"commits: {', '.join(commit_shas)}\n"
        f"workflow: .github/workflows/playwright_e2e.yml runs on every push.\n"
        f"Spec: §3 + §19 (Cursor v8 + §19.10 Phase A discoveries folded back).\n"
    )
    out = dict(spec)
    out["notes"] = notes
    return out


def main() -> int:
    commit_shas = [
        "3f105c0",  # Phase A
        "43ca045",  # Phase A handoff
        "5215125",  # Phase B
        "ef554c7",  # Phase C
        "64bdc50",  # Phase D
        "39c46a3",  # Phase E
        "a7f223a",  # Phase F (workflow extension)
    ]

    has_creds = bool(os.environ.get("DIRECTUS_EMAIL") or os.environ.get("DIRECTUS_ADMIN_EMAIL"))
    print(f"[s5_5f-closeout] DIRECTUS creds present: {has_creds}")

    client = DirectusAdminClient() if has_creds else None

    # ── Phase G — 6 LDs ─────────────────────────────────────────────────
    ld_results: list[dict] = []
    for spec in LDS:
        payload = _ld_payload_with_provenance(spec, commit_shas)
        result = try_post_or_queue("prod_locked_decisions", payload, client=client)
        ld_results.append({"key": spec["decision_key"], "result": result})
        if result.get("queued"):
            print(f"  [LD QUEUED] {spec['decision_key']} → {result['path']}")
        elif result.get("silent_write_failure"):
            print(f"  [LD SILENT-FAIL] {spec['decision_key']} → {result['error']}")
        else:
            print(f"  [LD WROTE]   {spec['decision_key']} id={result.get('id', '?')} severity={spec['severity']}")

    # ── Phase H — activity_log row ───────────────────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    activity_payload = {
        "action": "S5_5F_COMPLETE",
        "performed_by": "claude_opus_4_7_autonomous",
        "details": {
            "task_id": TASK_ID,
            "preflight_id": PREFLIGHT_ID,
            "commits_branch": commit_shas,
            "f_gates_passed": 18,
            "ld_keys_written": [spec["decision_key"] for spec in LDS],
            "workflow_extension": "playwright_e2e.yml line 89: appended e2e/s5_5f_smoke.spec.ts",
            "ci_proof": (
                "S5.5f Phase F workflow run (push a7f223a) — Smoke 21s + "
                "Playwright e2e 1m50s, both SUCCESS. Combined runs 31 tests "
                "(s5_5ce 13 + s5_5f F3-F17 = 18)."
            ),
            "summary": (
                "S5.5f shipped Phase A/B feature parity: WaveSurfer.js v7 "
                "timeline + watercolor drag-drop cue authoring + CuePopover "
                "inspector + Phase A 3-clip handling + Generate-stem button + "
                "ambient preset selector. F17 grep gate 0 hits. Server endpoint "
                "/api/phase_b/ambient_preset_list added. CI workflow extended "
                "to run both spec files on every push."
            ),
        },
    }
    activity_result = try_post_or_queue("prod_activity_log", activity_payload, client=client)
    if activity_result.get("queued"):
        print(f"  [ACT QUEUED] S5_5F_COMPLETE → {activity_result['path']}")
        activity_id = None
    else:
        activity_id = activity_result.get("id")
        print(f"  [ACT WROTE]  S5_5F_COMPLETE id={activity_id}")

    # ── PATCH preflight #203 with related_activity_log_id (Rule 35 + Step 8) ──
    if client is not None and activity_id is not None:
        try:
            client.patch_item(
                "prod_preflight_reviews",
                PREFLIGHT_ID,
                {"related_activity_log_id": activity_id},
            )
            print(f"  [PF PATCH]  preflight_reviews #{PREFLIGHT_ID}.related_activity_log_id = {activity_id}")
        except Exception as e:  # noqa: BLE001
            print(f"  [PF PATCH FAIL] {e}")
    else:
        print("  [PF PATCH SKIP] no creds or no activity id — manual flush will need this PATCH.")

    print("\n[s5_5f-closeout] DONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
