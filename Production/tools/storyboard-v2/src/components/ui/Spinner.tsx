// Spinner primitive — pure-CSS loading indicator.
// Per LD UI_PRIMITIVES_SHARED_V1 (S5.5c).

export interface SpinnerProps {
  /** Optional size: 'sm' (16px), 'md' (24px), 'lg' (40px). Default 'md'. */
  size?: 'sm' | 'md' | 'lg';
  /** Optional aria-label. Default 'Loading'. */
  label?: string;
  /** Optional inline-flex variant — sits next to text. */
  inline?: boolean;
}

export function Spinner({ size = 'md', label = 'Loading', inline = false }: SpinnerProps) {
  return (
    <span
      class={`mn-spinner mn-spinner-${size}${inline ? ' mn-spinner-inline' : ''}`}
      data-testid="spinner"
      role="status"
      aria-label={label}
    >
      <span class="mn-spinner-ring" />
    </span>
  );
}
