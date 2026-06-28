/** PSL — Storyboard v2 event state session store. */

import { signal } from '@preact/signals';
import { apiGet } from '../api/client';
import { storyboardSessionKey } from './producerSessionKeys';
import {
  runSessionFetch,
  sessionHasReadyCache,
  type SessionSliceMeta,
} from './sessionCacheCore';

const STORYBOARD_STALE_MS = 30_000;

export interface EventState {
  event_id?: string;
  videos?: Record<string, { beats?: Record<string, unknown> }>;
  [key: string]: unknown;
}

interface StoryboardRow {
  meta: SessionSliceMeta;
  data: EventState | null;
}

const rows = new Map<string, StoryboardRow>();

export const storyboardActiveKey = signal('');
export const storyboardState = signal<EventState | null>(null);
export const storyboardError = signal<string | null>(null);
export const storyboardLoading = signal(false);

function rowForKey(key: string): StoryboardRow {
  let row = rows.get(key);
  if (!row) {
    row = {
      meta: { status: 'idle', error: null, fetchedAt: 0, inflight: null },
      data: null,
    };
    rows.set(key, row);
  }
  return row;
}

export function storyboardSessionHasCache(): boolean {
  const row = rows.get(storyboardActiveKey.value);
  return Boolean(row && sessionHasReadyCache(row.meta.status, Boolean(row.data)));
}

export async function ensureStoryboardSession(
  eventId: string,
  projectType: string,
  milestoneId: string | null,
  opts?: { force?: boolean },
): Promise<void> {
  const key = storyboardSessionKey(eventId, projectType, milestoneId);
  const row = rowForKey(key);
  storyboardActiveKey.value = key;

  await runSessionFetch(row.meta, {
    force: opts?.force ?? false,
    staleMs: STORYBOARD_STALE_MS,
    hasPayload: () => sessionHasReadyCache(row.meta.status, Boolean(row.data)),
    showLoading: (on) => { storyboardLoading.value = on && !storyboardSessionHasCache(); },
    fetcher: async () => {
      const res = await apiGet<EventState>('v2_event_state', { event_id: eventId });
      if (!res.ok || !res.data) {
        throw new Error(res.error ?? `HTTP ${res.status}`);
      }
      return res.data;
    },
    onSuccess: (data) => {
      row.data = data;
      storyboardState.value = data;
      storyboardError.value = null;
    },
    onError: (message) => {
      storyboardError.value = message;
      storyboardState.value = null;
    },
  });
}

export function resetStoryboardSessionStoreForTesting(): void {
  rows.clear();
  storyboardActiveKey.value = '';
  storyboardState.value = null;
  storyboardError.value = null;
  storyboardLoading.value = false;
}
