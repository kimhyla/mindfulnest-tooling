/**
 * LINKED_VIDEO_MATCH_AUDIO_V1 — shared policy for Kling / lipsync preview playback.
 *
 * Coverage (all events, all beats — wired in source, not per-event data):
 *
 * 1. Phase A/B lipsync (WaveformTimeline + linked <video>):
 *    When preview MP4 basename matches waveform audio basename, WaveSurfer binds
 *    the same <video> via setMediaElement (VQ-P1 single clock — no dual decode).
 *
 * 2. Beat Gen Kling preview (StoryboardTab, BeatCompositePreview, BgTab O3):
 *    Apply PLAYBACK_VIDEO_ANTI_BANDING_CLASS on native <video> play() surfaces.
 *
 * 3. Stitcher (composer, slot preview, bake preview):
 *    Same CSS class on all stitcher <video> elements.
 */

/** CSS class — object-fit contain + compositor layer (see app.css). */
export const PLAYBACK_VIDEO_ANTI_BANDING_CLASS = 'mn-playback-video-stable';

/** Same basename on disk (e.g. phase_b_lipsync_*.mp4 on video + waveform). */
export function linkedMediaSameFilename(
  videoName: string | null | undefined,
  audioName: string | null | undefined,
): boolean {
  if (!videoName || !audioName) return false;
  const v = videoName.split('/').pop() ?? videoName;
  const a = audioName.split('/').pop() ?? audioName;
  return v === a;
}
