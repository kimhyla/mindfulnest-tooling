# LESSONS LEARNED — WTA-32 playhead authority regression (2026-07-06)

## LD tag

`WTA32_PLAYHEAD_AUTHORITY_V1` (extends `WAVEFORM_INTERACTION_CLOSURE_V1`, `WAVEFORM_TIME_AUTHORITY_V1`)

## Symptom chain

| Phase | Operator sees | Tests |
|-------|---------------|-------|
| A | Drop/scrub "catches" but ▶ Play starts at 0:00 | Fixture green; live Event_3 red |
| B | Drop/scrub bounces to 0:00 immediately | Live drag/drop red after ac59914 |

## Root cause (one sentence)

**WaveformTimeline is a composite surface** — five interaction owners share one DOM node; fixing play-from-scrub by **keeping `lastScrubMsRef` alive through ▶ Play** made `resolvePausedPlayheadMs` **always prefer stale scrub over WaveSurfer's clock**, which re-fought every `seeking`/`audioprocess` event and zeroed the label.

## Why regressions happened

### RC-1 — Symptom patch without invariant (ac59914)

- **Change:** Stop clearing `lastScrubMsRef` on `ws.on('play')` so scrub position survives into playback.
- **Missed:** `resolvePausedPlayheadMs` treated `legacyScrubMs` as **unconditional** winner (`if (legacy > 0) return legacy`).
- **Effect:** After any scrub, **all** paused/playing `onSeeking` paths used stale scrub ms instead of current WS clock → seek fights → snap to 0.

### RC-2 — Proof-surface mismatch (RC11)

- Fixture tests used short mocked audio; Event_3 stem ~163s — `ws.play()` ignores pre-`seekTo` on long mp3.
- Live `SEEK-PLAY-LIVE-1` was added late; deploy once failed preflight before fanout (operator saw old bundle).

### RC-3 — Composite surface (architecture)

Per `TECH_SPEC_WAVEFORM_INTERACTION_CLOSURE_v1.md` §1: WaveSurfer, React state, linked video, HTML5 DnD, and cue overlays each own fragments of playhead truth. **Any fix that moves authority between layers without a named invariant regresses an adjacent layer.**

## Durable fix (665f2a67+)

| Layer | Mechanism |
|-------|-----------|
| **Authority** | `legacyScrubMs` wins **only** when `mediaTimeMs < 50` (stale-zero class) |
| **Play from scrub** | `playbackAnchorMsRef` set in `startPlayback`; cleared when WS ≥ 85% of anchor |
| **Play event** | `lastScrubMsRef` cleared on `play` (restores normal playback clock) |
| **Paused hold** | `onSeeking` while paused uses `max(authority, playhead, legacy)` — never stomp positive hold to 0 |
| **Drop** | `commitPlayheadMs` **before** cue patch; uses `endDragSeek` for 750ms hold window |
| **Pure contracts** | `waveformPlaybackAnchor.ts` + vitest matrix |

## Invariants (must never regress)

| ID | Rule |
|----|------|
| WTA-INV-8 | `legacyScrubMs` wins only when `mediaTimeMs < 50` |
| WTA-INV-9 | `playbackAnchorMsRef` set on ▶ from scrub; cleared on pause / caught-up / from-start |
| WTA-INV-10 | `lastScrubMsRef` cleared on `ws.on('play')` |
| WTA-INV-11 | Paused `onSeeking` never publishes 0 when hold ms > 0 |
| WTA-INV-12 | Drop: `commitPlayheadMs` before `onWatercolorDrop` / sfx handler |

## Gates

- `verify_wta32_playhead_durability.sh` — structural + vitest
- `verify_waveform_interaction_closure.sh` — fixture e2e + optional Event_3 live
- `verify_phase_waveform_play_durability.sh` — includes WTA-32 greps
- CI: `phase_waveform_playback.spec.ts` SEEK-PLAY-1, DROP-PLAY-1

## Do not repeat

- Fix play-from-scrub by **only** stopping `lastScrubMsRef` clear on play
- Ship WTA rows with grep-only proof (no SEEK-PLAY-1 / DROP-PLAY-1 / live path)
- Partial fanout without `verify_storyboard_fleet_bundle_parity.sh`
