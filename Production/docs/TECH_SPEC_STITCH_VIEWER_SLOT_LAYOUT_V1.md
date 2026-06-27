# TECH_SPEC — STITCH_VIEWER_SLOT_LAYOUT_V1

**Status:** Implementing  
**Repos:** `mindfulnest-tooling` → `storyboard-v2`  
**Supersedes:** `STITCH_MILESTONE_VIEWER_SLOT_V1` milestone-only branch in `resolveStitchViewerSlot` (ab34e17 patch layer)

## Problem

Milestone Stitcher showed **intro — slot review** with empty/building composer while the **standalone** strip waveform played audio separately. Operator heard looping intro beats with no visible video.

## Root cause chain (3 levels of “why”)

| Level | Cause | Evidence |
|-------|--------|----------|
| **Symptom** | Composer targeted `intro`; strip rendered standalone waveform as a second surface | User screenshots; pre-fix header text |
| **Mechanism** | `viewerSlot = trackFocusedSlot ?? multiPhaseSlots[0]` — stale React state `intro` beat layout default `standalone` | `git show a5891e2:StitcherTab.tsx` ~L979 |
| **Terminal cause** | **No invariant that viewer slot ∈ current job layout keys.** Track focus is keepalive React state + LS keyed by `eventId` only; scope switch (event 4-slot ↔ milestone 1-slot) changes layout without invalidating focus. Track-focus effect skipped milestone (`if (standaloneMode) return`). | `stitchTrackFocus.ts` LS prefix; `StitcherTab.tsx` L638–677; PSL keepalive |

**First cause (no cause besides itself):** Stitcher conflated **layout schema** (which slots exist in the loaded job) with **navigation memory** (trackFocusedSlot / LS) without validating memory against schema on every resolve.

## 3×3 agent debate (decision record)

### Axis 1 — Viewer slot source of truth

| Position | Argument | Verdict |
|----------|----------|---------|
| **A — Layout-validated viewer** | `viewerSlot` must be ∈ `layoutSlotKeys`; track focus used only when valid. One rule for event + milestone; removes `standaloneMode` branch. | **Chosen** |
| **B — Namespaced LS + reset on scope change** | Fixes bleed via `stitchJobSessionKey`; keeps old formula. | **Partial** — necessary but not sufficient if in-memory React state stale |
| **C — Eliminate trackFocusedSlot** | Derive from URL only. | **Rejected** — large refactor; track click UX needs local focus |

### Axis 2 — Persistence namespace

| Position | Argument | Verdict |
|----------|----------|---------|
| **A — Keep eventId LS** | Backward compat. | **Rejected** — milestone + event share Event_2 id |
| **B — `stitchJobSessionKey` LS** | Matches PSL stitch cache (`milestone:milestone1_arc1` vs `Event_2`). | **Chosen** |
| **C — No LS** | Simplest. | **Rejected** — hard refresh should restore track segment |

### Axis 3 — Scope switch hygiene

| Position | Argument | Verdict |
|----------|----------|---------|
| **A — Milestone-only cleanup effect** | ab34e17 approach. | **Rejected** — N special cases per layout |
| **B — On `stitchSessionKey` change: reset focus via layout picker + stop playback + clear cross-layout previewUrls** | Category hygiene at boundary. | **Chosen** |
| **C — Unmount StitcherTab on scope change** | Nuclear reset. | **Rejected** — breaks PSL instant tab switch |

## Category fix

1. **`resolveStitchViewerSlot({ layoutSlotKeys, trackFocusedSlot })`** — return focus only if ∈ layout; else `layoutSlotKeys[0]`.
2. **`pickTrackSlotForLayout(..., stitchSessionKey, ...)`** — unified track picker for event + milestone layouts.
3. **Track focus LS** keyed by `stitchJobSessionKey`, not bare `eventId`.
4. **On `stitchSessionKey` change** — stop playback, clear previewUrls, re-pick focus from layout.
5. **Single track-focus effect** for all project types (remove `standaloneMode` early return).

## Sibling bugs closed

| Sibling | How closed |
|---------|------------|
| Milestone composer shows event slot name | Layout validation |
| Split playback (composer vs strip waveform) | Correct viewerSlot → strip shows hint not duplicate waveform |
| Stale mux build on wrong slot | viewerSlotData undefined → no hydrate on ghost slot |
| Event track focus LS bleeds Event_2 → milestone on same event | Session-key LS |
| Future 2-slot / N-slot layouts | Same layout validation — no new mode branches |

## Sibling bugs still open (honest)

| Sibling | Layer |
|---------|--------|
| `stitchSlotSessionCache` in-memory + LS preview keyed by `eventId` only | Session cache namespace |
| `?video=intro` URL vs `activeTargetVideo=standalone` in milestone | URL scope router (server already `active_video: standalone`) |
| Video pool retains hidden slot elements until URL cleared | Pool lifecycle (partially fixed ab34e17) |

## Gates

- Unit: layout validation rejects `intro` when layout is `['standalone']`.
- Unit: LS round-trip uses `stitchJobSessionKey`.
- E2E: milestone URL → composer header **Standalone — slot review** + video src contains `Milestones/`.
- Browser: hard refresh same URL; no background audio; play drives waveform.

## Markers

- `STITCH_VIEWER_SLOT_LAYOUT_V1` on slot composer
- `data-stitch-track-focus-session-key` on multiphase track (debug)

---

## Addendum — STITCH_SAVE_SLOT_DURABLE_MERGE_V1 (SFX drop empty player)

### Symptom
After SFX drop: long "Building muxed preview…", then empty player ("Assign slot video"), 2.5s track segment, ambient `— none —`. Server still has `video_path`.

### Terminal cause
**Client `setJob` after save used the client patch dict only.** Server `merge_slots` preserves `video_path` from previous slot, but save response does not return merged slots. If PSL cache race left client slot empty (no `video_path`), SFX save sent patch without video → client clobbered local truth → composer had no URL.

### Category fix
1. `mergeStitchJobSlotsClientPatch` before `setJob` — restore durable fields from prev slot.
2. Re-fetch `stitch_editor_job` after save — server truth wins.
3. `buildSlotPreview` failure → bind dry `/files` URL (STITCH_MUX_FAIL_KEEP_DRY_V1).
4. Block SFX drop when slot has no `video_path`.
5. Server: persist mux artifacts for `standalone` via `_valid_stitch_slot`.
