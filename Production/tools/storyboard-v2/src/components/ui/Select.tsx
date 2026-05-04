// Select primitive — wrapped <select> with consistent styling.
// Per LD UI_PRIMITIVES_SHARED_V1 (S5.5c).
//
// Supports flat option list AND grouped options (used by ProjectSelector to
// render Events / Milestones in the same dropdown per LD-467).

import type { ComponentChildren } from 'preact';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectOptionGroup {
  label: string;
  options: SelectOption[];
}

export interface SelectProps {
  /** Stable id used for label-for + data-testid. */
  id: string;
  /** Optional label rendered before the select. */
  label?: string;
  /** Either a flat list OR an array of groups. Mutually exclusive. */
  options?: SelectOption[];
  groups?: SelectOptionGroup[];
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  /** Optional placeholder shown when value is empty. */
  placeholder?: string;
  /** Extra slot rendered AFTER the select (e.g. the loading status text). */
  children?: ComponentChildren;
}

export function Select({
  id, label, options, groups, value, onChange, disabled, placeholder, children,
}: SelectProps) {
  return (
    <div class="mn-select-wrap" data-testid={`select-wrap-${id}`}>
      {label ? (
        <label class="mn-select-label" for={id}>{label}</label>
      ) : null}
      <select
        id={id}
        class="mn-select"
        data-testid={`select-${id}`}
        value={value}
        disabled={disabled === true}
        onChange={(e: Event) => {
          const t = e.target as HTMLSelectElement;
          onChange(t.value);
        }}
      >
        {placeholder !== undefined ? (
          <option value="">{placeholder}</option>
        ) : null}
        {options
          ? options.map((o) => (
              <option key={o.value} value={o.value} disabled={o.disabled === true}>
                {o.label}
              </option>
            ))
          : null}
        {groups
          ? groups.map((g) => (
              <optgroup key={g.label} label={g.label}>
                {g.options.map((o) => (
                  <option key={o.value} value={o.value} disabled={o.disabled === true}>
                    {o.label}
                  </option>
                ))}
              </optgroup>
            ))
          : null}
      </select>
      {children}
    </div>
  );
}
