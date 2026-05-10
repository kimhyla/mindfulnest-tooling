// LibraryPanel — Event-1 image library, mtime-sorted (LD-452 / Fix-V).
// Renders real data from GET /api/cr/library for the active event.
//
// S5.5c — migrated to AssetTile primitive (LD UI_PRIMITIVES_SHARED_V1) with
// hover-delete wiring to /api/cr/library/delete via pathappPatch (single
// mutation channel, no raw fetch). Tiles are also draggable so future drop
// targets (Beat Generator slots, Stitcher SFX) can consume them via the
// dragdrop helper.
//
// S5.5c-pass2 — Library primitives per spec §4 Phase A:
//   - CC-17: tier filter dropdown (images/ambient/sfx/transitions/watercolors)
//            with client-side TIER_TO_FILTER_MAP per Kim BS3 lock 2026-05-06
//            (no schema change). Default = images. Persisted in localStorage.
//   - CC-18: search box with substring match on file_name + iteration_notes,
//            debounced 300ms, combined with tier filter.
//   - CC-19: hover preview after 500ms (image 320px max). Click sticky-pins.
//            Audio/video preview shells reserved for Phase D when those tiers
//            populate (current cr_library returns image-only). Per LD-656
//            PHASED_DELIVERY_PRIMITIVE_HOOKS_S5_5C_V1 — phased architecture,
//            not Rule 19 shortcut.

import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { activeScope } from '../state/scope';
import { apiGet, pathappPatch } from '../api/client';
import { AssetTile } from './ui/AssetTile';
import { pushToast } from './ui/Toast';
import type { DragPayload } from '../utils/dragdrop';

// ----------------------------------------------------------------
// Types
// ----------------------------------------------------------------

interface LibItem {
  key?: string;
  abs_path?: string;
  filename?: string;
  thumb_b64?: string;
  gallery_b64?: string;
  thumb_url?: string;
  display_name?: string;
  mtime?: number;
  tier?: string; // server-set: 'source' | 'cropped' | 'character_master' (cr_library current shape)
  width?: number;
  height?: number;
  // CC-17/18 — optional fields populated when prod_assets metadata is enriched
  // server-side (Phase D extension per LD-656). [INFERRED — verify] not
  // populated by current cr_library.
  asset_type?: string;
  tags?: string[];
  asset_name?: string;
  iteration_notes?: string;
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

// ----------------------------------------------------------------
// CC-17 — Library tier filter (Kim BS3 lock 2026-05-06)
// ----------------------------------------------------------------
// Mapping is client-side; no prod_assets schema change. Each tier resolves
// against the existing item.asset_type / item.tags / item.asset_name fields
// [INFERRED — verify] server populates from prod_assets where available;
// cr_library currently returns image-only items where asset_type is inferred
// from item.tier.
//
// [INFERRED — verify] LIBRARY_TIER_FILTER_V1 to capture the verbatim mapping
// rules — file when CC-17/18/19 land in main and the rules are confirmed
// against runtime cr_library behavior.

export type LibraryTier = 'images' | 'ambient' | 'sfx' | 'transitions' | 'watercolors';

const LIBRARY_TIERS: LibraryTier[] = ['images', 'ambient', 'sfx', 'transitions', 'watercolors'];
const DEFAULT_LIBRARY_TIER: LibraryTier = 'images';
const LIBRARY_TIER_LS_KEY = 'mn.library.tier';

// Map current cr_library `tier` value to a prod_assets-shaped asset_type so
// the TIER_TO_FILTER_MAP can decide. cr_library returns 'source' / 'cropped'
// / 'character_master' for image disk items today.
function inferAssetType(it: LibItem): string {
  if (it.asset_type) return it.asset_type;
  if (it.tier === 'character_master') return 'still_master';
  if (it.tier === 'source' || it.tier === 'cropped') return 'still_delivery';
  return 'image';
}

// Per Kim BS3 lock 2026-05-06:
//  images       → asset_type IN ('image','still_delivery','still_master','beat_scene')
//  ambient      → asset_type='audio' AND tags CONTAINS 'ambient'
//  sfx          → asset_type='sfx'
//  transitions  → tags CONTAINS 'transition'
//  watercolors  → tags CONTAINS 'watercolor' OR asset_name CONTAINS 'watercolor'
export const TIER_TO_FILTER_MAP: Record<LibraryTier, (it: LibItem) => boolean> = {
  images: (it) => {
    const at = inferAssetType(it);
    return at === 'image' || at === 'still_delivery' || at === 'still_master' || at === 'beat_scene';
  },
  ambient: (it) => {
    const at = inferAssetType(it);
    const tags = it.tags ?? [];
    return at === 'audio' && tags.includes('ambient');
  },
  sfx: (it) => inferAssetType(it) === 'sfx',
  transitions: (it) => (it.tags ?? []).includes('transition'),
  watercolors: (it) => {
    const tags = it.tags ?? [];
    if (tags.includes('watercolor')) return true;
    const name = (it.asset_name ?? it.filename ?? it.key ?? '').toLowerCase();
    return name.includes('watercolor');
  },
};

function loadPersistedTier(): LibraryTier {
  try {
    const v = window.localStorage.getItem(LIBRARY_TIER_LS_KEY);
    if (v && (LIBRARY_TIERS as string[]).includes(v)) return v as LibraryTier;
  } catch {
    /* localStorage may be unavailable in some test contexts */
  }
  return DEFAULT_LIBRARY_TIER;
}

function persistTier(t: LibraryTier): void {
  try {
    window.localStorage.setItem(LIBRARY_TIER_LS_KEY, t);
  } catch {
    /* swallow — persistence is best-effort */
  }
}

// ----------------------------------------------------------------
// CC-18 — Library search (debounced 300ms)
// ----------------------------------------------------------------

const SEARCH_DEBOUNCE_MS = 300;

function matchesSearch(it: LibItem, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  const haystack = [
    it.filename ?? '',
    it.display_name ?? '',
    it.key ?? '',
    it.asset_name ?? '',
    // [INFERRED — verify] iteration_notes only populated when server enriches
    // from prod_assets; included for future-proofing (Phase D extension per
    // LD-656).
    it.iteration_notes ?? '',
  ].join(' ').toLowerCase();
  return haystack.includes(needle);
}

// ----------------------------------------------------------------
// CC-19 — Hover preview (image 320px max). Audio/video preview shells
// reserved for Phase D when those tiers populate. Per LD-656
// PHASED_DELIVERY_PRIMITIVE_HOOKS_S5_5C_V1 — phased architecture,
// not Rule 19 shortcut.
// ----------------------------------------------------------------

const PREVIEW_HOVER_DELAY_MS = 500;

interface PreviewState {
  item: LibItem;
  pinned: boolean;
}

// ----------------------------------------------------------------
// LibraryPanel
// ----------------------------------------------------------------

export function LibraryPanel() {
  const [items, setItems] = useState<LibItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  // CC-17 — tier state, persisted to localStorage
  const [tier, setTier] = useState<LibraryTier>(loadPersistedTier);

  // CC-18 — search input (immediate) + debounced query (300ms)
  const [searchInput, setSearchInput] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  useEffect(() => {
    const t = window.setTimeout(() => setSearchQuery(searchInput), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  // CC-19 — hover preview state + 500ms debounce timer
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const previewTimerRef = useRef<number | null>(null);

  const requestPreview = (it: LibItem) => {
    if (preview && preview.pinned) return; // pinned blocks hover updates
    if (previewTimerRef.current !== null) {
      window.clearTimeout(previewTimerRef.current);
    }
    previewTimerRef.current = window.setTimeout(() => {
      setPreview({ item: it, pinned: false });
    }, PREVIEW_HOVER_DELAY_MS);
  };

  const cancelPreviewRequest = () => {
    if (previewTimerRef.current !== null) {
      window.clearTimeout(previewTimerRef.current);
      previewTimerRef.current = null;
    }
    setPreview((p) => (p && p.pinned ? p : null));
  };

  const togglePin = (it: LibItem) => {
    setPreview((p) => {
      if (p && p.pinned && p.item === it) {
        return null; // click-to-unpin
      }
      return { item: it, pinned: true };
    });
  };

  // Click outside the preview unpins it (CC-19 sticky-until-clicked-elsewhere).
  useEffect(() => {
    if (!preview || !preview.pinned) return;
    const onDocClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null;
      if (!t) return;
      if (t.closest('.mn-library-preview') || t.closest('.mn-library-list')) return;
      setPreview(null);
    };
    window.addEventListener('click', onDocClick);
    return () => window.removeEventListener('click', onDocClick);
  }, [preview]);

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

  const onTierChange = (next: LibraryTier) => {
    setTier(next);
    persistTier(next);
    // Unpin preview on tier change so the user sees fresh hits.
    setPreview(null);
  };

  // CC-17 + CC-18 — combine tier filter + debounced search
  const filteredItems = useMemo(() => {
    const tierFilter = TIER_TO_FILTER_MAP[tier];
    return items.filter((it) => tierFilter(it) && matchesSearch(it, searchQuery));
  }, [items, tier, searchQuery]);

  return (
    <aside class="mn-library-panel" data-testid="library-panel">
      <header class="mn-library-header">
        <h3>Library</h3>
        <span class="mn-dim mn-library-count" data-testid="library-count">
          {loading ? '…' : `${filteredItems.length} / ${items.length} items`}
        </span>
      </header>

      <div class="mn-library-controls" data-testid="library-controls">
        {/* CC-18 — search input, debounced 300ms */}
        <input
          type="search"
          class="mn-library-search"
          data-testid="library-search"
          placeholder="Search filename or notes…"
          value={searchInput}
          onInput={(e) => setSearchInput((e.target as HTMLInputElement).value)}
        />
        {/* CC-17 — tier filter dropdown */}
        <select
          class="mn-library-tier-select"
          data-testid="library-tier-select"
          value={tier}
          onChange={(e) => onTierChange((e.target as HTMLSelectElement).value as LibraryTier)}
          aria-label="Library tier filter"
        >
          {LIBRARY_TIERS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

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
        ) : filteredItems.length === 0 ? (
          {/* Empty-state UI; non-image tiers will populate per LD-656
              PHASED_DELIVERY_PRIMITIVE_HOOKS_S5_5C_V1 Phase D. */}
          <p class="mn-empty" data-testid="library-empty-tier">
            {searchQuery
              ? `No items match "${searchQuery}" in tier ${tier}.`
              : `No items in tier ${tier} yet.`}
          </p>
        ) : (
          <ul class="mn-library-list" data-testid="library-list">
            {filteredItems.map((it, i) => {
              const libKey = it.key ?? it.abs_path ?? `item-${i}`;
              const dragPayload: DragPayload = {
                kind: 'lib-image',
                lib_key: libKey,
                tier: it.tier ?? 'unknown',
                ...(it.abs_path ? { abs_path: it.abs_path } : {}),
                ...(it.filename ? { filename: it.filename } : {}),
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
                onClick?: () => void;
              } = {
                libKey,
                name: displayName(it),
                testIdSuffix: i,
                dragPayload,
                onDelete: () => onDelete(it),
                onClick: () => togglePin(it),
              };
              const ts = thumbSrc(it);
              if (ts !== undefined) tileProps.thumbSrc = ts;
              if (it.tier !== undefined) tileProps.tier = it.tier;
              if (dimsLabel !== undefined) tileProps.dimsLabel = dimsLabel;
              return (
                <div
                  key={libKey}
                  class="mn-library-tile-wrap"
                  data-testid={`library-tile-wrap-${i}`}
                  onMouseEnter={() => requestPreview(it)}
                  onMouseLeave={cancelPreviewRequest}
                >
                  <AssetTile {...tileProps} />
                </div>
              );
            })}
          </ul>
        )}
      </div>

      {/* CC-19 — Hover/sticky preview overlay. Image-only for Phase A;
          audio/video shell reserved for Phase D extension. Per LD-656
          PHASED_DELIVERY_PRIMITIVE_HOOKS_S5_5C_V1. */}
      {preview ? (
        <div
          class={`mn-library-preview${preview.pinned ? ' mn-library-preview-pinned' : ''}`}
          data-testid="library-preview"
          data-preview-pinned={preview.pinned ? 'true' : 'false'}
        >
          <header class="mn-library-preview-header">
            <span class="mn-library-preview-name">{displayName(preview.item)}</span>
            {preview.pinned ? (
              <button
                type="button"
                class="mn-library-preview-close"
                data-testid="library-preview-close"
                onClick={() => setPreview(null)}
                aria-label="Close preview"
              >
                ✕
              </button>
            ) : null}
          </header>
          {(() => {
            const at = inferAssetType(preview.item);
            const src = preview.item.gallery_b64 ?? thumbSrc(preview.item);
            if (at === 'audio' && src) {
              return (
                <audio
                  class="mn-library-preview-audio"
                  data-testid="library-preview-audio"
                  src={src}
                  controls
                />
              );
            }
            if (at === 'video' && src) {
              return (
                <video
                  class="mn-library-preview-video"
                  data-testid="library-preview-video"
                  src={src}
                  muted
                  playsInline
                  autoPlay
                  loop
                />
              );
            }
            return src ? (
              <img
                class="mn-library-preview-img"
                data-testid="library-preview-img"
                src={src}
                alt={displayName(preview.item)}
              />
            ) : (
              <p class="mn-dim mn-library-preview-empty">no preview</p>
            );
          })()}
          {preview.item.iteration_notes ? (
            <p class="mn-dim mn-library-preview-notes">{preview.item.iteration_notes}</p>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}
