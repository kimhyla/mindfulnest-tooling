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
  activeTargetVideo,
  activeProjectType,
  activeMilestoneId,
  activeScopeQueryParams,
  beatGenAuthorityBadgeLabel,
  effectiveScopeVideoRole,
} from '../state/scope';
import { setActiveVideoRole, videoRoleForBgPhase } from '../state/videoRole';
import { apiGet, pathappPatch, type ApiResult } from '../api/client';
import { formatMutationError } from '../api/mutationErrors';
import { isClientBundleStaleError } from '../state/buildShaDrift';
import { SERVER_BASE } from '../api/endpoints';
import { makeDropTarget } from '../utils/dragdrop';
import { useDropTargetCapture } from '../hooks/useDropTargetCapture';
import { openCropper } from '../state/cropper';
import { Modal } from './ui/Modal';
import { BeatPlanModal, type BeatPlanDraftSaveStatus, type BeatPlanRow } from './BeatPlanModal';
import { InsertBeatModal, type InsertBeatPlanRow } from './InsertBeatModal';
import { Spinner } from './ui/Spinner';
import { Select } from './ui/Select';
import { pushToast } from './ui/Toast';
import {
  BgO3CutOverlay,
  isValidO3CutWindow,
  normalizeO3KeepWindow,
  resolveO3ExportDurationS,
  resolveO3OverlayDurationS,
  resolveO3PlaybackDurationS,
  resolveO3TrimAuthorityDurationS,
} from './bg/BgO3CutOverlay';
import { resolveClipPlaybackTruth } from '../utils/playbackCache';
import {
  forgetCutPreviewsForBeat,
  recallCutPreviewUrl,
  rememberCutPreviewUrl,
} from '../state/cutPreviewStore';
import { resolveStitchSlotSourceVideoUrl } from '../utils/stitchSlotVideo';
import { PLAYBACK_VIDEO_ANTI_BANDING_CLASS } from '../utils/playbackVideoPolicy';
import {
  BgO3TrimNumericControls,
  showBgO3NumericTrimControls,
} from './bg/BgO3TrimNumericControls.deprecated';
import { useBgO3TrimNumericDraft } from '../hooks/useBgO3TrimNumericDraft';
import { useBgO3CutSession } from '../hooks/useBgO3CutSession';
import { writePersistedTrackSlot, isStitchUiSlotKey } from '../utils/stitchTrackFocus';
import { stitchJobSessionKey } from '../state/producerSessionKeys';
import { ensureStitchJobSession } from '../state/stitchJobSessionStore';
import { stitcherRefreshTick } from '../state/refreshSignals';
import {
  BeatMagicButtons,
  resolveBgMagicStillPreviewUrl,
  resolveBgMagicVideoPreviewUrl,
  resolveBgMagicStillSourcePath,
  resolveO3TileMagicOverrideUrl,
} from './BeatMagicButtons';
import {
  allBeatsStitchExportReady,
  stitchExportBlockTooltip,
} from '../utils/bgStitchExport';
import {
  beatHasActiveO3DeliveryClip,
  KLING_STITCH_READINESS_V1,
  stillBeatNeedsStitchApprove as stillBeatNeedsStitchApproveContract,
} from '../utils/klingStitchReadiness';
import { lintKlingO3PromptContradictions } from '../utils/promptContradictionLint';
import {
  notifyStitchSlotExportApplied,
  stitchExportKeptExistingWarning,
} from '../utils/stitchSlotVideoLineage';
import {
  BG_EXPORT_POLL_INTERVAL_MS,
  bgExportScopeKey,
  bgExportStatusMessage,
  bgExportTerminalSuccess,
  isBgExportStatusTerminal,
  readBgExportBusyLatch,
  writeBgExportBusyLatch,
  type BgExportPollResult,
} from '../utils/bgExportToStitcherJobTruth';
import {
  beatElementCharRefError,
  beatElementCharRefOk,
  beatHasActiveNavJob,
  beatOperatorMutationsLocked,
  computeBeatNavItemStatuses,
  isStillInsertNavBeat,
  purgeO3ClientJobStateForBeatIds,
  type BeatNavItemStatus,
} from '../utils/bgBeatNavStatus';
import { applyPromptEditsToBeats, clearPromptEdit, readPromptEditText } from '../state/promptEditRegistry';
import { useProtectedPromptField } from '../hooks/useProtectedPromptField';
import {
  beatO3JobBusy,
  beatO3JobLooksRunning,
  beatO3ServerJobInFlight,
  O3_SUBMIT_PENDING_TTL_MS,
  pruneO3SubmitPending,
} from '../o3JobStatusContract';
import { effect } from '@preact/signals';
import type {
  BgBeat,
  BeatGenerationMode,
  GptOption,
} from '../types/bgBeat';
import {
  bgActiveJobId,
  bgActiveNativeLipSyncJobs,
  bgActiveO3Jobs,
  bgActiveSegment,
  bgActiveStillRenderJobs,
  bgArcNumber,
  bgBeats,
  bgGptBatchSubmitPending,
  bgLipsyncPublicHostMessage,
  bgLipsyncPublicHostReady,
  bgO3IntentByBeat,
  bgO3SubmitAuditByBeat,
  bgO3SubmitPending,
  bgO3WarningByBeat,
  bgPollResults,
  bgSegments,
  bgSessionHasCache,
  bgSessionLoading,
  bgSessionSlowHint,
  beatSaveBlockedRef,
  beatSaveNotFoundToastRef,
  ensureBgSession,
  genFailureToastRef,
  refreshBgSession,
  submitPollLatchRef,
  updateBgBeats,
  applyO3SubmitPollLatch,
  tryReattachO3JobFromSession,
} from '../state/bgSessionStore';
import {
  formatO3JobFailure,
  isNetworkPollBlip,
  mergeBeatFromO3Poll,
} from '../utils/bgPollHelpers';
import type {
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
  Loral: 'Lorelai',
  Laurel: 'Lorelai',
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

type RefDisplay = { key?: string; abs_path?: string; thumb_b64?: string; filename?: string };

/** Persisted sidecar ref wins over session `_derived` implicit fallback (workbench authority spec). */
function displayPersistedRef(
  stored: RefDisplay | null | undefined,
  derived: RefDisplay | null | undefined,
): RefDisplay | null {
  if (stored && (stored.thumb_b64 || stored.abs_path || stored.key)) {
    // Session refresh often returns abs_path-only stored refs; keep inline thumb from _derived.
    if (!stored.thumb_b64 && derived?.thumb_b64) {
      const merged: RefDisplay = { ...stored, thumb_b64: derived.thumb_b64 };
      const key = stored.key ?? derived.key;
      if (key) {
        merged.key = key;
      } else {
        delete merged.key;
      }
      return merged;
    }
    return stored;
  }
  return derived ?? stored ?? null;
}

function displayCharRef(beat: BgBeat): RefDisplay | null {
  return displayPersistedRef(beat.reference_image, beat._derived?.char_ref_display);
}

function displayBgRef(beat: BgBeat, stillInsert: boolean): RefDisplay | null {
  if (stillInsert) {
    return displayPersistedRef(beat.bg_ref_image, beat._derived?.still_scene_display);
  }
  return displayPersistedRef(beat.bg_ref_image, beat._derived?.bg_ref_display);
}

function displayStillScenePath(beat: BgBeat): string | null {
  const ref = beat._derived?.still_scene_display ?? beat.bg_ref_image;
  if (ref?.abs_path) return ref.abs_path;
  const lib = (beat as BgBeat & { accepted_library_ref?: { abs_path?: string } }).accepted_library_ref;
  if (lib?.abs_path) return lib.abs_path;
  for (const opt of beat.gpt_options ?? []) {
    if (opt?.local_path) return opt.local_path;
  }
  return null;
}

function resolveBeatOptionsToShow(
  beat: BgBeat,
  eventId: string,
  pollResultForBeat: GptOption[] | null | undefined,
): (GptOption | null)[] {
  const mode = beat._derived?.generation_mode
    ? String(beat._derived.generation_mode) as BeatGenerationMode
    : effectiveGenerationMode(beat, eventId);
  const serverSlots = beat._derived?.option_slots;
  if (Array.isArray(serverSlots) && serverSlots.some((s) => s?.video_path)) {
    return serverSlots.slice(0, 3);
  }
  const o3Slots = buildFixedO3OptionSlots(beat, mode);
  if (o3Slots.some((s) => s?.video_path)) {
    return o3Slots;
  }
  const persistedOptions = beat.gpt_options ?? beat.flux_options ?? [];
  const liveOptions = pollResultForBeat ?? null;
  const src = liveOptions ?? persistedOptions;
  const padded: (GptOption | null)[] = [...src];
  while (padded.length < 3) padded.push(null);
  return padded.slice(0, 3);
}

function isOperatorJobBusyError(code?: string | null): boolean {
  return code === 'BEAT_JOB_BUSY' || code === 'INTENT_JOB_ACTIVE';
}

function effectiveGenerationMode(beat?: BgBeat | null, eventId?: string): BeatGenerationMode {
  if (!beat) return 'element_native';
  const derived = beat._derived?.generation_mode;
  if (derived === 'still_insert' || derived === 'voice_first' || derived === 'element_native') {
    return derived;
  }
  if (derived === 'avatar_pro') {
    return 'element_native';
  }
  if (isStillInsertBeat(beat)) return 'still_insert';
  const gm = (beat.generation_mode ?? beat.o3_generate_mode ?? '').trim().toLowerCase();
  if (gm === 'avatar_pro') return 'element_native';
  if (gm === 'voice_first' || gm === 'element_native') return gm;
  const ev = (eventId ?? '').replace(/^Event_/i, '').trim();
  const hasSpeak = Boolean((beat.dialogue_text ?? beat.kling_o3_prompt ?? '').trim());
  if (ev === '2' && hasSpeak) return 'voice_first';
  return 'element_native';
}

/** Element pose registration applies to element_native / voice_first — not Avatar Pro. */
function elementCharRefApplies(beat?: BgBeat | null, eventId?: string): boolean {
  if (!beat || !isO3VoiceBeat(beat)) return false;
  return effectiveGenerationMode(beat, eventId) !== 'avatar_pro';
}

function o3GenerateButtonLabel(generationMode: BeatGenerationMode): string {
  if (generationMode === 'avatar_pro') {
    return 'Generate (Avatar Pro)';
  }
  if (generationMode === 'voice_first') {
    return 'Generate voice-first O3 (ElevenLabs + lipsync)';
  }
  if (generationMode === 'element_native') {
    return 'Generate Element native O3';
  }
  return 'Generate padded O3 voice video';
}

const GENERATION_MODE_TOAST: Record<BeatGenerationMode, string> = {
  still_insert: 'Pipeline: Still + TTS — Generate builds smooth zoom still (1.0→1.06×) with dialogue audio.',
  avatar_pro: 'Pipeline: Avatar Pro — ElevenLabs TTS → Kling Avatar Pro portrait → 720 delivery.',
  voice_first: 'Pipeline: Voice-first — Generate runs ElevenLabs → silent O3 → lipsync → 720 delivery.',
  element_native: 'Pipeline: Element native O3 — Generate runs O3 Pro with Element voice baked in.',
};

function inferO3OptionPipelineMode(opt?: GptOption | null): BeatGenerationMode | '' {
  if (!opt) return '';
  const source = (opt.source ?? '').trim().toLowerCase();
  const path = (opt.video_path ?? '').toLowerCase();
  if (
    source === 'kling_real_voice_harvest'
    || source === 'kling_o3_element_native_voice'
  ) {
    return 'element_native';
  }
  if (source === 'o3_pov_motion_i2v' || path.includes('_o3_i2v') || path.includes('_pov_')) {
    return 'element_native';
  }
  if (source.includes('still_insert') || path.includes('still_insert')) return 'still_insert';
  if (path.includes('_avatar_pro') || source === 'kling_o3_avatar_pro') return 'avatar_pro';
  if (path.includes('_voice_lipsync')) return 'voice_first';
  if (path.includes('_element_o3') || (path.includes('_element_') && !path.includes('_voice_lipsync'))) {
    return 'element_native';
  }
  if (source === 'kling_o3_voice_video') return 'voice_first';
  return '';
}

function displayO3OptionLabel(opt: GptOption): string {
  const stored = opt.label?.trim();
  if (stored === 'latest O3 voice video') return 'ElevenLabs voice-first (latest)';
  const mode = inferO3OptionPipelineMode(opt);
  if (mode === 'avatar_pro') return 'Avatar Pro (latest)';
  if (mode === 'voice_first') return 'ElevenLabs voice-first';
  if (mode === 'element_native') {
    const gen = typeof opt.generation === 'number'
      ? opt.generation
      : o3GenerationFromPath(opt.video_path);
    return gen ? `g${gen} Kling Element voice` : 'Kling Element voice';
  }
  if (mode === 'still_insert') return stored || 'Still + TTS clip';
  return stored || 'O3 clip';
}

function activeO3OptionForBeat(beat?: BgBeat | null): GptOption | null {
  if (!beat?.kling_o3_video_path) return null;
  return (beat.kling_o3_options ?? []).find((o) => o?.video_path === beat.kling_o3_video_path) ?? null;
}

function computePipelineSelectionMismatch(beat?: BgBeat | null): boolean {
  if (!beat) return false;
  const mode = effectiveGenerationMode(beat);
  if (mode === 'still_insert') return false;
  const clipMode = inferO3OptionPipelineMode(activeO3OptionForBeat(beat));
  if (!clipMode) {
    return !!beat.kling_o3_selection_pipeline_mismatch;
  }
  return clipMode !== mode;
}

function pipelineSelectionMismatchMessage(beat?: BgBeat | null): string | null {
  if (!computePipelineSelectionMismatch(beat)) return null;
  const mode = effectiveGenerationMode(beat);
  const clip = inferO3OptionPipelineMode(activeO3OptionForBeat(beat))
    || beat?.kling_o3_active_clip_pipeline
    || '';
  return (
    `Pipeline mismatch: beat is set to ${mode} but the selected clip is ${clip || 'another pipeline'}. `
    + 'Preview and stitch export use the selected clip — Element clips use Kling voice, not ElevenLabs. '
    + 'Select a matching clip or switch the pipeline toggle.'
  );
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

const STILL_INSERT_PROMPT_MARKERS = [
  'do not submit to kling o3 element',
  'assign the still image in beat gen',
  'use pre-made gpt still from library',
  'use pre-made from library',
  'no @image1 character clip for this beat',
];

function isStillInsertPromptText(text?: string | null): boolean {
  const t = (text ?? '').trim();
  if (!t) return false;
  if (t.toUpperCase().startsWith('STILL INSERT')) return true;
  const lower = t.toLowerCase();
  return STILL_INSERT_PROMPT_MARKERS.some((marker) => lower.includes(marker));
}

/** Prompt-box is law — mode-specific: still vs O3 (voice_first + element_native share O3). */
function beatPromptText(beat?: BgBeat | null, eventId?: string): string {
  if (!beat) return '';
  const fromDerived = (beat._derived?.display_prompt ?? '').trim();
  if (fromDerived) return fromDerived;
  const mode = effectiveGenerationMode(beat, eventId);
  if (mode === 'still_insert') {
    const still = (beat.kling_o3_prompt_still ?? '').trim();
    if (still) return still;
    const legacy = (beat.kling_o3_prompt ?? '').trim();
    if (isStillInsertPromptText(legacy)) return legacy;
    return legacy || beat.dialogue_text || '';
  }
  const o3 = (beat.kling_o3_prompt ?? '').trim();
  if (o3 && !isStillInsertPromptText(o3)) return beat.kling_o3_prompt ?? '';
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
      submitting?: boolean;
    };

/** Option key for **Approve still for stitch** — works even when sidecar row lacks ``key``. */
function resolveStillStitchApproveOptionKey(beat: BgBeat): string | null {
  if (!isStillInsertBeat(beat)) return null;
  return resolveActiveO3OptionKey(beat);
}

function stillBeatNeedsStitchApprove(beat: BgBeat): boolean {
  return stillBeatNeedsStitchApproveContract(beat);
}

function resolveActiveO3OptionKey(beat: BgBeat): string | null {
  const activePath = (beat.kling_o3_video_path ?? '').trim();
  if (!activePath) return null;
  const opts = beat.kling_o3_options ?? [];
  const matched = opts.find((o) => o?.video_path === activePath);
  if (matched) {
    const idx = Math.max(0, opts.indexOf(matched));
    return resolveO3OptionKey(matched, beat.beat_id, idx);
  }
  const slot = buildFixedO3OptionSlots(beat).find((s) => s?.video_path === activePath);
  if (slot) {
    return resolveO3OptionKey(slot, beat.beat_id, slot.slot_index ?? 0);
  }
  return resolveO3OptionKey({ video_path: activePath }, beat.beat_id, 0);
}

interface GptBatchSubmitResponse {
  ok: boolean;
  job_id?: string;
  beat_ids?: string[];
  total_options?: number;
}

interface StillClipRenderResponse {
  ok: boolean;
  beat_id?: string;
  beat?: BgBeat;
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

// ----------------------------------------------------------------
// Constants
// ----------------------------------------------------------------

// Per LD-440 GPT_IMAGE_2_PRIMARY_MODEL_V1 — gpt-image-2 published unit cost.
const PER_IMAGE_COST_USD = 0.04;

function isUserSelectableO3Video(path?: string | null, source?: string | null): boolean {
  if (source === 'still_insert_static_hold' || source === 'still_insert_ken_burns' || source === 'still_insert_kling_idle') {
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
  if (name.includes('_voice_lipsync_delivery')) return 1_000_000;
  const m = name.match(/_g(\d+)(?:_(?:element|kling)|\.mp4)/i) ?? name.match(/_g(\d+)\.mp4$/i);
  return m ? Number(m[1]) : 0;
}

/** Fixed 3-container layout — pin-slot by ``slot_index`` (replace slot overwrites one tile). */
function buildFixedO3OptionSlots(
  beat: BgBeat,
  generationMode?: BeatGenerationMode,
): (GptOption | null)[] {
  const slots: (GptOption | null)[] = [null, null, null];
  const mode = generationMode ?? effectiveGenerationMode(beat);
  const o3History = (beat.kling_o3_options ?? []).filter((o) => {
    if (!isUserSelectableO3Video(o?.video_path, o?.source)) return false;
    const optMode = inferO3OptionPipelineMode(o);
    if (mode === 'still_insert') return optMode === 'still_insert';
    if (optMode === 'still_insert') return false;
    if (mode === 'element_native' || mode === 'voice_first' || mode === 'avatar_pro') {
      if (!optMode) return true;
      return optMode === mode;
    }
    return true;
  });
  const activeO3Path = isUserSelectableO3Video(beat.kling_o3_video_path) ? beat.kling_o3_video_path! : null;
  const unslotted: GptOption[] = [];
  for (const opt of o3History) {
    const si = opt.slot_index;
    if (typeof si === 'number' && si >= 0 && si <= 2) {
      if (slots[si] == null) {
        slots[si] = opt;
      } else {
        unslotted.push(opt);
      }
      continue;
    }
    unslotted.push(opt);
  }
  for (const opt of unslotted) {
    const emptyIdx = slots.findIndex((s) => s == null);
    if (emptyIdx < 0) break;
    slots[emptyIdx] = { ...opt, slot_index: emptyIdx };
  }
  const activeListed = activeO3Path && slots.some((s) => s?.video_path === activeO3Path);
  if (beatHasActiveO3DeliveryClip(beat) && activeO3Path && !activeListed) {
    const activeOpt = o3History.find((o) => o.video_path === activeO3Path);
    const emptyIdx = slots.findIndex((s) => s == null);
    if (emptyIdx >= 0) {
      slots[emptyIdx] = activeOpt ?? {
        key: `${beat.beat_id}_approved_o3_video`,
        label: 'approved O3 video',
        video_path: activeO3Path,
        source: 'approved_kling_o3_video',
        slot_index: emptyIdx,
      };
    }
  }
  return slots;
}

function isStaleLipsyncHostingFailure(error?: string | null): boolean {
  const raw = (error ?? '').trim().toLowerCase();
  if (!raw) return false;
  return [
    'no lipsync input host returned byte-complete public files',
    'r2_cdn: unavailable or preflight failed',
    'production_staging: unavailable or preflight failed',
    'unsafe url: non-public host',
    'lipsync_hosting_not_configured',
  ].some((marker) => raw.includes(marker));
}

const LIPSYNC_HOSTING_SETUP_MESSAGE =
  'Voice-first Generate needs Cloudflare R2 lipsync staging on this machine. '
  + 'Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID, and R2_BUCKET_NAME '
  + 'in Doppler or Production/API_KEYS_MASTER.md, then restart Event servers.';

function voiceFirstLipsyncHostBlocked(
  lipsyncHostReady: boolean | null,
  beats: BgBeat[],
  eventId?: string,
): boolean {
  if (lipsyncHostReady === true) return false;
  return beats.some(
    (b) => !isStillInsertBeat(b) && effectiveGenerationMode(b, eventId) === 'voice_first',
  );
}

function notifyLipsyncHostBlocked(
  message: string,
  seenRef: { current: boolean },
): void {
  if (seenRef.current) return;
  seenRef.current = true;
  pushToast({
    kind: 'warning',
    message,
    source: 'bg-lipsync-host',
    ttlMs: 12000,
  });
}
function resolveO3FailureBanner(
  beat: BgBeat,
  lipsyncHostReady: boolean | null,
  eventId?: string,
): string | null {
  if (!isO3VoiceBeat(beat)) return null;
  if (beatO3JobLooksRunning(beat)) return null;
  const err = (beat.kling_o3_voice_fix_error ?? '').trim();
  if (!err) return null;
  if (
    effectiveGenerationMode(beat, eventId) === 'voice_first'
    && lipsyncHostReady === true
    && isStaleLipsyncHostingFailure(err)
    && beatHasActiveO3DeliveryClip(beat)
    && isUserSelectableO3Video(beat.kling_o3_video_path)
  ) {
    return null;
  }
  return formatO3JobFailure(err);
}

function beatGenFailureNotifyKey(beat: BgBeat): string | null {
  const voiceFix = (beat.kling_o3_voice_fix_status ?? '').toLowerCase();
  const err = (beat.kling_o3_voice_fix_error ?? '').trim();
  if (!beatO3JobLooksRunning(beat) && err) {
    return `o3-attempt-fail:${beat.beat_id}:${err.slice(0, 120)}`;
  }
  if (voiceFix.startsWith('failed')) {
    return `o3-fail:${beat.beat_id}:${voiceFix}:${err.slice(0, 120)}`;
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
  const beats = bgBeats.value;
  /** Mirror beats for Generate submit — ref box must not lag one render behind. */
  const beatsRef = useRef<BgBeat[]>([]);
  beatsRef.current = beats;

  const arcNumber = bgArcNumber.value;
  const segments = bgSegments.value;
  const activeSegment = bgActiveSegment.value;
  const isMilestoneScope = activeProjectType.value === 'milestone' && Boolean(activeMilestoneId.value);
  const milestoneSegmentLabel = useMemo(() => {
    if (!isMilestoneScope || segments.length === 0) return activeMilestoneId.value ?? 'Milestone';
    const s = segments[0];
    return s.name ? `${s.name}` : `Event ${s.event_id} ${s.phase}`;
  }, [isMilestoneScope, segments, activeMilestoneId.value]);
  const loading = bgSessionLoading.value && !bgSessionHasCache();
  const loadingSlowHint = bgSessionSlowHint.value;
  const activeJobId = bgActiveJobId.value;
  const activeO3Jobs = bgActiveO3Jobs.value;
  const o3IntentByBeat = bgO3IntentByBeat.value as Record<string, O3GenerationIntentPoll>;
  const o3SubmitAuditByBeat = bgO3SubmitAuditByBeat.value as Record<string, O3SubmitAudit>;
  const o3SubmitPending = bgO3SubmitPending.value;
  const o3WarningByBeat = bgO3WarningByBeat.value;
  const activeStillRenderJobs = bgActiveStillRenderJobs.value;
  const gptBatchSubmitPending = bgGptBatchSubmitPending.value;
  const activeNativeLipSyncJobs = bgActiveNativeLipSyncJobs.value;
  const lipsyncPublicHostReady = bgLipsyncPublicHostReady.value;
  const lipsyncPublicHostMessage = bgLipsyncPublicHostMessage.value;
  const pollResults = bgPollResults.value;

  const o3SubmitPendingTimersRef = useRef<Record<string, number>>({});
  const voiceDriftSubmitInFlightRef = useRef<string | null>(null);
  const markO3SubmitPending = useCallback((beatId: string) => {
    bgO3SubmitPending.value = { ...bgO3SubmitPending.value, [beatId]: true };
    const existingTimer = o3SubmitPendingTimersRef.current[beatId];
    if (existingTimer) window.clearTimeout(existingTimer);
    o3SubmitPendingTimersRef.current[beatId] = window.setTimeout(() => {
      bgO3SubmitPending.value = (prev => {
        const next = { ...prev };
        delete next[beatId];
        return next;
      })(bgO3SubmitPending.value);
      delete o3SubmitPendingTimersRef.current[beatId];
    }, O3_SUBMIT_PENDING_TTL_MS);
  }, []);
  const clearO3SubmitPending = useCallback((beatId: string) => {
    const timer = o3SubmitPendingTimersRef.current[beatId];
    if (timer) {
      window.clearTimeout(timer);
      delete o3SubmitPendingTimersRef.current[beatId];
    }
    bgO3SubmitPending.value = (prev => {
      const next = { ...prev };
      delete next[beatId];
      return next;
    })(bgO3SubmitPending.value);
  }, []);
  const lipsyncHostBlockToastRef = useRef(false);
  const [, setAcceptStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [stitcherExportStatus, setStitcherExportStatus] = useState<'idle' | 'submitting' | 'exporting'>('idle');
  const [activeExportJobId, setActiveExportJobId] = useState<string | null>(null);
  const [exportProgressMessage, setExportProgressMessage] = useState('');
  const exportTerminalToastRef = useRef<string | null>(null);
  const [extractStatus, setExtractStatus] = useState<'idle' | 'sending'>('idle');
  const [extractError, setExtractError] = useState<string | null>(null);
  const [approveStatus, setApproveStatus] = useState<'idle' | 'sending'>('idle');
  const [approveStartedAt, setApproveStartedAt] = useState<number | null>(null);
  /** EXTRACT_APPROVE_OUTCOME_V1 — inline modal error when approve fails (not toast-only). */
  const [approveBeatPlanError, setApproveBeatPlanError] = useState<string | null>(null);
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
  const [reorderBusyBeatId, setReorderBusyBeatId] = useState<string | null>(null);
  const navJumpLockUntilRef = useRef<number>(0);
  const closeModal = () => setModalState({ kind: 'none' });

  const purgeO3ClientLatchesForBeatIds = useCallback((beatIds: string[]) => {
    const ids = beatIds.map((id) => id.trim()).filter(Boolean);
    if (ids.length === 0) return;
    for (const id of ids) {
      delete submitPollLatchRef.current[id];
    }
    const purged = purgeO3ClientJobStateForBeatIds(ids, {
      o3IntentByBeat: bgO3IntentByBeat.value as Record<string, O3GenerationIntentPoll>,
      o3SubmitAuditByBeat: bgO3SubmitAuditByBeat.value as Record<string, O3SubmitAudit>,
      activeO3Jobs: bgActiveO3Jobs.value,
      o3SubmitPending: bgO3SubmitPending.value,
      submitPollLatch: submitPollLatchRef.current,
    });
    bgO3IntentByBeat.value = purged.o3IntentByBeat;
    bgO3SubmitAuditByBeat.value = purged.o3SubmitAuditByBeat;
    bgActiveO3Jobs.value = purged.activeO3Jobs;
    bgO3SubmitPending.value = purged.o3SubmitPending;
  }, []);

  const beatIdsKey = useMemo(
    () => beats.map((b) => b.beat_id).join('|'),
    [beats],
  );

  const beatNavJobContext = useMemo(() => ({
    activeJobId,
    activeO3Jobs,
    o3SubmitPending,
    activeStillRenderJobs,
    activeNativeLipSyncJobs,
    gptBatchSubmitPending,
  }), [activeJobId, activeO3Jobs, o3SubmitPending, activeStillRenderJobs, activeNativeLipSyncJobs, gptBatchSubmitPending]);

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

  const refreshState = async () => {
    const ok = await refreshBgSession();
    if (!ok) return;
    const nextBeats = bgBeats.value;
    notifyNewGenFailures(nextBeats, genFailureToastRef);
    const liveIds = new Set(nextBeats.map((b) => b.beat_id));
    beatSaveBlockedRef.current.forEach((id) => {
      if (liveIds.has(id)) beatSaveBlockedRef.current.delete(id);
    });
    const prunedPending = pruneO3SubmitPending(nextBeats, bgO3SubmitPending.value);
    bgO3SubmitPending.value = prunedPending;
    const nextIntent = { ...(bgO3IntentByBeat.value as Record<string, O3GenerationIntentPoll>) };
    const nextAudit = { ...(bgO3SubmitAuditByBeat.value as Record<string, O3SubmitAudit>) };
    for (const beat of nextBeats) {
      const beatId = (beat.beat_id ?? '').trim();
      if (!beatId) continue;
      const o3PollActive = !!bgActiveO3Jobs.value[beatId];
      if (
        isStillInsertNavBeat(beat)
        || (!beatO3JobBusy(beat, !!prunedPending[beatId]) && !o3PollActive)
      ) {
        delete nextIntent[beatId];
        delete nextAudit[beatId];
      }
    }
    bgO3IntentByBeat.value = nextIntent;
    bgO3SubmitAuditByBeat.value = nextAudit;
  };

  // Track GPT batch completion for session cost display (poll lives in BgPollCoordinator).
  useEffect(() => {
    let prevJobId: string | null = null;
    const dispose = effect(() => {
      const jobId = bgActiveJobId.value;
      if (prevJobId && !jobId) {
        let cost = 0;
        for (const opts of Object.values(bgPollResults.value)) {
          for (const o of opts) {
            if (typeof o.cost_usd === 'number') cost += o.cost_usd;
          }
        }
        if (cost === 0) {
          const doneCount = Object.values(bgPollResults.value).reduce((n, opts) => n + opts.length, 0);
          cost = doneCount * PER_IMAGE_COST_USD;
        }
        setLastBatchCostUsd(cost);
        setRunningCostUsd((c) => c + cost);
      }
      prevJobId = jobId;
    });
    return dispose;
  }, []);

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

  // Overnight / laptop-sleep: background tabs throttle O3 poll timers. Re-sync from
  // sidecar when the tab wakes so Generating clears after the job finished on disk.
  useEffect(() => {
    const syncAfterWake = () => {
      if (document.visibilityState === 'visible') {
        void refreshState();
      }
    };
    document.addEventListener('visibilitychange', syncAfterWake);
    window.addEventListener('focus', syncAfterWake);
    return () => {
      document.removeEventListener('visibilitychange', syncAfterWake);
      window.removeEventListener('focus', syncAfterWake);
    };
  }, []);

  const handleBeatMissingOnSave = useCallback(async (beatId: string) => {
    beatSaveBlockedRef.current.add(beatId);
    const hadBeatLocally = bgBeats.value.some((b) => b.beat_id === beatId);
    await refreshState();
    const stillOnServer = bgBeats.value.some((b) => b.beat_id === beatId);
    if (stillOnServer) {
      beatSaveBlockedRef.current.delete(beatId);
      return;
    }
    if (hadBeatLocally) {
      updateBgBeats((bs) => bs.filter((b) => b.beat_id !== beatId));
    }
    if (!beatSaveNotFoundToastRef.current.has(beatId)) {
      beatSaveNotFoundToastRef.current.add(beatId);
      pushToast({
        kind: 'warning',
        message: beatMissingToastMessage(beatId),
        source: 'bg-beat-missing',
        ttlMs: BEAT_MISSING_TOAST_MS,
      });
    }
  }, [activeScope.value.event_id, activeTargetVideo.value]);

  const guardBeatPatchResult = useCallback(async (
    beatId: string,
    result: Pick<ApiResult, 'ok' | 'error' | 'error_code'>,
    errorMessage: string,
    source: string,
  ): Promise<boolean> => {
    if (result.ok) return true;
    if (isClientBundleStaleError(result)) return false;
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
      bgActiveSegment.value = combined;
      // activeTargetVideo change re-fires session via ProducerSessionCoordinator.
      return;
    }
    bgActiveSegment.value = combined;
    const result = await pathappPatch(activeScope.value, 'bg_set_active_context', {
      arc_number: arcNumber, event_id, phase,
    });
    if (!result.ok) {
      const msg = formatMutationError(result, 'Set context failed');
      if (msg) {
        pushToast({ kind: 'error', message: msg, source: 'bg-set-context' });
      }
    }
    await refreshState();
  };

  const openBeatPlanDraft = async (): Promise<boolean> => {
    if (!activeSegment && !isMilestoneScope) {
      pushToast({ kind: 'info', message: 'Select a segment first.', source: 'bg-review-plan' });
      return false;
    }
    const { event_id, phase } = segmentCtx();
    const draftRes = await apiGet<{
      story_summary?: string;
      beats_plan?: BeatPlanRow[];
      beat_plan_draft?: { story_summary?: string; beats_plan?: BeatPlanRow[] };
      reconstructed_from_beats?: boolean;
    }>('bg_extract_beats_draft', {
      arc_number: String(arcNumber),
      event_id,
      phase,
      ...activeScopeQueryParams(),
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
    if (!activeSegment && !isMilestoneScope) return;
    const { event_id, phase } = segmentCtx();
    const draftRes = await apiGet<{ beats_plan?: BeatPlanRow[] }>('bg_extract_beats_draft', {
      arc_number: String(arcNumber),
      event_id,
      phase,
      ...activeScopeQueryParams(),
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
    setApproveBeatPlanError(null);
    setBeatPlanDraftSaveStatus('idle');
  };

  const formatBeatPlanApproveError = (
    result: Pick<ApiResult<unknown>, 'ok' | 'error' | 'error_code' | 'error_message' | 'status' | 'hint' | 'data'>,
  ): string => {
    const data = result.data as {
      author_audit?: string[];
      message?: string;
      code?: string;
    } | undefined;
    if (Array.isArray(data?.author_audit) && data.author_audit.length > 0) {
      const detail = data.author_audit.slice(0, 3).join('; ');
      const more = data.author_audit.length > 3
        ? ` (+${data.author_audit.length - 3} more)`
        : '';
      return `Approve failed — Kling author pass did not stick: ${detail}${more}`;
    }
    if (data?.message) return data.message;
    return formatMutationError(result, 'Approve beat plan');
  };

  const onApproveBeatPlan = async (storySummary: string, beatsPlan: BeatPlanRow[]) => {
    if (!activeSegment && !isMilestoneScope) return;
    const { event_id, phase } = segmentCtx();
    setApproveBeatPlanError(null);
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
        const approvedBeats = applyPromptEditsToBeats(result.data.beats ?? []);
        updateBgBeats(approvedBeats);
        setBeatPlanOpen(false);
        setApproveBeatPlanError(null);
        await refreshState();
        if (approvedBeats.length > 0 && bgBeats.value.length === 0) {
          updateBgBeats(approvedBeats);
        }
        pushToast({
          kind: 'success',
          message: (
            `Populated ${result.data.count ?? 0} beats — each beat card shows the full `
            + `Kling O3 prompt (editable; what you see is what submits)`
          ),
          source: 'bg-extract-approve',
        });
      } else if (isNetworkPollBlip(result)) {
        const msg = formatBeatPlanApproveError(result);
        setApproveBeatPlanError(msg);
        pushToast({ kind: 'error', message: msg, source: 'bg-approve-error' });
      } else {
        const msg = formatBeatPlanApproveError(result);
        setApproveBeatPlanError(msg);
        pushToast({ kind: 'error', message: msg, source: 'bg-approve-error' });
      }
    } catch (err) {
      const msg = formatMutationError(
        { ok: false, status: 0, error: err instanceof Error ? err.message : String(err) },
        'Approve beat plan',
      );
      setApproveBeatPlanError(msg);
      pushToast({ kind: 'error', message: msg, source: 'bg-approve-error' });
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
      updateBgBeats((bs) => {
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
    const unsavedPrompt = readPromptEditText(beatId)?.trim();
    if (unsavedPrompt) {
      const saved = await onUpdateBeatText(beatId, unsavedPrompt);
      if (!saved) {
        pushToast({
          kind: 'warning',
          message:
            `Could not save the prompt on ${beatId} — delete cancelled. `
            + 'Fix the save error or copy your prompt elsewhere first.',
          source: 'bg-delete-unsaved-prompt',
        });
        return;
      }
    }
    const result = await pathappPatch(activeScope.value, 'bg_delete_beat', { beat_id: beatId });
    if (result.ok) {
      clearPromptEdit(beatId);
      pushToast({
        kind: 'info',
        message:
          `Deleted ${beatId}. Other beats keep their own prompts — check the prompt box before Generate.`,
        source: 'bg-delete',
      });
      updateBgBeats((bs) => bs.filter((b) => b.beat_id !== beatId));
    } else {
      const msg = formatMutationError(result, 'Delete failed');
      if (msg) {
        pushToast({ kind: 'error', message: msg, source: 'bg-delete-error' });
      }
    }
  };

  const onUpdateBeatText = async (beatId: string, nextText: string): Promise<boolean> => {
    if (beatSaveBlockedRef.current.has(beatId)) {
      if (!beatSaveNotFoundToastRef.current.has(beatId)) {
        beatSaveNotFoundToastRef.current.add(beatId);
        pushToast({
          kind: 'warning',
          message: beatMissingToastMessage(beatId),
          source: 'bg-beat-missing-save',
          ttlMs: BEAT_MISSING_TOAST_MS,
        });
      }
      return false;
    }
    const beat = beats.find((b) => b.beat_id === beatId);
    const mode = beat ? effectiveGenerationMode(beat, activeScope.value.event_id) : 'element_native';
    const patchBody = {
      beat_id: beatId,
      ...(mode === 'still_insert'
        ? { ['kling_o3_prompt_still']: nextText, ['kling_o3_prompt']: nextText }
        : { ['kling_o3_prompt']: nextText }),
    };
    const patchBeatText = () => pathappPatch<{
      ok: boolean;
      element_char_ref_ok?: boolean;
      element_char_ref_error?: string | null;
      element_ref_warning?: string | null;
    }>(activeScope.value, 'bg_update_beat', patchBody);
    let result = await patchBeatText();
    if (!result.ok && isOperatorJobBusyError(result.error_code)) {
      await refreshState();
      result = await patchBeatText();
    }
    if (!result.ok && result.error_code === 'SIDECAR_LOCK_TIMEOUT') {
      await new Promise((r) => setTimeout(r, 2500));
      result = await patchBeatText();
    }
    if (!result.ok) {
      const err = (result.error || '').trim();
      if (isClientBundleStaleError(result)) {
        return false;
      }
      if (isBeatNotFoundResult(result)) {
        await handleBeatMissingOnSave(beatId);
        return false;
      }
      if (isOperatorJobBusyError(result.error_code)) {
        pushToast({
          kind: 'warning',
          message:
            'Beat is locked while a job is running — wait for it to finish, then try again.',
          source: 'bg-job-busy-lock',
        });
        return false;
      }
      if (result.error_code === 'SIDECAR_LOCK_TIMEOUT') {
        pushToast({
          kind: 'warning',
          message: formatMutationError(result, 'Save failed'),
          source: 'bg-sidecar-lock-timeout',
        });
        return false;
      }
      const msg = /failed to fetch|networkerror|load failed/i.test(err)
        ? 'Save failed — server was restarting. Wait for “server is back”, then click Generate again (your text is still in the box).'
        : formatMutationError(result, 'Save failed');
      if (!msg) return false;
      pushToast({ kind: 'error', message: msg, source: 'bg-update-text' });
      return false;
    }
    updateBgBeats((bs) => bs.map((b): BgBeat => {
      if (b.beat_id !== beatId) return b;
      const next: BgBeat = { ...b };
      if (mode === 'still_insert') {
        next.kling_o3_prompt_still = nextText;
        next.kling_o3_prompt = nextText;
      } else {
        next.kling_o3_prompt = nextText;
      }
      if (nextText.trim()) next.o3_prompt_box_law = true;
      else delete next.o3_prompt_box_law;
      return next;
    }));
    if (result.data && typeof result.data.element_char_ref_ok === 'boolean') {
      const gateOk = result.data.element_char_ref_ok;
      const gateErr = result.data.element_char_ref_error ?? null;
      updateBgBeats((bs) => bs.map((b): BgBeat => {
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
    const lockField = refField === 'reference_image'
      ? 'reference_image_locked'
      : 'bg_ref_image_locked';
    updateBgBeats((bs) => bs.map((b): BgBeat => {
      if (b.beat_id !== beatId) return b;
      if (patch === null) {
        const next: BgBeat = { ...b, [refField]: null };
        next[lockField] = false;
        if (refField === 'reference_image' && b._derived?.char_ref_display) {
          next._derived = { ...(b._derived ?? {}), char_ref_display: null };
        }
        return next;
      }
      const next: BgBeat = { ...b, [refField]: patch, [lockField]: true };
      if (refField === 'reference_image') {
        next._derived = { ...(b._derived ?? {}), char_ref_display: patch };
      } else if (isStillInsertBeat(b)) {
        next._derived = { ...(b._derived ?? {}), still_scene_display: patch };
      } else {
        next._derived = { ...(b._derived ?? {}), bg_ref_display: patch };
      }
      return next;
    }));
  };

  const onUpdateBeatSpeaker = async (beatId: string, nextSpeaker: string) => {
    if (beatSaveBlockedRef.current.has(beatId)) return;
    updateBgBeats((bs) => bs.map((b) => (
      b.beat_id === beatId ? { ...b, speaker: nextSpeaker } : b
    )));
    const result = await pathappPatch<{
      ok: boolean;
      element_char_ref_ok?: boolean;
      element_char_ref_error?: string | null;
      thumb_b64?: string;
    }>(activeScope.value, 'bg_update_beat', {
      beat_id: beatId, speaker: nextSpeaker,
    });
    if (result.ok) {
      const gateOk = result.data?.element_char_ref_ok;
      const gateErr = result.data?.element_char_ref_error ?? null;
      if (typeof gateOk === 'boolean') {
        updateBgBeats((bs) => bs.map((b): BgBeat => {
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

  const onSetBeatGenerationMode = async (beatId: string, mode: BeatGenerationMode) => {
    if (beatSaveBlockedRef.current.has(beatId)) return;
    const beat = beats.find((b) => b.beat_id === beatId);
    if (!beat || !isPipelineToggleable(beat)) return;
    if (effectiveGenerationMode(beat, activeScope.value.event_id) === mode) return;
    const oldMode = effectiveGenerationMode(beat, activeScope.value.event_id);
    const currentText = beatPromptText(beat, activeScope.value.event_id);
    updateBgBeats((bs) => bs.map((b): BgBeat => {
      if (b.beat_id !== beatId) return b;
      const next: BgBeat = { ...b };
      if (oldMode === 'still_insert') {
        next.kling_o3_prompt_still = currentText;
      } else if (currentText && !isStillInsertPromptText(currentText)) {
        next.kling_o3_prompt = currentText;
      }
      if (mode === 'still_insert') {
        next.pipeline = 'still_insert';
        next.beat_render_mode = 'still_insert';
        next.generation_mode = 'still_insert';
        const stillPrompt = (next.kling_o3_prompt_still ?? '').trim()
          || (isStillInsertPromptText(next.kling_o3_prompt) ? next.kling_o3_prompt : '');
        if (stillPrompt) {
          next.kling_o3_prompt = stillPrompt;
          next.kling_o3_prompt_still = stillPrompt;
        }
      } else {
        next.pipeline = 'kling_o3_omni';
        next.o3_generate_mode = mode;
        next.generation_mode = mode;
        delete next.beat_render_mode;
        const o3Prompt = (next.kling_o3_prompt ?? '').trim();
        if (!o3Prompt || isStillInsertPromptText(o3Prompt)) {
          // keep server rebuild; clear stale still header from textarea
          if (isStillInsertPromptText(o3Prompt)) {
            next.kling_o3_prompt = '';
          }
        }
      }
      return next;
    }));
    if (mode === 'still_insert') {
      purgeO3ClientLatchesForBeatIds([beatId]);
    }
    const result = await pathappPatch<{
      ok: boolean;
      pipeline?: string;
      beat_render_mode?: string;
      beat_type?: string;
      kling_o3_prompt?: string;
      kling_o3_prompt_still?: string;
      o3_generate_mode?: string;
      generation_mode?: BeatGenerationMode;
      element_char_ref_ok?: boolean;
      element_char_ref_error?: string | null;
      changed?: boolean;
    }>(activeScope.value, 'bg_set_pipeline', {
      beat_id: beatId,
      generation_mode: mode,
    });
    let pipelineResult = result;
    if (!pipelineResult.ok && isOperatorJobBusyError(pipelineResult.error_code)) {
      await refreshState();
      pipelineResult = await pathappPatch(activeScope.value, 'bg_set_pipeline', {
        beat_id: beatId,
        generation_mode: mode,
      });
    }
    if (pipelineResult.ok && pipelineResult.data) {
      updateBgBeats((bs) => bs.map((b): BgBeat => {
        if (b.beat_id !== beatId) return b;
        const next: BgBeat = { ...b };
        if (pipelineResult.data?.pipeline) next.pipeline = pipelineResult.data.pipeline;
        if (pipelineResult.data?.beat_render_mode) {
          next.beat_render_mode = pipelineResult.data.beat_render_mode;
        } else {
          delete next.beat_render_mode;
        }
        if (pipelineResult.data?.o3_generate_mode) {
          next.o3_generate_mode = pipelineResult.data.o3_generate_mode;
        }
        if (pipelineResult.data?.generation_mode) {
          next.generation_mode = pipelineResult.data.generation_mode;
        }
        if (pipelineResult.data?.kling_o3_prompt) {
          next.kling_o3_prompt = pipelineResult.data.kling_o3_prompt;
        }
        if (pipelineResult.data?.kling_o3_prompt_still) {
          next.kling_o3_prompt_still = pipelineResult.data.kling_o3_prompt_still;
        }
        if (typeof pipelineResult.data?.element_char_ref_ok === 'boolean') {
          next.element_char_ref_ok = pipelineResult.data.element_char_ref_ok;
          if (pipelineResult.data.element_char_ref_error) {
            next.element_char_ref_error = pipelineResult.data.element_char_ref_error;
          } else {
            delete next.element_char_ref_error;
          }
        }
        return next;
      }));
      pushToast({
        kind: 'success',
        message: GENERATION_MODE_TOAST[mode],
        source: 'bg-set-pipeline',
      });
      await refreshState();
    } else {
      await refreshState();
    }
    await guardBeatPatchResult(
      beatId,
      pipelineResult,
      `Pipeline switch failed: ${pipelineResult.error}`,
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
      updateBgBeats((bs) => bs.map((b): BgBeat => {
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
      updateBgBeats((bs) => bs.map((b): BgBeat => {
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
    const priorSlot = beats.find((b) => b.beat_id === beatId)?.kling_o3_replace_slot_index ?? 0;
    updateBgBeats((prev) => prev.map((b) => (
      b.beat_id === beatId ? { ...b, kling_o3_replace_slot_index: slotIndex } : b
    )));
    const result = await pathappPatch(activeScope.value, 'bg_update_beat', {
      beat_id: beatId,
      kling_o3_replace_slot_index: slotIndex,
    });
    if (!result.ok && priorSlot !== slotIndex) {
      updateBgBeats((prev) => prev.map((b) => (
        b.beat_id === beatId ? { ...b, kling_o3_replace_slot_index: priorSlot } : b
      )));
    }
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
    bgActiveStillRenderJobs.value = { ...bgActiveStillRenderJobs.value, [beatId]: true };
    try {
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
        if (result.data.beat?.beat_id) {
          updateBgBeats((bs) => mergeBeatFromO3Poll(bs, result.data!.beat!));
        }
        bgO3IntentByBeat.value = (prev => {
          const next = { ...prev };
          delete next[beatId];
          return next;
        })(bgO3IntentByBeat.value as Record<string, O3GenerationIntentPoll>);
        bgO3SubmitAuditByBeat.value = (prev => {
          const next = { ...prev };
          delete next[beatId];
          return next;
        })(bgO3SubmitAuditByBeat.value as Record<string, O3SubmitAudit>);
        purgeO3ClientLatchesForBeatIds([beatId]);
        await refreshState();
      } else if (isBeatNotFoundResult(result)) {
        await handleBeatMissingOnSave(beatId);
      } else {
        const msg = formatMutationError(result, 'Still clip failed');
        if (msg) {
          pushToast({ kind: 'error', message: msg, source: 'bg-still-clip-error' });
        }
      }
    } finally {
      bgActiveStillRenderJobs.value = (prev => {
        const next = { ...prev };
        delete next[beatId];
        return next;
      })(bgActiveStillRenderJobs.value);
    }
  };

  const handleO3SubmitResult = async (
    beatId: string,
    beat: BgBeat,
    result: Awaited<ReturnType<typeof pathappPatch<ArloO3SubmitResponse>>>,
  ): Promise<boolean> => {
    // BG_O3_SUBMIT_UI_REATTACH_V1 — poll latch + session reattach on ambiguous submit.
    if (result.ok && result.data?.job_id) {
      applyO3SubmitPollLatch(beatId, result.data.job_id);
      if (result.data.intent) {
        bgO3IntentByBeat.value = {
          ...(bgO3IntentByBeat.value as Record<string, O3GenerationIntentPoll>),
          [beatId]: result.data!.intent!,
        };
      }
      if (result.data.submitted) {
        bgO3SubmitAuditByBeat.value = {
          ...(bgO3SubmitAuditByBeat.value as Record<string, O3SubmitAudit>),
          [beatId]: result.data!.submitted!,
        };
      }
      await refreshState();
      const slot = result.data.generation_slot ?? result.data.submitted?.generation_slot;
      const mode = result.data.o3_generate_mode;
      const modeLabel = mode === 'avatar_pro'
        ? 'Avatar Pro'
        : mode === 'voice_first'
          ? 'ElevenLabs voice-first'
          : 'Element native O3';
      pushToast({
        kind: 'info',
        message: result.data.deduped
          ? 'This beat already has an O3 voice job running; reattached to the existing job.'
          : `Submitted ${beat.speaker} ${modeLabel}${slot ? ` (${slot})` : ''} — prompt locked until job finishes`,
        source: 'bg-o3-submit',
        ttlMs: 12_000,
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
    if (result.error_code === 'LIPSYNC_HOSTING_NOT_CONFIGURED') {
      const message = result.error_message
        ?? result.error
        ?? LIPSYNC_HOSTING_SETUP_MESSAGE;
      bgLipsyncPublicHostReady.value = false;
      bgLipsyncPublicHostMessage.value = message;
      notifyLipsyncHostBlocked(message, lipsyncHostBlockToastRef);
      return false;
    }
    if (
      isOperatorJobBusyError(result.error_code)
      || (result.status === 0 && /failed to fetch|networkerror|load failed|timeout|aborted/i.test(result.error ?? ''))
    ) {
      const reattached = await tryReattachO3JobFromSession(beatId);
      if (reattached) {
        pushToast({
          kind: 'info',
          message: 'O3 job is already running on the server — reattached to the existing job.',
          source: 'bg-o3-submit-reattach',
          ttlMs: 12_000,
        });
        return true;
      }
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
    const generationMode = effectiveGenerationMode(refBeat, activeScope.value.event_id);
    const result = await pathappPatch<ArloO3SubmitResponse>(
      activeScope.value, 'bg_submit_arlo_o3_voice', {
        beat_id: beatId,
        kling_o3_prompt: promptToSave,
        generation_mode: generationMode,
        model: 'pro',
        replace_slot_index: refBeat.kling_o3_replace_slot_index ?? 0,
        reference_image: refBeat.reference_image ?? null,
        bg_ref_image: refBeat.bg_ref_image ?? null,
        ...(acceptVoiceDrift ? { accept_voice_drift: true } : {}),
      },
      { skipSnapshot: true },
    );
    return handleO3SubmitResult(beatId, refBeat, result);
  };

  const confirmVoiceDriftSubmit = async () => {
    if (modalState.kind !== 'voice-drift-confirm') return;
    const { beatId, promptToSave, replaceSlotIndex, referenceImage, bgRefImage } = modalState;
    if (modalState.submitting || voiceDriftSubmitInFlightRef.current === beatId) return;
    const beat = beatsRef.current.find((b) => b.beat_id === beatId)
      ?? beats.find((b) => b.beat_id === beatId);
    if (!beat) return;
    const serverFlightCtx = {
      activeO3Jobs: bgActiveO3Jobs.value,
      submitPollLatch: submitPollLatchRef.current,
    };
    if (beatO3ServerJobInFlight(beatId, beat, serverFlightCtx)) {
      closeModal();
      pushToast({
        kind: 'info',
        message: 'This beat is already generating.',
        source: 'bg-voice-drift-already-busy',
      });
      return;
    }
    voiceDriftSubmitInFlightRef.current = beatId;
    setModalState((prev) => (
      prev.kind === 'voice-drift-confirm' && prev.beatId === beatId
        ? { ...prev, submitting: true }
        : prev
    ));
    const workBeat: BgBeat = {
      ...beat,
      kling_o3_prompt: promptToSave,
      kling_o3_replace_slot_index: replaceSlotIndex,
      reference_image: referenceImage ?? beat.reference_image ?? null,
      bg_ref_image: bgRefImage ?? beat.bg_ref_image ?? null,
    };
    try {
      const submitted = await submitO3Voice(beatId, workBeat, promptToSave, true);
      if (submitted) closeModal();
    } finally {
      if (voiceDriftSubmitInFlightRef.current === beatId) {
        voiceDriftSubmitInFlightRef.current = null;
      }
      setModalState((prev) => (
        prev.kind === 'voice-drift-confirm' && prev.beatId === beatId && prev.submitting
          ? { ...prev, submitting: false }
          : prev
      ));
    }
  };

  const onGenerateBatch = async (
    beatId: string,
    dialogueText?: string,
    opts?: { promptAlreadyPersisted?: boolean },
  ) => {
    const beat = beats.find((b) => b.beat_id === beatId);
    if (!beat) return;
    if (isStillInsertBeat(beat)) {
      await onRenderStillClip(beatId, dialogueText);
      return;
    }
    const serverFlightCtx = {
      activeO3Jobs: bgActiveO3Jobs.value,
      submitPollLatch: submitPollLatchRef.current,
    };
    if (beatO3ServerJobInFlight(beatId, beat, serverFlightCtx)) {
      pushToast({ kind: 'info', message: 'This beat is already generating.', source: 'bg-o3-beat-busy' });
      return;
    }
    if (!opts?.promptAlreadyPersisted) {
      markO3SubmitPending(beatId);
    }
    try {
    if (isO3VoiceBeat(beat)) {
      if (
        effectiveGenerationMode(beat, activeScope.value.event_id) === 'voice_first'
        && lipsyncPublicHostReady !== true
      ) {
        const message = lipsyncPublicHostMessage?.trim() || LIPSYNC_HOSTING_SETUP_MESSAGE;
        bgLipsyncPublicHostReady.value = false;
        bgLipsyncPublicHostMessage.value = message;
        notifyLipsyncHostBlocked(message, lipsyncHostBlockToastRef);
        return;
      }
      if (elementCharRefApplies(beat, activeScope.value.event_id) && beatElementCharRefOk(beat) === false) {
        pushToast({
          kind: 'error',
          message: beatElementCharRefError(beat) ?? 'Char ref must match Element pose images before O3 generate.',
          source: 'bg-element-ref-block',
        });
        return;
      }
      const mode = effectiveGenerationMode(beat, activeScope.value.event_id);
      const promptToSave = (dialogueText ?? '').trim();
      if (!promptToSave) {
        pushToast({
          kind: 'error',
          message: 'Prompt box is empty — type the full O3 prompt before Generate.',
          source: 'bg-o3-empty-prompt',
        });
        return;
      }
      if (mode !== 'still_insert' && isStillInsertPromptText(promptToSave)) {
        pushToast({
          kind: 'error',
          message:
            'Still+TTS prompt cannot be submitted to Element native or voice-first O3 — '
            + 'switch to Still Insert mode or paste the @Image1 O3 motion prompt.',
          source: 'bg-o3-still-prompt-block',
        });
        return;
      }
      if (mode !== 'still_insert' && promptToSave.length < 80) {
        pushToast({
          kind: 'error',
          message:
            `Prompt is too short (${promptToSave.length} chars) — paste the full @Image1 / @Image2 O3 prompt before Generate.`,
          source: 'bg-o3-prompt-too-short',
        });
        return;
      }
      if (mode !== 'still_insert' && !/@image2/i.test(promptToSave)) {
        pushToast({
          kind: 'error',
          message:
            'O3 prompt must include the background (Scene from @Image2) — what you see in the box is what submits.',
          source: 'bg-o3-prompt-missing-bg-ref',
        });
        return;
      }
      const promptContradictions = lintKlingO3PromptContradictions(promptToSave);
      if (mode !== 'still_insert' && promptContradictions.length > 0) {
        pushToast({
          kind: 'error',
          message: promptContradictions.join(' '),
          source: 'bg-o3-prompt-self-contradictory',
        });
        return;
      }
      const saved = opts?.promptAlreadyPersisted
        ? true
        : await onUpdateBeatText(beatId, promptToSave);
      if (!saved) {
        pushToast({
          kind: 'error',
          message:
            'Could not save the prompt before Generate — your text is still in the box. '
            + 'Wait for the server, then click Generate again.',
          source: 'bg-o3-save-before-submit',
        });
        return;
      }
      const latestBeat = beatsRef.current.find((b) => b.beat_id === beatId) ?? beat;
      if (beatO3ServerJobInFlight(beatId, latestBeat, serverFlightCtx)) {
        pushToast({ kind: 'info', message: 'This beat is already generating.', source: 'bg-o3-beat-busy' });
        return;
      }
      await submitO3Voice(beatId, beatForO3Submit(beatId, latestBeat), promptToSave);
      return;
    }
    markO3SubmitPending(beatId);
    bgGptBatchSubmitPending.value = { ...bgGptBatchSubmitPending.value, [beatId]: true };
    try {
    if (activeJobId) {
      pushToast({ kind: 'info', message: 'A still-generation job is still running.', source: 'bg-stills-busy' });
      return;
    }
    const result = await pathappPatch<GptBatchSubmitResponse>(
      activeScope.value, 'bg_submit_gpt_batch', { beat_ids: [beatId] },
    );
    if (result.ok && result.data?.job_id) {
      bgActiveJobId.value = result.data.job_id;
      // Forecast: 3 calls × per-image cost.
      pushToast({
        kind: 'info',
        message: `Submitted (forecast $${(3 * PER_IMAGE_COST_USD).toFixed(2)})`,
        source: 'bg-submit',
      });
    } else {
      const msg = formatMutationError(result, 'Submit failed');
      if (msg) {
        pushToast({ kind: 'error', message: msg, source: 'bg-submit-error' });
      }
    }
    } finally {
      bgGptBatchSubmitPending.value = (prev => {
        const next = { ...prev };
        delete next[beatId];
        return next;
      })(bgGptBatchSubmitPending.value);
    }
    } finally {
      const timer = o3SubmitPendingTimersRef.current[beatId];
      if (timer) {
        window.clearTimeout(timer);
        delete o3SubmitPendingTimersRef.current[beatId];
      }
      bgO3SubmitPending.value = (prev => {
        const next = { ...prev };
        delete next[beatId];
        return next;
      })(bgO3SubmitPending.value);
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
      bgActiveNativeLipSyncJobs.value = {
        ...bgActiveNativeLipSyncJobs.value,
        [beatId]: result.data!.job_id!,
      };
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
    updateBgBeats((bs) => bs.map((b) => (b.beat_id === beatId ? { ...b, kling_o3_prompt: nextText } : b)));
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

  const onSelectO3Video = async (
    beatId: string,
    optionKey: string,
    opts?: { stillApprove?: boolean; draftOnly?: boolean },
  ) => {
    const beat = beatsRef.current.find((b) => b.beat_id === beatId);
    const stillInsert = beat ? isStillInsertBeat(beat) : false;
    const result = await pathappPatch<{
      beat?: BgBeat;
      pipeline_mismatch?: boolean;
      pipeline_mismatch_message?: string;
    }>(activeScope.value, 'bg_select_o3_video', {
      beat_id: beatId,
      option_key: optionKey,
      ...(stillInsert
        ? { still_approve: opts?.stillApprove === true && opts?.draftOnly !== true }
        : {}),
    });
    if (result.ok) {
      if (result.data?.pipeline_mismatch) {
        pushToast({
          kind: 'warning',
          message: result.data.pipeline_mismatch_message
            ?? 'Selected clip uses a different pipeline than the beat toggle — voice may not match.',
          source: 'bg-select-o3-pipeline-mismatch',
        });
      } else {
        pushToast({
          kind: 'success',
          message: opts?.stillApprove
            ? 'Still clip approved for stitch export'
            : stillInsert
              ? 'Selected still clip for preview and trim'
              : 'Kling clip approved for stitch export',
          source: 'bg-select-o3',
        });
      }
      if (result.data?.beat?.beat_id) {
        updateBgBeats((bs) => mergeBeatFromO3Poll(bs, result.data!.beat!));
      } else {
        await refreshState();
      }
    } else {
      await guardBeatPatchResult(
        beatId,
        result,
        formatMutationError(result, 'Select O3 video failed'),
        'bg-select-o3-error',
      );
    }
  };

  const onApplyO3Cut = async (
    beatId: string,
    slotIndex: number,
    trimStartS: number,
    trimBackS: number | null,
    opts?: { clear?: boolean; previewOnly?: boolean; silent?: boolean; videoPath?: string },
  ): Promise<{
    previewUrl?: string;
    rawDurationS?: number;
    effectiveDurationS?: number | null;
    trimBaked?: boolean;
    videoPath?: string;
  } | undefined> => {
    const result = await pathappPatch<{
      trim_start?: number;
      trim_back?: number | null;
      trim_end?: number;
      slot_index?: number;
      raw_duration_s?: number;
      effective_duration_s?: number | null;
      preview_video_url?: string;
      video_path?: string;
      trim_baked?: boolean;
      export_baked?: boolean;
    }>(activeScope.value, 'bg_kling_o3_trim', {
      beat_id: beatId,
      slot_index: slotIndex,
      trim_start: trimStartS,
      trim_back: trimBackS,
      clear: opts?.clear ?? false,
      preview_only: opts?.previewOnly ?? false,
      ...(opts?.videoPath ? { video_path: opts.videoPath } : {}),
    });
    if (result.ok) {
      const rawDurationGate = result.data?.raw_duration_s;
      const effectiveGate = result.data?.effective_duration_s;
      const shorteningRequested = !opts?.clear && (
        trimStartS > 0.05 || (trimBackS != null && trimBackS > 0.05)
      );
      const trimBaked = !!result.data?.trim_baked;
      if (
        shorteningRequested
        && !trimBaked
        && rawDurationGate != null
        && effectiveGate != null
        && effectiveGate >= rawDurationGate - 0.05
      ) {
        pushToast({
          kind: 'error',
          message: opts?.previewOnly
            ? 'Preview failed — trim would not shorten the clip. Adjust handles and Apply Cut.'
            : 'Trim not saved — window would keep the full clip. Check handles match the clip length.',
          source: 'bg-o3-cut-truth',
        });
        return undefined;
      }
      if (!opts?.previewOnly) {
        updateBgBeats((bs): BgBeat[] => bs.map((b) => {
          if (b.beat_id !== beatId) return b;
          const slots = buildFixedO3OptionSlots(b);
          const slotOpt = slots[slotIndex];
          const targetPath = opts?.videoPath ?? slotOpt?.video_path ?? '';
          const bakedPath = result.data?.video_path;
          const trimBaked = !!result.data?.trim_baked;
          const optionMatchesTarget = (o: GptOption | undefined): boolean => {
            if (!o?.video_path) return false;
            if (targetPath && o.video_path === targetPath) return true;
            if (bakedPath && o.video_path === bakedPath) return true;
            if (typeof o.slot_index === 'number' && o.slot_index === slotIndex) return true;
            const slotPath = slotOpt?.video_path;
            return !!slotPath && o.video_path === slotPath;
          };
          const nextOptions = (b.kling_o3_options ?? []).map((o) => {
            if (!o || !optionMatchesTarget(o)) return o;
            if (opts?.clear) {
              const {
                trim_start_s: _ts,
                trim_back_s: _tb,
                cut_start_s: _cs,
                cut_end_s: _ce,
                ...rest
              } = o as GptOption & Record<string, unknown>;
              return rest as GptOption;
            }
            if (trimBaked && bakedPath) {
              const {
                trim_start_s: _ts,
                trim_back_s: _tb,
                cut_start_s: _cs,
                cut_end_s: _ce,
                kling_o3_baked_path: _obp,
                kling_o3_baked_token: _obt,
                ...rest
              } = o as GptOption & Record<string, unknown>;
              return { ...rest, video_path: bakedPath } as GptOption;
            }
            const next: GptOption & Record<string, unknown> = {
              ...o,
              trim_start_s: result.data?.trim_start ?? trimStartS,
            };
            const back = result.data?.trim_back ?? trimBackS;
            if (back != null && back > 0.009) {
              next.trim_back_s = back;
            } else {
              delete next.trim_back_s;
            }
            delete next.cut_start_s;
            delete next.cut_end_s;
            return next as GptOption;
          });
          const activePath = b.kling_o3_video_path ?? '';
          const mirrorsActive = targetPath === activePath
            || bakedPath === activePath
            || slotOpt?.video_path === activePath;
          if (mirrorsActive && opts?.clear) {
            const restoredPath = result.data?.video_path;
            const beatAny = b as BgBeat & Record<string, unknown>;
            const {
              kling_o3_cut_start_s: _bcs,
              kling_o3_cut_end_s: _bce,
              kling_o3_trim_start: _bts,
              kling_o3_trim_back: _btb,
              kling_o3_baked_path: _bbp,
              kling_o3_baked_token: _bbt,
              ...beatRest
            } = beatAny;
            const clearedOptions = (b.kling_o3_options ?? []).map((o) => {
              if (!o || (targetPath && o.video_path !== targetPath && !restoredPath)) return o;
              const {
                trim_start_s: _ts,
                trim_back_s: _tb,
                cut_start_s: _cs,
                cut_end_s: _ce,
                kling_o3_baked_path: _obp,
                kling_o3_baked_token: _obt,
                o3_untrimmed_video_path: _oup,
                ...rest
              } = o as GptOption & Record<string, unknown>;
              return {
                ...rest,
                ...(restoredPath ? { video_path: restoredPath } : {}),
              } as GptOption;
            });
            return {
              ...beatRest,
              ...(restoredPath ? { kling_o3_video_path: restoredPath } : {}),
              kling_o3_options: clearedOptions,
            };
          }
          if (mirrorsActive && !opts?.clear) {
            const back = result.data?.trim_back ?? trimBackS;
            const nextBeat: BgBeat = {
              ...b,
              kling_o3_options: nextOptions,
              ...(trimBaked && bakedPath ? { kling_o3_video_path: bakedPath } : {}),
              ...(trimBaked
                ? {}
                : {
                  kling_o3_trim_start: result.data?.trim_start ?? trimStartS,
                  kling_o3_trim_back: back != null && back > 0.009 ? back : null,
                }),
            };
            delete (nextBeat as BgBeat & Record<string, unknown>).kling_o3_cut_start_s;
            delete (nextBeat as BgBeat & Record<string, unknown>).kling_o3_cut_end_s;
            if (trimBaked) {
              delete (nextBeat as BgBeat & Record<string, unknown>).kling_o3_trim_start;
              delete (nextBeat as BgBeat & Record<string, unknown>).kling_o3_trim_back;
            }
            return nextBeat;
          }
          if (trimBaked && bakedPath) {
            return { ...b, kling_o3_options: nextOptions };
          }
          return { ...b, kling_o3_options: nextOptions };
        }));
      }
      const dur = result.data?.effective_duration_s;
      if (!opts?.silent) {
        pushToast({
          kind: 'success',
          message: opts?.clear
            ? 'Trim cleared — full clip restored for export'
            : opts?.previewOnly
              ? (dur != null ? `Preview ready (${dur.toFixed(2)}s)` : 'Preview ready')
              : (dur != null
                ? `Trim applied — ${dur.toFixed(2)}s kept (start + end crop saved)`
                : 'Trim applied'),
          source: 'bg-o3-cut',
        });
      }
      const preview = result.data?.preview_video_url;
      const previewUrl = preview
        ? (preview.startsWith('http') ? preview : `${SERVER_BASE}${preview}`)
        : undefined;
      if (
        !opts?.previewOnly
        && !opts?.clear
        && shorteningRequested
        && previewUrl === undefined
      ) {
        pushToast({
          kind: 'info',
          message: 'Trim saved — preview clip failed to build. Press Preview Cut or Retry.',
          source: 'bg-o3-cut-preview-missing',
        });
      }
      const rawDurationS = result.data?.raw_duration_s;
      const effectiveDurationS = result.data?.effective_duration_s;
      const bakedVideoPath = result.data?.video_path;
      return {
        ...(previewUrl !== undefined ? { previewUrl } : {}),
        ...(rawDurationS !== undefined ? { rawDurationS } : {}),
        ...(effectiveDurationS !== undefined ? { effectiveDurationS } : {}),
        ...(trimBaked ? { trimBaked: true as const } : {}),
        ...(bakedVideoPath ? { videoPath: bakedVideoPath } : {}),
      };
    }
    if (opts?.silent && opts?.previewOnly) {
      return undefined;
    }
    await guardBeatPatchResult(
      beatId,
      result,
      formatMutationError(result, 'Cut failed'),
      'bg-o3-cut-error',
    );
    return undefined;
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
      updateBgBeats((bs) => bs.map((b) => (
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
    if (activeSegment) {
      const [event_id, phase] = activeSegment.split('|');
      return { event_id, phase };
    }
    if (isMilestoneScope && segments.length > 0) {
      return {
        event_id: String(segments[0].event_id),
        phase: String(segments[0].phase),
      };
    }
    return { event_id: '1', phase: 'pre' };
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
    if (isMilestoneScope) return 'standalone';
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
  }, [activeSegment, activeTargetVideo.value, isMilestoneScope]);

  const exportScopeKey = useMemo(() => {
    const { event_id, phase } = segmentCtx();
    return bgExportScopeKey(arcNumber, event_id, phase, stitchSlotForSegment);
  }, [activeSegment, arcNumber, stitchSlotForSegment]);

  const stitchExportTooltip = useMemo(
    () => stitchExportBlockTooltip(beats, stitchSlotForSegment),
    [beats, stitchSlotForSegment],
  );

  const onReorderBeat = async (beatId: string, direction: 'up' | 'down') => {
    if (!activeSegment || reorderBusyBeatId) return;
    const idx = beats.findIndex((b) => b.beat_id === beatId);
    if (idx < 0) return;
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= beats.length) return;
    const { event_id, phase } = segmentCtx();
    const nextIds = beats.map((b) => b.beat_id);
    [nextIds[idx], nextIds[swapIdx]] = [nextIds[swapIdx], nextIds[idx]];
    setReorderBusyBeatId(beatId);
    try {
      const result = await pathappPatch(activeScope.value, 'bg_reorder_beats', {
        beat_ids: nextIds,
        arc_number: arcNumber,
        event_id,
        phase,
        ...activeScopeQueryParams(),
        scope_phase: phase,
        scope_arc_number: arcNumber,
      });
      if (result.ok) {
        updateBgBeats((bs) => {
          const byId = new Map(bs.map((b) => [b.beat_id, b]));
          return nextIds
            .map((id) => byId.get(id))
            .filter((b): b is BgBeat => !!b);
        });
        setActiveNavIndex((prev) => {
          if (prev === null) return prev;
          if (prev === idx) return swapIdx;
          if (prev === swapIdx) return idx;
          return prev;
        });
        pushToast({
          kind: 'success',
          message: `Beat #${idx + 1} moved ${direction}`,
          source: 'bg-reorder',
        });
      } else {
        pushToast({
          kind: 'error',
          message: formatMutationError(result, 'Reorder beats failed'),
          source: 'bg-reorder-error',
        });
      }
    } finally {
      setReorderBusyBeatId(null);
    }
  };

  const finishExportTerminal = useCallback((data: BgExportPollResult) => {
    const scopeEventId = activeScope.value.event_id;
    writeBgExportBusyLatch(scopeEventId, exportScopeKey, null);
    setActiveExportJobId(null);
    setStitcherExportStatus('idle');
    setExportProgressMessage('');

    const toastKey = `${data.job_id ?? 'unknown'}:${data.status ?? 'unknown'}`;
    if (exportTerminalToastRef.current === toastKey) return;
    exportTerminalToastRef.current = toastKey;

    if (data.status === 'done') {
      const { slotKey, warnings } = bgExportTerminalSuccess(data);
      if (stitchExportKeptExistingWarning(warnings)) {
        pushToast({
          kind: 'error',
          message: 'Send to Stitcher did not replace the slot — stored video is newer. Hard refresh Stitcher or re-export.',
          source: 'bg-kling-export-kept-existing',
        });
        return;
      }
      const slot = slotKey ?? stitchSlotForSegment;
      void (async () => {
        await ensureStitchJobSession(scopeEventId, {
          force: true,
          projectType: activeProjectType.value,
          milestoneId: activeMilestoneId.value,
        });
        if (isStitchUiSlotKey(slot)) {
          const stitchSessionKey = stitchJobSessionKey(
            scopeEventId,
            activeProjectType.value,
            activeMilestoneId.value,
          );
          writePersistedTrackSlot(stitchSessionKey, slot);
          notifyStitchSlotExportApplied(stitchSessionKey, slot);
        }
        stitcherRefreshTick.value += 1;
        pushToast({
          kind: 'success',
          message: `Sent to Stitcher → ${slot} slot (canonical tail + intro fades when applicable)`,
          source: 'bg-kling-export',
        });
      })();
      return;
    }

    const err = data.error
      ?? data.result?.error_message
      ?? data.message
      ?? 'Export failed';
    pushToast({
      kind: 'error',
      message: data.status === 'interrupted'
        ? `Send to Stitcher interrupted: ${err}`
        : `Send to Stitcher failed: ${err}`,
      source: data.status === 'interrupted' ? 'bg-kling-export-interrupted' : 'bg-kling-export-error',
    });
  }, [exportScopeKey, stitchSlotForSegment]);

  useEffect(() => {
    const scopeEventId = activeScope.value.event_id;
    const latched = readBgExportBusyLatch(scopeEventId, exportScopeKey);
    if (latched && !activeExportJobId) {
      setActiveExportJobId(latched);
      setStitcherExportStatus('exporting');
      setExportProgressMessage('Resuming export…');
    }
  }, [activeScope.value.event_id, exportScopeKey]);

  useEffect(() => {
    if (!activeExportJobId) return;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      const res = await apiGet<BgExportPollResult>('bg_poll_export_to_stitcher', {
        job_id: activeExportJobId,
        ...activeScopeQueryParams(),
      });
      if (cancelled) return;
      if (!res.ok || !res.data) {
        pushToast({
          kind: 'error',
          message: `Send to Stitcher poll error: ${res.error ?? `HTTP ${res.status}`}`,
          source: 'bg-kling-export-poll-error',
        });
        writeBgExportBusyLatch(activeScope.value.event_id, exportScopeKey, null);
        setActiveExportJobId(null);
        setStitcherExportStatus('idle');
        setExportProgressMessage('');
        return;
      }
      setExportProgressMessage(bgExportStatusMessage(res.data));
      if (!isBgExportStatusTerminal(res.data.status)) {
        timer = window.setTimeout(poll, BG_EXPORT_POLL_INTERVAL_MS);
        return;
      }
      finishExportTerminal(res.data);
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [activeExportJobId, exportScopeKey, finishExportTerminal]);

  const onSendToStitcher = async () => {
    if (!activeSegment || !allBeatsExportReady || stitcherExportStatus !== 'idle') return;
    const { event_id, phase } = segmentCtx();
    setStitcherExportStatus('submitting');
    setExportProgressMessage('Submitting export…');
    try {
      const result = await pathappPatch<BgExportPollResult>(
        activeScope.value,
        'bg_export_to_stitcher',
        {
          arc_number: arcNumber,
          event_id,
          phase,
          slot_key: stitchSlotForSegment,
        },
      );
      if (!result.ok) {
        const hint = result.hint?.trim();
        const detail = result.error_message ?? result.error ?? 'unknown error';
        pushToast({
          kind: 'error',
          message: hint
            ? `Send to Stitcher failed: ${hint}`
            : `Send to Stitcher failed: ${detail}`,
          source: 'bg-kling-export-error',
        });
        setStitcherExportStatus('idle');
        setExportProgressMessage('');
        return;
      }
      const jobId = result.data?.job_id;
      if (!jobId) {
        pushToast({
          kind: 'error',
          message:
            'Send to Stitcher failed: server returned no job_id '
            + '(export was not queued — server may have been restarting)',
          source: 'bg-kling-export-error',
        });
        setStitcherExportStatus('idle');
        setExportProgressMessage('');
        return;
      }
      writeBgExportBusyLatch(activeScope.value.event_id, exportScopeKey, jobId);
      setActiveExportJobId(jobId);
      setStitcherExportStatus('exporting');
      setExportProgressMessage(bgExportStatusMessage(result.data));
      if (result.data?.reattach) {
        pushToast({
          kind: 'info',
          message: 'Reattached to in-progress Send to Stitcher',
          source: 'bg-kling-export-reattach',
        });
      }
    } catch (e) {
      pushToast({
        kind: 'error',
        message: `Send to Stitcher failed: ${e instanceof Error ? e.message : String(e)}`,
        source: 'bg-kling-export-error',
      });
      setStitcherExportStatus('idle');
      setExportProgressMessage('');
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
      const msg = formatMutationError(result, 'Accept All failed');
      if (msg) {
        pushToast({
          kind: 'error',
          message: msg,
          source: 'bg-accept-all-error',
        });
      }
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

  const authorityBadgeLabel = useMemo(
    () => beatGenAuthorityBadgeLabel(
      activeScope.value.event_id,
      effectiveScopeVideoRole(),
      isMilestoneScope ? (activeMilestoneId.value ?? 'milestone') : null,
    ),
    [activeScope.value.event_id, activeTargetVideo.value, isMilestoneScope, activeMilestoneId.value, activeSegment],
  );

  return (
    <section class="mn-tab-pane mn-bg-pane" data-testid="pane-bg">
      <header class="mn-pane-header">
        <h2>Beat Generator</h2>
        <span class="mn-scope-chip" data-testid="bg-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
        <span class="mn-scope-chip" data-testid="bg-authority-badge" title="Beat Gen write authority">
          {authorityBadgeLabel}
        </span>
        {isVoiceFirstSegment ? (
          <span class="mn-scope-chip" data-testid="bg-voice-first-badge" title="Generate uses ElevenLabs TTS + silent O3 + lipsync (720 delivery)">
            Voice: ElevenLabs
          </span>
        ) : null}
        {isMilestoneScope ? (
          <span class="mn-scope-chip" data-testid="bg-milestone-segment-chip">
            Skeleton: {milestoneSegmentLabel}
          </span>
        ) : null}
      </header>

      <div class="mn-bg-toolbar" data-testid="bg-toolbar">
        {!isMilestoneScope ? (
          <>
        <Select
          id="bg-arc"
          label="Arc"
          options={[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => ({ value: String(n), label: `Arc ${n}` }))}
          value={String(arcNumber)}
          onChange={(v) => {
            const n = Number(v);
            bgArcNumber.value = n;
            void ensureBgSession(activeScope.value.event_id, effectiveScopeVideoRole(), { force: true, arcNumber: n });
          }}
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
          </>
        ) : null}
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid="bg-extract-btn"
          onClick={onExtractBeats}
          disabled={(!activeSegment && !isMilestoneScope) || extractStatus === 'sending'}
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
          disabled={!activeSegment && !isMilestoneScope}
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
        <>
          {voiceFirstLipsyncHostBlocked(lipsyncPublicHostReady, beats, activeScope.value.event_id) ? (
            <div
              class="mn-bg-lipsync-host-setup"
              data-testid="bg-lipsync-host-setup"
              role="alert"
            >
              {lipsyncPublicHostMessage?.trim() || LIPSYNC_HOSTING_SETUP_MESSAGE}
            </div>
          ) : null}
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
              lipsyncPublicHostReady={lipsyncPublicHostReady}
              nativeExperimentBusy={!!activeNativeLipSyncJobs[b.beat_id]}
              onDelete={() => onDeleteBeat(b.beat_id)}
              onUpdateText={(t) => onUpdateBeatText(b.beat_id, t)}
              onUpdateSpeaker={(s) => onUpdateBeatSpeaker(b.beat_id, s)}
              onSetGenerationMode={(mode) => onSetBeatGenerationMode(b.beat_id, mode)}
              onBeginGenerateSubmit={() => markO3SubmitPending(b.beat_id)}
              onAbortGenerateSubmit={() => clearO3SubmitPending(b.beat_id)}
              onGenerate={(dialogueText, opts) => onGenerateBatch(b.beat_id, dialogueText, opts)}
              onAccept={(optionKey) => onAcceptOption(b.beat_id, optionKey)}
              onSelectO3Video={(optionKey) => onSelectO3Video(
                b.beat_id,
                optionKey,
                isStillInsertBeat(b) ? { draftOnly: true } : undefined,
              )}
              onApproveStill={(optionKey) => onSelectO3Video(b.beat_id, optionKey, { stillApprove: true })}
              onApplyO3Cut={(slotIndex, trimStartS, trimBackS, opts) => onApplyO3Cut(b.beat_id, slotIndex, trimStartS, trimBackS, opts)}
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
                updateBgBeats((bs) => bs.map((bb): BgBeat => {
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
                  if (isStillInsertBeat(bb) && (patch.local_path || (patch as { abs_path?: string }).abs_path)) {
                    const ap = patch.local_path ?? (patch as { abs_path?: string }).abs_path ?? '';
                    const stillRef: RefDisplay = { abs_path: ap };
                    const refKey = patch.key || bb.accepted_image_key || undefined;
                    if (refKey) stillRef.key = refKey;
                    if (patch.thumb_b64) stillRef.thumb_b64 = patch.thumb_b64;
                    next.bg_ref_image = stillRef;
                    next._derived = {
                      ...(bb._derived ?? {}),
                      still_scene_display: stillRef,
                    };
                  }
                  return next;
                }));
                // RC1 fix — clear stale pollResultForBeat so the persisted
                // gpt_options (just patched above) become the visible source.
                bgPollResults.value = (prev => {
                  if (!(b.beat_id in prev)) return prev;
                  const next = { ...prev };
                  delete next[b.beat_id];
                  return next;
                })(bgPollResults.value);
              }}
              onPatchRefImage={(refField, patch) => {
                onPatchRefImageForBeat(b.beat_id, refField, patch);
              }}
              canMoveUp={i > 0}
              canMoveDown={i < beats.length - 1}
              reorderBusy={reorderBusyBeatId === b.beat_id}
              onMoveUp={() => { void onReorderBeat(b.beat_id, 'up'); }}
              onMoveDown={() => { void onReorderBeat(b.beat_id, 'down'); }}
            />
          ))}
          </ol>
        </div>
        </>
      )}

      <footer class="mn-pane-footer">
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid="bg-export-stitcher-btn"
          title={stitchExportTooltip}
          onClick={onSendToStitcher}
          disabled={(!activeSegment && !isMilestoneScope) || !allBeatsExportReady || stitcherExportStatus !== 'idle'}
        >
          {stitcherExportStatus === 'submitting' || stitcherExportStatus === 'exporting' ? (
            <><Spinner size="sm" inline /> {exportProgressMessage || 'Sending…'}</>
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
        approveError={approveBeatPlanError}
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
          This removes <strong>only this beat&apos;s</strong> prompt, refs, and options from the sidecar.
          Other beats are unchanged — list order shifts, but each beat keeps its own saved prompt.
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
            <button
              type="button"
              class="mn-btn"
              data-testid="bg-voice-drift-cancel"
              disabled={modalState.kind === 'voice-drift-confirm' && !!modalState.submitting}
              onClick={closeModal}
            >
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="bg-voice-drift-confirm"
              disabled={modalState.kind === 'voice-drift-confirm' && !!modalState.submitting}
              onClick={() => { void confirmVoiceDriftSubmit(); }}
            >
              {modalState.kind === 'voice-drift-confirm' && modalState.submitting ? (
                <><Spinner size="sm" inline /> Submitting…</>
              ) : (
                'Generate with current registry voice'
              )}
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
        class={PLAYBACK_VIDEO_ANTI_BANDING_CLASS}
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
  lipsyncPublicHostReady?: boolean | null;
  onDelete: () => void;
  onUpdateText: (next: string) => void | Promise<boolean>;
  // LD CHARACTER_DROPDOWN_RESTORED_V1 — speaker dropdown change.
  onUpdateSpeaker: (next: string) => void;
  onSetGenerationMode: (mode: BeatGenerationMode) => void;
  onBeginGenerateSubmit?: () => void;
  onAbortGenerateSubmit?: () => void;
  onGenerate: (
    dialogueText?: string,
    opts?: { promptAlreadyPersisted?: boolean },
  ) => void | Promise<void>;
  onAccept: (optionKey: string) => void;
  onSelectO3Video: (optionKey: string) => void;
  onApproveStill: (optionKey: string) => void;
  onApplyO3Cut: (
    slotIndex: number,
    trimStartS: number,
    trimBackS: number | null,
    opts?: { clear?: boolean; previewOnly?: boolean; silent?: boolean; videoPath?: string },
  ) => Promise<{
    previewUrl?: string;
    rawDurationS?: number;
    effectiveDurationS?: number | null;
    trimBaked?: boolean;
    videoPath?: string;
  } | undefined>;
  onApplyO3Trim: (
    trimStart: number,
    trimBack: number | null,
    clear?: boolean,
  ) => Promise<{
    previewUrl?: string;
    rawDurationS?: number;
    effectiveDurationS?: number | null;
  } | undefined>;
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
  canMoveUp: boolean;
  canMoveDown: boolean;
  reorderBusy: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

function BeatGenCard({
  index, beat, eventId, videoRole, pollResultForBeat, busy, nativeExperimentBusy,
  o3IntentSnapshot, o3SubmitAudit, o3WarningMessage, lipsyncPublicHostReady,
  onDelete, onUpdateText, onUpdateSpeaker, onSetGenerationMode,
  onBeginGenerateSubmit, onAbortGenerateSubmit,
  onGenerate, onAccept,
  onSelectO3Video, onApproveStill, onApplyO3Cut, onApplyO3Trim, onSetReplaceSlot, onSubmitNativeLipSyncExperiment,
  onEditChip, onInsertAfter, onRemoveRef, onAlignElementRef, onAddElementPose, onRefresh, onBeatMissing,
  onPatchOptionTile, onPatchRefImage,
  canMoveUp, canMoveDown, reorderBusy, onMoveUp, onMoveDown,
}: BeatGenCardProps) {
  const stillInsert = isStillInsertBeat(beat);
  const intentLockedPrompt = busy && !stillInsert
    ? (o3IntentSnapshot?.prompt?.verbatim ?? o3SubmitAudit?.prompt_excerpt ?? null)
    : null;
  const externalPrompt = intentLockedPrompt ?? beatPromptText(beat, eventId);
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
  const [chips, setChips] = useState<string[]>(extractStageChips(beatPromptText(beat, eventId)));

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

  const optionsToShow = resolveBeatOptionsToShow(beat, eventId, pollResultForBeat);
  const replaceSlotIndex = beat.kling_o3_replace_slot_index ?? 0;
  const o3FailureMessage = resolveO3FailureBanner(beat, lipsyncPublicHostReady ?? null, eventId);
  const nativeProfile = beat.kling_native_lipsync_experiment_output_profile;
  const nativeDims = nativeProfile?.width && nativeProfile?.height
    ? `${nativeProfile.width}x${nativeProfile.height}`
    : null;
  const nativeStatus = beat.kling_native_lipsync_experiment_status ?? null;
  // Native LipSync experiment is dev-only QA — hidden from producer UI so it cannot
  // be mistaken for the canonical Generate path (Element O3 + 720 delivery).
  const showNativeExperimentCard = false;

  const magicStillSource = displayStillScenePath(beat) ?? resolveBgMagicStillSourcePath(beat, eventId);
  const magicVideoSource = beat.kling_o3_magic_video_source_path ?? beat.kling_o3_video_path ?? null;
  const magicStillPreviewUrl = resolveBgMagicStillPreviewUrl(beat, eventId);
  const magicVideoPreviewUrl = resolveBgMagicVideoPreviewUrl(beat, eventId);
  const [magicPreviewMode, setMagicPreviewMode] = useState<'still' | 'video' | null>(null);
  const [stillPreviewAutoplay, setStillPreviewAutoplay] = useState(false);
  const generationMode = effectiveGenerationMode(beat, eventId);
  const charRefDisplay = displayCharRef(beat);
  const bgRefDisplay = displayBgRef(beat, stillInsert);
  const mutationsLocked = beatOperatorMutationsLocked(beat) || busy;
  const hasStillSource = !!magicStillSource
    || !!beat._derived?.still_scene_display
    || optionsToShow.some((o) => o?.local_path || o?.thumb_b64);
  const showStillClipHint = stillInsert && !beat.kling_o3_video_path && hasStillSource;
  const stillNeedsStitchApprove = stillBeatNeedsStitchApprove(beat);
  const stillApproveOptionKey = stillNeedsStitchApprove
    ? resolveStillStitchApproveOptionKey(beat)
    : null;
  const elementCharRefOk = beatElementCharRefOk(beat);
  const elementCharRefErr = beatElementCharRefError(beat);
  const elementCharRefBlocked = elementCharRefApplies(beat, eventId) && elementCharRefOk === false;
  const charRefHasImage = !!(
    charRefDisplay
    && (charRefDisplay.thumb_b64 || charRefDisplay.abs_path || charRefDisplay.key)
  );
  const showAddElementPose = elementCharRefApplies(beat, eventId) && charRefHasImage;

  return (
    <li
      class="mn-bg-beat-card"
      data-testid={`bg-beat-card-${index}`}
      data-beat-id={beat.beat_id}
      data-kling-stitch-readiness-v1={KLING_STITCH_READINESS_V1}
    >
      <div class="mn-bg-beat-meta">
        <span class="mn-bg-beat-index">#{index + 1}</span>
        <span class="mn-bg-beat-reorder" data-testid={`bg-beat-reorder-${index}`}>
          <button
            type="button"
            class="mn-btn mn-btn-small mn-bg-beat-reorder-btn"
            data-testid={`bg-beat-move-up-${index}`}
            disabled={!canMoveUp || busy || reorderBusy}
            title="Move beat earlier in segment"
            aria-label={`Move beat ${index + 1} up`}
            onClick={onMoveUp}
          >
            ↑
          </button>
          <button
            type="button"
            class="mn-btn mn-btn-small mn-bg-beat-reorder-btn"
            data-testid={`bg-beat-move-down-${index}`}
            disabled={!canMoveDown || busy || reorderBusy}
            title="Move beat later in segment"
            aria-label={`Move beat ${index + 1} down`}
            onClick={onMoveDown}
          >
            ↓
          </button>
        </span>
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
            aria-label={`Generation mode for beat ${beat.beat_id}`}
          >
            <button
              type="button"
              class={`mn-btn mn-btn-small${generationMode === 'still_insert' ? ' mn-btn-primary' : ''}`}
              data-testid={`bg-pipeline-still-${index}`}
              aria-pressed={generationMode === 'still_insert' ? 'true' : 'false'}
              disabled={busy}
              title="Still image + TTS (smooth zoom 1.0→1.06×), no Kling O3"
              onClick={() => {
                if (generationMode !== 'still_insert') onSetGenerationMode('still_insert');
              }}
            >
              Still + TTS
            </button>
            <button
              type="button"
              class={`mn-btn mn-btn-small${generationMode === 'voice_first' ? ' mn-btn-primary' : ''}`}
              data-testid={`bg-pipeline-voice-first-${index}`}
              aria-pressed={generationMode === 'voice_first' ? 'true' : 'false'}
              disabled={busy}
              title="ElevenLabs TTS → silent O3 → lipsync → 720 delivery"
              onClick={() => {
                if (generationMode !== 'voice_first') onSetGenerationMode('voice_first');
              }}
            >
              Voice-first
            </button>
            <button
              type="button"
              class={`mn-btn mn-btn-small${generationMode === 'element_native' ? ' mn-btn-primary' : ''}`}
              data-testid={`bg-pipeline-element-native-${index}`}
              aria-pressed={generationMode === 'element_native' ? 'true' : 'false'}
              disabled={busy}
              title="O3 Pro Element with native voice baked in"
              onClick={() => {
                if (generationMode !== 'element_native') onSetGenerationMode('element_native');
              }}
            >
              Element native
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
      {busy && !stillInsert && (o3SubmitAudit || o3IntentSnapshot) ? (
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
      {pipelineSelectionMismatchMessage(beat) ? (
        <div
          class="mn-bg-o3-pipeline-mismatch-banner"
          data-testid={`bg-o3-pipeline-mismatch-${index}`}
          style="margin: 4px 0 8px; padding: 8px; background: #450a0a; border: 1px solid #f87171; border-radius: 6px; color: #fecaca; font-size: 12px;"
        >
          {pipelineSelectionMismatchMessage(beat)}
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
          refImg={charRefDisplay}
          testId={`bg-char-ref-${index}`}
          beatId={beat.beat_id}
          refField="reference_image"
          mutationsLocked={mutationsLocked}
          {...(elementCharRefBlocked
            ? {
              elementRefError: elementCharRefInlineHint(elementCharRefErr),
              ...(elementCharRefErr ? { elementRefErrorDetail: elementCharRefErr } : {}),
              showAlignElementRef: true,
              onAlignElementRef,
            }
            : {})}
          {...(showAddElementPose
            ? { showAddElementPose: true, onAddElementPose }
            : {})}
          suppressElementGateUi={generationMode === 'avatar_pro'}
          onRemoveRef={onRemoveRef}
          onRefresh={onRefresh}
          onBeatMissing={onBeatMissing}
          onPatchRefImage={onPatchRefImage}
        />
        {(stillInsert || generationMode !== 'avatar_pro') && (
        <BgRefSlot
          label={stillInsert ? 'Still scene' : 'BG ref'}
          refImg={bgRefDisplay}
          testId={`bg-bg-ref-${index}`}
          beatId={beat.beat_id}
          refField="bg_ref_image"
          mutationsLocked={mutationsLocked}
          onRemoveRef={onRemoveRef}
          onRefresh={onRefresh}
          onBeatMissing={onBeatMissing}
          onPatchRefImage={onPatchRefImage}
        />
        )}
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid={`bg-generate-btn-${index}`}
          onClick={async () => {
            onBeginGenerateSubmit?.();
            const saved = await promptField.flushSave();
            if (!saved) {
              onAbortGenerateSubmit?.();
              if (beatSaveBlockedRef.current.has(beat.beat_id)) {
                if (!beatSaveNotFoundToastRef.current.has(beat.beat_id)) {
                  beatSaveNotFoundToastRef.current.add(beat.beat_id);
                  pushToast({
                    kind: 'warning',
                    message: beatMissingToastMessage(beat.beat_id),
                    source: 'bg-generate-beat-missing',
                    ttlMs: BEAT_MISSING_TOAST_MS,
                  });
                }
              } else {
                pushToast({
                  kind: 'warning',
                  message: 'Could not save the prompt before Generate — wait for beat state to load, then try again.',
                  source: 'bg-generate-save-blocked',
                });
              }
              return;
            }
            await onGenerate(promptField.getText(), { promptAlreadyPersisted: true });
          }}
          disabled={busy || elementCharRefBlocked}
          title={elementCharRefBlocked ? elementCharRefInlineHint(elementCharRefErr) : undefined}
        >
          {busy ? (
            stillInsert ? (
              <><Spinner size="sm" inline /> Building still clip (+ TTS)…</>
            ) : (
              <><Spinner size="sm" inline /> Generating{o3IntentSnapshot?.generation?.slot ? ` ${o3IntentSnapshot.generation.slot}` : ''}…</>
            )
          ) : isStillInsertBeat(beat) ? (
            'Build still video (+ TTS)'
          ) : isO3VoiceBeat(beat) ? (
            o3GenerateButtonLabel(generationMode)
          ) : (
            'Generate 3 options'
          )}
        </button>
      </div>

      {showStillClipHint ? (
        <p class="mn-dim mn-bg-still-clip-hint" data-testid={`bg-still-clip-hint-${index}`}>
          Still ready — click <strong>Build still video (+ TTS)</strong> above for smooth zoom
          (1.0→1.06×) and dialogue audio. Trim below, then use <strong>Approve still for stitch</strong>.
        </p>
      ) : null}

      {stillNeedsStitchApprove && stillApproveOptionKey ? (
        <div
          class="mn-bg-still-approve-banner"
          data-testid={`bg-still-approve-banner-${index}`}
        >
          <p class="mn-dim">
            Still clip built — trim in the option tile if needed, then approve so
            <strong> Send Beat Gen to Stitcher</strong> can include this beat.
          </p>
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid={`bg-still-approve-banner-btn-${index}`}
            onClick={() => onApproveStill(stillApproveOptionKey)}
          >
            Approve still for stitch
          </button>
        </div>
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
        onPreviewMagicVideo={magicVideoPreviewUrl ? () => {
          setMagicPreviewMode('video');
          requestAnimationFrame(() => {
            document.querySelector(`[data-testid="bg-magic-preview-video-${index}"]`)
              ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          });
        } : undefined}
        onMagicStillCleared={() => {
          setMagicPreviewMode(null);
          setStillPreviewAutoplay(false);
          onRefresh();
        }}
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
          <video
            controls
            preload="metadata"
            src={magicStillPreviewUrl}
            class={PLAYBACK_VIDEO_ANTI_BANDING_CLASS}
          />
          <p class="mn-dim">No storyboard beat id — TTS preview unavailable.</p>
        </div>
      ) : null}
      {magicPreviewMode === 'video' && magicVideoPreviewUrl ? (
        <div class="mn-bg-magic-preview" data-testid={`bg-magic-preview-video-${index}`}>
          <video
            controls
            preload="metadata"
            src={magicVideoPreviewUrl}
            class={PLAYBACK_VIDEO_ANTI_BANDING_CLASS}
          />
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
                onSelectO3Video(optionKey);
              } else if (opt.key) onAccept(opt.key);
            }}
            onRefresh={onRefresh}
            onPatchOptionTile={onPatchOptionTile}
            stillInsert={stillInsert}
            klingO3Status={beat.kling_o3_status ?? null}
            videoCacheKey={`${opt?.key ?? i}|${opt?.video_path ?? ''}|${beat.kling_o3_selected_at ?? beat.beat_id}`}
            onApproveStill={(optionKey) => onApproveStill(optionKey)}
            cutStartS={opt?.cut_start_s ?? 0}
            cutEndS={opt?.cut_end_s ?? 0}
            trimStartS={opt?.trim_start_s ?? 0}
            trimBackS={opt?.trim_back_s ?? 0}
            onApplyO3Cut={onApplyO3Cut}
            trimStart={beat.kling_o3_trim_start ?? 0}
            trimBack={beat.kling_o3_trim_back ?? null}
            onApplyO3Trim={onApplyO3Trim}
            replaceSelected={i === replaceSlotIndex}
            onSetReplaceSlot={() => onSetReplaceSlot(i)}
            showReplaceOnRegen={!!beat.speaker}
            overrideVideoUrl={resolveO3TileMagicOverrideUrl(beat, opt, eventId)}
          />
        ))}
      </div>
      {(beat.kling_o3_disk_delivery_count ?? 0) > 0 && beat.kling_o3_clips_dir ? (
        <p class="mn-dim mn-bg-o3-disk-hint" data-testid={`bg-o3-disk-hint-${index}`}>
          {(beat.kling_o3_element_delivery_count ?? beat.kling_o3_disk_delivery_count ?? 0)} element O3 clip
          {(beat.kling_o3_element_delivery_count ?? beat.kling_o3_disk_delivery_count ?? 0) === 1 ? '' : 's'} on disk
          {(beat.kling_o3_disk_delivery_count ?? 0) > (beat.kling_o3_element_delivery_count ?? beat.kling_o3_disk_delivery_count ?? 0)
            ? ` (+${(beat.kling_o3_disk_delivery_count ?? 0) - (beat.kling_o3_element_delivery_count ?? beat.kling_o3_disk_delivery_count ?? 0)} POV/still aux)`
            : ''}
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
  mutationsLocked?: boolean;
  elementRefError?: string;
  elementRefErrorDetail?: string;
  showAlignElementRef?: boolean;
  onAlignElementRef?: () => void;
  showAddElementPose?: boolean;
  onAddElementPose?: () => void;
  /** Avatar Pro beats skip Element registration toasts/warnings. */
  suppressElementGateUi?: boolean;
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
  suppressElementGateUi,
  onRemoveRef, onRefresh, onBeatMissing, onPatchRefImage, mutationsLocked,
}: BgRefSlotPropsExt) {
  const hasImage = !!refImg && (refImg.thumb_b64 || refImg.abs_path || refImg.key);
  const dropHandlers = makeDropTarget(
    async (payload) => {
      if (mutationsLocked) {
        pushToast({
          kind: 'warning',
          message: 'Beat is locked while a job is running — wait for it to finish.',
          source: 'bg-ref-drop-busy',
        });
        return;
      }
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
        if (isClientBundleStaleError(result)) {
          return;
        }
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
        && !suppressElementGateUi
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
  const dropRef = useRef<HTMLDivElement>(null);
  useDropTargetCapture(dropRef, dropHandlers, [dropHandlers]);
  return (
    <div class="mn-bg-ref-slot-wrap" data-testid={`${testId}-wrap`}>
      <div
        ref={dropRef}
        class={`mn-bg-ref-slot mn-drop-target${hasImage ? ' has-image' : ''}`}
        data-testid={testId}
      >
        <span class="mn-bg-ref-slot-label">{label}</span>
        {hasImage ? (
          <button
            type="button"
            class="mn-bg-ref-remove-btn"
            data-testid={`${testId}-remove`}
            disabled={mutationsLocked}
            onClick={(e) => {
              e.stopPropagation();
              if (mutationsLocked) return;
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
  cutStartS: number;
  cutEndS: number;
  trimStartS?: number;
  trimBackS?: number;
  onApplyO3Cut: (
    slotIndex: number,
    trimStartS: number,
    trimBackS: number | null,
    opts?: { clear?: boolean; previewOnly?: boolean; silent?: boolean; videoPath?: string },
  ) => Promise<{
    previewUrl?: string;
    rawDurationS?: number;
    effectiveDurationS?: number | null;
    trimBaked?: boolean;
    videoPath?: string;
  } | undefined>;
  trimStart: number;
  trimBack: number | null;
  onApplyO3Trim: (
    trimStart: number,
    trimBack: number | null,
    clear?: boolean,
  ) => Promise<{
    previewUrl?: string;
    rawDurationS?: number;
    effectiveDurationS?: number | null;
  } | undefined>;
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
  cutStartS: _cutStartS, cutEndS: _cutEndS, trimStartS = 0, trimBackS = 0, onApplyO3Cut, trimStart, trimBack, onApplyO3Trim,
  replaceSelected, onSetReplaceSlot, showReplaceOnRegen,
  overrideVideoUrl, stillInsert, klingO3Status, videoCacheKey, onApproveStill,
}: BgOptionTilePropsExt) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const trimPlaybackListenerRef = useRef<((this: HTMLVideoElement, ev: Event) => void) | null>(null);
  const rawDurationRef = useRef<number | null>(null);
  const showNumericTrim = showBgO3NumericTrimControls();
  const trimDraft = useBgO3TrimNumericDraft(beatId, optionIndex, trimStart || 0, trimBack);
  const cutSession = useBgO3CutSession(beatId, optionIndex);
  const {
    trimStartDraft,
    trimBackDraft,
    trimDraftDirty,
    setTrimStartDraft,
    setTrimBackDraft,
    clearDirtyAfterSave,
  } = trimDraft;
  const { pendingCut, setPendingCut, onOverlayDragStart, onOverlayDragEnd, clearPendingCut } = cutSession;
  const savedTrimStart = trimStart || 0;
  const savedTrimBack = trimBack ?? 0;
  const [videoLoadError, setVideoLoadError] = useState(false);
  const [loadedDuration, setLoadedDuration] = useState<number | null>(null);
  const [sourceDurationS, setSourceDurationS] = useState<number | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [cutBusy, setCutBusy] = useState(false);
  const lastAutoPreviewRef = useRef<string | null>(null);
  /** STITCH_NO_AUTO_CUT_PREVIEW_V1 — Apply Cut only after operator commits both handles. */
  const [cutHandlesAdjusted, setCutHandlesAdjusted] = useState({ start: false, end: false });
  const resetCutHandleFlags = () => setCutHandlesAdjusted({ start: false, end: false });
  const cutReadyForApply = cutHandlesAdjusted.start && cutHandlesAdjusted.end;
  const clipMissingOnDisk = option?.video_path_exists === false;

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
  const dropRef = useRef<HTMLDivElement>(null);
  useDropTargetCapture(dropRef, dropHandlers, [dropHandlers]);
  if (!option) {
    return (
      <div
        ref={dropRef}
        class="mn-bg-option mn-bg-option-empty-wrap mn-drop-target"
        data-testid={`bg-option-${beatIndex}-${optionIndex}`}
        data-bg-option-empty="true"
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
  const hasClipVideo = !!option.video_path;
  const isStillDraft = !!stillInsert && hasClipVideo && !isStitchApproved;
  const optionLabel = displayO3OptionLabel(option)
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
      ?? resolveStitchSlotSourceVideoUrl(option.video_path)
      ?? `${SERVER_BASE}/files?path=${encodeURIComponent(option.video_path)}${cacheBust}`)
    : null;
  const clipVideoPath = option.video_path ?? undefined;
  const sourceVideoPath = clipVideoPath ?? '';
  const cutTargetOpts = clipVideoPath ? { videoPath: clipVideoPath } : {};
  const showCutControls = selected && hasClipVideo;
  const showTrimControls = showNumericTrim && selected && hasClipVideo;
  const MIN_O3_CUT_S = 0.25;
  const isCutPreviewActive = !!previewUrl;
  const playbackDurationS = resolveO3PlaybackDurationS(sourceDurationS, loadedDuration);
  const overlayTimelineDurationS = resolveO3OverlayDurationS(sourceDurationS, loadedDuration);
  const exportDurationS = resolveO3ExportDurationS(sourceDurationS, playbackDurationS);
  const trimAuthorityDurationS = resolveO3TrimAuthorityDurationS(
    overlayTimelineDurationS,
    exportDurationS,
    playbackDurationS,
  );
  const savedKeepStartS = trimStartS > 0.009 ? trimStartS : 0;
  const savedKeepEndRaw = overlayTimelineDurationS > 0
    ? Math.max(savedKeepStartS + MIN_O3_CUT_S, overlayTimelineDurationS - (trimBackS > 0.009 ? trimBackS : 0))
    : 0;
  const savedKeep = normalizeO3KeepWindow(
    overlayTimelineDurationS,
    savedKeepStartS,
    savedKeepEndRaw,
  );
  const pendingKeep = pendingCut && overlayTimelineDurationS > 0
    ? normalizeO3KeepWindow(overlayTimelineDurationS, pendingCut.startS, pendingCut.endS)
    : null;
  const effectiveKeepStartS = pendingKeep?.startS ?? savedKeep.startS;
  const effectiveKeepEndS = pendingKeep?.endS ?? savedKeep.endS;
  const cutDraftDirty = pendingCut !== null && (
    Math.abs((pendingKeep?.startS ?? pendingCut.startS) - savedKeep.startS) > 0.009
    || Math.abs((pendingKeep?.endS ?? pendingCut.endS) - savedKeep.endS) > 0.009
  );
  const hasActiveCut = (
    savedKeepStartS > 0.009
    || trimBackS > 0.05
    || (pendingCut !== null && cutDraftDirty)
  );
  const hasSavedCut = savedKeepStartS > 0.009 || trimBackS > 0.05;
  const cutPreviewTrimBackS = () => {
    const dur = trimAuthorityDurationS;
    if (dur <= 0) return 0;
    return Math.max(0, dur - effectiveKeepEndS);
  };
  // Magic-on-video override must win over cached Kling playback — same clip the beat exports.
  const activeVideoUrl = previewUrl ?? overrideVideoUrl ?? playbackUrl ?? canonicalVideoUrl;
  // Overlay timeline = loaded video element duration (not max(ffprobe, loaded)).
  const trimTimelineDurationS = overlayTimelineDurationS;
  const overlayDurationS = isCutPreviewActive || overlayTimelineDurationS <= 0
    ? 0
    : trimTimelineDurationS;

  useEffect(() => {
    if (!pendingCut || overlayTimelineDurationS <= 0) return;
    const clamped = normalizeO3KeepWindow(
      overlayTimelineDurationS,
      pendingCut.startS,
      pendingCut.endS,
    );
    if (
      Math.abs(clamped.startS - pendingCut.startS) > 0.009
      || Math.abs(clamped.endS - pendingCut.endS) > 0.009
    ) {
      setPendingCut(clamped);
    }
  }, [overlayTimelineDurationS]);

  useEffect(() => {
    if (!selected || !option.video_path || previewUrl) {
      if (!selected) {
        setPlaybackUrl(null);
        setSourceDurationS(null);
      }
      return;
    }
    let cancelled = false;
    void (async () => {
      const truth = await resolveClipPlaybackTruth(option.video_path!);
      if (cancelled) return;
      if (truth?.rawDurationS != null && truth.rawDurationS > 0) {
        setSourceDurationS(truth.rawDurationS);
        rawDurationRef.current = truth.rawDurationS;
      }
      if (truth?.playbackUrl) {
        setPlaybackUrl(truth.playbackUrl);
      }
    })();
    return () => { cancelled = true; };
  }, [selected, option.video_path, previewUrl]);

  useEffect(() => {
    if (!canonicalVideoUrl) {
      setPlaybackUrl(null);
    }
  }, [canonicalVideoUrl]);

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

  useEffect(() => {
    // Only drop materialized preview when the underlying source clip changes —
    // NOT when cache-bust query params change on session refresh.
    setPreviewUrl(null);
    lastAutoPreviewRef.current = null;
    setPendingCut(null);
    resetCutHandleFlags();
    setLoadedDuration(null);
    setSourceDurationS(null);
  }, [sourceVideoPath]);

  useEffect(() => {
    setVideoLoadError(false);
    setLoadedDuration(null);
    if (!selected) {
      setPlaybackUrl(null);
      setSourceDurationS(null);
    }
  }, [sourceVideoPath, selected]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !activeVideoUrl) return;
    if (video.src !== activeVideoUrl) {
      video.src = activeVideoUrl;
      video.load();
    }
  }, [activeVideoUrl]);

  const swapVideoToPreview = async (url: string, opts?: { autoplay?: boolean }) => {
    const autoplay = opts?.autoplay === true;
    setVideoLoadError(false);
    setPreviewUrl(url);
    const video = videoRef.current;
    if (!video) return;
    video.src = url;
    video.load();
    try {
      await waitForVideoMetadata(video);
      video.currentTime = 0;
      if (autoplay) {
        await video.play();
      } else {
        video.pause();
      }
    } catch {
      // load blocked — user can press play; preview src is still set
      try {
        video.pause();
      } catch {
        // defensive
      }
    }
  };

  const persistCut = async (
    keepStartS: number,
    keepEndS: number,
  ): Promise<{
    ok: boolean;
    previewUrl?: string;
    trimBackS?: number;
    keepStartS?: number;
    trimBaked?: boolean;
    videoPath?: string;
  }> => {
    if (!selected) return { ok: false };
    const validateDuration = trimAuthorityDurationS;
    if (validateDuration <= 0) {
      pushToast({
        kind: 'info',
        message: 'Loading clip duration — try again in a moment',
        source: 'bg-o3-cut-duration-loading',
      });
      return { ok: false };
    }
    const { startS, endS } = normalizeO3KeepWindow(validateDuration, keepStartS, keepEndS);
    if (!isValidO3CutWindow(validateDuration, startS, endS)) {
      pushToast({
        kind: 'info',
        message: validateDuration <= MIN_O3_CUT_S * 2
          ? `Clip is only ${validateDuration.toFixed(1)}s — too short to trim`
          : 'Trim window too small — drag handles farther apart (need ≥0.25s kept)',
        source: 'bg-o3-cut-rejected',
      });
      console.info('[bg_o3_trim_audit_client]', {
        phase: 'persist_reject',
        beatId,
        optionIndex,
        validateDuration,
        exportDurationS,
        overlayTimelineDurationS,
        trimAuthorityDurationS,
        playbackDurationS,
        keepStartS,
        keepEndS,
        keptS: endS - startS,
        trimStartS,
        trimBackS,
        pendingCut,
      });
      return { ok: false };
    }
    const trimBack = Math.max(0, validateDuration - endS);
    setCutBusy(true);
    try {
      const applied = await onApplyO3Cut(
        optionIndex,
        startS,
        trimBack > 0.009 ? trimBack : null,
        cutTargetOpts,
      );
      if (!applied) return { ok: false };
      if (applied.rawDurationS != null) {
        setSourceDurationS(applied.rawDurationS);
        rawDurationRef.current = applied.rawDurationS;
      }
      const raw = applied.rawDurationS ?? validateDuration;
      const eff = applied.effectiveDurationS;
      const shortening = startS > 0.05 || trimBack > 0.05;
      if (shortening && eff != null && eff >= raw - 0.05 && !applied.trimBaked) {
        return { ok: false };
      }
      return {
        ok: true,
        ...(applied.previewUrl !== undefined ? { previewUrl: applied.previewUrl } : {}),
        ...(applied.trimBaked ? { trimBaked: true as const } : {}),
        ...(applied.videoPath ? { videoPath: applied.videoPath } : {}),
        trimBackS: trimBack,
        keepStartS: startS,
      };
    } finally {
      setCutBusy(false);
    }
  };

  const refreshSavedCutPreview = async (
    startS: number,
    trimBack: number,
    previewUrlHint?: string,
  ) => {
    if (!selected || !option.video_path) return;
    lastAutoPreviewRef.current = null;
    const sig = `${option.video_path}|${startS.toFixed(2)}|${trimBack.toFixed(2)}`;
    const cached = previewUrlHint
      ? null
      : recallCutPreviewUrl(beatId, optionIndex, option.video_path, startS, trimBack);
    if (cached) {
      rememberCutPreviewUrl(beatId, optionIndex, option.video_path, startS, trimBack, cached);
      lastAutoPreviewRef.current = sig;
      await swapVideoToPreview(cached, { autoplay: false });
      return;
    }
    setCutBusy(true);
    try {
      const applied = await onApplyO3Cut(
        optionIndex,
        startS,
        trimBack > 0.009 ? trimBack : null,
        { previewOnly: true, silent: true, ...cutTargetOpts },
      );
      if (!applied?.previewUrl) return;
      rememberCutPreviewUrl(beatId, optionIndex, option.video_path, startS, trimBack, applied.previewUrl);
      lastAutoPreviewRef.current = sig;
      await swapVideoToPreview(applied.previewUrl, { autoplay: false });
    } finally {
      setCutBusy(false);
    }
  };

  const pendingCutValid = pendingKeep != null
    && trimAuthorityDurationS > 0
    && isValidO3CutWindow(trimAuthorityDurationS, pendingKeep.startS, pendingKeep.endS);

  const applyDraftCut = async () => {
    if (cutDraftDirty && !pendingCutValid) {
      pushToast({
        kind: 'info',
        message: cutReadyForApply
          ? 'Trim window too small — drag handles farther apart (need ≥0.25s kept)'
          : 'Drag start and end handles to set the keep region — then press Apply Cut',
        source: 'bg-o3-cut-both-handles-required',
      });
      return;
    }
    if (!selected || !hasActiveCut) return;
    const saved = await persistCut(effectiveKeepStartS, effectiveKeepEndS);
    if (!saved.ok) return;
    clearPendingCut();
    resetCutHandleFlags();
    if (saved.trimBaked && saved.videoPath) {
      setPreviewUrl(null);
      lastAutoPreviewRef.current = null;
      forgetCutPreviewsForBeat(beatId);
      const video = videoRef.current;
      if (video && canonicalVideoUrl) {
        video.src = canonicalVideoUrl;
        video.load();
      }
      return;
    }
    const trimBack = saved.trimBackS ?? cutPreviewTrimBackS();
    const startS = saved.keepStartS ?? effectiveKeepStartS;
    await refreshSavedCutPreview(startS, trimBack, saved.previewUrl);
  };

  const clearCut = async () => {
    if (!selected) return;
    setCutBusy(true);
    try {
      clearPendingCut();
      resetCutHandleFlags();
      setPreviewUrl(null);
      lastAutoPreviewRef.current = null;
      forgetCutPreviewsForBeat(beatId);
      await onApplyO3Cut(optionIndex, 0, null, { clear: true, ...cutTargetOpts });
      const video = videoRef.current;
      if (video && canonicalVideoUrl) {
        video.src = canonicalVideoUrl;
        video.load();
      }
    } finally {
      setCutBusy(false);
    }
  };

  const returnToCutEdit = async () => {
    setPreviewUrl(null);
    await resetVideoToCanonical();
  };

  const initCutFromDuration = () => {
    const clipDur = overlayTimelineDurationS || exportDurationS || playbackDurationS;
    if (clipDur <= MIN_O3_CUT_S * 2) {
      pushToast({
        kind: 'info',
        message: `Clip is only ${clipDur.toFixed(1)}s — too short to trim`,
        source: 'bg-o3-cut-too-short',
      });
      return;
    }
    const margin = Math.max(MIN_O3_CUT_S, clipDur * 0.12);
    resetCutHandleFlags();
    setPendingCut({ startS: margin, endS: clipDur - margin });
  };

  const resetVideoToCanonical = async () => {
    const video = videoRef.current;
    if (!video || !canonicalVideoUrl) return;
    clearTrimPlaybackListener(video);
    if (video.src !== canonicalVideoUrl) {
      video.src = canonicalVideoUrl;
    }
    video.load();
    try {
      await waitForVideoMetadata(video);
      video.currentTime = 0;
    } catch {
      // leave for user refresh
    }
  };

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
  const ensureCanonicalVideoForPlayhead = async () => {
    const video = videoRef.current;
    if (!video || !canonicalVideoUrl) return null;
    clearTrimPlaybackListener(video);
    setPreviewUrl(null);
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
      setPreviewUrl(null);
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
    clearDirtyAfterSave();
    const video = videoRef.current;
    if (video && canonicalVideoUrl) {
      setPreviewUrl(null);
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
  const clearDraftTrim = async () => {
    setTrimStartDraft('0');
    setTrimBackDraft('0');
    rawDurationRef.current = null;
    const video = videoRef.current;
    if (video && canonicalVideoUrl) {
      clearTrimPlaybackListener(video);
      setPreviewUrl(null);
      video.src = canonicalVideoUrl;
      video.load();
    }
    await onApplyO3Trim(0, null, true);
  };

  return (
    <div
      ref={dropRef}
      class={`mn-bg-option mn-drop-target${selected ? ' is-selected' : ''}${keyMissing ? ' is-disabled' : ''}${isStitchApproved && hasClipVideo ? ' is-approved-video' : ''}${isStillDraft ? ' is-still-draft' : ''}`}
      data-testid={`bg-option-${beatIndex}-${optionIndex}`}
      data-option-key={option.key ?? ''}
      onClick={keyMissing ? undefined : onClick}
      title={tooltip}
    >
      {selected && activeVideoUrl && !clipMissingOnDisk ? (
        <>
          <div
            class="mn-bg-option-video-wrap"
            data-playback-cache-v1="PLAYBACK_CACHE_V1"
            style={{ position: 'relative' }}
            onClick={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <video
              ref={videoRef}
              controls
              preload="metadata"
              src={activeVideoUrl}
              class={PLAYBACK_VIDEO_ANTI_BANDING_CLASS}
              data-testid={`bg-option-video-${beatIndex}-${optionIndex}`}
              onPause={() => clearTrimPlaybackListener()}
              onEnded={() => {
                const v = videoRef.current;
                if (v) {
                  v.currentTime = 0;
                }
              }}
              onError={() => setVideoLoadError(true)}
              onLoadedData={() => {
                setVideoLoadError(false);
                const v = videoRef.current;
                if (v && Number.isFinite(v.duration) && v.duration > 0) {
                  setLoadedDuration(v.duration);
                }
              }}
            />
            {showCutControls && overlayDurationS > 0 ? (
              <BgO3CutOverlay
                beatIndex={beatIndex}
                optionIndex={optionIndex}
                beatId={beatId}
                durationS={overlayDurationS}
                keepStartS={effectiveKeepStartS}
                keepEndS={effectiveKeepEndS}
                editable={!cutBusy}
                onDragStart={onOverlayDragStart}
                onDragEnd={onOverlayDragEnd}
                onKeepDraftChange={(startS, endS) => {
                  setPendingCut({ startS, endS });
                }}
                onKeepStartCommitted={() => {
                  setCutHandlesAdjusted((prev) => ({ ...prev, start: true }));
                }}
                onKeepEndCommitted={() => {
                  setCutHandlesAdjusted((prev) => ({ ...prev, end: true }));
                }}
                onKeepRejected={(message) => {
                  console.info('[bg_o3_trim_audit_client]', {
                    phase: 'overlay_reject',
                    beatId,
                    optionIndex,
                    message,
                    overlayDurationS,
                    overlayTimelineDurationS,
                    playbackDurationS,
                    exportDurationS,
                    sourceDurationS,
                    loadedDuration,
                    effectiveKeepStartS,
                    effectiveKeepEndS,
                    keptS: effectiveKeepEndS - effectiveKeepStartS,
                    trimStartS,
                    trimBackS,
                    pendingCut,
                    isCutPreviewActive,
                  });
                  pushToast({ kind: 'info', message, source: 'bg-o3-cut-rejected' });
                }}
              />
            ) : null}
          </div>
          {videoLoadError ? (
            <div class="mn-bg-option-empty" data-testid={`bg-option-video-error-${beatIndex}-${optionIndex}`}>
              Trim preview failed to load — trim may still be saved.
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
          {showCutControls ? (
            <div class="mn-bg-o3-cut-controls" data-testid={`bg-o3-cut-controls-${beatIndex}-${optionIndex}`}>
              <span class="mn-dim">
                {isCutPreviewActive
                  ? 'playing cut preview'
                  : cutDraftDirty
                    ? cutReadyForApply
                      ? 'both handles set — press Apply Cut'
                      : 'drag both start and end handles — then Apply Cut'
                    : hasSavedCut
                      ? 'trim applied (start + end crop)'
                      : 'amber = head/tail remove'}
              </span>
              {isCutPreviewActive ? (
                <button
                  type="button"
                  class="mn-btn mn-btn-small"
                  data-testid={`bg-o3-edit-cut-${beatIndex}-${optionIndex}`}
                  disabled={cutBusy}
                  onClick={(e) => {
                    e.stopPropagation();
                    void returnToCutEdit();
                  }}
                >
                  Edit cut
                </button>
              ) : null}
              {!hasActiveCut && !isCutPreviewActive ? (
                <button
                  type="button"
                  class="mn-btn mn-btn-small"
                  data-testid={`bg-o3-init-cut-${beatIndex}-${optionIndex}`}
                  disabled={cutBusy || (exportDurationS || playbackDurationS) <= MIN_O3_CUT_S * 2}
                  onClick={(e) => {
                    e.stopPropagation();
                    initCutFromDuration();
                  }}
                >
                  Start cut
                </button>
              ) : null}
              {cutDraftDirty ? (
                <button
                  type="button"
                  class="mn-btn mn-btn-small mn-btn-primary"
                  data-testid={`bg-o3-apply-cut-${beatIndex}-${optionIndex}`}
                  disabled={cutBusy || !hasActiveCut || (cutDraftDirty && !pendingCutValid)}
                  title="Save cut region for stitch export (Phase A/B Apply Cut parity)"
                  onClick={(e) => {
                    e.stopPropagation();
                    void applyDraftCut();
                  }}
                >
                  {cutBusy ? 'Cutting…' : 'Apply Cut'}
                </button>
              ) : null}
              <button
                type="button"
                class="mn-btn mn-btn-small"
                data-testid={`bg-o3-clear-cut-${beatIndex}-${optionIndex}`}
                disabled={cutBusy || (!hasActiveCut && !hasSavedCut)}
                onClick={(e) => {
                  e.stopPropagation();
                  void clearCut();
                }}
              >
                Clear cut
              </button>
            </div>
          ) : null}
          {showTrimControls ? (
            <BgO3TrimNumericControls
              beatIndex={beatIndex}
              optionIndex={optionIndex}
              trimStartDraft={trimStartDraft}
              trimBackDraft={trimBackDraft}
              savedTrimInvalid={savedTrimInvalid}
              onTrimStartInput={setTrimStartDraft}
              onTrimBackInput={setTrimBackDraft}
              onStartFromPlayhead={() => { void setStartFromPlayhead(); }}
              onEndFromPlayhead={() => { void setEndFromPlayhead(); }}
              onApplyTrim={() => { void applyDraftTrim(); }}
              onPreviewTrim={() => { void playTrimPreview(); }}
              onClearTrim={() => { void clearDraftTrim(); }}
            />
          ) : null}
          {isStillDraft && onApproveStill ? (
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
      ) : !selected && hasClipVideo && canonicalVideoUrl ? (
        <video
          class="mn-bg-option-video-preview"
          preload="metadata"
          muted
          playsInline
          src={canonicalVideoUrl}
          data-testid={`bg-option-video-preview-${beatIndex}-${optionIndex}`}
        />
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
          title={isStillDraft ? 'Select this draft still clip to preview and trim' : tooltip}
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
