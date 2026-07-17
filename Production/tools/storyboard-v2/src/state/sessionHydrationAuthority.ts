// PSL_STALE_KEY_HYDRATION_GUARD_V1 — single authority for "may this completed
// session payload hydrate the global UI signals?".
//
// Invariant: a completed session fetch may write into the shared UI signals
// ONLY when its cache key still equals the key the live scope signals expect
// at completion time. Stale completions update their own cache row silently.
//
// Bug class closed (Event_5, 2026-07-17): page boots on ?video=intro, the
// coordinator fetches the intro partition; VideoSelector adopts the server's
// persisted active_video=resolution and a second fetch starts. The INTRO
// response lands LAST and last-writer-wins hydration clobbers bgBeats — the
// header dropdown + authority badge say "resolution" while the beat list shows
// bg_arc1_event5_pre_beat_*. Same class applies to any in-flight fetch that
// completes after the operator switches video role, event, or project type
// (map / storyboard / stitch job stores).
//
// Spec: Production/docs/TECH_SPEC_PSL_STALE_KEY_HYDRATION_GUARD_V1.md
// Tests: src/state/__tests__/sessionHydrationStaleKey.test.ts
// Deploy gate: Production/scripts/verify_psl_stale_key_hydration_durability.sh

import {
  activeMilestoneId,
  activeProjectType,
  activeScope,
  effectiveScopeVideoRole,
} from './scope';
import {
  bgSessionKey,
  mapSessionKey,
  stitchJobSessionKey,
  storyboardSessionKey,
} from './producerSessionKeys';

export const PSL_STALE_KEY_HYDRATION_GUARD_V1 = 'PSL_STALE_KEY_HYDRATION_GUARD_V1';

/** True when a payload fetched for `completedKey` may hydrate global signals now. */
export function sessionPayloadMayHydrate(
  completedKey: string,
  expectedKeyNow: string,
): boolean {
  return completedKey === expectedKeyNow;
}

/** Beat Gen partition key the UI expects right now (event + video role). */
export function expectedBgSessionKeyNow(): string {
  return bgSessionKey(activeScope.value.event_id, effectiveScopeVideoRole());
}

/** Production Map key the UI expects right now. */
export function expectedMapSessionKeyNow(): string {
  return mapSessionKey(activeScope.value.event_id);
}

/** Storyboard event-state key the UI expects right now. */
export function expectedStoryboardSessionKeyNow(): string {
  return storyboardSessionKey(
    activeScope.value.event_id,
    activeProjectType.value,
    activeMilestoneId.value,
  );
}

/** Stitch job key the UI expects right now. */
export function expectedStitchJobSessionKeyNow(): string {
  return stitchJobSessionKey(
    activeScope.value.event_id,
    activeProjectType.value,
    activeMilestoneId.value,
  );
}
