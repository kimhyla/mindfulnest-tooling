import { defineConfig, devices } from '@playwright/test';

// Path C Session 1 — minimal smoke. Session 2 expands to ~45 tests covering
// the wrap-chain regression cases extracted from patch_v52..v58 + Touchpoint A.

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  // Single worker — rollback.spec.ts flips the served storyboard mid-test;
  // parallel workers loading the page would see v58 mid-flip and fail.
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.STORYBOARD_BASE_URL ?? 'http://localhost:5111',
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
});
