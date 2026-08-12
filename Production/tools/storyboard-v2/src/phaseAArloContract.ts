/** Phase A Arlo base clip — mirrors phase_a_arlo_contract.py */
export const PHASE_A_ARLO_BASE_CLIP_CANONICAL = 'arlo_idle_kim_gate0_headshot_v1';
export const PHASE_A_ARLO_AVATAR_STILL_LABEL =
  'Arlo Gate0 headshot idle (locked Speak asset)';

const DEPRECATED_EXACT = new Set([
  'arlo_idle_wizard_desk_v1',
  'arlo_idle_wizard_desk_v2',
  'arlo_idle_wizard_desk_v3',
  'arlo_idle_wizard_desk_v4',
  'arlo_idle_wizard_desk_v5',
  'arlo_idle_wizard_desk_v6',
  'arlo_idle_wizard_desk_v7',
  'arlo_idle_wizard_desk_v8',
  'chipper_idle_closeup_v1',
  'chipper_idle_closeup_v2',
]);

const DEPRECATED_PREFIXES = [
  'chipper_idle_',
  'placeholder_arlo_',
  'arlo_idle_wizard_desk_',
] as const;

export function phaseAArloBaseClipDeprecated(clipId: string | null | undefined): boolean {
  if (!clipId || !clipId.trim()) return true;
  const id = clipId.trim();
  if (id === PHASE_A_ARLO_BASE_CLIP_CANONICAL) return false;
  if (DEPRECATED_EXACT.has(id)) return true;
  return DEPRECATED_PREFIXES.some((p) => id.startsWith(p));
}

export function coercePhaseAArloBaseClipId(clipId: string | null | undefined): string {
  if (phaseAArloBaseClipDeprecated(clipId)) return PHASE_A_ARLO_BASE_CLIP_CANONICAL;
  return clipId!.trim();
}
