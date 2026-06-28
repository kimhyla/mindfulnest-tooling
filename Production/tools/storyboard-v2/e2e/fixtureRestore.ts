// Restore Event_e2e_fixture from .pristine/ between Playwright tests.
// global-setup.ts runs once per session; mutating specs (s5_5ce R1.2, scope_router)
// must reset disk + server pin so downstream tests see fixture invariants.

import { copyFileSync, existsSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { APIRequestContext } from '@playwright/test';
import { SERVER } from './testServer';

const __dirname_restore = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname_restore, '..', '..', '..', '..');
const fixtureDir = resolve(repoRoot, 'Production', 'Event_e2e_fixture');
const pristineDir = resolve(fixtureDir, '.pristine');

export const FIXTURE_EVENT_ID = 'Event_e2e_fixture';

/** Copy mutation-prone fixture files from .pristine/ (matches global-setup.ts). */
export function restoreE2eFixtureFilesFromPristine(): void {
  if (!existsSync(pristineDir)) {
    throw new Error(`[fixture-restore] missing pristine dir: ${pristineDir}`);
  }
  for (const fname of readdirSync(pristineDir)) {
    if (fname.startsWith('.')) continue;
    if (fname === 'storyboard_v59_prod.html') continue;
    copyFileSync(resolve(pristineDir, fname), resolve(fixtureDir, fname));
  }
}

/** Disk restore; optional server reload (use afterAll — not afterEach — to avoid lock storms). */
export async function restoreE2eFixtureOnServer(
  request: APIRequestContext,
  server = SERVER,
  opts?: { reload?: boolean },
): Promise<void> {
  restoreE2eFixtureFilesFromPristine();
  if (opts?.reload === false) return;
  const load = await request.post(`${server}/api/event/load`, {
    data: { event_id: FIXTURE_EVENT_ID },
    timeout: 30_000,
  });
  if (!load.ok()) {
    throw new Error(
      `[fixture-restore] event/load failed HTTP ${load.status()}: ${await load.text()}`,
    );
  }
}
