# TECH_SPEC — Ambient Period Junction + Lipsync Export A/V (FF-039 / FF-040)

**Status:** Implemented v1.1 (2026-07-02) — FF-039 + FF-040 shipped pending Event_4 re-export proof  
**Date:** 2026-07-02  
**Parent:** `FAST_AND_FLAWLESS_DONE_v1.md` (add FF-039, FF-040)  
**Supersedes (partial):** `TECH_SPEC_STITCH_AMBIENT_FULL_PERIOD_TILE_V2` §5 loop expansion; FF-038 `STITCH_AMBIENT_TILE_CONCAT_LOOP_V1` hard tile repeat  
**Related:** `TECH_SPEC_STITCH_INTRO_EXPORT_TRUTH_V2.md` (FF-038 — wrong layer for ambient restart)

---

## Executive summary

| Symptom | Root cause (proven) | Fix track |
|---------|---------------------|-----------|
| Ambient “click” / extraneous restart ~0:33 and ~1:06 | **Period tile hard-restart** at 32.808s multiples — baked ambient jumps back to bed `t=0`, not speech | **FF-039** |
| Lipsync off from beat 1 onward | **Export A/V geometry** — per-clip audio longer than video, `min(v,a)` trim + `normalize_for_concat` widens drift; cumulative tail loss across concat | **FF-040** |

Deploy, waveform cache, and speech concat seams are **not** the primary blockers for these two symptoms.

---

## 2×2 adversarial debate (consensus + red-team)

### Grid A — Ambient (FF-039)

| | **Pro (Audio)** | **Pro (Export)** |
|--|-----------------|------------------|
| **Claim** | Hard `concat` of period tiles resets to bed `t=0`; junction `acrossfade` is the category fix | FF-038 tile concat was wrong layer; internal wrap is fine |
| **Red team** | `acrossfade` shortens timeline — loop point drifts from 32.808s | `aloop` on tile is sample-seamless; why change? |

**Resolution:** Accept timeline shrink from junction xfades (audible period ≈ `content_s - jxf` per hop); **reject** `aloop`/hard-concat — measured restart fingerprint `corr(after, bed_start)` **0.90 → -0.05** @32.808s after junction fix. Acceptance = restart fingerprint ≤0.55, not sample-step click.

### Grid B — Lipsync (FF-040)

| | **Pro (Export)** | **Pro (Stitcher)** |
|--|------------------|---------------------|
| **Claim** | Video authority + norm A/V lock; beat 1 rules out UI-only | Composer plays one muxed MP4 — fix the file |
| **Red team** | Trimming audio to video cuts speech tails | Kling source may be bad before export |

**Resolution:** Video authority is correct for muxed Kling; norm gate ≤16ms on `*_norm_concat`. Operator A/B raw vs norm on beat 1 is follow-up if drift persists post-gate. **Reject** still-insert-cut and waveform-cache theories for beat-1 symptom.

---

## Part A — FF-039: Ambient period junction crossfade

### Problem (operator-verified)

On Event_4 intro (`Intro video ambient bed.mp3`, period **32.808s**):

- Operator hears an **extraneous ambient bed restart** at ~0:31–0:33 and ~1:05–1:06.
- This is **in the ambient layer**, not dialogue (dry intro at 65.616s still has energy, but isolated ambient bake shows the musical reset without speech).

### Forensic proof (2026-07-02, exact server filter graph)

Isolated ambient bake (`build_ambient_bed_filter_lane_for_file`, vol=0.15, slot=125.8s):

| Metric | Loop #1 @32.808s | Loop #2 @65.616s |
|--------|------------------|------------------|
| corr(last 0.5s before, first 0.5s after) | **0.11** (discontinuous) | **0.11** |
| corr(first 0.5s after, bed start 0.5s) | **0.90** (restarts opening) | **0.90** |
| corr(+0.05s after boundary, +0.05s from start) | **0.95** | **0.96** |
| RMS jump (after/before) | **1.49×** | **1.49×** |
| Digital sample step @boundary | ~0.006 (inaudible as click) | ~0.005 |

**Conclusion:** Not a digital pop. The **musical content resets to the bed opening** every 32.808s.

### Why current code does this

`STITCH_AMBIENT_FULL_PERIOD_TILE_V2` builds one period tile:

```
pre  = bed[0 : content_s - xf]     # main body (starts at musical opening)
wrap = acrossfade(tail, head, xf)  # 2.5s tail→head blend
tile = concat(pre, wrap)           # length ≈ content_s (32.808s intro bed)
```

FF-038 expands the slot with `build_ambient_explicit_tile_concat_loop`:

```
[tile]asplit=N → concat=n=N → atrim(slot)
```

Each hard `concat` junction is:

```
… end of tile (wrap zone)  |  start of next tile (clean pre / bed opening)
```

The internal wrap crossfade only softens **within** one tile. **Between tiles** the bed audibly restarts — operator “double-back.”

`aloop` on the same tile has the **same** musical discontinuity (loop point is `pre` start, not the crossfade phase).

### Target behavior

| Requirement | Detail |
|-------------|--------|
| Loop period | Unchanged: one period = trimmed bed `content_s` (e.g. 32.808s intro) |
| Audible restart | **Eliminated** at period multiples — no extraneous return to bed `t=0` |
| Internal wrap | Keep 2.5s tail→head crossfade **inside** the period tile |
| Junction | **Soft crossfade** between consecutive period instances at repeat boundaries |
| Slot fades | Unchanged: 0.5s fade-in @0, 0.75s fade-out @tail |
| Scope | All events / slots using `build_ambient_bed_filter_lane` (server bake only) |
| Cache | Bump `ambient_loop_sig_token()` — forces playback re-bake on re-export |

### Algorithm — `STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1`

**Marker:** `STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1`

Replace hard `concat` of identical tiles with a **chained acrossfade** loop expansion:

1. Build `period_tile` as today (`build_ambient_seamless_period_tile`).
2. Compute `reps = min(24, max(2, ceil(slot_s / period_s) + 1))` (unchanged budget).
3. **Expand loop** (new):

```
[0:a]… → [ptile]                           # one period tile
[ptile]asplit=reps → [t0]…[t{reps-1}]
# Chain acrossfade (not concat):
[t0][t1]acrossfade=d=jxf:c1=tri:c2=tri[t01]
[t01][t2]acrossfade=d=jxf:…[t02]
…
[loop]atrim=duration=slot_s
```

Where:

- `jxf = clamp_ambient_loop_crossfade_s(content_s)` (default cap 2.5s, same as wrap).
- Use triangular windows (`c1=tri:c2=tri`) to match existing wrap.
- For `reps=2`, single acrossfade suffices.

4. Apply existing `_ambient_bed_lane_out` (slot fade-in/out + volume).

**Rejected alternatives**

| Option | Why rejected |
|--------|--------------|
| Revert to raw `aloop` on MP3 | Same restart at tile wrap→pre junction; FF-038 disproved |
| Longer speech join fades | Wrong layer — symptom is ambient-only |
| Shorter bed / different file | Operator-approved asset; geometry fix required |
| Client-side loop | Ambient is always baked in four-files playback |

### Acceptance criteria (FF-039)

**Automated** (`tests/test_stitch_ambient_period_junction.py` + extend `test_stitch_ambient_loop.py`):

1. Filter graph contains `acrossfade` in loop expansion path; hard `concat=n={reps}` for tile repeat **absent**.
2. Render intro bed to 70s @48kHz; at `t = period` and `t = 2×period`:
   - `corr(last 0.5s before, first 0.5s after) ≥ 0.45`
   - `corr(first 0.5s after, bed start 0.5s) ≤ 0.55` (no restart fingerprint)
3. `ambient_loop_sig_token()` includes `PERIOD_JUNCTION_XFADE_V1`.
4. `stitchConstants.ts` client sig parity updated.

**Operator** (Event_4 intro after re-export):

1. Play `intro_playback_*` — no extraneous ambient restart at ~0:33 or ~1:06.
2. Dry-only file unchanged (ambient is playback-only layer).

**Verify script:** `Production/scripts/verify_stitch_ambient_period_junction_durability.sh`

### Files to touch

| File | Change |
|------|--------|
| `server_handlers/stitch_ambient_loop.py` | New `build_ambient_period_junction_loop()`; wire into `build_ambient_bed_filter_lane` |
| `storyboard-v2/src/constants/stitchConstants.ts` | Sig token parity |
| `tests/test_stitch_ambient_loop.py` | Update expectations |
| `tests/test_stitch_ambient_period_junction.py` | New correlation gates |
| `Production/scripts/verify_stitch_ambient_period_junction_durability.sh` | New |
| `FAST_AND_FLAWLESS_DONE_v1.md` | FF-039 row |

---

## Part B — FF-040: Lipsync export A/V authority

### Problem (revised — not still-insert cut)

Operator reports lipsync off **from beat 1**, worsening through the slot. Intro beat map:

| Beats | Pipeline |
|-------|----------|
| 01–04, 15+ | Kling `element_native` |
| 05 only | `still_insert` (Ken Burns animation, not a freeze) |

Still-insert → Kling at 33.876s is a visible cut but **cannot explain beat-1 lipsync**.

### Forensic proof

**Per-clip A/V drift** (raw Kling → `*_norm_concat.mp4`):

| Clip | Raw drift | Export drift | Trim loss @ concat |
|------|-----------|--------------|-------------------|
| beat_01 | +16ms | **+41ms** | 41ms |
| beat_05 | +32ms | **+100ms** | 100ms |
| beat_09 | ~+39ms | ~+39ms | 39ms |
| **Cumulative to beat_09** | | | **~560ms audio tail discarded** |

Concat uses `export_clip_timeline_duration_s = min(video, audio)` for **both** lanes — audio tails are cut to match video. `normalize_for_concat` re-encode can **widen** drift (beat_01: 16ms → 41ms).

Playback bake: intro playback audio **23ms longer** than video (within 250ms gate but audible over 125s).

### Root cause model

1. **Within-clip:** Kling deliveries often have audio slightly longer than video; normalization does not lock streams to a shared trim window.
2. **Across concat:** `min(v,a)` discards audio tail each beat — speech can extend past lip motion at clip ends; errors **accumulate** (~560ms by beat 9).
3. **Not** composer dry-vs-playback split (four-files plays one muxed MP4 for review).

### Target behavior

| Requirement | Detail |
|-------------|--------|
| Timeline authority | **Video stream** defines beat duration in export |
| Audio fit | Trim or pad audio to **exactly** video duration per clip — no silent tail discard of speech |
| Post-normalize gate | `norm_concat` clip: `av_duration_drift_s ≤ 16ms` (fail export, not kid-facing drift) |
| Cumulative gate | Keep `STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S = 50ms` on assembled dry |
| Scope | `normalize_for_concat`, `materialize_kling_o3_trimmed_clip`, `_ffmpeg_concat_kling_clips_reencode` |

### Algorithm — `STITCH_EXPORT_LIPSYNC_VIDEO_AUTHORITY_V1`

**Marker:** `STITCH_EXPORT_LIPSYNC_VIDEO_AUTHORITY_V1`

#### B1 — Video-authority timeline

In `export_clip_timeline_duration_s`:

```python
# Prefer video when present; audio trimmed/padded to match (not min).
if video_s > 0.0:
    return video_s
```

#### B2 — Normalize with A/V lock

Extend `_normalize_to_encoder_spec` (or wrap `normalize_for_concat`):

- Probe `video_s`, `audio_s`.
- Re-encode with filter graph that **atrim/pad audio to video_s** before mux:
  - If `audio_s > video_s`: `atrim=duration=video_s` on audio lane.
  - If `audio_s < video_s`: `apad=whole_dur=video_s` (or `adelay`+silence — prefer apad).
- Apply existing `fuse_ss_args` for video start-time offset **to both lanes**.

#### B3 — Concat reencode

`_ffmpeg_concat_kling_clips_reencode` already trims both lanes to `durations[i]` — ensure `durations[i]` = **video authority** from B1.

#### B4 — Export gate

Before Send to Stitcher concat:

- `assert_stitch_export_clips_av_aligned(max_drift_s=0.016)` on each `*_norm_concat.mp4`.
- Existing assembled gate unchanged.

#### B5 — Playback bake (follow-up if needed)

If dry export passes gates but playback still drifts: extend `bake_slot_playback_mp4` to trim mixed audio to video stream length (secondary; may be unnecessary after B1–B4).

### Acceptance criteria (FF-040)

**Automated:**

1. `test_stitch_export_lipsync_video_authority.py` — synthetic clip with audio +80ms → norm output drift ≤16ms.
2. Event_4 intro export job: all 17 `*_norm_concat` clips ≤16ms drift.
3. Cumulative trim loss **reported** in export job metadata (`audio_trim_loss_ms_total`) — expect **~0ms** after fix vs ~560ms today.

**Operator:**

1. Beat Gen beat 01 raw approved clip vs post-export norm_concat — lipsync **same or better**.
2. Stitcher intro playback: lipsync acceptable on beats 1, 5, 9 (start/mid/late).
3. Resolution slot: re-export on four-files + beat boundaries (separate from FF-040 but required for resolution timeline).

**Verify script:** `Production/scripts/verify_stitch_export_lipsync_video_authority_durability.sh`

### Files to touch

| File | Change |
|------|--------|
| `credentials_lib/ffmpeg_stitch.py` | Video authority, norm A/V lock, gate threshold |
| `beat_generator.py` | Wire gate before concat; optional trim loss telemetry |
| `tests/test_stitch_export_lipsync_video_authority.py` | New |
| `FAST_AND_FLAWLESS_DONE_v1.md` | FF-040 row |

---

## Implementation order

| Phase | Track | Why this order |
|-------|-------|----------------|
| **1** | FF-039 ambient junction | Operator-blocking audible defect; isolated module; no beat re-gen |
| **2** | FF-040 lipsync authority | Requires re-export; touches normalize + concat; validate per-beat |
| **3** | Resolution re-export | Four-files + beat boundaries (existing STITCH_FOUR_FILES_V1) |

After FF-039: **Send to Stitcher intro** on Event_4 → new `intro_playback_*` → listen at 32.8s / 65.6s.

After FF-040: **Send to Stitcher** all affected slots → verify beat 1 lipsync in Stitcher + spot-check beats 5/9.

---

## 3×3 debate consensus (abbreviated)

| Agent | FF-039 | FF-040 |
|-------|--------|--------|
| **Export** | Hard tile concat is the restart; junction acrossfade is the category fix | `min(v,a)` is wrong authority for muxed Kling; video wins |
| **Ambient** | Internal wrap stays; external junction was always the gap | N/A |
| **Stitcher** | Re-bake playback only; dry unchanged | Composer is innocent; fix the MP4 |
| **Reject** | More speech fades; revert to MP3 aloop | Blame still-insert; UI-only sync hacks |

---

## Registry markers (add to `authority_registry.py`)

```
STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1
STITCH_EXPORT_LIPSYNC_VIDEO_AUTHORITY_V1
```
