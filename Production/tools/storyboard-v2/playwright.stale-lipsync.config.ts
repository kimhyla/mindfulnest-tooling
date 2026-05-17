// Standalone Playwright config for stale_lipsync_ui_gate.spec.ts only.
//
// Why a separate config: the default playwright.config.ts boots
// production_server.py on port 5111 — but Kim's interactive dev session
// often holds 5111 for Event_1 work. This config spawns a tiny static
// file server on port 5599 (dist/index.html only) so the test run is
// completely independent of any live server, and the page.route() mocks
// in the spec fully control API behavior.
//
// Only used by the stale-lipsync UI gate spec. Other e2e tests continue
// to use playwright.config.ts unchanged.

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'stale_lipsync_ui_gate.spec.ts',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  retries: 0,
  use: {
    baseURL: 'http://localhost:5599',
    headless: true,
    trace: 'on-first-retry',
    actionTimeout: 5_000,
    navigationTimeout: 10_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // Tiny static-file server bound to ./dist (built by `npm run build`).
    // Also responds 200 OK to /api/health so Playwright's health probe
    // resolves before the spec starts.
    command: 'node ./scripts/stale-lipsync-test-server.mjs',
    url: 'http://localhost:5599/api/health',
    timeout: 15_000,
    reuseExistingServer: false,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
