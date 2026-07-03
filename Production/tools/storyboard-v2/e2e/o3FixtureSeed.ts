/**
 * O3 hermetic fixture seed — Event_e2e_fixture disk + beatgen for G1/G2 e2e.
 */
import { execFileSync } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { APIRequestContext } from '@playwright/test';
import { FIXTURE_EVENT_ID, restoreE2eFixtureOnServer } from './fixtureRestore';
import { SERVER } from './testServer';

const __dirname_seed = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname_seed, '..', '..', '..', '..');

export const O3_FAILED_REDO_BEAT_ID = 'bg_arc1_event2_pre_beat_o3fr1';
export const O3_FAILED_REDO_JOB_ID = 'o3fr1-failed-g4';

export async function seedO3FailedRedoFixture(
  request: APIRequestContext,
  server = SERVER,
): Promise<void> {
  execFileSync('bash', [resolve(repoRoot, 'Production/scripts/seed_o3_failed_redo_fixture.sh')], {
    cwd: repoRoot,
    env: {
      ...process.env,
      O3_FIXTURE_BEAT_ID: O3_FAILED_REDO_BEAT_ID,
      O3_FIXTURE_JOB_ID: O3_FAILED_REDO_JOB_ID,
      MN_BEATGEN_DB_PATH:
        process.env.MN_BEATGEN_DB_PATH
        ?? `${process.env.HOME}/.mindfulnest/state/beatgen_evente2efixture.db`,
    },
    stdio: 'pipe',
  });
  await restoreE2eFixtureOnServer(request, server, { reload: true });
}

export { FIXTURE_EVENT_ID };
