// TECH_SPEC_PATHAPP_SCOPE_EVENT_ID_ONLY_V1 — payload contract unit tests.
// Run: cd Production/tools/storyboard-v2 && node --experimental-strip-types --test src/api/__tests__/pathappPayload.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { buildPathappMutationPayload } from '../pathappPayload.ts';
import { makeScope } from '../../state/scope.ts';

const scope = makeScope('Event_4', null, 0);

describe('buildPathappMutationPayload — scope_event_id only', () => {
  it('event_create preserves body.event_id (new event) and injects scope_event_id (pin)', () => {
    const payload = buildPathappMutationPayload(
      scope,
      'event_create',
      { event_id: 'Event_3', event_label: 'Ember arrival' },
      { scopeVideoRole: 'intro', injectMilestoneScope: false, milestoneId: null },
    );
    assert.equal(payload.event_id, 'Event_3');
    assert.equal(payload.scope_event_id, 'Event_4');
    assert.equal(payload.scope_video_role, 'intro');
  });

  it('event_provision_server preserves target event_id', () => {
    const payload = buildPathappMutationPayload(
      scope,
      'event_provision_server',
      { event_id: 'Event_3' },
      { scopeVideoRole: 'intro', injectMilestoneScope: false, milestoneId: null },
    );
    assert.equal(payload.event_id, 'Event_3');
    assert.equal(payload.scope_event_id, 'Event_4');
  });

  it('beat_update_text does not auto-inject event_id', () => {
    const payload = buildPathappMutationPayload(
      scope,
      'beat_update_text',
      { beat_id: 'beat_01', text: 'hello' },
      { scopeVideoRole: 'intro', injectMilestoneScope: false, milestoneId: null },
    );
    assert.equal(payload.event_id, undefined);
    assert.equal(payload.scope_event_id, 'Event_4');
  });

  it('bg_update_beat does not clobber segment event_id when caller supplies it', () => {
    const payload = buildPathappMutationPayload(
      scope,
      'bg_update_beat',
      { event_id: '3', beat_id: 'beat_01' },
      { scopeVideoRole: 'intro', injectMilestoneScope: false, milestoneId: null },
    );
    assert.equal(payload.event_id, '3');
    assert.equal(payload.scope_event_id, 'Event_4');
  });
});
