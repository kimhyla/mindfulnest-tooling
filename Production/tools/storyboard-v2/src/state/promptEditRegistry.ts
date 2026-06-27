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

/** Unsaved in-flight prompt text for a beat (undefined when clean). */
export function readPromptEditText(beatId: string): string | undefined {
  const e = edits.get(beatId);
  if (!e || !isPromptEditProtected(beatId)) return undefined;
  return e.text;
}

export function hasUnsavedPromptEdit(beatId: string): boolean {
  return isPromptEditProtected(beatId);
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

/** O3 poll / session — always take server gallery authority on terminal done. */
export function applyO3GalleryFieldsFromPoll<T extends {
  beat_id: string;
  pipeline?: string | null;
  beat_render_mode?: string | null;
  kling_o3_options?: unknown;
  kling_o3_video_path?: string | null;
  kling_o3_selected_option_key?: string | null;
  kling_o3_generation?: number | null;
  kling_o3_status?: string | null;
  kling_o3_replace_slot_index?: number | null;
  kling_o3_video_path_exists?: boolean;
  job_busy?: boolean | null;
  kling_o3_voice_fix_status?: string | null;
  kling_o3_voice_fix_phase?: string | null;
  o3_current_job_id?: string | null;
  status?: string | null;
  _derived?: { option_slots?: unknown };
}>(local: T, patch: T): T {
  const merged = preserveLockedRefsOnO3PollMerge(local, patch);
  const gallery: Partial<T> = {};
  const keys = [
    'kling_o3_options',
    'kling_o3_video_path',
    'kling_o3_selected_option_key',
    'kling_o3_generation',
    'kling_o3_status',
    'kling_o3_replace_slot_index',
    'kling_o3_video_path_exists',
    'job_busy',
    'kling_o3_voice_fix_status',
    'kling_o3_voice_fix_phase',
    'o3_current_job_id',
    'status',
  ] as const;
  for (const key of keys) {
    if (patch[key] !== undefined) {
      (gallery as Record<string, unknown>)[key] = patch[key];
    }
  }
  if (patch._derived?.option_slots !== undefined) {
    gallery._derived = {
      ...(local._derived ?? {}),
      ...(patch._derived ?? {}),
      option_slots: patch._derived.option_slots,
    };
  }
  const stillInsert = local.pipeline === 'still_insert' || local.beat_render_mode === 'still_insert';
  if (stillInsert) {
    delete gallery.job_busy;
    delete gallery.o3_current_job_id;
    delete gallery.kling_o3_voice_fix_status;
    delete gallery.kling_o3_voice_fix_phase;
  }
  return { ...merged, ...gallery };
}

/** Session refresh + poll — preserve operator ref boxes from clobbering. */
export function preserveRefBoxesOnServerBeatMerge<T extends {
  beat_id: string;
  reference_image?: { abs_path?: string } | null;
  bg_ref_image?: { abs_path?: string } | null;
  reference_image_locked?: boolean;
  bg_ref_image_locked?: boolean;
}>(currentBeats: T[], serverBeats: T[]): T[] {
  const byId = new Map(currentBeats.map((b) => [b.beat_id, b]));
  return serverBeats.map((serverBeat) => {
    const local = byId.get(serverBeat.beat_id);
    if (!local) return serverBeat;
    return preserveLockedRefsOnO3PollMerge(local, serverBeat);
  });
}
