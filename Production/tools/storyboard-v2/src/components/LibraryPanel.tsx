// LibraryPanel — Event-1 image library, mtime-sorted (LD-452 / Fix-V).
// Renders real data from GET /api/cr/library for the active event.
//
// Session 1 ships read-only display. Drag-to-slot, delete, and crop-from-lib
// are wired in Session 1.5+ via pathappPatch() through the single mutation
// channel.
//
// Server response shape (verified 2026-05-02 against production_server.py
// _handle_cr_library):
//   { "images": [
//       { key, filename, thumb_b64, gallery_b64, tier, abs_path }, ...
//     ] }
// Tier values currently in use: "source", "cropped".

import { useEffect, useState } from 'preact/hooks';
import { activeScope } from '../state/scope';
import { apiGet } from '../api/client';

interface LibItem {
  key?: string;
  abs_path?: string;
  filename?: string;
  /** Inlined base64 data URL — current production_server.py shape. */
  thumb_b64?: string;
  /** Larger inlined preview (used when dragged/expanded). */
  gallery_b64?: string;
  /** Legacy: separate-resource thumb URL (fallback if a future server returns this). */
  thumb_url?: string;
  /** Legacy: pretty name (fallback). */
  display_name?: string;
  mtime?: number;
  tier?: string;
  width?: number;
  height?: number;
}

interface LibraryResponse {
  /** Current shape: `{"images": [...]}`. */
  images?: LibItem[];
  /** Hypothetical alternate shapes — kept for forward-compatibility but never branch on these alone. */
  items?: LibItem[];
  sources?: LibItem[];
  crops?: LibItem[];
  masters?: LibItem[];
}

export function flattenLibraryResponse(r: LibraryResponse): LibItem[] {
  if (Array.isArray(r.images)) return r.images;
  if (Array.isArray(r.items)) return r.items;
  // Tiered fallback (never observed yet but cheap to support).
  return [...(r.sources ?? []), ...(r.crops ?? []), ...(r.masters ?? [])];
}

function thumbSrc(it: LibItem): string | null {
  return it.thumb_b64 ?? it.thumb_url ?? null;
}

function displayName(it: LibItem): string {
  return it.display_name ?? it.filename ?? it.key ?? '(unnamed)';
}

export function LibraryPanel() {
  const [items, setItems] = useState<LibItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
  }, []);

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
              const src = thumbSrc(it);
              return (
                <li
                  key={it.key ?? it.abs_path ?? i}
                  class={`mn-library-item${it.tier ? ` mn-library-tier-${it.tier}` : ''}`}
                  data-testid={`library-item-${i}`}
                  data-lib-key={it.key ?? it.abs_path ?? ''}
                  data-lib-tier={it.tier ?? ''}
                >
                  {src ? (
                    <img
                      src={src}
                      alt={displayName(it)}
                      class="mn-library-thumb"
                      loading="lazy"
                    />
                  ) : (
                    <div class="mn-library-thumb mn-library-thumb-placeholder" />
                  )}
                  <span class="mn-library-name">{displayName(it)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
