/**
 * mergeBeatsOnSessionHydrate — BG session refresh beat merge (OPERATOR_EDIT_AUTHORITY_V1).
 * Single entry for bg_session_state → row.beats hydration.
 */
import { preserveRefBoxesOnServerBeatMerge } from '../state/promptEditRegistry.ts';

export const BG_SESSION_BEAT_MERGE_V1 = 'BG_SESSION_BEAT_MERGE_V1';

export function mergeBeatsOnSessionHydrate<T extends {
  beat_id: string;
  reference_image?: { abs_path?: string; thumb_b64?: string; key?: string } | null;
  bg_ref_image?: { abs_path?: string; thumb_b64?: string; key?: string } | null;
  reference_image_locked?: boolean;
  bg_ref_image_locked?: boolean;
  _derived?: {
    char_ref_display?: { abs_path?: string; thumb_b64?: string; key?: string } | null;
    bg_ref_display?: { abs_path?: string; thumb_b64?: string; key?: string } | null;
    still_scene_display?: { abs_path?: string; thumb_b64?: string; key?: string } | null;
    option_slots?: unknown;
  };
}>(currentBeats: T[], serverBeats: T[]): T[] {
  return preserveRefBoxesOnServerBeatMerge(currentBeats, serverBeats);
}
