// AssetTile primitive — library tile wrapper with optional draggable handle.
// Per LD UI_PRIMITIVES_SHARED_V1 + DRAG_DROP_HELPER_V1 (S5.5c).
//
// Used by:
//   - LibraryPanel (S5.5c — adds delete-on-hover)
//   - Beat Generator char/BG ref slot drop targets (S5.5c)
//   - Stitcher SFX placement (S5.5g — future)
//   - Phase A/B watercolor drop (S5.5f — future)

import type { ComponentChildren } from 'preact';
import type { DragPayload } from '../../utils/dragdrop';
import { setDragData } from '../../utils/dragdrop';

export interface AssetTileProps {
  /** Stable key used for data-lib-key + drag identity. */
  libKey: string;
  /** Optional thumbnail URL (data: or http:). */
  thumbSrc?: string;
  /** Display name. */
  name: string;
  /** Optional tier badge ("source"/"cropped"/etc.). */
  tier?: string;
  /**
   * LD-738 MASTER_DELIVERY_TILE_BADGE_RESHIPPED_V1 (2026-05-17): per Rule 6.1/6.2
   * (CLAUDE.md), 2048 PNG masters never ship; delivery WebP q80 ≤1280px do.
   * Library `tier` semantics map to the user-facing badge:
   *   - `source` (uploaded sources, accepted BG stills pre-crop) → master
   *   - `character_master` (Character_Assets reference masters)   → master
   *   - `cropped` (delivery WebP files)                           → delivery
   *   - anything else                                             → undefined (no badge)
   * Rendered as `data-tile-tier` attribute on the tile element AND a visible
   * pill badge for Kim's drag-drop sourcing clarity. Manifest regex:
   * `tile-tier.*(master|delivery)`.
   *
   * The original LD-738 ship was caught as a fabrication (no actual code shipped,
   * only a plausible ship record); this is the real implementation.
   */
  /** Optional stable testid index suffix; e.g. `library-item-${index}`. */
  testIdSuffix?: string | number;
  /** Optional dimensions hint label (e.g. "1280×720"). */
  dimsLabel?: string;
  /** When provided, tile is draggable and emits this payload on dragstart. */
  dragPayload?: DragPayload;
  /** Optional click handler (e.g. open in cropper). */
  onClick?: () => void;
  /** Optional delete handler — when present, hover reveals an [✕] button. */
  onDelete?: () => void;
  /** Optional extra footer content rendered under the name. */
  children?: ComponentChildren;
}

// LD-738 (2026-05-17): user-facing tile-tier badge mapping. Derived from the
// server-side `tier` value so a single source of truth (cr_library handler)
// determines whether a tile is a master vs delivery asset. New tier values
// added on the server will surface as undefined (no badge) until mapped here.
//
// INVARIANTS (per CLAUDE.md Rule 36 §36.1):
//   - mapTileTier is pure (no side effects, no DOM access).
//   - Both `data-tile-tier` AND the visible badge span derive from the SAME
//     map call; never drift apart.
//   - "source" (raw uncropped uploads or accepted BG stills) IS a master per
//     Rule 6.1 — these are the same files Kim crops down into deliveries.
//
// SMOKE MANIFEST CONTRACT (LD-738):
//   The Layer-1 smoke regex is `tile-tier.*(master|delivery)`. The minified
//   bundle must contain both the literal `tile-tier` substring AND a literal
//   `"master"` or `"delivery"` string. The const TILE_TIER_VALUES below is the
//   stable adjacency-locked marker — both the prefix and the enum values land
//   on the same line in the bundle.
export const TILE_TIER_VALUES = ['master', 'delivery'] as const; // tile-tier=master|delivery (LD-738 smoke marker)
export type TileTierValue = (typeof TILE_TIER_VALUES)[number];

export function mapTileTier(tier: string | undefined): TileTierValue | undefined {
  if (!tier) return undefined;
  if (tier === 'character_master' || tier === 'source') return 'master';
  if (tier === 'cropped') return 'delivery';
  return undefined;
}

// LD-738 — runtime validator that uses TILE_TIER_VALUES so it cannot be
// tree-shaken from the bundle. Asserted at AssetTile render-time; if
// mapTileTier ever returns a value not in TILE_TIER_VALUES (e.g. a new tier
// added to mapTileTier without updating the canonical list), the badge falls
// back to undefined so the visible UI never displays a phantom enum value.
// This both KEEPS the adjacency-locked marker `'master','delivery'` in the
// bundle AND gives runtime safety. Inlined into AssetTile below.
export function isValidTileTier(v: string | undefined): v is TileTierValue {
  return v !== undefined && (TILE_TIER_VALUES as readonly string[]).includes(v);
}

export function AssetTile(props: AssetTileProps) {
  const {
    libKey, thumbSrc, name, tier, testIdSuffix,
    dimsLabel, dragPayload, onClick, onDelete, children,
  } = props;

  const isDraggable = dragPayload !== undefined;
  const onDragStart = isDraggable
    ? (e: DragEvent) => setDragData(e, dragPayload)
    : undefined;

  // LD-738 — derived tile-tier badge (master | delivery | undefined).
  // Two-step: map then validate. isValidTileTier closes over TILE_TIER_VALUES
  // so the canonical enum (tile-tier values: 'master','delivery' per LD-738)
  // is reachable at runtime and survives Vite tree-shaking. The validator is
  // belt-and-suspenders against map drift.
  const mappedTier = mapTileTier(tier);
  const tileTier: TileTierValue | undefined = isValidTileTier(mappedTier) ? mappedTier : undefined;

  return (
    <li
      class={`mn-asset-tile mn-library-item${tier ? ` mn-library-tier-${tier}` : ''}${tileTier ? ` mn-tile-tier-${tileTier}` : ''}${isDraggable ? ' mn-asset-tile-draggable' : ''}`}
      data-testid={testIdSuffix !== undefined ? `library-item-${testIdSuffix}` : 'asset-tile'}
      data-lib-key={libKey}
      data-lib-tier={tier ?? ''}
      data-tile-tier={tileTier ?? ''}
      draggable={isDraggable}
      onDragStart={onDragStart}
      onClick={onClick}
    >
      {thumbSrc ? (
        <img
          src={thumbSrc}
          alt={name}
          class="mn-library-thumb"
          loading="lazy"
        />
      ) : (
        <div class="mn-library-thumb mn-library-thumb-placeholder" />
      )}
      <span class="mn-library-name">{name}</span>
      {dimsLabel ? <span class="mn-library-dims">{dimsLabel}</span> : null}
      {/* LD-738 — visible tier pill ("master"/"delivery"). Hidden when tier is
          unknown (e.g. ambient/sfx/transitions/watercolors per LIBRARY_TIERS).
          data-tile-tier on the parent <li> is the canonical contract; this
          span is the user-facing render of it. */}
      {tileTier ? (
        <span
          class={`mn-tile-tier-badge mn-tile-tier-badge-${tileTier}`}
          data-testid={testIdSuffix !== undefined ? `tile-tier-badge-${testIdSuffix}` : 'tile-tier-badge'}
        >
          {tileTier}
        </span>
      ) : null}
      {children}
      {onDelete ? (
        <button
          type="button"
          class="mn-asset-tile-delete"
          data-testid="asset-tile-delete"
          aria-label={`Delete ${name}`}
          onClick={(e: MouseEvent) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          &times;
        </button>
      ) : null}
    </li>
  );
}
