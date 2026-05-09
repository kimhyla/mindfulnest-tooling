"""Amend LD-204 with post-approval execution pivot to local Directus.

Per Kim directive 2026-04-17: log as amendment to existing decision 204,
not a new LD. PATCH decision_text to append AMENDMENT block.
"""
from __future__ import annotations
import sys, json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
PROD_ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(PROD_ROOT / "tools"))

from credentials_lib.directus import DirectusClient  # type: ignore

EMAIL = "kimhyla11@gmail.com"
PASSWORD = "directus11$"
BASE = "https://directus-production-3460.up.railway.app"

AMENDMENT_MARKER = "AMENDMENT 2026-04-17 (post-approval execution pivot):"

AMENDMENT = f"""

---

{AMENDMENT_MARKER}

Execution-session discovery (preflight id=48, task_id=option-c-prototype-exec-20260417):
hosted Directus on Railway has zero extensions installed, no Dockerfile in this repo,
and no `extensions/` volume mount on the Railway service. Deploying custom Vue
interfaces (drag-drop image assignment + 3-up A/B/C video compare) to the hosted
Directus would require a Railway deploy-pipeline build-out (~2-3 hrs, touches prod
infra — high blast radius on the live dashboard that all current production work
depends on). That cost was not counted in the original ~8hr prototype budget and
was not surfaced in preflight 47. Additionally, docker is not installed on Kim's
Mac, so a docker-compose-based local Directus is also unavailable in this session.

PIVOT (approved by Kim 2026-04-17): run the prototype against a LOCAL Directus v11
instance installed via npm directly (no Docker required). Node v22 is available on
Kim's Mac; Directus ships with built-in SQLite support for development, which
eliminates the need for a separate Postgres container. Extensions load from a
local `extensions/` folder with `EXTENSIONS_AUTO_RELOAD=true`, and the
"Generate B+C" Flow can reach `production_server.py` on localhost directly
(no tunnel required). This is the cheapest and most honest way to answer the
falsification question: does drag-drop survive reactive Flow updates in Vue
custom-interface land?

WHAT THE PIVOT CHANGES:
- All prototype Directus writes (new prod_storyboard_beats + prod_video_candidates
  collections, seed beats, Flow definition) happen in the LOCAL Directus SQLite DB,
  not hosted Postgres. Hosted Directus stays untouched except for audit rows
  (prod_activity_log + prod_preflight_reviews) that track this execution session.
- Exit Criterion #5 ("feels like my tool" after 2hrs) is tested against local
  Directus. This slightly weakens the "feels like production" test because the
  data does not live where Kim's real workflow lives — but it cleanly answers
  criteria 1-4 (workflow speed, drag-drop robustness, webhook refresh, Kanban
  paint performance). Kim's feel-score interpretation should account for this.
- The Railway deploy-pipeline build-out becomes part of the post-prototype full
  Option C commit work (originally ~90 Kim-active-hrs) if the prototype passes,
  NOT part of the prototype itself.

WHAT THE PIVOT PRESERVES:
- Same 5 exit criteria, same 3 stop conditions, same fallback tree, same
  decision-record template from the original LD-204 scope.
- Drag-drop 2hr stop-signal still applies. If the widget can't be built in 2
  hours against local Directus, Option C dies for the same reason it would die
  against hosted — the Vue custom-interface pattern itself is what's being
  tested.
- Event_1 state still untouched (the rule was about hosted production state;
  local Directus has its own SQLite DB).

LOCAL DIRECTUS LAYOUT (in Kim's home directory, outside Dropbox to avoid sync
thrash on SQLite file):
- `~/directus-prototype/` — root of the local instance
- `~/directus-prototype/database.db` — SQLite file (throwaway)
- `~/directus-prototype/extensions/` — custom Vue interfaces live here
- `~/directus-prototype/uploads/` — local file storage for image_override drops
- Runs on http://localhost:8055, admin = kim@local / local-prototype

ROLLBACK (unchanged + extended): if prototype fails, `rm -rf ~/directus-prototype`
tears down the entire local instance including SQLite + uploads + extensions.
Hosted Directus sees no schema changes regardless of outcome. Only audit rows
(prod_activity_log + preflight rows 47 and 48) remain on hosted as the audit
trail."""

def main():
    c = DirectusClient(BASE, EMAIL, PASSWORD)
    c.authenticate()

    row = c.get_one("prod_locked_decisions", 204)
    current_text = row.get("decision_text", "")

    if AMENDMENT_MARKER in current_text:
        print("Amendment already present on LD-204 — no-op.")
        return

    new_text = current_text + AMENDMENT

    c.update("prod_locked_decisions", 204, {
        "decision_text": new_text,
    })

    # Read-back confirm
    confirm = c.get_one("prod_locked_decisions", 204)
    assert AMENDMENT_MARKER in confirm.get("decision_text", ""), "Amendment did not persist"
    print(f"Amended LD-204. decision_text length: {len(confirm['decision_text'])} chars")
    print(f"Amendment marker present: {AMENDMENT_MARKER!r}")

if __name__ == "__main__":
    main()
