"""
Stillgen is_current Backfill — prod_visual_assets (2026-04-21)

Sets is_current=true on all 75 existing prod_visual_assets rows EXCEPT the known
v1→v4 supersession chain for `image_command_center_m1e1` tool HTML (ids 78, 79, 80):
those get is_current=false with superseded_by_id pointing to the next version.
The v4 row (id=82) gets is_current=true, superseded_by_id=null.

Why not the blanket-default from Kim's instruction? Phase 0 counter-agent C1 flagged
that 5 groups had >1 row at migration time; 4 were peer candidates (parallel options
A/B/C — all correctly is_current=true); 1 was a clear v1→v4 supersession sequence
where blanket is_current=true would mis-label 3 superseded rows. Kim's intent
("rows are current") is honored for 71 of 75 rows; 3 are treated as superseded to
match their actual semantics.

Task: stillgen-addon-phase0-resolutions-20260421
Two-Write Rule honored via activity_log entries per phase.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production")
from lib.directus_admin_client import DirectusAdminClient

TASK_ID = "stillgen-addon-phase0-resolutions-20260421"

# v1→v4 supersession chain for image_command_center_m1e1 tool HTML
# (confirmed by dup scan 2026-04-21: same module_id=1, event_number=1, shot_number=0,
#  asset_type=production_tool, purpose='Image selection and 4:3 cropping tool')
SUPERSEDED = [
    {"id": 78, "superseded_by_id": 79, "filename": "image_selector_cropper_m1e1_v1.html"},
    {"id": 79, "superseded_by_id": 80, "filename": "image_command_center_m1e1_v2.html"},
    {"id": 80, "superseded_by_id": 82, "filename": "image_command_center_m1e1_v3.html"},
]
CURRENT_TIP = 82  # image_command_center_m1e1_v4.html

def main():
    c = DirectusAdminClient()
    all_rows = c.get_items("prod_visual_assets", fields=["id","filename"], limit=-1)
    total = len(all_rows)
    superseded_ids = {s["id"] for s in SUPERSEDED}
    current_ids = [r["id"] for r in all_rows if r["id"] not in superseded_ids]
    print(f"total rows: {total}")
    print(f"superseded rows (will set is_current=false): {sorted(superseded_ids)}")
    print(f"current rows (will set is_current=true): {len(current_ids)}")

    # Log start
    c.post_item("prod_activity_log", {
        "action": "stillgen_backfill_is_current_start",
        "details": {"task_id": TASK_ID, "total": total, "current_count": len(current_ids),
                    "superseded_count": len(superseded_ids),
                    "superseded_rows": SUPERSEDED, "current_tip_id": CURRENT_TIP},
        "performed_by": "claude",
    })

    # Step 1: Set is_current=true on the current rows (chunked bulk)
    CHUNK = 25
    updated_current = 0
    for i in range(0, len(current_ids), CHUNK):
        chunk = current_ids[i:i+CHUNK]
        c.patch_items_bulk("prod_visual_assets", chunk, {"is_current": True})
        updated_current += len(chunk)
        print(f"  [current] batch {i//CHUNK + 1}: {len(chunk)} rows → OK")
    print(f"is_current=true set on {updated_current} rows")

    # Step 2: PATCH each superseded row individually (different superseded_by_id per row)
    superseded_patched = []
    for s in SUPERSEDED:
        c.patch_item("prod_visual_assets", s["id"], {
            "is_current": False,
            "superseded_by_id": s["superseded_by_id"],
        })
        superseded_patched.append(s["id"])
        print(f"  [superseded] id={s['id']} → is_current=false, superseded_by_id={s['superseded_by_id']}  ({s['filename']})")

    # Readback verification
    print("\n=== READBACK ===")
    for s in SUPERSEDED + [{"id": CURRENT_TIP, "filename": "image_command_center_m1e1_v4.html (expected is_current=true)"}]:
        r = c.get_item("prod_visual_assets", s["id"],
            fields=["id","is_current","superseded_by_id","filename"])
        print(f"  id={r['id']} is_current={r['is_current']} superseded_by_id={r['superseded_by_id']} filename={r['filename']}")

    c.post_item("prod_activity_log", {
        "action": "stillgen_backfill_is_current_complete",
        "details": {"task_id": TASK_ID, "updated_current": updated_current,
                    "superseded_patched": superseded_patched, "total": total},
        "performed_by": "claude",
    })
    print("\nDone.")

if __name__ == "__main__":
    main()
