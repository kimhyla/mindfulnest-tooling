"""Second amendment to LD-204: seed scope correction.

Kim directive 2026-04-17 (post-build): seed scope was over-specified. Kanban
density test already passed at 33 placeholder cards, so the original spec
step 3 ("33 REAL beats with real video URLs") is descoped to "ONE beat
(beat_03) with real clip_paths + the pre-existing gallery images."
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import hosted  # type: ignore

LD_ID = 204
AMENDMENT_MARKER = "AMENDMENT 2026-04-17 (seed scope correction):"

AMENDMENT = f"""

---

{AMENDMENT_MARKER}

Kim directive 2026-04-17 (post-build, mid-execution): the original scope
step 3 ("Seed 33 REAL beats with real video URLs") is descoped. The Kanban
density concern behind the "33 real" requirement is already answered: 33
placeholder cards render cleanly in the cdh-kanboard layout, so Exit
Criterion #4 (Kanban paint <3s at 33 beats) does not require real mp4s on
every card — placeholders stress the layout engine the same way.

REVISED STEP 3: seed 33 beats with placeholder dialogue + status mix
(to exercise Kanban groupBy + density), wire ONLY beat_03 with real clip_paths
on its A/B/C candidates, and ensure the image_override gallery has at least
1 selectable image. Everything else (32 other beats, 96 stub candidates)
stays as empty placeholders. This is the minimum state needed to verify
both custom Vue interfaces render and interact correctly.

ACTUAL SEED DELIVERED (over-indexes the revised step 3 without extra cost
because the work was already done before the correction landed):
- 33 beats with status distribution {{pending: 10, animating: 8, lipsyncing: 7, approved: 8}}
- beat_03 wired with 3 real mp4 candidates (A/B/C from Event_1)
- beat_01 also wired with 1 real mp4 + 1 image_override from the end-to-end
  Kling smoke test — incidental, not a seed requirement
- 8 gallery images (directus_files) for the image-dragdrop widget
- Other 31 beats: dialogue_text labeled [prototype placeholder], no media

WHAT THE CORRECTION CHANGES DOWNSTREAM:
- Kim's test script (KIM_TEST_SCRIPT.md) was already scoped to beat_03 for
  the 3-up compare step and any-beat for the drag-drop step — no edits
  needed.
- Exit Criterion #4 interpretation: paint timing is measured against the
  seeded 33 cards regardless of which have real media.
- Teardown is unchanged."""

def main():
    c = hosted()
    row = c.get_one("prod_locked_decisions", LD_ID)
    current = row.get("decision_text", "")
    if AMENDMENT_MARKER in current:
        print("Scope-correction amendment already present on LD-204 — no-op.")
        return
    c.update("prod_locked_decisions", LD_ID, {"decision_text": current + AMENDMENT})
    after = c.get_one("prod_locked_decisions", LD_ID)
    assert AMENDMENT_MARKER in after["decision_text"], "Amendment did not persist"
    print(f"LD-{LD_ID} amended (decision_text now {len(after['decision_text'])} chars).")

if __name__ == "__main__":
    main()
