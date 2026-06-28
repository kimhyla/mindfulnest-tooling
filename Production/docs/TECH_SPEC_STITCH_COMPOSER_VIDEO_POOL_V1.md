# TECH_SPEC — Stitch Composer Video Pool v1

**Status:** Implementing  
**Repos:** `mindfulnest-tooling` → `storyboard-v2`  
**Depends on:** `STITCH_SLOT_SESSION_CACHE_V1`, `resolvePersistedPlaybackFromArtifacts`, PSL stitch job cache

## Problem

Stitcher slot review uses **one** `<video>` element. Switching Intro / Phase A / Phase B / Resolution changes `src` or remounts the element (`key={url}`). The browser must decode a new clip on every switch — black frame, “Loading video…”, audible restart even when server artifacts are cached and remux is skipped.

**Category:** single-player DOM lifecycle for multi-asset navigation — not a server/remux bug.

## Category fix

**Four persistent `<video>` elements** (one per stitch slot), mounted when job URLs are known, `preload="auto"`, stacked in the composer wrap. Phase switch = **show/hide + pause inactive** — no destroy, no `src` swap on the visible element when revisiting a slot.

## 3×3 agent / counter debate (decision record)

### Axis 1 — Pool location

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — Single video + HTTP cache** | Smallest diff; browser cache should be enough. | **Rejected** — Kim still sees reload UX; cache does not skip decode/spinner reliably. |
| **Agent B — Module-level DOM outside React** | Survives Stitcher tab unmount. | **Rejected** — leak risk; Stitcher tab remount is acceptable cold start. |
| **Counter — React pool inside composer, 4 stable keys** | Matches slot keys; testable; pauses hidden elements; no src change on revisit. | **Chosen** |

### Axis 2 — Preload timing

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — Preload only active slot** | Saves bandwidth. | **Rejected** — defeats instant switch goal. |
| **Agent B — Preload all 4 on job load** | All URLs resolved from artifacts + session before first click. | **Chosen** |
| **Counter — Lazy preload on first visit** | Lower memory. | **Rejected** — second visit fast but first round-trip still slow. |

### Axis 3 — Hidden video strategy

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — `display: none`** | Simple hide. | **Rejected** — some engines throttle/decode less aggressively. |
| **Agent B — `visibility: hidden` + absolute stack** | Keeps elements in layout stack; pointer-events none on hidden. | **Chosen** |
| **Counter — Off-DOM detach** | Saves GPU. | **Rejected** — reattach = reload class of bug. |

### Axis 4 — URL updates (mux rebuild)

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — Remount pool on URL change** | Simple. | **Rejected** — nukes other slots’ loaded state. |
| **Agent B — Per-slot `src` update only when URL changes** | `shouldUpdateComposerMuxSrc` + quiet defer while playing. | **Chosen** |
| **Counter — Blob cache** | Complex; server URLs already canonical. | **Rejected** |

### Axis 5 — Waveform sync

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — Rebind masterVideo ref each switch** | Existing WaveformTimeline contract. | **Chosen** — update `composerVideoRef` to active pool element on `viewerSlot` change. |
| **Counter — New sync bus** | Over-engineered for v1. | **Deferred** |

## Architecture

```
StitcherTab
 └── StitchComposerVideoPool (STITCH_COMPOSER_VIDEO_POOL_V1)
      ├── <video data-stitch-slot="intro" />   (hidden or active)
      ├── <video data-stitch-slot="phase_a" />
      ├── <video data-stitch-slot="phase_b" />
      └── <video data-stitch-slot="resolution" />
```

### URL map

`composerSlotUrls` — `resolveSlotPlaybackPreviewUrl` for **all** slots with `video_path`, recomputed when `previewUrls` / job slots / event change.

### Loading UX

- Spinner only when **active** slot URL not in `isStitchComposerUrlLoaded` AND `readyState < HAVE_CURRENT_DATA`.
- Switching to a preloaded slot: **no spinner**.

### Markers

- `STITCH_COMPOSER_VIDEO_POOL_V1` on pool container
- `data-stitch-slot` on each video
- Active video retains `data-testid="stitcher-composer-video"`

## Files

| File | Role |
|------|------|
| `src/components/StitchComposerVideoPool.tsx` | 4-video pool component + imperative handle |
| `src/components/StitcherTab.tsx` | Replace single video; `composerSlotUrls`; ref sync |
| `src/app.css` | Pool stack + hidden slot styles |
| `e2e/stitcher_phase_switch_instant_pool.spec.ts` | Browser proof: no loading overlay on revisit |
| `Production/tools/tests/test_stitch_composer_video_pool.py` | Durability grep |

## Verification

1. Unit/durability pytest on markers and pool source patterns
2. E2E on `localhost:5112/?event=Event_2`: warm all slots → rapid switch lap → no “Loading video…” / “Building muxed preview…”
3. `deploy_storyboard_v59.sh --event Event_2` + `build-sha` = commit
4. Manual: hard refresh → phase switches feel instant after first lap

## Non-goals (v1)

- Stitcher tab keepalive (pool remounts when leaving Stitcher — acceptable)
- Preloading module-final bake video
- Mobile memory caps / lazy pool shrink
