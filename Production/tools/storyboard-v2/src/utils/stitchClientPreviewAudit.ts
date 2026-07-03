/**
 * STITCH_CLIENT_PREVIEW_AUDIT_V1 — client forensics for Stitcher slot review playback.
 * Mirrors bg_o3_trim_audit: console + POST → event-dir _stitch_client_preview_audit.jsonl
 */

import { SERVER_BASE } from '../api/endpoints';
import { activeScope } from '../state/scope';

export const STITCH_CLIENT_PREVIEW_AUDIT_V1 = 'STITCH_CLIENT_PREVIEW_AUDIT_V1';

function bundledBuildSha(): string | undefined {
  if (typeof document === 'undefined') return undefined;
  return document.querySelector('meta[name="build-sha"]')?.getAttribute('content') ?? undefined;
}

export function stitchClientPreviewAudit(
  event: string,
  fields: Record<string, unknown> = {},
): void {
  const row = {
    code: STITCH_CLIENT_PREVIEW_AUDIT_V1,
    ts: new Date().toISOString(),
    event,
    event_id: activeScope.value.event_id,
    build_sha: bundledBuildSha(),
    ...fields,
  };
  console.info('[stitch_client_preview_audit]', row);
  void fetch(`${SERVER_BASE}/api/stitch_editor/client_preview_audit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(row),
  }).catch(() => {
    /* audit must never block playback */
  });
}

export function videoPlaybackSnapshot(video: HTMLVideoElement | null | undefined): Record<string, unknown> {
  if (!video) return { video: null };
  return {
    src_tail: (video.currentSrc || video.src || '').slice(-120),
    ready_state: video.readyState,
    network_state: video.networkState,
    paused: video.paused,
    ended: video.ended,
    current_time: video.currentTime,
    duration: Number.isFinite(video.duration) ? video.duration : null,
    error_code: video.error?.code ?? null,
    error_message: video.error?.message ?? null,
  };
}
