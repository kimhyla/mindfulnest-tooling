// BeatMagicButtons — magic trail triggers (LD-468 still / LD-469 video).
// Shared by StoryboardTab and BgTab so resolution Beat Gen keeps parity.

import { SERVER_BASE } from '../api/endpoints';

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
  /** Server-enriched: video when O3 approved + magic_video, else still */
  magicCanonicalKind?: 'still' | 'video' | null | undefined;
  klingO3Status?: string | null | undefined;
  onPreviewMagicStill?: (() => void) | undefined;
  onPreviewMagicVideo?: (() => void) | undefined;
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
  magicCanonicalKind,
  klingO3Status,
  onPreviewMagicStill,
  onPreviewMagicVideo,
}: BeatMagicButtonsProps) {
  const hasMagicStill = !!magicStillPath;
  const hasMagicVideo = !!magicVideoPath;
  const canonicalKind = magicCanonicalKind ?? resolveBgMagicCanonicalKind({
    kling_o3_status: klingO3Status,
    magic_still_path: magicStillPath,
    magic_video_path: magicVideoPath,
  });
  const onPreviewCanonical = canonicalKind === 'video'
    ? onPreviewMagicVideo
    : canonicalKind === 'still'
      ? onPreviewMagicStill
      : undefined;
  const showCanonicalPreview = !!onPreviewCanonical && (
    (canonicalKind === 'video' && hasMagicVideo)
    || (canonicalKind === 'still' && hasMagicStill)
  );

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
          {showCanonicalPreview && canonicalKind === 'still' && onPreviewCanonical ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-magic-preview-${index}`}
              onClick={onPreviewCanonical}
              title="Preview magic-on-still composite with ElevenLabs dialogue"
            >
              ▶ Preview magic
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
          {showCanonicalPreview && canonicalKind === 'video' && onPreviewCanonical ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-magic-preview-${index}`}
              onClick={onPreviewCanonical}
              title="Preview magic-on-video composite in the approved O3 player"
            >
              ▶ Preview magic
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
  },
  eventId: string,
): string | null {
  for (const ref of [
    beat.start_frame_image,
    beat.reference_image,
    beat.end_frame_image,
    beat.bg_ref_image,
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
  beat: { magic_still_path?: string | null; magic_video_path?: string | null },
  eventId: string,
): string | null {
  return magicPathToPreviewUrl(beat.magic_still_path, eventId);
}

export function resolveBgMagicVideoPreviewUrl(
  beat: { magic_still_path?: string | null; magic_video_path?: string | null },
  eventId: string,
): string | null {
  return magicPathToPreviewUrl(beat.magic_video_path, eventId);
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
  if (beat.kling_o3_status === 'approved' && beat.magic_video_path) return 'video';
  if (beat.magic_still_path) return 'still';
  if (beat.magic_video_path) return 'video';
  return null;
}
