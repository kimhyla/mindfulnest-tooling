# Lessons Learned — Stitcher Canonical Job + Phase B Overlay Export (2026-05-28)

## Symptoms

1. **Resolution slot vanished** after Phase B “Export to Stitcher” — only `phase_b` remained.
2. **Stitcher preview showed raw lipsync** — watercolor popup overlays placed in Phase B were not visible.
3. **Client-side job merge was fragile** — saving `{eventId}_stitch` with partial slots could overwrite slots collected from Send Out.

## Root causes

| Issue | Cause |
|-------|--------|
| Resolution disappeared | Slots lived in separate jobs (`auto_resolution`, `phase_b_Event_1`). Client merge + full-job save could drop slots without `video_path`. |
| Missing overlays | Export sent raw `phase_b_lipsync_*.mp4`; overlays only existed in preview cache (`handle_phase_b_preview`). |
| Non-persistent collection | No server-side canonical job; each producer wrote to its own job name. |

## Fix (LD-830+)

1. **`{eventId}_stitch` canonical job** — `stitch_upsert_event_slot()` deep-merges one slot at a time; never replaces unrelated slots.
2. **`scene_assemble` Send Out** — upserts intro/resolution into canonical job (replaces legacy `auto_*` only writes).
3. **`POST /api/phase/export_stitcher`** — Phase B export calls `_phase_ensure_overlay_mp4()` (same cache as preview) then upserts composited path with `overlay_baked: true`.
4. **`stitch_migrate_legacy_to_canonical()`** — on load/upsert, merges legacy `auto_*` + `phase_*` jobs into canonical without dropping filled slots.
5. **`merge_slots: true`** on `stitch_save_job` — UI trim/SFX edits merge into canonical job instead of blind replace.

## Invariants (do not regress)

- Exporting Phase B **must** bake watercolor overlays before stitch slot write.
- Upserting any stitch slot **must not** clear other slots on the same event.
- StitcherTab **must** load `{eventId}_stitch` first; legacy merge is fallback only.
- Beat boundaries on intro/resolution slots **must** come from scoped partition `display_order`, not global clip scan.

## Verification multipass

```bash
cd Production/tools && python3 -m pytest tests/test_stitch_canonical_job.py -q
python3 Production/scripts/verify_stitcher_lockin_20260528.py
```

Manual: Send Out resolution → Export Phase B → Stitcher shows **both** slots; Phase B preview shows watercolors.
