"""Foundation: Event_2 scaffold on disk, session-start audit log on hosted,
and a connectivity probe against local Directus.

Event_2 folder lives in the Dropbox project tree so any seed files we write
alongside the prototype are under the same governance as the rest of the
production content.
"""
from __future__ import annotations
import sys, os, json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import hosted, local, TASK_ID, PREFLIGHT_ID, ORIGINAL_PREFLIGHT_ID, LD_ID  # type: ignore

DROPBOX_ROOT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
EVENT_2 = DROPBOX_ROOT / "Production" / "Event_2"

def create_event2_scaffold():
    (EVENT_2).mkdir(parents=True, exist_ok=True)
    (EVENT_2 / "animation_clips").mkdir(exist_ok=True)
    (EVENT_2 / "_option_c_prototype").mkdir(exist_ok=True)

    readme = EVENT_2 / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Event_2 (Luna, M2)\n\n"
            "Created 2026-04-17 for Option C Directus-as-UI prototype execution "
            f"(task_id={TASK_ID}, preflight id={PREFLIGHT_ID}, LD id={LD_ID}).\n\n"
            "`animation_clips/` will hold the 33 Luna M2 beat videos; during the "
            "prototype, these are SYMLINKED or REFERENCED from Event_1 clips to "
            "avoid duplicating multi-MB mp4s across the Dropbox sync tree.\n\n"
            "`_option_c_prototype/` holds prototype-only scratch state (seed "
            "manifests, Kim-test script) — deleted on prototype teardown.\n"
        )
    print(f"Event_2 scaffold: {EVENT_2}")
    return EVENT_2

def verify_local_directus():
    c = local()
    info = c._request("GET", "/server/info")
    print(f"Local Directus /server/info -> setup={info['data']['setupCompleted']}, "
          f"mcp={info['data']['mcp_enabled']}")

def log_session_start():
    c = hosted()

    # Find a module_id for Luna M2 to hang the activity log row on. If not
    # present, use 0 (activity log accepts module_id=0 for infrastructure work).
    modules = c.get("prod_modules", filters={"m_number": 2}, limit=1)
    module_id = modules[0]["id"] if modules else 0

    details = {
        "task_id": TASK_ID,
        "preflight_id": PREFLIGHT_ID,
        "original_preflight_id": ORIGINAL_PREFLIGHT_ID,
        "linked_decision_id": LD_ID,
        "event": "prototype_execution_started",
        "pivot": "local-directus-via-npm (amended to LD-204)",
        "local_directus_url": "http://localhost:8055",
        "event_2_scaffold_path": str(EVENT_2),
        "node_version": "v22.11.0",
        "directus_version": "11 (sqlite3 dev)",
        "stop_conditions": {
            "wall_clock_hours": 8,
            "spend_usd_cap": 50,
            "event_1_state": "untouched",
        },
    }

    logged = c.log_activity(
        module_id=module_id,
        action="option_c_prototype_execution_started",
        details=details,
        performed_by="claude-opus-4-7-terminal-cli",
    )
    log_id = logged.get("id")
    print(f"Session start logged: prod_activity_log id={log_id}")

    # Patch the FK on preflight id=48 so the audit can join on it
    try:
        c.update("prod_preflight_reviews", PREFLIGHT_ID, {
            "related_activity_log_id": log_id,
        })
        print(f"Linked prod_preflight_reviews id={PREFLIGHT_ID} -> activity_log id={log_id}")
    except Exception as e:
        print(f"WARN: could not link preflight FK: {e}")

    return log_id

def main():
    create_event2_scaffold()
    verify_local_directus()
    log_session_start()

if __name__ == "__main__":
    main()
