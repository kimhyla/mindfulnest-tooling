/**
 * WTA32_PLAYBACK_ANCHOR_V1 — pure playhead hold/reassert contracts for WaveformTimeline.
 * Extracted so ac59914-class regressions are caught by vitest, not only e2e.
 */
export const WTA32_PLAYBACK_ANCHOR_V1 = 'WTA32_PLAYBACK_ANCHOR_V1';

/** ▶ from scrub: prefer anchor until WS catches up. */
export function resolvePlaybackAuthorityMs(
  playbackAnchorMs: number | null | undefined,
  authorityPlayheadMs: number,
): number {
  if (playbackAnchorMs != null && playbackAnchorMs > 0) return playbackAnchorMs;
  return authorityPlayheadMs;
}

/** Long stem mp3: ws.play() may start near 0 while authority holds scrub ms. */
export function shouldReassertPlayheadFromAuthority(
  authorityMs: number,
  wsMs: number,
  minAuthorityMs = 500,
  staleFraction = 0.15,
): boolean {
  if (authorityMs <= minAuthorityMs) return false;
  return wsMs < authorityMs * staleFraction;
}

/** WS clock caught up — drop playback anchor. */
export function shouldClearPlaybackAnchor(
  anchorMs: number | null | undefined,
  wsMs: number,
  caughtUpFraction = 0.85,
): boolean {
  if (anchorMs == null || anchorMs <= 0) return false;
  return wsMs >= anchorMs * caughtUpFraction;
}

/** Paused onSeeking: never stomp a positive scrub/drop hold to stale zero. */
export function pausedPlayheadHoldMs(
  authorityMs: number,
  playheadMs: number,
  legacyScrubMs: number | null | undefined,
): number {
  return Math.max(authorityMs, playheadMs, legacyScrubMs ?? 0);
}
