/**
 * PSL coordinator — scope-driven session hydration (always mounted).
 */

import { useEffect } from 'preact/hooks';
import { effect } from '@preact/signals';
import {
  activeMilestoneId,
  activeProjectType,
  activeScope,
  effectiveScopeVideoRole,
} from '../state/scope';
import { serverRehydrateTick, stitcherRefreshTick } from '../state/refreshSignals';
import { scopeReady } from '../state/scopeReady';
import { ensureBgSession } from '../state/bgSessionStore';
import { ensureMapSession } from '../state/mapSessionStore';
import { ensureStoryboardSession } from '../state/storyboardSessionStore';
import { ensureStitchJobSession } from '../state/stitchJobSessionStore';
import { BgPollCoordinator } from './BgPollCoordinator';

export function ProducerSessionCoordinator() {
  useEffect(() => {
    const dispose = effect(() => {
      if (!scopeReady.value) return;
      const eventId = activeScope.value.event_id;
      const videoRole = effectiveScopeVideoRole();
      const projectType = activeProjectType.value;
      const milestoneId = activeMilestoneId.value;
      void ensureBgSession(eventId, videoRole);
      void ensureMapSession(eventId);
      void ensureStoryboardSession(eventId, projectType, milestoneId);
      void ensureStitchJobSession(eventId, { projectType, milestoneId });
    });
    return dispose;
  }, []);

  useEffect(() => {
    const dispose = effect(() => {
      const tick = serverRehydrateTick.value;
      if (tick <= 0) return;
      if (!scopeReady.value) return;
      const eventId = activeScope.value.event_id;
      const videoRole = effectiveScopeVideoRole();
      const projectType = activeProjectType.value;
      const milestoneId = activeMilestoneId.value;
      void ensureBgSession(eventId, videoRole, { force: true });
      void ensureMapSession(eventId, { force: true });
      void ensureStoryboardSession(eventId, projectType, milestoneId, { force: true });
      void ensureStitchJobSession(eventId, { force: true, projectType, milestoneId });
    });
    return dispose;
  }, []);

  useEffect(() => {
    const dispose = effect(() => {
      const tick = stitcherRefreshTick.value;
      if (tick <= 0) return;
      void ensureStitchJobSession(activeScope.value.event_id, {
        force: true,
        projectType: activeProjectType.value,
        milestoneId: activeMilestoneId.value,
      });
    });
    return dispose;
  }, []);

  return <BgPollCoordinator />;
}
