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
import { activeTab, serverRehydrateTick } from '../state/refreshSignals';
import { apiGet, pathappPatch } from '../api/client';
import { SERVER_BASE } from '../api/endpoints';
import { AssetTile } from './ui/AssetTile';
import { pushToast } from './ui/Toast';
import type { DragPayload } from '../utils/dragdrop';
import { openCropper } from '../state/cropper';
import {
  ELEMENT_SPEAKERS,
  libraryItemCanAddToElement,
} from '../utils/libraryElementPose';

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
  // LD-738 LIBRARY_MASTER_ASSET_VISIBILITY_FIX_V1
  is_master?: boolean;
  has_crop?: boolean;
  /** Audio items from stitch_editor/library (ms). */
  duration_ms?: number;
  /** Element pose tier / character_master — from cr_library. */
  speaker?: string;
  element_pose_contaminated?: boolean;
}

interface StitchLibraryAudioItem {
  filename: string;
  path: string;
  duration_ms: number;
  category: string;
  source_folder: string;
}

interface StitchLibraryResponse {
  ambient?: StitchLibraryAudioItem[];
  sfx?: StitchLibraryAudioItem[];
  transitions?: StitchLibraryAudioItem[];
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

/** Map GET /api/stitch_editor/library scan into LibItem rows for sfx/ambient/transitions tiers. */
export function stitchLibraryToLibItems(data: StitchLibraryResponse): LibItem[] {
  const out: LibItem[] = [];
  const push = (list: StitchLibraryAudioItem[] | undefined, category: string) => {
    for (const item of list ?? []) {
      const tags =
        category === 'ambient'
          ? ['ambient']
          : category === 'transitions'
            ? ['transition']
            : ['sfx'];
      out.push({
        key: item.filename,
        abs_path: item.path,
        filename: item.filename,
        display_name: item.filename,
        asset_type: category === 'ambient' ? 'audio' : category === 'sfx' ? 'sfx' : 'transition',
        tags,
        tier: category,
        duration_ms: item.duration_ms,
        mtime: 0,
      });
    }
  };
  push(data.ambient, 'ambient');
  push(data.sfx, 'sfx');
  push(data.transitions, 'transitions');
  return out;
}

const AUDIO_LIBRARY_TIERS = new Set<LibraryTier>(['ambient', 'sfx', 'transitions']);

/** Preview URL for sound_library audio rows (sfx / ambient / transitions). */
export function libraryAudioPreviewUrl(item: LibItem): string | undefined {
  const fname = item.filename ?? item.key;
  if (!fname) return undefined;
  const at = inferAssetType(item);
  const tags = item.tags ?? [];
  const isAudioRow =
    at === 'audio' ||
    at === 'sfx' ||
    at === 'transition' ||
    tags.includes('ambient') ||
    tags.includes('sfx') ||
    tags.includes('transition') ||
    AUDIO_LIBRARY_TIERS.has((item.tier ?? '') as LibraryTier);
  if (!isAudioRow) return undefined;
  return `/api/stitch_editor/audio_file/${encodeURIComponent(fname)}`;
}

function thumbSrc(it: LibItem): string | undefined {
  return it.thumb_b64 ?? it.thumb_url ?? undefined;
}

function displayName(it: LibItem): string {
  return it.display_name ?? it.filename ?? it.key ?? '(unnamed)';
}

/** LD-738 — display name with master crop-status suffix when applicable. */
function libraryTileLabel(it: LibItem): string {
  const base = displayName(it);
  if (it.is_master !== true) return base;
  return it.has_crop === true
    ? `${base} (master — crop exists)`
    : `${base} (uncropped — crop me first)`;
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
  if (it.tier === 'canonical') return 'canonical_image';
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
    return (
      at === 'image' ||
      at === 'still_delivery' ||
      at === 'still_master' ||
      at === 'beat_scene' ||
      at === 'canonical_image' ||
      it.tier === 'canonical'
    );
  },
  ambient: (it) => {
    const at = inferAssetType(it);
    const tags = it.tags ?? [];
    return at === 'audio' && tags.includes('ambient');
  },
  sfx: (it) => inferAssetType(it) === 'sfx' || inferAssetType(it) === 'transition',
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
    // Eviction: if a value persists that is no longer in LIBRARY_TIERS
    // (e.g. enum shrank, schema migrated), remove it so the next read
    // doesn't keep returning DEFAULT via fall-through. Best-effort.
    if (v !== null && v !== undefined) {
      try {
        window.localStorage.removeItem(LIBRARY_TIER_LS_KEY);
      } catch (e) {
        // Read-only storage / quota / disabled — surface the persistent
        // invalid value to the console so a stale tier doesn't get
        // silently re-loaded on every render forever (DS observability).
        // eslint-disable-next-line no-console
        console.warn('[LibraryPanel] Could not evict invalid tier value', { value: v, error: e });
      }
    }
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

// [INFERRED — verify — chosen for perceived responsiveness; no LD lock]
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

// [INFERRED — verify — chosen for perceived responsiveness; no LD lock]
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
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [elementSpeaker, setElementSpeaker] = useState<string>('Lorelai');
  const [elementAdding, setElementAdding] = useState(false);

  // CC-17 — tier state, persisted to localStorage
  const [tier, setTier] = useState<LibraryTier>(loadPersistedTier);

  // LD-682 STITCHER_LIBRARY_DEFAULT_SFX_TIER_V1 — when the Stitcher tab is
  // active, default the tier to 'sfx' (SFX drops are the dominant Library
  // interaction inside Stitcher). User can still flip manually; the
  // transient override is NOT persisted to localStorage so leaving Stitcher
  // restores their prior preference. Reactive on activeTab signal.
  useEffect(() => {
    if (activeTab.value === 'stitcher') {
      setTier((prev) => (prev === 'sfx' ? prev : 'sfx'));
    } else {
      // Restore localStorage-preferred tier when leaving Stitcher.
      setTier((prev) => {
        const preferred = loadPersistedTier();
        return prev === preferred ? prev : preferred;
      });
    }
  }, [activeTab.value]);

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
    if (!preview?.item) return;
    const sp = (preview.item.speaker ?? '').trim();
    if (sp && ELEMENT_SPEAKERS.includes(sp as typeof ELEMENT_SPEAKERS[number])) {
      setElementSpeaker(sp);
    }
  }, [preview?.item?.key, preview?.item?.abs_path]);

  const onAddLibraryItemToElement = async () => {
    if (!preview?.item?.abs_path || elementAdding) return;
    setElementAdding(true);
    const result = await pathappPatch<{
      ok: boolean;
      pose_rel?: string;
      element_id?: string;
    }>(activeScope.value, 'bg_add_element_pose', {
      speaker: elementSpeaker,
      abs_path: preview.item.abs_path,
    });
    setElementAdding(false);
    if (!result.ok) {
      pushToast({
        kind: 'error',
        message: result.error ?? 'Could not add pose to Element',
        source: 'library-add-element-error',
      });
      return;
    }
    pushToast({
      kind: 'success',
      message: `Registered on ${elementSpeaker} Element`
        + (result.data?.pose_rel ? ` (${result.data.pose_rel})` : ''),
      source: 'library-add-element',
    });
    setRefreshTick((n) => n + 1);
  };

  // mn:library-refresh — fired by CropperModal onSaved after a crop is saved.
  useEffect(() => {
    const onLibRefresh = () => setRefreshTick((n) => n + 1);
    window.addEventListener('mn:library-refresh', onLibRefresh);
    return () => window.removeEventListener('mn:library-refresh', onLibRefresh);
  }, []);

  // BUG-A real UX fix (Kim 2026-05-20): track which library tiles are
  // CURRENTLY assigned to any beat in the active video scope, so Kim can
  // see at a glance which crops are "in use" — distinguishing master vs
  // delivery of the same crop becomes trivial when only one of them is
  // highlighted. Set rebuilds from /api/v2/event/<id>/state's
  // image_overrides per video_role. Refresh whenever scope changes OR
  // assignment events fire elsewhere.
  const [inUseKeys, setInUseKeys] = useState<Set<string>>(new Set());
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await apiGet<{
        videos?: Record<string, { image_overrides?: Record<string, string> }>;
      }>('v2_event_state', { event_id: activeScope.value.event_id });
      if (cancelled || !res.ok || !res.data) return;
      const keys = new Set<string>();
      for (const partition of Object.values(res.data.videos ?? {})) {
        for (const v of Object.values(partition?.image_overrides ?? {})) {
          if (typeof v === 'string' && v) keys.add(v);
        }
      }
      setInUseKeys(keys);
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshTick, serverRehydrateTick.value, activeScope.value.event_id]);
  // Listen for assign-image refreshes from other parts of the app.
  useEffect(() => {
    const onAssign = () => setRefreshTick((n) => n + 1);
    window.addEventListener('mn:image-assigned', onAssign);
    return () => window.removeEventListener('mn:image-assigned', onAssign);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [crRes, stitchRes] = await Promise.all([
        apiGet<LibraryResponse>('cr_library', { event_id: activeScope.value.event_id }),
        apiGet<StitchLibraryResponse>('stitch_editor_library'),
      ]);
      if (cancelled) return;
      setLoading(false);
      const imageItems = crRes.ok && crRes.data ? flattenLibraryResponse(crRes.data) : [];
      const audioItems =
        stitchRes.ok && stitchRes.data ? stitchLibraryToLibItems(stitchRes.data) : [];
      if (!crRes.ok && !stitchRes.ok) {
        setError(crRes.error ?? stitchRes.error ?? 'unknown error');
        setItems([]);
        return;
      }
      setItems([...imageItems, ...audioItems]);
      setError(null);
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshTick, serverRehydrateTick.value, activeScope.value.event_id]);

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
      const resultData = result.data as Record<string, unknown> | undefined;
      const deleteErrCode = resultData?.['code'] as string | undefined;
      const assetIds = resultData?.['asset_ids'] as number[] | undefined;

      if (deleteErrCode === 'PROD_ASSETS_PROTECTED' && assetIds?.length) {
        // Registered in Directus — offer a second confirmation with explicit warning.
        const forceConfirmed = window.confirm(
          `"${displayName(item)}" is registered in Directus (prod_assets id=${assetIds.join(', ')}).\n\nDeregister from Directus AND permanently delete from disk?\n\nThis cannot be undone.`
        );
        if (!forceConfirmed) return;
        const forceResult = await pathappPatch(activeScope.value, 'cr_library_delete', {
          key: k,
          abs_path: item.abs_path ?? '',
          force: true,
        });
        if (forceResult.ok) {
          pushToast({ kind: 'success', message: `Deregistered + deleted ${displayName(item)}`, source: 'library-delete' });
          setRefreshTick((n) => n + 1);
        } else {
          const forceErrMsg = (forceResult.data as Record<string, unknown> | undefined)?.['error'] as string | undefined;
          pushToast({
            kind: 'error',
            message: `Force delete failed: ${forceErrMsg ?? forceResult.error ?? `HTTP ${forceResult.status}`}`,
            source: 'library-delete-error',
          });
        }
      } else {
        // Use server's error message if present; fall back to HTTP status string.
        const deleteErrMsg = resultData?.['error'] as string | undefined;
        pushToast({
          kind: 'error',
          message: `Delete failed: ${deleteErrMsg ?? result.error ?? `HTTP ${result.status}`}`,
          source: 'library-delete-error',
        });
      }
    }
  };

  const onTierChange = (next: LibraryTier) => {
    setTier(next);
    // LD-682: when inside Stitcher tab, tier flips are transient (don't
    // persist) so leaving Stitcher restores the user's preferred default.
    // Outside Stitcher, manual flips persist as the new default.
    if (activeTab.value !== 'stitcher') {
      persistTier(next);
    }
    // Unpin preview on tier change so the user sees fresh hits.
    setPreview(null);
  };

  const onUpload = async (e: Event) => {
    const files = (e.target as HTMLInputElement).files;
    if (!files || files.length === 0) return;
    setUploading(true);
    let added = 0;
    const audioTier = AUDIO_LIBRARY_TIERS.has(tier) ? tier : null;
    for (const file of Array.from(files)) {
      try {
        const dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        });
        const file_b64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl;
        const result = await pathappPatch(activeScope.value, 'cr_upload', {
          filename: file.name,
          ...(audioTier
            ? { file_b64, tier: audioTier }
            : { image_b64: file_b64, tier: 'source' }),
        });
        if (result.ok) {
          added++;
          pushToast({ kind: 'success', message: `Uploaded ${file.name}`, source: 'library-upload' });
        } else {
          pushToast({
            kind: 'error',
            message: `Upload failed: ${result.error ?? `HTTP ${result.status}`}`,
            source: 'library-upload-error',
          });
        }
      } catch (err) {
        pushToast({ kind: 'error', message: `Upload error: ${String(err)}`, source: 'library-upload-error' });
      }
    }
    setUploading(false);
    if (added > 0) setRefreshTick((n) => n + 1);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // CC-17 + CC-18 — combine tier filter + debounced search
  const filteredItems = useMemo(() => {
    const tierFilter = TIER_TO_FILTER_MAP[tier];
    return items.filter((it) => tierFilter(it) && matchesSearch(it, searchQuery));
  }, [items, tier, searchQuery]);

  const uploadAccept = AUDIO_LIBRARY_TIERS.has(tier)
    ? 'audio/mpeg,audio/wav,audio/mp4,.mp3,.wav,.m4a'
    : 'image/png,image/jpeg,image/webp';
  const uploadTitle = AUDIO_LIBRARY_TIERS.has(tier)
    ? `Upload ${tier} audio to sound_library/${tier}/`
    : 'Upload image to library';

  return (
    <aside class="mn-library-panel" data-testid="library-panel" data-library-audio-preview="LIBRARY_AUDIO_PREVIEW_V1">
      <header class="mn-library-header">
        <h3>Library</h3>
        <span class="mn-dim mn-library-count" data-testid="library-count">
          {loading ? '…' : `${filteredItems.length} / ${items.length} items`}
        </span>
        {/* CC-20 — upload always in header so narrow rails never clip "+ Add". */}
        <label
          class="mn-library-upload-btn"
          data-testid="library-upload-btn"
          aria-disabled={uploading ? 'true' : undefined}
          title={uploadTitle}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={uploadAccept}
            multiple
            hidden
            onChange={onUpload}
            data-testid="library-upload-input"
          />
          {uploading ? '…' : '+ Add'}
        </label>
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
          // Empty-state UI; non-image tiers will populate per LD-656
          // PHASED_DELIVERY_PRIMITIVE_HOOKS_S5_5C_V1 Phase D.
          <p class="mn-empty" data-testid="library-empty-tier">
            {searchQuery
              ? `No items match "${searchQuery}" in tier ${tier}.`
              : `No items in tier ${tier} yet.`}
          </p>
        ) : (
          <ul class="mn-library-list" data-testid="library-list">
            {filteredItems.map((it, i) => {
              const libKey = it.key ?? it.abs_path ?? `item-${i}`;
              // Wave 5 R2 (Q1 source-side completion): emit lib-sfx for SFX-tier
              // items so target-context-aware drop predicates (StitcherSlot SFX
              // strip) can accept them. Images, watercolors, transitions stay as
              // lib-image so existing image-slot drop targets continue working.
              // Built as discriminated-union variants (DragPayload requires
              // source_path on the lib-sfx variant).
              const isAudioDragTier =
                tier === 'sfx' || tier === 'ambient' || tier === 'transitions';
              const dragPayload: DragPayload = isAudioDragTier
                ? {
                    kind: 'lib-sfx',
                    lib_key: libKey,
                    tier: it.tier ?? 'unknown',
                    source_path: it.abs_path ?? libKey,
                  }
                : {
                    kind: 'lib-image',
                    lib_key: libKey,
                    tier: it.tier ?? 'unknown',
                    ...(it.abs_path ? { abs_path: it.abs_path } : {}),
                    ...(it.filename ? { filename: it.filename } : {}),
                  };
              const dimsLabel =
                it.duration_ms != null && it.duration_ms > 0
                  ? `${(it.duration_ms / 1000).toFixed(1)}s`
                  : it.width && it.height
                    ? `${it.width}×${it.height}`
                    : undefined;
              const isMaster = it.is_master === true;
              const tileTier = isMaster ? 'master' : 'delivery';
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
                name: libraryTileLabel(it),
                testIdSuffix: i,
                dragPayload,
                onDelete: () => onDelete(it),
                onClick: () => togglePin(it),
              };
              const ts = thumbSrc(it);
              if (ts !== undefined) tileProps.thumbSrc = ts;
              if (it.tier !== undefined) tileProps.tier = it.tier;
              if (dimsLabel !== undefined) tileProps.dimsLabel = dimsLabel;
              const cropSrc = it.abs_path
                ? `${SERVER_BASE}/api/cr/full?abs_path=${encodeURIComponent(it.abs_path)}`
                : it.gallery_b64
                  ? (it.gallery_b64.startsWith('data:') ? it.gallery_b64 : `data:image/webp;base64,${it.gallery_b64}`)
                  : it.thumb_b64
                    ? (it.thumb_b64.startsWith('data:') ? it.thumb_b64 : `data:image/webp;base64,${it.thumb_b64}`)
                    : (it.thumb_url ?? '');
              const inUse = inUseKeys.has(libKey);
              return (
                <div
                  key={libKey}
                  class={`mn-library-tile-wrap${inUse ? ' mn-library-tile-in-use' : ''}`}
                  data-testid={`library-tile-wrap-${i}`}
                  data-tile-tier={tileTier}
                  data-in-use={inUse ? 'true' : 'false'}
                  onMouseEnter={() => requestPreview(it)}
                  onMouseLeave={cancelPreviewRequest}
                >
                  <AssetTile {...tileProps}>
                    <span
                      class={`mn-badge ${isMaster ? 'mn-badge-master' : 'mn-badge-delivery'}`}
                      data-tile-tier={tileTier}
                    >
                      {isMaster ? 'MASTER' : 'DELIVERY'}
                    </span>
                    {inUse ? (
                      <span
                        class="mn-badge mn-badge-in-use"
                        title="This image is currently assigned to one or more beats in this video"
                        data-testid={`library-tile-in-use-${i}`}
                      >● IN USE</span>
                    ) : null}
                    {cropSrc ? (
                      <button
                        type="button"
                        class="mn-crop-btn"
                        title="Send to Cropper"
                        data-testid={`library-crop-btn-${i}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          openCropper({
                            source: cropSrc,
                            sourceLabel: it.display_name ?? it.filename ?? it.key ?? 'Library image',
                            targetBeatId: null,
                          });
                        }}
                      >
                        ✂
                      </button>
                    ) : null}
                  </AssetTile>
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
            const audioUrl = libraryAudioPreviewUrl(preview.item);
            const src = preview.item.gallery_b64 ?? thumbSrc(preview.item);
            if (audioUrl) {
              return (
                <audio
                  key={audioUrl}
                  class="mn-library-preview-audio"
                  data-testid="library-preview-audio"
                  data-audio-filename={preview.item.filename ?? preview.item.key}
                  src={audioUrl}
                  controls
                  autoPlay
                  preload="metadata"
                />
              );
            }
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
          {libraryItemCanAddToElement(preview.item) ? (
            <div class="mn-library-element-add" data-testid="library-add-element-row">
              <label class="mn-dim" for="library-element-speaker">Element speaker</label>
              <select
                id="library-element-speaker"
                class="mn-library-element-speaker"
                data-testid="library-element-speaker"
                value={elementSpeaker}
                onChange={(e) => setElementSpeaker((e.target as HTMLSelectElement).value)}
              >
                {ELEMENT_SPEAKERS.map((sp) => (
                  <option key={sp} value={sp}>{sp}</option>
                ))}
              </select>
              <button
                type="button"
                class="mn-btn mn-btn-small mn-library-element-add-btn"
                data-testid="library-add-element-btn"
                disabled={elementAdding}
                onClick={() => { void onAddLibraryItemToElement(); }}
              >
                {elementAdding ? 'Registering…' : 'Add to Element'}
              </button>
              <p class="mn-dim mn-library-element-add-hint">
                Registers this library still on the speaker&apos;s Kling Element — then drag it onto any beat char ref.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}
