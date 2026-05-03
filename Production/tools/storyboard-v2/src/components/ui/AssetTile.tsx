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

export function AssetTile(props: AssetTileProps) {
  const {
    libKey, thumbSrc, name, tier, testIdSuffix,
    dimsLabel, dragPayload, onClick, onDelete, children,
  } = props;

  const isDraggable = dragPayload !== undefined;
  const onDragStart = isDraggable
    ? (e: DragEvent) => setDragData(e, dragPayload)
    : undefined;

  return (
    <li
      class={`mn-asset-tile mn-library-item${tier ? ` mn-library-tier-${tier}` : ''}${isDraggable ? ' mn-asset-tile-draggable' : ''}`}
      data-testid={testIdSuffix !== undefined ? `library-item-${testIdSuffix}` : 'asset-tile'}
      data-lib-key={libKey}
      data-lib-tier={tier ?? ''}
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
