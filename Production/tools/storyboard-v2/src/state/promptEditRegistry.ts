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
