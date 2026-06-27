/** PSL — Production Map session store. */

import { signal } from '@preact/signals';
import { apiGet } from '../api/client';
import { mapSessionKey } from './producerSessionKeys';
import {
  runSessionFetch,
  sessionHasReadyCache,
  type SessionSliceMeta,
} from './sessionCacheCore';

const MAP_STALE_MS = 120_000;

export interface MapModuleRow {
  module_id?: string;
  title?: string;
  status?: string;
  [key: string]: unknown;
}

export interface MapResponse {
  modules?: MapModuleRow[];
  [key: string]: unknown;
}

interface MapRow {
  meta: SessionSliceMeta;
  data: MapResponse | null;
}

const rows = new Map<string, MapRow>();

export const mapActiveKey = signal('');
export const mapData = signal<MapResponse | null>(null);
export const mapError = signal<string | null>(null);
export const mapLoading = signal(false);

function rowForKey(key: string): MapRow {
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

export function mapSessionHasCache(): boolean {
  const row = rows.get(mapActiveKey.value);
  return Boolean(row && sessionHasReadyCache(row.meta.status, Boolean(row.data)));
}

export async function ensureMapSession(eventId: string, opts?: { force?: boolean }): Promise<void> {
  const key = mapSessionKey(eventId);
  const row = rowForKey(key);
  mapActiveKey.value = key;

  await runSessionFetch(row.meta, {
    force: opts?.force ?? false,
    staleMs: MAP_STALE_MS,
    hasPayload: () => sessionHasReadyCache(row.meta.status, Boolean(row.data)),
    showLoading: (on) => { mapLoading.value = on && !mapSessionHasCache(); },
    fetcher: async () => {
      const res = await apiGet<MapResponse>('production_map');
      if (!res.ok || !res.data) {
        throw new Error(res.error ?? `HTTP ${res.status}`);
      }
      return res.data;
    },
    onSuccess: (data) => {
      row.data = data;
      mapData.value = data;
      mapError.value = null;
    },
    onError: (message) => {
      mapError.value = message;
      mapData.value = null;
    },
  });
}

export function resetMapSessionStoreForTesting(): void {
  rows.clear();
  mapActiveKey.value = '';
  mapData.value = null;
  mapError.value = null;
  mapLoading.value = false;
}
