import { defineConfig, devices } from '@playwright/test';

// Path C Session 1 — minimal smoke. Session 2 expands to ~45 tests covering
// the wrap-chain regression cases extracted from patch_v52..v58 + Touchpoint A.
//
// proper-fix Phase 1 (2026-05-03): adds webServer config (spawns
// production_server.py against Event_e2e_fixture per spec §19 + §17),
// globalSetup/Teardown for fixture pinning, and `retries: 1` in CI per
// spec §16 flake governance.

// E2E fixture server uses port 5200 — outside dedicated 5111–5199 range so
// Event_e2e_fixture is not conflated with Event_1 port math and event/load works.
const E2E_SERVER_PORT = 5200;
const E2E_BASE_URL = `http://localhost:${E2E_SERVER_PORT}`;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  // Single worker — rollback.spec.ts flips the served storyboard mid-test;
  // parallel workers loading the page would see v58 mid-flip and fail.
  workers: 1,
  reporter: [['list']],
  // Spec §16 flake governance: 1 retry in CI for transient infra (network
  // blips, runner cold-start), 0 locally so Kim sees flake immediately.
  retries: process.env.CI ? 1 : 0,
  // Spec §17 fixture pinning — copy pristine over live state at start of
  // every run, remove library test PNG at exit. See e2e/global-{setup,teardown}.ts.
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',
  use: {
    baseURL: process.env.STORYBOARD_BASE_URL ?? E2E_BASE_URL,
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
  // Spec §19 + Phase 1.4 — production_server.py spawned against the
  // Event_e2e_fixture (NOT Event_1, which isn't in this tree). Path is
  // relative to playwright.config.ts location:
  //   Production/tools/storyboard-v2/playwright.config.ts
  //   ../../..                       → repo root (mindfulnest-tooling/)
  //   ../../../Production/tools/...  → tools dir
  //   ../../../Production/Event_e2e_fixture → fixture dir
  webServer: {
    command:
      'python3 ../../../Production/tools/production_server.py' +
      ' --event-dir ../../../Production/Event_e2e_fixture' +
      ' --storyboard storyboard_v59_prod.html' +
      ' --event-id Event_e2e_fixture' +
      ` --port ${E2E_SERVER_PORT}`,
    // Inherited MN_BEATGEN_DB_PATH (e.g. beatgen_event1.db from launchd) fails
    // assert_beatgen_db_path_matches_event — pin fixture shard explicitly.
    env: {
      MN_BEATGEN_DB_PATH: `${process.env.HOME}/.mindfulnest/state/beatgen_evente2efixture.db`,
    },
    url: `${E2E_BASE_URL}/api/health`,
    timeout: 30_000,
    // ALWAYS spawn fresh — never reuse, including locally. The spec's original
    // `!process.env.CI` would silently reuse Kim's local Event_1 dev server
    // (different fixture, wrong data), producing false-RED test failures.
    // Explicit kill-before-run is the documented friction:
    //   pkill -f 'production_server.py.*Event_1' || true
    //   npx playwright test
    // Tests then exit cleanly and Kim restarts her dev server.
    reuseExistingServer: false,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
