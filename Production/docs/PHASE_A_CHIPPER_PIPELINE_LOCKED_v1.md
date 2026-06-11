# Phase A Chipper Pipeline — Locked Decisions v2

**Status:** ACTIVE (Kim session 2026-06-08)  
**Scope:** Module 1 Event 1 — Chipper fly-in / talking middle / fly-out  
**Enforcement:** Code + tests (not chat memory)

---

## Repeatable workflow (what Kim does every time)

| Step | Who | Action | Regenerate? |
|------|-----|--------|-------------|
| 0 | Once | Pin wide fly-in + fly-out bookends in state | **Never** (unless art direction changes) |
| 0 | Once | Generate + pin `chipper_idle_element_v1` base clip in `assets/lipsync_bases/` | **Never** (unless anatomy drifts) |
| 1 | Kim | Phase A tab → confirm voice stem + base clip `chipper_idle_element_v1` | — |
| 2 | Kim | **Send for Lipsync** (ByteDance middle from pinned base clip) | **Yes — every new audio** |
| 3 | Auto | Server lipsyncs base clip → runs media gate → extracts QA frames | Auto |
| 4 | Kim/QA gate | Review middle QA packet; stitch/export only after visual approval | — |

**Do not** regenerate fly-in/out or base clip for routine module work. Those are library assets.

---

## Architecture (three segments)

| Segment | Source | Lipsync? |
|---------|--------|----------|
| Fly-in (~5s) | Kling start/end on **wide** empty desk ↔ bird on desk PNGs | No |
| Middle | **Pre-made** `chipper_idle_element_v1` → ByteDance LatentSync, non-chained by default | **Yes** |
| Fly-out (~5s) | Kling start/end (bird on desk → empty desk) | No |

**Stitch order:** fly-in + **raw** lipsync middle + fly-out + continuous ambient bed (`meditation_pretty_v1` default).

**Storyboard player:** Phase A tab shows **stitched** video (`phase_a_stitched_file`).

---

## Resolution / sharpness (Kim 2026-06-08 blur fix)

| Clip | Native resolution | Aspect | Notes |
|------|-------------------|--------|-------|
| Fly-in / fly-out | **1660×1244** | ~4:3 | High-res Kling start/end output |
| Base clip library | **1280×960** | 4:3 | Normalized once at generation |
| ByteDance LipSync return | model-dependent low-res | ~4:3 | Upscale before stitch normalization |
| Stitched canonical | **1280×720** | 16:9 | LD-284 `normalize_for_concat` letterboxes all segments |

**Blur root cause:** Middle was upscaled from 720×544 at stitch time while bookends were *down*scaled from 1660×1244 → middle looked soft.

**Fix:** After ByteDance LipSync, `upscale_lipsync_to_bookend` in `phase_a_av_post.py` upscales middle to **1660×1244** (2× lanczos prescale) *before* stitch normalization. No Ken Burns zoom on middle (zoom caused crop/hallucination issues).

---

## Why element-bound base clip is still required (hands / wings / lipsync)

Flawless middle run (2026-06-08) vs earlier hallucination batches:

| Earlier (bad) | Current (good) |
|---------------|----------------|
| `idle_kling_lipsync` — regen idle from body plate still each lipsync | `base_clip_bytedance_tight_v1` — lipsync only on pre-made MP4 |
| Tight body plate + Ken Burns zoom | Wider `chipper_idle_element_v1` base, **no zoom** |
| Kling idle gen + LipSync (2 jobs, fresh motion) | ByteDance lipsync on pinned base — body/wings/hands come from base |
| Element binding failed or skipped on lipsync path | Base clip generated **once** with Elements + wing-hand prompt |

**`chipper_idle_element_v1` origin (Jun 7–8):**

1. Refreshed Kling Element `312852063706525` with ChatGPT hand/pose reference images.
2. `phase_a_chipper_lipsync_base.py` on `phase_a_chipper_closeup_crop_v3.png` **with Elements bound**.
3. Prompt locks wings visible at sides, TOOTH-FREE beak, no gesticulation.
4. Saved to `assets/lipsync_bases/chipper_idle_element_v1.mp4` (1280×960).

**Wings not frozen:** Base clip allows subtle breathing/blinks — lipsync does not re-run idle Kling, so wing motion comes from the base clip (expected, not a bug).

**Hand images:** Element update + one-time base generation locked anatomy. Subsequent lipsync runs must preserve that stable video and may not use chained gap-tail seeds as the production default.

---

## Vendor split (HARD)

| Phase | Character | Middle pipeline | Endpoint |
|-------|-----------|-----------------|----------|
| **A** | Chipper (bird) | **Base clip + ByteDance LatentSync** (`base_clip_bytedance_tight_v1`) | `POST /api/phase_a/lipsync` |
| **B** | Cedric (human) | Kling Sync on Cedric base | `POST /api/phase_b/lipsync` |

### Rejected approaches (do not reintroduce)

1. **Chained ByteDance as default** — gap-tail `tpad=clone` can freeze blink/pose frames into speech chunks.
2. **Kling Sync direct on bird close-up** (no idle base) — human arms on wings, teeth, gaze drift.
3. **Idle regen from still on every lipsync** — inconsistent wings/hands.
4. **Ken Burns zoom on middle** — forehead crop + quality masking; use bookend upscale instead.
5. **2.5s fadeblack middle→fly-out** — use 500ms xfade (beatgen pattern).

---

## Canonical code paths

| Role | File |
|------|------|
| Base-clip ByteDance lipsync | `Production/tools/phase_a_middle_permanent.py`, `Production/tools/phase_a_chipper_bytedance_lipsync.py` |
| A/V post (loop/pad/upscale/trim) | `Production/tools/phase_a_av_post.py` |
| Idle lipsync (legacy fallback) | `Production/tools/phase_a_chipper_idle_lipsync.py` |
| Base clip one-time generator | `Production/tools/phase_a_chipper_lipsync_base.py` |
| Wide fly-in/out | `Production/tools/phase_a_flyin_flyout_wide_v1.py` |
| Auto-stitch + ambient | `production_server._auto_assemble_phase_a_stitched` |
| Server lipsync | `server_handlers/phases.handle_phase_a_lipsync` |
| Restitch CLI | `Production/scripts/phase_a_restitch_from_state.py` |
| Tests | `test_phase_a_av_post.py`, `test_phase_a_stitch_resolve.py` |

---

## Base-clip lipsync pipeline (middle) — v4 reliability gate

Dependency order:

1. **Audio prep:** `_silcomp_audio` + loudnorm + `auto_preroll=True`.
2. **ByteDance LatentSync** on pinned base clip (`chipper_idle_element_v1`), `chain_chunks=False` by default.
3. **Upscale** to 1660×1244 (`upscale_lipsync_to_bookend`).
4. **Pad video** to match audio (`pad_video_to_match_audio`).
5. **Trim preroll** (`trim_av_lead_in`).
6. Write `phase_a_lipsync_*`, extract QA frames, set `needs_manual_visual_review`; stitch/export only after visual gates pass.

---

## Pinned library assets (Event_1 defaults)

| Asset | State key | Current pinned file |
|-------|-----------|---------------------|
| Fly-in | `phase_a_flyin_file` | `phase_a_flyin_wide_20260608T170541Z.mp4` |
| Fly-out | `phase_a_flyout_file` | `phase_a_flyout_wide_20260608T170753Z.mp4` |
| Base clip | `phase_a_chipper_sitting_clip_id` | `chipper_idle_element_v1` |
| Ambient | `phase_a_ambient_preset_id` | `meditation_pretty_v1` |

---

## State field contracts

| Field | Purpose |
|-------|---------|
| `phase_a_flyin_file` | Pinned fly-in mp4 |
| `phase_a_flyout_file` | Pinned fly-out mp4 |
| `phase_a_lipsync_file` | Pinned middle (raw, no `withbed`) |
| `phase_a_stitched_file` | Canonical stitched output (UI player) |
| `phase_a_chipper_sitting_clip_id` | Library base for lipsync |
| `phase_a_voice_stem_file` | TTS source |
| `phase_a_ambient_preset_id` | Bed at stitch |

---

## QA checklist

```bash
cd Production/tools
python3 -m pytest tests/test_phase_a_av_post.py tests/test_phase_a_stitch_resolve.py -q

# Re-stitch from pinned state (after upscale fix on existing middle):
python3 ../scripts/phase_a_restitch_from_state.py
```

---

## Lessons learned

- Lipsync model outputs must be upscaled before stitch.
- Anatomy quality comes from **one-time** element-bound base clip, not per-run idle regen.
- Fly-in/out use `--no-element` when registry element_id stale; middle quality is independent (uses library base).
- Storyboard “same video” usually means stitched unchanged — check middle file separately.
