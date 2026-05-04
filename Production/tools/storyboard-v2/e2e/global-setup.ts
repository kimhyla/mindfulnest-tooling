// Playwright global setup — proper-fix Phase 1 §17 fixture pinning.
//
// Runs once before all tests. Restores `Production/Event_e2e_fixture/`
// to its pristine seed state, then seeds a single test PNG into the
// project-level `Production/beat_generator_stills/sources/` directory
// for library tests (R2, R5). Pairs with global-teardown.ts which
// removes the test PNG at exit.

import { existsSync, mkdirSync, copyFileSync, writeFileSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// ESM-safe __dirname equivalent (package.json declares "type": "module").
const __filename = fileURLToPath(import.meta.url);
const __dirname_setup = dirname(__filename);

// Resolve repo root from this file: e2e/global-setup.ts → ../../../.. (repo root)
const repoRoot = resolve(__dirname_setup, '..', '..', '..', '..');
const fixtureDir = resolve(repoRoot, 'Production', 'Event_e2e_fixture');
const pristineDir = resolve(fixtureDir, '.pristine');
const stillsDir = resolve(repoRoot, 'Production', 'beat_generator_stills');
const stillsSourcesDir = resolve(stillsDir, 'sources');
const TEST_PNG_NAME = 'e2e_fixture_test.png';
const testPngPath = resolve(stillsSourcesDir, TEST_PNG_NAME);

// 1×1 transparent PNG, ~70 bytes — placeholder image for library tests
const TINY_PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';

async function globalSetup() {
  // Refuse to run if fixture is missing — better to fail loud than silently use real data
  if (!existsSync(pristineDir)) {
    throw new Error(
      `[global-setup] FATAL: pristine fixture missing at ${pristineDir}. ` +
      'Did you check out the proper-fix branch? See Production/Event_e2e_fixture/README.md.'
    );
  }

  // Restore mutation-prone files from pristine.
  // NOTE: skip storyboard_v59_prod.html — it's overwritten with the BUILT
  // v59 dist below, so .pristine's placeholder would shadow the real bundle.
  for (const fname of readdirSync(pristineDir)) {
    if (fname.startsWith('.')) continue;
    if (fname === 'storyboard_v59_prod.html') continue;
    const src = resolve(pristineDir, fname);
    const dst = resolve(fixtureDir, fname);
    copyFileSync(src, dst);
  }

  // Copy the freshly-built v59 app over the storyboard placeholder.
  // production_server.py serves --storyboard at `/`, so this MUST be the
  // built dist/index.html (single-file bundle ~120 kB) for the tests'
  // page.goto('/') to render the app. Workflow runs `npm run build` before
  // Playwright, so dist exists by the time globalSetup fires.
  const builtBundle = resolve(__dirname_setup, '..', 'dist', 'index.html');
  if (!existsSync(builtBundle)) {
    throw new Error(
      `[global-setup] FATAL: built v59 bundle missing at ${builtBundle}. ` +
      'Run `npm run build` before `npx playwright test`. CI handles this in playwright_e2e.yml.'
    );
  }
  copyFileSync(builtBundle, resolve(fixtureDir, 'storyboard_v59_prod.html'));

  // Seed library test PNG (BG_STILLS_DIR is project-level not event-scoped)
  if (!existsSync(stillsSourcesDir)) {
    mkdirSync(stillsSourcesDir, { recursive: true });
  }
  writeFileSync(testPngPath, Buffer.from(TINY_PNG_B64, 'base64'));

  // Eslint-disable to avoid CI noise; this is intentional console output
  // eslint-disable-next-line no-console
  console.log(
    `[global-setup] fixture restored at ${fixtureDir}; library seeded at ${testPngPath}`
  );
}

export default globalSetup;
