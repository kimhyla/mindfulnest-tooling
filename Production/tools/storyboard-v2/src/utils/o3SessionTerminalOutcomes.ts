import { pushToast } from '../components/ui/Toast';
import { clearPlaybackUrlCache, resolveClipPlaybackTruth } from './playbackCache';

export type O3TerminalOutcome = {
  beat_id: string;
  status: string;
  job_id?: string | null;
  video_path?: string;
  generation?: number;
  error?: string;
  reconciled?: boolean;
};

const toastedOutcomeKeys = new Set<string>();

export function resetO3TerminalOutcomeToastsForTesting(): void {
  toastedOutcomeKeys.clear();
}

function outcomeToastKey(row: O3TerminalOutcome): string {
  return `${row.beat_id}|${row.job_id ?? ''}|${row.status}|${row.generation ?? ''}`;
}

/** Toast + warm playback when session GET reconciled a terminal job the poll loop missed. */
export async function handleO3TerminalOutcomesFromSession(
  outcomes: O3TerminalOutcome[] | undefined | null,
): Promise<void> {
  if (!outcomes?.length) return;
  for (const row of outcomes) {
    const beatId = (row.beat_id ?? '').trim();
    if (!beatId) continue;
    const key = outcomeToastKey(row);
    if (toastedOutcomeKeys.has(key)) continue;
    toastedOutcomeKeys.add(key);
    const status = (row.status ?? '').trim();
    if (status === 'done' || status === 'done_with_warning') {
      const gen = row.generation != null ? ` g${row.generation}` : '';
      pushToast({
        kind: 'success',
        message: `${beatId}: O3 voice video ready${gen} (loaded from disk)`,
        source: 'bg-o3-session-reconcile',
      });
      const videoPath = (row.video_path ?? '').trim();
      if (videoPath) {
        clearPlaybackUrlCache();
        void resolveClipPlaybackTruth(videoPath);
      }
      continue;
    }
    if (status === 'failed') {
      const err = (row.error ?? 'O3 voice job failed').trim();
      pushToast({
        kind: 'error',
        message: `${beatId}: O3 voice job failed: ${err.slice(0, 120)}`,
        source: 'bg-o3-session-reconcile-failed',
      });
    }
  }
}
