# Tech Spec — Waveform Time Authority (WTA) v1

**Status:** SPEC (pre-implementation)  
**Date:** 2026-06-22  
**LD tag:** `WAVEFORM_TIME_AUTHORITY_V1`  
**Scope:** All storyboard surfaces that use `WaveformTimeline`, drag-seek (red playhead), drag-drop cue placement, and linked-video sync.  
**Repos:** `mindfulnest-tooling` → mirror Dropbox → restart storyboard server.

---

## 1. Problem statement

Operators drag on the waveform (seek) or drag library tiles onto the waveform (cue/SFX placement). The red playhead or cue timestamp **snaps to 0.0s** or “does not stick.” This has been fixed repeatedly since May 2025; fixes regress when new overlays, audio sources, or effect lifecycle changes land in `WaveformTimeline.tsx`.

**Category:** Multiple competing **time authorities** (WaveSurfer clock, React state, linked `<video>`, remount resets) — not a single bad line of code.

**Canonical postmortem:** `LESSONS_LEARNED_20260612_WAVEFORM_DRAG_SEEK_V1.md`

---

## 2. Surfaces in scope (inventory)

| Surface | Component | Drag-seek | Drag-drop | Cue resize | Linked video | Notes |
|---------|-----------|-----------|-----------|------------|--------------|-------|
| Phase A producer | `PhaseProducer.tsx` → `WaveformTimeline` | Yes | `lib-watercolor` | L/R handles | Yes (`videoRef`) | Never load stitched MP4 on waveform (SEEK-5) |
| Phase B producer | Same | Yes | `lib-watercolor` | L/R handles | Yes | Cedric preview muted |
| Stitcher per-slot SFX | `StitcherSlotWaveform.tsx` → `WaveformTimeline` | Yes | `lib-sfx` | L/R handles | No (`displayOnly` + master video) | Compact strip |
| Stitcher module SFX strip | `StitcherTab.tsx` → `WaveformTimeline` | Yes | `lib-sfx` | Partial | No | `fallbackDurationMs` when audio loading |
| Beat Gen / Storyboard | `StoryboardTab.tsx`, `BgTab.tsx` | **No** | `lib-image` on slots | N/A | N/A | Image drop targets — **out of WTA scope** |
| Library panel | drag source only | N/A | `setDragData` | N/A | N/A | Payload contract unchanged |

**In scope:** Everything that mounts `WaveformTimeline` or duplicates its seek/drop math.  
**Out of scope:** Beat-level lipsync play buttons, BG image slots, path picker — unless a future beat timeline adds WaveSurfer.

---

## 3. Goals

1. **One playhead authority** — red cursor, time label, linked video scrub, and drop X→ms all derive from the same ms value.
2. **Seek lifecycle isolated from WaveSurfer mount** — audio source change must not silently zero the playhead without explicit user action.
3. **Cue overlay never blocks seek** — cue block bodies pass-through; handles remain interactive (WAVEFORM_CUE_HANDLE_V1).
4. **Single implementation** — no forked drag-seek math in Stitcher vs Phase.
5. **Behavioral CI** — Playwright mouse drag tests are merge gates, not grep-only guards.

## 4. Non-goals

- Replacing WaveSurfer.
- Beat Gen beat timeline (no waveform today).
- Changing server cue schema (`timestamp_ms` / `offset_ms` translation stays).
- New WaveSurfer `interact: true` / `dragToSeek` (known snap-to-0 bug).

---

## 5. Architecture

### 5.1 New module: `waveformTimeAuthority.ts`

Pure TypeScript (no WaveSurfer import). Holds:

```ts
interface WaveformTimeState {
  durationMs: number;           // authoritative timeline length
  playheadMs: number;           // authoritative scrub position
  isDraggingSeek: boolean;
  isPlaying: boolean;
}

interface WaveformTimeAuthority {
  read(): WaveformTimeState;
  setDurationMs(ms: number): void;
  beginDragSeek(): void;
  scrubToMs(ms: number, source: 'pointer' | 'ws' | 'master'): void;
  endDragSeek(ms: number): void;
  preserveAcrossRemount(): number;  // returns ms to restore after audioSrc change
}
```

**Rules (encoded in module, not comments):**

| Rule ID | Rule |
|---------|------|
| WTA-1 | While `isDraggingSeek`, ignore WaveSurfer `seeking` / `getCurrentTime()` updates with `t <= 0`. |
| WTA-2 | Duration for scrub math uses `durationMs` ref; never `ws.getDuration()` when ref > 0. |
| WTA-3 | `scrubToMs` updates playhead + calls `ws.seekTo(ms/duration)` + optional `linkedVideo.currentTime` in one transaction. |
| WTA-4 | On `audioSrc` / `displayOnly` remount: restore `playheadMs` from `preserveAcrossRemount()` unless user explicitly sought to 0. |
| WTA-5 | Drop offset: `offset_ms = round(relX * durationMs)` only when `durationMs > 0` and `isReady`; else reject drop with visible toast. |

### 5.2 New module: `waveformSeekController.ts`

Binds pointer handlers to `wrapperRef` (capture phase). Consumes `WaveformTimeAuthority`. Extracted from `WaveformTimeline.tsx` lines ~682–798.

- **Never** lives in the same `useEffect` as `WaveSurfer.create`.
- Deps: `isReady`, `audioSrc` / display peaks, `wrapperRef` — not closed-over `ws`.
- `applySeek(rel)` → authority.scrubToMs(rel * duration, 'pointer').

### 5.3 New module: `waveformAudioPolicy.ts`

```ts
type WaveformAudioSource = { kind: 'stem' | 'mixed' | 'lipsync'; filename: string };
type PreviewVideoSource = { kind: 'stitched' | 'lipsync'; filename: string };

function waveformAudioForPhase(slice, stemTrimMode): WaveformAudioSource | null;
function previewVideoForPhase(slice, phase): PreviewVideoSource | null;
```

**Policy:** Waveform NEVER loads `phase_a_stitched_*.mp4` or video-only URLs. Stitched stays on preview `<video>` only (SEEK-5/6). Type system + unit test enforces separation.

### 5.4 `WaveformTimeline.tsx` refactor

- Inject authority + seek controller hooks.
- Remove duplicate `lastScrubMsRef` / `isDraggingSeekRef` / `timelineDurationMsRef` — owned by authority.
- Cue handle drag uses `authority.getDurationMs()` (CUE-RESIZE-1).
- Drop handler uses authority; if `!isReady` → `onDropRejected?.('waveform_loading')`.

### 5.5 CSS contract (unchanged, enforced)

Paired rules in `app.css` — already guarded by `verify_phase_waveform_play_durability.sh`:

- `.mn-waveform-cue-block { pointer-events: none }`
- `.mn-waveform-cue-block-handle { pointer-events: auto }`
- `.mn-waveform-seek-layer { pointer-events: none }` — seek on wrapper

Add CI check: **forbid** `pointer-events: auto` on `.mn-waveform-cue-block` without handle exception.

---

## 6. Implementation phases

### Phase WTA-0 — Extract without behavior change (1 PR)

1. Add `waveformTimeAuthority.ts`, `waveformSeekController.ts`, `waveformAudioPolicy.ts`.
2. Move existing refs/logic into authority; `WaveformTimeline` behavior identical.
3. Run `e2e/phase_waveform_playback.spec.ts` + stitcher slot tests.

### Phase WTA-1 — Remount preservation (1 PR)

1. On WS mount effect cleanup: save `playheadMs` to authority.
2. On WS ready: restore seek unless `playheadMs === 0 && !userSeekedToZero`.
3. Add test: change `audioSrc` (mock stem regen) → playhead stays within 5% of prior.

### Phase WTA-2 — Stitcher parity audit (1 PR)

1. Confirm `StitcherSlotWaveform` uses shared authority (no local `relXFromPointer` duplication).
2. Module SFX strip: same drop gating when `mixExtracting`.

### Phase WTA-3 — CI hardening (1 PR)

1. Extend `phase_waveform_playback.spec.ts`:
   - SEEK-DRAG-A1 Phase A parity
   - DROP-WC-B1 watercolor drop at ~50% → cue `offset_ms` within 10% of duration
   - REMOUNT-1 audioSrc swap preserves playhead
2. Add `verify_waveform_time_authority.sh` — forbids `ws.getDuration()` in seek path outside authority module.

---

## 7. Test plan

| Test | Type | Pass criteria |
|------|------|---------------|
| SEEK-DRAG-B1 | Playwright | play→pause→drag over cues; `data-current-time-ms` > 50% duration |
| SEEK-DRAG-A1 | Playwright | Same on Phase A |
| CUE-RESIZE-1/2 | Playwright | Existing — must stay green |
| DROP-WC-1 | Playwright | Drop watercolor at 60% → persisted cue `offset_ms` ≈ 0.6 × duration |
| REMOUNT-1 | Playwright | Mock audioSrc change; playhead not reset to 0 |
| WTA-grep | Shell | No `getDuration()` in `WaveformTimeline` seek handlers |
| Event_1 manual | Operator | play→pause→drag on lipsync mp4; no 0.0 flash |

---

## 8. Rollout

1. Implement in `mindfulnest-tooling`.
2. `MN_ALLOW_DIRTY_DEPLOY=1 bash Production/scripts/post_tooling_change_smoke.sh`
3. Hard refresh storyboard; verify `data-drag-seek-bound="WAVEFORM_DRAG_SEEK_V2"` on timeline.
4. No server Python changes required (client-only).

---

## 9. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Over-refactor breaks Stitcher composer sync | Keep `displayOnly` + `masterVideo` path in authority; existing STITCH_UNIFIED_PLAYBACK tests |
| Authority/state split confuses future authors | Single file header in `WaveformTimeline` points to WTA modules only |
| Playwright flakiness on drag | Use `steps` + `data-current-time-ms` poll, not screenshot |

---

## 10. Success criteria

- Zero reports of playhead snap-to-0 on Phase A/B for 30 days after ship.
- SEEK-DRAG + DROP + REMOUNT tests green in CI on every PR touching `WaveformTimeline*` or `app.css` waveform section.
- No new drag-seek handler bindings inside WaveSurfer mount effect (grep gate).
