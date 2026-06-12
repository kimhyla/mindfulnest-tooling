# Stitcher SFX + Ambient Timeline Spec v1

**Status:** SPEC (implementation Phase 1–3 below)  
**Date:** 2026-06-12  
**Scope:** Extend Phase A/B watercolor timeline architecture to Stitcher slot tracks — drag/drop from Library, duration resize via left/right handles, server bake respects cue ranges.  
**Non-goal:** New parallel timeline subsystem; WaveSurfer-only stitcher UI unrelated to PhaseProducer.

---

## 1. Problem statement

Kim can drag SFX from Library onto Stitcher, but:

1. **Library was empty for audio** — `LibraryPanel` only called `GET /api/cr/library` (images). SFX files on disk (`Production/assets/sound_library/sfx/*.mp3`) were never listed. Upload input `accept=` blocked `.mp3`.
2. **Drop target exists but cues are point markers** — `StitcherSlotWaveform` renders vertical ticks at `offset_ms` only; no `duration_ms`, no resize handles, no WaveSurfer waveform.
3. **Server ignores cue duration** — `_stitch_mix_slot_audio()` mixes full SFX file at offset; no `atrim` by cue window.
4. **Ambient beds are slot dropdown only** — no timeline block; acceptable for v1 if beds stay full-slot (existing `ambient_bed` on slot).

**Phase 1 (this session) fixes:** fade clipping on Phase A/B exports + Library audio restore + upload.  
**Phase 2–3 (this spec):** watercolor-parity timeline blocks on Stitcher.

---

## 2. Reference architecture (what already works)

### 2.1 Phase A/B watercolor — DO replicate

| Layer | File | Pattern |
|-------|------|---------|
| Data | `phase_X_watercolor_cues_json` in event state | `{id, watercolor_key, offset_ms, duration_ms}` |
| UI | `WaveformTimeline.tsx` | Absolute-position blocks; left/right pointer handles; `onCueRangeChange` |
| Drop | `makeDropTarget` + `lib-watercolor` payload | Drop X → `offset_ms = relX × durationMs` |
| CSS | `app.css` `.mn-watercolor-cue-block` | `%` left/width on timeline wrapper sized to video |
| Server | Phase overlay bake | Cues with offset + duration baked into export |

### 2.2 Phase A/B regressions — DO NOT repeat

| Mistake | Symptom | Prevention for Stitcher |
|---------|---------|-------------------------|
| Raw animated MP4 in CSS overlay | Magenta matte / pink frame | N/A for audio; if video preview added later, use chromakey path |
| `.mn-lipsync-video-wrapper { width:100% }` | Overlay blocks sized to panel not video | Stitcher slot wrapper must match **slot video duration width**, not panel |
| `stopAllPhasePlayback()` during render | Playhead jump / broken play | Use `useEffect` + ref for tab/slot changes only |
| Vite-stripped comment markers | CI dist guards false-green | Runtime strings: `data-stitcher-sfx-timeline="STITCHER_SFX_TIMELINE_V1"` |
| Partial deploy (single-file cp) | UI/server mismatch | Always `deploy_storyboard_v59.sh` + sha256 verify |
| Wrong library API | SFX “disappeared” | Merge `cr_library` + `stitch_editor/library` in `LibraryPanel` |
| Audio fade on tail | Dialogue clipped | `fade_audio=False` / `-c:a copy`; black **between** slots via `expand_clips_with_black_pause_boundaries` |

### 2.3 Intro fade pattern (canonical)

- `trim_body_with_fade(..., fade_audio=False)` — short video tail fade (~600ms)
- `expand_clips_with_black_pause_boundaries(..., fade_audio=False)` — black hold **between** beats
- Audio full level until hard cut at clip end

**Applied to Phase A/B (2026-06-12):**

- Phase B lipsync whiteout: `PHASE_B_WHITEOUT_FADE_AUDIO=False`, duration 0.6s video-only
- Phase A tail trim: `TRAILING_SPEECH_HOLD_S=0.75`
- Default stitch transitions: `audio_xfade_ms=0` (visual dissolve + black pause only)

---

## 3. Target UX (Stitcher)

Per slot (`intro`, `phase_a`, `phase_b`, `resolution`):

```
┌─ Slot video waveform (WaveSurfer, optional Phase 2) ─────────────┐
│ [====ambient bed block====]  (full slot or future trim)         │
│      [==SFX cue==]     [====SFX cue====]                        │
└─────────────────────────────────────────────────────────────────┘
```

Interactions (match watercolor):

- Drag `lib-sfx` / `lib-ambient` from Library → drop on slot track → create cue at drop X
- Left handle → adjust `offset_ms` (move block)
- Right handle → adjust `duration_ms` (extend/shrink playback window)
- Click block → `SfxCuePopover` (volume, fadein, fadeout, delete)

Module-level strip (`module_sfx_cues`) keeps point markers for now; slot-level `slot.sfx_cues` gets duration blocks first (higher operator value).

---

## 4. Data model changes

### 4.1 Extend `SfxCue` (client + server)

```typescript
interface SfxCue {
  id: string;
  source_path: string;
  name?: string;
  offset_ms: number;
  duration_ms?: number;  // NEW — default = min(file_duration, slot_end - offset)
  volume: number;
  fadein_ms: number;
  fadeout_ms: number;
}
```

Server: `_stitch_mix_slot_audio` — when `duration_ms` set:

```python
play_s = min(file_dur, duration_ms / 1000.0)
# ffmpeg: atrim=0:play_s, adelay=offset_ms, volume, afade in/out
```

Backward compat: missing `duration_ms` → full file (current behavior).

### 4.2 Persistence (unchanged paths)

- Per-slot: `stitch_save_job` → `jobs[name].slots[slot].sfx_cues[]`
- Module: `/api/timeline/cues` → `state.module_sfx_cues`

Validate on save via existing stitch job schema; add optional `duration_ms` int ≥ 100.

---

## 5. Implementation phases

### Phase 1 — Library + fade fixes ✅ (2026-06-12)

| Step | Action | Verify |
|------|--------|--------|
| 1.1 | `LibraryPanel` merge `stitch_editor/library` | SFX tier shows files from disk |
| 1.2 | `cr_upload` accept audio tiers → `sound_library/{tier}/` | MP3 not grayed in picker |
| 1.3 | Phase B whiteout audio copy + 0.6s visual | `test_phase_b_whiteout_fade.py` |
| 1.4 | Phase A hold 0.75s | `test_phase_a_av_post.py` |
| 1.5 | Default `audio_xfade_ms=0` | `test_stitch_module_preview.py` |
| 1.6 | Build + `deploy_storyboard_v59.sh` | curl library + dist marker |

### Phase 2 — UI blocks (watercolor port)

| Step | File | Work |
|------|------|------|
| 2.1 | `StitcherSlotWaveform.tsx` | Replace point markers with `%` blocks; add L/R handles (copy pointer logic from `WaveformTimeline.tsx` lines 528–600) |
| 2.2 | `StitcherTab.tsx` | Wire `onCueRangeChange(slot, cueId, offset, duration)` → `stitch_save_job` |
| 2.3 | Drop handler | Set initial `duration_ms = min(lib.duration_ms, slotDur - offset)` from library metadata |
| 2.4 | `app.css` | `.mn-stitcher-sfx-cue-block` mirror `.mn-watercolor-cue-block` |
| 2.5 | Optional | WaveSurfer on slot strip (reuse `WaveformTimeline` audio load pattern) |

**E2E:** Extend `e2e/s5_5g_smoke.spec.ts` G3 — drop SFX → block visible with width > marker; drag right handle → `duration_ms` increases in saved job.

### Phase 3 — Server bake

| Step | File | Work |
|------|------|------|
| 3.1 | `production_server.py` `_stitch_mix_slot_audio` | Honor `duration_ms` via `atrim` |
| 3.2 | Preview/bake cache key | Include cue duration in hash |
| 3.3 | pytest | `test_stitch_sfx_duration_trim.py` — 10s file, 3s cue → mixed length |

### Phase 4 — Durability + deploy checklist

Every ship must pass:

```bash
cd mindfulnest-tooling/Production/tools/storyboard-v2 && npm run build
pytest Production/tools/tests/test_phase_b_whiteout_fade.py \
       Production/tools/tests/test_cr_upload_audio.py \
       Production/tools/tests/test_stitch_module_preview.py -q
bash Production/scripts/check_storyboard_critical_features.sh
bash Production/scripts/deploy_storyboard_v59.sh
curl -s http://localhost:5111/api/stitch_editor/library | jq '.sfx | length'
curl -s -o /dev/null -w '%{http_code}' http://localhost:5111/
```

Add dist marker `STITCHER_SFX_TIMELINE_V1` in `StitcherSlotWaveform` root when Phase 2 lands.

---

## 6. QA matrix

| Check | Method | Pass criteria |
|-------|--------|---------------|
| Library SFX visible | UI + curl | ≥1 item in sfx tier; count matches disk |
| MP3 upload | UI file picker | Not grayed; appears after refresh |
| Phase B tail audio | Re-lipsync or probe existing | Last syllable audible; video fades 0.6s only |
| Phase A tail audio | Mix/restitch | No hard cut mid-word |
| Module preview dissolve | Stitcher Preview | Black between slots; dialogue not ducked at boundary |
| SFX drop | E2E G3 | Cue at drop position |
| SFX resize | E2E (Phase 2) | `duration_ms` in saved job JSON |
| Bake | Preview MP4 | SFX audible at offset; trimmed to duration |

---

## 7. Files touched (Phase 1)

- `server_handlers/phases.py` — whiteout audio copy, 0.6s fade
- `phase_a_av_post.py` — `TRAILING_SPEECH_HOLD_S`
- `server_handlers/stitch_editor.py` — default `audio_xfade_ms=0`
- `server_handlers/cropper.py` — audio upload tiers
- `storyboard-v2/src/components/LibraryPanel.tsx` — dual library load + audio accept
- `storyboard-v2/src/api/endpoints.ts` — `stitch_editor_library`
- `storyboard-v2/src/utils/stitchModulePreview.ts` — `audio_xfade_ms: 0`

---

## 8. Open questions (defer)

- Ambient bed as timeline block vs full-slot dropdown (recommend dropdown v1; timeline block v2)
- Module-level strip blocks vs slot-only (slot-first)
- WaveSurfer on every slot vs intro-only (performance)

---

## 9. Sign-off

Phase 1 deploy proof required in session notes:

- [ ] pytest green
- [ ] dist built
- [ ] deploy script exit 0
- [ ] `GET /api/stitch_editor/library` sfx count > 0
- [ ] Library UI SFX tier populated (screenshot or e2e)

Phase 2+ requires PR with e2e G3/G3.2 before merge.
