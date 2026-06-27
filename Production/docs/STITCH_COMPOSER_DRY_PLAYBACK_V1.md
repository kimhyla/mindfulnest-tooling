# STITCH_COMPOSER_DRY_PLAYBACK_V1 — subtractive playback path

## Problem (bug class)

Stitcher conflated **“mux/SFX mix preview failed”** with **“slot has no export.”** When the composer `<video>` fired `error` on a mux URL, `muxPreviewFailedBySlot` hid the slot from `composerSlotUrls`, so the UI showed “Preview unavailable” / “Assign slot video” even though `job.slots[slot].video_path` still pointed at a valid assembled MP4 on disk.

## Category fix (subtractive)

**One playback path:** if `video_path` is set, the composer always gets a URL from `resolveSlotPlaybackPreviewUrl` (session mux → persisted artifacts → dry `/files?path=…` floor). Mux failure is a **status message only** — never a visibility gate.

### Removed

- `muxPreviewFailedBySlot` state and all branches that skip URLs or set `composerVideoUrl = undefined` on mux failure
- `onPoolSlotError` cache nukes (`clearCachedStitcherPreviewLs`, `deleteStitchComposerPreviewUrl`, `previewUrls` delete) — bad mux URL is overridden by binding dry via `bindSlotPreviewUrl`, not by wiping job identity

### Kept

- `resolveSlotPlaybackPreviewUrl` / `resolveDrySlotSourceVideoUrl` in `stitchJobMediaHydrate.ts` (existing dry floor)
- Review button → `buildSlotPreview` to rebuild mux when operator wants SFX mix again
- `composerVideoError` alert for operator-visible failure text

## Implementation steps

1. **`StitcherTab.tsx`**
   - `composerSlotUrls`: always `resolveSlotPlaybackPreviewUrl` when `video_path` present
   - `composerVideoUrl`: always `composerSlotUrls[viewerSlot]` (no ternary)
   - `onPoolSlotError`: bind dry URL + set message; no cache wipe
   - Remove `muxPreviewFailedBySlot` entirely
   - Marker: `data-stitch-composer-dry-playback="STITCH_COMPOSER_DRY_PLAYBACK_V1"`

2. **Tests**
   - `stitchPersistedPlaybackArtifacts.test.ts`: contract — mux slot with empty `previewUrls` still resolves dry `/files`
   - Python durability: assert `STITCH_COMPOSER_DRY_PLAYBACK_V1` present; assert `muxPreviewFailed` absent from `StitcherTab.tsx`

3. **Deploy**
   - `npm run build` in `storyboard-v2`
   - `bash Production/scripts/deploy_storyboard_v59.sh --event Event_2`
   - Verify `build-sha` in served HTML matches commit

## Acceptance criteria

| Check | Pass |
|-------|------|
| Intro slot with `intro_kling_o3_*.mp4` on disk shows composer video (not “Assign slot video”) | ✓ |
| Playback survives Beat 6 boundary on dry path when mux cache is stale/broken | ✓ |
| Simulated mux `error` → dry `/files` URL bound; slot stays assigned | ✓ |
| Review rebuilds mux without requiring re-export from Beat Gen | ✓ |
| Unit + Python contract tests green | ✓ |

## QA commands

```bash
cd Production/tools/storyboard-v2 && npm run build
cd Production/tools && python3 -m pytest tests/test_stitch_slot_preview_video_playable.py tests/test_stitch_slot_preview_scope_gate.py tests/test_stitch_composer_playback_sync.py tests/test_stitch_viewer_fallback.py -v
bash Production/scripts/deploy_storyboard_v59.sh --event Event_2
curl -s http://localhost:5112/ | grep -o 'build-sha[^"]*'
curl -s http://localhost:5112/api/stitch_editor/job/Event_2_stitch | jq '.job.slots.intro.video_path'
```

Browser: Storyboard → Stitcher → intro slot — video visible, seek past ~29s (Beat 6), no black “Assign slot video” placeholder.
