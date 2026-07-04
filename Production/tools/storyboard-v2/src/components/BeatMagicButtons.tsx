// BeatMagicButtons — magic trail triggers (LD-468 still / LD-469 video).
// Shared by StoryboardTab and BgTab so resolution Beat Gen keeps parity.

import { pathappPatch } from '../api/client';
import { SERVER_BASE } from '../api/endpoints';
import { activeScope } from '../state/scope';

export interface BeatMagicButtonsProps {
  index: number;
  beatId: string;
  eventId: string;
  videoRole: string;
  /** Project-relative still, e.g. Production/Event_1/images/foo.png */
  stillImagePath?: string | null;
  /** Storyboard animation_clips filename OR absolute Kling O3 path */
  videoSourcePath?: string | null;
  videoSourceIsAbsolute?: boolean;
  magicStillPath?: string | null | undefined;
  magicVideoPath?: string | null | undefined;
  magicVideoAppliesToActive?: boolean;
  magicStillAppliesToActive?: boolean;
  /** Server-enriched: video when O3 approved + magic_video, else still */
  magicCanonicalKind?: 'still' | 'video' | null | undefined;
  klingO3Status?: string | null | undefined;
  onPreviewMagicStill?: (() => void) | undefined;
  onPreviewMagicVideo?: (() => void) | undefined;
  /** Called after server clears magic still or video (refresh beat state). */
  onMagicCleared?: (() => void) | undefined;
}

export function BeatMagicButtons({
  index,
  beatId,
  eventId,
  videoRole,
  stillImagePath,
  videoSourcePath,
  videoSourceIsAbsolute = false,
  magicStillPath,
  magicVideoPath,
  magicVideoAppliesToActive = false,
  magicStillAppliesToActive = false,
  magicCanonicalKind,
  klingO3Status,
  onPreviewMagicStill,
  onPreviewMagicVideo,
  onMagicCleared,
}: BeatMagicButtonsProps) {
  const hasMagicStill = !!magicStillPath;
  const hasMagicVideo = !!magicVideoPath;
  const canonicalKind = magicCanonicalKind ?? resolveBgMagicCanonicalKind({
    kling_o3_status: klingO3Status,
    magic_still_path: magicStillPath,
    magic_video_path: magicVideoPath,
  });
  const showDualMagicPreview = hasMagicStill && hasMagicVideo;
  const onPreviewCanonicalStill = onPreviewMagicStill;
  const onPreviewCanonicalVideo = onPreviewMagicVideo;
  const showStillPreview = !!onPreviewCanonicalStill && hasMagicStill && magicStillAppliesToActive && (
    showDualMagicPreview || canonicalKind === 'still' || !hasMagicVideo
  );
  const showVideoPreview = !!onPreviewCanonicalVideo && hasMagicVideo && magicVideoAppliesToActive && (
    showDualMagicPreview || canonicalKind === 'video' || !hasMagicStill
  );

  const clearMagicVideo = async () => {
    if (!hasMagicVideo) return;
    if (!window.confirm(
      'Remove magic on video from this beat? (The old MP4 stays on disk; preview and stitch will ignore it.)',
    )) return;
    try {
      const result = await pathappPatch<{ ok?: boolean; error_message?: string; error?: string }>(
        activeScope.value,
        'storyboard_clear_magic_video',
        {
          beat_id: beatId,
          scope_event_id: eventId,
          scope_video_role: videoRole,
        },
      );
      if (!result.ok || result.data?.ok === false) {
        window.alert(result.error ?? result.data?.error_message ?? result.data?.error ?? `Clear failed (HTTP ${result.status})`);
        return;
      }
      onMagicCleared?.();
    } catch (err) {
      window.alert(`Clear failed: ${String(err)}`);
    }
  };

  const openMagicStill = () => {
    if (!stillImagePath) return;
    const u = new URL(`${SERVER_BASE}/magic`);
    u.searchParams.set('mode', 'magic_still');
    u.searchParams.set('beat_id', beatId);
    u.searchParams.set('source_image_path', stillImagePath);
    u.searchParams.set('return_endpoint', '/api/storyboard/magic_still');
    u.searchParams.set('scope_event_id', eventId);
    u.searchParams.set('scope_video_role', videoRole);
    window.open(u.toString(), '_blank');
  };

  const clearMagicStill = async () => {
    if (!hasMagicStill) return;
    if (!window.confirm(
      'Remove magic on still from this beat? (The old MP4 stays on disk; preview and stitch will ignore it.)',
    )) return;
    try {
      const result = await pathappPatch<{ ok?: boolean; error_message?: string; error?: string }>(
        activeScope.value,
        'storyboard_clear_magic_still',
        {
          beat_id: beatId,
          scope_event_id: eventId,
          scope_video_role: videoRole,
        },
      );
      if (!result.ok || result.data?.ok === false) {
        window.alert(result.error ?? result.data?.error_message ?? result.data?.error ?? `Clear failed (HTTP ${result.status})`);
        return;
      }
      onMagicCleared?.();
    } catch (err) {
      window.alert(`Clear failed: ${String(err)}`);
    }
  };

  const openMagicVideo = () => {
    if (!videoSourcePath) return;
    const u = new URL(`${SERVER_BASE}/magic`);
    u.searchParams.set('mode', 'magic_video');
    u.searchParams.set('beat_id', beatId);
    const videoParam = videoSourceIsAbsolute
      ? videoSourcePath
      : `Production/${eventId}/animation_clips/${videoSourcePath}`;
    u.searchParams.set('source_video_path', videoParam);
    if (stillImagePath) {
      u.searchParams.set('source_image_path', stillImagePath);
    }
    u.searchParams.set('return_endpoint', '/api/storyboard/magic_video');
    u.searchParams.set('scope_event_id', eventId);
    u.searchParams.set('scope_video_role', videoRole);
    window.open(u.toString(), '_blank');
  };

  return (
    <div class="mn-beat-magic-row" data-testid={`beat-magic-row-${index}`}>
      {stillImagePath ? (
        <>
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-magic-still-${index}`}
            onClick={openMagicStill}
            title={hasMagicStill
              ? 'Re-draw magic path on still — replaces the current magic_still_path'
              : 'Add magic trail on still (LD-468)'}
          >
            {hasMagicStill ? '↻ Redo magic on still' : '🌟 Add magic on still'}
          </button>
          {hasMagicStill ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-magic-clear-still-${index}`}
              onClick={() => { void clearMagicStill(); }}
              title="Remove magic_still_path from this beat (does not delete the MP4 file)"
            >
              ✕ Clear magic on still
            </button>
          ) : null}
          {showStillPreview && onPreviewCanonicalStill ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-magic-preview-still-${index}`}
              onClick={onPreviewCanonicalStill}
              title="Preview magic-on-still composite with ElevenLabs dialogue"
            >
              {showDualMagicPreview ? '▶ Preview magic (still)' : '▶ Preview magic'}
            </button>
          ) : null}
        </>
      ) : null}
      {videoSourcePath ? (
        <>
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-magic-video-${index}`}
            onClick={openMagicVideo}
            title={hasMagicVideo
              ? 'Re-draw magic path on lipsync frame — replaces the current magic_video_path'
              : 'Add magic trail on video (LD-469)'}
          >
            {hasMagicVideo ? '↻ Redo magic on video' : '🎬 Add magic on video'}
          </button>
          {hasMagicVideo ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-magic-clear-video-${index}`}
              onClick={() => { void clearMagicVideo(); }}
              title="Remove magic_video_path from this beat (does not delete the MP4 file)"
            >
              ✕ Clear magic on video
            </button>
          ) : null}
          {showVideoPreview && onPreviewCanonicalVideo ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-magic-preview-video-${index}`}
              onClick={onPreviewCanonicalVideo}
              title="Preview magic-on-video composite in the approved O3 player"
            >
              {showDualMagicPreview ? '▶ Preview magic (video)' : '▶ Preview magic'}
            </button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/** Map absolute Dropbox/event paths to Production/Event_N/... for path_picker. */
export function toProjectRelativeMediaPath(absOrRel: string, eventId: string): string {
  if (absOrRel.startsWith('Production/')) return absOrRel;
  const marker = `/Production/${eventId}/`;
  const idx = absOrRel.indexOf(marker);
  if (idx >= 0) return `Production/${eventId}/${absOrRel.slice(idx + marker.length)}`;
  const prodIdx = absOrRel.indexOf('/Production/');
  if (prodIdx >= 0) return absOrRel.slice(prodIdx + 1);
  return absOrRel;
}

/** Resolve Beat Gen still source for magic_still (mirrors beat_generator.resolve_beat_magic_still_source_path). */
export function resolveBgMagicStillSourcePath(
  beat: {
    reference_image?: { abs_path?: string } | null;
    bg_ref_image?: { abs_path?: string } | null;
    start_frame_image?: { abs_path?: string } | null;
    end_frame_image?: { abs_path?: string } | null;
    gpt_options?: Array<{ local_path?: string; abs_path?: string } | null> | null;
    flux_options?: Array<{ local_path?: string; abs_path?: string } | null> | null;
    accepted_library_ref?: { abs_path?: string } | null;
  },
  eventId: string,
): string | null {
  const libAp = beat.accepted_library_ref?.abs_path;
  if (libAp) {
    const rel = toProjectRelativeMediaPath(libAp, eventId);
    if (rel) return rel;
  }
  for (const opt of [...(beat.gpt_options ?? []), ...(beat.flux_options ?? [])]) {
    if (!opt) continue;
    const ap = opt.local_path || opt.abs_path;
    if (ap) return toProjectRelativeMediaPath(ap, eventId);
  }
  for (const ref of [
    beat.start_frame_image,
    beat.bg_ref_image,
    beat.end_frame_image,
    beat.reference_image,
  ]) {
    const ap = ref?.abs_path;
    if (ap) return toProjectRelativeMediaPath(ap, eventId);
  }
  return null;
}

function magicPathToPreviewUrl(
  rel: string | null | undefined,
  eventId: string,
): string | null {
  if (!rel) return null;
  const path = rel.startsWith('/') ? rel : `Production/${eventId}/${rel}`;
  return `${SERVER_BASE}/files?path=${encodeURIComponent(path)}`;
}

export function resolveBgMagicStillPreviewUrl(
  beat: {
    magic_still_path?: string | null;
    magic_still_path_exists?: boolean;
    magic_video_path?: string | null;
  },
  eventId: string,
): string | null {
  if (beat.magic_still_path_exists === false) return null;
  const base = magicPathToPreviewUrl(beat.magic_still_path, eventId);
  if (!base || !beat.magic_still_path) return base;
  return `${base}&v=${encodeURIComponent(beat.magic_still_path)}`;
}

export function resolveBgMagicVideoPreviewUrl(
  beat: {
    magic_still_path?: string | null;
    magic_video_path?: string | null;
    magic_video_path_exists?: boolean;
  },
  eventId: string,
): string | null {
  if (beat.magic_video_path_exists === false) return null;
  const base = magicPathToPreviewUrl(beat.magic_video_path, eventId);
  if (!base || !beat.magic_video_path) return base;
  return `${base}&v=${encodeURIComponent(beat.magic_video_path)}`;
}

export function resolveBgMagicCanonicalKind(beat: {
  kling_o3_status?: string | null | undefined;
  magic_canonical_kind?: 'still' | 'video' | null | undefined;
  magic_still_path?: string | null | undefined;
  magic_video_path?: string | null | undefined;
}): 'still' | 'video' | null {
  if (beat.magic_canonical_kind === 'still' || beat.magic_canonical_kind === 'video') {
    return beat.magic_canonical_kind;
  }
  // Offline fallback only — server enriches magic_canonical_kind from disk mtimes.
  if (beat.magic_still_path && !beat.magic_video_path) return 'still';
  if (beat.magic_video_path && !beat.magic_still_path) return 'video';
  if (beat.magic_still_path) return 'still';
  if (beat.magic_video_path) return 'video';
  return null;
}

/** O3 tiles always play the Kling/harvest clip — magic preview uses Preview magic buttons. */
export function resolveO3TileMagicOverrideUrl(
  _beat: {
    kling_o3_video_path?: string | null;
    magic_video_path?: string | null;
    magic_canonical_kind?: 'still' | 'video' | null;
    magic_video_path_exists?: boolean;
  },
  _option: { video_path?: string | null } | null | undefined,
  _eventId: string,
): string | null {
  return null;
}
