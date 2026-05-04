// Modal primitive — backdrop + close-on-Esc + content/header/footer slots.
// Per LD UI_PRIMITIVES_SHARED_V1 (S5.5c). Replaces the one-off CropperModal
// wrapper pattern.
//
// Single-modal stack invariant (Cursor v8 Q2): only one Modal may be open at
// any given time. Components opening a Modal inside another Modal must close
// the parent first OR re-use the modal-id slot. Enforced by data-testid +
// z-index ladder; no nested-stack management.

import type { ComponentChildren } from 'preact';
import { useEffect } from 'preact/hooks';

export interface ModalProps {
  /** Stable id used for data-testid + a11y. e.g. "cropper" → data-testid="modal-cropper". */
  id: string;
  /** Title rendered in <h2> in the header. */
  title: string;
  /** Body content. */
  children: ComponentChildren;
  /** Footer content (action buttons etc.). Optional. */
  footer?: ComponentChildren;
  /** Open flag. When false the Modal renders nothing. */
  open: boolean;
  /** Called on backdrop click, Esc key, or close-X click. */
  onClose: () => void;
  /** Optional extra class on the panel for sizing variants ("mn-modal-wide" etc). */
  panelClass?: string;
}

export function Modal({ id, title, children, footer, open, onClose, panelClass }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const titleId = `modal-title-${id}`;
  return (
    <div
      class="mn-modal mn-modal-backdrop"
      data-testid={`modal-${id}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={(e: MouseEvent) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div class={`mn-modal-panel${panelClass ? ' ' + panelClass : ''}`}>
        <header class="mn-modal-header">
          <h2 id={titleId} class="mn-modal-title">{title}</h2>
          <button
            type="button"
            class="mn-modal-close"
            data-testid={`modal-close-${id}`}
            aria-label="Close"
            onClick={onClose}
          >
            &times;
          </button>
        </header>
        <div class="mn-modal-body">{children}</div>
        {footer ? <footer class="mn-modal-footer">{footer}</footer> : null}
      </div>
    </div>
  );
}
