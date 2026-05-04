// Playwright global teardown — proper-fix Phase 1 §17 fixture pinning.
//
// Removes the test PNG seeded by global-setup.ts. The fixture's mutation-prone
// files (production_state.json, etc.) stay in place — they're gitignored, and
// the next run's globalSetup will overwrite them from .pristine/.

import { existsSync, unlinkSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname_teardown = dirname(__filename);

const repoRoot = resolve(__dirname_teardown, '..', '..', '..', '..');
const stillsSourcesDir = resolve(repoRoot, 'Production', 'beat_generator_stills', 'sources');
const TEST_PNG_NAME = 'e2e_fixture_test.png';
const testPngPath = resolve(stillsSourcesDir, TEST_PNG_NAME);

async function globalTeardown() {
  if (existsSync(testPngPath)) {
    unlinkSync(testPngPath);
    // eslint-disable-next-line no-console
    console.log(`[global-teardown] removed library test PNG at ${testPngPath}`);
  }
}

export default globalTeardown;
