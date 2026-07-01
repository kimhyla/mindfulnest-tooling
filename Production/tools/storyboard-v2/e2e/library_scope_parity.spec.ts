/**
 * LIBRARY_SCOPE_ROOT_PARITY_V1 — milestone scope keys on library mutations.
 * Marker: LIBRARY-SCOPE-PARITY-1
 */
import { test, expect } from '@playwright/test';
import { SERVER } from './testServer';

test.describe('Library scope parity G5', () => {
  test('LIBRARY-SCOPE-PARITY-1 cr_library list accepts milestone scope query', async ({
    request,
  }) => {
    const res = await request.get(
      `${SERVER}/api/cr/library?scope_type=milestone&event_id=Event_e2e_fixture&arc=1&segment=event_2_pre`,
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.images)).toBeTruthy();
  });
});
