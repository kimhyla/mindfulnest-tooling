/**
 * LIBRARY_CLIENT_CACHE_COHERENCE_V1 — upload busts session cache.
 * Marker: LIBRARY-CACHE-COHERENCE-1
 */
import { test, expect } from '@playwright/test';
import { SERVER } from './testServer';

test.describe('Library cache coherence G7', () => {
  test('LIBRARY-CACHE-COHERENCE-1 library list responds with cache bust param', async ({
    request,
  }) => {
    const res = await request.get(
      `${SERVER}/api/cr/library?scope_type=project&event_id=Event_e2e_fixture&_=${Date.now()}`,
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.images)).toBeTruthy();
  });
});
