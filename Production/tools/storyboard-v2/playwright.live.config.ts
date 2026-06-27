import { defineConfig, devices } from '@playwright/test';

/**
 * Live storyboard E2E — runs against dedicated Event_2 server (:5112).
 * No webServer spawn; no Event_e2e_fixture mutation.
 *
 * Usage:
 *   cd Production/tools/storyboard-v2
 *   npx playwright test --config playwright.live.config.ts
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: '*_live.spec.ts',
  timeout: 300_000,
  expect: { timeout: 180_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.STORYBOARD_LIVE_BASE_URL ?? 'http://localhost:5112',
    headless: true,
    trace: 'on-first-retry',
    actionTimeout: 15_000,
    navigationTimeout: 60_000,
  },
  projects: [
    {
      name: 'chromium-live',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
