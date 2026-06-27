/** Shared Beat Generator poll helpers (BgTab + BgPollCoordinator). */

import type { BgBeat } from '../types/bgBeat';
import type { ArloO3PollResponse } from '../o3GenerationIntent';
import {
  applyO3GalleryFieldsFromPoll,
  stripProtectedPromptFromPatch,
} from '../state/promptEditRegistry';

export function mergeBeatFromO3Poll(beats: BgBeat[], patch: BgBeat): BgBeat[] {
  const safePatch = stripProtectedPromptFromPatch(patch);
  const idx = beats.findIndex((b) => b.beat_id === safePatch.beat_id);
  if (idx < 0) return beats;
  const next = [...beats];
  next[idx] = applyO3GalleryFieldsFromPoll(beats[idx], safePatch);
  return next;
}

export function isNetworkPollBlip(res: { ok: boolean; status: number; error?: string }): boolean {
  return !res.ok
    && res.status === 0
    && /failed to fetch|networkerror|load failed/i.test(res.error ?? '');
}

export function isSidecarLockPollBlip(
  res: { ok: boolean; status: number; error?: string; error_message?: string },
): boolean {
  const msg = `${res.error ?? ''} ${res.error_message ?? ''}`.toLowerCase();
  return !res.ok && /sidecar lock timeout|beat_generator_state\.json\.lock/i.test(msg);
}

export function isStaleO3JobPoll(
  res: { ok: boolean; status: number; error?: string; error_code?: string },
): boolean {
  if (res.ok) return false;
  return res.error_code === 'ARLO_JOB_NOT_FOUND'
    || (res.status === 404 && /job.*not in server memory|unknown.*job_id/i.test(res.error ?? ''));
}

export function formatO3JobFailure(error?: string | null): string {
  const raw = (error ?? '').trim();
  if (!raw) return 'O3 voice job failed; previous approved clip was kept active.';
  const runtime = raw.includes('RuntimeError:') ? raw.split('RuntimeError:').pop()!.trim() : raw;
  if (runtime.includes('Kling LipSync returned sub-720p output')) {
    const first = runtime.split('\n')[0];
    return first.includes('Previous approved clip was kept active')
      ? first
      : `${first} Previous approved clip was kept active.`;
  }
  if (runtime.includes('Could not download the input')) {
    return 'WaveSpeed could not download the lipsync input URL and data-URI fallback did not complete; previous approved clip was kept active.';
  }
  if (runtime.includes('No lipsync input host returned byte-complete public files')) {
    return 'Lipsync could not upload video/audio to a public URL WaveSpeed can fetch. Configure Cloudflare R2 on this server, then restart Event servers.';
  }
  if (runtime.includes('O3 job process is no longer running')) {
    return 'The O3 job process stopped without a completion result. The stale job marker was cleared; previous approved clip was kept active.';
  }
  return runtime.split('\n').filter(Boolean).pop()?.slice(0, 500) ?? runtime.slice(0, 500);
}

type O3BeatSlotFields = {
  kling_o3_video_path?: string | null;
  kling_o3_options?: Array<{ video_path?: string | null; source?: string | null } | null> | null;
};

function isUserSelectableO3Video(path?: string | null, source?: string | null): boolean {
  if (source === 'still_insert_static_hold' || source === 'still_insert_ken_burns' || source === 'still_insert_kling_idle') {
    return Boolean(path);
  }
  const name = (path ?? '').toLowerCase().split('/').pop() ?? '';
  return Boolean(path)
    && !name.includes('_silent_o3_base')
    && !name.includes('_delivery_input')
    && !name.includes('_noaudio');
}

function beatHasPopulatedO3Slot(beat: O3BeatSlotFields | null | undefined): boolean {
  if (!beat) return false;
  if (isUserSelectableO3Video(beat.kling_o3_video_path)) return true;
  return (beat.kling_o3_options ?? []).some((o) => isUserSelectableO3Video(o?.video_path, o?.source));
}

export function o3PollResultHasVideo(res: ArloO3PollResponse): boolean {
  if (res.result?.video) return true;
  if (res.terminal?.delivered?.video_path) return true;
  return beatHasPopulatedO3Slot(res.beat as O3BeatSlotFields);
}

/** When server poll is terminal but beat snapshot was missing, still clear busy + show clip path. */
export function beatPatchFromO3PollTerminal(
  beatId: string,
  res: ArloO3PollResponse,
): BgBeat | null {
  if (res.beat?.beat_id) return res.beat as BgBeat;
  if (res.status !== 'done' && res.status !== 'done_with_warning' && res.status !== 'failed') {
    return null;
  }
  const video = res.result?.video ?? res.terminal?.delivered?.video_path ?? null;
  const patch: BgBeat = {
    beat_id: beatId,
    job_busy: false,
    o3_current_job_id: null,
  };
  if (res.status === 'failed') {
    patch.kling_o3_voice_fix_status = 'failed';
  } else {
    patch.kling_o3_voice_fix_status = 'approved';
    patch.kling_o3_status = 'approved';
    patch.status = 'approved';
  }
  if (video) {
    patch.kling_o3_video_path = video;
    patch.kling_o3_video_path_exists = true;
  }
  return patch;
}
