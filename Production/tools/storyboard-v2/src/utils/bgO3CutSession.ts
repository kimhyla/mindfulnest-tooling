/** BG_O3_CUT_SESSION_V1 — overlay drag must survive poll hydration. */

export const BG_O3_CUT_SESSION_V1 = 'BG_O3_CUT_SESSION_V1';

const activeDrags = new Set<string>();

export function bgO3CutSessionKey(beatId: string, optionIndex: number): string {
  return `${beatId}|${optionIndex}`;
}

export function markBgO3CutDragActive(beatId: string, optionIndex: number): void {
  activeDrags.add(bgO3CutSessionKey(beatId, optionIndex));
}

export function clearBgO3CutDragActive(beatId: string, optionIndex: number): void {
  activeDrags.delete(bgO3CutSessionKey(beatId, optionIndex));
}

export function isBgO3CutDragActive(beatId: string, optionIndex: number): boolean {
  return activeDrags.has(bgO3CutSessionKey(beatId, optionIndex));
}

export function shouldPreserveBgO3CutDraft(
  beatId: string,
  optionIndex: number,
  hasLocalDraft: boolean,
): boolean {
  return hasLocalDraft || isBgO3CutDragActive(beatId, optionIndex);
}
