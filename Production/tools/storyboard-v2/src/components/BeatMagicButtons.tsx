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
  onPreviewMagic?: (() => void) | undefined;
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
  onPreviewMagic,
}: BeatMagicButtonsProps) {
  const hasMagicStill = !!magicStillPath;
  const hasMagicVideo = !!magicVideoPath;

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
          {hasMagicStill && onPreviewMagic ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-magic-still-preview-${index}`}
              onClick={onPreviewMagic}
              title="Preview the magic-on-still composite video inline"
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
          {hasMagicVideo && onPreviewMagic ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-magic-video-preview-${index}`}
              onClick={onPreviewMagic}
              title="Preview the magic-on-video composite inline"
            >
              ▶ Preview magic·v
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

export function resolveBgMagicPreviewUrl(
  beat: { magic_still_path?: string | null; magic_video_path?: string | null },
  eventId: string,
): string | null {
  const rel = beat.magic_still_path || beat.magic_video_path;
  if (!rel) return null;
  const path = rel.startsWith('/') ? rel : `Production/${eventId}/${rel}`;
  return `${SERVER_BASE}/files?path=${encodeURIComponent(path)}`;
}
