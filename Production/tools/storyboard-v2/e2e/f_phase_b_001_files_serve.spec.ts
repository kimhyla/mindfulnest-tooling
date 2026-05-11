// F-PHASE-B-001 (prod_blockers id=121) — /files must resolve repo-relative
// Production/<Event>/… paths (webServer cwd is storyboard-v2, not repo root).

import { test, expect } from '@playwright/test';

test.describe('F-PHASE-B-001 — /files path resolution (id=121)', () => {
  test('F121.1 — GET /files?path=Production/Event_e2e_fixture/production_state.json returns 200', async ({
    request,
  }) => {
    const rel = 'Production/Event_e2e_fixture/production_state.json';
    const res = await request.get(
      `http://localhost:5111/files?path=${encodeURIComponent(rel)}`,
    );
    expect(res.status(), await res.text()).toBe(200);
  });
});
