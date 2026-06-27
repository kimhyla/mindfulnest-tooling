# TECH_SPEC_STITCH_SFX_PLAYBACK_TRUTH_V1

## Problem

Milestone (and event) Stitcher: operator drops SFX on waveform; marker appears at drop
position but playback audio has no SFX (or SFX at wrong time). UI may show
"SFX preview" while playing dry `/files` lipsync MP4.

## Root cause chain (terminal → surface)

1. **Terminal:** `resolveSlotPlaybackPreviewUrl` returns dry slot video when
   `stitchSlotRequiresMuxedPreview` is true but no mux artifact exists yet.
2. **Why:** STITCH_COMPOSER_DRY_PLAYBACK_V1 prioritized instant video bind over
   mux truth; viewer effect treats any URL as playback-ready and skips rebuild.
3. **Why save didn't recover:** `saveJobSlots` cleared `previewUrls` on geometry
   change but did not queue `pendingMuxBuildsRef` (unlike job load path).
4. **Timeline skew (sibling):** displayOnly waveform used peaks duration (~79.6s)
   for drop math while video/mux clock is `video_dur_ms` (~94.1s) — markers and
   playhead diverge from mux `adelay=offset_ms` on full slot duration.
5. **Milestone persistence (sibling):** empty `standalone` bootstrap on server;
   PSL-only client state until first save; preview persist used global stitch store.

## 3×3 agent debate (summary)

| Agent | Position |
|-------|----------|
| A1 Playback | Never bind dry URL when SFX cues exist; undefined → mux build |
| A2 Timeline | Single clock: `mux_preview_duration_ms ?? video_dur_ms` for drop/cue/sync |
| A3 Session | Rekey stitch slot session + preview LS to `stitchJobSessionKey` |
| B1 Server | `handle_stitch_preview` must swap `stitch_state_store_for_job` like save |
| B2 Server | Hydrate milestone `standalone` from `Milestones/{id}/assembled/standalone_*.mp4` |
| B3 UX | `composerUsingMux` only when URL is mux artifact, not dry `/files` |
| C1 Tests | Golden: SFX slot + empty preview state → resolve returns undefined |
| C2 Tests | pytest: milestone disk hydrate + preview state store swap |
| C3 QA | Browser: drop SFX → mux completes → hear SFX at dropped second |

**Verdict:** Implement A1+A2+B1+B2+B3 + save mux queue (category); session rekey (A3) in same commit.

## Category fix (STITCH_SFX_PLAYBACK_TRUTH_V1)

1. **Playback truth gate** — dry fallback only when slot has no SFX cues.
2. **Mux rebuild on SFX geometry save** — queue same path as job load.
3. **Slot timeline clock** — pass `videoDurMs` as authoritative `durationMs` to composer waveform.
4. **Milestone server** — disk hydrate + preview/save state store routing.
5. **Session scope** — cache keys use `stitchJobSessionKey`, not bare `eventId`.

## Sibling bugs closed

- False "SFX preview" label on dry video
- SFX drop after export without mux rebuild
- Milestone cold load empty job despite assembled MP4 on disk
- Milestone mux artifact persist to wrong stitch state file
- Event↔milestone preview session bleed on same Event_N port

## Proof

- Unit: `stitchPersistedPlaybackArtifacts.test.ts`, `test_milestone_stitch_disk_hydrate.py`, `test_stitch_preview_state_store.py`
- API: save SFX → preview → ffprobe duration + mux hash on milestone `stitch_state.json`
- Browser: `localhost:5112/?video=intro&milestone=milestone1_arc1` hard refresh, drop SFX, pause after mux, hear cue
