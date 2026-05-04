// HTML5 dataTransfer wrapper with strict typed payloads.
// Per LD DRAG_DROP_HELPER_V1 (S5.5c).
//
// Why this exists: HTML5 drag-and-drop's dataTransfer is stringly-typed and
// has cross-browser quirks (Safari requires a 'text/*' MIME; Firefox needs
// at least one setData call to even FIRE dragstart). This helper:
//   1. Locks payload shape via a discriminated union (compile-time)
//   2. Always uses MIME 'application/x-mn-drag' + 'text/plain' fallback
//   3. Returns null cleanly on cross-window drags / unrelated drops

export type DragPayload =
  // S5.5c+e proper-fix R2: filename added so drop handlers can build the
  // server-accurate bg_accept_lib_image body {beat_id, key, filename,
  // abs_path, slot_index} without a separate library lookup.
  | { kind: 'lib-image'; lib_key: string; tier: string; abs_path?: string; filename?: string }
  | { kind: 'lib-watercolor'; lib_key: string; animation_type: string }
  | { kind: 'lib-sfx'; lib_key: string; source_path: string; tier: string }
  | { kind: 'beat'; beat_id: string };

const MN_MIME = 'application/x-mn-drag';

export function setDragData(e: DragEvent, payload: DragPayload): void {
  if (!e.dataTransfer) return;
  const json = JSON.stringify(payload);
  // Set both — Safari requires 'text/plain' at minimum; Chrome/Firefox honor
  // the custom MIME.
  e.dataTransfer.setData(MN_MIME, json);
  e.dataTransfer.setData('text/plain', json);
  e.dataTransfer.effectAllowed = 'copy';
}

export function getDragData(e: DragEvent): DragPayload | null {
  if (!e.dataTransfer) return null;
  let raw = e.dataTransfer.getData(MN_MIME);
  if (!raw) raw = e.dataTransfer.getData('text/plain');
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as DragPayload;
    if (typeof parsed === 'object' && parsed !== null && 'kind' in parsed) {
      // shallow runtime guard — string check on kind tag
      const kind = (parsed as { kind: unknown }).kind;
      if (
        kind === 'lib-image' ||
        kind === 'lib-watercolor' ||
        kind === 'lib-sfx' ||
        kind === 'beat'
      ) {
        return parsed;
      }
    }
  } catch {
    // fall through
  }
  return null;
}

/**
 * Make a drop target — call ondragover.preventDefault and forward the parsed
 * payload to onDrop. Returns the props bag the component should spread.
 *
 * S5.5c+e proper-fix R2.4: also toggles `is-drag-over` class on the target
 * element so CSS can show a visual cue. Class name matches spec §4.1 R2.
 */
export interface DropTargetHandlers {
  onDragOver: (e: DragEvent) => void;
  onDragLeave: (e: DragEvent) => void;
  onDrop: (e: DragEvent) => void;
}

const DRAG_OVER_CLASS = 'is-drag-over';

export function makeDropTarget(
  onDrop: (payload: DragPayload, event: DragEvent) => void,
  filter?: (payload: DragPayload) => boolean,
): DropTargetHandlers {
  return {
    onDragOver: (e: DragEvent) => {
      // Allow drop only if the payload kind passes the filter.
      // We can't peek at the data on dragover (security restriction); the best
      // we can do is preventDefault to enable drop and validate on drop.
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
      const el = e.currentTarget as Element | null;
      if (el && !el.classList.contains(DRAG_OVER_CLASS)) {
        el.classList.add(DRAG_OVER_CLASS);
      }
    },
    onDragLeave: (e: DragEvent) => {
      // Don't toggle off if we're moving to a child element (relatedTarget is
      // inside currentTarget). HTML5 dragleave fires on every element transition.
      const el = e.currentTarget as Element | null;
      const related = e.relatedTarget as Node | null;
      if (el && related && el.contains(related)) return;
      el?.classList.remove(DRAG_OVER_CLASS);
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      const el = e.currentTarget as Element | null;
      el?.classList.remove(DRAG_OVER_CLASS);
      const payload = getDragData(e);
      if (!payload) return;
      if (filter && !filter(payload)) return;
      onDrop(payload, e);
    },
  };
}
