// BaseClipPicker — modal-with-list picker for Phase A 3-clip slots
// (fly-in / sitting / fly-out). Per LD PHASE_A_THREE_CLIP_HANDLING_V1
// (S5.5f spec §3.5).
//
// Filtered to a single character (`chipper` for Phase A; `cedric` for the
// future Phase B variant if Kim ever wants the same modal there). Caller
// passes an already-loaded list of base clips so the modal stays a pure
// view (no fetching).

import { Modal } from '../ui/Modal';

export interface BaseClipItem {
  id: string;
  filename: string;
  ext: string;
  character: string | null;
  duration_s: number | null;
}

export interface BaseClipPickerProps {
  open: boolean;
  /** "fly-in" | "sitting" | "fly-out" — purely a UI label, not used to filter. */
  positionLabel: string;
  character: string;
  clips: ReadonlyArray<BaseClipItem>;
  onPick: (clipId: string) => void;
  onClose: () => void;
}

export function BaseClipPicker({
  open,
  positionLabel,
  character,
  clips,
  onPick,
  onClose,
}: BaseClipPickerProps) {
  const filtered = clips.filter((c) => c.character === character);
  return (
    <Modal
      id="base-clip-picker"
      title={`Pick ${positionLabel} clip (${character})`}
      open={open}
      onClose={onClose}
      panelClass="mn-modal-wide"
    >
      {filtered.length === 0 ? (
        <p class="mn-dim">No {character} clips in the library.</p>
      ) : (
        <ul class="mn-base-clip-list" data-testid="base-clip-list">
          {filtered.map((c) => (
            <li
              key={c.id}
              class="mn-base-clip-row"
              data-testid={`base-clip-option-${c.id}`}
              onClick={() => onPick(c.id)}
            >
              <strong>{c.id}</strong>
              <span class="mn-dim">{c.filename}</span>
              <span class="mn-dim">{c.duration_s ?? '?'}s</span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
