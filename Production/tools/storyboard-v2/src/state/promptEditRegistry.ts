// PROMPT_EDIT_DURABILITY_V1 — prevents server refresh / O3 poll from clobbering
// in-progress textarea edits (Beat Gen prompt, beat-plan script, etc.).

export interface PromptEditState {
  text: string;
  dirty: boolean;
  focused: boolean;
  saveInFlight: boolean;
}

const edits = new Map<string, PromptEditState>();

export function getPromptEdit(beatId: string): PromptEditState | undefined {
  return edits.get(beatId);
}

export function isPromptEditProtected(beatId: string): boolean {
  const e = edits.get(beatId);
  if (!e) return false;
  return e.dirty || e.focused || e.saveInFlight;
}

export function syncPromptEdit(
  beatId: string,
  patch: Partial<PromptEditState> & { text?: string },
): void {
  const prev = edits.get(beatId) ?? {
    text: patch.text ?? '',
    dirty: false,
    focused: false,
    saveInFlight: false,
  };
  const next: PromptEditState = {
    text: patch.text ?? prev.text,
    dirty: patch.dirty ?? prev.dirty,
    focused: patch.focused ?? prev.focused,
    saveInFlight: patch.saveInFlight ?? prev.saveInFlight,
  };
  if (!next.dirty && !next.focused && !next.saveInFlight) {
    edits.delete(beatId);
    return;
  }
  edits.set(beatId, next);
}

export function clearPromptEdit(beatId: string): void {
  edits.delete(beatId);
}

/** Overlay protected in-flight edits onto beats[] from server refresh. */
export function applyPromptEditsToBeats<T extends { beat_id: string; kling_o3_prompt?: string; o3_prompt_box_law?: boolean }>(
  beats: T[],
): T[] {
  return beats.map((b) => {
    const e = edits.get(b.beat_id);
    if (!e || !isPromptEditProtected(b.beat_id)) return b;
    const text = e.text;
    return {
      ...b,
      kling_o3_prompt: text,
      o3_prompt_box_law: !!text.trim(),
    };
  });
}

/** Drop prompt fields from O3 poll patch when the user is editing that beat. */
export function stripProtectedPromptFromPatch<T extends {
  beat_id: string;
  kling_o3_prompt?: string;
  dialogue_text?: string;
  o3_prompt_box_law?: boolean;
}>(patch: T): T {
  if (!isPromptEditProtected(patch.beat_id)) return patch;
  const next = { ...patch };
  delete next.kling_o3_prompt;
  delete next.dialogue_text;
  delete next.o3_prompt_box_law;
  return next;
}

type RefImageField = 'reference_image' | 'bg_ref_image';
type RefLockField = 'reference_image_locked' | 'bg_ref_image_locked';

const REF_LOCK_PAIRS: ReadonlyArray<{ ref: RefImageField; lock: RefLockField }> = [
  { ref: 'reference_image', lock: 'reference_image_locked' },
  { ref: 'bg_ref_image', lock: 'bg_ref_image_locked' },
];

function refAbsPath(ref: { abs_path?: string } | null | undefined): string {
  return (ref?.abs_path ?? '').trim();
}

/** Keep operator-locked ref box paths when O3 poll snapshot is stale. */
export function preserveLockedRefsOnO3PollMerge<T extends {
  beat_id: string;
  reference_image?: { abs_path?: string } | null;
  bg_ref_image?: { abs_path?: string } | null;
  reference_image_locked?: boolean;
  bg_ref_image_locked?: boolean;
}>(current: T, patch: T): T {
  let merged: T = { ...current, ...patch };
  for (const { ref, lock } of REF_LOCK_PAIRS) {
    if (!current[lock]) continue;
    const localPath = refAbsPath(current[ref]);
    const patchPath = refAbsPath(patch[ref]);
    if (!localPath || !patchPath || localPath === patchPath) continue;
    merged = {
      ...merged,
      [ref]: current[ref],
      [lock]: true,
    };
  }
  return merged;
}
