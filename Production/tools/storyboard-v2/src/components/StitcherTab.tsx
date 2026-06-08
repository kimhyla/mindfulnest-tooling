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

import { useEffect, useRef, useState } from 'preact/hooks';
import { activeScope, activeProjectType, scopeKey } from '../state/scope';
import { stitcherRefreshTick } from '../app';
import { apiGet, pathappPatch } from '../api/client';
import { StitcherSlotWaveform } from './StitcherSlotWaveform';
import { StitcherTransitionSelector, type Transition } from './StitcherTransitionSelector';
import { SfxCuePopover, type SfxCue } from './phase/SfxCuePopover';
import { acceptDragForTarget, makeDropTarget, type DragPayload } from '../utils/dragdrop';

type SlotKey = 'intro' | 'phase_a' | 'phase_b' | 'resolution';

const SLOT_DEFS: Array<{ key: SlotKey; label: string }> = [
  { key: 'intro', label: 'Intro' },
  { key: 'phase_a', label: 'Phase A' },
  { key: 'phase_b', label: 'Phase B' },
  { key: 'resolution', label: 'Resolution' },
];

interface StitchSlot {
  video_path?: string;
  video_dur_ms?: number;
  beat_boundaries?: BeatBoundary[];
  ambient_bed?: string;
  loudnorm_already_applied?: boolean;
  sfx_cues?: SfxCue[];
  trim_in_ms?: number;
  trim_out_ms?: number | null;
}

interface StitchJob {
  name?: string;
  slots?: Record<string, StitchSlot>;
  transitions?: Transition[];
  bake_path?: string;
  bake_mtime?: number;
}

interface StitchLibraryResponse {
  ok?: boolean;
  jobs?: StitchJob[];
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
  volume: 0.45,
  fadein_ms: 300,
  fadeout_ms: 1200,
};

// Slot duration fallback when the server-provided video_dur_ms is missing.
// Stitcher slots are typically short; 30s is a safe default that keeps drop
// math sane until the real duration loads. Tests inject explicit video_dur_ms.
const DEFAULT_SLOT_DUR_MS = 30000;
const STITCHER_TRACK_SLOT_LS_PREFIX = 'storyboard_v2_stitcher_track_slot';

function isSlotKey(value: string): value is SlotKey {
  return value === 'intro' || value === 'phase_a' || value === 'phase_b' || value === 'resolution';
}

function readPersistedTrackSlot(eventId: string): SlotKey | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(`${STITCHER_TRACK_SLOT_LS_PREFIX}:${eventId}`);
    return raw && isSlotKey(raw) ? raw : null;
  } catch {
    return null;
  }
}

function writePersistedTrackSlot(eventId: string, slot: SlotKey | null): void {
  if (typeof window === 'undefined') return;
  try {
    const key = `${STITCHER_TRACK_SLOT_LS_PREFIX}:${eventId}`;
    if (slot) {
      window.localStorage.setItem(key, slot);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // localStorage may be unavailable in some test contexts.
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
  const dropHandlers = makeDropTarget(
    (payload) => {
      if (payload.kind !== 'lib-image') return;
      void onImageDrop(payload);
    },
    acceptDragForTarget('image-slot'),
    'image-slot',
  );
  return (
    <div
      class="mn-stitcher-slot-video mn-drop-target"
      data-testid="stitcher-drop-target-image-slot"
      data-slot-key={slotKey}
      data-drop-target-kind="image-slot"
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
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
  const [refreshTick, setRefreshTick] = useState(0);
  // ST-14: derive standaloneMode from canonical activeProjectType signal —
  // reactive on signal change. Milestone scope is always 1-slot standalone
  // by definition; event scope is 4-slot. (Was: inferred from slot count.)
  const standaloneMode = activeProjectType.value === 'milestone';
  const [popover, setPopover] = useState<PopoverState | null>(null);
  // F-AMBIENT-001 — fetched ambient catalog (replaces hardcoded constant).
  // Pattern lifted from PhaseProducer.tsx:154-176 so Phase A, Phase B, and
  // Stitcher all consume the same catalog via the same single endpoint.
  const [ambientPresets, setAmbientPresets] = useState<AmbientPreset[]>([]);

  // Inline preview player state
  const [activePreviewSlot, setActivePreviewSlot] = useState<SlotKey | null>(null);
  const [trackFocusedSlot, setTrackFocusedSlot] = useState<SlotKey | null>(null);
  const [beatBoundaries, setBeatBoundaries] = useState<BeatBoundary[]>([]);
  const [beatBoundariesLoading, setBeatBoundariesLoading] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Re-fetch whenever SendOutButton completes a scene_assemble (cross-tab signal).
  // This ensures the intro slot auto-populated by scene_assemble becomes visible
  // without requiring Kim to manually refresh the Stitcher tab.
  useEffect(() => {
    setRefreshTick((n) => n + 1);
  }, [stitcherRefreshTick.value]);

  useEffect(() => {
    const persisted = readPersistedTrackSlot(activeScope.value.event_id);
    setTrackFocusedSlot(persisted);
  }, [activeScope.value.event_id]);

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
    (async () => {
      try {
        // S5.5b Bug 2 fix: was /library (returns sound library: ambient/sfx/transitions);
        // correct endpoint is /jobs which returns {jobs: [{name, created_at, updated_at, slot_count}]}.
        // After picking active summary, fetch full job via /api/stitch_editor/job/<name> for slots.
        const res = await apiGet<StitchLibraryResponse>('stitch_editor_jobs');
        if (cancelled) return;
        if (!res.ok) {
          setError(res.error ?? `HTTP ${res.status}`);
          setLoading(false);
          return;
        }
        const data = res.data;
        const eventName = activeScope.value.event_id;
        const jobs = data?.jobs ?? [];
        const canonicalName = `${eventName}_stitch`;

        const mergeSlotsFromJob = (
          merged: Record<string, StitchSlot>,
          jobSlots: Record<string, StitchSlot> | StitchSlot[] | undefined,
        ) => {
          if (!jobSlots || typeof jobSlots !== 'object' || Array.isArray(jobSlots)) return;
          for (const [key, slot] of Object.entries(jobSlots)) {
            if (!slot?.video_path) continue;
            merged[key] = { ...(merged[key] ?? {}), ...slot };
          }
        };

        // Prefer canonical per-event job (server upserts preserve all slots).
        const canonicalDetailRes = await apiGet<{ job?: StitchJob; name?: string }>(
          'stitch_editor_job',
          { job_name: canonicalName },
        );
        if (!cancelled && canonicalDetailRes.ok && canonicalDetailRes.data?.job) {
          const canonicalJob = canonicalDetailRes.data.job;
          const canonicalSlots: Record<string, StitchSlot> = {};
          mergeSlotsFromJob(canonicalSlots, canonicalJob.slots as Record<string, StitchSlot>);
          if (Object.keys(canonicalSlots).length > 0) {
            setJob({
              name: canonicalName,
              slots: canonicalSlots,
              transitions: canonicalJob.transitions ?? [],
            });
            setError(null);
            setLoading(false);
            return;
          }
        }

        // Legacy fallback: merge auto_* + phase_* jobs (skip empty slots).
        const relevantSummaries = jobs.filter(
          (j) => j.name?.startsWith('auto_') || j.name?.includes(eventName),
        );
        const mergedSlots: Record<string, StitchSlot> = {};
        let mergedTransitions: Transition[] = [];
        for (const summary of relevantSummaries) {
          if (!summary.name || summary.name === canonicalName) continue;
          const mergeDetailRes = await apiGet<{ job?: StitchJob; name?: string }>(
            'stitch_editor_job',
            { job_name: summary.name },
          );
          if (cancelled || !mergeDetailRes.ok || !mergeDetailRes.data?.job) continue;
          const j = mergeDetailRes.data.job;
          mergeSlotsFromJob(mergedSlots, j.slots as Record<string, StitchSlot>);
          if (j.transitions?.length && !mergedTransitions.length) {
            mergedTransitions = j.transitions;
          }
        }
        if (Object.keys(mergedSlots).length > 0) {
          setJob({
            name: canonicalName,
            slots: mergedSlots,
            transitions: mergedTransitions,
          });
          setError(null);
          setLoading(false);
          return;
        }
        // Fallback: legacy single-job pick.
        const eventJobSummary =
          jobs.find((j) => j.name?.startsWith('auto_')) ??
          jobs.find((j) => j.name?.includes(eventName)) ??
          (jobs.length > 1
            ? jobs.reduce((a, b) =>
                ((a as any).updated_at ?? '') >= ((b as any).updated_at ?? '') ? a : b
              )
            : null) ??
          jobs[0] ?? null;
        if (!eventJobSummary?.name) {
          setJob(null);
          setError(null);
          return;
        }
        // 2nd fetch: full job detail (with slots).
        const detailRes = await apiGet<{ job?: StitchJob; name?: string }>(
          'stitch_editor_job',
          { job_name: eventJobSummary.name },
        );
        if (cancelled) return;
        if (!detailRes.ok) {
          setError(detailRes.error ?? `HTTP ${detailRes.status} loading job detail`);
          return;
        }
        const detailData = detailRes.data;
        if (!detailData) {
          setError('job detail response had no body');
          return;
        }
        const fullJob: StitchJob | null = detailData.job
          ? { ...detailData.job, name: detailData.name ?? eventJobSummary.name }
          : null;
        setJob(fullJob);
        // standaloneMode is now a derived value (see component top); no need
        // to set it here. ST-14 fix removed the slot-count inference path.
        setError(null);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [refreshTick, activeScope.value.event_id]);

  const slotsToShow = standaloneMode && job?.slots
    ? SLOT_DEFS.filter((s) => job.slots && s.key in job.slots)
    : SLOT_DEFS;
  const multiPhaseSlots = standaloneMode ? slotsToShow : SLOT_DEFS;
  const multiPhaseTotalMs = Math.max(
    1,
    multiPhaseSlots.reduce((acc, sd) => {
      const dur = job?.slots?.[sd.key]?.video_dur_ms ?? DEFAULT_SLOT_DUR_MS;
      return acc + dur;
    }, 0),
  );

  useEffect(() => {
    if (!job?.slots) return;
    const activeSlot = trackFocusedSlot ? job.slots[trackFocusedSlot] : null;
    if (activeSlot?.video_path) return;
    const fallback = multiPhaseSlots.find((sd) => job.slots?.[sd.key]?.video_path)?.key ?? null;
    if (fallback !== trackFocusedSlot) {
      setTrackFocusedSlot(fallback);
      writePersistedTrackSlot(activeScope.value.event_id, fallback);
    }
  }, [job, trackFocusedSlot, multiPhaseSlots, activeScope.value.event_id]);

  /**
   * Persist the entire job slots dict via stitch_save_job. Used when sfx_cues
   * change (add/edit/delete) on any slot — the slot.sfx_cues array is the
   * source of truth for per-slot cues per audit doc §3.
   */
  const saveJobSlots = async (
    nextSlots: Record<string, StitchSlot>,
    transitions?: Transition[],
  ): Promise<boolean> => {
    if (!job?.name) return false;
    const res = await pathappPatch(activeScope.value, 'stitch_save_job', {
      name: job.name,
      slots: nextSlots,
      transitions: transitions ?? job.transitions ?? [],
      merge_slots: true,
    });
    if (res.ok) {
      // Update local state mirror immediately so the UI reflects the write.
      setJob({
        ...job,
        slots: nextSlots,
        ...(transitions ? { transitions } : {}),
      });
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
    return t ?? null;
  };

  const fetchBeatBoundaries = async (slot?: SlotKey) => {
    setBeatBoundariesLoading(true);
    setBeatBoundaries([]);
    const slotData = slot ? job?.slots?.[slot] : undefined;
    if (slotData?.beat_boundaries?.length) {
      setBeatBoundaries(slotData.beat_boundaries);
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
    const video = videoRef.current;
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

  const onPreviewSlot = async (slot: SlotKey) => {
    const slotData = job?.slots?.[slot];
    if (!slotData?.video_path) {
      setStatusMsg(`Slot ${slot} has no video assigned.`);
      return;
    }
    setBusySlot({ slot, action: 'preview' });
    setStatusMsg(null);
    // _stitch_build_pipeline expects a `slots` list of slot objects each with
    // video_path. The client was only sending the slot key — server returned
    // "No slots provided". Also open the returned preview_url in a new tab.
    const res = await pathappPatch(activeScope.value, 'stitch_preview', {
      name: job?.name,
      slot,
      slots: [slotData],   // single-slot preview — server builds just this clip
    });
    setBusySlot(null);
    if (res.ok) {
      const data = res.data as { preview_url?: string } | undefined;
      if (data?.preview_url) {
        // Store URL for inline "▶ Watch" link — window.open is blocked by Chrome
        // after async/await (breaks trusted-event chain). Rendered link is user-clicked.
        setPreviewUrls((prev) => ({ ...prev, [slot]: data.preview_url }));
        setActivePreviewSlot(slot);
        setTrackFocusedSlot(slot);
        writePersistedTrackSlot(activeScope.value.event_id, slot);
        void fetchBeatBoundaries(slot);
      }
      setStatusMsg(`✓ Preview ${slot} ready`);
    } else {
      const data = res.data as { error?: string } | undefined;
      setStatusMsg(`✗ Preview HTTP ${res.status}: ${data?.error ?? res.error ?? ''}`);
    }
  };

  const onMultiPhaseSegmentClick = (slot: SlotKey) => {
    const slotData = job?.slots?.[slot];
    if (!slotData?.video_path) return;
    setTrackFocusedSlot(slot);
    writePersistedTrackSlot(activeScope.value.event_id, slot);
    if (previewUrls[slot]) {
      setActivePreviewSlot(slot);
      void fetchBeatBoundaries(slot);
      return;
    }
    void onPreviewSlot(slot);
  };

  const onBake = async () => {
    if (!job?.name) {
      setStatusMsg('No active stitch job. Send a producer output to Stitcher first.');
      return;
    }
    setBusySlot({ slot: 'intro', action: 'bake' });
    setStatusMsg('Baking final MP4…');
    // V59 architectural-fix (Wave 1, F-S2-001): mutation via pathappPatch.
    const res = await pathappPatch<{ bake_path?: string }>(activeScope.value, 'stitch_bake', {
      name: job.name,
    });
    setBusySlot(null);
    if (res.ok) {
      setStatusMsg(`✓ Baked: ${res.data?.bake_path ?? job.name}`);
      setRefreshTick((n) => n + 1);
    } else {
      setStatusMsg(`✗ Bake HTTP ${res.status}`);
    }
  };

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
      setRefreshTick((n) => n + 1);
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
    if (!job?.name) return;
    setBusySlot({ slot, action: 'ambient' });
    // V59 architectural-fix (Wave 1, F-S2-001): mutation via pathappPatch.
    const res = await pathappPatch(activeScope.value, 'stitch_save_job', {
      name: job.name,
      slot,
      ambient_bed: value,
    });
    setBusySlot(null);
    if (res.ok) {
      setStatusMsg(`✓ ${slot} ambient bed → ${value || 'none'}`);
      setRefreshTick((n) => n + 1);
    } else {
      setStatusMsg(`✗ Ambient bed save HTTP ${res.status}`);
    }
  };

  // --------------------------------------------------------------------------
  // Per-slot SFX cue handlers (G3 / G4 / G5)
  // --------------------------------------------------------------------------

  const onSfxDropOnSlot = (slotKey: SlotKey) => (
    lib_key: string,
    source_path: string,
    offset_ms: number,
  ) => {
    if (!job?.slots) return;
    const slot = job.slots[slotKey];
    if (!slot) return;
    const newCue: SfxCue = {
      id: generateCueId('cue'),
      source_path,
      name: source_path.split('/').pop() ?? lib_key,
      offset_ms,
      ...SFX_DEFAULTS,
    };
    const nextCues = [...(slot.sfx_cues ?? []), newCue];
    const nextSlots: Record<string, StitchSlot> = {
      ...job.slots,
      [slotKey]: { ...slot, sfx_cues: nextCues },
    };
    void saveJobSlots(nextSlots);
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
    const nextCues = (slot.sfx_cues ?? []).filter((c) => c.id !== popover.cueId);
    const nextSlots: Record<string, StitchSlot> = {
      ...job.slots,
      [slotKey]: { ...slot, sfx_cues: nextCues },
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
      total += s?.video_dur_ms ?? DEFAULT_SLOT_DUR_MS;
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

  // Active popover cue — read from job state when scope='slot'.
  const popoverCue: SfxCue | null = (() => {
    if (!popover) return null;
    if (popover.scope === 'slot' && popover.slotKey && job?.slots) {
      const slot = job.slots[popover.slotKey];
      return slot?.sfx_cues?.find((c) => c.id === popover.cueId) ?? null;
    }
    return null;
  })();

  return (
    <section class="mn-tab-pane mn-stitcher-pane" data-testid="pane-stitcher">
      <header class="mn-pane-header">
        <h2>Stitcher</h2>
        <span class="mn-scope-chip" data-testid="stitcher-scope-chip">
          scope: {scopeKey(activeScope.value)}
          {standaloneMode ? ' · standalone' : ''}
        </span>
      </header>

      {loading ? (
        <p class="mn-loading" data-testid="stitcher-loading">Loading stitch jobs…</p>
      ) : error ? (
        <div class="mn-empty" data-testid="stitcher-error">
          <p class="mn-warn">Could not reach /api/stitch_editor/jobs.</p>
          <p class="mn-dim">{error}</p>
        </div>
      ) : !job ? (
        <div class="mn-empty" data-testid="stitcher-no-job">
          <p>No active stitch job for {activeScope.value.event_id}.</p>
          <p class="mn-dim">
            Use Phase A / Phase B "Export to Stitcher" buttons to send producer
            outputs here, then Bake the final MP4.
          </p>
        </div>
      ) : (
        <>
          <div class="mn-stitcher-strip" data-testid="stitcher-strip">
            {slotsToShow.map((sd) => {
              const slot = job.slots?.[sd.key];
              const busy = busySlot?.slot === sd.key;
              const slotDurMs = slot?.video_dur_ms ?? DEFAULT_SLOT_DUR_MS;
              const cues = slot?.sfx_cues ?? [];
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
                      <span class="mn-stitcher-loudnorm-tag">loudnorm ✓</span>
                    ) : null}
                  </div>
                  <SlotImageDropTarget
                    slotKey={sd.key}
                    hasVideo={Boolean(slot?.video_path)}
                    videoLabel={slot?.video_path?.split('/').pop()}
                    videoTitle={slot?.video_path}
                    onImageDrop={onImageDropOnSlot(sd.key)}
                  />
                  <StitcherSlotWaveform
                    slotKey={sd.key}
                    videoDurMs={slotDurMs}
                    cues={cues}
                    onSfxDrop={onSfxDropOnSlot(sd.key)}
                    onCueClick={onSfxClickOnSlot(sd.key)}
                  />
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
                      value={slot?.ambient_bed ?? ''}
                      disabled={busy || !slot?.video_path}
                      onChange={(e: Event) => onAmbientBedChange(sd.key, (e.target as HTMLSelectElement).value)}
                    >
                      {/* F-AMBIENT-001 — empty/no-selection always available so users
                          can clear an existing ambient bed. Real preset_ids follow,
                          fetched from /api/phase_b/ambient_preset_list. */}
                      <option value="">— none —</option>
                      {ambientPresets.map((p) => (
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
                      {busySlot?.slot === sd.key && busySlot.action === 'preview' ? '…' : 'Preview'}
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

          <div class="mn-stitcher-multiphase-track" data-testid="stitcher-multiphase-track">
            <div class="mn-stitcher-multiphase-track-header">
              <strong>Multi-phase view track</strong>
              <span class="mn-dim">selection persists per event</span>
            </div>
            <div class="mn-stitcher-multiphase-track-rail">
              {multiPhaseSlots.map((sd) => {
                const slot = job.slots?.[sd.key];
                const durMs = slot?.video_dur_ms ?? DEFAULT_SLOT_DUR_MS;
                const widthPct = (durMs / multiPhaseTotalMs) * 100;
                const selected = trackFocusedSlot === sd.key;
                return (
                  <button
                    type="button"
                    key={`track-${sd.key}`}
                    class={`mn-stitcher-multiphase-segment${selected ? ' is-active' : ''}${slot?.video_path ? '' : ' is-empty'}`}
                    style={`width:${widthPct.toFixed(3)}%`}
                    data-testid={`stitcher-multiphase-segment-${sd.key}`}
                    onClick={() => onMultiPhaseSegmentClick(sd.key)}
                    disabled={!slot?.video_path}
                    title={slot?.video_path ?? `${sd.label} slot is empty`}
                  >
                    <span class="mn-stitcher-multiphase-segment-label">{sd.label}</span>
                    <span class="mn-stitcher-multiphase-segment-meta">{(durMs / 1000).toFixed(1)}s</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Inline preview player + beat timeline.
              Shows below the slot strip when any slot's Preview is active.
              Full-width to give proper NLE-style viewing context. */}
          {activePreviewSlot && previewUrls[activePreviewSlot] ? (
            <div class="mn-stitcher-preview-area" data-testid="stitcher-preview-area">
              <div class="mn-stitcher-preview-header">
                <span class="mn-dim">Preview: <strong>{activePreviewSlot}</strong></span>
                <button
                  type="button"
                  class="mn-btn mn-btn-small"
                  onClick={() => { setActivePreviewSlot(null); setBeatBoundaries([]); }}
                  data-testid="stitcher-preview-close"
                >✕ Close</button>
              </div>
              <video
                ref={videoRef}
                controls
                src={previewUrls[activePreviewSlot]}
                class="mn-stitcher-video-player"
                data-testid="stitcher-video-player"
              />
              <div
                class={`mn-beat-timeline${beatBoundariesLoading ? ' mn-beat-timeline-loading' : ''}`}
                data-testid="mn-beat-timeline"
                onClick={onTimelineClick}
                title="Click to seek"
              >
                {beatBoundaries.length > 0 ? (() => {
                  const video = videoRef.current;
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
          ) : null}

          {/* Per-boundary transitions (G7-G8). 3 selectors for 4 slots:
              after_slot=0 (intro→phase_a), 1 (phase_a→phase_b),
              2 (phase_b→resolution). Per spec §3.3 + Q1 LOCKED 2026-05-04
              + STITCHER_TRANSITIONS_V1 (HARD). Hidden in standalone mode. */}
          {!standaloneMode ? (
            <div class="mn-stitcher-transitions-row" data-testid="stitcher-transitions-row">
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
            class="mn-stitcher-module-timeline mn-drop-target"
            data-testid="stitcher-module-timeline"
            data-drop-target-kind="sfx-strip"
            onDragOver={moduleDropHandlers.onDragOver}
            onDragLeave={moduleDropHandlers.onDragLeave}
            onDrop={moduleDropHandlers.onDrop}
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
        <div class="mn-stitcher-bake-row">
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid="stitcher-bake-btn"
            onClick={onBake}
            disabled={!job?.name || busySlot !== null}
          >
            🔨 Bake final MP4
          </button>
          {job?.bake_path ? (
            <span class="mn-dim">Last bake: {job.bake_path.split('/').pop()}</span>
          ) : null}
        </div>
        {statusMsg ? (
          <div class="mn-phase-status-line" data-testid="stitcher-status">{statusMsg}</div>
        ) : null}
      </footer>
    </section>
  );
}
