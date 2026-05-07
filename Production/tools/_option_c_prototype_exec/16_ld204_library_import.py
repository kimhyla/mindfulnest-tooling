"""Third amendment to LD-204: 4:3 image library imported into prototype
prod_visual_assets collection. Scope narrowed to library-dump only —
no Flow wiring, no TTS, no Kling automation beyond what already exists.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import hosted  # type: ignore

LD_ID = 204
AMENDMENT_MARKER = "AMENDMENT 2026-04-18 (4:3 library import):"

AMENDMENT = f"""

---

{AMENDMENT_MARKER}

Kim directive 2026-04-18 (scope narrowing): the earlier "wire 4 real
production Flows" instruction is retracted. Scope for tonight is
library-dump ONLY — bring Kim's real Event_1 4:3 image library into the
prototype so the drag-drop gallery shows the real production assets
instead of the initial 8 seed thumbnails.

WHAT WAS IMPORTED (into local-prototype prod_visual_assets collection):

Source scan (Production/Event_1/):
- _temp_images/tessa_initial_4x3.png (200x150, thumbnail)
- _temp_images/tessa_closeup_4x3.png (200x150, thumbnail)
- _temp_images/guidebird_closeup_4x3.png (200x150, thumbnail)
- _temp_images/gb_sideview_4x3.png (200x150, thumbnail)
- gb_solo_c1_cropped_4x3.png (1014x761, crop, Rule 6 compliant)
- _tmp_tessa_initial_4x3_upscaled_20260417-035748.png (800x600, upscale, Rule 6 compliant)
- _tmp_tessa_initial_4x3_upscaled_s1_20260417-044454.png (800x600, upscale, Rule 6 compliant)
- crops/beat02_guidebird_closeup.png (1018x764, crop, Rule 6 compliant)
- (from storyboard_v37_prod.html embedded base64) storyboard_embed_1127a7b9_693x520.png
  (693x520, crop — included because 4:3 + production-sized, rule6_compliant=False due to shortest side <600)

EXCLUDED:
- gemini_stills/crops/*_16x9.png (16:9, wrong aspect)
- gemini_stills/crops/shot6_*.png (square / near-square, not 4:3)
- crops/guidebird closeup.png, ref image intro1.png, tessa closeup.png
  (all 16:9 per PNG header parse)
- Storyboard embedded base64 ≤200px shortest side (UI thumbnails)
- Storyboard embedded base64 dupes of disk files (dedupe by md5 of first 64KB)

TOTAL: 9 rows in prod_visual_assets (all module_id=1, event_number=1, status=approved).

WHAT ALSO CHANGED:
- Created prod_visual_assets collection in local Directus with fields matching
  hosted production pattern (module_id, event_number, filename, filepath,
  asset_type, status, shot_number, width, height, rule6_compliant, file,
  source_note, created_at).
- Created /relations entry for prod_visual_assets.file -> directus_files
  so nested field expansion works for the widget's gallery query.
- Granted kim_producer_policy read on prod_visual_assets.
- Updated directus-extension-image-dragdrop to query prod_visual_assets
  (filter: status=approved, sort by asset_type+created_at) instead of raw
  /files. Gallery now shows filename + dimensions + Rule 6 warning chip per
  row. Drop still emits the file uuid (image_override field unchanged).

NOT TOUCHED (per directive):
- No Flow wiring beyond the Generate B+C (Kling) Flow built previously.
- No TTS, no ByteDance LipSync, no silcomp.
- beat_03 still empty image_override (Kim's original "canonical drop
  target" instruction was from the superseded flow-wiring message).
- production_server.py untouched."""

def main():
    c = hosted()
    row = c.get_one("prod_locked_decisions", LD_ID)
    current = row.get("decision_text", "")
    if AMENDMENT_MARKER in current:
        print("Library-import amendment already present on LD-204 — no-op.")
        return
    c.update("prod_locked_decisions", LD_ID, {"decision_text": current + AMENDMENT})
    after = c.get_one("prod_locked_decisions", LD_ID)
    assert AMENDMENT_MARKER in after["decision_text"], "Amendment did not persist"
    print(f"LD-{LD_ID} amended (decision_text now {len(after['decision_text'])} chars).")

if __name__ == "__main__":
    main()
