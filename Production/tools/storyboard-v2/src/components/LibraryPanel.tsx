// LibraryPanel — Event-1 image library, mtime-sorted (LD-452 / Fix-V).
// Renders real data from GET /api/cr/library for the active event.
//
// S5.5c — migrated to AssetTile primitive (LD UI_PRIMITIVES_SHARED_V1) with
// hover-delete wiring to /api/cr/library/delete via pathappPatch (single
// mutation channel, no raw fetch). Tiles are also draggable so future drop
// targets (Beat Generator slots, Stitcher SFX) can consume them via the
// dragdrop helper.

import { useEffect, useState } from 'preact/hooks';
import { activeScope } from '../state/scope';
import { apiGet, pathappPatch } from '../api/client';
import { AssetTile } from './ui/AssetTile';
import { pushToast } from './ui/Toast';
import type { DragPayload } from '../utils/dragdrop';

interface LibItem {
  key?: string;
  abs_path?: string;
  filename?: string;
  thumb_b64?: string;
  gallery_b64?: string;
  thumb_url?: string;
  display_name?: string;
  mtime?: number;
  tier?: string;
  width?: number;
  height?: number;
}

interface LibraryResponse {
  images?: LibItem[];
  items?: LibItem[];
  sources?: LibItem[];
  crops?: LibItem[];
  masters?: LibItem[];
}

export function flattenLibraryResponse(r: LibraryResponse): LibItem[] {
  if (Array.isArray(r.images)) return r.images;
  if (Array.isArray(r.items)) return r.items;
  return [...(r.sources ?? []), ...(r.crops ?? []), ...(r.masters ?? [])];
}

function thumbSrc(it: LibItem): string | undefined {
  return it.thumb_b64 ?? it.thumb_url ?? undefined;
}

function displayName(it: LibItem): string {
  return it.display_name ?? it.filename ?? it.key ?? '(unnamed)';
}

export function LibraryPanel() {
  const [items, setItems] = useState<LibItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await apiGet<LibraryResponse>('cr_library', {
        event_id: activeScope.value.event_id,
      });
      if (cancelled) return;
      setLoading(false);
      if (res.ok && res.data) {
        setItems(flattenLibraryResponse(res.data));
        setError(null);
      } else {
        setError(res.error ?? 'unknown error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  const onDelete = async (item: LibItem) => {
    const k = item.key ?? item.abs_path;
    if (!k) return;
    const confirmed = window.confirm(`Delete "${displayName(item)}" from the library?`);
    if (!confirmed) return;
    const result = await pathappPatch(activeScope.value, 'cr_library_delete', {
      key: k,
      abs_path: item.abs_path ?? '',
    });
    if (result.ok) {
      pushToast({ kind: 'success', message: `Deleted ${displayName(item)}`, source: 'library-delete' });
      setRefreshTick((n) => n + 1);
    } else {
      pushToast({
        kind: 'error',
        message: `Delete failed: ${result.error ?? `HTTP ${result.status}`}`,
        source: 'library-delete-error',
      });
    }
  };

  return (
    <aside class="mn-library-panel" data-testid="library-panel">
      <header class="mn-library-header">
        <h3>Library</h3>
        <span class="mn-dim mn-library-count" data-testid="library-count">
          {loading ? '…' : `${items.length} items`}
        </span>
      </header>

      <div class="mn-library-body">
        {loading ? (
          <p class="mn-loading" data-testid="library-loading">
            Loading library&hellip;
          </p>
        ) : error ? (
          <div class="mn-empty" data-testid="library-error">
            <p class="mn-warn">Could not reach /api/cr/library.</p>
            <p class="mn-dim">{error}</p>
          </div>
        ) : items.length === 0 ? (
          <p class="mn-empty" data-testid="library-empty">
            Library is empty for this event.
          </p>
        ) : (
          <ul class="mn-library-list" data-testid="library-list">
            {items.map((it, i) => {
              const libKey = it.key ?? it.abs_path ?? `item-${i}`;
              const dragPayload: DragPayload = {
                kind: 'lib-image',
                lib_key: libKey,
                tier: it.tier ?? 'unknown',
                ...(it.abs_path ? { abs_path: it.abs_path } : {}),
              };
              const dimsLabel = it.width && it.height ? `${it.width}×${it.height}` : undefined;
              const tileProps: {
                libKey: string;
                name: string;
                testIdSuffix: number;
                dragPayload: DragPayload;
                onDelete: () => Promise<void>;
                thumbSrc?: string;
                tier?: string;
                dimsLabel?: string;
              } = {
                libKey,
                name: displayName(it),
                testIdSuffix: i,
                dragPayload,
                onDelete: () => onDelete(it),
              };
              const ts = thumbSrc(it);
              if (ts !== undefined) tileProps.thumbSrc = ts;
              if (it.tier !== undefined) tileProps.tier = it.tier;
              if (dimsLabel !== undefined) tileProps.dimsLabel = dimsLabel;
              return <AssetTile key={libKey} {...tileProps} />;
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
