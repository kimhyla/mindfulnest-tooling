// Tooltip primitive — hover + focus tooltip wrapper.
// Per LD UI_PRIMITIVES_SHARED_V1 (S5.5c).
//
// Native <title>/aria-label is NOT enough for richer descriptive text in the
// Beat Generator + Storyboard button rows. Tooltip wraps any child and
// renders a small popover on hover/focus.

import type { ComponentChildren } from 'preact';
import { useState } from 'preact/hooks';

export interface TooltipProps {
  /** Content rendered inside the tooltip popover. */
  text: string;
  /** Element being annotated. */
  children: ComponentChildren;
  /** Optional placement: 'top' (default) | 'bottom' | 'left' | 'right'. */
  placement?: 'top' | 'bottom' | 'left' | 'right';
}

export function Tooltip({ text, children, placement = 'top' }: TooltipProps) {
  const [open, setOpen] = useState(false);
  return (
    <span
      class="mn-tooltip-wrap"
      data-testid="tooltip-wrap"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open ? (
        <span
          class={`mn-tooltip mn-tooltip-${placement}`}
          data-testid="tooltip-popover"
          role="tooltip"
        >
          {text}
        </span>
      ) : null}
    </span>
  );
}
