// BgTab — Beat Generator full UI (S5.5c rewrite, supersedes 91-line Session 2 stub).
//
// Per LD BEAT_GEN_3_OPTIONS_NOT_GRID_V1: 3 OPTIONS per beat (NOT 3×3 matrix,
// NOT 9 stills, NOT FLUX). One char ref + one BG ref per beat; backend submits
// 3 GPT calls (varied seed) → 3 options. UI layout is 1×3, NOT 3×3.
//
// Per LD UI_PRIMITIVES_SHARED_V1: uses Modal/Toast/Spinner/Select/AssetTile.
// Per LD CROPPER_CANVAS_REAL_V1: opens CropperModal for char/BG ref editing.
// Per LD SCOPE_VALIDATION_V1: every mutation routed via pathappPatch.
// Per LD ASYNC_JOB_GENERATION_PIN_V1: GPT batch is async (10s poll cadence
// per Cursor v8 Q6).

import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import {
  activeScope, scopeKey,
  activeProjectType, activeMilestoneId, activeTargetVideo,
} from '../state/scope';
import { apiGet, pathappPatch } from '../api/client';
import { SERVER_BASE } from '../api/endpoints';
import { makeDropTarget } from '../utils/dragdrop';
import { openCropper } from '../state/cropper';
import { Modal } from './ui/Modal';
import { Spinner } from './ui/Spinner';
import { Select } from './ui/Select';
import { pushToast } from './ui/Toast';
import { stitcherRefreshTick } from '../app';
import { serverRehydrateTick } from '../state/refreshSignals';
import {
  allBeatsStitchExportReady,
  stitchExportBlockTooltip,
} from '../utils/bgStitchExport';

// Canonical speaker roster (LD CHARACTER_DROPDOWN_RESTORED_V1).
// Kept identical to StoryboardTab.KNOWN_SPEAKERS — single source of truth
// is content-lockfiles/voice_profiles.toml. Drift between the two consts
// is a CI-checkable error (C13 Test D lockfile correctness).
const KNOWN_SPEAKERS: readonly string[] = [
  'Cedric', 'Arlo', 'Tessa', 'Luna', 'Benson',
  'Ember', 'Bork', 'Bramble', 'Grizzle', 'Oliver',
] as const;

// ----------------------------------------------------------------
// Modal state — single-modal stack invariant per UI_PRIMITIVES_SHARED_V1.
// BG-9 (delete confirm), BG-34/35 (Accept All warn + confirm), BG-5 (edit chip),
// BG-18 (remove ref confirm) all multiplex through this state machine.
// ----------------------------------------------------------------

type BgModalState =
  | { kind: 'none' }
  | { kind: 'delete-beat'; beatId: string }
  | { kind: 'accept-all-warn'; unsetIds: string[]; readyCount: number }
  | { kind: 'accept-all-confirm'; readyCount: number }
  | { kind: 'edit-chip'; beatId: string; oldChipText: string; draftText: string }
  | { kind: 'remove-ref'; beatId: string; refField: 'reference_image' | 'bg_ref_image'; label: string };

// ----------------------------------------------------------------
// Types — derived from server handler shapes (production_server.py:8627+)
// ----------------------------------------------------------------

interface GptOption {
  key: string;
  label?: string;
  local_path?: string;
  video_path?: string;
  source?: string;
  thumb_b64?: string;
  gallery_b64?: string;
  cost_usd?: number;
  error?: string;
}

interface BgBeat {
  beat_id: string;
  speaker?: string;
  dialogue_text?: string;
  scene_notes?: string;
  emotion?: string;
  status?: string;
  accepted_image_key?: string | null;
  reference_image?: { key?: string; abs_path?: string; thumb_b64?: string } | null;
  bg_ref_image?: { key?: string; abs_path?: string; thumb_b64?: string } | null;
  flux_options?: GptOption[];
  gpt_options?: GptOption[];
  bg_gpt_batch_job_id?: string | null;
  kling_o3_status?: string;
  kling_o3_video_path?: string;
  kling_o3_options?: GptOption[];
  kling_o3_trim_start?: number;
  kling_o3_trim_back?: number | null;
  kling_o3_trim_end?: number | null;
  kling_o3_voice_fix_ui_job_id?: string | null;
  kling_o3_voice_fix_status?: string | null;
  kling_o3_voice_fix_error?: string | null;
  kling_native_lipsync_experiment_ui_job_id?: string | null;
  kling_native_lipsync_experiment_status?: string | null;
  kling_native_lipsync_experiment_route?: string | null;
  kling_native_lipsync_experiment_error?: string | null;
  kling_native_lipsync_experiment_error_code?: string | null;
  kling_native_lipsync_experiment_output_path?: string | null;
  kling_native_lipsync_experiment_passed_gate?: boolean | null;
  kling_native_lipsync_experiment_output_profile?: {
    width?: number;
    height?: number;
    min_dimension?: number;
    has_audio?: boolean;
  } | null;
}

interface BgSegment {
  event_id: string;
  phase: string;
  name?: string;
  arc_number?: number;
}

interface BgSegmentsResponse {
  segments?: BgSegment[];
  arc_number?: number;
}

interface BgSessionState {
  active_context?: { arc_number: number; event_id: string; phase: string } | null;
  beats?: BgBeat[];
  flux_options_complete?: boolean;
}

interface GptBatchSubmitResponse {
  ok: boolean;
  job_id?: string;
  beat_ids?: string[];
  total_options?: number;
}

interface GptPollResponse {
  status: 'running' | 'done';
  results: Record<string, GptOption[]>;
  total: number;
  done_count: number;
}

interface ArloO3SubmitResponse {
  ok: boolean;
  job_id?: string;
  beat_id?: string;
  attempt_id?: string;
  deduped?: boolean;
  message?: string;
}

interface ArloO3PollResponse {
  status: 'running' | 'done' | 'failed';
  beat_id?: string;
  result?: { video?: string; voice_id?: string; o3_model?: string; duration_s?: number } | null;
  error?: string | null;
}

interface NativeLipSyncSubmitResponse {
  ok: boolean;
  job_id?: string;
  beat_id?: string;
  route?: string;
  attempt_id?: string;
  deduped?: boolean;
  message?: string;
}

interface NativeLipSyncPollResponse {
  status: 'running' | 'done' | 'failed';
  beat_id?: string;
  route?: string;
  result?: {
    status?: string;
    passed_gate?: boolean;
    raw_profile?: {
      width?: number;
      height?: number;
      min_dimension?: number;
      has_audio?: boolean;
    };
    raw_output_path?: string;
    error?: string | null;
    error_code?: string | null;
  } | null;
  error?: string | null;
}

// ----------------------------------------------------------------
// Constants
// ----------------------------------------------------------------

// Per LD-440 GPT_IMAGE_2_PRIMARY_MODEL_V1 — gpt-image-2 published unit cost.
const PER_IMAGE_COST_USD = 0.04;
const POLL_INTERVAL_MS = 10000; // 10s per Cursor v8 Q6

function collectActiveO3JobsFromBeats(beats: BgBeat[]): Record<string, string> {
  const jobs: Record<string, string> = {};
  for (const beat of beats) {
    const jobId = (beat.kling_o3_voice_fix_ui_job_id ?? '').trim();
    const status = (beat.kling_o3_voice_fix_status ?? beat.kling_o3_status ?? '').toLowerCase();
    if (jobId && status !== 'approved' && !status.startsWith('failed')) {
      jobs[beat.beat_id] = jobId;
    }
  }
  return jobs;
}

function collectActiveNativeLipSyncJobsFromBeats(beats: BgBeat[]): Record<string, string> {
  const jobs: Record<string, string> = {};
  for (const beat of beats) {
    const jobId = (beat.kling_native_lipsync_experiment_ui_job_id ?? '').trim();
    const status = (beat.kling_native_lipsync_experiment_status ?? '').toLowerCase();
    if (jobId && status === 'running') {
      jobs[beat.beat_id] = jobId;
    }
  }
  return jobs;
}

function collectActiveStillJobFromBeats(beats: BgBeat[]): string | null {
  for (const beat of beats) {
    const jobId = (beat.bg_gpt_batch_job_id ?? '').trim();
    if (jobId && beat.status === 'stills_pending') {
      return jobId;
    }
  }
  return null;
}

function isUserSelectableO3Video(path?: string | null): boolean {
  const name = (path ?? '').toLowerCase().split('/').pop() ?? '';
  return Boolean(path)
    && !name.includes('_silent_o3_base')
    && !name.includes('_delivery_input')
    && !name.includes('_noaudio');
}

function formatO3JobFailure(error?: string | null): string {
  const raw = (error ?? '').trim();
  if (!raw) return 'O3 voice job failed; previous approved clip was kept active.';
  const runtime = raw.includes('RuntimeError:') ? raw.split('RuntimeError:').pop()!.trim() : raw;
  if (runtime.includes('Kling LipSync returned sub-720p output')) {
    const first = runtime.split('\n')[0];
    return first.includes('Previous approved clip was kept active')
      ? first
      : `${first} Previous approved clip was kept active.`;
  }
  if (runtime.includes('Could not download the input')) {
    return 'WaveSpeed could not download the lipsync input URL. Data-URI fallback is disabled because it returns sub-720p output; previous approved clip was kept active.';
  }
  if (runtime.includes('No lipsync input host returned byte-complete public files')) {
    return 'No lipsync input host returned byte-complete public files. The job was stopped before WaveSpeed submission; previous approved clip was kept active.';
  }
  if (runtime.includes('O3 job process is no longer running')) {
    return 'The O3 job process stopped without a completion result. The stale job marker was cleared; previous approved clip was kept active.';
  }
  return runtime.split('\n').filter(Boolean).pop()?.slice(0, 500) ?? runtime.slice(0, 500);
}

// Stage-direction chip extraction.
// Cursor v8 Q6 amendment: "first two matches after stripping quoted dialogue"
// + length cap 4-50 chars.
function extractStageChips(text: string): string[] {
  if (!text) return [];
  // Strip quoted dialogue first so parens inside quotes don't match.
  const stripped = text
    .replace(/"[^"]*"/g, '')
    .replace(/“[^”]*”/g, '');
  const matches: string[] = [];
  const re = /\(([^)]{4,50})\)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(stripped)) !== null) {
    matches.push(m[1].trim());
    if (matches.length >= 2) break;
  }
  return matches;
}

// ----------------------------------------------------------------
// BgTab root
// ----------------------------------------------------------------

export function BgTab() {
  // Active context state.
  const [arcNumber, setArcNumber] = useState<number>(1);
  const [segments, setSegments] = useState<BgSegment[]>([]);
  const [activeSegment, setActiveSegment] = useState<string>(''); // "<event_id>|<phase>"
  const [beats, setBeats] = useState<BgBeat[]>([]);
  // F-BG-001 fix: initial state is `true` because the data-load useEffect
  // fires synchronously on first mount (prevDepsRef === null branch) and
  // immediately sets loading=true. Without `true` here, the first paint
  // would falsely show the loaded-empty placeholder "(no segments yet)"
  // for one frame before the fetch starts.
  const [loading, setLoading] = useState(true);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeO3Jobs, setActiveO3Jobs] = useState<Record<string, string>>({});
  const [activeNativeLipSyncJobs, setActiveNativeLipSyncJobs] = useState<Record<string, string>>({});
  const [pollResults, setPollResults] = useState<Record<string, GptOption[]>>({});
  const [, setAcceptStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [stitcherExportStatus, setStitcherExportStatus] = useState<'idle' | 'sending'>('idle');
  const [extractStatus, setExtractStatus] = useState<'idle' | 'sending'>('idle');
  // Running cost across this session (only counts batches submitted from this UI).
  const [runningCostUsd, setRunningCostUsd] = useState<number>(0);
  const [lastBatchCostUsd, setLastBatchCostUsd] = useState<number>(0);
  // BG-9 / BG-34/35 / BG-5 / BG-18 — Modal state machine.
  const [modalState, setModalState] = useState<BgModalState>({ kind: 'none' });
  const closeModal = () => setModalState({ kind: 'none' });

  // Initial load + scope-change re-fetch (R1 fix per spec §5 Phase 3.1).
  // Deps include all scope signals so changing event/milestone/partition
  // re-fires the fetch. First mount runs sync; subsequent runs are debounced
  // 200ms (counter Q6 — first-run-sync gate via prevDepsRef).
  const prevDepsRef = useRef<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    const fetchData = async () => {
      setLoading(true);
      const segRes = await apiGet<BgSegmentsResponse>('bg_segments', { arc_number: String(arcNumber) });
      if (cancelled) return;
      const segs = segRes.data?.segments ?? [];
      setSegments(segs);

      // LD-545 Option B — pass scope_event_id so the server derives the
      // active segment from the scope's event, not the sidecar's active_context.
      const stateRes = await apiGet<BgSessionState>('bg_session_state', {
        scope_event_id: activeScope.value.event_id,
      });
      if (cancelled) return;
      const ctx = stateRes.data?.active_context;
      if (ctx) {
        setArcNumber(Number(ctx.arc_number) || arcNumber);
        setActiveSegment(`${ctx.event_id}|${ctx.phase}`);
      } else if (segs.length > 0) {
        setActiveSegment(`${segs[0].event_id}|${segs[0].phase}`);
      }
      const initialBeats = stateRes.data?.beats ?? [];
      setBeats(initialBeats);
      setActiveJobId((prev) => prev ?? collectActiveStillJobFromBeats(initialBeats));
      // Server sidecar is the source of truth. Do not merge old local active
      // jobs back in, or a tab can keep showing "Generating..." after the
      // backend has failed/cleared the job.
      setActiveO3Jobs(collectActiveO3JobsFromBeats(initialBeats));
      setLoading(false);
    };

    const depKey = [
      arcNumber,
      serverRehydrateTick.value,
      activeScope.value.event_id,
      activeProjectType.value,
      activeMilestoneId.value ?? '',
      activeTargetVideo.value,
    ].join('|');

    if (prevDepsRef.current === null) {
      // First mount: sync — must not delay or initial render shows empty.
      prevDepsRef.current = depKey;
      fetchData();
    } else if (prevDepsRef.current !== depKey) {
      // Subsequent re-fires (scope change): 200ms debounce.
      prevDepsRef.current = depKey;
      timer = window.setTimeout(fetchData, 200);
    }

    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [
    arcNumber,
    serverRehydrateTick.value,
    activeScope.value.event_id,
    activeProjectType.value,
    activeMilestoneId.value,
    activeTargetVideo.value,
  ]);

  // Poll GPT job until done.
  useEffect(() => {
    if (!activeJobId) return;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      const res = await apiGet<GptPollResponse>('bg_poll_gpt_status', { job_id: activeJobId });
      if (cancelled) return;
      if (res.ok && res.data) {
        setPollResults(res.data.results ?? {});
        if (res.data.status === 'done') {
          setActiveJobId(null);
          // Compute batch cost from completed results.
          let cost = 0;
          for (const opts of Object.values(res.data.results ?? {})) {
            for (const o of opts) {
              if (typeof o.cost_usd === 'number') cost += o.cost_usd;
            }
          }
          if (cost === 0) {
            // Fall back to flat per-image price × done count.
            cost = res.data.done_count * PER_IMAGE_COST_USD;
          }
          setLastBatchCostUsd(cost);
          setRunningCostUsd((c) => c + cost);
          pushToast({ kind: 'success', message: `Generated ${res.data.done_count} options ($${cost.toFixed(2)})`, source: 'bg-batch-done' });
          // Refresh sidecar so beats[].gpt_options + status update.
          void refreshState();
          return;
        }
      } else {
        pushToast({ kind: 'error', message: `Poll error: ${res.error}`, source: 'bg-poll-error' });
        setActiveJobId(null);
        return;
      }
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [activeJobId]);

  // Poll durable O3 + padded voice jobs until done. O3 jobs are tracked per
  // beat so Kim can submit multiple independent beats concurrently.
  useEffect(() => {
    const entries = Object.entries(activeO3Jobs);
    if (entries.length === 0) return;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      const jobs = Object.entries(activeO3Jobs);
      let anyStillRunning = false;
      const completedBeatIds: string[] = [];
      const failedBeatIds: string[] = [];

      await Promise.all(jobs.map(async ([beatId, jobId]) => {
        const res = await apiGet<ArloO3PollResponse>('bg_poll_arlo_o3_voice_status', { job_id: jobId });
        if (cancelled) return;
        if (res.ok && res.data) {
          if (res.data.status === 'done') {
            completedBeatIds.push(beatId);
            pushToast({
              kind: 'success',
              message: `O3 voice video ready${res.data.result?.duration_s ? ` (${res.data.result.duration_s.toFixed(2)}s)` : ''}`,
              source: 'bg-o3-done',
            });
            return;
          }
          if (res.data.status === 'failed') {
            failedBeatIds.push(beatId);
            pushToast({
              kind: 'error',
              message: `O3 voice job failed: ${formatO3JobFailure(res.data.error)}`,
              source: 'bg-o3-error',
            });
            return;
          }
          anyStillRunning = true;
          return;
        }
        failedBeatIds.push(beatId);
        pushToast({ kind: 'error', message: `O3 poll error: ${res.error}`, source: 'bg-o3-poll-error' });
      }));
      if (cancelled) return;

      if (completedBeatIds.length > 0 || failedBeatIds.length > 0) {
        setActiveO3Jobs((prev) => {
          const next = { ...prev };
          for (const beatId of [...completedBeatIds, ...failedBeatIds]) {
            delete next[beatId];
          }
          return next;
        });
        void refreshState();
      }
      if (!anyStillRunning) {
        return;
      }
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [activeO3Jobs]);

  // Poll isolated native Kling-compatible lipsync experiments. These jobs
  // never approve or replace the current O3 clip; they only report raw proof.
  useEffect(() => {
    const entries = Object.entries(activeNativeLipSyncJobs);
    if (entries.length === 0) return;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      const jobs = Object.entries(activeNativeLipSyncJobs);
      let anyStillRunning = false;
      const completedBeatIds: string[] = [];

      await Promise.all(jobs.map(async ([beatId, jobId]) => {
        const res = await apiGet<NativeLipSyncPollResponse>(
          'bg_poll_kling_native_lipsync_experiment_status',
          { job_id: jobId },
        );
        if (cancelled) return;
        if (res.ok && res.data) {
          if (res.data.status === 'running') {
            anyStillRunning = true;
            return;
          }
          completedBeatIds.push(beatId);
          const profile = res.data.result?.raw_profile;
          const dims = profile?.width && profile?.height ? `${profile.width}x${profile.height}` : 'no raw dimensions';
          const passed = res.data.result?.passed_gate === true;
          pushToast({
            kind: passed ? 'success' : 'error',
            message: passed
              ? `Native Kling LipSync proof passed raw gate (${dims}). No approval was changed.`
              : `Native Kling LipSync proof failed or blocked (${dims}). No approval was changed.`,
            source: passed ? 'bg-native-lipsync-done' : 'bg-native-lipsync-failed',
          });
          return;
        }
        completedBeatIds.push(beatId);
        pushToast({ kind: 'error', message: `Native lipsync poll error: ${res.error}`, source: 'bg-native-lipsync-poll-error' });
      }));
      if (cancelled) return;

      if (completedBeatIds.length > 0) {
        setActiveNativeLipSyncJobs((prev) => {
          const next = { ...prev };
          for (const beatId of completedBeatIds) delete next[beatId];
          return next;
        });
        void refreshState();
      }
      if (!anyStillRunning) return;
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [activeNativeLipSyncJobs]);

  const refreshState = async () => {
    // LD-545 Option B — include scope_event_id on refresh fetches too.
    const stateRes = await apiGet<BgSessionState>('bg_session_state', {
      scope_event_id: activeScope.value.event_id,
    });
    if (stateRes.ok && stateRes.data) {
      const nextBeats = stateRes.data.beats ?? [];
      setBeats(nextBeats);
      setActiveJobId((prev) => prev ?? collectActiveStillJobFromBeats(nextBeats));
      setActiveO3Jobs(collectActiveO3JobsFromBeats(nextBeats));
      setActiveNativeLipSyncJobs(collectActiveNativeLipSyncJobsFromBeats(nextBeats));
    }
  };

  // ----------------------------------------------------------------
  // Mutations
  // ----------------------------------------------------------------

  const onSelectSegment = async (combined: string) => {
    if (!combined) return;
    setActiveSegment(combined);
    const [event_id, phase] = combined.split('|');
    const result = await pathappPatch(activeScope.value, 'bg_set_active_context', {
      arc_number: arcNumber, event_id, phase,
    });
    if (!result.ok) {
      pushToast({ kind: 'error', message: `Set context failed: ${result.error}`, source: 'bg-set-context' });
    }
    await refreshState();
  };

  const onExtractBeats = async () => {
    if (!activeSegment) return;
    const [event_id, phase] = activeSegment.split('|');
    setExtractStatus('sending');
    const result = await pathappPatch<{ beats: BgBeat[]; count: number }>(
      activeScope.value, 'bg_extract_beats', { arc_number: arcNumber, event_id, phase },
    );
    setExtractStatus('idle');
    if (result.ok && result.data) {
      setBeats(result.data.beats ?? []);
      pushToast({ kind: 'success', message: `Extracted ${result.data.count} beats`, source: 'bg-extract' });
    } else {
      pushToast({ kind: 'error', message: `Extract failed: ${result.error}`, source: 'bg-extract-error' });
    }
  };

  const onAddBeat = async (afterBeatId: string) => {
    if (!activeSegment) return;
    const [event_id, phase] = activeSegment.split('|');
    const result = await pathappPatch(activeScope.value, 'bg_add_beat', {
      after_beat_id: afterBeatId,
      segment: `event_${event_id}_${phase}`,
    });
    if (result.ok) {
      pushToast({ kind: 'info', message: 'Beat added', source: 'bg-add' });
      await refreshState();
    } else {
      pushToast({ kind: 'error', message: `Add failed: ${result.error}`, source: 'bg-add-error' });
    }
  };

  // BG-9 — Modal-based delete confirm (replaces window.confirm per Kim 2026-05-06 lock).
  const onDeleteBeat = (beatId: string) => {
    setModalState({ kind: 'delete-beat', beatId });
  };

  const executeDeleteBeat = async () => {
    if (modalState.kind !== 'delete-beat') return;
    const beatId = modalState.beatId;
    closeModal();
    const result = await pathappPatch(activeScope.value, 'bg_delete_beat', { beat_id: beatId });
    if (result.ok) {
      pushToast({ kind: 'info', message: `Deleted ${beatId}`, source: 'bg-delete' });
      setBeats((bs) => bs.filter((b) => b.beat_id !== beatId));
    } else {
      pushToast({ kind: 'error', message: `Delete failed: ${result.error}`, source: 'bg-delete-error' });
    }
  };

  const onUpdateBeatText = async (beatId: string, nextText: string) => {
    const result = await pathappPatch(activeScope.value, 'bg_update_beat', {
      beat_id: beatId, dialogue_text: nextText,
    });
    if (!result.ok) {
      pushToast({ kind: 'error', message: `Save failed: ${result.error}`, source: 'bg-update-text' });
    }
  };

  // Speaker dropdown handler (LD CHARACTER_DROPDOWN_RESTORED_V1).
  // BG already accepts `speaker` field on bg_update_beat — see
  // production_server.py _BG_BEAT_WRITABLE (line ~9937). Optimistic local
  // update so the dropdown reflects the new value before refreshState()
  // (matches the 2026-05-11 Rule 26 fix pattern for ref-image drops).
  const onUpdateBeatSpeaker = async (beatId: string, nextSpeaker: string) => {
    setBeats((bs) => bs.map((b) => (
      b.beat_id === beatId ? { ...b, speaker: nextSpeaker } : b
    )));
    const result = await pathappPatch(activeScope.value, 'bg_update_beat', {
      beat_id: beatId, speaker: nextSpeaker,
    });
    if (!result.ok) {
      pushToast({
        kind: 'error',
        message: `Speaker save failed: ${result.error}`,
        source: 'bg-update-speaker',
      });
    }
  };

  const onGenerateBatch = async (beatId: string) => {
    if (activeO3Jobs[beatId]) {
      pushToast({ kind: 'info', message: 'This beat is already generating.', source: 'bg-o3-beat-busy' });
      return;
    }
    const beat = beats.find((b) => b.beat_id === beatId);
    if (beat?.speaker) {
      const result = await pathappPatch<ArloO3SubmitResponse>(
        activeScope.value, 'bg_submit_arlo_o3_voice', {
          beat_id: beatId,
          model: 'pro',
          // Submit the refs currently visible in the card. This closes the
          // drop-then-immediately-generate race where the async ref save has
          // not reached the sidecar before the server starts the O3 subprocess.
          reference_image: beat.reference_image ?? null,
          bg_ref_image: beat.bg_ref_image ?? null,
        },
      );
      if (result.ok && result.data?.job_id) {
        setActiveO3Jobs((prev) => ({ ...prev, [beatId]: result.data!.job_id! }));
        pushToast({
          kind: result.data.deduped ? 'info' : 'info',
          message: result.data.deduped
            ? 'This beat already has an O3 voice job running; reattached to the existing job.'
            : `Submitted ${beat.speaker} O3 Pro + Element voice (720 delivery encode)`,
          source: 'bg-o3-submit',
        });
      } else {
        pushToast({ kind: 'error', message: `O3 submit failed: ${result.error}`, source: 'bg-o3-submit-error' });
      }
      return;
    }
    if (activeJobId) {
      pushToast({ kind: 'info', message: 'A still-generation job is still running.', source: 'bg-stills-busy' });
      return;
    }
    const result = await pathappPatch<GptBatchSubmitResponse>(
      activeScope.value, 'bg_submit_gpt_batch', { beat_ids: [beatId] },
    );
    if (result.ok && result.data?.job_id) {
      setActiveJobId(result.data.job_id);
      // Forecast: 3 calls × per-image cost.
      pushToast({
        kind: 'info',
        message: `Submitted (forecast $${(3 * PER_IMAGE_COST_USD).toFixed(2)})`,
        source: 'bg-submit',
      });
    } else {
      pushToast({ kind: 'error', message: `Submit failed: ${result.error}`, source: 'bg-submit-error' });
    }
  };

  const onSubmitNativeLipSyncExperiment = async (beatId: string) => {
    if (activeNativeLipSyncJobs[beatId]) {
      pushToast({ kind: 'info', message: 'Native Kling LipSync experiment is already running for this beat.', source: 'bg-native-lipsync-busy' });
      return;
    }
    const result = await pathappPatch<NativeLipSyncSubmitResponse>(
      activeScope.value,
      'bg_submit_kling_native_lipsync_experiment',
      {
        beat_id: beatId,
        route: 'native_kling_identify_face_advanced_lipsync',
      },
    );
    if (result.ok && result.data?.job_id) {
      setActiveNativeLipSyncJobs((prev) => ({ ...prev, [beatId]: result.data!.job_id! }));
      pushToast({
        kind: 'info',
        message: result.data.deduped
          ? 'Reattached to the running native Kling LipSync experiment. No approval will change.'
          : 'Testing native Kling LipSync route... not approving.',
        source: 'bg-native-lipsync-submit',
      });
      await refreshState();
    } else {
      pushToast({ kind: 'error', message: `Native lipsync submit failed: ${result.error}`, source: 'bg-native-lipsync-submit-error' });
    }
  };

  // BG-5 — Edit chip via Modal (replaces no-edit-was-possible UX).
  // Click pencil icon → modal with prefilled draftText input → save → splice
  // (oldChipText) → (newChipText) in the beat's dialogue text. Empty newChipText
  // is rejected (use Remove × instead).
  const requestEditChip = (beatId: string, oldChipText: string) => {
    setModalState({ kind: 'edit-chip', beatId, oldChipText, draftText: oldChipText });
  };

  const executeEditChip = async () => {
    if (modalState.kind !== 'edit-chip') return;
    const { beatId, oldChipText, draftText } = modalState;
    const trimmed = draftText.trim();
    if (!trimmed || trimmed === oldChipText) {
      closeModal();
      return;
    }
    closeModal();
    const beat = beats.find((b) => b.beat_id === beatId);
    if (!beat) return;
    const currentText = beat.dialogue_text ?? '';
    const oldEsc = oldChipText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`\\(${oldEsc}\\)`);
    const nextText = currentText.replace(re, `(${trimmed})`);
    if (nextText === currentText) {
      pushToast({
        kind: 'error',
        message: `Could not locate chip "${oldChipText}" in dialogue`,
        source: 'bg-chip-edit-miss',
      });
      return;
    }
    // Optimistic local update.
    setBeats((bs) => bs.map((b) => (b.beat_id === beatId ? { ...b, dialogue_text: nextText } : b)));
    const result = await pathappPatch(activeScope.value, 'bg_update_beat', {
      beat_id: beatId,
      dialogue_text: nextText,
    });
    if (!result.ok) {
      pushToast({
        kind: 'error',
        message: `Chip edit save failed: ${result.error}`,
        source: 'bg-chip-edit-error',
      });
    }
  };

  // BG-18 — Remove ref via Modal confirm (clears reference_image / bg_ref_image).
  const requestRemoveRef = (
    beatId: string,
    refField: 'reference_image' | 'bg_ref_image',
    label: string,
  ) => {
    setModalState({ kind: 'remove-ref', beatId, refField, label });
  };

  const executeRemoveRef = async () => {
    if (modalState.kind !== 'remove-ref') return;
    const { beatId, refField, label } = modalState;
    closeModal();
    const result = await pathappPatch(activeScope.value, 'bg_update_beat', {
      beat_id: beatId,
      [refField]: null,
    });
    if (result.ok) {
      pushToast({ kind: 'info', message: `${label} cleared`, source: 'bg-ref-remove' });
      await refreshState();
    } else {
      pushToast({
        kind: 'error',
        message: `${label} remove failed: ${result.error}`,
        source: 'bg-ref-remove-error',
      });
    }
  };

  const onAcceptOption = async (beatId: string, optionKey: string) => {
    const result = await pathappPatch(activeScope.value, 'bg_accept_option', {
      beat_id: beatId, option_key: optionKey,
    });
    if (result.ok) {
      pushToast({ kind: 'success', message: `Locked ${optionKey}`, source: 'bg-accept-opt' });
      await refreshState();
    } else {
      pushToast({ kind: 'error', message: `Lock failed: ${result.error}`, source: 'bg-accept-opt-error' });
    }
  };

  const onSelectO3Video = async (beatId: string, optionKey: string) => {
    const result = await pathappPatch(activeScope.value, 'bg_select_o3_video', {
      beat_id: beatId, option_key: optionKey,
    });
    if (result.ok) {
      pushToast({ kind: 'success', message: 'Selected preserved O3 video', source: 'bg-select-o3' });
      await refreshState();
    } else {
      pushToast({ kind: 'error', message: `Select O3 video failed: ${result.error}`, source: 'bg-select-o3-error' });
    }
  };

  const onApplyO3Trim = async (beatId: string, trimStart: number, trimBack: number | null, clear = false) => {
    const result = await pathappPatch<{
      trim_start?: number;
      trim_back?: number | null;
      effective_duration_s?: number | null;
    }>(activeScope.value, 'bg_kling_o3_trim', {
      beat_id: beatId,
      trim_start: trimStart,
      trim_back: trimBack,
      clear,
    });
    if (result.ok) {
      setBeats((bs) => bs.map((b) => (
        b.beat_id === beatId
          ? {
            ...b,
            kling_o3_trim_start: result.data?.trim_start ?? 0,
            kling_o3_trim_back: result.data?.trim_back ?? null,
          }
          : b
      )));
      const dur = result.data?.effective_duration_s;
      pushToast({
        kind: 'success',
        message: clear ? 'Trim cleared' : (dur != null ? `Trim saved (${dur.toFixed(1)}s)` : 'Trim saved'),
        source: 'bg-o3-trim',
      });
    } else {
      pushToast({ kind: 'error', message: `Trim failed: ${result.error}`, source: 'bg-o3-trim-error' });
    }
  };

  // BG-34/35 — Accept All warn modal (lists unset beats) + confirm modal
  // (Lock in N selections...). Replaces direct mutation; gates on user
  // acknowledgement of unset beats per Kim 2026-05-06 lock.
  const segmentCtx = () => {
    const [event_id, phase] = (activeSegment || '1|pre').split('|');
    return { event_id, phase };
  };

  const allBeatsExportReady = useMemo(
    () => allBeatsStitchExportReady(beats),
    [beats],
  );

  const stitchSlotForSegment = useMemo(() => {
    const phase = (activeSegment || '1|pre').split('|')[1] || 'pre';
    const byPhase: Record<string, string> = {
      pre: 'intro',
      intro: 'intro',
      post: 'resolution',
      resolution: 'resolution',
      phase_a: 'phase_a',
      phase_b: 'phase_b',
    };
    return byPhase[phase] ?? activeTargetVideo.value ?? 'intro';
  }, [activeSegment, activeTargetVideo.value]);

  const stitchExportTooltip = useMemo(
    () => stitchExportBlockTooltip(beats, stitchSlotForSegment),
    [beats, stitchSlotForSegment],
  );

  const onSendToStitcher = async () => {
    if (!activeSegment || !allBeatsExportReady || stitcherExportStatus === 'sending') return;
    const { event_id, phase } = segmentCtx();
    setStitcherExportStatus('sending');
    const result = await pathappPatch<{ slot_key?: string; video_path?: string; duration_s?: number }>(
      activeScope.value,
      'bg_export_to_stitcher',
      {
        arc_number: arcNumber,
        event_id,
        phase,
        slot_key: stitchSlotForSegment,
      },
    );
    setStitcherExportStatus('idle');
    if (result.ok) {
      const slot = result.data?.slot_key ?? stitchSlotForSegment;
      stitcherRefreshTick.value += 1;
      pushToast({
        kind: 'success',
        message: `Sent to Stitcher → ${slot} slot (canonical tail + intro fades when applicable)`,
        source: 'bg-kling-export',
      });
    } else {
      pushToast({
        kind: 'error',
        message: `Send to Stitcher failed: ${result.error ?? 'unknown error'}`,
        source: 'bg-kling-export-error',
      });
    }
  };

  const _onAcceptAll = () => {
    if (beats.length === 0) {
      pushToast({ kind: 'info', message: 'No beats to accept.', source: 'bg-accept-all-empty' });
      return;
    }
    const ready = beats.filter((b) => b.accepted_image_key || b.kling_o3_video_path);
    const unset = beats.filter((b) => !b.accepted_image_key && !b.kling_o3_video_path).map((b) => b.beat_id);
    if (unset.length > 0) {
      // BG-34 — Show warn modal with unset beat_ids before proceeding.
      setModalState({ kind: 'accept-all-warn', unsetIds: unset, readyCount: ready.length });
      return;
    }
    // All beats have selections → straight to BG-35 confirm.
    setModalState({ kind: 'accept-all-confirm', readyCount: ready.length });
  };

  // BG-34 → BG-35 transition: warn modal "Continue anyway" advances to confirm.
  const proceedToAcceptConfirm = () => {
    if (modalState.kind !== 'accept-all-warn') return;
    setModalState({ kind: 'accept-all-confirm', readyCount: modalState.readyCount });
  };

  // BG-35 — Final confirm fires the actual mutation.
  const executeAcceptAll = async () => {
    if (modalState.kind !== 'accept-all-confirm') return;
    closeModal();
    setAcceptStatus('sending');
    // Cursor v8 Q9 — partial-failure idempotent retry: the server is the source
    // of truth for pipeline_stage; the client just submits the current
    // selections. Re-running Accept All is safe (server merges).
    const acceptedBeats = beats
      .filter((b) => b.accepted_image_key || b.kling_o3_video_path)
      .map((b) => ({
        beat_id: b.beat_id,
        accepted_image_key: b.accepted_image_key,
        kling_o3_video_path: b.kling_o3_video_path,
        kling_o3_trim_start: b.kling_o3_trim_start,
        kling_o3_trim_back: b.kling_o3_trim_back,
        kling_o3_trim_end: b.kling_o3_trim_end,
        speaker: b.speaker,
        dialogue_text: b.dialogue_text,
      }));
    const [event_id] = (activeSegment || '|').split('|');
    const result = await pathappPatch(activeScope.value, 'bg_accept_beats', {
      beats: acceptedBeats,
      segment: Number(event_id) || 0,
    });
    if (result.ok) {
      setAcceptStatus('ok');
      pushToast({
        kind: 'success',
        message: `Sent ${acceptedBeats.length} Beat Gen clips to Stitcher`,
        source: 'bg-accept-all',
      });
      setTimeout(() => setAcceptStatus('idle'), 3000);
    } else {
      setAcceptStatus('error');
      pushToast({
        kind: 'error',
        message: `Accept All failed: ${result.error}`,
        source: 'bg-accept-all-error',
      });
    }
  };

  void _onAcceptAll;

  // ----------------------------------------------------------------
  // Render
  // ----------------------------------------------------------------

  const segmentOptions = useMemo(
    () => segments.map((s) => ({
      value: `${s.event_id}|${s.phase}`,
      label: `Event ${s.event_id} ${s.phase}${s.name ? ` — ${s.name}` : ''}`,
    })),
    [segments],
  );

  return (
    <section class="mn-tab-pane mn-bg-pane" data-testid="pane-bg">
      <header class="mn-pane-header">
        <h2>Beat Generator</h2>
        <span class="mn-scope-chip" data-testid="bg-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
      </header>

      <div class="mn-bg-toolbar" data-testid="bg-toolbar">
        <Select
          id="bg-arc"
          label="Arc"
          options={[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => ({ value: String(n), label: `Arc ${n}` }))}
          value={String(arcNumber)}
          onChange={(v) => setArcNumber(Number(v))}
        />
        <Select
          id="bg-segment"
          label="Segment"
          options={segmentOptions}
          value={activeSegment}
          onChange={onSelectSegment}
          // F-BG-001 fix: distinguish in-flight fetch from loaded-empty.
          // Pre-fix code keyed off `segments.length === 0`, which left the
          // placeholder stuck on "Loading…" forever when the server returned
          // {segments: [], arc_number: N} (a valid empty result, not a
          // pending request). Now: loading state controls the loading copy;
          // empty-after-load surfaces "(no segments yet)" so the user knows
          // authoring is required.
          placeholder={
            loading
              ? 'Loading…'
              : segments.length === 0
                ? '(no segments yet)'
                : 'Select segment'
          }
        />
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid="bg-extract-btn"
          onClick={onExtractBeats}
          disabled={!activeSegment || extractStatus === 'sending'}
        >
          {extractStatus === 'sending' ? (
            <><Spinner size="sm" inline /> Extracting…</>
          ) : '+ Extract Beats from script'}
        </button>
        <button
          type="button"
          class="mn-btn"
          data-testid="bg-add-empty-btn"
          onClick={() => {
            const lastId = beats.length > 0 ? beats[beats.length - 1].beat_id : '';
            void onAddBeat(lastId);
          }}
          disabled={!activeSegment}
        >
          + Add empty beat
        </button>
        <span class="mn-bg-cost" data-testid="bg-cost">
          Cost this session:{' '}
          <span class="mn-bg-cost-running">${runningCostUsd.toFixed(2)}</span>
          {' • '}This generation: ${lastBatchCostUsd.toFixed(2)}
        </span>
      </div>

      {loading ? (
        <p class="mn-loading"><Spinner size="md" inline /> Loading beat state…</p>
      ) : beats.length === 0 ? (
        <div class="mn-empty" data-testid="bg-empty">
          <p>No beats yet for this segment. Click <strong>Extract Beats from script</strong> to start.</p>
        </div>
      ) : (
        <ol class="mn-bg-beat-list" data-testid="bg-beat-list">
          {beats.map((b, i) => (
            <BeatGenCard
              key={b.beat_id}
              index={i}
              beat={b}
              pollResultForBeat={pollResults[b.beat_id]}
              busy={activeJobId !== null || !!activeO3Jobs[b.beat_id] || !!activeNativeLipSyncJobs[b.beat_id]}
              nativeExperimentBusy={!!activeNativeLipSyncJobs[b.beat_id]}
              onDelete={() => onDeleteBeat(b.beat_id)}
              onUpdateText={(t) => onUpdateBeatText(b.beat_id, t)}
              onUpdateSpeaker={(s) => onUpdateBeatSpeaker(b.beat_id, s)}
              onGenerate={() => onGenerateBatch(b.beat_id)}
              onAccept={(optionKey) => onAcceptOption(b.beat_id, optionKey)}
              onSelectO3Video={(optionKey) => onSelectO3Video(b.beat_id, optionKey)}
              onApplyO3Trim={(trimStart, trimBack, clear) => onApplyO3Trim(b.beat_id, trimStart, trimBack, clear)}
              onSubmitNativeLipSyncExperiment={() => onSubmitNativeLipSyncExperiment(b.beat_id)}
              onEditChip={(c) => requestEditChip(b.beat_id, c)}
              onInsertAfter={() => onAddBeat(b.beat_id)}
              onRemoveRef={(refField, label) => requestRemoveRef(b.beat_id, refField, label)}
              onRefresh={() => refreshState()}
              // 2026-05-11 Rule 26 fix — optimistic local-state patchers so the
              // UI updates IMMEDIATELY from the server response, independent
              // of the follow-up bg_session_state GET. Eliminates the
              // "second drop doesn't repaint" symptom (RC1: stale
              // pollResultForBeat shadowed persisted gpt_options on refresh)
              // and the "Char ref shows key text instead of thumb" symptom
              // (RC2: bg_update_beat doesn't return a thumbnail).
              onPatchOptionTile={(slotIndex, patch) => {
                setBeats((bs) => bs.map((bb): BgBeat => {
                  if (bb.beat_id !== b.beat_id) return bb;
                  const opts: (GptOption | null)[] = [...(bb.gpt_options ?? [])];
                  while (opts.length <= slotIndex) opts.push(null);
                  const existing = (opts[slotIndex] as GptOption | null) ?? { key: '' };
                  opts[slotIndex] = { ...existing, ...patch };
                  const next: BgBeat = {
                    ...bb,
                    gpt_options: opts.filter((o): o is GptOption => o !== null),
                    accepted_image_key: patch.key ?? bb.accepted_image_key ?? null,
                    status: 'lib_chosen',
                  };
                  return next;
                }));
                // RC1 fix — clear stale pollResultForBeat so the persisted
                // gpt_options (just patched above) become the visible source.
                setPollResults((prev) => {
                  if (!(b.beat_id in prev)) return prev;
                  const next = { ...prev };
                  delete next[b.beat_id];
                  return next;
                });
              }}
              onPatchRefImage={(refField, patch) => {
                setBeats((bs) => bs.map((bb) =>
                  bb.beat_id === b.beat_id ? { ...bb, [refField]: patch } : bb,
                ));
              }}
            />
          ))}
        </ol>
      )}

      <footer class="mn-pane-footer">
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid="bg-export-stitcher-btn"
          title={stitchExportTooltip}
          onClick={onSendToStitcher}
          disabled={!activeSegment || !allBeatsExportReady || stitcherExportStatus === 'sending'}
        >
          {stitcherExportStatus === 'sending' ? (
            <><Spinner size="sm" inline /> Sending…</>
          ) : 'Send Beat Gen to Stitcher'}
        </button>
      </footer>

      {/* BG-9 — Delete-beat confirm Modal */}
      <Modal
        id="bg-delete-beat"
        title="Delete beat?"
        open={modalState.kind === 'delete-beat'}
        onClose={closeModal}
        footer={
          <>
            <button type="button" class="mn-btn" data-testid="bg-delete-cancel" onClick={closeModal}>
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="bg-delete-confirm"
              onClick={executeDeleteBeat}
            >
              Delete
            </button>
          </>
        }
      >
        <p>
          Delete beat{' '}
          <strong>{modalState.kind === 'delete-beat' ? modalState.beatId : ''}</strong>?
          This removes the beat record from the BG sidecar.
        </p>
      </Modal>

      {/* BG-34 — Accept All warn Modal (lists unset beat_ids) */}
      <Modal
        id="bg-accept-all-warn"
        title="Some beats have no selection"
        open={modalState.kind === 'accept-all-warn'}
        onClose={closeModal}
        footer={
          <>
            <button
              type="button"
              class="mn-btn"
              data-testid="bg-accept-warn-cancel"
              onClick={closeModal}
            >
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="bg-accept-warn-continue"
              onClick={proceedToAcceptConfirm}
            >
              Continue anyway
            </button>
          </>
        }
      >
        {modalState.kind === 'accept-all-warn' ? (
          <>
            <p>
              <strong>{modalState.unsetIds.length}</strong> beat
              {modalState.unsetIds.length === 1 ? '' : 's'} have no accepted image.
              They will be skipped. <strong>{modalState.readyCount}</strong> beat
              {modalState.readyCount === 1 ? '' : 's'} will be sent to Stitcher.
            </p>
            <ul class="mn-bg-modal-unset-list" data-testid="bg-accept-warn-list">
              {modalState.unsetIds.map((id) => (
                <li key={id}>{id}</li>
              ))}
            </ul>
          </>
        ) : null}
      </Modal>

      {/* BG-35 — Accept All final confirm Modal */}
      <Modal
        id="bg-accept-all-confirm"
        title="Lock in selections?"
        open={modalState.kind === 'accept-all-confirm'}
        onClose={closeModal}
        footer={
          <>
            <button
              type="button"
              class="mn-btn"
              data-testid="bg-accept-confirm-cancel"
              onClick={closeModal}
            >
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="bg-accept-confirm-go"
              onClick={executeAcceptAll}
            >
              Lock in & advance
            </button>
          </>
        }
      >
        {modalState.kind === 'accept-all-confirm' ? (
          <p>
            Lock in <strong>{modalState.readyCount}</strong> selection
            {modalState.readyCount === 1 ? '' : 's'} and advance pipeline_stage?
            This sends accepted Beat Gen clips to Stitcher.
          </p>
        ) : null}
      </Modal>

      {/* BG-5 — Edit chip Modal */}
      <Modal
        id="bg-edit-chip"
        title="Edit stage direction"
        open={modalState.kind === 'edit-chip'}
        onClose={closeModal}
        footer={
          <>
            <button type="button" class="mn-btn" data-testid="bg-chip-edit-cancel" onClick={closeModal}>
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="bg-chip-edit-save"
              onClick={executeEditChip}
            >
              Save
            </button>
          </>
        }
      >
        {modalState.kind === 'edit-chip' ? (
          <>
            <p class="mn-dim">Editing chip for beat {modalState.beatId}</p>
            <input
              type="text"
              class="mn-bg-chip-edit-input"
              data-testid="bg-chip-edit-input"
              value={modalState.draftText}
              onInput={(e) => {
                const next = (e.target as HTMLInputElement).value;
                setModalState((prev) =>
                  prev.kind === 'edit-chip' ? { ...prev, draftText: next } : prev,
                );
              }}
              autoFocus
            />
          </>
        ) : null}
      </Modal>

      {/* BG-18 — Remove ref confirm Modal */}
      <Modal
        id="bg-remove-ref"
        title="Remove reference?"
        open={modalState.kind === 'remove-ref'}
        onClose={closeModal}
        footer={
          <>
            <button type="button" class="mn-btn" data-testid="bg-remove-ref-cancel" onClick={closeModal}>
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="bg-remove-ref-confirm"
              onClick={executeRemoveRef}
            >
              Remove
            </button>
          </>
        }
      >
        {modalState.kind === 'remove-ref' ? (
          <p>
            Remove the <strong>{modalState.label}</strong> from this beat?
            The reference is cleared; you can drop a new image any time.
          </p>
        ) : null}
      </Modal>
    </section>
  );
}

// ----------------------------------------------------------------
// BeatGenCard — per-beat UI (1 char ref + 1 BG ref + 1×3 options)
// ----------------------------------------------------------------

interface BeatGenCardProps {
  index: number;
  beat: BgBeat;
  pollResultForBeat?: GptOption[];
  busy: boolean;
  nativeExperimentBusy: boolean;
  onDelete: () => void;
  onUpdateText: (next: string) => void;
  // LD CHARACTER_DROPDOWN_RESTORED_V1 — speaker dropdown change.
  onUpdateSpeaker: (next: string) => void;
  onGenerate: () => void;
  onAccept: (optionKey: string) => void;
  onSelectO3Video: (optionKey: string) => void;
  onApplyO3Trim: (trimStart: number, trimBack: number | null, clear?: boolean) => void;
  onSubmitNativeLipSyncExperiment: () => void;
  // BG-5 / BG-8 / BG-18 — visible-button handlers (NOT right-click per Kim 2026-05-06).
  onEditChip: (chipText: string) => void;
  onInsertAfter: () => void;
  onRemoveRef: (refField: 'reference_image' | 'bg_ref_image', label: string) => void;
  // 2026-05-11 fix — parent refreshState() threaded into BgRefSlot + BgOptionTile.
  onRefresh: () => void;
  // 2026-05-11 Rule 26 fix — optimistic local-state patchers per beat.
  // BgOptionTile calls onPatchOptionTile(slotIndex, {key, thumb_b64, ...}) on
  // successful library-image drop to update the gpt_options[slot] entry +
  // accepted_image_key + status WITHOUT waiting for the refresh round-trip.
  // BgRefSlot calls onPatchRefImage('reference_image'|'bg_ref_image',
  // {key, abs_path, thumb_b64?}) similarly for char/bg refs.
  onPatchOptionTile: (slotIndex: number, patch: Partial<GptOption> & { key?: string; thumb_b64?: string }) => void;
  onPatchRefImage: (
    refField: 'reference_image' | 'bg_ref_image',
    patch: { key?: string; abs_path?: string; thumb_b64?: string } | null,
  ) => void;
}

function BeatGenCard({
  index, beat, pollResultForBeat, busy, nativeExperimentBusy,
  onDelete, onUpdateText, onUpdateSpeaker, onGenerate, onAccept,
  onSelectO3Video, onApplyO3Trim, onSubmitNativeLipSyncExperiment,
  onEditChip, onInsertAfter, onRemoveRef, onRefresh,
  onPatchOptionTile, onPatchRefImage,
}: BeatGenCardProps) {
  const [localText, setLocalText] = useState<string>(beat.dialogue_text ?? '');
  const [chips, setChips] = useState<string[]>(extractStageChips(beat.dialogue_text ?? ''));
  // Sync local text when the beat prop changes (server-driven update).
  useEffect(() => {
    setLocalText(beat.dialogue_text ?? '');
    setChips(extractStageChips(beat.dialogue_text ?? ''));
  }, [beat.dialogue_text]);

  const onTextInput = (e: Event) => {
    const t = (e.target as HTMLTextAreaElement).value;
    setLocalText(t);
    setChips(extractStageChips(t));
  };

  const onTextBlur = () => {
    if (localText !== (beat.dialogue_text ?? '')) {
      onUpdateText(localText);
    }
  };

  const onRemoveChip = (chipText: string) => {
    // Remove the FIRST occurrence of the chip's parenthesized form from the
    // dialogue text. setNext.
    const re = new RegExp(`\\s*\\(${chipText.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}\\)`);
    const next = localText.replace(re, '');
    setLocalText(next);
    setChips(extractStageChips(next));
    onUpdateText(next);
  };

  // Determine which option list to show. Preference: live poll results for
  // this beat, else the persisted gpt_options/flux_options on the beat.
  const persistedOptions = beat.gpt_options ?? beat.flux_options ?? [];
  const liveOptions = pollResultForBeat ?? null;
  const optionsToShow: (GptOption | null)[] = (() => {
    const o3History = (beat.kling_o3_options ?? []).filter((o) => isUserSelectableO3Video(o?.video_path));
    const activeAlreadyListed = o3History.some((o) => o.video_path === beat.kling_o3_video_path);
    const activeO3Path = isUserSelectableO3Video(beat.kling_o3_video_path) ? beat.kling_o3_video_path! : null;
    const approvedO3 = beat.kling_o3_status === 'approved' && activeO3Path && !activeAlreadyListed
      ? [{
          key: `${beat.beat_id}_approved_o3_video`,
          label: 'approved O3 video',
          video_path: activeO3Path,
          source: 'approved_kling_o3_video',
        }]
      : [];
    const o3Options = [...o3History, ...approvedO3];
    const src = liveOptions ?? (o3Options.length > 0 ? o3Options : persistedOptions);
    const padded: (GptOption | null)[] = [...src];
    while (padded.length < 3) padded.push(null);
    return padded.slice(0, 3); // hard cap at 3 — never 9 (LD BEAT_GEN_3_OPTIONS_NOT_GRID_V1)
  })();
  const o3FailureMessage = (beat.kling_o3_voice_fix_status ?? '').startsWith('failed')
    ? formatO3JobFailure(beat.kling_o3_voice_fix_error)
    : null;
  const nativeProfile = beat.kling_native_lipsync_experiment_output_profile;
  const nativeDims = nativeProfile?.width && nativeProfile?.height
    ? `${nativeProfile.width}x${nativeProfile.height}`
    : null;
  const nativeStatus = beat.kling_native_lipsync_experiment_status ?? null;
  // Native LipSync experiment is dev-only QA — hidden from producer UI so it cannot
  // be mistaken for the canonical Generate path (Element O3 + 720 delivery).
  const showNativeExperimentCard = false;

  return (
    <li class="mn-bg-beat-card" data-testid={`bg-beat-card-${index}`} data-beat-id={beat.beat_id}>
      <div class="mn-bg-beat-meta">
        <span class="mn-bg-beat-index">#{index + 1}</span>
        <span class="mn-bg-beat-anchor">{beat.beat_id}</span>
        <select
          class="mn-beat-speaker"
          data-testid={`bg-beat-speaker-${index}`}
          value={beat.speaker ?? ''}
          onChange={(e) => {
            const target = e.target as HTMLSelectElement | null;
            const v = (target?.value ?? '').trim();
            if (v && v !== (beat.speaker ?? '')) onUpdateSpeaker(v);
          }}
          aria-label={`Speaker for beat ${beat.beat_id}`}
          title="Change speaker (will trigger stale-TTS state on regen path)"
        >
          {(beat.speaker && !KNOWN_SPEAKERS.includes(beat.speaker)) ? (
            <option value={beat.speaker}>{beat.speaker}</option>
          ) : null}
          {!beat.speaker ? <option value="">— speaker —</option> : null}
          {KNOWN_SPEAKERS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {beat.status ? <span class="mn-dim">[{beat.status}]</span> : null}
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`bg-beat-delete-${index}`}
          onClick={onDelete}
          aria-label={`Delete beat ${beat.beat_id}`}
          style="margin-left: auto"
        >
          ✕
        </button>
      </div>

      <textarea
        class="mn-bg-beat-text"
        data-testid={`bg-beat-text-${index}`}
        value={localText}
        onInput={onTextInput}
        onBlur={onTextBlur}
        rows={2}
        spellcheck={true}
      />
      {o3FailureMessage ? (
        <div
          class="mn-bg-o3-failure"
          data-testid={`bg-o3-failure-${index}`}
          style="margin: 4px 0 8px; color: #fca5a5; font-size: 12px;"
        >
          O3/lipsync attempt failed: {o3FailureMessage}
        </div>
      ) : null}

      {showNativeExperimentCard ? (
        <div
          class="mn-bg-native-lipsync-experiment"
          data-testid={`bg-native-lipsync-experiment-${index}`}
          style="margin: 4px 0 8px; padding: 8px; border: 1px solid #475569; border-radius: 8px; font-size: 12px;"
        >
          <div style="font-weight: 600;">Test native Kling LipSync route (no approval)</div>
          <div class="mn-dim">{'No approval. Raw provider output must pass >=720 before promotion.'}</div>
          <div class="mn-dim">
            route: {beat.kling_native_lipsync_experiment_route ?? 'native_kling_identify_face_advanced_lipsync'}
            {nativeStatus ? ` • status: ${nativeStatus}` : ''}
            {nativeDims ? ` • raw: ${nativeDims}` : ''}
            {nativeProfile ? ` • audio: ${nativeProfile.has_audio ? 'yes' : 'no'}` : ''}
          </div>
          {beat.kling_native_lipsync_experiment_error ? (
            <div style="color: #fca5a5;">
              {beat.kling_native_lipsync_experiment_error_code ? `${beat.kling_native_lipsync_experiment_error_code}: ` : ''}
              {beat.kling_native_lipsync_experiment_error}
            </div>
          ) : null}
          {beat.kling_native_lipsync_experiment_output_path ? (
            <div class="mn-dim">output: {beat.kling_native_lipsync_experiment_output_path}</div>
          ) : null}
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`bg-native-lipsync-test-${index}`}
            onClick={onSubmitNativeLipSyncExperiment}
            disabled={nativeExperimentBusy}
            style="margin-top: 6px;"
          >
            {nativeExperimentBusy ? (
              <><Spinner size="sm" inline /> Testing route... not approving</>
            ) : 'Test native Kling LipSync route'}
          </button>
        </div>
      ) : null}

      {chips.length > 0 ? (
        <div class="mn-bg-stage-chips" data-testid={`bg-beat-chips-${index}`}>
          <span>Stage:</span>
          {chips.map((c) => (
            <span key={c} class="mn-bg-stage-chip">
              <span>{c}</span>
              {/* BG-5 — Edit chip pencil icon (visible button per Kim 2026-05-06 lock). */}
              <button
                type="button"
                class="mn-bg-stage-chip-edit"
                data-testid={`bg-chip-edit-${index}`}
                onClick={() => onEditChip(c)}
                aria-label={`Edit stage direction ${c}`}
                title="Edit chip"
              >
                ✎
              </button>
              <button
                type="button"
                class="mn-bg-stage-chip-x"
                data-testid={`bg-chip-x-${index}`}
                onClick={() => onRemoveChip(c)}
                aria-label={`Remove stage direction ${c}`}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      ) : null}

      <div class="mn-bg-refs-row" data-testid={`bg-beat-refs-${index}`}>
        <BgRefSlot
          label="Char ref"
          refImg={beat.reference_image ?? null}
          testId={`bg-char-ref-${index}`}
          beatId={beat.beat_id}
          refField="reference_image"
          onRemoveRef={onRemoveRef}
          onRefresh={onRefresh}
          onPatchRefImage={onPatchRefImage}
        />
        <BgRefSlot
          label="BG ref"
          refImg={beat.bg_ref_image ?? null}
          testId={`bg-bg-ref-${index}`}
          beatId={beat.beat_id}
          refField="bg_ref_image"
          onRemoveRef={onRemoveRef}
          onRefresh={onRefresh}
          onPatchRefImage={onPatchRefImage}
        />
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid={`bg-generate-btn-${index}`}
          onClick={onGenerate}
          disabled={busy}
        >
          {busy ? (
            <><Spinner size="sm" inline /> Generating…</>
          ) : beat.speaker ? 'Generate padded O3 voice video' : 'Generate 3 options'}
        </button>
      </div>

      {/* 3-options row — 1×3 layout (NOT 3×3 matrix) */}
      <div class="mn-bg-options-row" data-testid={`bg-options-row-${index}`}>
        {optionsToShow.map((opt, i) => (
          <BgOptionTile
            // 2026-05-11 Rule 26 fix — key is INDEX-stable, not opt.key. With
            // the prior `opt?.key ?? slot-${i}` key, dropping a library image
            // changed the key from "slot-N" to lib_key, which unmount/remount
            // sequence triggered a brief "no thumb" flash before next render.
            // Stable index keys + optimistic onPatchOptionTile guarantee the
            // tile re-renders in place with thumb_b64 immediately.
            key={`bg-opt-${index}-${i}`}
            optionIndex={i}
            beatIndex={index}
            beatId={beat.beat_id}
            option={opt}
            selected={!!opt && (
              opt.video_path
                ? opt.video_path === beat.kling_o3_video_path
                : opt.key === beat.accepted_image_key
            )}
            onClick={() => opt?.key && (
              opt.video_path
                ? onSelectO3Video(opt.key)
                : onAccept(opt.key)
            )}
            onRefresh={onRefresh}
            onPatchOptionTile={onPatchOptionTile}
            trimStart={beat.kling_o3_trim_start ?? 0}
            trimBack={beat.kling_o3_trim_back ?? null}
            onApplyO3Trim={onApplyO3Trim}
          />
        ))}
      </div>

      {/* BG-8 — Insert beat after this card (visible + button per Kim 2026-05-06 lock). */}
      <div class="mn-bg-insert-after" data-testid={`bg-insert-after-${index}`}>
        <button
          type="button"
          class="mn-btn mn-btn-small mn-bg-insert-after-btn"
          data-testid={`bg-insert-after-btn-${index}`}
          onClick={onInsertAfter}
          aria-label={`Insert beat after ${beat.beat_id}`}
          title="Insert beat after this one"
        >
          + Insert beat
        </button>
      </div>
    </li>
  );
}

// ----------------------------------------------------------------
// BgRefSlot — char/BG ref display
// ----------------------------------------------------------------

interface BgRefSlotProps {
  label: string;
  // NOTE: not "ref" — Preact intercepts that prop name for ref forwarding.
  refImg: { key?: string; abs_path?: string; thumb_b64?: string } | null;
  testId: string;
}

interface BgRefSlotPropsExt extends BgRefSlotProps {
  beatId: string;
  refField: 'reference_image' | 'bg_ref_image';
  // BG-18 — visible × button to remove the ref (NOT right-click per Kim 2026-05-06).
  onRemoveRef: (refField: 'reference_image' | 'bg_ref_image', label: string) => void;
  // 2026-05-11 fix — parent refreshState() to repaint stale beats[] after drop success.
  onRefresh: () => void;
  // 2026-05-11 Rule 26 fix — optimistic local-state patcher (see BeatGenCardProps).
  onPatchRefImage: (
    refField: 'reference_image' | 'bg_ref_image',
    patch: { key?: string; abs_path?: string; thumb_b64?: string } | null,
  ) => void;
}

function BgRefSlot({ label, refImg, testId, beatId, refField, onRemoveRef, onRefresh, onPatchRefImage }: BgRefSlotPropsExt) {
  const hasImage = !!refImg && (refImg.thumb_b64 || refImg.key);
  // R2 fix: drop target for library-image drag → POST bg_update_beat with the
  // ref field (reference_image or bg_ref_image) per server _BG_BEAT_WRITABLE
  // (production_server.py:8744).
  //
  // 2026-05-11 Rule 26 fix — optimistic update BEFORE the server round-trip
  // so the slot shows the dropped image immediately. refreshState() runs
  // afterward as a background consistency check.
  const dropHandlers = makeDropTarget(
    async (payload) => {
      if (payload.kind !== 'lib-image') return;
      // OPTIMISTIC LOCAL UPDATE — sets key + abs_path immediately. The server
      // response with thumb_b64 (if available) layers on top after the await.
      onPatchRefImage(refField, {
        key: payload.lib_key,
        abs_path: payload.abs_path ?? '',
      });
      const result = await pathappPatch<{ ok: boolean; thumb_b64?: string }>(
        activeScope.value, 'bg_update_beat', {
          beat_id: beatId,
          [refField]: {
            key: payload.lib_key,
            abs_path: payload.abs_path ?? '',
          },
        },
      );
      if (!result.ok) {
        // ROLLBACK on server failure — clear the optimistic patch.
        onPatchRefImage(refField, null);
        pushToast({
          kind: 'error',
          message: `${label} drop failed: ${result.error ?? `HTTP ${result.status}`}`,
          source: 'bg-ref-drop-error',
        });
      } else {
        // Layer thumb_b64 onto the optimistic update if server returned one.
        // Server side _handle_bg_update_beat was patched 2026-05-11 to mirror
        // _handle_bg_accept_lib_image's PIL thumbnail generation.
        if (result.data?.thumb_b64) {
          onPatchRefImage(refField, {
            key: payload.lib_key,
            abs_path: payload.abs_path ?? '',
            thumb_b64: result.data.thumb_b64,
          });
        }
        pushToast({
          kind: 'success',
          message: `${label} set: ${payload.lib_key}`,
          source: 'bg-ref-drop',
        });
        // Background consistency check — refreshState confirms server is in
        // sync with our optimistic local state. If a divergence appears here
        // it would surface in the next render via setBeats from refreshState.
        onRefresh();
      }
    },
    (p) => p.kind === 'lib-image',
  );
  return (
    <div
      class={`mn-bg-ref-slot mn-drop-target${hasImage ? ' has-image' : ''}`}
      data-testid={testId}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
    >
      <span class="mn-bg-ref-slot-label">{label}</span>
      {hasImage ? (
        <button
          type="button"
          class="mn-bg-ref-remove-btn"
          data-testid={`${testId}-remove`}
          onClick={(e) => {
            e.stopPropagation();
            onRemoveRef(refField, label);
          }}
          aria-label={`Remove ${label}`}
          title={`Remove ${label}`}
        >
          ✕
        </button>
      ) : null}
      {refImg?.thumb_b64 ? (
        <img src={refImg.thumb_b64} alt={label} class="mn-bg-ref-thumb" />
      ) : refImg?.key ? (
        <span class="mn-dim">{refImg.key}</span>
      ) : (
        <span class="mn-dim">drop here</span>
      )}
    </div>
  );
}

// ----------------------------------------------------------------
// BgOptionTile — one of 3 options
// ----------------------------------------------------------------

interface BgOptionTileProps {
  beatIndex: number;
  optionIndex: number;
  option: GptOption | null;
  selected: boolean;
  onClick: () => void;
}

interface BgOptionTilePropsExt extends BgOptionTileProps {
  beatId: string;
  // 2026-05-11 fix — parent refreshState() to repaint stale option slot after drop.
  onRefresh: () => void;
  // 2026-05-11 Rule 26 fix — optimistic local-state patcher (see BeatGenCardProps).
  onPatchOptionTile: (slotIndex: number, patch: Partial<GptOption> & { key?: string; thumb_b64?: string }) => void;
  trimStart: number;
  trimBack: number | null;
  onApplyO3Trim: (trimStart: number, trimBack: number | null, clear?: boolean) => void;
}

function BgOptionTile({
  beatIndex, optionIndex, option, selected, onClick, beatId, onRefresh, onPatchOptionTile,
  trimStart, trimBack, onApplyO3Trim,
}: BgOptionTilePropsExt) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [trimStartDraft, setTrimStartDraft] = useState<string>(String(trimStart || 0));
  const [trimBackDraft, setTrimBackDraft] = useState<string>(String(trimBack || 0));
  useEffect(() => {
    setTrimStartDraft(String(trimStart || 0));
  }, [trimStart]);
  useEffect(() => {
    setTrimBackDraft(String(trimBack || 0));
  }, [trimBack]);
  // R2.1 fix: drop target for library-image drag → POST bg_accept_lib_image
  // with server-accurate body shape (spec §4.3): {beat_id, key, filename,
  // abs_path, slot_index}. slot_index = optionIndex (0/1/2).
  //
  // 2026-05-11 Rule 26 fix — optimistic update from server response. Server
  // returns {ok, beat_id, accepted_image_key, thumb_b64, slot_index} so we can
  // patch the local gpt_options[slot] directly without waiting for the GET
  // round-trip (which previously got shadowed by stale pollResultForBeat).
  const dropHandlers = makeDropTarget(
    async (payload) => {
      if (payload.kind !== 'lib-image') return;
      // OPTIMISTIC LOCAL UPDATE — sets key + filename immediately so the
      // empty-slot "(empty)" placeholder swaps to a real tile before the
      // server response. thumb_b64 layers on after the server response.
      onPatchOptionTile(optionIndex, {
        key: payload.lib_key,
        ...(payload.abs_path ? { local_path: payload.abs_path } : {}),
      });
      const result = await pathappPatch<{
        ok: boolean;
        beat_id?: string;
        accepted_image_key?: string;
        thumb_b64?: string;
        slot_index?: number;
      }>(activeScope.value, 'bg_accept_lib_image', {
        beat_id: beatId,
        key: payload.lib_key,
        filename: payload.filename ?? '',
        abs_path: payload.abs_path ?? '',
        slot_index: optionIndex,
      });
      if (!result.ok) {
        // ROLLBACK on server failure — empty key, no thumb.
        onPatchOptionTile(optionIndex, { key: '' });
        pushToast({
          kind: 'error',
          message: `Drop failed: ${result.error ?? `HTTP ${result.status}`}`,
          source: 'bg-option-drop-error',
        });
      } else {
        // Layer thumb_b64 from server response onto optimistic update.
        // _handle_bg_accept_lib_image already returns thumb_b64 on success.
        if (result.data?.thumb_b64) {
          onPatchOptionTile(optionIndex, {
            key: payload.lib_key,
            thumb_b64: result.data.thumb_b64,
            ...(payload.abs_path ? { local_path: payload.abs_path } : {}),
          });
        }
        pushToast({
          kind: 'success',
          message: `Option ${optionIndex + 1} set: ${payload.lib_key}`,
          source: 'bg-option-drop',
        });
        // Background consistency check.
        onRefresh();
      }
    },
    (p) => p.kind === 'lib-image',
  );
  if (!option) {
    return (
      <div
        class="mn-bg-option mn-bg-option-empty-wrap mn-drop-target"
        data-testid={`bg-option-${beatIndex}-${optionIndex}`}
        data-bg-option-empty="true"
        onDragOver={dropHandlers.onDragOver}
        onDragLeave={dropHandlers.onDragLeave}
        onDrop={dropHandlers.onDrop}
      >
        <div class="mn-bg-option-empty">option {optionIndex + 1} (empty)</div>
      </div>
    );
  }
  // R3 fix: option without `key` → radio DISABLED + tooltip explaining why.
  // Without this gate the click silently no-ops or 400s server-side because
  // bg_accept_option requires option_key on the wire.
  const keyMissing = !option.key;
  const isApprovedVideo = !!option.video_path;
  const tooltip = keyMissing ? 'Option missing key — regenerate beat' : undefined;
  const videoUrl = option.video_path
    ? `${SERVER_BASE}/files?path=${encodeURIComponent(option.video_path)}`
    : null;
  const currentVideoTime = () => {
    const video = videoRef.current;
    return video ? Math.max(0, Number(video.currentTime) || 0) : 0;
  };
  const currentVideoBack = (atTime = currentVideoTime()) => {
    const video = videoRef.current;
    if (!video || !Number.isFinite(video.duration)) return trimBack;
    return Math.max(0, (Number(video.duration) || 0) - atTime);
  };
  const parseDraft = (value: string) => {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
  };
  const trimStartValue = () => parseDraft(trimStartDraft);
  const trimBackValue = () => parseDraft(trimBackDraft);
  const trimEndValue = (video: HTMLVideoElement) => {
    const dur = Number.isFinite(video.duration) ? Number(video.duration) : 0;
    if (dur <= 0) return null;
    return Math.max(trimStartValue() + 0.01, dur - trimBackValue());
  };
  const playTrimPreview = async () => {
    const video = videoRef.current;
    if (!video) return;
    const start = trimStartValue();
    const end = trimEndValue(video);
    video.pause();
    video.currentTime = start;
    video.ontimeupdate = () => {
      const stopAt = end ?? (Number.isFinite(video.duration) ? video.duration : Infinity);
      if (video.currentTime >= stopAt) {
        video.pause();
        video.ontimeupdate = null;
      }
    };
    try {
      await video.play();
    } catch {
      // Browser may block autoplay; the seek still makes the preview range visible.
    }
  };
  const applyDraftTrim = () => {
    onApplyO3Trim(trimStartValue(), trimBackValue() > 0 ? trimBackValue() : null);
  };
  const setStartFromPlayhead = () => {
    const start = currentVideoTime();
    setTrimStartDraft(start.toFixed(2));
    onApplyO3Trim(start, trimBackValue() > 0 ? trimBackValue() : null);
  };
  const setEndFromPlayhead = () => {
    const endAt = currentVideoTime();
    const back = currentVideoBack(endAt) ?? 0;
    setTrimBackDraft(back.toFixed(2));
    onApplyO3Trim(trimStartValue(), back > 0 ? back : null);
  };
  return (
    <div
      class={`mn-bg-option mn-drop-target${selected ? ' is-selected' : ''}${keyMissing ? ' is-disabled' : ''}${isApprovedVideo ? ' is-approved-video' : ''}`}
      data-testid={`bg-option-${beatIndex}-${optionIndex}`}
      data-option-key={option.key ?? ''}
      onClick={keyMissing ? undefined : onClick}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
      title={tooltip}
    >
      {videoUrl ? (
        <>
          <video
            ref={videoRef}
            controls
            preload="metadata"
            src={videoUrl}
            data-testid={`bg-option-video-${beatIndex}-${optionIndex}`}
            onPlay={() => {
              const video = videoRef.current;
              if (!video) return;
              const start = trimStartValue();
              const end = trimEndValue(video);
              if (start > 0.01 && video.currentTime < start) {
                video.currentTime = start;
              }
              video.ontimeupdate = () => {
                const stopAt = end ?? Infinity;
                if (video.currentTime >= stopAt) {
                  video.pause();
                  video.ontimeupdate = null;
                }
              };
            }}
          />
          <div class="mn-bg-o3-trim-controls" data-testid={`bg-o3-trim-controls-${beatIndex}-${optionIndex}`}>
            <span class="mn-dim">
              trim front
            </span>
            <input
              type="number"
              min="0"
              step="0.1"
              class="mn-bg-o3-trim-input"
              data-testid={`bg-o3-trim-start-input-${beatIndex}-${optionIndex}`}
              value={trimStartDraft}
              onClick={(e) => e.stopPropagation()}
              onInput={(e) => setTrimStartDraft((e.target as HTMLInputElement).value)}
              aria-label="Seconds to trim from the beginning"
            />
            <span class="mn-dim">s / back</span>
            <input
              type="number"
              min="0"
              step="0.1"
              class="mn-bg-o3-trim-input"
              data-testid={`bg-o3-trim-back-input-${beatIndex}-${optionIndex}`}
              value={trimBackDraft}
              onClick={(e) => e.stopPropagation()}
              onInput={(e) => setTrimBackDraft((e.target as HTMLInputElement).value)}
              aria-label="Seconds to trim from the end"
            />
            <span class="mn-dim">s</span>
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`bg-o3-start-trim-${beatIndex}-${optionIndex}`}
              onClick={(e) => {
                e.stopPropagation();
                setStartFromPlayhead();
              }}
              title="Set front trim to the current video playhead"
            >
              Start Trim
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`bg-o3-end-trim-${beatIndex}-${optionIndex}`}
              onClick={(e) => {
                e.stopPropagation();
                setEndFromPlayhead();
              }}
              title="Set end trim to the current video playhead"
            >
              End Trim
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`bg-o3-apply-trim-${beatIndex}-${optionIndex}`}
              onClick={(e) => {
                e.stopPropagation();
                applyDraftTrim();
              }}
            >
              Apply Trim
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`bg-o3-preview-trim-${beatIndex}-${optionIndex}`}
              onClick={(e) => {
                e.stopPropagation();
                void playTrimPreview();
              }}
            >
              Preview Trim
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`bg-o3-clear-trim-${beatIndex}-${optionIndex}`}
              onClick={(e) => {
                e.stopPropagation();
                setTrimStartDraft('0');
                setTrimBackDraft('0');
                onApplyO3Trim(0, null, true);
              }}
            >
              Clear Trim
            </button>
          </div>
        </>
      ) : option.thumb_b64 ? (
        <img src={option.thumb_b64} alt={`option ${optionIndex + 1}`} />
      ) : (
        <div class="mn-bg-option-empty">{option.error ?? 'no thumb'}</div>
      )}
      <label class="mn-dim" style="font-size:11px">
        <input
          type="radio"
          name={`bg-opt-${beatIndex}`}
          checked={selected}
          onChange={keyMissing ? undefined : onClick}
          disabled={keyMissing}
          title={tooltip}
          aria-label={isApprovedVideo ? `approved O3 video ${optionIndex + 1}` : (tooltip ?? `option ${optionIndex + 1}`)}
          data-testid={`bg-option-radio-${beatIndex}-${optionIndex}`}
        />
        {' '}{isApprovedVideo ? 'approved O3 video' : `option ${optionIndex + 1}`}
      </label>
      {/* ✂ Send to Cropper — hover-revealed. gallery_b64 is raw base64 (not data: URI). */}
      {(option.gallery_b64 || option.local_path || option.thumb_b64) && (
        <button
          type="button"
          class="mn-crop-btn"
          title="Send to Cropper"
          data-testid={`bg-option-crop-btn-${beatIndex}-${optionIndex}`}
          onClick={(e) => {
            e.stopPropagation();
            const src = option.gallery_b64
              ? `data:image/webp;base64,${option.gallery_b64}`
              : option.local_path
                ? `${SERVER_BASE}/api/cr/full?abs_path=${encodeURIComponent(option.local_path)}`
                : `data:image/webp;base64,${option.thumb_b64}`;
            if (!src) return;
            openCropper({
              source: src,
              sourceLabel: option.key ?? `beat ${beatId} option ${optionIndex + 1}`,
              targetBeatId: beatId,
            });
          }}
        >
          ✂
        </button>
      )}
    </div>
  );
}
