/** Phase B Cedric base clip — mirrors phase_b_cedric_contract.py */
export const PHASE_B_CEDRIC_BASE_CLIP_CANONICAL = 'cedric_idle_newstyle_v3';

const DEPRECATED_PREFIXES = [
  'cedric_idle_camera_',
  'cedric_idle_study_',
  'placeholder_cedric_',
] as const;

const DEPRECATED_EXACT = new Set([
  'cedric_idle_newstyle_v1',
  'cedric_idle_newstyle_v2',
]);

export function phaseBCedricBaseClipDeprecated(clipId: string | null | undefined): boolean {
  if (!clipId || !clipId.trim()) return true;
  const id = clipId.trim();
  if (DEPRECATED_EXACT.has(id)) return true;
  return DEPRECATED_PREFIXES.some((p) => id.startsWith(p));
}

export function coercePhaseBCedricBaseClipId(clipId: string | null | undefined): string {
  if (phaseBCedricBaseClipDeprecated(clipId)) return PHASE_B_CEDRIC_BASE_CLIP_CANONICAL;
  return clipId!.trim();
}
