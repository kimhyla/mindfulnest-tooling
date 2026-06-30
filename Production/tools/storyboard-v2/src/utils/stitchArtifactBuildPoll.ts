/** STITCH_ARTIFACT_ORCHESTRATOR_V1 — client poll after stitch_save_job queues tier builds. */

import { apiGet } from '../api/client.ts';

export const STITCH_ARTIFACT_ORCHESTRATOR_V1 = 'STITCH_ARTIFACT_ORCHESTRATOR_V1';

export type StitchArtifactBuildPoll = {
  build_id?: string;
  status?: string;
  phase?: string;
  error?: string;
  code?: string;
};

export async function pollStitchArtifactBuild(
  jobName: string,
  buildId: string,
  opts?: {
    timeoutMs?: number;
    intervalMs?: number;
    slotKey?: string;
    excludeMuxHash?: string;
  },
): Promise<StitchArtifactBuildPoll> {
  const timeoutMs = opts?.timeoutMs ?? 900_000;
  const intervalMs = opts?.intervalMs ?? 1_000;
  const slotKey = opts?.slotKey ?? 'standalone';
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await apiGet<{
      artifact_build?: StitchArtifactBuildPoll;
      job?: { slots?: Record<string, { mux_preview_hash?: string }> };
    }>(
      'stitch_editor_job',
      { job_name: jobName },
      { fetchTimeoutMs: 120_000 },
    );
    const art = res.data?.artifact_build;
    if (art?.build_id === buildId) {
      if (art.status === 'done') return art;
      if (art.status === 'failed') {
        throw new Error(art.error || 'Stitch artifact rebuild failed');
      }
    } else {
      // Active build record clears after terminal status — durable job slot is truth.
      const mux = String(res.data?.job?.slots?.[slotKey]?.mux_preview_hash ?? '').trim();
      if (mux.length >= 8 && (!opts?.excludeMuxHash || mux !== opts.excludeMuxHash)) {
        return {
          build_id: buildId,
          status: 'done',
          code: STITCH_ARTIFACT_ORCHESTRATOR_V1,
        };
      }
    }
    await sleep(intervalMs);
  }
  throw new Error(`Stitch artifact build ${buildId} timed out after ${timeoutMs}ms`);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
