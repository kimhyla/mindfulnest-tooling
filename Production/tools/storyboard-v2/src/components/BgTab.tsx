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

import { useEffect, useMemo, useRef, useState, useCallback, useLayoutEffect } from 'preact/hooks';
import {
  activeScope, scopeKey,
  activeProjectType, activeMilestoneId, activeTargetVideo,
} from '../state/scope';
import { setActiveVideoRole, videoRoleForBgPhase } from '../state/videoRole';
import { apiGet, pathappPatch, type ApiResult } from '../api/client';
import { formatMutationError } from '../api/mutationErrors';
import { SERVER_BASE } from '../api/endpoints';
import { makeDropTarget } from '../utils/dragdrop';
import { openCropper } from '../state/cropper';
import { Modal } from './ui/Modal';
import { BeatPlanModal, type BeatPlanDraftSaveStatus, type BeatPlanRow } from './BeatPlanModal';
import { InsertBeatModal, type InsertBeatPlanRow } from './InsertBeatModal';
import { Spinner } from './ui/Spinner';
import { Select } from './ui/Select';
import { pushToast } from './ui/Toast';
import { stitcherRefreshTick } from '../app';
import { serverRehydrateTick } from '../state/refreshSignals';
import {
  BeatMagicButtons,
  resolveBgMagicStillPreviewUrl,
  resolveBgMagicVideoPreviewUrl,
  resolveBgMagicStillSourcePath,
} from './BeatMagicButtons';
import {
  allBeatsStitchExportReady,
  stitchExportBlockTooltip,
} from '../utils/bgStitchExport';
import {
  beatHasActiveNavJob,
  computeBeatNavItemStatuses,
  type BeatNavItemStatus,
} from '../utils/bgBeatNavStatus';
import {
  applyPromptEditsToBeats,
  stripProtectedPromptFromPatch,
} from '../state/promptEditRegistry';
import { useProtectedPromptField } from '../hooks/useProtectedPromptField';
import { collectActiveO3JobsFromBeats } from '../o3JobStatusContract';
import type {
  ArloO3PollResponse,
  ArloO3SubmitResponse,
  O3GenerationIntentPoll,
  O3SubmitAudit,
} from '../o3GenerationIntent';

const BEAT_MISSING_TOAST_MS = 12000;

function isBeatNotFoundResult(result: Pick<ApiResult, 'ok' | 'error' | 'error_code'>): boolean {
  return !result.ok && (
    result.error_code === 'BEAT_NOT_FOUND'
    || /beat .* not found/i.test(result.error ?? '')
  );
}

function beatMissingToastMessage(beatId: string): string {
  return (
    `${beatId} is not on the server — edits in this tab are not saved. `
    + 'Hard-refresh, use + Insert after the beat above if needed, then paste your text back.'
  );
}

// Canonical speaker roster (LD CHARACTER_DROPDOWN_RESTORED_V1).
// Kept identical to StoryboardTab.KNOWN_SPEAKERS — single source of truth
// is content-lockfiles/voice_profiles.toml. Drift between the two consts
// is a CI-checkable error (C13 Test D lockfile correctness).
const KNOWN_SPEAKERS: readonly string[] = [
  'Cedric', 'Arlo', 'Tessa', 'Lorelai', 'Benson',
  'Ember', 'Bork', 'Bramble', 'Grizzle', 'Oliver',
] as const;

/** Retired cast names map to canonical roster entries (2026-06-13). */
const RETIRED_SPEAKER_CANON: Readonly<Record<string, string>> = {
  Luna: 'Lorelai',
  Chipper: 'Arlo',
  'Guide Bird': 'Arlo',
  Pip: 'Arlo',
  'Assistant Bird': 'Arlo',
};

function canonBeatSpeaker(raw?: string): string {
  const s = (raw ?? '').trim();
  if (!s) return '';
  return RETIRED_SPEAKER_CANON[s] ?? RETIRED_SPEAKER_CANON[s.toLowerCase()] ?? s;
}

function isStillInsertBeat(beat?: BgBeat | null): boolean {
  if (!beat) return false;
  return beat.pipeline === 'still_insert' || beat.beat_render_mode === 'still_insert';
}

function isO3VoiceBeat(beat?: BgBeat | null): boolean {
  if (!beat) return false;
  if (isStillInsertBeat(beat)) return false;
  const sp = (beat.speaker ?? '').trim().toLowerCase();
  if (!sp || sp === '[stage direction]' || sp === 'stage direction') return false;
  return true;
}

function isPipelineToggleable(beat?: BgBeat | null): boolean {
  if (!beat) return false;
  const sp = (beat.speaker ?? '').trim().toLowerCase();
  if (!sp || sp === '[stage direction]' || sp === 'stage direction') return false;
  return true;
}

/** Short inline gate hint — full server detail stays in yellow toast only. */
function elementCharRefInlineHint(_full?: string | null): string {
  return 'Needs registered Element pose — @Image1 must match Production/<Char>/poses/ (or re-register a new pose)';
}

/** Prompt-box is law — UI edits the same field Kling submit reads from sidecar. */
function beatPromptText(beat?: BgBeat | null): string {
  if (!beat) return '';
  const prompt = (beat.kling_o3_prompt ?? '').trim();
  if (prompt) return beat.kling_o3_prompt ?? '';
  return beat.dialogue_text ?? '';
}

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
  | { kind: 'extract-overwrite-confirm'; beatCount: number }
  | { kind: 'edit-chip'; beatId: string; oldChipText: string; draftText: string }
  | { kind: 'remove-ref'; beatId: string; refField: 'reference_image' | 'bg_ref_image'; label: string }
  | {
      kind: 'voice-drift-confirm';
      beatId: string;
      promptToSave: string;
      replaceSlotIndex: number;
      referenceImage: BgBeat['reference_image'];
      bgRefImage: BgBeat['bg_ref_image'];
      message: string;
    };

// ----------------------------------------------------------------
// Types — derived from server handler shapes (production_server.py:8627+)
// ----------------------------------------------------------------

interface GptOption {
  key: string;
  label?: string;
  generation?: number;
  local_path?: string;
  video_path?: string;
  video_path_exists?: boolean;
  source?: string;
  slot_index?: number;
  thumb_b64?: string;
  gallery_b64?: string;
  cost_usd?: number;
  error?: string;
}

interface BgBeat {
  beat_id: string;
  beat_plan_source?: string;
  speaker?: string;
  pipeline?: string;
  beat_render_mode?: string;
  dialogue_text?: string;
  scene_notes?: string;
  emotion?: string;
  status?: string;
  accepted_image_key?: string | null;
  reference_image?: { key?: string; abs_path?: string; thumb_b64?: string } | null;
  bg_ref_image?: { key?: string; abs_path?: string; thumb_b64?: string } | null;
  element_char_ref_ok?: boolean;
  element_char_ref_error?: string;
  flux_options?: GptOption[];
  gpt_options?: GptOption[];
  bg_gpt_batch_job_id?: string | null;
  kling_o3_status?: string;
  kling_o3_prompt?: string;
  o3_prompt_box_law?: boolean;
  kling_o3_video_path?: string;
  kling_o3_video_path_exists?: boolean;
  kling_o3_selected_at?: string;
  kling_o3_options?: GptOption[];
  kling_o3_clips_dir?: string;
  kling_o3_disk_delivery_count?: number;
  kling_o3_orphan_delivery_count?: number;
  kling_o3_replace_slot_index?: number;
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
  magic_still_path?: string | null;
  magic_video_path?: string | null;
  magic_still_path_exists?: boolean;
  magic_video_path_exists?: boolean;
  magic_canonical_kind?: 'still' | 'video' | null;
  storyboard_beat_id?: string | null;
  audio_file?: string | null;
  audio_file_exists?: boolean;
  start_frame_image?: { abs_path?: string } | null;
  end_frame_image?: { abs_path?: string } | null;
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
  scope_active_context?: { arc_number: number; event_id: string; phase: string } | null;
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

interface StillClipRenderResponse {
  ok: boolean;
  beat_id?: string;
  video_path?: string;
  option_key?: string;
  method?: string;
  duration_s?: number;
  tts_mixed?: boolean;
  tts_ok?: boolean;
  tts_error?: string | null;
  tts_skipped?: boolean;
  tts_regenerated?: boolean;
  tts_unchanged?: boolean;
  still_path?: string;
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
const POLL_INTERVAL_MS = 10000; // 10s per Cursor v8 Q6 — GPT batch jobs
const O3_POLL_INTERVAL_MS = 3000; // O3: faster terminal detection; poll payload carries beat snapshot
const BG_SESSION_LOAD_SLOW_HINT_MS = 8000;
const BG_SESSION_STATE_FETCH_TIMEOUT_MS = 120_000;

function mergeBeatFromO3Poll(beats: BgBeat[], patch: BgBeat): BgBeat[] {
  const safePatch = stripProtectedPromptFromPatch(patch);
  const idx = beats.findIndex((b) => b.beat_id === safePatch.beat_id);
  if (idx < 0) return beats;
  const next = [...beats];
  next[idx] = { ...beats[idx], ...safePatch };
  return next;
}

function isNetworkPollBlip(res: { ok: boolean; status: number; error?: string }): boolean {
  return !res.ok
    && res.status === 0
    && /failed to fetch|networkerror|load failed/i.test(res.error ?? '');
}

function isStaleO3JobPoll(res: { ok: boolean; status: number; error?: string; error_code?: string }): boolean {
  if (res.ok) return false;
  return res.error_code === 'ARLO_JOB_NOT_FOUND'
    || (res.status === 404 && /job.*not in server memory|unknown.*job_id/i.test(res.error ?? ''));
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

function isUserSelectableO3Video(path?: string | null, source?: string | null): boolean {
  if (source === 'still_insert_static_hold' || source === 'still_insert_ken_burns') {
    return Boolean(path);
  }
  const name = (path ?? '').toLowerCase().split('/').pop() ?? '';
  return Boolean(path)
    && !name.includes('_silent_o3_base')
    && !name.includes('_delivery_input')
    && !name.includes('_noaudio');
}

/** Stable option key for O3 history rows that were persisted without ``key``. */
function resolveO3OptionKey(opt: GptOption, beatId: string, slotIndex: number): string {
  if (opt.key) return opt.key;
  const base = (opt.video_path ?? '').split('/').pop()?.replace(/\.mp4$/i, '') ?? '';
  return base || `${beatId}_o3_${slotIndex}`;
}

function o3GenerationFromPath(path?: string | null): number {
  const name = (path ?? '').split('/').pop() ?? '';
  const m = name.match(/_g(\d+)(?:_(?:element|kling)|\.mp4)/i) ?? name.match(/_g(\d+)\.mp4$/i);
  return m ? Number(m[1]) : 0;
}

/** Fixed 3-container layout — always the three newest paid O3 deliveries (highest gN). */
function buildFixedO3OptionSlots(beat: BgBeat): (GptOption | null)[] {
  const slots: (GptOption | null)[] = [null, null, null];
  const o3History = (beat.kling_o3_options ?? []).filter((o) => isUserSelectableO3Video(o?.video_path, o?.source));
  const activeO3Path = isUserSelectableO3Video(beat.kling_o3_video_path) ? beat.kling_o3_video_path! : null;
  const sorted = [...o3History].sort((a, b) => {
    const ga = typeof a.generation === 'number' ? a.generation : o3GenerationFromPath(a.video_path);
    const gb = typeof b.generation === 'number' ? b.generation : o3GenerationFromPath(b.video_path);
    return gb - ga;
  });
  for (let si = 0; si < 3; si += 1) {
    slots[si] = sorted[si] ?? null;
  }
  const activeListed = activeO3Path && o3History.some((o) => o.video_path === activeO3Path);
  if (beat.kling_o3_status === 'approved' && activeO3Path && !activeListed) {
    const firstEmpty = slots.findIndex((s) => !s);
    const idx = firstEmpty >= 0 ? firstEmpty : 0;
    slots[idx] = {
      key: `${beat.beat_id}_approved_o3_video`,
      label: 'approved O3 video',
      video_path: activeO3Path,
      source: 'approved_kling_o3_video',
      slot_index: idx,
    };
  }
  return slots;
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

type O3BeatSlotFields = {
  kling_o3_video_path?: string | null;
  kling_o3_options?: Array<{ video_path?: string | null; source?: string | null } | null> | null;
};

function beatHasPopulatedO3Slot(beat: O3BeatSlotFields | null | undefined): boolean {
  if (!beat) return false;
  if (isUserSelectableO3Video(beat.kling_o3_video_path)) return true;
  return (beat.kling_o3_options ?? []).some((o) => isUserSelectableO3Video(o?.video_path, o?.source));
}

function o3PollResultHasVideo(res: ArloO3PollResponse): boolean {
  if (res.result?.video) return true;
  if (res.terminal?.delivered?.video_path) return true;
  return beatHasPopulatedO3Slot(res.beat as O3BeatSlotFields);
}

function beatGenFailureNotifyKey(beat: BgBeat): string | null {
  const voiceFix = (beat.kling_o3_voice_fix_status ?? '').toLowerCase();
  if (voiceFix.startsWith('failed')) {
    return `o3-fail:${beat.beat_id}:${voiceFix}:${(beat.kling_o3_voice_fix_error ?? '').slice(0, 120)}`;
  }
  const status = (beat.status ?? '').toLowerCase();
  if (status.includes('failed') || status.startsWith('o3_voice_job_failed')) {
    return `status-fail:${beat.beat_id}:${status}`;
  }
  return null;
}

function notifyNewGenFailures(beats: BgBeat[], seenRef: { current: Set<string> }): void {
  for (const beat of beats) {
    const key = beatGenFailureNotifyKey(beat);
    if (!key || seenRef.current.has(key)) continue;
    seenRef.current.add(key);
    const detail = beat.kling_o3_voice_fix_error
      ? formatO3JobFailure(beat.kling_o3_voice_fix_error)
      : (beat.status ?? 'generation failed');
    pushToast({
      kind: 'error',
      message: `${beat.beat_id}: ${detail}`,
      source: 'bg-gen-failure',
    });
  }
}

const bgSessionStateQuery = (eventId: string, videoRole: string) => ({
  scope_event_id: eventId,
  scope_video_role: videoRole,
});

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
// BG_BEAT_JUMP_NAV_V1 — Word-style persistent left jump column
// ----------------------------------------------------------------

function scrollToBeat(beatId: string): void {
  const el = document.querySelector<HTMLElement>(
    `.mn-bg-beat-list [data-beat-id="${CSS.escape(beatId)}"]`,
  );
  if (!el) return;
  const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ? 'auto' as const
    : 'smooth' as const;
  el.scrollIntoView({ behavior, block: 'start' });
}

interface BgBeatNavProps {
  beats: ReadonlyArray<{ beat_id: string }>;
  itemStatuses: ReadonlyArray<BeatNavItemStatus>;
  activeIndex: number | null;
  onJump: (beatId: string, index: number) => void;
}

function BgBeatNav({ beats, itemStatuses, activeIndex, onJump }: BgBeatNavProps) {
  return (
    <nav class="mn-bg-beat-nav" aria-label="Jump to beat" data-testid="bg-beat-nav">
      {beats.map((b, i) => {
        const status = itemStatuses[i] ?? { hasActiveJob: false, isApproved: false, activeJobHint: null };
        const badgeParts: string[] = [];
        if (status.hasActiveJob) badgeParts.push('active job');
        if (status.isApproved) badgeParts.push('approved');
        const title = badgeParts.length > 0
          ? `${b.beat_id} (${badgeParts.join(', ')})`
          : b.beat_id;
        return (
          <button
            type="button"
            key={b.beat_id}
            class={`mn-bg-beat-nav-item${activeIndex === i ? ' is-active' : ''}`}
            data-testid={`bg-beat-nav-${i}`}
            {...(activeIndex === i ? { 'aria-current': 'true' as const } : {})}
            title={title}
            onClick={() => onJump(b.beat_id, i)}
          >
            <span class="mn-bg-beat-nav-label">Beat {i + 1}</span>
            {(status.hasActiveJob || status.isApproved) ? (
              <span class="mn-bg-beat-nav-badges" aria-hidden="true">
                {status.hasActiveJob ? (
                  <span
                    class="mn-bg-beat-nav-dot"
                    data-testid={`bg-beat-nav-dot-${i}`}
                    title={status.activeJobHint ?? 'Job running'}
                  />
                ) : null}
                {status.isApproved ? (
                  <span
                    class="mn-bg-beat-nav-check"
                    data-testid={`bg-beat-nav-check-${i}`}
                    title="Approved for stitch export"
                  >
                    ✓
                  </span>
                ) : null}
              </span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
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
  /** Mirror beats state for Generate submit — ref box must not lag one render behind. */
  const beatsRef = useRef<BgBeat[]>([]);
  beatsRef.current = beats;
  // F-BG-001 fix: initial state is `true` because the data-load useEffect
  // fires synchronously on first mount (prevDepsRef === null branch) and
  // immediately sets loading=true. Without `true` here, the first paint
  // would falsely show the loaded-empty placeholder "(no segments yet)"
  // for one frame before the fetch starts.
  const [loading, setLoading] = useState(true);
  const [loadingSlowHint, setLoadingSlowHint] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeO3Jobs, setActiveO3Jobs] = useState<Record<string, string>>({});
  const [o3IntentByBeat, setO3IntentByBeat] = useState<Record<string, O3GenerationIntentPoll>>({});
  const [o3SubmitAuditByBeat, setO3SubmitAuditByBeat] = useState<Record<string, O3SubmitAudit>>({});
  const [o3WarningByBeat, setO3WarningByBeat] = useState<Record<string, string>>({});
  const [activeStillRenderJobs, setActiveStillRenderJobs] = useState<Record<string, boolean>>({});
  const [activeNativeLipSyncJobs, setActiveNativeLipSyncJobs] = useState<Record<string, string>>({});
  const [pollResults, setPollResults] = useState<Record<string, GptOption[]>>({});
  const [, setAcceptStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [stitcherExportStatus, setStitcherExportStatus] = useState<'idle' | 'sending'>('idle');
  const [extractStatus, setExtractStatus] = useState<'idle' | 'sending'>('idle');
  const [extractError, setExtractError] = useState<string | null>(null);
  const [approveStatus, setApproveStatus] = useState<'idle' | 'sending'>('idle');
  const [approveStartedAt, setApproveStartedAt] = useState<number | null>(null);
  const [beatPlanOpen, setBeatPlanOpen] = useState(false);
  const [beatPlanSummary, setBeatPlanSummary] = useState('');
  const [beatPlanRows, setBeatPlanRows] = useState<BeatPlanRow[]>([]);
  const [beatPlanDraftSaveStatus, setBeatPlanDraftSaveStatus] = useState<BeatPlanDraftSaveStatus>('idle');
  // Running cost across this session (only counts batches submitted from this UI).
  const [runningCostUsd, setRunningCostUsd] = useState<number>(0);
  const [lastBatchCostUsd, setLastBatchCostUsd] = useState<number>(0);
  // BG-9 / BG-34/35 / BG-5 / BG-18 — Modal state machine.
  const [modalState, setModalState] = useState<BgModalState>({ kind: 'none' });
  const [insertAfterBeatId, setInsertAfterBeatId] = useState<string>('');
  const [insertModalOpen, setInsertModalOpen] = useState(false);
  const [insertSubmitting, setInsertSubmitting] = useState(false);
  const [insertError, setInsertError] = useState('');
  const [activeNavIndex, setActiveNavIndex] = useState<number | null>(null);
  const navJumpLockUntilRef = useRef<number>(0);
  const closeModal = () => setModalState({ kind: 'none' });

  const beatIdsKey = useMemo(
    () => beats.map((b) => b.beat_id).join('|'),
    [beats],
  );

  const beatNavJobContext = useMemo(() => ({
    activeJobId,
    activeO3Jobs,
    o3SubmitPending: {} as Record<string, boolean>,
    activeStillRenderJobs,
    activeNativeLipSyncJobs,
  }), [activeJobId, activeO3Jobs, activeStillRenderJobs, activeNativeLipSyncJobs]);

  const beatNavItemStatuses = useMemo(
    () => computeBeatNavItemStatuses(beats, beatNavJobContext),
    [beats, beatNavJobContext],
  );

  // Reset highlight when segment/event/arc reload replaces the beat list.
  useEffect(() => {
    setActiveNavIndex(null);
  }, [beatIdsKey]);

  // Highlight nav item for the beat most visible in the scroll viewport.
  useEffect(() => {
    if (beats.length === 0) return;
    const cards = document.querySelectorAll<HTMLElement>(
      '.mn-bg-beat-list .mn-bg-beat-card',
    );
    if (cards.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        let best: { index: number; ratio: number } | null = null;
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const idx = Number((entry.target as HTMLElement).dataset['beatIndex']);
          if (Number.isNaN(idx)) continue;
          const ratio = entry.intersectionRatio;
          if (!best || ratio > best.ratio) best = { index: idx, ratio };
        }
        if (best && best.ratio >= 0.25) {
          if (Date.now() < navJumpLockUntilRef.current) return;
          setActiveNavIndex(best.index);
        }
      },
      { root: null, rootMargin: '-10% 0px -60% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] },
    );

    cards.forEach((card, i) => {
      card.dataset['beatIndex'] = String(i);
      observer.observe(card);
    });
    return () => observer.disconnect();
  }, [beatIdsKey, beats.length]);

  // Initial load + scope-change re-fetch (R1 fix per spec §5 Phase 3.1).
  // Deps include all scope signals so changing event/milestone/partition
  // re-fires the fetch. First mount runs sync; subsequent runs are debounced
  // 200ms (counter Q6 — first-run-sync gate via prevDepsRef).
  const prevDepsRef = useRef<string | null>(null);
  const beatSaveNotFoundToastRef = useRef(new Set<string>());
  const beatSaveBlockedRef = useRef(new Set<string>());
  const genFailureToastRef = useRef(new Set<string>());
  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    const fetchData = async () => {
      setLoading(true);
      setLoadingSlowHint(false);
      setActiveO3Jobs({});
      const slowHintTimer = window.setTimeout(() => {
        if (!cancelled) setLoadingSlowHint(true);
      }, BG_SESSION_LOAD_SLOW_HINT_MS);
      try {
        const segRes = await apiGet<BgSegmentsResponse>('bg_segments', { arc_number: String(arcNumber) });
        if (cancelled) return;
        const segs = segRes.data?.segments ?? [];
        setSegments(segs);

        // LD-545 Option B — scope_event_id + scope_video_role derive the segment
        // (intro→pre, resolution→post). Without scope_video_role the server falls
        // back to stale sidecar active_context and shows the wrong beats.
        const stateRes = await apiGet<BgSessionState>(
          'bg_session_state',
          bgSessionStateQuery(activeScope.value.event_id, activeTargetVideo.value),
          { fetchTimeoutMs: BG_SESSION_STATE_FETCH_TIMEOUT_MS },
        );
        if (cancelled) return;
        if (!stateRes.ok) {
          pushToast({
            kind: 'error',
            message: `Could not load beat state: ${stateRes.error ?? 'unknown error'}`,
            source: 'bg-session-load-error',
          });
        }
        const ctx = stateRes.data?.scope_active_context ?? stateRes.data?.active_context;
        if (ctx) {
          setArcNumber(Number(ctx.arc_number) || arcNumber);
          setActiveSegment(`${ctx.event_id}|${ctx.phase}`);
        } else if (segs.length > 0) {
          setActiveSegment(`${segs[0].event_id}|${segs[0].phase}`);
        }
        const initialBeats = applyPromptEditsToBeats(stateRes.data?.beats ?? []);
        setBeats(initialBeats);
        notifyNewGenFailures(initialBeats, genFailureToastRef);
        setActiveJobId((prev) => prev ?? collectActiveStillJobFromBeats(initialBeats));
        // Server sidecar is the source of truth. Do not merge old local active
        // jobs back in, or a tab can keep showing "Generating..." after the
        // backend has failed/cleared the job.
        setActiveO3Jobs(collectActiveO3JobsFromBeats(initialBeats));
      } finally {
        clearTimeout(slowHintTimer);
        if (!cancelled) {
          setLoadingSlowHint(false);
          setLoading(false);
        }
      }
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
      const staleBeatIds: string[] = [];

      const beatPatches: BgBeat[] = [];

      await Promise.all(jobs.map(async ([beatId, jobId]) => {
        const res = await apiGet<ArloO3PollResponse>('bg_poll_arlo_o3_voice_status', { job_id: jobId });
        if (cancelled) return;
        if (res.ok && res.data) {
          if (res.data.intent) {
            setO3IntentByBeat((prev) => ({ ...prev, [beatId]: res.data!.intent! }));
          }
          if (res.data.status === 'done_with_warning') {
            completedBeatIds.push(beatId);
            if (res.data.beat) beatPatches.push(res.data.beat as BgBeat);
            if (!o3PollResultHasVideo(res.data)) {
              pushToast({
                kind: 'error',
                message: `${beatId}: O3 job finished but no clip appeared in slots — check kling_o3_clips or retry Generate.`,
                source: 'bg-o3-empty',
              });
              return;
            }
            const warnMsg = res.data.warning?.message
              ?? res.data.terminal?.warning?.message
              ?? 'Delivery recovered with sidecar warning — verify clip in kling_o3_clips folder.';
            setO3WarningByBeat((prev) => ({ ...prev, [beatId]: warnMsg }));
            pushToast({
              kind: 'success',
              message: `${beatId}: O3 voice video ready (recovered after Dropbox sync blip)`,
              source: 'bg-o3-warning',
            });
            return;
          }
          if (res.data.status === 'done') {
            completedBeatIds.push(beatId);
            if (res.data.beat) beatPatches.push(res.data.beat as BgBeat);
            if (!o3PollResultHasVideo(res.data)) {
              pushToast({
                kind: 'error',
                message: `${beatId}: O3 job reported done but no clip appeared in slots — check kling_o3_clips or retry Generate.`,
                source: 'bg-o3-empty',
              });
              return;
            }
            pushToast({
              kind: 'success',
              message: `${beatId}: O3 voice video ready${res.data.result?.duration_s ? ` (${res.data.result.duration_s.toFixed(2)}s)` : ''}`,
              source: 'bg-o3-done',
            });
            return;
          }
          if (res.data.status === 'failed') {
            failedBeatIds.push(beatId);
            if (res.data.beat) beatPatches.push(res.data.beat as BgBeat);
            pushToast({
              kind: 'error',
              message: `${beatId}: O3 voice job failed: ${formatO3JobFailure(res.data.error)}`,
              source: 'bg-o3-error',
            });
            return;
          }
          anyStillRunning = true;
          return;
        }
        if (isNetworkPollBlip(res)) {
          anyStillRunning = true;
          return;
        }
        if (isStaleO3JobPoll(res)) {
          staleBeatIds.push(beatId);
          return;
        }
        failedBeatIds.push(beatId);
        pushToast({ kind: 'error', message: `O3 poll error: ${res.error}`, source: 'bg-o3-poll-error' });
      }));
      if (cancelled) return;

      if (completedBeatIds.length > 0 || failedBeatIds.length > 0 || staleBeatIds.length > 0) {
        setActiveO3Jobs((prev) => {
          const next = { ...prev };
          for (const beatId of [...completedBeatIds, ...failedBeatIds, ...staleBeatIds]) {
            delete next[beatId];
          }
          return next;
        });
        setO3IntentByBeat((prev) => {
          const next = { ...prev };
          for (const beatId of [...completedBeatIds, ...failedBeatIds, ...staleBeatIds]) {
            delete next[beatId];
          }
          return next;
        });
        if (beatPatches.length > 0) {
          setBeats((bs) => beatPatches.reduce((acc, patch) => mergeBeatFromO3Poll(acc, patch), bs));
        } else {
          void refreshState();
        }
      }
      if (!anyStillRunning) {
        return;
      }
      timer = window.setTimeout(poll, O3_POLL_INTERVAL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [activeO3Jobs]);

  // After server restart, drop stale poll ids once sidecar reloads.
  useEffect(() => {
    if (serverRehydrateTick.value <= 0) return;
    void refreshState();
  }, [serverRehydrateTick.value]);

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
    const stateRes = await apiGet<BgSessionState>(
      'bg_session_state',
      bgSessionStateQuery(activeScope.value.event_id, activeTargetVideo.value),
      { fetchTimeoutMs: BG_SESSION_STATE_FETCH_TIMEOUT_MS },
    );
    if (stateRes.ok && stateRes.data) {
      const nextBeats = applyPromptEditsToBeats(stateRes.data.beats ?? []);
      setBeats(nextBeats);
      notifyNewGenFailures(nextBeats, genFailureToastRef);
      const liveIds = new Set(nextBeats.map((b) => b.beat_id));
      beatSaveBlockedRef.current.forEach((id) => {
        if (liveIds.has(id)) beatSaveBlockedRef.current.delete(id);
      });
      setActiveJobId((prev) => prev ?? collectActiveStillJobFromBeats(nextBeats));
      setActiveO3Jobs(collectActiveO3JobsFromBeats(nextBeats));
      setActiveNativeLipSyncJobs(collectActiveNativeLipSyncJobsFromBeats(nextBeats));
    }
  };

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      if (e.data?.type === 'mn-magic-or-animate-complete') {
        void refreshState();
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, []);

  const handleBeatMissingOnSave = useCallback(async (beatId: string) => {
    beatSaveBlockedRef.current.add(beatId);
    setBeats((bs) => bs.filter((b) => b.beat_id !== beatId));
    if (!beatSaveNotFoundToastRef.current.has(beatId)) {
      beatSaveNotFoundToastRef.current.add(beatId);
      pushToast({
        kind: 'warning',
        message: beatMissingToastMessage(beatId),
        source: 'bg-beat-missing',
        ttlMs: BEAT_MISSING_TOAST_MS,
      });
    }
    await refreshState();
  }, [activeScope.value.event_id, activeTargetVideo.value]);

  const guardBeatPatchResult = useCallback(async (
    beatId: string,
    result: Pick<ApiResult, 'ok' | 'error' | 'error_code'>,
    errorMessage: string,
    source: string,
  ): Promise<boolean> => {
    if (result.ok) return true;
    if (isBeatNotFoundResult(result)) {
      await handleBeatMissingOnSave(beatId);
      return false;
    }
    pushToast({ kind: 'error', message: errorMessage, source });
    return false;
  }, [handleBeatMissingOnSave]);

  // ----------------------------------------------------------------
  // Mutations
  // ----------------------------------------------------------------

  const onSelectSegment = async (combined: string) => {
    if (!combined) return;
    const [event_id, phase] = combined.split('|');
    const targetRole = videoRoleForBgPhase(phase);
    if (targetRole && targetRole !== activeTargetVideo.value) {
      const roleRes = await setActiveVideoRole(targetRole);
      if (!roleRes.ok) {
        pushToast({
          kind: 'error',
          message: `Video switch failed: ${roleRes.error ?? 'unknown error'}`,
          source: 'bg-segment-video-role',
        });
        return;
      }
      setActiveSegment(combined);
      // activeTargetVideo change re-fires fetchData via useEffect — beats reload cleanly.
      return;
    }
    setActiveSegment(combined);
    const result = await pathappPatch(activeScope.value, 'bg_set_active_context', {
      arc_number: arcNumber, event_id, phase,
    });
    if (!result.ok) {
      pushToast({ kind: 'error', message: `Set context failed: ${result.error}`, source: 'bg-set-context' });
    }
    await refreshState();
  };

  const openBeatPlanDraft = async (): Promise<boolean> => {
    if (!activeSegment) {
      pushToast({ kind: 'info', message: 'Select a segment first.', source: 'bg-review-plan' });
      return false;
    }
    const [event_id, phase] = activeSegment.split('|');
    const draftRes = await apiGet<{
      story_summary?: string;
      beats_plan?: BeatPlanRow[];
      beat_plan_draft?: { story_summary?: string; beats_plan?: BeatPlanRow[] };
      reconstructed_from_beats?: boolean;
    }>('bg_extract_beats_draft', {
      arc_number: String(arcNumber),
      event_id,
      phase,
      scope_event_id: activeScope.value.event_id,
      scope_video_role: activeTargetVideo.value,
    });
    if (!draftRes.ok) {
      pushToast({
        kind: 'error',
        message: `Could not load saved plan: ${draftRes.error_message || draftRes.error || 'unknown error'}`,
        source: 'bg-review-plan-error',
      });
      return false;
    }
    const rows = draftRes.data?.beats_plan
      ?? draftRes.data?.beat_plan_draft?.beats_plan
      ?? [];
    if (rows.length === 0) {
      pushToast({
        kind: 'info',
        message: 'No saved plan for this segment — run Extract Beats from script first.',
        source: 'bg-review-plan-empty',
      });
      return false;
    }
    setBeatPlanSummary(draftRes.data?.story_summary ?? '');
    setBeatPlanRows(rows);
    setBeatPlanDraftSaveStatus('saved');
    setBeatPlanOpen(true);
    if (draftRes.data?.reconstructed_from_beats) {
      pushToast({
        kind: 'info',
        message: 'Rebuilt plan from current beats — edit and Approve to re-run Kling author.',
        source: 'bg-review-plan-reconstructed',
      });
    }
    return true;
  };

  const onExtractBeats = async () => {
    if (!activeSegment) return;
    const [event_id, phase] = activeSegment.split('|');
    const draftRes = await apiGet<{ beats_plan?: BeatPlanRow[] }>('bg_extract_beats_draft', {
      arc_number: String(arcNumber),
      event_id,
      phase,
      scope_event_id: activeScope.value.event_id,
      scope_video_role: activeTargetVideo.value,
    });
    const existingCount = draftRes.data?.beats_plan?.length ?? 0;
    if (draftRes.ok && existingCount > 0) {
      setModalState({ kind: 'extract-overwrite-confirm', beatCount: existingCount });
      return;
    }
    await runExtractBeatsPlan(event_id, phase);
  };

  const runExtractBeatsPlan = async (event_id: string, phase: string) => {
    setExtractStatus('sending');
    setExtractError(null);
    const result = await pathappPatch<{
      story_summary?: string;
      beats_plan?: BeatPlanRow[];
      model_used?: string;
      generation_time_ms?: number;
    }>(
      activeScope.value, 'bg_extract_beats_plan', { arc_number: arcNumber, event_id, phase },
    );
    setExtractStatus('idle');
    const planRows = result.data?.beats_plan ?? [];
    if (result.ok && result.data && planRows.length > 0) {
      setExtractError(null);
      setBeatPlanSummary(result.data.story_summary ?? '');
      setBeatPlanRows(planRows);
      setBeatPlanDraftSaveStatus('saved');
      setBeatPlanOpen(true);
      pushToast({
        kind: 'success',
        message: `Planned ${planRows.length} beats — review and Approve`,
        source: 'bg-extract-plan',
      });
    } else if (planRows.length > 0) {
      setExtractError(null);
      setBeatPlanSummary(result.data?.story_summary ?? '');
      setBeatPlanRows(planRows);
      setBeatPlanDraftSaveStatus('saved');
      setBeatPlanOpen(true);
      pushToast({
        kind: 'info',
        message: `Planned ${planRows.length} beats — draft save had an issue; review and Approve`,
        source: 'bg-extract-plan-partial',
      });
    } else if (await openBeatPlanDraft()) {
      setExtractError(null);
      pushToast({
        kind: 'info',
        message: 'Showing saved plan from last Extract — edit and Approve',
        source: 'bg-extract-draft',
      });
    } else {
      const msg = result.error_message || result.error || 'Unknown error';
      setExtractError(msg);
      pushToast({ kind: 'error', message: `Extract failed: ${msg}`, source: 'bg-extract-error' });
    }
  };

  const confirmExtractOverwrite = async () => {
    if (!activeSegment || modalState.kind !== 'extract-overwrite-confirm') return;
    const [event_id, phase] = activeSegment.split('|');
    closeModal();
    await runExtractBeatsPlan(event_id, phase);
  };

  const onBeatPlanAutosave = useCallback(async (storySummary: string, beatsPlan: BeatPlanRow[]) => {
    if (!activeSegment) return;
    const [event_id, phase] = activeSegment.split('|');
    setBeatPlanDraftSaveStatus('saving');
    const result = await pathappPatch<{
      beats_plan?: BeatPlanRow[];
      saved_at?: string;
      count?: number;
    }>(
      activeScope.value,
      'bg_extract_beats_draft_save',
      {
        arc_number: arcNumber,
        event_id,
        phase,
        story_summary: storySummary,
        beats_plan: beatsPlan,
        source: 'modal_autosave',
      },
    );
    if (result.ok) {
      setBeatPlanDraftSaveStatus('saved');
      return;
    }
    setBeatPlanDraftSaveStatus('error');
  }, [activeSegment, arcNumber, activeScope.value, activeTargetVideo.value]);

  const closeBeatPlanModal = () => {
    setBeatPlanOpen(false);
    setApproveStatus('idle');
    setApproveStartedAt(null);
    setBeatPlanDraftSaveStatus('idle');
  };

  const onApproveBeatPlan = async (storySummary: string, beatsPlan: BeatPlanRow[]) => {
    if (!activeSegment) return;
    const [event_id, phase] = activeSegment.split('|');
    setApproveStatus('sending');
    setApproveStartedAt(Date.now());
    try {
      const result = await pathappPatch<{
        beats: BgBeat[];
        count: number;
        kling_author_applied?: boolean;
        author_audit?: string[];
        message?: string;
      }>(
        activeScope.value, 'bg_extract_beats_approve', {
          arc_number: arcNumber, event_id, phase, story_summary: storySummary, beats_plan: beatsPlan,
        },
        { fetchTimeoutMs: 600_000 },
      );
      if (result.ok && result.data) {
        setBeats(applyPromptEditsToBeats(result.data.beats ?? []));
        setBeatPlanOpen(false);
        pushToast({
          kind: 'success',
          message: (
            `Populated ${result.data.count ?? 0} beats — each beat card shows the full `
            + `Kling O3 prompt (editable; what you see is what submits)`
          ),
          source: 'bg-extract-approve',
        });
      } else if (isNetworkPollBlip(result)) {
        pushToast({
          kind: 'error',
          message: formatMutationError(result, 'Approve beat plan'),
          source: 'bg-approve-error',
        });
      } else if (
        Array.isArray((result.data as { author_audit?: string[] } | undefined)?.author_audit)
        && ((result.data as { author_audit?: string[] }).author_audit?.length ?? 0) > 0
      ) {
        const audit = (result.data as { author_audit: string[] }).author_audit;
        const detail = audit.slice(0, 2).join('; ');
        pushToast({
          kind: 'error',
          message: `Approve failed — Kling author pass did not stick (${detail})`,
          source: 'bg-approve-error',
        });
      } else {
        pushToast({
          kind: 'error',
          message: formatMutationError(result, 'Approve beat plan'),
          source: 'bg-approve-error',
        });
      }
    } catch (err) {
      pushToast({
        kind: 'error',
        message: formatMutationError(
          { ok: false, status: 0, error: err instanceof Error ? err.message : String(err) },
          'Approve beat plan',
        ),
        source: 'bg-approve-error',
      });
    } finally {
      setApproveStatus('idle');
      setApproveStartedAt(null);
    }
  };

  const openInsertBeatModal = (afterBeatId: string) => {
    setInsertAfterBeatId(afterBeatId);
    setInsertError('');
    setInsertModalOpen(true);
  };

  const closeInsertBeatModal = () => {
    if (insertSubmitting) return;
    setInsertModalOpen(false);
    setInsertError('');
  };

  const executeInsertBeat = async (planRow: InsertBeatPlanRow) => {
    if (!activeSegment) return;
    const [event_id, phase] = activeSegment.split('|');
    setInsertSubmitting(true);
    setInsertError('');
    const result = await pathappPatch<{ beat?: BgBeat; beat_id?: string }>(
      activeScope.value,
      'bg_insert_beat',
      {
        after_beat_id: insertAfterBeatId,
        segment: `event_${event_id}_${phase}`,
        plan_row: planRow,
      },
    );
    setInsertSubmitting(false);
    if (result.ok && result.data?.beat) {
      const newBeat = result.data.beat;
      setBeats((bs) => {
        if (bs.some((b) => b.beat_id === newBeat.beat_id)) return bs;
        const idx = bs.findIndex((b) => b.beat_id === insertAfterBeatId);
        const next = [...bs];
        next.splice(idx >= 0 ? idx + 1 : next.length, 0, newBeat);
        return next;
      });
      pushToast({ kind: 'info', message: `Inserted ${newBeat.beat_id}`, source: 'bg-insert' });
      setInsertModalOpen(false);
      await refreshState();
    } else {
      const msg = formatMutationError(result, 'Insert beat failed');
      setInsertError(msg);
      pushToast({ kind: 'error', message: msg, source: 'bg-insert-error' });
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

  const onUpdateBeatText = async (beatId: string, nextText: string): Promise<boolean> => {
    if (beatSaveBlockedRef.current.has(beatId)) return false;
    const result = await pathappPatch<{
      ok: boolean;
      element_char_ref_ok?: boolean;
      element_char_ref_error?: string | null;
      element_ref_warning?: string | null;
    }>(activeScope.value, 'bg_update_beat', {
      beat_id: beatId, kling_o3_prompt: nextText,
    });
    if (!result.ok) {
      const err = (result.error || '').trim();
      if (isBeatNotFoundResult(result)) {
        await handleBeatMissingOnSave(beatId);
        return false;
      }
      const msg = /failed to fetch|networkerror|load failed/i.test(err)
        ? 'Save failed — server was restarting. Wait for “server is back”, then click Generate again (your text is still in the box).'
        : `Save failed: ${result.error}`;
      pushToast({ kind: 'error', message: msg, source: 'bg-update-text' });
      return false;
    }
    setBeats((bs) => bs.map((b): BgBeat => {
      if (b.beat_id !== beatId) return b;
      const next: BgBeat = { ...b, kling_o3_prompt: nextText };
      if (nextText.trim()) next.o3_prompt_box_law = true;
      else delete next.o3_prompt_box_law;
      return next;
    }));
    if (result.data && typeof result.data.element_char_ref_ok === 'boolean') {
      const gateOk = result.data.element_char_ref_ok;
      const gateErr = result.data.element_char_ref_error ?? null;
      setBeats((bs) => bs.map((b): BgBeat => {
        if (b.beat_id !== beatId) return b;
        const next: BgBeat = { ...b, element_char_ref_ok: gateOk };
        if (gateErr) next.element_char_ref_error = gateErr;
        else delete next.element_char_ref_error;
        return next;
      }));
    }
    return true;
  };

  // Speaker dropdown handler (LD CHARACTER_DROPDOWN_RESTORED_V1).
  // BG already accepts `speaker` field on bg_update_beat — see
  // production_server.py _BG_BEAT_WRITABLE (line ~9937). Optimistic local
  // update so the dropdown reflects the new value before refreshState()
  // (matches the 2026-05-11 Rule 26 fix pattern for ref-image drops).
  const onPatchRefImageForBeat = (
    beatId: string,
    refField: 'reference_image' | 'bg_ref_image',
    patch: { key?: string; abs_path?: string; thumb_b64?: string } | null,
  ) => {
    setBeats((bs) => bs.map((b): BgBeat => {
      if (b.beat_id !== beatId) return b;
      return { ...b, [refField]: patch };
    }));
  };

  const onUpdateBeatSpeaker = async (beatId: string, nextSpeaker: string) => {
    if (beatSaveBlockedRef.current.has(beatId)) return;
    setBeats((bs) => bs.map((b) => (
      b.beat_id === beatId ? { ...b, speaker: nextSpeaker } : b
    )));
    const result = await pathappPatch<{
      ok: boolean;
      element_char_ref_ok?: boolean;
      element_char_ref_error?: string | null;
    }>(activeScope.value, 'bg_update_beat', {
      beat_id: beatId, speaker: nextSpeaker,
    });
    if (result.ok) {
      const gateOk = result.data?.element_char_ref_ok;
      const gateErr = result.data?.element_char_ref_error ?? null;
      if (typeof gateOk === 'boolean') {
        setBeats((bs) => bs.map((b): BgBeat => {
          if (b.beat_id !== beatId) return b;
          const next: BgBeat = { ...b, element_char_ref_ok: gateOk };
          if (gateErr) next.element_char_ref_error = gateErr;
          else delete next.element_char_ref_error;
          return next;
        }));
      }
      await refreshState();
    }
    await guardBeatPatchResult(
      beatId,
      result,
      `Speaker save failed: ${result.error}`,
      'bg-update-speaker',
    );
  };

  const onSetBeatPipeline = async (beatId: string, pipeline: 'still_insert' | 'kling_o3_omni') => {
    if (beatSaveBlockedRef.current.has(beatId)) return;
    const beat = beats.find((b) => b.beat_id === beatId);
    if (!beat || !isPipelineToggleable(beat)) return;
    const priorMode = isStillInsertBeat(beat) ? 'still_insert' : 'kling_o3_omni';
    if (priorMode === pipeline) return;
    setBeats((bs) => bs.map((b): BgBeat => {
      if (b.beat_id !== beatId) return b;
      if (pipeline === 'still_insert') {
        return {
          ...b,
          pipeline: 'still_insert',
          beat_render_mode: 'still_insert',
        };
      }
      const next: BgBeat = { ...b, pipeline: 'kling_o3_omni' };
      delete next.beat_render_mode;
      return next;
    }));
    const result = await pathappPatch<{
      ok: boolean;
      pipeline?: string;
      beat_render_mode?: string;
      beat_type?: string;
      kling_o3_prompt?: string;
      element_char_ref_ok?: boolean;
      element_char_ref_error?: string | null;
      changed?: boolean;
    }>(activeScope.value, 'bg_set_pipeline', {
      beat_id: beatId,
      pipeline,
    });
    if (result.ok && result.data) {
      setBeats((bs) => bs.map((b): BgBeat => {
        if (b.beat_id !== beatId) return b;
        const next: BgBeat = { ...b };
        if (result.data?.pipeline) next.pipeline = result.data.pipeline;
        if (result.data?.beat_render_mode) {
          next.beat_render_mode = result.data.beat_render_mode;
        } else {
          delete next.beat_render_mode;
        }
        if (result.data?.kling_o3_prompt) {
          next.kling_o3_prompt = result.data.kling_o3_prompt;
        }
        if (typeof result.data?.element_char_ref_ok === 'boolean') {
          next.element_char_ref_ok = result.data.element_char_ref_ok;
          if (result.data.element_char_ref_error) {
            next.element_char_ref_error = result.data.element_char_ref_error;
          } else {
            delete next.element_char_ref_error;
          }
        }
        return next;
      }));
      pushToast({
        kind: 'success',
        message: pipeline === 'still_insert'
          ? 'Pipeline: Still + TTS — Generate builds Ken Burns still with dialogue audio.'
          : 'Pipeline: O3 Kling — Generate submits padded O3 voice video.',
        source: 'bg-set-pipeline',
      });
      await refreshState();
    }
    await guardBeatPatchResult(
      beatId,
      result,
      `Pipeline switch failed: ${result.error}`,
      'bg-set-pipeline-error',
    );
  };

  const onAlignElementRef = async (beatId: string) => {
    if (beatSaveBlockedRef.current.has(beatId)) return;
    const beat = beats.find((b) => b.beat_id === beatId);
    const result = await pathappPatch<{
      ok: boolean;
      aligned?: boolean;
      reference_image?: BgBeat['reference_image'];
      thumb_b64?: string;
      element_char_ref_ok?: boolean;
      element_char_ref_error?: string | null;
    }>(activeScope.value, 'bg_align_element_ref', { beat_id: beatId });
    if (!result.ok) {
      if (isBeatNotFoundResult(result)) {
        await handleBeatMissingOnSave(beatId);
        return;
      }
      pushToast({
        kind: 'error',
        message: result.error ?? 'Could not align char ref to Element pose',
        source: 'bg-align-element-ref-error',
      });
      return;
    }
    const data = result.data;
    if (data?.reference_image) {
      onPatchRefImageForBeat(beatId, 'reference_image', {
        ...data.reference_image,
        ...(data.thumb_b64 ? { thumb_b64: data.thumb_b64 } : {}),
      });
    }
    const gateOk = data?.element_char_ref_ok;
    if (typeof gateOk === 'boolean') {
      setBeats((bs) => bs.map((b): BgBeat => {
        if (b.beat_id !== beatId) return b;
        const next: BgBeat = { ...b, element_char_ref_ok: gateOk };
        const gateErr = data?.element_char_ref_error ?? null;
        if (gateErr) next.element_char_ref_error = gateErr;
        else delete next.element_char_ref_error;
        return next;
      }));
    }
    if (gateOk) {
      pushToast({
        kind: 'success',
        message: `Char ref aligned to Element pose for ${beat?.speaker ?? 'speaker'}`,
        source: 'bg-align-element-ref',
      });
    } else {
      pushToast({
        kind: 'warning',
        message: data?.element_char_ref_error
          ?? 'Element pose alignment did not pass gate — check speaker registration',
        source: 'bg-align-element-ref-warn',
        ttlMs: 14000,
      });
    }
    await refreshState();
  };

  const onAddElementPose = async (beatId: string) => {
    if (beatSaveBlockedRef.current.has(beatId)) return;
    const beat = beats.find((b) => b.beat_id === beatId);
    const result = await pathappPatch<{
      ok: boolean;
      pose_rel?: string;
      element_id?: string;
      element_char_ref_ok?: boolean;
      element_char_ref_error?: string | null;
    }>(activeScope.value, 'bg_add_element_pose', { beat_id: beatId });
    if (!result.ok) {
      if (isBeatNotFoundResult(result)) {
        await handleBeatMissingOnSave(beatId);
        return;
      }
      pushToast({
        kind: 'error',
        message: result.error ?? 'Could not add pose to Element',
        source: 'bg-add-element-pose-error',
      });
      return;
    }
    const data = result.data;
    const gateOk = data?.element_char_ref_ok;
    if (typeof gateOk === 'boolean') {
      setBeats((bs) => bs.map((b): BgBeat => {
        if (b.beat_id !== beatId) return b;
        const next: BgBeat = { ...b, element_char_ref_ok: gateOk };
        const gateErr = data?.element_char_ref_error ?? null;
        if (gateErr) next.element_char_ref_error = gateErr;
        else delete next.element_char_ref_error;
        return next;
      }));
    }
    pushToast({
      kind: 'success',
      message: `Pose registered on ${beat?.speaker ?? 'speaker'} Element`
        + (data?.pose_rel ? ` (${data.pose_rel})` : ''),
      source: 'bg-add-element-pose',
    });
    await refreshState();
  };

  const onSetReplaceSlot = async (beatId: string, slotIndex: number) => {
    if (beatSaveBlockedRef.current.has(beatId)) return;
    setBeats((prev) => prev.map((b) => (
      b.beat_id === beatId ? { ...b, kling_o3_replace_slot_index: slotIndex } : b
    )));
    const result = await pathappPatch(activeScope.value, 'bg_update_beat', {
      beat_id: beatId,
      kling_o3_replace_slot_index: slotIndex,
    });
    await guardBeatPatchResult(
      beatId,
      result,
      `Replace slot save failed: ${result.error}`,
      'bg-replace-slot',
    );
  };

  const onRenderStillClip = async (beatId: string, dialogueText?: string) => {
    if (activeStillRenderJobs[beatId]) {
      pushToast({ kind: 'info', message: 'Still clip is already rendering.', source: 'bg-still-clip-busy' });
      return;
    }
    const beat = beats.find((b) => b.beat_id === beatId);
    const pendingPrompt = (dialogueText ?? '').trim();
    if (pendingPrompt) {
      const saved = await onUpdateBeatText(beatId, dialogueText!);
      if (!saved) return;
    }
    setActiveStillRenderJobs((prev) => ({ ...prev, [beatId]: true }));
    const result = await pathappPatch<StillClipRenderResponse>(
      activeScope.value,
      'bg_render_still_clip',
      {
        beat_id: beatId,
        method: 'ken_burns',
        slot_index: beat?.kling_o3_replace_slot_index ?? 0,
        ...(pendingPrompt ? { kling_o3_prompt: pendingPrompt } : {}),
      },
    );
    setActiveStillRenderJobs((prev) => {
      const next = { ...prev };
      delete next[beatId];
      return next;
    });
    if (result.ok && result.data) {
      const ttsMixed = !!result.data?.tts_mixed;
      const ttsErr = (result.data?.tts_error || '').trim();
      const ttsRegen = !!result.data?.tts_regenerated;
      const ttsOk = result.data?.tts_ok !== false && !ttsErr;
      let message = 'Still clip rebuilt — trim below, then Approve still for stitch.';
      if (ttsMixed && ttsRegen) {
        message = 'Still clip rebuilt with fresh TTS — trim below, then Approve still for stitch.';
      } else if (ttsMixed && result.data?.tts_unchanged) {
        message = 'Still clip rebuilt (TTS unchanged — edit prompt line to regen audio) — trim below.';
      } else if (ttsErr) {
        message = `Still clip rebuilt without audio (${ttsErr}) — trim below.`;
      }
      pushToast({
        kind: ttsOk && ttsMixed ? 'success' : (result.data?.ok ? 'info' : 'error'),
        message,
        source: 'bg-still-clip',
      });
      await refreshState();
    } else if (isBeatNotFoundResult(result)) {
      await handleBeatMissingOnSave(beatId);
    } else {
      pushToast({ kind: 'error', message: `Still clip failed: ${result.error}`, source: 'bg-still-clip-error' });
    }
  };

  const handleO3SubmitResult = async (
    beatId: string,
    beat: BgBeat,
    result: Awaited<ReturnType<typeof pathappPatch<ArloO3SubmitResponse>>>,
  ): Promise<boolean> => {
    if (result.ok && result.data?.job_id) {
      setActiveO3Jobs((prev) => ({ ...prev, [beatId]: result.data!.job_id! }));
      if (result.data.intent) {
        setO3IntentByBeat((prev) => ({ ...prev, [beatId]: result.data!.intent! }));
      }
      if (result.data.submitted) {
        setO3SubmitAuditByBeat((prev) => ({ ...prev, [beatId]: result.data!.submitted! }));
      }
      const slot = result.data.generation_slot ?? result.data.submitted?.generation_slot;
      const mode = result.data.o3_generate_mode;
      const modeLabel = mode === 'voice_first' ? 'ElevenLabs voice-first' : 'Element native O3';
      pushToast({
        kind: 'info',
        message: result.data.deduped
          ? 'This beat already has an O3 voice job running; reattached to the existing job.'
          : `Submitted ${beat.speaker} ${modeLabel}${slot ? ` (${slot})` : ''} — prompt locked until job finishes`,
        source: 'bg-o3-submit',
      });
      return true;
    }
    if (result.error_code === 'VOICE_BIND_DRIFT' && result.retry_safe !== false) {
      setModalState({
        kind: 'voice-drift-confirm',
        beatId,
        promptToSave: (beat.kling_o3_prompt ?? '').trim(),
        replaceSlotIndex: beat.kling_o3_replace_slot_index ?? 0,
        referenceImage: beat.reference_image ?? null,
        bgRefImage: beat.bg_ref_image ?? null,
        message: result.error ?? result.error_message ?? 'Registry voice differs from this beat\'s last approved bind.',
      });
      return false;
    }
    return guardBeatPatchResult(
      beatId,
      result,
      `O3 submit failed: ${result.error}`,
      'bg-o3-submit-error',
    );
  };

  const beatForO3Submit = (beatId: string, beat: BgBeat): BgBeat => (
    beatsRef.current.find((b) => b.beat_id === beatId) ?? beat
  );

  const submitO3Voice = async (
    beatId: string,
    beat: BgBeat,
    promptToSave: string,
    acceptVoiceDrift = false,
  ): Promise<boolean> => {
    const refBeat = beatForO3Submit(beatId, beat);
    const result = await pathappPatch<ArloO3SubmitResponse>(
      activeScope.value, 'bg_submit_arlo_o3_voice', {
        beat_id: beatId,
        kling_o3_prompt: promptToSave,
        model: 'pro',
        replace_slot_index: refBeat.kling_o3_replace_slot_index ?? 0,
        reference_image: refBeat.reference_image ?? null,
        bg_ref_image: refBeat.bg_ref_image ?? null,
        ...(acceptVoiceDrift ? { accept_voice_drift: true } : {}),
      },
    );
    return handleO3SubmitResult(beatId, refBeat, result);
  };

  const confirmVoiceDriftSubmit = async () => {
    if (modalState.kind !== 'voice-drift-confirm') return;
    const { beatId, promptToSave, replaceSlotIndex, referenceImage, bgRefImage } = modalState;
    closeModal();
    const beat = beatsRef.current.find((b) => b.beat_id === beatId)
      ?? beats.find((b) => b.beat_id === beatId);
    if (!beat) return;
    const workBeat: BgBeat = {
      ...beat,
      kling_o3_prompt: promptToSave,
      kling_o3_replace_slot_index: replaceSlotIndex,
      reference_image: referenceImage ?? beat.reference_image ?? null,
      bg_ref_image: bgRefImage ?? beat.bg_ref_image ?? null,
    };
    await submitO3Voice(beatId, workBeat, promptToSave, true);
  };

  const onGenerateBatch = async (beatId: string, dialogueText?: string) => {
    const beat = beats.find((b) => b.beat_id === beatId);
    if (!beat) return;
    if (isStillInsertBeat(beat)) {
      await onRenderStillClip(beatId, dialogueText);
      return;
    }
    if (activeO3Jobs[beatId]) {
      pushToast({ kind: 'info', message: 'This beat is already generating.', source: 'bg-o3-beat-busy' });
      return;
    }
    if (isO3VoiceBeat(beat)) {
      if (beat.element_char_ref_ok === false) {
        pushToast({
          kind: 'error',
          message: beat.element_char_ref_error ?? 'Char ref must match Element pose images before O3 generate.',
          source: 'bg-element-ref-block',
        });
        return;
      }
      const promptToSave = (dialogueText ?? '').trim();
      if (!promptToSave) {
        pushToast({
          kind: 'error',
          message: 'Prompt box is empty — type the full O3 prompt before Generate.',
          source: 'bg-o3-empty-prompt',
        });
        return;
      }
      const saved = await onUpdateBeatText(beatId, promptToSave);
      if (!saved) return;
      await submitO3Voice(beatId, beatForO3Submit(beatId, beat), promptToSave);
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
      await guardBeatPatchResult(
        beatId,
        result,
        `Native lipsync submit failed: ${result.error}`,
        'bg-native-lipsync-submit-error',
      );
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
    const currentText = beatPromptText(beat);
    const oldEsc = oldChipText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`\\(${oldEsc}\\)`);
    const nextText = currentText.replace(re, `(${trimmed})`);
    if (nextText === currentText) {
      pushToast({
        kind: 'error',
        message: `Could not locate chip "${oldChipText}" in prompt`,
        source: 'bg-chip-edit-miss',
      });
      return;
    }
    setBeats((bs) => bs.map((b) => (b.beat_id === beatId ? { ...b, kling_o3_prompt: nextText } : b)));
    const result = await pathappPatch(activeScope.value, 'bg_update_beat', {
      beat_id: beatId,
      kling_o3_prompt: nextText,
    });
    if (!await guardBeatPatchResult(
      beatId,
      result,
      `Chip edit save failed: ${result.error}`,
      'bg-chip-edit-error',
    )) {
      return;
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
    } else if (!(await guardBeatPatchResult(
      beatId,
      result,
      `${label} remove failed: ${result.error}`,
      'bg-ref-remove-error',
    ))) {
      await refreshState();
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
      await guardBeatPatchResult(
        beatId,
        result,
        `Lock failed: ${result.error}`,
        'bg-accept-opt-error',
      );
    }
  };

  const onSelectO3Video = async (beatId: string, optionKey: string, opts?: { stillApprove?: boolean }) => {
    const result = await pathappPatch(activeScope.value, 'bg_select_o3_video', {
      beat_id: beatId, option_key: optionKey,
    });
    if (result.ok) {
      pushToast({
        kind: 'success',
        message: opts?.stillApprove
          ? 'Still clip approved for stitch export'
          : 'Selected preserved O3 video',
        source: 'bg-select-o3',
      });
      await refreshState();
    } else {
      await guardBeatPatchResult(
        beatId,
        result,
        formatMutationError(result, 'Select O3 video failed'),
        'bg-select-o3-error',
      );
    }
  };

  const onApplyO3Trim = async (beatId: string, trimStart: number, trimBack: number | null, clear = false) => {
    const result = await pathappPatch<{
      trim_start?: number;
      trim_back?: number | null;
      trim_end?: number;
      raw_duration_s?: number;
      effective_duration_s?: number | null;
      preview_video_url?: string;
      trim_baked?: boolean;
      video_path?: string;
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
            ...(result.data?.video_path ? { kling_o3_video_path: result.data.video_path } : {}),
            ...(result.data?.trim_baked && result.data?.video_path
              ? {
                kling_o3_options: (b.kling_o3_options ?? []).map((o) => (
                  o?.video_path === b.kling_o3_video_path
                    ? { ...o, video_path: result.data!.video_path! }
                    : o
                )),
              }
              : {}),
          }
          : b
      )));
      const dur = result.data?.effective_duration_s;
      pushToast({
        kind: 'success',
        message: clear
          ? 'Trim cleared — full clip restored for export (switch O3 option separately if needed)'
          : result.data?.trim_baked
            ? (dur != null
              ? `Trim baked into clip (${dur.toFixed(1)}s) — audio/video updated in place`
              : 'Trim baked into clip — audio/video updated in place')
            : (dur != null
              ? `Trim saved — ${dur.toFixed(2)}s effective (back ${result.data?.trim_back ?? 0}s)`
              : 'Trim saved'),
        source: 'bg-o3-trim',
      });
      if (result.data?.trim_baked || result.data?.video_path) {
        await refreshState();
      }
      const preview = result.data?.preview_video_url;
      const previewUrl = preview
        ? (preview.startsWith('http') ? preview : `${SERVER_BASE}${preview}`)
        : undefined;
      const rawDurationS = result.data?.raw_duration_s;
      return {
        ...(previewUrl !== undefined ? { previewUrl } : {}),
        ...(rawDurationS !== undefined ? { rawDurationS } : {}),
      };
    }
    await guardBeatPatchResult(
      beatId,
      result,
      formatMutationError(result, 'Trim failed'),
      'bg-o3-trim-error',
    );
    return undefined;
  };

  // BG-34/35 — Accept All warn modal (lists unset beats) + confirm modal
  // (Lock in N selections...). Replaces direct mutation; gates on user
  // acknowledgement of unset beats per Kim 2026-05-06 lock.
  const segmentCtx = () => {
    const [event_id, phase] = (activeSegment || '1|pre').split('|');
    return { event_id, phase };
  };

  const isVoiceFirstSegment = useMemo(() => {
    const { event_id, phase } = segmentCtx();
    return event_id === '2' && phase === 'pre';
  }, [activeSegment]);

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
      { fetchTimeoutMs: 600_000 },
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
        {isVoiceFirstSegment ? (
          <span class="mn-scope-chip" data-testid="bg-voice-first-badge" title="Generate uses ElevenLabs TTS + silent O3 + lipsync (720 delivery)">
            Voice: ElevenLabs
          </span>
        ) : null}
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
            <><Spinner size="sm" inline /> Reading skeleton…</>
          ) : '+ Extract Beats from script'}
        </button>
        <button
          type="button"
          class="mn-btn"
          data-testid="bg-review-draft-btn"
          onClick={() => { void openBeatPlanDraft(); }}
          disabled={!activeSegment}
        >
          Review saved plan
        </button>
        <button
          type="button"
          class="mn-btn"
          data-testid="bg-insert-btn"
          onClick={() => {
            const lastId = beats.length > 0 ? beats[beats.length - 1].beat_id : '';
            openInsertBeatModal(lastId);
          }}
          disabled={!activeSegment || insertSubmitting}
        >
          + Insert beat
        </button>
        <span class="mn-bg-cost" data-testid="bg-cost">
          Cost this session:{' '}
          <span class="mn-bg-cost-running">${runningCostUsd.toFixed(2)}</span>
          {' • '}This generation: ${lastBatchCostUsd.toFixed(2)}
        </span>
        {extractError ? (
          <p class="mn-bg-extract-error" data-testid="bg-extract-error" role="alert">
            Extract failed: {extractError}
          </p>
        ) : null}
      </div>

      {loading ? (
        <p class="mn-loading" data-testid="bg-loading">
          <Spinner size="md" inline /> Loading beat state…
          {loadingSlowHint ? (
            <span class="mn-loading-slow-hint">
              Still loading — server is busy reconciling sidecar while your WaveSpeed gens keep running.
            </span>
          ) : null}
        </p>
      ) : beats.length === 0 ? (
        <div class="mn-empty" data-testid="bg-empty">
          <p>No beats yet for this segment. Click <strong>Extract Beats from script</strong> or <strong>+ Insert beat</strong> to start.</p>
        </div>
      ) : (
        <div class="mn-bg-body-layout" data-testid="bg-body-layout">
          <BgBeatNav
            beats={beats}
            itemStatuses={beatNavItemStatuses}
            activeIndex={
              activeNavIndex !== null && activeNavIndex < beats.length
                ? activeNavIndex
                : null
            }
            onJump={(beatId, index) => {
              navJumpLockUntilRef.current = Date.now() + 1200;
              setActiveNavIndex(index);
              scrollToBeat(beatId);
            }}
          />
          <ol class="mn-bg-beat-list" data-testid="bg-beat-list">
          {beats.map((b, i) => (
            <BeatGenCard
              key={b.beat_id}
              index={i}
              beat={b}
              eventId={activeScope.value.event_id}
              videoRole={activeTargetVideo.value}
              pollResultForBeat={pollResults[b.beat_id]}
              busy={beatHasActiveNavJob(b, beatNavJobContext)}
              o3IntentSnapshot={o3IntentByBeat[b.beat_id]}
              o3SubmitAudit={o3SubmitAuditByBeat[b.beat_id]}
              o3WarningMessage={o3WarningByBeat[b.beat_id]}
              nativeExperimentBusy={!!activeNativeLipSyncJobs[b.beat_id]}
              onDelete={() => onDeleteBeat(b.beat_id)}
              onUpdateText={(t) => onUpdateBeatText(b.beat_id, t)}
              onUpdateSpeaker={(s) => onUpdateBeatSpeaker(b.beat_id, s)}
              onSetPipeline={(pipeline) => onSetBeatPipeline(b.beat_id, pipeline)}
              onGenerate={(dialogueText) => onGenerateBatch(b.beat_id, dialogueText)}
              onAccept={(optionKey) => onAcceptOption(b.beat_id, optionKey)}
              onSelectO3Video={(optionKey) => onSelectO3Video(b.beat_id, optionKey)}
              onApproveStill={(optionKey) => onSelectO3Video(b.beat_id, optionKey, { stillApprove: true })}
              onApplyO3Trim={(trimStart, trimBack, clear) => onApplyO3Trim(b.beat_id, trimStart, trimBack, clear)}
              onSetReplaceSlot={(slotIndex) => onSetReplaceSlot(b.beat_id, slotIndex)}
              onSubmitNativeLipSyncExperiment={() => onSubmitNativeLipSyncExperiment(b.beat_id)}
              onEditChip={(c) => requestEditChip(b.beat_id, c)}
              onInsertAfter={() => openInsertBeatModal(b.beat_id)}
              onRemoveRef={(refField, label) => requestRemoveRef(b.beat_id, refField, label)}
              onAlignElementRef={() => onAlignElementRef(b.beat_id)}
              onAddElementPose={() => onAddElementPose(b.beat_id)}
              onRefresh={() => refreshState()}
              onBeatMissing={handleBeatMissingOnSave}
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
                onPatchRefImageForBeat(b.beat_id, refField, patch);
              }}
            />
          ))}
          </ol>
        </div>
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

      {/* Beat plan approval modal (Claude extract Phase A → B) */}
      <BeatPlanModal
        open={beatPlanOpen}
        storySummary={beatPlanSummary}
        beatsPlan={beatPlanRows}
        approveStatus={approveStatus}
        approveStartedAt={approveStartedAt}
        draftSaveStatus={beatPlanDraftSaveStatus}
        onClose={closeBeatPlanModal}
        onApprove={onApproveBeatPlan}
        onAutosave={onBeatPlanAutosave}
      />

      <InsertBeatModal
        open={insertModalOpen}
        afterBeatId={insertAfterBeatId}
        submitting={insertSubmitting}
        errorMessage={insertError}
        onClose={closeInsertBeatModal}
        onSubmit={(planRow) => { void executeInsertBeat(planRow); }}
      />

      {/* Extract overwrite confirm — saved draft would be replaced by fresh Claude plan */}
      <Modal
        id="bg-extract-overwrite"
        title="Overwrite saved beat plan?"
        open={modalState.kind === 'extract-overwrite-confirm'}
        onClose={closeModal}
        footer={(
          <>
            <button type="button" class="mn-btn" data-testid="bg-extract-overwrite-cancel" onClick={closeModal}>
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="bg-extract-overwrite-confirm"
              onClick={() => { void confirmExtractOverwrite(); }}
            >
              Overwrite &amp; re-extract
            </button>
          </>
        )}
      >
        {modalState.kind === 'extract-overwrite-confirm' ? (
          <p>
            You already have a saved plan with{' '}
            <strong>{modalState.beatCount}</strong>
            {' '}
            beat{modalState.beatCount === 1 ? '' : 's'} for this segment.
            Running Extract again will replace it with a fresh auto-generated plan.
            Use <strong>Review saved plan</strong> if you want to keep editing your current draft.
          </p>
        ) : null}
      </Modal>

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

      {/* Voice bind drift — registry voice_id changed since this beat was last approved */}
      <Modal
        id="bg-voice-drift-confirm"
        title="Voice bind changed since last approval"
        open={modalState.kind === 'voice-drift-confirm'}
        onClose={closeModal}
        footer={(
          <>
            <button type="button" class="mn-btn" data-testid="bg-voice-drift-cancel" onClick={closeModal}>
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="bg-voice-drift-confirm"
              onClick={() => { void confirmVoiceDriftSubmit(); }}
            >
              Generate with current registry voice
            </button>
          </>
        )}
      >
        {modalState.kind === 'voice-drift-confirm' ? (
          <>
            <p>
              This beat was approved with an older Element voice bind. The character registry now
              points at a different <code>kling_voice_id</code>, so a redo may sound different
              (for Lorelai, the Beat 18 female stack is the current proven voice).
            </p>
            <p class="mn-muted" style={{ marginTop: '0.75rem' }}>
              {modalState.message}
            </p>
          </>
        ) : null}
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
// ----------------------------------------------------------------
// BgMagicStillPreview — silent magic_still + ElevenLabs TTS (Storyboard parity)
// ----------------------------------------------------------------

function BgMagicStillPreview({
  index,
  videoUrl,
  storyboardBeatId,
  eventId,
  autoPlayOnMount,
}: {
  index: number;
  videoUrl: string;
  storyboardBeatId: string;
  eventId: string;
  autoPlayOnMount?: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrl = `${SERVER_BASE}/api/beat/audio/${encodeURIComponent(storyboardBeatId)}?event_id=${encodeURIComponent(eventId)}`;

  const syncPlay = useCallback(async () => {
    const vid = videoRef.current;
    const aud = audioRef.current;
    if (!vid || !aud) return;
    try { aud.currentTime = 0; } catch { /* defensive */ }
    try { vid.currentTime = 0; } catch { /* defensive */ }
    await Promise.all([vid.play(), aud.play().catch(() => {})]);
  }, []);

  const syncPause = useCallback(() => {
    try { videoRef.current?.pause(); } catch { /* defensive */ }
    try { audioRef.current?.pause(); } catch { /* defensive */ }
  }, []);

  useLayoutEffect(() => {
    if (!autoPlayOnMount) return;
    void syncPlay();
  }, [autoPlayOnMount, videoUrl, storyboardBeatId, syncPlay]);

  const onVideoPlay = () => { void syncPlay(); };
  const onVideoPause = () => { syncPause(); };
  const onVideoEnded = () => {
    const aud = audioRef.current;
    if (aud && !aud.ended && !aud.paused) return;
    syncPause();
  };
  const onAudioEnded = () => {
    window.setTimeout(() => syncPause(), 2000);
  };

  return (
    <div class="mn-bg-magic-preview" data-testid={`bg-magic-preview-still-${index}`}>
      <video
        ref={videoRef}
        controls
        preload="metadata"
        src={videoUrl}
        onPlay={onVideoPlay}
        onPause={onVideoPause}
        onEnded={onVideoEnded}
      />
      <audio
        ref={audioRef}
        preload="auto"
        src={audioUrl}
        onEnded={onAudioEnded}
      />
    </div>
  );
}

// BeatGenCard — per-beat UI (1 char ref + 1 BG ref + 1×3 options)
// ----------------------------------------------------------------

interface BeatGenCardProps {
  index: number;
  beat: BgBeat;
  eventId: string;
  videoRole: string;
  pollResultForBeat?: GptOption[];
  busy: boolean;
  nativeExperimentBusy: boolean;
  o3IntentSnapshot?: O3GenerationIntentPoll;
  o3SubmitAudit?: O3SubmitAudit;
  o3WarningMessage?: string;
  onDelete: () => void;
  onUpdateText: (next: string) => void | Promise<boolean>;
  // LD CHARACTER_DROPDOWN_RESTORED_V1 — speaker dropdown change.
  onUpdateSpeaker: (next: string) => void;
  onSetPipeline: (pipeline: 'still_insert' | 'kling_o3_omni') => void;
  onGenerate: (dialogueText?: string) => void;
  onAccept: (optionKey: string) => void;
  onSelectO3Video: (optionKey: string) => void;
  onApproveStill: (optionKey: string) => void;
  onApplyO3Trim: (
    trimStart: number,
    trimBack: number | null,
    clear?: boolean,
  ) => Promise<{ previewUrl?: string; rawDurationS?: number } | undefined>;
  onSetReplaceSlot: (slotIndex: number) => void;
  onSubmitNativeLipSyncExperiment: () => void;
  // BG-5 / BG-8 / BG-18 — visible-button handlers (NOT right-click per Kim 2026-05-06).
  onEditChip: (chipText: string) => void;
  onInsertAfter: () => void;
  onRemoveRef: (refField: 'reference_image' | 'bg_ref_image', label: string) => void;
  onAlignElementRef?: () => void;
  onAddElementPose: () => void;
  // 2026-05-11 fix — parent refreshState() threaded into BgRefSlot + BgOptionTile.
  onRefresh: () => void;
  onBeatMissing: (beatId: string) => void | Promise<void>;
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
  index, beat, eventId, videoRole, pollResultForBeat, busy, nativeExperimentBusy,
  o3IntentSnapshot, o3SubmitAudit, o3WarningMessage,
  onDelete, onUpdateText, onUpdateSpeaker, onSetPipeline, onGenerate, onAccept,
  onSelectO3Video, onApproveStill, onApplyO3Trim, onSetReplaceSlot, onSubmitNativeLipSyncExperiment,
  onEditChip, onInsertAfter, onRemoveRef, onAlignElementRef, onAddElementPose, onRefresh, onBeatMissing,
  onPatchOptionTile, onPatchRefImage,
}: BeatGenCardProps) {
  const intentLockedPrompt = busy
    ? (o3IntentSnapshot?.prompt?.verbatim ?? o3SubmitAudit?.prompt_excerpt ?? null)
    : null;
  const externalPrompt = intentLockedPrompt ?? beatPromptText(beat);
  const savePrompt = useCallback(
    async (text: string) => {
      const ok = await onUpdateText(text);
      return ok !== false;
    },
    [onUpdateText],
  );
  const promptField = useProtectedPromptField({
    fieldId: beat.beat_id,
    externalText: externalPrompt,
    onSave: savePrompt,
    lockedExternal: !!intentLockedPrompt,
  });
  const [chips, setChips] = useState<string[]>(extractStageChips(beatPromptText(beat)));

  const onPromptInput = (e: Event) => {
    promptField.onInput(e);
    setChips(extractStageChips(promptField.getText()));
  };

  const onRemoveChip = (chipText: string) => {
    const re = new RegExp(`\\s*\\(${chipText.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}\\)`);
    const next = promptField.getText().replace(re, '');
    promptField.setText(next);
    setChips(extractStageChips(next));
    void onUpdateText(next);
  };

  const optionsToShow: (GptOption | null)[] = (() => {
    const o3Slots = buildFixedO3OptionSlots(beat);
    if (o3Slots.some((s) => s?.video_path)) {
      return o3Slots;
    }
    const persistedOptions = beat.gpt_options ?? beat.flux_options ?? [];
    const liveOptions = pollResultForBeat ?? null;
    const src = liveOptions ?? persistedOptions;
    const padded: (GptOption | null)[] = [...src];
    while (padded.length < 3) padded.push(null);
    return padded.slice(0, 3);
  })();
  const replaceSlotIndex = beat.kling_o3_replace_slot_index ?? 0;
  const o3FailureMessage = (beat.kling_o3_voice_fix_status ?? '').startsWith('failed')
    && beat.kling_o3_status !== 'approved'
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

  const magicStillSource = resolveBgMagicStillSourcePath(beat, eventId);
  const magicVideoSource = beat.kling_o3_video_path ?? null;
  const magicStillPreviewUrl = resolveBgMagicStillPreviewUrl(beat, eventId);
  const magicVideoPreviewUrl = resolveBgMagicVideoPreviewUrl(beat, eventId);
  const useMagicVideoOnO3 =
    beat.magic_canonical_kind === 'video'
    && !!magicVideoPreviewUrl
    && beat.magic_video_path_exists !== false;
  const [magicPreviewMode, setMagicPreviewMode] = useState<'still' | 'video' | null>(null);
  const [stillPreviewAutoplay, setStillPreviewAutoplay] = useState(false);
  const stillInsert = isStillInsertBeat(beat);
  const hasStillSource = !!magicStillSource
    || optionsToShow.some((o) => o?.local_path || o?.thumb_b64);
  const showStillClipHint = stillInsert && !beat.kling_o3_video_path && hasStillSource;
  const elementCharRefBlocked = isO3VoiceBeat(beat) && beat.element_char_ref_ok === false;
  const charRefHasImage = !!(
    beat.reference_image
    && (beat.reference_image.thumb_b64 || beat.reference_image.abs_path || beat.reference_image.key)
  );
  const showAddElementPose = isO3VoiceBeat(beat) && charRefHasImage;

  return (
    <li class="mn-bg-beat-card" data-testid={`bg-beat-card-${index}`} data-beat-id={beat.beat_id}>
      <div class="mn-bg-beat-meta">
        <span class="mn-bg-beat-index">#{index + 1}</span>
        <span class="mn-bg-beat-anchor">{beat.beat_id}</span>
        <select
          class="mn-beat-speaker"
          data-testid={`bg-beat-speaker-${index}`}
          value={canonBeatSpeaker(beat.speaker) || ''}
          disabled={beat.beat_plan_source === 'operator_insert_v1'}
          onChange={(e) => {
            const target = e.target as HTMLSelectElement | null;
            const v = (target?.value ?? '').trim();
            if (v && v !== canonBeatSpeaker(beat.speaker)) onUpdateSpeaker(v);
          }}
          aria-label={`Speaker for beat ${beat.beat_id}`}
          title={
            beat.beat_plan_source === 'operator_insert_v1'
              ? 'Speaker is fixed for inserted beats — delete and re-insert to change'
              : 'Change speaker (will trigger stale-TTS state on regen path)'
          }
        >
          {(() => {
            const raw = (beat.speaker ?? '').trim();
            const canon = canonBeatSpeaker(beat.speaker);
            const showLegacy = raw && raw === canon && !KNOWN_SPEAKERS.includes(raw as typeof KNOWN_SPEAKERS[number]);
            return showLegacy ? <option value={raw}>{raw}</option> : null;
          })()}
          {!beat.speaker ? <option value="">— speaker —</option> : null}
          {KNOWN_SPEAKERS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {isPipelineToggleable(beat) ? (
          <span
            class="mn-bg-pipeline-toggle"
            data-testid={`bg-pipeline-toggle-${index}`}
            role="group"
            aria-label={`Pipeline mode for beat ${beat.beat_id}`}
          >
            <button
              type="button"
              class={`mn-btn mn-btn-small${stillInsert ? ' mn-btn-primary' : ''}`}
              data-testid={`bg-pipeline-still-${index}`}
              aria-pressed={stillInsert ? 'true' : 'false'}
              disabled={busy}
              title="Still image + TTS audio (Ken Burns), no Kling O3 Element clip"
              onClick={() => {
                if (!stillInsert) onSetPipeline('still_insert');
              }}
            >
              Still + TTS
            </button>
            <button
              type="button"
              class={`mn-btn mn-btn-small${!stillInsert ? ' mn-btn-primary' : ''}`}
              data-testid={`bg-pipeline-o3-${index}`}
              aria-pressed={!stillInsert ? 'true' : 'false'}
              disabled={busy}
              title="Kling O3 Element voice video with padded lipsync tail"
              onClick={() => {
                if (stillInsert) onSetPipeline('kling_o3_omni');
              }}
            >
              O3 Kling
            </button>
          </span>
        ) : null}
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

      {promptField.lockedValue !== null ? (
        <textarea
          class="mn-bg-beat-text mn-bg-kling-prompt-editor"
          data-testid={`bg-beat-text-${index}`}
          value={promptField.lockedValue}
          readOnly
          rows={14}
          spellcheck={true}
          placeholder="Generation in progress — prompt locked to submitted intent."
          aria-label={`Kling O3 prompt for beat ${beat.beat_id}`}
        />
      ) : (
        <textarea
          ref={promptField.textareaRef}
          class="mn-bg-beat-text mn-bg-kling-prompt-editor"
          data-testid={`bg-beat-text-${index}`}
          onFocus={promptField.onFocus}
          onInput={onPromptInput}
          onBlur={promptField.onBlur}
          rows={14}
          spellcheck={true}
          aria-label={`Kling O3 prompt for beat ${beat.beat_id}`}
        />
      )}
      {o3SubmitAudit || o3IntentSnapshot ? (
        <div
          class="mn-bg-o3-intent-audit"
          data-testid={`bg-o3-intent-audit-${index}`}
          style="margin: 4px 0 8px; font-size: 11px; color: #94a3b8; font-family: ui-monospace, monospace;"
        >
          {o3IntentSnapshot?.generation?.slot || o3SubmitAudit?.generation_slot ? (
            <div>Slot: {o3IntentSnapshot?.generation?.slot ?? o3SubmitAudit?.generation_slot}</div>
          ) : null}
          {o3SubmitAudit?.prompt_excerpt ? (
            <div>Submitted: {o3SubmitAudit.prompt_excerpt.slice(0, 120)}…</div>
          ) : null}
          {o3SubmitAudit?.char_ref ? (
            <div>Char ref: {o3SubmitAudit.char_ref.split('/').pop()}</div>
          ) : null}
          {o3SubmitAudit?.element_id ? (
            <div>Element: {o3IntentSnapshot?.voice?.element_name ?? beat.speaker} ({o3SubmitAudit.element_id})</div>
          ) : null}
        </div>
      ) : null}
      {o3WarningMessage ? (
        <div
          class="mn-bg-o3-warning-banner"
          data-testid={`bg-o3-warning-${index}`}
          style="margin: 4px 0 8px; padding: 8px; background: #422006; border: 1px solid #f59e0b; border-radius: 6px; color: #fcd34d; font-size: 12px;"
        >
          {o3WarningMessage}
        </div>
      ) : null}
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
          {...(elementCharRefBlocked
            ? {
              elementRefError: elementCharRefInlineHint(beat.element_char_ref_error),
              elementRefErrorDetail: beat.element_char_ref_error,
              showAlignElementRef: true,
              onAlignElementRef,
            }
            : {})}
          {...(showAddElementPose
            ? { showAddElementPose: true, onAddElementPose }
            : {})}
          onRemoveRef={onRemoveRef}
          onRefresh={onRefresh}
          onBeatMissing={onBeatMissing}
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
          onBeatMissing={onBeatMissing}
          onPatchRefImage={onPatchRefImage}
        />
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid={`bg-generate-btn-${index}`}
          onClick={async () => {
            const saved = await promptField.flushSave();
            if (!saved) return;
            onGenerate(promptField.getText());
          }}
          disabled={busy || elementCharRefBlocked}
          title={elementCharRefBlocked ? elementCharRefInlineHint(beat.element_char_ref_error) : undefined}
        >
          {busy ? (
            <><Spinner size="sm" inline /> Generating{o3IntentSnapshot?.generation?.slot ? ` ${o3IntentSnapshot.generation.slot}` : ''}…</>
          ) : isStillInsertBeat(beat) ? (
            'Build still video (+ TTS)'
          ) : isO3VoiceBeat(beat) ? (
            'Generate padded O3 voice video'
          ) : (
            'Generate 3 options'
          )}
        </button>
      </div>

      {showStillClipHint ? (
        <p class="mn-dim mn-bg-still-clip-hint" data-testid={`bg-still-clip-hint-${index}`}>
          Still ready — click <strong>Build still video (+ TTS)</strong> above to Ken Burns the
          image and mux dialogue audio. Trim below, then use <strong>Approve still for stitch</strong>.
        </p>
      ) : null}

      <BeatMagicButtons
        index={index}
        beatId={beat.beat_id}
        eventId={eventId}
        videoRole={videoRole}
        stillImagePath={magicStillSource}
        videoSourcePath={magicVideoSource}
        videoSourceIsAbsolute={!!magicVideoSource}
        magicStillPath={beat.magic_still_path}
        magicVideoPath={beat.magic_video_path}
        magicCanonicalKind={beat.magic_canonical_kind ?? null}
        klingO3Status={beat.kling_o3_status ?? null}
        onPreviewMagicStill={magicStillPreviewUrl ? () => {
          setStillPreviewAutoplay(true);
          setMagicPreviewMode('still');
        } : undefined}
        onPreviewMagicVideo={magicVideoPreviewUrl ? () => setMagicPreviewMode('video') : undefined}
      />
      {magicPreviewMode === 'still' && magicStillPreviewUrl && beat.storyboard_beat_id ? (
        <BgMagicStillPreview
          index={index}
          videoUrl={magicStillPreviewUrl}
          storyboardBeatId={beat.storyboard_beat_id}
          eventId={eventId}
          autoPlayOnMount={stillPreviewAutoplay}
        />
      ) : null}
      {magicPreviewMode === 'still' && magicStillPreviewUrl && !beat.storyboard_beat_id ? (
        <div class="mn-bg-magic-preview" data-testid={`bg-magic-preview-still-${index}`}>
          <video controls preload="metadata" src={magicStillPreviewUrl} />
          <p class="mn-dim">No storyboard beat id — TTS preview unavailable.</p>
        </div>
      ) : null}
      {magicPreviewMode === 'video' && magicVideoPreviewUrl ? (
        <div class="mn-bg-magic-preview" data-testid={`bg-magic-preview-video-${index}`}>
          <video controls preload="metadata" src={magicVideoPreviewUrl} />
        </div>
      ) : null}

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
            onClick={() => {
              if (!opt) return;
              const optionKey = resolveO3OptionKey(opt, beat.beat_id, i);
              if (opt.video_path) {
                if (isStillInsertBeat(beat) && beat.kling_o3_status !== 'approved') {
                  return;
                }
                onSelectO3Video(optionKey);
              } else if (opt.key) onAccept(opt.key);
            }}
            onRefresh={onRefresh}
            onPatchOptionTile={onPatchOptionTile}
            stillInsert={stillInsert}
            klingO3Status={beat.kling_o3_status ?? null}
            videoCacheKey={beat.kling_o3_selected_at ?? beat.kling_o3_video_path ?? beat.beat_id}
            onApproveStill={(optionKey) => onApproveStill(optionKey)}
            trimStart={beat.kling_o3_trim_start ?? 0}
            trimBack={beat.kling_o3_trim_back ?? null}
            onApplyO3Trim={onApplyO3Trim}
            replaceSelected={i === replaceSlotIndex}
            onSetReplaceSlot={() => onSetReplaceSlot(i)}
            showReplaceOnRegen={!!beat.speaker}
            overrideVideoUrl={
              useMagicVideoOnO3 && opt?.source === 'approved_kling_o3_video'
                ? magicVideoPreviewUrl
                : null
            }
          />
        ))}
      </div>
      {(beat.kling_o3_disk_delivery_count ?? 0) > 0 && beat.kling_o3_clips_dir ? (
        <p class="mn-dim mn-bg-o3-disk-hint" data-testid={`bg-o3-disk-hint-${index}`}>
          {(beat.kling_o3_disk_delivery_count ?? 0)} paid O3 clip
          {(beat.kling_o3_disk_delivery_count ?? 0) === 1 ? '' : 's'} on disk
          {(beat.kling_o3_orphan_delivery_count ?? 0) > 0
            ? ` (${beat.kling_o3_orphan_delivery_count} recovered into Beat Gen on refresh)`
            : ''}
          . Newest 3 show in video 0–2 above. Review all in Finder: {beat.kling_o3_clips_dir}
        </p>
      ) : null}

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
  elementRefError?: string;
  elementRefErrorDetail?: string;
  showAlignElementRef?: boolean;
  onAlignElementRef?: () => void;
  showAddElementPose?: boolean;
  onAddElementPose?: () => void;
  // BG-18 — visible × button to remove the ref (NOT right-click per Kim 2026-05-06).
  onRemoveRef: (refField: 'reference_image' | 'bg_ref_image', label: string) => void;
  // 2026-05-11 fix — parent refreshState() to repaint stale beats[] after drop success.
  onRefresh: () => void;
  onBeatMissing: (beatId: string) => void | Promise<void>;
  // 2026-05-11 Rule 26 fix — optimistic local-state patcher (see BeatGenCardProps).
  onPatchRefImage: (
    refField: 'reference_image' | 'bg_ref_image',
    patch: { key?: string; abs_path?: string; thumb_b64?: string } | null,
  ) => void;
}

function BgRefSlot({
  label, refImg, testId, beatId, refField, elementRefError, elementRefErrorDetail,
  showAlignElementRef, onAlignElementRef, showAddElementPose, onAddElementPose,
  onRemoveRef, onRefresh, onBeatMissing, onPatchRefImage,
}: BgRefSlotPropsExt) {
  const hasImage = !!refImg && (refImg.thumb_b64 || refImg.abs_path || refImg.key);
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
      const result = await pathappPatch<{
        ok: boolean;
        thumb_b64?: string;
        element_ref_warning?: string;
        element_ref_registered?: string;
        element_char_ref_ok?: boolean;
      }>(
        activeScope.value, 'bg_update_beat', {
          beat_id: beatId,
          [refField]: {
            key: payload.lib_key,
            abs_path: payload.abs_path ?? '',
          },
        },
      );
      if (!result.ok) {
        onPatchRefImage(refField, null);
        if (isBeatNotFoundResult(result)) {
          await onBeatMissing(beatId);
          return;
        }
        const err = (result.error ?? `HTTP ${result.status}`).trim();
        const networkDead = /failed to fetch|networkerror|load failed/i.test(err);
        pushToast({
          kind: 'error',
          message: networkDead
            ? `${label} drop failed — no server on this port. Hard refresh http://localhost:5111/?event=${encodeURIComponent(activeScope.value.event_id)} and retry.`
            : `${label} drop failed: ${err}`,
          source: 'bg-ref-drop-error',
        });
      } else if (refField === 'reference_image' && result.data?.element_ref_registered) {
        if (result.data.thumb_b64) {
          onPatchRefImage(refField, {
            key: payload.lib_key,
            abs_path: payload.abs_path ?? '',
            thumb_b64: result.data.thumb_b64,
          });
        }
        pushToast({
          kind: 'success',
          message: result.data.element_ref_registered,
          source: 'bg-ref-element-registered',
        });
        onRefresh();
      } else if (
        refField === 'reference_image'
        && result.data?.element_ref_warning
        && result.data?.element_char_ref_ok !== true
      ) {
        if (result.data.thumb_b64) {
          onPatchRefImage(refField, {
            key: payload.lib_key,
            abs_path: payload.abs_path ?? '',
            thumb_b64: result.data.thumb_b64,
          });
        }
        pushToast({
          kind: 'warning',
          message: result.data.element_ref_warning,
          source: 'bg-ref-element-gate',
          ttlMs: 14000,
        });
        onRefresh();
      } else if (
        refField === 'reference_image'
        && result.data?.element_char_ref_ok === true
      ) {
        if (result.data.thumb_b64) {
          onPatchRefImage(refField, {
            key: payload.lib_key,
            abs_path: payload.abs_path ?? '',
            thumb_b64: result.data.thumb_b64,
          });
        }
        onRefresh();
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
    <div class="mn-bg-ref-slot-wrap" data-testid={`${testId}-wrap`}>
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
        ) : refImg?.abs_path ? (
          <img
            src={`${SERVER_BASE}/files?path=${encodeURIComponent(refImg.abs_path)}`}
            alt={label}
            class="mn-bg-ref-thumb"
          />
        ) : refImg?.key ? (
          <span class="mn-dim">{refImg.key}</span>
        ) : (
          <span class="mn-dim">drop here</span>
        )}
      </div>
      {showAddElementPose && onAddElementPose && refField === 'reference_image' ? (
        <button
          type="button"
          class="mn-btn mn-btn-small mn-bg-ref-add-element-btn"
          data-testid={`${testId}-add-element`}
          onClick={(e) => {
            e.stopPropagation();
            onAddElementPose();
          }}
        >
          Add to Element
        </button>
      ) : null}
      {elementRefError ? (
        <div
          class="mn-bg-ref-element-error"
          data-testid={`${testId}-element-error`}
          title={elementRefErrorDetail ?? elementRefError}
        >
          <p>{elementRefError}</p>
          {showAlignElementRef && onAlignElementRef ? (
            <button
              type="button"
              class="mn-btn mn-btn-small mn-bg-ref-element-align-btn"
              data-testid={`${testId}-align-element`}
              onClick={(e) => {
                e.stopPropagation();
                onAlignElementRef();
              }}
            >
              Use Element pose
            </button>
          ) : null}
        </div>
      ) : null}
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
  onRefresh: () => void;
  onPatchOptionTile: (slotIndex: number, patch: Partial<GptOption> & { key?: string; thumb_b64?: string }) => void;
  trimStart: number;
  trimBack: number | null;
  onApplyO3Trim: (
    trimStart: number,
    trimBack: number | null,
    clear?: boolean,
  ) => Promise<{ previewUrl?: string; rawDurationS?: number } | undefined>;
  replaceSelected: boolean;
  onSetReplaceSlot: () => void;
  showReplaceOnRegen: boolean;
  overrideVideoUrl?: string | null;
  stillInsert?: boolean;
  klingO3Status?: string | null;
  videoCacheKey?: string;
  onApproveStill?: (optionKey: string) => void;
}

function BgOptionTile({
  beatIndex, optionIndex, option, selected, onClick, beatId, onRefresh, onPatchOptionTile,
  trimStart, trimBack, onApplyO3Trim, replaceSelected, onSetReplaceSlot, showReplaceOnRegen,
  overrideVideoUrl, stillInsert, klingO3Status, videoCacheKey, onApproveStill,
}: BgOptionTilePropsExt) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const trimPlaybackListenerRef = useRef<((this: HTMLVideoElement, ev: Event) => void) | null>(null);
  const [videoLoadError, setVideoLoadError] = useState(false);
  const clipMissingOnDisk = option?.video_path_exists === false;
  const [trimStartDraft, setTrimStartDraft] = useState<string>(String(trimStart || 0));
  const [trimBackDraft, setTrimBackDraft] = useState<string>(String(trimBack || 0));
  const [loadedDuration, setLoadedDuration] = useState<number | null>(null);
  const rawDurationRef = useRef<number | null>(null);
  const savedTrimStart = trimStart || 0;
  const savedTrimBack = trimBack ?? 0;
  const trimDraftDirty = trimStartDraft !== String(savedTrimStart)
    || trimBackDraft !== String(savedTrimBack);
  useEffect(() => {
    setTrimStartDraft(String(trimStart || 0));
  }, [trimStart]);
  useEffect(() => {
    setTrimBackDraft(String(trimBack || 0));
  }, [trimBack]);
  const clearTrimPlaybackListener = useCallback((video?: HTMLVideoElement | null) => {
    const el = video ?? videoRef.current;
    if (!el) return;
    if (trimPlaybackListenerRef.current) {
      el.removeEventListener('timeupdate', trimPlaybackListenerRef.current);
      trimPlaybackListenerRef.current = null;
    }
    el.ontimeupdate = null;
  }, []);
  useEffect(() => () => clearTrimPlaybackListener(), [clearTrimPlaybackListener]);
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
        {showReplaceOnRegen ? (
          <label class="mn-dim" style="font-size:11px;display:block;margin-top:4px">
            <input
              type="radio"
              name={`bg-replace-${beatIndex}`}
              checked={replaceSelected}
              onChange={() => onSetReplaceSlot()}
              data-testid={`bg-replace-radio-${beatIndex}-${optionIndex}`}
              aria-label={`Replace empty slot ${optionIndex + 1} on next Kling generation`}
            />
            {' '}Replace on regen
          </label>
        ) : null}
      </div>
    );
  }
  // R3 fix: option without `key` → radio DISABLED + tooltip explaining why.
  // Without this gate the click silently no-ops or 400s server-side because
  // bg_accept_option requires option_key on the wire.
  const keyMissing = !option.key;
  const isStitchApproved = klingO3Status === 'approved';
  const isStillDraft = !!stillInsert && !!option.video_path && !isStitchApproved;
  const hasClipVideo = !!option.video_path;
  const showTrimControls = selected && hasClipVideo;
  const optionLabel = option.label?.trim()
    || (isStitchApproved
    ? 'approved O3 video'
    : isStillDraft
      ? 'still clip (draft — approve below)'
      : hasClipVideo
        ? 'O3 clip (select to approve)'
        : `option ${optionIndex + 1}`);
  const tooltip = keyMissing ? 'Option missing key — regenerate beat' : undefined;
  const cacheBust = videoCacheKey ? `&v=${encodeURIComponent(String(videoCacheKey))}` : '';
  const canonicalVideoUrl = option.video_path
    ? (overrideVideoUrl
      ?? `${SERVER_BASE}/files?path=${encodeURIComponent(option.video_path)}${cacheBust}`)
    : null;
  const activeVideoUrl = canonicalVideoUrl;
  const waitForVideoMetadata = (video: HTMLVideoElement) => new Promise<void>((resolve, reject) => {
    if (Number.isFinite(video.duration) && video.duration > 0) {
      resolve();
      return;
    }
    const onReady = () => {
      video.removeEventListener('loadedmetadata', onReady);
      video.removeEventListener('error', onErr);
      resolve();
    };
    const onErr = () => {
      video.removeEventListener('loadedmetadata', onReady);
      video.removeEventListener('error', onErr);
      reject(new Error('video load failed'));
    };
    video.addEventListener('loadedmetadata', onReady, { once: true });
    video.addEventListener('error', onErr, { once: true });
  });
  const resetVideoToCanonical = async () => {
    const video = videoRef.current;
    if (!video || !activeVideoUrl) return;
    clearTrimPlaybackListener(video);
    if (video.src !== activeVideoUrl) {
      video.src = activeVideoUrl;
    }
    video.load();
    try {
      await waitForVideoMetadata(video);
      video.currentTime = 0;
    } catch {
      // leave for user refresh
    }
  };
  useEffect(() => {
    void resetVideoToCanonical();
  }, [activeVideoUrl]);
  useEffect(() => {
    setVideoLoadError(false);
    rawDurationRef.current = null;
    setLoadedDuration(null);
  }, [canonicalVideoUrl]);
  const parseDraft = (value: string) => {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
  };
  const trimStartValue = () => parseDraft(trimStartDraft);
  const trimBackValue = () => parseDraft(trimBackDraft);
  const effectiveTrimStart = () => (trimDraftDirty ? trimStartValue() : savedTrimStart);
  const effectiveTrimBack = () => (trimDraftDirty ? trimBackValue() : savedTrimBack);
  const trimEndValue = (
    video: HTMLVideoElement,
    start = effectiveTrimStart(),
    back = effectiveTrimBack(),
  ) => {
    const dur = Number.isFinite(video.duration) ? Number(video.duration) : 0;
    if (dur <= 0) return null;
    if (back <= 0 && start <= 0.01) return null;
    const end = back > 0 ? dur - back : dur;
    if (end <= start + 0.05) return null;
    return Math.max(start + 0.01, end);
  };
  const trimWindowInvalid = (
    video: HTMLVideoElement | null,
    start = savedTrimStart,
    back = savedTrimBack,
  ) => {
    const dur = loadedDuration ?? (video && Number.isFinite(video.duration) ? video.duration : 0);
    if (dur <= 0) return false;
    if (start <= 0.01 && back <= 0.05) return false;
    const end = back > 0 ? dur - back : dur;
    return end <= start + 0.05;
  };
  const savedTrimInvalid = trimWindowInvalid(videoRef.current);
  const attachTrimStopListener = (video: HTMLVideoElement, stopAt: number | null) => {
    clearTrimPlaybackListener(video);
    const onTimeUpdate = () => {
      const end = stopAt ?? (Number.isFinite(video.duration) ? video.duration : Infinity);
      if (video.currentTime >= end) {
        video.pause();
        clearTrimPlaybackListener(video);
      }
    };
    trimPlaybackListenerRef.current = onTimeUpdate;
    video.addEventListener('timeupdate', onTimeUpdate);
  };
  const playTrimPreview = async () => {
    if (!selected) {
      pushToast({
        kind: 'error',
        message: 'Select this clip before trimming',
        source: 'bg-o3-trim-preview-not-active',
      });
      return;
    }
    const video = videoRef.current;
    if (!video || !canonicalVideoUrl) return;
    try {
      if (video.src !== canonicalVideoUrl) {
        video.src = canonicalVideoUrl;
        video.load();
      }
      await waitForVideoMetadata(video);
    } catch {
      pushToast({
        kind: 'error',
        message: 'Preview Trim: could not load clip — try refreshing',
        source: 'bg-o3-trim-preview-load',
      });
      return;
    }
    const start = effectiveTrimStart();
    const stopAt = trimEndValue(video, start, effectiveTrimBack());
    clearTrimPlaybackListener(video);
    video.currentTime = start;
    attachTrimStopListener(video, stopAt);
    try {
      await video.play();
    } catch {
      pushToast({
        kind: 'info',
        message: 'Preview Trim: seek set — press play if autoplay was blocked',
        source: 'bg-o3-trim-preview-play',
      });
    }
    pushToast({
      kind: 'info',
      message: stopAt != null
        ? `Preview Trim: ${start.toFixed(1)}s → ${stopAt.toFixed(1)}s${trimDraftDirty ? ' (draft — Apply Trim to save)' : ''}`
        : `Preview Trim: from ${start.toFixed(1)}s${trimDraftDirty ? ' (draft — Apply Trim to save)' : ''}`,
      source: 'bg-o3-trim-preview',
    });
  };
  const applyDraftTrim = async () => {
    if (!selected) {
      pushToast({
        kind: 'error',
        message: 'Select this clip before applying trim',
        source: 'bg-o3-trim-apply-not-active',
      });
      return;
    }
    clearTrimPlaybackListener(videoRef.current);
    const applied = await onApplyO3Trim(
      trimStartValue(),
      trimBackValue() > 0 ? trimBackValue() : null,
    );
    if (applied?.rawDurationS != null && applied.rawDurationS > 0) {
      rawDurationRef.current = applied.rawDurationS;
    }
    const video = videoRef.current;
    if (video && canonicalVideoUrl) {
      if (video.src !== canonicalVideoUrl) {
        video.src = canonicalVideoUrl;
      }
      video.load();
      try {
        await waitForVideoMetadata(video);
        const start = trimStartValue();
        video.currentTime = start;
        attachTrimStopListener(video, trimEndValue(video, start, trimBackValue()));
      } catch {
        // user can retry play
      }
    }
  };
  const ensureCanonicalVideoForPlayhead = async () => {
    const video = videoRef.current;
    if (!video || !canonicalVideoUrl) return null;
    clearTrimPlaybackListener(video);
    if (video.src !== canonicalVideoUrl) {
      video.src = canonicalVideoUrl;
      video.load();
      try {
        await waitForVideoMetadata(video);
      } catch {
        return null;
      }
    }
    return video;
  };
  const setStartFromPlayhead = async () => {
    const video = await ensureCanonicalVideoForPlayhead();
    if (!video) return;
    const start = Math.max(0, Number(video.currentTime) || 0);
    setTrimStartDraft(start.toFixed(2));
  };
  const setEndFromPlayhead = async () => {
    const video = await ensureCanonicalVideoForPlayhead();
    if (!video || !Number.isFinite(video.duration)) return;
    const rawDur = rawDurationRef.current ?? Number(video.duration) ?? 0;
    const atTime = Math.max(0, Number(video.currentTime) || 0);
    const back = Math.max(0, rawDur - atTime);
    setTrimBackDraft(back.toFixed(2));
  };
  return (
    <div
      class={`mn-bg-option mn-drop-target${selected ? ' is-selected' : ''}${keyMissing ? ' is-disabled' : ''}${isStitchApproved && hasClipVideo ? ' is-approved-video' : ''}${isStillDraft ? ' is-still-draft' : ''}`}
      data-testid={`bg-option-${beatIndex}-${optionIndex}`}
      data-option-key={option.key ?? ''}
      onClick={keyMissing || isStillDraft ? undefined : onClick}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
      title={tooltip}
    >
      {activeVideoUrl && !clipMissingOnDisk ? (
        <>
          <video
            ref={videoRef}
            controls
            preload="metadata"
            src={activeVideoUrl}
            data-testid={`bg-option-video-${beatIndex}-${optionIndex}`}
            onPause={() => clearTrimPlaybackListener()}
            onError={() => setVideoLoadError(true)}
            onLoadedData={() => {
              setVideoLoadError(false);
              const v = videoRef.current;
              if (v && Number.isFinite(v.duration) && v.duration > 0) {
                setLoadedDuration(v.duration);
              }
            }}
            onPlay={() => {
              const video = videoRef.current;
              if (!video) return;
              if (trimWindowInvalid(video, effectiveTrimStart(), effectiveTrimBack())) {
                clearTrimPlaybackListener(video);
                return;
              }
              const start = effectiveTrimStart();
              const stopAt = trimEndValue(video, start, effectiveTrimBack());
              if (start > 0.01 && video.currentTime < start) {
                video.currentTime = start;
              }
              attachTrimStopListener(video, stopAt);
            }}
          />
          {videoLoadError ? (
            <div class="mn-bg-option-empty" data-testid={`bg-option-video-error-${beatIndex}-${optionIndex}`}>
              Clip failed to load — server may have restarted.
              <button
                type="button"
                class="mn-btn mn-btn-small"
                onClick={(e) => {
                  e.stopPropagation();
                  setVideoLoadError(false);
                  void resetVideoToCanonical();
                }}
              >
                Retry
              </button>
            </div>
          ) : null}
          {showTrimControls ? (
          <div class="mn-bg-o3-trim-controls" data-testid={`bg-o3-trim-controls-${beatIndex}-${optionIndex}`}>
            {savedTrimInvalid ? (
              <span class="mn-dim" style={{ color: '#f88' }}>
                trim invalid for this clip — Clear Trim or Apply a shorter back trim
              </span>
            ) : null}
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
                void setStartFromPlayhead();
              }}
              title="Set front trim from playhead (draft only — Apply Trim to save)"
            >
              Start Trim
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`bg-o3-end-trim-${beatIndex}-${optionIndex}`}
              onClick={(e) => {
                e.stopPropagation();
                void setEndFromPlayhead();
              }}
              title="Set back trim from playhead (draft only — Apply Trim to save)"
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
                rawDurationRef.current = null;
                const video = videoRef.current;
                if (video && canonicalVideoUrl) {
                  clearTrimPlaybackListener(video);
                  video.src = canonicalVideoUrl;
                  video.load();
                }
                void onApplyO3Trim(0, null, true);
              }}
            >
              Clear Trim
            </button>
          </div>
          ) : null}
          {isStillDraft && onApproveStill && option.key ? (
            <button
              type="button"
              class="mn-btn mn-btn-small mn-btn-primary"
              data-testid={`bg-approve-still-${beatIndex}-${optionIndex}`}
              onClick={(e) => {
                e.stopPropagation();
                onApproveStill(resolveO3OptionKey(option, beatId, optionIndex));
              }}
            >
              Approve still for stitch
            </button>
          ) : null}
        </>
      ) : clipMissingOnDisk ? (
        <div class="mn-bg-option-empty" data-testid={`bg-option-video-missing-${beatIndex}-${optionIndex}`}>
          Clip missing on disk — regenerate O3 or pick another slot.
        </div>
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
          onChange={isStillDraft ? undefined : (keyMissing ? undefined : onClick)}
          disabled={keyMissing || isStillDraft}
          title={isStillDraft ? 'Draft still clip — use Approve still for stitch below' : tooltip}
          aria-label={optionLabel}
          data-testid={`bg-option-radio-${beatIndex}-${optionIndex}`}
        />
        {' '}{optionLabel}
      </label>
      {showReplaceOnRegen && option?.video_path ? (
        <label class="mn-dim" style="font-size:11px;display:block;margin-top:2px">
          <input
            type="radio"
            name={`bg-replace-${beatIndex}`}
            checked={replaceSelected}
            onChange={(e) => {
              e.stopPropagation();
              onSetReplaceSlot();
            }}
            data-testid={`bg-replace-radio-${beatIndex}-${optionIndex}`}
            aria-label={`Replace slot ${optionIndex + 1} on next Kling generation`}
          />
          {' '}Replace on regen
        </label>
      ) : showReplaceOnRegen ? (
        <label class="mn-dim" style="font-size:11px;display:block;margin-top:2px">
          <input
            type="radio"
            name={`bg-replace-${beatIndex}`}
            checked={replaceSelected}
            onChange={(e) => {
              e.stopPropagation();
              onSetReplaceSlot();
            }}
            data-testid={`bg-replace-radio-${beatIndex}-${optionIndex}`}
            aria-label={`Replace slot ${optionIndex + 1} on next Kling generation`}
          />
          {' '}Replace on regen
        </label>
      ) : null}
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
