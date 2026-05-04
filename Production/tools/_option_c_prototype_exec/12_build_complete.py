"""Log build-complete row on HOSTED Directus.

Marks the autonomous build phase done and documents what was verified +
what requires Kim's UI test. Writes the pre-verdict audit trail.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import hosted, TASK_ID, PREFLIGHT_ID, ORIGINAL_PREFLIGHT_ID, LD_ID  # type: ignore


def main():
    c = hosted()

    # Find Luna module
    modules = c.get("prod_modules", filters={"m_number": 2}, limit=1)
    module_id = modules[0]["id"] if modules else 0

    pre_verified = {
        "schema_created": {
            "collections": ["prod_storyboard_beats", "prod_video_candidates"],
            "fields_beats": 20,
            "fields_candidates": 7,
            "relations": [
                "prod_video_candidates.beat_id -> prod_storyboard_beats",
                "prod_storyboard_beats.selected_option -> prod_video_candidates",
            ],
        },
        "seed_data": {
            "beats": 33,
            "status_distribution": {"pending": 10, "animating": 8, "lipsyncing": 7, "approved": 8},
            "candidates": 99,
            "real_mp4_candidates": 4,  # 3 from beat_03 seed + 1 from real-Kling smoke
        },
        "presets": ["Kanban by Status (cdh-kanboard)", "Table (inline edit)"],
        "extensions_built_and_loaded": [
            "directus-extension-image-dragdrop",
            "directus-extension-video-compare",
            "directus-extension-kanboard (third-party)",
        ],
        "roles": ["kim_producer (14 grants)", "kim_admin (bootstrap)"],
        "flow": {
            "name": "Generate B+C (Kling)",
            "trigger": "manual",
            "operation": "request POST http://127.0.0.1:8090/animate",
            "validated": "webhook → adapter (dry-run), direct adapter POST → real Kling end-to-end",
        },
        "real_kling_smoke": {
            "beat": "beat_01",
            "task_id": "0b310bb3e9b746aeb49484095a19e437",
            "mp4_bytes": 7_494_596,
            "spend_usd": 0.45,
            "duration_s": 5,
        },
    }

    kim_gated = {
        "exit_1_workflow_speed_under_5min": "Kim runs 5-step test script against her Mac browser",
        "exit_2_drag_drop_robust_under_reactive": "Kim holds drag while concurrent Flow fires webhook on a different beat",
        "exit_3_kanban_refresh_under_10s": "Kim watches Kanban after Flow completes — database updates are proven, UI repaint timing is not",
        "exit_4_kanban_paint_under_3s_33_beats": "Kim loads the Kanban preset cold and times initial paint on her Mac",
        "exit_5_feel_score_7_or_higher_after_2hrs": "Kim plays producer for 2 hours of real work",
    }

    details = {
        "task_id": TASK_ID,
        "activity_type": "prototype_build_complete",
        "event": "autonomous_build_phase_done",
        "linked_preflight_id": PREFLIGHT_ID,
        "linked_original_preflight_id": ORIGINAL_PREFLIGHT_ID,
        "linked_decision_id": LD_ID,
        "local_directus_url": "http://localhost:8055",
        "adapter_url": "http://127.0.0.1:8090",
        "pre_verified_autonomously": pre_verified,
        "kim_gated_exit_criteria": kim_gated,
        "next_step": "Kim runs Production/Event_2/_option_c_prototype/KIM_TEST_SCRIPT.md then 11_decision_record.py",
        "teardown_command": "rm -rf ~/directus-prototype (hosted Directus sees no schema changes)",
        "deviations_from_ld204": [
            "Pivot to local Directus (npm+SQLite) due to zero extensions on hosted Railway — logged as LD-204 amendment 2026-04-17",
            "Kanban layout is third-party (directus-extension-kanboard) — Directus 11 has no native Kanban",
            "IMPORT_IP_DENY_LIST overridden in .env (default blocks 127.0.0.1; adapter lives on loopback)",
        ],
    }

    log = c.log_activity(
        module_id=module_id,
        action="option_c_prototype_build_complete",
        details=details,
        performed_by="claude-opus-4-7-terminal-cli",
    )
    print(f"Logged build-complete: prod_activity_log id={log['id']}")


if __name__ == "__main__":
    main()
