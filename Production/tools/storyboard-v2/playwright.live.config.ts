import { defineConfig, devices } from '@playwright/test';

const LIVE_BASE = process.env.STORYBOARD_BASE_URL ?? 'http://localhost:5111';

export default defineConfig({
  testDir: './e2e',
  testMatch: ['phase_e_hydrate_live.spec.ts'],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: LIVE_BASE,
    headless: true,
    trace: 'on-first-retry',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
