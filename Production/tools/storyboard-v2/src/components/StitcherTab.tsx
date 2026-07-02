// StitcherTab — Session 5 v3.1 full UI per LD-471 STITCHER_FULL_UI_V1.
// S5.5g extension: per-slot SFX cue placement (STITCHER_SFX_CUE_UI_V1 HARD)
// + module-level SFX cue strip. Per spec §3.2 + §4 Phase B G3-G6.
//
// 4-slot strip: intro → Phase A → Phase B → resolution. Each slot shows:
//   * Slot label + assigned video filename (if any)
//   * Per-slot ambient bed dropdown
//   * StitcherSlotWaveform with SFX cue markers + lib-sfx drop target
//   * Preview button → calls _handle_stitch_preview
//   * Bake button → calls _handle_stitch_bake
//   * Loudnorm toggle → calls /api/stitch_editor/loudnorm
//
// Module-level SFX cues live in a separate timeline strip below the slots
// and persist via /api/timeline/cues (state.module_sfx_cues), distinct
// from slot.sfx_cues which travel inside stitch_save_job.slots[i].
//
// All actions go through pathappPatch so scope guards + snapshot fire.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'preact/hooks';
import { useDropTargetCapture } from '../hooks/useDropTargetCapture';
import { useStitchSlotClientMix } from '../hooks/useStitchSlotClientMix';
import { effect } from '@preact/signals';
import { activeScope, activeProjectType, activeMilestoneId, producerScopeChipLabel, activeTargetVideo } from '../state/scope';
import { pushToast } from './ui/Toast';
import { stitcherRefreshTick } from '../app';
import { serverRehydrateTick, activeTab } from '../state/refreshSignals';
import {
  stitchActiveKey,
  stitchCachedJob,
  stitchJobSessionHasCache,
  stitchJobLoading,
} from '../state/stitchJobSessionStore';
import { stitchJobNameForScope, stitchJobSessionKey } from '../state/producerSessionKeys';
import { apiGet, pathappPatch } from '../api/client';
import { READ_ENDPOINTS } from '../api/endpoints';
import { StitcherSlotWaveform } from './StitcherSlotWaveform';
import { StitcherTransitionSelector, type Transition } from './StitcherTransitionSelector';
import { SfxCuePopover, type SfxCue } from './phase/SfxCuePopover';
import { acceptDragForTarget, makeDropTarget, type DragPayload } from '../utils/dragdrop';
import { resolveServerMediaUrl } from '../utils/stitchSlotVideo';
import { PLAYBACK_VIDEO_ANTI_BANDING_CLASS } from '../utils/playbackVideoPolicy';
import {
  StitchComposerVideoPool,
  STITCH_COMPOSER_VIDEO_POOL_V1,
  type StitchComposerVideoPoolHandle,
} from './StitchComposerVideoPool';
import {
  pickTrackSlotForLayout,
  resolveStitchViewerSlot,
  resolveTrackSlotForInteraction,
  slotHasStitchVideo,
  STITCH_EMPTY_SEGMENT_MS,
  STITCH_VIEWER_SLOT_LAYOUT_V1,
  writePersistedTrackSlot,
  type StitchTrackSlotKey,
} from '../utils/stitchTrackFocus';
import {
  mergeStitchJobSlotsClientPatch,
  STITCH_SAVE_SLOT_DURABLE_MERGE_V1,
  beginStitchAmbientPatch,
  endStitchAmbientPatch,
} from '../utils/stitchSlotDurableMerge';
import {
  STITCH_AMBIENT_BED_VOLUME,
  STITCH_AMBIENT_SELECT_HYDRATE_V1,
  STITCH_AMBIENT_VOLUME_PERSIST_V1,
  STITCH_CANONICAL_DEFAULTS_PERSIST_V1,
  STITCH_DEFAULT_AMBIENT_BEDS_V1,
  STITCH_SFX_CUE_DEFAULT_FADEIN_MS,
  STITCH_SFX_CUE_DEFAULT_FADEOUT_MS,
  STITCH_SFX_CUE_DEFAULT_VOLUME,
  STITCH_SLOT_CANONICAL_DEFAULTS_V1,
  defaultAmbientBedForSlot,
} from '../utils/stitchConstants';
import { stopAllPhasePlayback } from '../utils/waveformPlaybackBus';
import {
  defaultStitchTransitions,
  resolveStitchTransitions,
} from '../utils/stitchModulePreview';
import {
  STITCH_SLOT_LIVE_GEOMETRY_SIG_V1,
  STITCH_SLOT_MUX_AUDIO_SIG_V1,
  stitchSlotGeometryChanged,
  stitchSlotLiveGeometrySig,
  stitchSlotMuxAudioSig,
  stitchSlotRequiresMuxedPreview,
  stitchSlotRequiresAmbientMix,
  stitchSlotLiveAmbientSig,
  stitchSlotUsesFourFilesPlayback,
  stitchSlotUsesDryAuthorityClientMix,
  stitchSlotRequiresClientPreviewMix,
  STITCH_DRY_AUTHORITY_CLIENT_MIX_V1,
  STITCH_AMBIENT_BAKE_ON_SAVE_V1,
  stripStaleStitchSlotArtifacts,
} from '../utils/stitchSlotMuxAudioSig';
import {
  inferStitchEditKind,
  STITCH_SLOT_EDIT_DISPATCH_V1,
} from '../utils/stitchSlotEditDispatch';
import {
  pollStitchArtifactBuild,
  STITCH_ARTIFACT_ORCHESTRATOR_V1,
} from '../utils/stitchArtifactBuildPoll';
import {
  hydrateAllSlotMediaFromJob,
  isStitchMuxPlaybackUrl,
  previewUrlMatchesPersistedMux,
  resolveDrySlotSourceVideoUrl,
  resolvePersistedPlaybackFromArtifacts,
  resolveSlotPlaybackPreviewUrl,
  resolveSlotWaveformVideoPath,
  selectSlotsForMuxRebuild,
  stitchSlotTimelineDurMs,
  STITCH_MUX_REBUILD_QUEUE_V1,
  STITCH_SFX_PLAYBACK_TRUTH_V1,
} from '../utils/stitchJobMediaHydrate';
import { syncActiveVideoRoleFromUrl } from '../state/videoRole';
import {
  clearStitchComposerPreviewUrls,
  isStitchComposerUrlLoaded,
  markStitchComposerUrlLoaded,
  restoreStitchComposerPreviewUrls,
  setStitchComposerPreviewUrl,
} from '../utils/stitchComposerSessionStore';
import {
  STITCH_MUX_SRC_IDENTITY_V1,
  type MuxSrcUpdateIntent,
  shouldUpdateComposerMuxSrc,
} from '../utils/stitchMuxPreviewIdentity';
import {
  isStitchBakeStatusActive,
  isStitchBakeStatusTerminal,
  readStitchBakeBusyLatch,
  shouldToastStitchBakeRefreshFailure,
  stitchBakeStatusMessage,
  stitchBakeSuccessPaths,
  STITCH_BAKE_POLL_INTERVAL_MS,
  writeStitchBakeBusyLatch,
  type StitchBakeJobSummary,
  type StitchBakePollResult,
} from '../utils/stitchBakeJobTruth';
import {
  STITCH_MUX_VIDEO_LINEAGE_V1,
  stitchSlotMuxPreviewLineageMatches,
} from '../utils/stitchMuxVideoLineage';
import {
  STITCH_SLOT_VIDEO_LINEAGE_V1,
  invalidateStitchSlotPlaybackCaches,
  mergeHydratedPreviewUrlsAfterLineage,
  slotsWithVideoPathChanges,
  stripPreviewUrlsForArtifactRebuild,
} from '../utils/stitchSlotVideoLineage';
import {
  singleFlightMuxPreview,
  stitchMediaFlightKey,
} from '../utils/stitchMediaBuildFlight';
import {
  clearAllCachedStitcherPreviewsLs,
  clearCachedStitcherPreviewLs,
  clearStitchSlotSessionEvent,
  commitMuxSession,
  getStitchSlotSession,
  hydrateMuxFromLocalStorage,
  isMuxSessionFresh,
  readCachedStitcherPreviewLs,
  reconcileStitchSlotSession,
  stitchSlotSessionExpectedSig,
  STITCH_PREVIEW_LS_HYDRATE_V1,
  writeCachedStitcherPreviewLs,
  type CachedStitcherPreviewLs,
  type StitchSessionSlotKey,
} from '../utils/stitchSlotSessionCache';

type StandaloneSlotKey = 'standalone';
type StitchUiSlotKey = StitchTrackSlotKey | StandaloneSlotKey;
type SlotKey = StitchUiSlotKey;

const SLOT_DEFS: Array<{ key: StitchTrackSlotKey; label: string }> = [
  { key: 'intro', label: 'Intro' },
  { key: 'phase_a', label: 'Phase A' },
  { key: 'phase_b', label: 'Phase B' },
  { key: 'resolution', label: 'Resolution' },
];

const STANDALONE_SLOT_DEFS: Array<{ key: StandaloneSlotKey; label: string }> = [
  { key: 'standalone', label: 'Standalone' },
];

function stitchJobSlotsAsRecord(
  raw: Record<string, StitchSlot> | StitchSlot[] | undefined,
): Record<string, StitchSlot> {
  if (!raw || typeof raw !== 'object') return {};
  if (Array.isArray(raw)) {
    return raw.length > 0 && typeof raw[0] === 'object' ? { standalone: raw[0] } : {};
  }
  return { ...(raw as Record<string, StitchSlot>) };
}

function milestoneStandaloneNeedsExport(slots: Record<string, StitchSlot> | undefined): boolean {
  const slot = slots?.['standalone'];
  return !Boolean((slot?.video_path ?? '').trim());
}

interface StitchSlot {
  video_path?: string;
  video_dur_ms?: number;
  beat_boundaries?: BeatBoundary[];
  ambient_bed?: string;
  ambient_bed_path?: string;
  ambient_volume?: number;
  loudnorm_already_applied?: boolean;
  intro_whoosh_default_dismissed?: boolean;
  phase_a_tail_sfx_default_dismissed?: boolean;
  phase_b_tail_sfx_default_dismissed?: boolean;
  resolution_head_sfx_default_dismissed?: boolean;
  resolution_tail_sfx_default_dismissed?: boolean;
  sfx_cues?: SfxCue[];
  trim_in_ms?: number;
  trim_out_ms?: number | null;
  mix_sig?: string;
  ambient_mix_sig?: string;
  ambient_mix_hash?: string;
  ambient_mix_duration_ms?: number;
  ambient_mix_video_path?: string;
  ambient_mix_video_mtime_ms?: number;
  mux_preview_hash?: string;
  mux_preview_duration_ms?: number;
  mux_video_path?: string;
  mux_video_mtime_ms?: number;
  waveform_peaks_hash?: string;
  waveform_peaks_duration_s?: number;
  _mux_preview_url?: string;
  _waveform_peaks_url?: string;
  _ambient_mix_url?: string;
  playback_recipe_version?: string;
  dry_export_path?: string;
}

interface StitchJob {
  name?: string;
  slots?: Record<string, StitchSlot>;
  transitions?: Transition[];
  bake_path?: string;
  bake_mtime?: number;
  active_bake_job_id?: string;
  module_final_cache_key?: string;
}

interface StitchLibraryResponse {
  ok?: boolean;
  jobs?: StitchJob[];
}

/** Footer final-MP4 fields from load_job (job dict + payload root fallback). */
function stitchJobFooterPlaybackFields(
  job?: Pick<StitchJob, 'bake_path' | 'module_final_cache_key'> | null,
  loadPayload?: { module_final_cache_key?: string },
): Pick<StitchJob, 'bake_path' | 'module_final_cache_key'> {
  const cacheKey = (
    job?.module_final_cache_key
    ?? loadPayload?.module_final_cache_key
    ?? ''
  ).trim();
  return {
    ...(job?.bake_path ? { bake_path: job.bake_path } : {}),
    ...(cacheKey ? { module_final_cache_key: cacheKey } : {}),
  };
}

// F-AMBIENT-001 (prod_blockers id=118) — ambient bed catalog. Pre-fix this
// was a hardcoded array of 4 fake preset_ids (gentle_forest, soft_chimes,
// warm_room_tone, water_stream) that did not resolve to ANY file on disk;
// selecting one would fail at audio assembly. The fetched catalog comes from
// `/api/phase_b/ambient_preset_list` (misleadingly named — it is the global
// ambient catalog used by Phase A, Phase B, AND Stitcher; rename is out of
// scope per the F-AMBIENT-001 dispatch). Same shape as PhaseProducer's
// AmbientPreset interface (PhaseProducer.tsx:60-68) so the two surfaces stay
// consistent. The "— none —" entry is prepended at render time so users can
// still clear a slot's ambient bed.
interface AmbientPreset {
  preset_id: string;
  file_size_bytes: number;
}
interface AmbientPresetListResponse {
  ok: boolean;
  items?: AmbientPreset[];
  count?: number;
}

// Server defaults from server.py:14085-14087 (_handle_timeline_cue_upsert).
const SFX_DEFAULTS = {
  volume: STITCH_SFX_CUE_DEFAULT_VOLUME,
  fadein_ms: STITCH_SFX_CUE_DEFAULT_FADEIN_MS,
  fadeout_ms: STITCH_SFX_CUE_DEFAULT_FADEOUT_MS,
};

const STITCH_MUX_PAUSE_ON_GEOMETRY_V1 = 'STITCH_MUX_PAUSE_ON_GEOMETRY_V1';
const STITCH_SLOT_TIMELINE_ATOMIC_V1 = 'STITCH_SLOT_TIMELINE_ATOMIC_V1';
// Stitcher slots are typically short; 30s is a safe default that keeps drop
// math sane until the real duration loads. Tests inject explicit video_dur_ms.
const DEFAULT_SLOT_DUR_MS = 30000;

const STITCH_SLOT_TAIL_SFX_DISMISS: Partial<Record<SlotKey, keyof StitchSlot>> = {
  intro: 'intro_whoosh_default_dismissed',
  phase_a: 'phase_a_tail_sfx_default_dismissed',
  phase_b: 'phase_b_tail_sfx_default_dismissed',
};

const STITCH_SLOT_CANONICAL_SFX_FILE_DISMISS: Partial<
  Record<SlotKey, Record<string, keyof StitchSlot>>
> = {
  resolution: {
    'whoosh sound.mp3': 'resolution_head_sfx_default_dismissed',
    'exit resolution video sfx.mp3': 'resolution_tail_sfx_default_dismissed',
  },
};

function canonicalSfxDismissKey(
  slotKey: SlotKey,
  cue?: { name?: string; auto_default?: boolean },
): keyof StitchSlot | undefined {
  if (!cue?.auto_default) return undefined;
  const name = (cue.name ?? '').trim().toLowerCase();
  const perFile = STITCH_SLOT_CANONICAL_SFX_FILE_DISMISS[slotKey];
  if (perFile) {
    for (const [filename, key] of Object.entries(perFile)) {
      if (name.includes(filename.toLowerCase()) || name.includes(filename.replace('.mp3', '').toLowerCase())) {
        return key;
      }
    }
  }
  return STITCH_SLOT_TAIL_SFX_DISMISS[slotKey];
}

/** Persist only default-field deltas — never re-send full slot blobs that can wipe SFX. */
function stitchDefaultFieldsPatch(
  slots: Record<string, StitchSlot>,
): Record<string, StitchSlot> {
  const out: Record<string, StitchSlot> = {};
  for (const [key, slot] of Object.entries(slots)) {
    if (!slot?.video_path) continue;
    out[key] = {
      video_path: slot.video_path,
      ...(slot.video_dur_ms != null ? { video_dur_ms: slot.video_dur_ms } : {}),
      ...(slot.ambient_bed ? { ambient_bed: slot.ambient_bed } : {}),
      ...(slot.ambient_volume != null ? { ambient_volume: slot.ambient_volume } : {}),
    };
  }
  return out;
}

/** Refuse save when snapshot would wipe persisted slot media (STITCH_SFX_PLAYBACK_TRUTH_V1). */
function stitchSnapshotReadyForSave(
  slots: Record<string, StitchSlot>,
  projectType: string,
): boolean {
  if (!Object.keys(slots).length) return false;
  if (projectType === 'milestone') {
    const standalone = slots['standalone'];
    return Boolean((standalone?.video_path ?? '').trim());
  }
  return SLOT_DEFS.some(({ key }) => Boolean((slots[key]?.video_path ?? '').trim()));
}

/** Backfill canonical ambient presets on slots that have video but no bed yet. */
function applyDefaultAmbientPresetsToSlots(slots: Record<string, StitchSlot>): boolean {
  let changed = false;
  const defs = activeProjectType.value === 'milestone' ? STANDALONE_SLOT_DEFS : SLOT_DEFS;
  for (const { key } of defs) {
    const slot = slots[key];
    if (!slot?.video_path || (slot.ambient_bed ?? '').trim()) continue;
    slot.ambient_bed = defaultAmbientBedForSlot(key);
    slot.ambient_volume = STITCH_AMBIENT_BED_VOLUME;
    delete slot.ambient_bed_path;
    changed = true;
  }
  return changed;
}

/** Force canonical 0.15 under-speech volume on every slot that has an ambient bed. */
function normalizeStitchSlotAmbientVolumesInPlace(slots: Record<string, StitchSlot>): void {
  const defs = activeProjectType.value === 'milestone' ? STANDALONE_SLOT_DEFS : SLOT_DEFS;
  for (const { key } of defs) {
    const slot = slots[key];
    if (!slot || !(slot.ambient_bed ?? '').trim()) continue;
    slot.ambient_volume = STITCH_AMBIENT_BED_VOLUME;
    delete slot.ambient_bed_path;
  }
}

interface PopoverState {
  scope: 'slot' | 'module';
  slotKey?: SlotKey;
  cueId: string;
  anchor: { x: number; y: number };
}

interface BeatBoundary {
  beat_id: string;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
}

function generateCueId(prefix: string): string {
  // 8-char random suffix — enough for in-session uniqueness; server is the
  // source of truth on persistence.
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

interface SlotImageDropTargetProps {
  slotKey: string;
  hasVideo: boolean;
  // Note: explicit `| undefined` required because tsconfig has
  // exactOptionalPropertyTypes:true; callers pass `string | undefined`
  // from `slot?.video_path?.split(...)` which would not satisfy `?:string`.
  videoLabel?: string | undefined;
  videoTitle?: string | undefined;
  onImageDrop: (payload: DragPayload) => void;
}

/** Per-slot video area — image-slot context accepts lib-image (Q1 Option C). */
function SlotImageDropTarget({
  slotKey,
  hasVideo,
  videoLabel,
  videoTitle,
  onImageDrop,
}: SlotImageDropTargetProps) {
  const dropRef = useRef<HTMLDivElement>(null);
  const dropHandlers = makeDropTarget(
    (payload) => {
      if (payload.kind !== 'lib-image') return;
      void onImageDrop(payload);
    },
    acceptDragForTarget('image-slot'),
    'image-slot',
  );
  useDropTargetCapture(dropRef, dropHandlers, [dropHandlers]);
  return (
    <div
      ref={dropRef}
      class="mn-stitcher-slot-video mn-drop-target"
      data-testid="stitcher-drop-target-image-slot"
      data-slot-key={slotKey}
      data-drop-target-kind="image-slot"
    >
      {hasVideo ? (
        <code title={videoTitle}>{videoLabel}</code>
      ) : (
        <span class="mn-dim">— empty — drop image —</span>
      )}
    </div>
  );
}

export function StitcherTab() {
  const [job, setJob] = useState<StitchJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busySlot, setBusySlot] = useState<{ slot: SlotKey; action: string } | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  // Per-slot preview URL — set after a successful Preview call. Renders as a
  // visible "▶ Watch" link directly in the slot so popup-blocker doesn't swallow it.
  const [previewUrls, setPreviewUrls] = useState<Partial<Record<SlotKey, string>>>({});
  const [previewLoadingSlot, setPreviewLoadingSlot] = useState<SlotKey | null>(null);
  /** Full module reel: intro → phase_a → phase_b → resolution with dissolve transitions. */
  const slotPreviewGenRef = useRef<Partial<Record<SlotKey, number>>>({});
  const stitchEventRef = useRef<string | null>(null);
  /** Triggers mux preview builds without re-fetching the full stitch job. */
  const [muxBuildTick, setMuxBuildTick] = useState(0);
  // ST-14: derive standaloneMode from canonical activeProjectType signal —
  // reactive on signal change. Milestone scope is always 1-slot standalone
  // by definition; event scope is 4-slot. (Was: inferred from slot count.)
  const standaloneMode = activeProjectType.value === 'milestone';
  const stitchSessionKey = stitchJobSessionKey(
    activeScope.value.event_id,
    activeProjectType.value,
    activeMilestoneId.value,
  );
  const [popover, setPopover] = useState<PopoverState | null>(null);
  // F-AMBIENT-001 — fetched ambient catalog (replaces hardcoded constant).
  // Pattern lifted from PhaseProducer.tsx:154-176 so Phase A, Phase B, and
  // Stitcher all consume the same catalog via the same single endpoint.
  const [ambientPresets, setAmbientPresets] = useState<AmbientPreset[]>([]);
  const [activeBakeJobId, setActiveBakeJobId] = useState<string | null>(null);
  const bakeTerminalToastRef = useRef<string | null>(null);
  /** Bust module-final <video> src after each successful bake (cache-safe URL). */
  const [moduleFinalRevision, setModuleFinalRevision] = useState(0);

  const persistJobSlotsByName = async (
    jobName: string,
    nextSlots: Record<string, StitchSlot>,
    transitions: Transition[],
  ): Promise<boolean> => {
    const res = await pathappPatch(activeScope.value, 'stitch_save_job', {
      name: jobName,
      slots: nextSlots,
      transitions,
      merge_slots: true,
    });
    return res.ok;
  };

  const ambientSelectOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const p of ambientPresets) ids.add(p.preset_id);
    for (const sd of SLOT_DEFS) {
      const bed = (job?.slots?.[sd.key]?.ambient_bed ?? '').trim();
      if (bed) ids.add(bed);
    }
    return [...ids].sort().map((preset_id) => ({
      preset_id,
      file_size_bytes: ambientPresets.find((p) => p.preset_id === preset_id)?.file_size_bytes ?? 0,
    }));
  }, [ambientPresets, job?.slots]);

  const moduleFinalVideoSrc = useMemo(() => {
    if (!job?.bake_path) return null;
    const base = READ_ENDPOINTS.stitch_module_final;
    const cacheKey = (job.module_final_cache_key || '').trim();
    if (cacheKey) {
      return `${base}?v=${encodeURIComponent(cacheKey.slice(0, 16))}`;
    }
    return moduleFinalRevision > 0 ? `${base}?v=${moduleFinalRevision}` : base;
  }, [job?.bake_path, job?.module_final_cache_key, moduleFinalRevision]);

  // STITCH_COMPOSER_DRY_PLAYBACK_V1 — one playback path; video_path always resolves to a URL.
  const composerSlotUrls = useMemo(() => {
    const out: Partial<Record<SlotKey, string>> = {};
    if (!job?.slots) return out;
    const defs = standaloneMode ? STANDALONE_SLOT_DEFS : SLOT_DEFS;
    for (const sd of defs) {
      const slotData = job.slots[sd.key];
      if (!slotData?.video_path) continue;
      const url = resolveSlotPlaybackPreviewUrl(
        stitchSessionKey,
        sd.key as StitchSessionSlotKey,
        slotData,
        previewUrls as Partial<Record<StitchSessionSlotKey, string>>,
      );
      if (url) out[sd.key] = url;
    }
    return out;
  }, [
    job?.slots,
    previewUrls,
    stitchSessionKey,
    standaloneMode,
    job?.slots?.['intro']?.video_path,
    job?.slots?.['phase_a']?.video_path,
    job?.slots?.['phase_b']?.video_path,
    job?.slots?.['resolution']?.video_path,
    job?.slots?.['standalone']?.video_path,
    job?.slots?.['intro']?.mux_preview_hash,
    job?.slots?.['phase_a']?.mux_preview_hash,
    job?.slots?.['phase_b']?.mux_preview_hash,
    job?.slots?.['resolution']?.mux_preview_hash,
    job?.slots?.['standalone']?.mux_preview_hash,
    job?.slots?.['intro']?.ambient_mix_hash,
    job?.slots?.['phase_a']?.ambient_mix_hash,
    job?.slots?.['phase_b']?.ambient_mix_hash,
    job?.slots?.['resolution']?.ambient_mix_hash,
    job?.slots?.['standalone']?.ambient_mix_hash,
  ]);

  // Inline preview player state
  const [trackFocusedSlot, setTrackFocusedSlot] = useState<StitchUiSlotKey | null>(null);
  const [beatBoundaries, setBeatBoundaries] = useState<BeatBoundary[]>([]);
  const [beatBoundariesLoading, setBeatBoundariesLoading] = useState(false);
  const composerVideoRef = useRef<HTMLVideoElement | null>(null);
  const [composerVideoNode, setComposerVideoNode] = useState<HTMLVideoElement | null>(null);
  const composerPoolRef = useRef<StitchComposerVideoPoolHandle | null>(null);
  const [composerVideoLoading, setComposerVideoLoading] = useState(false);
  const [composerVideoError, setComposerVideoError] = useState<string | null>(null);

  const jobLoadedForEventRef = useRef<string | null>(null);
  const slotPreviewPrewarmJobRef = useRef<string | null>(null);
  const pendingMuxBuildsRef = useRef<SlotKey[]>([]);
  /** Slots queued for mux rebuild on job refresh — suppress duplicate viewer triggers. */
  const scheduledMuxSlotsRef = useRef<Set<SlotKey>>(new Set());
  const slotsNeedingAmbientBakeRef = useRef<StitchSessionSlotKey[]>([]);
  const [ambientBakeTick, setAmbientBakeTick] = useState(0);
  const viewerSlotRef = useRef<SlotKey>('intro');
  const lastViewerVideoPathRef = useRef<string | null>(null);
  const jobSlotsSnapshotRef = useRef<Record<string, StitchSlot>>({});
  /** Ignore stale stitch_save_job refresh merges when a newer save is in flight. */
  const stitchSaveSeqRef = useRef(0);

  const bindSlotPreviewUrl = (slot: SlotKey, url: string, intent: MuxSrcUpdateIntent): boolean => {
    setPreviewUrls((prev) => {
      if (!shouldUpdateComposerMuxSrc(prev[slot], url, intent)) return prev;
      return prev[slot] === url ? prev : { ...prev, [slot]: url };
    });
    setStitchComposerPreviewUrl(stitchSessionKey, slot, url);
    return true;
  };

  // Leaving Stitcher tab (keepalive hides pane): pause pool without unmounting.
  useEffect(() => {
    const dispose = effect(() => {
      if (activeTab.value === 'stitcher') return;
      composerPoolRef.current?.pauseAllExcept(null);
    });
    return dispose;
  }, []);

  // Leaving Stitcher / fresh mount: never auto-play module preview or slot waveforms.
  useEffect(() => {
    stopAllPhasePlayback();
    composerPoolRef.current?.pauseAllExcept(null);
    return () => {
      stopAllPhasePlayback();
    };
  }, []);

  // PSL stitch job cache updates (e.g. Beat Gen export) must apply while Stitcher is mounted.
  useEffect(() => {
    return effect(() => {
      const cached = stitchCachedJob.value;
      const eventName = activeScope.value.event_id;
      const projectType = activeProjectType.value;
      const milestoneId = activeMilestoneId.value;
      const sessionKey = stitchJobSessionKey(eventName, projectType, milestoneId);
      if (!cached || jobLoadedForEventRef.current !== sessionKey) return;

      const canonicalSlots = (cached.slots as Record<string, StitchSlot>) ?? {};
      if (!Object.keys(canonicalSlots).length) return;

      const canonicalName = stitchJobNameForScope(eventName, projectType, milestoneId);
      const lineageChanged = slotsWithVideoPathChanges(
        jobSlotsSnapshotRef.current,
        canonicalSlots,
      );
      if (lineageChanged.length > 0) {
        invalidateStitchSlotPlaybackCaches(stitchSessionKey, lineageChanged);
      }
      const mergedSlots = mergeStitchJobSlotsClientPatch(
        jobSlotsSnapshotRef.current,
        canonicalSlots,
        { eventId: eventName },
      );
      const hydrated = hydrateAllSlotMediaFromJob(sessionKey, mergedSlots);
      setJob({
        name: canonicalName,
        slots: mergedSlots,
        transitions: (cached.transitions as Transition[]) ?? [],
        ...(cached['bake_path'] || cached['module_final_cache_key']
          ? stitchJobFooterPlaybackFields(cached as StitchJob)
          : {}),
      });
      jobSlotsSnapshotRef.current = mergedSlots;
      setPreviewUrls((prev) => mergeHydratedPreviewUrlsAfterLineage(
        stripPreviewUrlsForArtifactRebuild(
          prev,
          hydrated.slotsNeedingMux,
          hydrated.slotsNeedingAmbientMix,
        ),
        hydrated.previewUrls,
        lineageChanged,
      ));
      slotPreviewPrewarmJobRef.current = canonicalName;
      const muxQueue = selectSlotsForMuxRebuild(lineageChanged, hydrated.slotsNeedingMux);
      scheduledMuxSlotsRef.current = new Set(muxQueue);
      pendingMuxBuildsRef.current = muxQueue;
      if (hydrated.slotsNeedingAmbientMix.length > 0) {
        slotsNeedingAmbientBakeRef.current = hydrated.slotsNeedingAmbientMix;
        setAmbientBakeTick((n) => n + 1);
      }
      setMuxBuildTick((n) => n + 1);
      setLoading(false);
      setError(null);
    });
  }, []);

  // Drop in-memory slot previews when leaving a stitch session; cache is per session key.
  useEffect(() => {
    const prev = stitchEventRef.current;
    if (prev && prev !== stitchSessionKey) {
      clearStitchSlotSessionEvent(prev);
      clearStitchComposerPreviewUrls(prev);
      setPreviewUrls({});
    }
    stitchEventRef.current = stitchSessionKey;
    const restored = restoreStitchComposerPreviewUrls(stitchSessionKey);
    if (Object.keys(restored).length > 0) {
      setPreviewUrls((prev) => ({ ...restored, ...prev }));
    }
  }, [stitchSessionKey]);

  useEffect(() => {
    if (!job?.slots) return;
    for (const sd of SLOT_DEFS) {
      const slotData = job.slots?.[sd.key];
      const path = slotData?.video_path;
      const audioSig = stitchSlotSessionExpectedSig(slotData);
      const cached = readCachedStitcherPreviewLs(stitchSessionKey, sd.key, slotData);
      const cacheStale = cached && (
        cached.video_path !== path
        || (cached.audio_sig ?? '') !== audioSig
        || (
          (slotData?.playback_recipe_version ?? '').trim()
          !== (cached.playback_recipe_version ?? '').trim()
        )
      );
      if (cacheStale) {
        clearCachedStitcherPreviewLs(stitchSessionKey, sd.key);
      }
      // STITCH_MUX_STALE_WHILE_REVALIDATE_V1 — drop persisted cache only.
      // In-memory previewUrls stay until buildSlotPreview succeeds with new mux.
      reconcileStitchSlotSession(stitchSessionKey, sd.key, slotData);
    }
  }, [
    job?.slots?.['intro']?.video_path,
    job?.slots?.['phase_a']?.video_path,
    job?.slots?.['phase_b']?.video_path,
    job?.slots?.['resolution']?.video_path,
    stitchSlotMuxAudioSig(job?.slots?.['intro']),
    stitchSlotMuxAudioSig(job?.slots?.['phase_a']),
    stitchSlotMuxAudioSig(job?.slots?.['phase_b']),
    stitchSlotMuxAudioSig(job?.slots?.['resolution']),
    stitchSlotMuxAudioSig(job?.slots?.['standalone']),
    stitchSessionKey,
  ]);

  const prevStitchSessionKeyRef = useRef<string | null>(null);

  useEffect(() => {
    syncActiveVideoRoleFromUrl();
  }, [activeScope.value.event_id]);

  /** STITCH_VIEWER_SLOT_LAYOUT_V1 — scope boundary hygiene (event ↔ milestone). */
  useEffect(() => {
    const prev = prevStitchSessionKeyRef.current;
    if (prev && prev !== stitchSessionKey) {
      stopAllPhasePlayback();
      composerPoolRef.current?.pauseAllExcept(null);
      setPreviewLoadingSlot(null);
      setPreviewUrls({});
      setTrackFocusedSlot(null);
    }
    prevStitchSessionKeyRef.current = stitchSessionKey;
  }, [stitchSessionKey]);

  useEffect(() => {
    if (!job?.slots) return;
    const layoutKeys = (standaloneMode ? STANDALONE_SLOT_DEFS : SLOT_DEFS).map((sd) => sd.key);
    const best = pickTrackSlotForLayout(
      job.slots,
      layoutKeys,
      stitchSessionKey,
      activeTargetVideo.value,
    );
    setTrackFocusedSlot((prev) => {
      if (prev && layoutKeys.includes(prev) && slotHasStitchVideo(job.slots, prev)) return prev;
      if (best !== prev) writePersistedTrackSlot(stitchSessionKey, best);
      return best;
    });
  }, [
    job?.name,
    job?.slots?.['intro']?.video_path,
    job?.slots?.['phase_a']?.video_path,
    job?.slots?.['phase_b']?.video_path,
    job?.slots?.['resolution']?.video_path,
    job?.slots?.['standalone']?.video_path,
    stitcherRefreshTick.value,
    stitchSessionKey,
    activeTargetVideo.value,
    standaloneMode,
  ]);

  // One-shot fetch of the ambient catalog. The catalog is module-level static
  // (filesystem inventory of Production/assets/sound_library/ambient/), not
  // scope-dependent — no need to re-fetch on event/video changes.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await apiGet<AmbientPresetListResponse>('phase_b_ambient_preset_list');
      if (!cancelled && res.ok && res.data?.items) {
        setAmbientPresets(res.data.items);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const eventName = activeScope.value.event_id;
    const projectType = activeProjectType.value;
    const milestoneId = activeMilestoneId.value;
    const sessionKey = stitchJobSessionKey(eventName, projectType, milestoneId);
    const canonicalName = stitchJobNameForScope(eventName, projectType, milestoneId);

    if (
      stitchJobSessionHasCache()
      && stitchCachedJob.value
      && jobLoadedForEventRef.current !== sessionKey
    ) {
      const cached = stitchCachedJob.value;
      jobLoadedForEventRef.current = sessionKey;
      setJob({
        name: canonicalName,
        slots: (cached.slots as Record<string, StitchSlot>) ?? {},
        transitions: (cached.transitions as Transition[]) ?? [],
        ...(cached['bake_path'] || cached['module_final_cache_key']
          ? stitchJobFooterPlaybackFields(cached as StitchJob)
          : {}),
      });
      setLoading(false);
      setError(null);
    }

    const softRefresh = jobLoadedForEventRef.current === sessionKey;

    if (jobLoadedForEventRef.current !== sessionKey) {
      lastViewerVideoPathRef.current = null;
    }

    if (!softRefresh) {
      setLoading(true);
    }

    const slotHasVideo = (slot?: StitchSlot) => Boolean((slot?.video_path ?? '').trim());

    const mergeSlotsFromJob = (
      merged: Record<string, StitchSlot>,
      jobSlots: Record<string, StitchSlot> | StitchSlot[] | undefined,
      onlyEmpty = false,
    ) => {
      if (!jobSlots || typeof jobSlots !== 'object' || Array.isArray(jobSlots)) return;
      for (const [key, slot] of Object.entries(jobSlots)) {
        if (!slot?.video_path) continue;
        if (onlyEmpty && slotHasVideo(merged[key])) continue;
        merged[key] = { ...(merged[key] ?? {}), ...slot };
      }
    };

    (async () => {
      try {
        const canonicalDetailRes = await apiGet<{
          job?: StitchJob;
          name?: string;
          slot_warnings?: Record<string, string[]>;
          defaults_applied?: boolean;
          bake_job?: StitchBakeJobSummary;
          module_final_cache_key?: string;
        }>(
          'stitch_editor_job',
          { job_name: canonicalName },
          { fetchTimeoutMs: 120000 },
        );
        if (cancelled) return;

        const hadBakeLatch = Boolean(readStitchBakeBusyLatch(eventName, canonicalName));
        const bakeJob = canonicalDetailRes.data?.bake_job;
        const canonicalJob = canonicalDetailRes.data?.job;
        const reattachJobId = (
          bakeJob?.job_id
          ?? canonicalJob?.active_bake_job_id
          ?? (hadBakeLatch ? readStitchBakeBusyLatch(eventName, canonicalName) : null)
        );
        if (reattachJobId && isStitchBakeStatusActive(bakeJob?.status ?? 'running')) {
          setActiveBakeJobId(reattachJobId);
          writeStitchBakeBusyLatch(eventName, canonicalName, reattachJobId);
          setStatusMsg(stitchBakeStatusMessage(bakeJob ?? { status: 'running' }));
        } else if (bakeJob && isStitchBakeStatusTerminal(bakeJob.status) && hadBakeLatch) {
          writeStitchBakeBusyLatch(eventName, canonicalName, null);
          const toastKey = `${bakeJob.job_id}:${bakeJob.status}`;
          if (bakeTerminalToastRef.current !== toastKey) {
            bakeTerminalToastRef.current = toastKey;
            if (bakeJob.status === 'interrupted') {
              pushToast({
                kind: 'error',
                message: `Bake interrupted: ${bakeJob.error ?? bakeJob.message ?? 'worker lost'}`,
                source: 'stitch-bake-interrupted',
              });
              setStatusMsg(`✗ Bake interrupted: ${bakeJob.error ?? bakeJob.message ?? 'worker lost'}`);
            } else if (bakeJob.status === 'failed') {
              pushToast({
                kind: 'error',
                message: `Bake failed: ${bakeJob.error ?? bakeJob.message ?? 'unknown'}`,
                source: 'stitch-bake-error',
              });
              setStatusMsg(`✗ Bake: ${bakeJob.error ?? bakeJob.message ?? 'unknown'}`);
            } else if (bakeJob.status === 'done') {
              const { canonical, assetId } = stitchBakeSuccessPaths(bakeJob);
              const label = canonical?.split('/').pop() ?? canonicalName;
              setStatusMsg(`✓ Baked + pinned: ${label}`);
              pushToast({
                kind: 'success',
                message: assetId && assetId > 0
                  ? `Final MP4 → ${label} (Directus #${assetId})`
                  : `Final MP4 → ${label}`,
                source: 'stitch-bake-done',
              });
              setModuleFinalRevision((n) => n + 1);
            }
          }
        } else if (shouldToastStitchBakeRefreshFailure(
          hadBakeLatch,
          canonicalDetailRes.ok,
          Boolean(bakeJob),
        )) {
          pushToast({
            kind: 'error',
            message: 'Could not confirm bake job after refresh',
            source: 'stitch-bake-refresh-failure',
          });
          writeStitchBakeBusyLatch(eventName, canonicalName, null);
        }

        const canonicalSlots: Record<string, StitchSlot> = {};
        let mergedTransitions: Transition[] = [];
        if (canonicalDetailRes.ok && canonicalJob) {
          mergeSlotsFromJob(canonicalSlots, canonicalJob.slots as Record<string, StitchSlot>);
          mergedTransitions = canonicalJob.transitions ?? [];
        }

        // Fill only empty canonical slots from legacy jobs — never overwrite persisted slots.
        if (!standaloneMode && Object.keys(canonicalSlots).length < SLOT_DEFS.length) {
          const jobsRes = await apiGet<StitchLibraryResponse>('stitch_editor_jobs');
          if (!cancelled && jobsRes.ok) {
            const jobs = jobsRes.data?.jobs ?? [];
            const relevantSummaries = jobs.filter(
              (j) => j.name?.startsWith('auto_') || j.name?.includes(eventName),
            );
            for (const summary of relevantSummaries) {
              if (!summary.name || summary.name === canonicalName) continue;
              const mergeDetailRes = await apiGet<{ job?: StitchJob; name?: string }>(
                'stitch_editor_job',
                { job_name: summary.name },
                { fetchTimeoutMs: 120000 },
              );
              if (cancelled || !mergeDetailRes.ok || !mergeDetailRes.data?.job) continue;
              mergeSlotsFromJob(
                canonicalSlots,
                mergeDetailRes.data.job.slots as Record<string, StitchSlot>,
                true,
              );
              if (mergeDetailRes.data.job.transitions?.length && !mergedTransitions.length) {
                mergedTransitions = mergeDetailRes.data.job.transitions ?? [];
              }
            }
          }
        }

        if (!cancelled && Object.keys(canonicalSlots).length > 0) {
          const mergedSlots = mergeStitchJobSlotsClientPatch(
            jobSlotsSnapshotRef.current,
            canonicalSlots,
          );
          const clientAmbientChanged = applyDefaultAmbientPresetsToSlots(mergedSlots);
          normalizeStitchSlotAmbientVolumesInPlace(mergedSlots);
          const serverDefaultsApplied = canonicalDetailRes.data?.defaults_applied === true;
          if (serverDefaultsApplied || clientAmbientChanged) {
            clearAllCachedStitcherPreviewsLs(sessionKey);
            await persistJobSlotsByName(
              canonicalName,
              stitchDefaultFieldsPatch(mergedSlots),
              mergedTransitions,
            );
          }
          const clearedDefaults = serverDefaultsApplied || clientAmbientChanged;
          const lineageChanged = slotsWithVideoPathChanges(
            jobSlotsSnapshotRef.current,
            mergedSlots,
          );
          if (lineageChanged.length > 0) {
            invalidateStitchSlotPlaybackCaches(stitchSessionKey, lineageChanged);
          }
          const hydrated = hydrateAllSlotMediaFromJob(sessionKey, mergedSlots);
          setJob({
            name: canonicalName,
            slots: mergedSlots,
            transitions: mergedTransitions,
            ...stitchJobFooterPlaybackFields(canonicalJob, canonicalDetailRes.data),
          });
          jobSlotsSnapshotRef.current = mergedSlots;
          if (clearedDefaults) {
            setPreviewUrls({});
            slotPreviewPrewarmJobRef.current = null;
          } else {
            setPreviewUrls((prev) => mergeHydratedPreviewUrlsAfterLineage(
              prev,
              hydrated.previewUrls,
              lineageChanged,
            ));
          }
          jobLoadedForEventRef.current = sessionKey;
          slotPreviewPrewarmJobRef.current = canonicalName;
          const muxQueue = selectSlotsForMuxRebuild(
            lineageChanged,
            hydrated.slotsNeedingMux,
          );
          scheduledMuxSlotsRef.current = new Set(muxQueue);
          pendingMuxBuildsRef.current = muxQueue;
          if (hydrated.slotsNeedingAmbientMix.length > 0) {
            slotsNeedingAmbientBakeRef.current = hydrated.slotsNeedingAmbientMix;
            setAmbientBakeTick((n) => n + 1);
          }
          setMuxBuildTick((n) => n + 1);
          const warns = canonicalDetailRes.data?.slot_warnings;
          if (warns && Object.keys(warns).length > 0) {
            const flat = Object.entries(warns).flatMap(([k, list]) =>
              list.map((w) => `${k}: ${w}`),
            );
            setStatusMsg(`⚠ ${flat.join(' · ')}`);
          }
          setError(null);
          setLoading(false);
          return;
        }

        // Milestone: keep job shell even when standalone has no video yet (composer + export CTA).
        if (!cancelled && standaloneMode && canonicalJob) {
          const slotsFromJob = stitchJobSlotsAsRecord(
            canonicalJob.slots as Record<string, StitchSlot> | StitchSlot[] | undefined,
          );
          if (!slotsFromJob['standalone']) slotsFromJob['standalone'] = {};
          const mergedSlots = mergeStitchJobSlotsClientPatch(
            jobSlotsSnapshotRef.current,
            slotsFromJob,
          );
          setJob({
            name: canonicalName,
            slots: mergedSlots,
            transitions: mergedTransitions,
            ...stitchJobFooterPlaybackFields(canonicalJob, canonicalDetailRes.data),
          });
          jobSlotsSnapshotRef.current = mergedSlots;
          jobLoadedForEventRef.current = sessionKey;
          setError(null);
          setLoading(false);
          return;
        }

        // Bootstrap: merge from saved job summaries when canonical slots are still empty.
        if (standaloneMode) {
          if (!cancelled) {
            setJob({
              name: canonicalName,
              slots: { standalone: {} },
              transitions: mergedTransitions,
            });
            jobLoadedForEventRef.current = sessionKey;
            setError(null);
            setLoading(false);
          }
          return;
        }
        const jobsRes = await apiGet<StitchLibraryResponse>('stitch_editor_jobs');
        if (cancelled) return;
        if (!jobsRes.ok) {
          setError(jobsRes.error ?? `HTTP ${jobsRes.status}`);
          setLoading(false);
          return;
        }
        const jobs = jobsRes.data?.jobs ?? [];
        const relevantSummaries = jobs.filter(
          (j) => j.name?.startsWith('auto_') || j.name?.includes(eventName),
        );
        const mergedSlots: Record<string, StitchSlot> = {};
        mergedTransitions = [];
        for (const summary of relevantSummaries) {
          if (!summary.name) continue;
          // Canonical job already fetched above (success or failure) — never duplicate GET.
          if (summary.name === canonicalName) continue;
          const mergeDetailRes = await apiGet<{ job?: StitchJob; name?: string }>(
            'stitch_editor_job',
            { job_name: summary.name },
            { fetchTimeoutMs: 120000 },
          );
          if (cancelled || !mergeDetailRes.ok || !mergeDetailRes.data?.job) continue;
          mergeSlotsFromJob(mergedSlots, mergeDetailRes.data.job.slots as Record<string, StitchSlot>);
          if (mergeDetailRes.data.job.transitions?.length && !mergedTransitions.length) {
            mergedTransitions = mergeDetailRes.data.job.transitions ?? [];
          }
        }
        if (Object.keys(mergedSlots).length > 0) {
          const clientAmbientChanged = applyDefaultAmbientPresetsToSlots(mergedSlots);
          normalizeStitchSlotAmbientVolumesInPlace(mergedSlots);
          if (clientAmbientChanged) {
            await persistJobSlotsByName(canonicalName, mergedSlots, mergedTransitions);
          }
          const lsPreviews = hydrateMuxFromLocalStorage(sessionKey, mergedSlots);
          jobSlotsSnapshotRef.current = mergedSlots;
          setJob({
            name: canonicalName,
            slots: mergedSlots,
            transitions: mergedTransitions,
          });
          if (Object.keys(lsPreviews).length > 0) {
            setPreviewUrls((prev) => ({ ...prev, ...lsPreviews }));
          }
          jobLoadedForEventRef.current = sessionKey;
          setError(null);
          setLoading(false);
          return;
        }

        if (!cancelled) {
          // STITCH_JOB_SOFT_REFRESH_V1 — never wipe a loaded job when a background
          // reload fails or times out (e.g. load_job contends with final MP4 bake).
          if (!softRefresh) {
            setJob(null);
          } else if (!canonicalDetailRes.ok) {
            setStatusMsg('⚠ Stitch job refresh delayed — showing last loaded compilation');
          }
          jobLoadedForEventRef.current = sessionKey;
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [
    stitcherRefreshTick.value,
    activeScope.value.event_id,
    activeProjectType.value,
    activeMilestoneId.value,
    serverRehydrateTick.value,
    standaloneMode,
  ]);

  const slotsToShow = standaloneMode
    ? STANDALONE_SLOT_DEFS
    : SLOT_DEFS;
  const multiPhaseSlots = standaloneMode ? slotsToShow : SLOT_DEFS;
  const multiPhaseTotalMs = Math.max(
    1,
    multiPhaseSlots.reduce((acc, sd) => {
      const slot = job?.slots?.[sd.key];
      const dur = slot?.video_path
        ? stitchSlotTimelineDurMs(slot, DEFAULT_SLOT_DUR_MS)
        : STITCH_EMPTY_SEGMENT_MS;
      return acc + dur;
    }, 0),
  );
  const layoutSlotKeys = useMemo(
    () => multiPhaseSlots.map((sd) => sd.key),
    [multiPhaseSlots],
  );
  const viewerSlot: SlotKey = resolveStitchViewerSlot({
    layoutSlotKeys,
    trackFocusedSlot,
  });
  viewerSlotRef.current = viewerSlot;
  const viewerSlotData = job?.slots?.[viewerSlot];
  const viewerWaveformVideoPath = resolveSlotWaveformVideoPath(viewerSlotData);
  const viewerSlotNeedsMux = stitchSlotRequiresMuxedPreview(viewerSlotData);
  const viewerSlotNeedsAmbientMix = stitchSlotRequiresAmbientMix(viewerSlotData);
  const composerVideoUrl = composerSlotUrls[viewerSlot];
  const resolvedComposerUrl = composerVideoUrl;
  const composerUsingMux = Boolean(
    resolvedComposerUrl
    && viewerSlotNeedsMux
    && isStitchMuxPlaybackUrl(resolvedComposerUrl),
  );
  const composerUsingAmbientMix = Boolean(
    resolvedComposerUrl
    && viewerSlotNeedsAmbientMix
    && isStitchMuxPlaybackUrl(resolvedComposerUrl),
  );
  const composerMuxRefreshing = previewLoadingSlot === viewerSlot && composerUsingMux;
  const composerPreviewBuilding = previewLoadingSlot === viewerSlot && !resolvedComposerUrl;
  const composerAmbientBuilding = busySlot?.slot === viewerSlot && busySlot.action === 'ambient';

  useLayoutEffect(() => {
    const video = composerPoolRef.current?.getVideo(viewerSlot) ?? null;
    composerVideoRef.current = video;
    setComposerVideoNode(video);
  }, [viewerSlot, composerSlotUrls, previewUrls]);

  useStitchSlotClientMix(
    composerVideoNode,
    viewerSlotData,
    job?.name ? { jobName: job.name, slotKey: viewerSlot } : null,
  );

  useEffect(() => {
    setComposerVideoError(null);
    const url = composerSlotUrls[viewerSlot];
    const video = composerPoolRef.current?.getVideo(viewerSlot);
    const alreadyLoaded = Boolean(
      url
      && (isStitchComposerUrlLoaded(url) || (video && video.readyState >= 2)),
    );
    setComposerVideoLoading(Boolean(url) && !alreadyLoaded);
  }, [viewerSlot, composerSlotUrls]);

  // Pin resolved playback URL into previewUrls when composer resolved it outside previewUrls state.
  useEffect(() => {
    const url = composerSlotUrls[viewerSlot];
    if (!url || previewUrls[viewerSlot]) return;
    if (
      stitchSlotRequiresMuxedPreview(viewerSlotData)
      && !isStitchMuxPlaybackUrl(url)
    ) return;
    bindSlotPreviewUrl(viewerSlot, url, 'hydrate');
  }, [viewerSlot, composerSlotUrls, previewUrls, viewerSlotData]);

  useEffect(() => {
    setComposerVideoError(null);
  }, [viewerSlot]);

  // Stop stray phase playback when switching stitch slots (pool pauses inactive).
  useEffect(() => {
    if (!job?.name) return;
    stopAllPhasePlayback();
    composerPoolRef.current?.pauseAllExcept(viewerSlot);
    const t = window.setTimeout(() => stopAllPhasePlayback(), 800);
    return () => clearTimeout(t);
  }, [job?.name, viewerSlot]);

  /**
   * STITCH_SLOT_MEDIA_ARTIFACTS_V1 — build missing mux only for slots without server artifacts.
   */
  useEffect(() => {
    if (!job?.name) return;
    const pending = pendingMuxBuildsRef.current;
    if (!pending.length) return;
    pendingMuxBuildsRef.current = [];
    void (async () => {
      for (const slotKey of pending) {
        if (standaloneMode && slotKey !== 'standalone') continue;
        if (!job?.slots?.[slotKey]?.video_path) continue;
        await buildSlotPreview(slotKey, { quiet: true });
        scheduledMuxSlotsRef.current.delete(slotKey);
      }
    })();
  }, [job?.name, muxBuildTick, standaloneMode]);

  /** STITCH_AMBIENT_PREVIEW_V1 — preview build for ambient mix; never saveJobSlots auto-bake. */
  useEffect(() => {
    if (!job?.name) return;
    const pending = [...slotsNeedingAmbientBakeRef.current];
    if (!pending.length) return;
    slotsNeedingAmbientBakeRef.current = [];
    void (async () => {
      for (const slotKey of pending) {
        if (standaloneMode && slotKey !== 'standalone') continue;
        const slot = jobSlotsSnapshotRef.current[slotKey];
        if (!slot?.video_path) continue;
        if ((slot.ambient_mix_hash ?? '').trim()) continue;
        await buildSlotPreview(slotKey as SlotKey, { quiet: true });
      }
    })();
  }, [job?.name, ambientBakeTick, standaloneMode]);

  /**
   * Persist the entire job slots dict via stitch_save_job. Used when sfx_cues
   * change (add/edit/delete) on any slot — the slot.sfx_cues array is the
   * source of truth for per-slot cues per audit doc §3.
   *
   * STITCH_INSTANT_GEOMETRY_BASELINE_V1 — instant drop/range paths update
   * jobSlotsSnapshotRef before calling save; pass geometryBaseline so mux pause
   * + edit_kind still compare pre-edit vs post-edit geometry.
   */
  const saveJobSlots = async (
    nextSlots: Record<string, StitchSlot>,
    transitions?: Transition[],
    opts?: { geometryBaseline?: Record<string, StitchSlot> },
  ): Promise<boolean> => {
    if (!job?.name) return false;
    const jobName = job.name as string;
    if (!stitchSnapshotReadyForSave(nextSlots, activeProjectType.value)) {
      return false;
    }
    const saveSeq = ++stitchSaveSeqRef.current;
    const diffBaseline = opts?.geometryBaseline ?? jobSlotsSnapshotRef.current ?? job.slots ?? {};
    const prevSlots = jobSlotsSnapshotRef.current ?? job.slots ?? {};
    const sanitized: Record<string, StitchSlot> = { ...nextSlots };
    const geometryChangedSlots: StitchSessionSlotKey[] = [];
    for (const [key, slot] of Object.entries(sanitized)) {
      const slotKey = key as StitchSessionSlotKey;
      const prev = diffBaseline[slotKey];
      if (stitchSlotGeometryChanged(prev, slot)) {
        sanitized[slotKey] = stripStaleStitchSlotArtifacts(slot);
        // STITCH_MUX_STALE_WHILE_REVALIDATE_V1 — drop persisted LS only; keep in-memory
        // previewUrls + session mux URL until buildSlotPreview succeeds with new hash.
        clearCachedStitcherPreviewLs(stitchSessionKey, slotKey);
        geometryChangedSlots.push(slotKey);
      }
    }
    if (geometryChangedSlots.length > 0) {
      composerPoolRef.current?.pauseAllExcept(null);
      stopAllPhasePlayback();
      setStatusMsg('Paused — updating SFX preview (video stays loaded)');
    }
    const editKind = inferStitchEditKind(diffBaseline, sanitized);
    const res = await pathappPatch(activeScope.value, 'stitch_save_job', {
      name: jobName,
      slots: sanitized,
      transitions: transitions ?? job.transitions ?? [],
      merge_slots: true,
      edit_kind: editKind,
      dispatch_code: STITCH_SLOT_EDIT_DISPATCH_V1,
    });
    if (res.ok) {
      if (saveSeq !== stitchSaveSeqRef.current) {
        return true;
      }
      const data = res.data as {
        built_slots?: Record<string, {
          ok?: boolean;
          ambient_mix_hash?: string;
          _ambient_mix_url?: string;
          ambient_mix_sig?: string;
          ambient_mix_duration_ms?: number;
          cleared?: boolean;
        }>;
        artifact_build?: {
          build_id?: string;
          status?: string;
          mux_rebuild_keys?: string[];
        };
        edit_dispatch?: {
          mux_rebuild_hint_keys?: string[];
        };
      } | undefined;
      let mergedSlots = mergeStitchJobSlotsClientPatch(prevSlots, sanitized);
      if (data?.built_slots) {
        for (const [key, built] of Object.entries(data.built_slots)) {
          const slotKey = key as StitchSessionSlotKey;
          if (!built?.ok) continue;
          const slot = mergedSlots[slotKey];
          if (!slot) continue;
          if (built.cleared) {
            delete slot.ambient_mix_hash;
            delete slot._ambient_mix_url;
          } else if (built.ambient_mix_hash) {
            slot.ambient_mix_hash = built.ambient_mix_hash;
            if (built.ambient_mix_sig) slot.ambient_mix_sig = built.ambient_mix_sig;
            if (built.ambient_mix_duration_ms) {
              slot.ambient_mix_duration_ms = built.ambient_mix_duration_ms;
            }
            if (built._ambient_mix_url) {
              slot._ambient_mix_url = built._ambient_mix_url;
              // STITCH_SFX_PLAYBACK_TRUTH_V1 — never swap composer to ambient-only
              // URL when slot has SFX; mux preview owns playback until rebuild lands.
              if (!stitchSlotRequiresMuxedPreview(slot)) {
                const url = resolveServerMediaUrl(built._ambient_mix_url);
                bindSlotPreviewUrl(slotKey, url, 'ambient_bake');
                commitMuxSession(stitchSessionKey, slotKey, {
                  previewUrl: url,
                  videoPath: slot.video_path!,
                  audioSig: stitchSlotLiveAmbientSig(slot),
                });
              }
            }
          }
        }
      }
      // STITCH_SAVE_OPTIMISTIC_SLOTS_V1 — refresh merges in background (drop already painted).
      jobSlotsSnapshotRef.current = mergedSlots;
      setJob((prev) => (
        prev
          ? {
              ...prev,
              slots: mergedSlots,
              ...(transitions ? { transitions } : {}),
            }
          : prev
      ));
      void (async () => {
        const refreshRes = await apiGet<{ job?: StitchJob }>(
          'stitch_editor_job',
          { job_name: jobName },
          { fetchTimeoutMs: 120000 },
        );
        if (saveSeq !== stitchSaveSeqRef.current) return;
        if (!refreshRes.ok || !refreshRes.data?.job?.slots) return;
        // STITCH_SAVE_REFRESH_LOCAL_CUES_V1 — server GET is for durable fields; local
        // snapshot owns sfx_cues geometry the operator just dragged (avoid stale revert).
        const refreshed = mergeStitchJobSlotsClientPatch(
          refreshRes.data.job.slots as Record<string, StitchSlot>,
          jobSlotsSnapshotRef.current,
        );
        if (saveSeq !== stitchSaveSeqRef.current) return;
        jobSlotsSnapshotRef.current = refreshed;
        setJob((prev) => (prev ? { ...prev, slots: refreshed } : prev));
      })();
      if (geometryChangedSlots.length > 0) {
        const artBuild = data?.artifact_build;
        const muxHintKeys = data?.edit_dispatch?.mux_rebuild_hint_keys
          ?? artBuild?.mux_rebuild_keys
          ?? [];
        const slotsNeedingMux = geometryChangedSlots.filter((slotKey) =>
          stitchSlotRequiresMuxedPreview(mergedSlots[slotKey]),
        );
        const orchestratorMux = slotsNeedingMux.filter((k) => muxHintKeys.includes(k));

        if (
          artBuild?.build_id
          && (artBuild.status === 'queued' || artBuild.status === 'running')
          && orchestratorMux.length > 0
        ) {
          void (async () => {
            try {
              await pollStitchArtifactBuild(jobName, artBuild.build_id!);
              if (saveSeq !== stitchSaveSeqRef.current) return;
              const refreshRes = await apiGet<{ job?: StitchJob }>(
                'stitch_editor_job',
                { job_name: jobName },
                { fetchTimeoutMs: 120_000 },
              );
              if (!refreshRes.ok || !refreshRes.data?.job?.slots) return;
              const refreshed = mergeStitchJobSlotsClientPatch(
                refreshRes.data.job.slots as Record<string, StitchSlot>,
                jobSlotsSnapshotRef.current,
              );
              jobSlotsSnapshotRef.current = refreshed;
              setJob((prev) => (prev ? { ...prev, slots: refreshed } : prev));
              for (const slotKey of orchestratorMux) {
                const slot = refreshed[slotKey];
                const url = resolvePersistedPlaybackFromArtifacts(slot);
                if (url) {
                  bindSlotPreviewUrl(slotKey, url, 'quiet_rebuild');
                  commitMuxSession(stitchSessionKey, slotKey, {
                    previewUrl: url,
                    videoPath: slot?.video_path!,
                    audioSig: stitchSlotSessionExpectedSig(slot),
                  });
                }
              }
              setStatusMsg('✓ SFX preview updated');
            } catch (err) {
              if (saveSeq !== stitchSaveSeqRef.current) return;
              setStatusMsg(`✗ Preview rebuild: ${err instanceof Error ? err.message : String(err)}`);
            }
          })();
        } else if (slotsNeedingMux.length > 0) {
          scheduledMuxSlotsRef.current = new Set([
            ...scheduledMuxSlotsRef.current,
            ...slotsNeedingMux,
          ]);
          pendingMuxBuildsRef.current = [
            ...new Set([...pendingMuxBuildsRef.current, ...slotsNeedingMux]),
          ];
          setMuxBuildTick((n) => n + 1);
        }
      }
      return true;
    }
    setStatusMsg(`✗ Save HTTP ${res.status}: ${res.error ?? ''}`);
    return false;
  };

  /**
   * Persist transitions only (slots unchanged). Used when a per-boundary
   * transition selector changes kind / audio_xfade_ms. Per spec §3.3.
   */
  const saveJobTransitions = async (nextTransitions: Transition[]): Promise<boolean> => {
    if (!job?.slots || !job?.name) return false;
    return saveJobSlots(job.slots, nextTransitions);
  };

  const onTransitionChange = (next: Transition) => {
    const existing = job?.transitions ?? [];
    const idx = existing.findIndex((t) => t.after_slot === next.after_slot);
    const nextArr = idx >= 0
      ? existing.map((t, i) => (i === idx ? next : t))
      : [...existing, next];
    void saveJobTransitions(nextArr);
  };

  const findTransition = (afterSlot: number): Transition | null => {
    const t = (job?.transitions ?? []).find((x) => x.after_slot === afterSlot);
    if (t) return t;
    return defaultStitchTransitions().find((x) => x.after_slot === afterSlot) ?? null;
  };

  const fetchBeatBoundaries = async (slot?: SlotKey) => {
    setBeatBoundariesLoading(true);
    setBeatBoundaries([]);
    const slotData = slot ? job?.slots?.[slot] : undefined;
    if (slotData?.beat_boundaries?.length) {
      const enriched = slotData.beat_boundaries.map((b) => ({
        ...b,
        duration_ms: b.duration_ms ?? (b.end_ms - b.start_ms),
      }));
      setBeatBoundaries(enriched);
      setBeatBoundariesLoading(false);
      return;
    }
    const scopeTarget =
      slot && (slot === 'intro' || slot === 'resolution') ? slot : undefined;
    const res = await apiGet<{ ok: boolean; beats?: BeatBoundary[] }>(
      'stitch_editor_beat_boundaries',
      {
        event_id: activeScope.value.event_id,
        ...(scopeTarget ? { scope_target_video: scopeTarget } : {}),
      },
    );
    setBeatBoundariesLoading(false);
    if (res.ok && res.data?.beats?.length) {
      setBeatBoundaries(res.data.beats);
    }
  };

  const onTimelineClick = (e: MouseEvent) => {
    const video = composerVideoRef.current;
    if (!video) return;
    const el = e.currentTarget as HTMLElement;
    const box = el.getBoundingClientRect();
    if (box.width <= 0) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - box.left) / box.width));
    const totalMs = beatBoundaries.length > 0
      ? beatBoundaries[beatBoundaries.length - 1].end_ms
      : video.duration * 1000;
    const videoMs = Number.isFinite(video.duration) ? video.duration * 1000 : totalMs;
    const seekMs = Math.min(totalMs, videoMs > 0 ? videoMs : totalMs);
    video.currentTime = (ratio * seekMs) / 1000;
  };

  const buildSlotPreview = async (slot: SlotKey, opts?: { quiet?: boolean }): Promise<boolean> => {
    if (!job?.name) return false;
    const slotData = jobSlotsSnapshotRef.current[slot as string] ?? job?.slots?.[slot];
    if (!slotData?.video_path) {
      if (!opts?.quiet) setStatusMsg(`Slot ${slot} has no video assigned.`);
      return false;
    }
    if (stitchSlotUsesFourFilesPlayback(slotData) || stitchSlotUsesDryAuthorityClientMix(slotData)) {
      const flatUrl = resolveDrySlotSourceVideoUrl(slotData.video_path);
      if (!flatUrl) return false;
      const audioSig = stitchSlotSessionExpectedSig(slotData);
      bindSlotPreviewUrl(slot, flatUrl, 'hydrate');
      const cacheEntry: CachedStitcherPreviewLs = {
        video_path: slotData.video_path,
        preview_url: flatUrl,
        audio_sig: audioSig,
      };
      const recipe = (slotData.playback_recipe_version ?? '').trim();
      if (recipe) cacheEntry.playback_recipe_version = recipe;
      writeCachedStitcherPreviewLs(stitchSessionKey, slot, cacheEntry);
      commitMuxSession(stitchSessionKey, slot, {
        previewUrl: flatUrl,
        videoPath: slotData.video_path,
        audioSig,
      });
      return true;
    }
    const audioSig = stitchSlotSessionExpectedSig(slotData);
    const persistedArtifactUrl = resolvePersistedPlaybackFromArtifacts(slotData);
    if (persistedArtifactUrl && isMuxSessionFresh(stitchSessionKey, slot, slotData)) {
      bindSlotPreviewUrl(slot, persistedArtifactUrl, 'hydrate');
      return true;
    }
    if (
      persistedArtifactUrl
      && previewUrlMatchesPersistedMux(persistedArtifactUrl, slotData)
    ) {
      bindSlotPreviewUrl(slot, persistedArtifactUrl, 'hydrate');
      commitMuxSession(stitchSessionKey, slot, {
        previewUrl: persistedArtifactUrl,
        videoPath: slotData.video_path!,
        audioSig,
      });
      return true;
    }
    if (
      slotData.mux_preview_hash
      && slotData._mux_preview_url
      && stitchSlotMuxPreviewLineageMatches(slotData)
      && isMuxSessionFresh(stitchSessionKey, slot, slotData)
    ) {
      const url = resolveServerMediaUrl(slotData._mux_preview_url);
      bindSlotPreviewUrl(slot, url, 'hydrate');
      commitMuxSession(stitchSessionKey, slot, {
        previewUrl: url,
        videoPath: slotData.video_path!,
        audioSig,
      });
      return true;
    }
    if (isMuxSessionFresh(stitchSessionKey, slot, slotData)) {
      const url = getStitchSlotSession(stitchSessionKey, slot)!.muxPreviewUrl!;
      bindSlotPreviewUrl(slot, url, 'hydrate');
      return true;
    }
    if (opts?.quiet && previewUrls[slot] && isMuxSessionFresh(stitchSessionKey, slot, slotData)) {
      commitMuxSession(stitchSessionKey, slot, {
        previewUrl: previewUrls[slot]!,
        videoPath: slotData.video_path!,
        audioSig,
      });
      return true;
    }
    const cached = readCachedStitcherPreviewLs(stitchSessionKey, slot, slotData);
    if (
      !stitchSlotRequiresMuxedPreview(slotData)
      && cached?.video_path === slotData.video_path
      && (cached.audio_sig ?? '') === audioSig
      && cached.preview_url
    ) {
      bindSlotPreviewUrl(slot, cached.preview_url, 'hydrate');
      commitMuxSession(stitchSessionKey, slot, {
        previewUrl: cached.preview_url,
        videoPath: slotData.video_path,
        audioSig,
      });
      return true;
    }
    // STITCH_MUX_STALE_WHILE_REVALIDATE_V1 — never blank an already-playing mux while
    // ffmpeg rebuilds after SFX/ambient geometry change; swap src only on success.

    const gen = (slotPreviewGenRef.current[slot] ?? 0) + 1;
    slotPreviewGenRef.current[slot] = gen;
    setPreviewLoadingSlot(slot);
    if (!opts?.quiet) {
      setBusySlot({ slot, action: 'preview' });
      setStatusMsg(null);
    }
  const flightKey = stitchMediaFlightKey(stitchSessionKey, slot, audioSig);
  const slotScopeRole =
    slot === 'resolution' ? 'resolution' : slot === 'standalone' ? 'standalone' : 'intro';
  const res = await singleFlightMuxPreview(flightKey, () => pathappPatch(
    activeScope.value,
    'stitch_preview',
    {
      name: job.name,
      slot,
      slot_preview: true,
      transitions: [],
      slots: [slotData],
      scope_video_role: slotScopeRole,
      scope_target_video: slotScopeRole,
    },
      { fetchTimeoutMs: 300_000 },
    ));
    if (gen !== slotPreviewGenRef.current[slot]) return false;
    setPreviewLoadingSlot(null);
    if (!opts?.quiet) setBusySlot(null);

    if (res.ok) {
      const data = res.data as { preview_url?: string; video_playable?: boolean } | undefined;
      if (data?.preview_url && data.video_playable !== false) {
        const muxCommit = {
          previewUrl: data.preview_url!,
          videoPath: slotData.video_path!,
          audioSig,
        };
        bindSlotPreviewUrl(
          slot,
          data.preview_url!,
          opts?.quiet ? 'quiet_rebuild' : 'explicit_preview',
        );
        writeCachedStitcherPreviewLs(stitchSessionKey, slot, {
          video_path: slotData.video_path,
          preview_url: data.preview_url,
          audio_sig: audioSig,
        });
        commitMuxSession(stitchSessionKey, slot, muxCommit);
      }
      if (!opts?.quiet) setStatusMsg(`✓ Preview ${slot} ready`);
      return Boolean(data?.preview_url && data.video_playable !== false);
    }
    const sigSlot = { ...slotData, sfx_cues: slotData.sfx_cues ?? [] };
    const mayBindDry = !stitchSlotRequiresMuxedPreview(sigSlot)
      && !stitchSlotRequiresAmbientMix(sigSlot);
    const dryUrl = mayBindDry ? resolveDrySlotSourceVideoUrl(slotData.video_path) : undefined;
    if (dryUrl) {
      bindSlotPreviewUrl(slot, dryUrl, 'hydrate');
      commitMuxSession(stitchSessionKey, slot, {
        previewUrl: dryUrl,
        videoPath: slotData.video_path!,
        audioSig,
      });
    }
    const data = res.data as { error?: string } | undefined;
    if (!opts?.quiet) {
      setStatusMsg(`✗ Preview HTTP ${res.status}: ${data?.error ?? res.error ?? ''} — playing dry slot video`);
    }
    return false;
  };

  const seekComposerTo = (offsetMs: number, opts?: { play?: boolean }, slotKey?: SlotKey) => {
    const slot = slotKey ?? viewerSlotRef.current;
    const sessionSlot = slot as StitchSessionSlotKey;
    const video = composerPoolRef.current?.getVideo(sessionSlot) ?? composerVideoRef.current;
    if (!video) return;
    const shouldPlay = opts?.play === true;
    const shouldPause = opts?.play === false;
    const apply = () => {
      video.currentTime = Math.max(0, offsetMs / 1000);
      if (shouldPlay) {
        void video.play().catch(() => {});
      } else if (shouldPause) {
        video.pause();
      }
    };
    if (video.readyState >= 1) {
      apply();
      return;
    }
    video.addEventListener('loadedmetadata', apply, { once: true });
  };

  const onPoolSlotCanPlay = (slot: SlotKey, url: string) => {
    markStitchComposerUrlLoaded(url);
    if (slot === viewerSlotRef.current) {
      setComposerVideoLoading(false);
      setComposerVideoError(null);
    }
  };

  const onPoolSlotError = (slot: StitchSessionSlotKey) => {
    if (slot !== viewerSlotRef.current) return;
    const video = composerPoolRef.current?.getVideo(slot);
    const code = video?.error?.code;
    const msg = video?.error?.message || `MEDIA_ERR code=${code ?? '?'}`;
    setComposerVideoLoading(false);
    const slotData = job?.slots?.[slot];
    const usingMux = stitchSlotRequiresMuxedPreview(slotData);
    const dryUrl = slotData?.video_path
      ? resolveDrySlotSourceVideoUrl(slotData.video_path)
      : undefined;
    if (usingMux && dryUrl) {
      bindSlotPreviewUrl(slot, dryUrl, 'hydrate');
      setComposerVideoError(
        `SFX mix preview failed (${msg}) — playing speech-only. Click Review to rebuild the mix.`,
      );
    } else {
      setComposerVideoError(`Video load failed: ${msg}`);
    }
  };

  const onPreviewSlot = async (slot: SlotKey, opts?: { quiet?: boolean }) => {
    const built = await buildSlotPreview(slot, opts);
    if (built) {
      if (layoutSlotKeys.includes(slot)) {
        setTrackFocusedSlot(slot);
        writePersistedTrackSlot(stitchSessionKey, slot);
      }
      void fetchBeatBoundaries(slot);
      seekComposerTo(0, { play: opts?.quiet !== true }, slot);
    }
    return built;
  };

  const onMultiPhaseSegmentClick = (slot: SlotKey, opts?: { playModulePreview?: boolean }) => {
    if (!layoutSlotKeys.includes(slot)) return;
    const target: StitchUiSlotKey = slot === 'standalone'
      ? 'standalone'
      : resolveTrackSlotForInteraction(
        job?.slots,
        stitchSessionKey,
        slot as StitchTrackSlotKey,
        activeTargetVideo.value,
      );
    setTrackFocusedSlot(target);
    if (slotHasStitchVideo(job?.slots, target)) {
      writePersistedTrackSlot(stitchSessionKey, target);
    }
    void fetchBeatBoundaries(target);
    if (!slotHasStitchVideo(job?.slots, target)) return;
    const slotData = job?.slots?.[target];
    const instantUrl = slotData
      ? resolveSlotPlaybackPreviewUrl(stitchSessionKey, target, slotData, previewUrls)
      : undefined;
    if (instantUrl) {
      bindSlotPreviewUrl(target, instantUrl, 'hydrate');
      seekComposerTo(0, { play: opts?.playModulePreview === true }, target);
      return;
    }
    // STITCH_SLOT_SESSION_CACHE_V1 — phase switch is navigation, not a reload.
    if (slotData && isMuxSessionFresh(stitchSessionKey, target, slotData)) {
      const url = getStitchSlotSession(stitchSessionKey, target)!.muxPreviewUrl!;
      bindSlotPreviewUrl(target, url, 'hydrate');
      seekComposerTo(0, { play: opts?.playModulePreview === true }, target);
      return;
    }
    if (previewUrls[target]) {
      seekComposerTo(0, { play: opts?.playModulePreview === true }, target);
      return;
    }
    void buildSlotPreview(target, { quiet: true }).then(() => {
      seekComposerTo(0, { play: opts?.playModulePreview === true }, target);
    });
  };

  const viewerMuxAudioSig = useMemo(
    () => stitchSlotLiveGeometrySig(viewerSlotData),
    [viewerSlotData],
  );

  useEffect(() => {
    if (!job?.name || !viewerSlotData?.video_path) return;
    const sessionSlot = viewerSlot as StitchSessionSlotKey;
    if (!stitchSlotRequiresMuxedPreview(viewerSlotData)) return;
    if (scheduledMuxSlotsRef.current.has(sessionSlot)) return;
    if (previewLoadingSlot === sessionSlot) return;
    const instantUrl = resolveSlotPlaybackPreviewUrl(
      stitchSessionKey,
      sessionSlot,
      viewerSlotData,
      previewUrls,
    );
    if (instantUrl) {
      bindSlotPreviewUrl(sessionSlot, instantUrl, 'hydrate');
      return;
    }
    if (isMuxSessionFresh(stitchSessionKey, sessionSlot, viewerSlotData)) {
      const url = getStitchSlotSession(stitchSessionKey, sessionSlot)?.muxPreviewUrl;
      if (url) {
        bindSlotPreviewUrl(sessionSlot, url, 'hydrate');
      }
      return;
    }
    const hydrated = hydrateMuxFromLocalStorage(stitchSessionKey, { [sessionSlot]: viewerSlotData });
    if (hydrated[sessionSlot]) {
      bindSlotPreviewUrl(sessionSlot, hydrated[sessionSlot]!, 'hydrate');
      return;
    }
    if (previewUrls[sessionSlot] && isMuxSessionFresh(stitchSessionKey, sessionSlot, viewerSlotData)) {
      return;
    }
    const t = window.setTimeout(() => {
      void buildSlotPreview(sessionSlot, { quiet: true });
    }, 400);
    return () => clearTimeout(t);
  }, [
    standaloneMode,
    job?.name,
    viewerSlot,
    viewerSlotData?.video_path,
    viewerMuxAudioSig,
  ]);

  /** Ambient-only slots: bind playback URL; dry speech video until ambient mix is baked. */
  useEffect(() => {
    if (!job?.name || !viewerSlotData?.video_path) return;
    const sessionSlot = viewerSlot as StitchSessionSlotKey;
    if (!stitchSlotRequiresAmbientMix(viewerSlotData)) return;
    if (previewLoadingSlot === sessionSlot) return;
    const instantUrl = resolveSlotPlaybackPreviewUrl(
      stitchSessionKey,
      sessionSlot,
      viewerSlotData,
      previewUrls,
    );
    if (instantUrl) {
      bindSlotPreviewUrl(sessionSlot, instantUrl, 'hydrate');
      return;
    }
    if (isMuxSessionFresh(stitchSessionKey, sessionSlot, viewerSlotData)) {
      const url = getStitchSlotSession(stitchSessionKey, sessionSlot)?.muxPreviewUrl;
      if (url) {
        bindSlotPreviewUrl(sessionSlot, url, 'hydrate');
        return;
      }
    }
    const dryUrl = resolveDrySlotSourceVideoUrl(viewerSlotData.video_path);
    if (dryUrl) {
      bindSlotPreviewUrl(sessionSlot, dryUrl, 'hydrate');
    }
    if (!(viewerSlotData.ambient_mix_hash ?? '').trim()) {
      if (!slotsNeedingAmbientBakeRef.current.includes(sessionSlot)) {
        slotsNeedingAmbientBakeRef.current = [sessionSlot];
        setAmbientBakeTick((n) => n + 1);
      }
    }
  }, [
    standaloneMode,
    job?.name,
    viewerSlot,
    viewerSlotData?.video_path,
    viewerSlotData?.ambient_bed,
    viewerSlotData?.ambient_volume,
    activeScope.value.event_id,
  ]);

  useEffect(() => {
    if (standaloneMode || !job?.name) return;
    const canonical = defaultStitchTransitions();
    const current = resolveStitchTransitions(job.transitions);
    const needsSync =
      !job.transitions?.length
      || JSON.stringify(current) !== JSON.stringify(canonical);
    if (needsSync) void saveJobTransitions(canonical);
  }, [standaloneMode, job?.name, JSON.stringify(job?.transitions)]);

  useEffect(() => {
    if (!job?.transitions?.length || !job?.name) return;
    const needsAudioFix = job.transitions.some((t) => (t.audio_xfade_ms ?? 0) > 0);
    if (!needsAudioFix) return;
    void saveJobTransitions(resolveStitchTransitions(job.transitions));
  }, [job?.name, JSON.stringify(job?.transitions)]);

  const focusedSlotVideoPath =
    trackFocusedSlot != null ? job?.slots?.[trackFocusedSlot]?.video_path : undefined;

  useEffect(() => {
    if (standaloneMode || !trackFocusedSlot || !job?.slots) return;
    void fetchBeatBoundaries(trackFocusedSlot);
  }, [
    standaloneMode,
    trackFocusedSlot,
    focusedSlotVideoPath,
  ]);

  // Reset composer when switching slots.
  useEffect(() => {
    const video = composerVideoRef.current;
    if (!video) return;
    video.pause();
    try {
      video.currentTime = 0;
    } catch {
      // ignore seek before metadata
    }
  }, [viewerSlot]);

  const onBake = async () => {
    if (!job?.name) {
      setStatusMsg('No active stitch job. Send a producer output to Stitcher first.');
      return;
    }
    if (activeBakeJobId) {
      setStatusMsg(stitchBakeStatusMessage({ status: 'running' }));
      return;
    }
    const eventId = activeScope.value.event_id;
    setBusySlot({ slot: 'intro', action: 'bake' });
    setStatusMsg('Submitting bake…');
    const res = await pathappPatch<StitchBakePollResult>(activeScope.value, 'stitch_bake', {
      name: job.name,
    });
    setBusySlot(null);
    if (!res.ok) {
      const detail = res.error_message ?? res.error ?? `HTTP ${res.status}`;
      setStatusMsg(`✗ Bake: ${detail}`);
      pushToast({
        kind: 'error',
        message: `Bake failed: ${detail}`,
        source: 'stitch-bake-error',
      });
      return;
    }
    const jobId = res.data?.job_id;
    if (!jobId) {
      setStatusMsg('✗ Bake: server returned no job_id');
      pushToast({
        kind: 'error',
        message: 'Bake failed: server returned no job_id',
        source: 'stitch-bake-error',
      });
      return;
    }
    writeStitchBakeBusyLatch(eventId, job.name, jobId);
    setActiveBakeJobId(jobId);
    setStatusMsg(stitchBakeStatusMessage(res.data));
    if (res.data?.reattach) {
      pushToast({
        kind: 'info',
        message: 'Reattached to in-progress bake',
        source: 'stitch-bake-reattach',
      });
    }
  };

  // Poll durable bake job until terminal (survives refresh via latch + load_job bake_job).
  useEffect(() => {
    if (!activeBakeJobId || !job?.name) return;
    let cancelled = false;
    let timer: number | null = null;

    const finishTerminal = (data: StitchBakePollResult) => {
      const eventId = activeScope.value.event_id;
      writeStitchBakeBusyLatch(eventId, job.name!, null);
      setActiveBakeJobId(null);
      const toastKey = `${data.job_id ?? activeBakeJobId}:${data.status ?? 'unknown'}`;
      if (bakeTerminalToastRef.current === toastKey) return;
      bakeTerminalToastRef.current = toastKey;

      if (data.status === 'done') {
        const { canonical, assetId } = stitchBakeSuccessPaths(data);
        const label = canonical?.split('/').pop() ?? job.name ?? 'module';
        setStatusMsg(`✓ Baked + pinned: ${label}`);
        pushToast({
          kind: 'success',
          message: assetId && assetId > 0
            ? `Final MP4 → ${label} (Directus #${assetId})`
            : `Final MP4 → ${label}`,
          source: 'stitch-bake-done',
        });
        setModuleFinalRevision((n) => n + 1);
        stitcherRefreshTick.value += 1;
        return;
      }
      const err = data.error ?? data.message ?? data.result?.error_message ?? 'Bake failed';
      setStatusMsg(`✗ Bake: ${err}`);
      pushToast({
        kind: 'error',
        message: data.status === 'interrupted'
          ? `Bake interrupted: ${err}`
          : `Bake failed: ${err}`,
        source: data.status === 'interrupted' ? 'stitch-bake-interrupted' : 'stitch-bake-error',
      });
    };

    const poll = async () => {
      const res = await apiGet<StitchBakePollResult>('stitch_bake_status', {
        job_id: activeBakeJobId,
      });
      if (cancelled) return;
      if (!res.ok || !res.data) {
        pushToast({
          kind: 'error',
          message: `Bake poll error: ${res.error ?? `HTTP ${res.status}`}`,
          source: 'stitch-bake-poll-error',
        });
        writeStitchBakeBusyLatch(activeScope.value.event_id, job.name!, null);
        setActiveBakeJobId(null);
        return;
      }
      setStatusMsg(stitchBakeStatusMessage(res.data));
      if (!isStitchBakeStatusTerminal(res.data.status)) {
        timer = window.setTimeout(poll, STITCH_BAKE_POLL_INTERVAL_MS);
        return;
      }
      finishTerminal(res.data);
    };

    poll();
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [activeBakeJobId, job?.name]);

  // Reconcile bake latch on tab visibility (server restart → interrupted).
  useEffect(() => {
    if (!job?.name) return;
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      const eventId = activeScope.value.event_id;
      const latched = readStitchBakeBusyLatch(eventId, job.name!);
      if (latched && !activeBakeJobId) {
        setActiveBakeJobId(latched);
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [job?.name, activeBakeJobId]);

  const onLoudnormSlot = async (slot: SlotKey) => {
    const slotData = job?.slots?.[slot];
    if (!slotData?.video_path) {
      setStatusMsg(`Slot ${slot} has no video assigned.`);
      return;
    }
    setBusySlot({ slot, action: 'loudnorm' });
    setStatusMsg(`Applying loudnorm to ${slot}…`);
    const res = await pathappPatch(activeScope.value, 'stitch_loudnorm', {
      input_path: slotData.video_path,
    });
    setBusySlot(null);
    if (res.ok) {
      setStatusMsg(`✓ Loudnorm applied to ${slot}`);
      stitcherRefreshTick.value += 1;
    } else {
      const data = res.data as { error?: string } | undefined;
      setStatusMsg(`✗ Loudnorm HTTP ${res.status}: ${data?.error ?? res.error}`);
    }
  };

  // --------------------------------------------------------------------------
  // Per-slot trim handlers (G9-G10) — STITCHER_PER_SLOT_TRIMS_V1 (HARD)
  //
  // Per audit doc §5 LOCKED:
  //   - trim_in_ms (default 0) and trim_out_ms (null = end of clip)
  //   - Persisted via stitch_save_job extension; server-side ffmpeg -ss/-to
  //     in _stitch_normalize_slot with cache key including trim fingerprint
  //
  // UX: numeric inputs in SECONDS (Cursor v8 Q9 deferred keyboard nudge);
  // wire format remains ms.
  // --------------------------------------------------------------------------

  const onTrimChange = (slotKey: SlotKey, side: 'in' | 'out', valueSeconds: string) => {
    if (!job?.slots) return;
    const slot = job.slots[slotKey];
    if (!slot) return;
    // Empty input on trim_out means "end of clip" → null per audit doc §5.
    const ms: number | null = valueSeconds === '' || side === 'out' && Number(valueSeconds) <= 0
      ? null
      : Math.max(0, Math.round(Number(valueSeconds) * 1000));
    const nextSlot: StitchSlot = {
      ...slot,
      ...(side === 'in'
        ? { trim_in_ms: ms ?? 0 }
        : { trim_out_ms: ms }),
    };
    const nextSlots: Record<string, StitchSlot> = {
      ...job.slots,
      [slotKey]: nextSlot,
    };
    void saveJobSlots(nextSlots);
  };

  const onAmbientBedChange = async (slot: SlotKey, value: string) => {
    if (!job?.slots?.[slot]) return;
    setBusySlot({ slot, action: 'ambient' });
    const eventId = activeScope.value.event_id;
    beginStitchAmbientPatch(eventId, slot);
    const prev = job.slots[slot] ?? {};
    const nextSlot: StitchSlot = { ...prev, ambient_bed: value };
    if (value) {
      nextSlot.ambient_volume = STITCH_AMBIENT_BED_VOLUME;
    } else {
      delete nextSlot.ambient_volume;
    }
    delete nextSlot.ambient_bed_path;
    const nextSlots: Record<string, StitchSlot> = {
      ...job.slots,
      [slot]: nextSlot,
    };
    try {
      const ok = await saveJobSlots(nextSlots);
      setBusySlot(null);
      if (ok) {
        setStatusMsg(
          value
            ? `✓ ${slot} ambient bed → ${value} (composer preview updated)`
            : `✓ ${slot} ambient bed cleared`,
        );
      }
    } finally {
      endStitchAmbientPatch(eventId, slot);
    }
  };

  // --------------------------------------------------------------------------
  // Per-slot SFX cue handlers (G3 / G4 / G5)
  // --------------------------------------------------------------------------

  const onSfxDropOnSlot = (slotKey: SlotKey) => (
    lib_key: string,
    source_path: string,
    offset_ms: number,
    duration_ms: number,
  ) => {
    if (!job?.slots) return;
    const slot = job.slots[slotKey];
    if (!slot) return;
    if (!slot?.video_path) {
      setStatusMsg('Assign slot video before placing SFX cues.');
      return;
    }
    const slotDur = stitchSlotTimelineDurMs(slot, DEFAULT_SLOT_DUR_MS);
    // Trust timeline drop math (WaveSurfer/extract duration). Only cap when slot
    // duration is known and the cue would extend past the slot end.
    let durMs = Math.max(250, duration_ms);
    if (slotDur > 0 && offset_ms + durMs > slotDur) {
      durMs = Math.max(250, slotDur - offset_ms);
    }
    const newCue: SfxCue = {
      id: generateCueId('cue'),
      source_path,
      name: source_path.split('/').pop() ?? lib_key,
      offset_ms,
      duration_ms: durMs,
      ...SFX_DEFAULTS,
    };
    const nextCues = [...(slot.sfx_cues ?? []), newCue];
    const nextSlots: Record<string, StitchSlot> = {
      ...job.slots,
      [slotKey]: { ...slot, sfx_cues: nextCues },
    };
    // STITCH_SFX_DROP_INSTANT_V1 — cue marker immediately; persist async.
    const geometryBaseline = { ...(jobSlotsSnapshotRef.current ?? job.slots ?? {}) };
    const merged = mergeStitchJobSlotsClientPatch(job.slots, nextSlots);
    jobSlotsSnapshotRef.current = merged;
    setJob((prev) => (prev ? { ...prev, slots: merged } : prev));
    void saveJobSlots(nextSlots, undefined, { geometryBaseline });
  };

  const onSfxCueRangeChangeOnSlot = (slotKey: SlotKey) => (
    cueId: string,
    offsetMs: number,
    durationMs: number,
  ) => {
    const baseSlots = jobSlotsSnapshotRef.current;
    const slot = baseSlots[slotKey] ?? job?.slots?.[slotKey];
    if (!slot) return;
    const nextCues = (slot.sfx_cues ?? []).map((c) =>
      c.id === cueId
        ? { ...c, offset_ms: offsetMs, duration_ms: durationMs }
        : c,
    );
    const nextSlots: Record<string, StitchSlot> = {
      ...baseSlots,
      ...(job?.slots ?? {}),
      [slotKey]: { ...slot, sfx_cues: nextCues },
    };
    // STITCH_SFX_RANGE_INSTANT_V1 — paint cue geometry before save (same as drop path).
    const geometryBaseline = { ...baseSlots };
    const merged = mergeStitchJobSlotsClientPatch(baseSlots, nextSlots);
    jobSlotsSnapshotRef.current = merged;
    setJob((prev) => (prev ? { ...prev, slots: merged } : prev));
    void saveJobSlots(nextSlots, undefined, { geometryBaseline });
  };

  const onSfxClickOnSlot = (slotKey: SlotKey) => (
    cueId: string,
    anchor: { x: number; y: number },
  ) => {
    setPopover({ scope: 'slot', slotKey, cueId, anchor });
  };

  const onSfxPatch = (updated: SfxCue) => {
    if (!popover || popover.scope !== 'slot' || !popover.slotKey) return;
    if (!job?.slots) return;
    const slotKey = popover.slotKey;
    const slot = job.slots[slotKey];
    if (!slot) return;
    const nextCues = (slot.sfx_cues ?? []).map((c) =>
      c.id === updated.id ? updated : c,
    );
    const nextSlots: Record<string, StitchSlot> = {
      ...job.slots,
      [slotKey]: { ...slot, sfx_cues: nextCues },
    };
    void saveJobSlots(nextSlots);
  };

  const onSfxDelete = () => {
    if (!popover || popover.scope !== 'slot' || !popover.slotKey) return;
    if (!job?.slots) return;
    const slotKey = popover.slotKey;
    const slot = job.slots[slotKey];
    if (!slot) return;
    const deletedCue = (slot.sfx_cues ?? []).find((c) => c.id === popover.cueId);
    const nextCues = (slot.sfx_cues ?? []).filter((c) => c.id !== popover.cueId);
    let nextSlot: StitchSlot = { ...slot, sfx_cues: nextCues };
    const dismissKey = canonicalSfxDismissKey(slotKey, deletedCue);
    if (dismissKey) {
      nextSlot = { ...nextSlot, [dismissKey]: true };
    }
    const nextSlots: Record<string, StitchSlot> = {
      ...job.slots,
      [slotKey]: nextSlot,
    };
    void saveJobSlots(nextSlots);
    setPopover(null);
  };

  // --------------------------------------------------------------------------
  // Module-level SFX cue handlers (G6)
  // --------------------------------------------------------------------------

  /**
   * Module-level cue: persists to state.module_sfx_cues via /api/timeline/cues.
   * Distinct path from per-slot cues which travel via stitch_save_job.
   * Per audit doc §3 module-level scope.
   *
   * Module timeline duration fallback: spans across all slots; for the drop
   * offset compute we use the sum of slot durations (or DEFAULT × 4 fallback).
   */
  const moduleTimelineDurMs = (): number => {
    if (!job?.slots) return DEFAULT_SLOT_DUR_MS * 4;
    let total = 0;
    for (const sd of SLOT_DEFS) {
      const s = job.slots[sd.key];
      total += stitchSlotTimelineDurMs(s, DEFAULT_SLOT_DUR_MS);
    }
    return total > 0 ? total : DEFAULT_SLOT_DUR_MS * 4;
  };

  const onModuleSfxDrop = async (lib_key: string, source_path: string, offset_ms: number) => {
    const cueId = generateCueId('mod_cue');
    const res = await pathappPatch(activeScope.value, 'timeline_cue_upsert', {
      id: cueId,
      cue_type: 'sfx',
      source_path,
      offset_ms,
      volume: SFX_DEFAULTS.volume,
      fadein_ms: SFX_DEFAULTS.fadein_ms,
      fadeout_ms: SFX_DEFAULTS.fadeout_ms,
    });
    if (res.ok) {
      setStatusMsg(`✓ Module SFX cue added: ${source_path.split('/').pop() ?? lib_key}`);
    } else {
      setStatusMsg(`✗ Module cue HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  const onImageDropOnSlot = (slotKey: SlotKey) => async (payload: DragPayload) => {
    if (payload.kind !== 'lib-image' || !job?.slots) return;
    const videoPath = payload.abs_path;
    if (!videoPath) {
      setStatusMsg('✗ Image drop: missing abs_path on library payload');
      return;
    }
    const nextSlots: Record<string, StitchSlot> = {
      ...job.slots,
      [slotKey]: { ...job.slots[slotKey], video_path: videoPath },
    };
    const ok = await saveJobSlots(nextSlots);
    if (ok) {
      setStatusMsg(`✓ Assigned image to ${slotKey}: ${videoPath.split('/').pop() ?? videoPath}`);
    }
  };

  // Module strip drop target — sfx-strip context: lib-sfx only.
  const moduleDropHandlers = makeDropTarget(
    (payload: DragPayload, e: DragEvent) => {
      if (payload.kind !== 'lib-sfx') return;
      const target = e.currentTarget as HTMLElement | null;
      if (!target) return;
      const box = target.getBoundingClientRect();
      if (box.width <= 0) return;
      const relativeX = (e.clientX - box.left) / box.width;
      const clamped = Math.max(0, Math.min(1, relativeX));
      const offsetMs = Math.round(clamped * moduleTimelineDurMs());
      void onModuleSfxDrop(payload.lib_key, payload.source_path, offsetMs);
    },
    acceptDragForTarget('sfx-strip'),
    'sfx-strip',
  );
  const moduleTimelineRef = useRef<HTMLDivElement>(null);
  useDropTargetCapture(moduleTimelineRef, moduleDropHandlers, [moduleDropHandlers]);

  // Active popover cue — read from job state when scope='slot'.
  const popoverCue: SfxCue | null = (() => {
    if (!popover) return null;
    if (popover.scope === 'slot' && popover.slotKey && job?.slots) {
      const slot = job.slots[popover.slotKey];
      return slot?.sfx_cues?.find((c) => c.id === popover.cueId) ?? null;
    }
    return null;
  })();

  const showStitcherLoading =
    (loading || (stitchJobLoading.value && stitchActiveKey.value === stitchSessionKey))
    && !stitchJobSessionHasCache();

  return (
    <section
      class="mn-tab-pane mn-stitcher-pane"
      data-testid="pane-stitcher"
      data-stitch-default-ambient-beds={STITCH_DEFAULT_AMBIENT_BEDS_V1}
      data-stitch-ambient-volume-persist={STITCH_AMBIENT_VOLUME_PERSIST_V1}
      data-stitch-slot-canonical-defaults={STITCH_SLOT_CANONICAL_DEFAULTS_V1}
      data-stitch-live-geometry-sig={STITCH_SLOT_LIVE_GEOMETRY_SIG_V1}
      data-stitch-slot-video-lineage={STITCH_SLOT_VIDEO_LINEAGE_V1}
      data-stitch-mux-video-lineage={STITCH_MUX_VIDEO_LINEAGE_V1}
      data-stitch-mux-rebuild-queue={STITCH_MUX_REBUILD_QUEUE_V1}
      data-stitch-canonical-defaults-persist={STITCH_CANONICAL_DEFAULTS_PERSIST_V1}
      data-stitch-ambient-select-hydrate={STITCH_AMBIENT_SELECT_HYDRATE_V1}
    >
      <header class="mn-pane-header">
        <h2>Stitcher</h2>
        <span class="mn-scope-chip" data-testid="stitcher-scope-chip">
          scope: {producerScopeChipLabel()}
        </span>
      </header>

      {showStitcherLoading ? (
        <p class="mn-loading" data-testid="stitcher-loading">Loading stitch jobs…</p>
      ) : error ? (
        <div class="mn-empty" data-testid="stitcher-error">
          <p class="mn-warn">Could not reach /api/stitch_editor/jobs.</p>
          <p class="mn-dim">{error}</p>
        </div>
      ) : !job ? (
        <div class="mn-empty" data-testid="stitcher-no-job">
          <p>
            No active stitch job for{' '}
            {standaloneMode && activeMilestoneId.value
              ? `milestone ${activeMilestoneId.value}`
              : activeScope.value.event_id}
            .
          </p>
          <p class="mn-dim">
            {standaloneMode
              ? 'Beat Gen → Send to Stitcher exports the standalone MP4 here, then Bake final MP4.'
              : 'Use Phase A / Phase B "Export to Stitcher" buttons to send producer outputs here, then Bake the final MP4.'}
          </p>
        </div>
      ) : (
        <>
          {standaloneMode && milestoneStandaloneNeedsExport(job.slots) ? (
            <div class="mn-warn" data-testid="stitcher-milestone-export-needed" style={{ marginBottom: '0.75rem' }}>
              Standalone slot is empty — open Beat Gen and use <strong>Send to Stitcher</strong> before baking.
            </div>
          ) : null}
          <div
            class="mn-stitcher-multiphase-track"
            data-testid="stitcher-multiphase-track"
            data-stitcher-single-composer="STITCHER_SINGLE_COMPOSER_V1"
          >
            <div class="mn-stitcher-multiphase-track-header">
              <strong>Multi-phase view track</strong>
              <span class="mn-dim">click a phase to switch slot review · selection persists per event</span>
            </div>
            <div class="mn-stitcher-multiphase-track-rail">
              {multiPhaseSlots.map((sd) => {
                const slot = job.slots?.[sd.key];
                const hasVideo = Boolean(slot?.video_path);
                const durMs = hasVideo
                  ? stitchSlotTimelineDurMs(slot, DEFAULT_SLOT_DUR_MS)
                  : STITCH_EMPTY_SEGMENT_MS;
                const widthPct = (durMs / multiPhaseTotalMs) * 100;
                const selected = trackFocusedSlot === sd.key;
                return (
                  <button
                    type="button"
                    key={`track-${sd.key}`}
                    class={`mn-stitcher-multiphase-segment${selected ? ' is-active' : ''}${hasVideo ? '' : ' is-empty'}`}
                    style={`width:${widthPct.toFixed(3)}%`}
                    data-testid={`stitcher-multiphase-segment-${sd.key}`}
                    onClick={() => onMultiPhaseSegmentClick(sd.key)}
                    title={slot?.video_path ?? `${sd.label} — no video yet (black frame)`}
                  >
                    <span class="mn-stitcher-multiphase-segment-label">{sd.label}</span>
                    <span class="mn-stitcher-multiphase-segment-meta">{(durMs / 1000).toFixed(1)}s</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div
              class="mn-stitcher-slot-composer"
              data-testid="stitcher-slot-composer"
              data-stitcher-slot-composer="STITCHER_SLOT_COMPOSER_V1"
              data-stitch-slot-preview-video-playable="STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1"
              data-stitch-unified-playback="STITCH_UNIFIED_PLAYBACK_V1"
              data-stitch-viewer-slot-layout={STITCH_VIEWER_SLOT_LAYOUT_V1}
              data-stitch-save-slot-durable-merge={STITCH_SAVE_SLOT_DURABLE_MERGE_V1}
              data-stitch-sfx-playback-truth={STITCH_SFX_PLAYBACK_TRUTH_V1}
              data-stitch-sfx-drop-instant="STITCH_SFX_DROP_INSTANT_V1"
              data-stitch-instant-geometry-baseline="STITCH_INSTANT_GEOMETRY_BASELINE_V1"
              data-stitch-slot-timeline-atomic={STITCH_SLOT_TIMELINE_ATOMIC_V1}
              data-stitch-mux-pause-on-geometry={STITCH_MUX_PAUSE_ON_GEOMETRY_V1}
              data-stitch-track-focus-session-key={stitchSessionKey}
              data-stitch-composer-dry-playback="STITCH_COMPOSER_DRY_PLAYBACK_V1"
              data-stitch-ambient-preview="STITCH_AMBIENT_PREVIEW_V1"
              data-stitch-composer-mux-fallback="STITCH_COMPOSER_MUX_FALLBACK_V1"
              data-stitch-slot-mux-audio-sig={STITCH_SLOT_MUX_AUDIO_SIG_V1}
              data-stitch-slot-requires-muxed-preview="STITCH_SLOT_REQUIRES_MUXED_PREVIEW_V1"
              data-stitch-mux-stale-while-revalidate="STITCH_MUX_STALE_WHILE_REVALIDATE_V1"
              data-stitch-artifact-orchestrator={STITCH_ARTIFACT_ORCHESTRATOR_V1}
              data-stitch-single-owner="STITCH_SINGLE_OWNER_V1"
              data-stitch-slot-edit-dispatch={STITCH_SLOT_EDIT_DISPATCH_V1}
              data-stitch-mux-src-identity={STITCH_MUX_SRC_IDENTITY_V1}
              data-stitch-slot-session-cache="STITCH_SLOT_SESSION_CACHE_V1"
              data-stitch-composer-video-pool={STITCH_COMPOSER_VIDEO_POOL_V1}
              data-stitch-ambient-bake-on-save={STITCH_AMBIENT_BAKE_ON_SAVE_V1}
              data-stitch-preview-ls-hydrate={STITCH_PREVIEW_LS_HYDRATE_V1}
            >
              <div class="mn-stitcher-slot-composer-header">
                <strong>
                  {slotsToShow.find((s) => s.key === viewerSlot)?.label ?? viewerSlot}
                  {' '}
                  — slot review
                </strong>
                <span class="mn-dim">
                  {composerMuxRefreshing
                    ? 'Updating SFX preview — video stays loaded'
                    : composerUsingMux
                    ? 'SFX preview (speech + ambient + SFX) · drag waveform to seek'
                    : composerUsingAmbientMix
                      ? 'Speech + ambient bed · use dropdown below to change ambient'
                      : composerAmbientBuilding
                        ? 'Saving ambient bed…'
                        : composerPreviewBuilding
                          ? 'Building SFX preview…'
                          : composerVideoError?.includes('speech-only')
                            ? 'Speech-only fallback — click Review to rebuild SFX mix'
                            : 'Slot video · no ambient or SFX'}
                </span>
              </div>
              <div class="mn-stitcher-slot-composer-body">
                <div
                  class="mn-stitcher-composer-video-wrap"
                  {...(stitchSlotRequiresClientPreviewMix(viewerSlotData)
                    ? { 'data-stitch-client-mix': STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 }
                    : {})}
                >
                  {composerVideoUrl ? (
                    <StitchComposerVideoPool
                      activeSlot={viewerSlot as StitchSessionSlotKey}
                      slotUrls={composerSlotUrls}
                      poolRef={composerPoolRef}
                      onSlotCanPlay={onPoolSlotCanPlay}
                      onSlotError={onPoolSlotError}
                    />
                  ) : (
                    <div
                      class="mn-stitcher-composer-video-status mn-stitcher-composer-video-loading"
                      data-testid="stitcher-composer-video-waiting-mux"
                    >
                      {composerPreviewBuilding
                        ? 'Building muxed preview…'
                        : 'Assign slot video to preview'}
                    </div>
                  )}
                  {composerVideoLoading ? (
                    <div
                      class="mn-stitcher-composer-video-status mn-stitcher-composer-video-loading"
                      data-testid="stitcher-composer-video-loading"
                    >
                      Loading video…
                    </div>
                  ) : null}
                </div>
                {composerVideoError ? (
                  <p
                    class="mn-stitcher-composer-video-error"
                    data-testid="stitcher-composer-video-error"
                    role="alert"
                  >
                    {composerVideoError}
                  </p>
                ) : null}
                {viewerWaveformVideoPath ? (
                <StitcherSlotWaveform
                  slotKey={viewerSlot}
                  videoPath={viewerWaveformVideoPath}
                  {...(viewerSlotData?.ambient_bed ? { ambientBed: viewerSlotData.ambient_bed } : {})}
                  {...(viewerSlotData?.mix_sig ? { mixSig: viewerSlotData.mix_sig } : {})}
                  {...(viewerSlotData?._waveform_peaks_url ? { artifactPeaksUrl: viewerSlotData._waveform_peaks_url } : {})}
                  videoDurMs={stitchSlotTimelineDurMs(viewerSlotData, DEFAULT_SLOT_DUR_MS)}
                  cues={viewerSlotData?.sfx_cues ?? []}
                  displayOnly
                  masterVideo={composerVideoRef}
                  {...(composerVideoUrl ? { masterVideoSrc: composerVideoUrl } : {})}
                  onMasterSeek={(ms) => {
                    const v = composerVideoRef.current;
                    const playing = Boolean(v && !v.paused && !v.ended);
                    seekComposerTo(ms, { play: playing ? true : false });
                  }}
                  compact={false}
                  onSfxDrop={onSfxDropOnSlot(viewerSlot)}
                  onCueRangeChange={onSfxCueRangeChangeOnSlot(viewerSlot)}
                  onCueClick={onSfxClickOnSlot(viewerSlot)}
                />
                ) : null}
              </div>
              <div
                class={`mn-beat-timeline${beatBoundariesLoading ? ' mn-beat-timeline-loading' : ''}`}
                data-testid="mn-beat-timeline"
                onClick={onTimelineClick}
                title="Click to seek"
              >
                {beatBoundaries.length > 0 ? (() => {
                  const video = composerVideoRef.current;
                  const boundaryTotal = beatBoundaries[beatBoundaries.length - 1].end_ms;
                  const videoMs = video && Number.isFinite(video.duration)
                    ? video.duration * 1000
                    : boundaryTotal;
                  const totalMs = videoMs > 0 ? Math.min(boundaryTotal, videoMs) : boundaryTotal;
                  return beatBoundaries.map((b, i) => {
                    const leftPct = (b.start_ms / totalMs) * 100;
                    const widthPct = (b.duration_ms / totalMs) * 100;
                    return (
                      <div
                        key={b.beat_id}
                        class={`mn-beat-segment ${i % 2 === 0 ? 'mn-beat-even' : 'mn-beat-odd'}`}
                        style={`left:${leftPct.toFixed(2)}%;width:${widthPct.toFixed(2)}%`}
                        title={`${b.beat_id}: ${(b.start_ms / 1000).toFixed(1)}s – ${(b.end_ms / 1000).toFixed(1)}s`}
                      >
                        <span class="mn-beat-segment-label">{b.beat_id.replace('beat_', '')}</span>
                      </div>
                    );
                  });
                })() : (
                  <span class="mn-dim" style="padding:0 8px">
                    {beatBoundariesLoading ? 'Loading beat markers…' : 'No beat markers (non-assembled slot)'}
                  </span>
                )}
              </div>
            </div>

          <div class="mn-stitcher-strip" data-testid="stitcher-strip">
            {slotsToShow.map((sd) => {
              const slot = job.slots?.[sd.key];
              const busy = busySlot?.slot === sd.key;
              const slotDurMs = stitchSlotTimelineDurMs(slot, DEFAULT_SLOT_DUR_MS);
              const cues = slot?.sfx_cues ?? [];
              const waveformVideoPath = resolveSlotWaveformVideoPath(slot);
              return (
                <div
                  class="mn-stitcher-slot"
                  key={sd.key}
                  data-testid={`stitcher-slot-${sd.key}`}
                  data-has-video={slot?.video_path ? 'true' : 'false'}
                >
                  <div class="mn-stitcher-slot-header">
                    <strong>{sd.label}</strong>
                    {slot?.loudnorm_already_applied ? (
                      <span class="mn-stitcher-loudnorm-tag">speech loudnorm ✓</span>
                    ) : null}
                  </div>
                  <SlotImageDropTarget
                    slotKey={sd.key}
                    hasVideo={Boolean(slot?.video_path)}
                    videoLabel={slot?.video_path?.split('/').pop()}
                    videoTitle={slot?.video_path}
                    onImageDrop={onImageDropOnSlot(sd.key)}
                  />
                  {sd.key === viewerSlot ? (
                    <p class="mn-dim mn-stitcher-slot-composer-hint" data-testid={`stitcher-slot-hint-${sd.key}`}>
                      ↑ Synced playback in slot review above — drop SFX on that waveform
                    </p>
                ) : slot?.video_path && waveformVideoPath ? (
                    <StitcherSlotWaveform
                      slotKey={sd.key}
                      videoPath={waveformVideoPath}
                      {...(slot?.ambient_bed ? { ambientBed: slot.ambient_bed } : {})}
                      {...(slot?.mix_sig ? { mixSig: slot.mix_sig } : {})}
                      {...(slot?._waveform_peaks_url ? { artifactPeaksUrl: slot._waveform_peaks_url } : {})}
                      videoDurMs={slotDurMs}
                      cues={cues}
                      compact
                      displayOnly
                      playbackDisabled
                      onSfxDrop={onSfxDropOnSlot(sd.key)}
                      onCueRangeChange={onSfxCueRangeChangeOnSlot(sd.key)}
                      onCueClick={onSfxClickOnSlot(sd.key)}
                    />
                  ) : null}
                  {/* Per-slot trim controls (G9-G10) — values in seconds for
                      UX; wire format = ms. trim_out blank/zero → null = full
                      clip end (audit doc §5 LOCKED). */}
                  <div class="mn-stitcher-slot-row mn-stitcher-trim-row">
                    <label class="mn-dim" for={`stitcher-trim-in-${sd.key}`}>Trim in (s):</label>
                    <input
                      type="number"
                      id={`stitcher-trim-in-${sd.key}`}
                      data-testid={`stitcher-slot-trim-in-${sd.key}`}
                      min={0}
                      max={300}
                      step={0.1}
                      value={slot?.trim_in_ms ? (slot.trim_in_ms / 1000).toString() : '0'}
                      disabled={busy || !slot?.video_path}
                      onInput={(e: Event) =>
                        onTrimChange(sd.key, 'in', (e.target as HTMLInputElement).value)
                      }
                      onBlur={(e: Event) =>
                        onTrimChange(sd.key, 'in', (e.target as HTMLInputElement).value)
                      }
                    />
                    <label class="mn-dim" for={`stitcher-trim-out-${sd.key}`}>Trim out (s):</label>
                    <input
                      type="number"
                      id={`stitcher-trim-out-${sd.key}`}
                      data-testid={`stitcher-slot-trim-out-${sd.key}`}
                      min={0}
                      max={300}
                      step={0.1}
                      value={
                        slot?.trim_out_ms !== null && slot?.trim_out_ms !== undefined
                          ? (slot.trim_out_ms / 1000).toString()
                          : ''
                      }
                      placeholder="end"
                      disabled={busy || !slot?.video_path}
                      onInput={(e: Event) =>
                        onTrimChange(sd.key, 'out', (e.target as HTMLInputElement).value)
                      }
                      onBlur={(e: Event) =>
                        onTrimChange(sd.key, 'out', (e.target as HTMLInputElement).value)
                      }
                    />
                  </div>
                  <div class="mn-stitcher-slot-row">
                    <label class="mn-dim" for={`stitcher-amb-${sd.key}`}>Ambient:</label>
                    <select
                      id={`stitcher-amb-${sd.key}`}
                      data-testid={`stitcher-amb-${sd.key}`}
                      data-stitch-ambient-select-hydrate={STITCH_AMBIENT_SELECT_HYDRATE_V1}
                      value={slot?.ambient_bed ?? ''}
                      disabled={busy || !slot?.video_path}
                      title="Saved per slot — baked into composer audio on save (not editable on waveform)"
                      onChange={(e: Event) => onAmbientBedChange(sd.key, (e.target as HTMLSelectElement).value)}
                    >
                      {/* F-AMBIENT-001 — empty/no-selection always available so users
                          can clear an existing ambient bed. Real preset_ids follow,
                          fetched from /api/phase_b/ambient_preset_list. */}
                      <option value="">— none —</option>
                      {ambientSelectOptions.map((p) => (
                        <option key={p.preset_id} value={p.preset_id}>{p.preset_id}</option>
                      ))}
                    </select>
                  </div>
                  <div class="mn-stitcher-slot-row">
                    <button
                      type="button"
                      class="mn-btn mn-btn-small"
                      data-testid={`stitcher-preview-${sd.key}`}
                      onClick={() => onPreviewSlot(sd.key)}
                      disabled={busy || !slot?.video_path}
                    >
                      {busySlot?.slot === sd.key && busySlot.action === 'preview' ? '…' : 'Review'}
                    </button>
                    <button
                      type="button"
                      class="mn-btn mn-btn-small"
                      data-testid={`stitcher-loudnorm-${sd.key}`}
                      onClick={() => onLoudnormSlot(sd.key)}
                      disabled={busy || !slot?.video_path || slot?.loudnorm_already_applied}
                    >
                      Loudnorm
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Per-boundary transitions (G7-G8). Apply on Bake / slot Preview only. */}
          {!standaloneMode ? (
            <div
              class="mn-stitcher-transitions-row"
              data-testid="stitcher-transitions-row"
              data-stitch-canonical-transitions="STITCH_CANONICAL_TRANSITIONS_V1"
              data-stitch-canonical-transition-sfx="STITCH_CANONICAL_TRANSITION_SFX_V1"
            >
              {[0, 1, 2].map((afterSlot) => (
                <StitcherTransitionSelector
                  key={`trans-${afterSlot}`}
                  afterSlot={afterSlot}
                  transition={findTransition(afterSlot)}
                  onChange={onTransitionChange}
                />
              ))}
            </div>
          ) : null}

          {/* Module-level SFX cue strip (G6). Drop a lib-sfx payload below the
              slot strip to write into state.module_sfx_cues via
              /api/timeline/cues. Distinct from per-slot cues which travel
              inside stitch_save_job.slots[i].sfx_cues. */}
          {/* CI fix #4: consolidated to single div — drop event was firing
              on the outer wrapper but handlers were on the inner element,
              so G6 test's drop never registered. Single element with
              testid + data-drop-target-kind. */}
          <div
            ref={moduleTimelineRef}
            class="mn-stitcher-module-timeline mn-drop-target"
            data-testid="stitcher-module-timeline"
            data-drop-target-kind="sfx-strip"
          >
            <span class="mn-dim">Module SFX cues — drag SFX from the Library here</span>
          </div>
        </>
      )}

      {popover && popoverCue ? (
        <SfxCuePopover
          cue={popoverCue}
          anchor={popover.anchor}
          onPatch={onSfxPatch}
          onDelete={onSfxDelete}
          onClose={() => setPopover(null)}
        />
      ) : null}

      <footer class="mn-pane-footer">
        <div class="mn-stitcher-bake-preview-shell" data-testid="stitcher-bake-preview-shell">
          {moduleFinalVideoSrc ? (
            <video
              class={`mn-stitcher-bake-preview-video ${PLAYBACK_VIDEO_ANTI_BANDING_CLASS}`}
              data-testid="stitcher-bake-preview-video"
              controls
              preload="none"
              src={moduleFinalVideoSrc}
            />
          ) : (
            <div class="mn-stitcher-bake-preview-empty mn-dim" data-testid="stitcher-bake-preview-empty">
              Final module preview will appear here after Bake.
            </div>
          )}
        </div>
        <div class="mn-stitcher-bake-row">
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid="stitcher-bake-btn"
            onClick={onBake}
            disabled={!job?.name || busySlot !== null || Boolean(activeBakeJobId)}
          >
            🔨 Bake final MP4
          </button>
          {job?.bake_path ? (
            <span class="mn-dim" data-testid="stitcher-last-bake-label">
              Last bake: {job.bake_path.split('/').pop()}
            </span>
          ) : null}
        </div>
        {statusMsg ? (
          <div class="mn-phase-status-line" data-testid="stitcher-status">{statusMsg}</div>
        ) : null}
      </footer>
    </section>
  );
}
