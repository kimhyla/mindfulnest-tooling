# TECH_SPEC — STITCH_UNIFIED_PLAYBACK_STANDALONE_v1

**Supersedes:** `STITCH_STANDALONE_DRY_VIDEO_V1` separate preview player (removed).

## Problem

Milestone Stitcher forked playback: dry `<video>` in strip footer + `playbackDisabled` strip waveform. Play on video did not drive waveform — SFX drag requires `STITCH_UNIFIED_PLAYBACK_V1` (masterVideo + displayOnly waveform in slot composer).

## 3×3 debate

| | A: Mirror video→waveform events | B: Reuse slot composer (event path) | C: New standalone sync hook |
|--|--|--|--|
| **Pro** | Small patch | Zero new architecture; Phase A/B parity | Isolated |
| **Con** | Two players remain | Removes milestone fork | Third playback path |
| **Verdict** | Rejected | **Winner** | Rejected |

## Category fix

One playback surface for all Stitcher modes:

1. `composerSlotUrls` iterates `STANDALONE_SLOT_DEFS` or `SLOT_DEFS`.
2. Slot composer always rendered when job loaded (milestone + event).
3. Strip slot hides duplicate waveform when `sd.key === viewerSlot`; shows composer hint.
4. `StitchComposerVideoPool` includes `standalone` pool slot.
5. Mux/ambient hydrate effects run for standalone (removed `standaloneMode` early-return).

## Gates

- Browser: `[data-testid="stitcher-slot-composer"]` present in milestone scope.
- Browser: `[data-testid="stitcher-composer-video"]` + unified waveform; play advances both.
- No `[data-testid="stitcher-video-player"]` separate standalone player.
