// Canonical video-role switching — shared by header VideoSelector and Beat Gen Segment dropdown.
// Keeps activeTargetVideo, URL ?video=, server sidecar active_context, and BG beats in sync.

import { activeScope, activeTargetVideo } from './scope';
import { pathappPatch } from '../api/client';

/** BG segment phase → storyboard video role (mirrors server _BG_PHASE_MAP). */
const PHASE_TO_VIDEO_ROLE: Record<string, string> = {
  pre: 'intro',
  post: 'resolution',
  main: 'standalone',
};

export function videoRoleForBgPhase(phase: string): string | null {
  return PHASE_TO_VIDEO_ROLE[phase] ?? null;
}

const URL_VIDEO_ROLES = new Set(['intro', 'resolution', 'phase_a', 'phase_b', 'standalone']);

/** Honor bookmark ?video=resolution on load (Stitcher + Beat Gen scope). */
export function syncActiveVideoRoleFromUrl(): void {
  if (typeof window === 'undefined') return;
  try {
    const role = new URL(window.location.href).searchParams.get('video');
    if (role && URL_VIDEO_ROLES.has(role)) {
      activeTargetVideo.value = role;
    }
  } catch {
    // headless / restricted context
  }
}

/**
 * Keep the URL ?video= hint in step with the signal — bookmark truth.
 * Also used when VideoSelector adopts the server's persisted active_video on
 * mount (PSL_STALE_KEY_HYDRATION_GUARD_V1 companion: a URL stuck on
 * video=intro while the signal says resolution misled debugging).
 */
export function syncUrlVideoParam(role: string): void {
  if (typeof window === 'undefined' || !role) return;
  try {
    const url = new URL(window.location.href);
    url.searchParams.set('video', role);
    window.history.replaceState({}, '', url.toString());
  } catch {
    // no-op when history API unavailable
  }
}

export interface SetActiveVideoRoleResult {
  ok: boolean;
  status: number;
  error?: string;
  activeVideo?: string;
}

/** Persist video role on server + update client scope signal + URL hint. */
export async function setActiveVideoRole(newRole: string): Promise<SetActiveVideoRoleResult> {
  if (!newRole || newRole === activeTargetVideo.value) {
    return { ok: true, status: 200, activeVideo: activeTargetVideo.value };
  }
  const res = await pathappPatch<{ ok: boolean; active_video?: string }>(
    activeScope.value,
    'video_set_active',
    { video_role: newRole },
  );
  if (!res.ok) {
    return { ok: false, status: res.status, error: res.error ?? `HTTP ${res.status}` };
  }
  const active = res.data?.active_video ?? newRole;
  activeTargetVideo.value = active;
  syncUrlVideoParam(active);
  return { ok: true, status: res.status, activeVideo: active };
}
