# TECH_SPEC — STITCH_AMBIENT_FULL_PERIOD_TILE_V2

## Classification

**Category fix** — structural ffmpeg loop geometry (not gain/volume tweak).

## Problem

`STITCH_AMBIENT_SINGLE_SEAM_V1` (commit `9baf4fe`) misimplemented FF-026 Option A: the loop tile was only the **2.5s wrap crossfade**, not the full **~27s bed period**. `aloop` repeated every ~2.5s → harsh audible restart every ~2 seconds.

Prior body+glue design (`0f5bd49`) had the correct **period length** but **two seams** per period (~25s inner concat + ~27s tile repeat).

## Target behavior (operator acceptance)

| Requirement | Detail |
|-------------|--------|
| Loop period | One loop per **trimmed bed period** (`content_s`, e.g. ~27s for resolution bed) |
| Wrap crossfade | **2.5s triangular** (`acrossfade`, `c1=tri:c2=tri`) tail→head at period end only |
| Audible seams | **≤1** soft seam per bed period (wrap crossfade region); no mid-period harsh restart |
| Slot fades | Unchanged: 0.5s fade-in at slot start, 0.75s fade-out at slot tail |
| Scope | All events, all stitch slots, all dedicated ports — server-side bake only |

## Algorithm — `build_ambient_seamless_period_tile`

For slot longer than trimmed bed (`content_s`):

1. **Trim** leading/trailing silence (`STITCH_AMBIENT_LOOP_TRIM_V2`).
2. **pre** = bed `[0 : content_s - xf]` — main musical body.
3. **wrap** = `acrossfade(tail, head, d=xf)` where tail = last `xf` s, head = first `xf` s.
4. **tile** = `concat(pre, wrap)` — length ≈ **content_s** (full period).
5. **aloop(tile)** → slot duration.
6. Slot fade-in/out + volume on outer lane.

The wrap crossfade **is** the professional soft loop — listeners hear continuous bed, then a gentle 2.5s blend from ending into beginning once per period.

## Authority

| Layer | Module | Marker |
|-------|--------|--------|
| Filter lane | `stitch_ambient_loop.py` | `STITCH_AMBIENT_FULL_PERIOD_TILE_V2` |
| Cache bust | `ambient_loop_sig_token()` | replaces `STITCH_AMBIENT_SINGLE_SEAM_V1` in sig |
| Client parity | `stitchConstants.ts` | `STITCH_AMBIENT_LOOP_SIG_V1` must match server token |
| Export rebuild | `stitch_editor.py` | `STITCH_AMBIENT_FORCE_REBUILD_ON_EXPORT_V1` |

## Durability gates

1. `test_stitch_ambient_loop.py` — filter graph contains full-period pre+wrap, not glue-only tile.
2. `test_stitch_ambient_loop_seam_budget.py` — rendered loop dominant period ≥ `content_s * 0.75`.
3. `verify_stitch_ambient_durability.sh` — sig parity + pytest.
4. Post-deploy: resolution slot re-export; browser Stitcher playback without ~2s restart pattern.

## Out of scope

- Changing default bed files per event.
- Client-side runtime looping (ambient is always baked in mux).
