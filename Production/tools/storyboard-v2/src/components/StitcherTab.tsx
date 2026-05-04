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

import { useEffect, useState } from 'preact/hooks';
import { activeScope, scopeKey } from '../state/scope';
import { pathappPatch } from '../api/client';
import { SERVER_BASE } from '../api/endpoints';
import { StitcherSlotWaveform } from './StitcherSlotWaveform';
import { SfxCuePopover, type SfxCue } from './phase/SfxCuePopover';
import { makeDropTarget, type DragPayload } from '../utils/dragdrop';

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
  ambient_bed?: string;
  loudnorm_already_applied?: boolean;
  sfx_cues?: SfxCue[];
  trim_in_ms?: number;
  trim_out_ms?: number | null;
}

interface StitchJob {
  name?: string;
  slots?: Record<string, StitchSlot>;
  transitions?: Array<Record<string, unknown>>;
  bake_path?: string;
  bake_mtime?: number;
}

interface StitchLibraryResponse {
  ok?: boolean;
  jobs?: StitchJob[];
}

const AMBIENT_BED_CHOICES = [
  { value: '', label: '— none —' },
  { value: 'gentle_forest', label: 'Gentle forest' },
  { value: 'soft_chimes', label: 'Soft chimes' },
  { value: 'warm_room_tone', label: 'Warm room tone' },
  { value: 'water_stream', label: 'Water stream' },
];

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

interface PopoverState {
  scope: 'slot' | 'module';
  slotKey?: SlotKey;
  cueId: string;
  anchor: { x: number; y: number };
}

function generateCueId(prefix: string): string {
  // 8-char random suffix — enough for in-session uniqueness; server is the
  // source of truth on persistence.
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

export function StitcherTab() {
  const [job, setJob] = useState<StitchJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busySlot, setBusySlot] = useState<{ slot: SlotKey; action: string } | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [standaloneMode, setStandaloneMode] = useState(false);
  const [popover, setPopover] = useState<PopoverState | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // S5.5b Bug 2 fix: was /library (returns sound library: ambient/sfx/transitions);
        // correct endpoint is /jobs which returns {jobs: [{name, created_at, updated_at, slot_count}]}.
        // After picking active summary, fetch full job via /api/stitch_editor/job/<name> for slots.
        const res = await fetch(`${SERVER_BASE}/api/stitch_editor/jobs`);
        if (cancelled) return;
        if (!res.ok) {
          setError(`HTTP ${res.status}`);
          setLoading(false);
          return;
        }
        const data = (await res.json()) as StitchLibraryResponse;
        const eventName = activeScope.value.event_id;
        // Pick the active job for this event (name pattern: phase_*_<event>).
        const jobs = data.jobs ?? [];
        const eventJobSummary = jobs.find((j) => j.name?.includes(eventName)) ?? jobs[0] ?? null;
        if (!eventJobSummary?.name) {
          setJob(null);
          setError(null);
          return;
        }
        // 2nd fetch: full job detail (with slots).
        const detailRes = await fetch(
          `${SERVER_BASE}/api/stitch_editor/job/${encodeURIComponent(eventJobSummary.name)}`,
        );
        if (cancelled) return;
        if (!detailRes.ok) {
          setError(`HTTP ${detailRes.status} loading job detail`);
          return;
        }
        const detailData = (await detailRes.json()) as { job?: StitchJob; name?: string };
        const fullJob: StitchJob | null = detailData.job
          ? { ...detailData.job, name: detailData.name ?? eventJobSummary.name }
          : null;
        setJob(fullJob);
        if (fullJob?.slots) {
          const slotKeys = Object.keys(fullJob.slots);
          setStandaloneMode(slotKeys.length === 1);
        }
        setError(null);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [refreshTick]);

  const slotsToShow = standaloneMode && job?.slots
    ? SLOT_DEFS.filter((s) => job.slots && s.key in job.slots)
    : SLOT_DEFS;

  /**
   * Persist the entire job slots dict via stitch_save_job. Used when sfx_cues
   * change (add/edit/delete) on any slot — the slot.sfx_cues array is the
   * source of truth for per-slot cues per audit doc §3.
   */
  const saveJobSlots = async (
    nextSlots: Record<string, StitchSlot>,
    transitions?: Array<Record<string, unknown>>,
  ): Promise<boolean> => {
    if (!job?.name) return false;
    const res = await pathappPatch(activeScope.value, 'stitch_save_job', {
      name: job.name,
      slots: nextSlots,
      transitions: transitions ?? job.transitions ?? [],
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

  const onPreviewSlot = async (slot: SlotKey) => {
    setBusySlot({ slot, action: 'preview' });
    setStatusMsg(null);
    // V59 architectural-fix (Wave 1, F-S2-001): mutation routes through
    // pathappPatch so M1 snapshot fires + scope keys auto-inject + 409/423
    // surface per LD-461 / LD-456 / LD-458/460. event_id is auto-injected.
    const res = await pathappPatch(activeScope.value, 'stitch_preview', {
      name: job?.name,
      slot,
    });
    setBusySlot(null);
    if (res.ok) {
      setStatusMsg(`✓ Preview ${slot} ready`);
    } else {
      const data = res.data as { error?: string } | undefined;
      setStatusMsg(`✗ Preview HTTP ${res.status}: ${data?.error ?? res.error ?? ''}`);
    }
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

  // Module strip drop target — accepts lib-sfx; offset_ms = drop_x / width × total_dur.
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
    (payload) => payload.kind === 'lib-sfx',
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
                  <div class="mn-stitcher-slot-video">
                    {slot?.video_path ? (
                      <code title={slot.video_path}>
                        {slot.video_path.split('/').pop()}
                      </code>
                    ) : (
                      <span class="mn-dim">— empty —</span>
                    )}
                  </div>
                  <StitcherSlotWaveform
                    slotKey={sd.key}
                    videoDurMs={slotDurMs}
                    cues={cues}
                    onSfxDrop={onSfxDropOnSlot(sd.key)}
                    onCueClick={onSfxClickOnSlot(sd.key)}
                  />
                  <div class="mn-stitcher-slot-row">
                    <label class="mn-dim" for={`stitcher-amb-${sd.key}`}>Ambient:</label>
                    <select
                      id={`stitcher-amb-${sd.key}`}
                      data-testid={`stitcher-amb-${sd.key}`}
                      value={slot?.ambient_bed ?? ''}
                      disabled={busy || !slot?.video_path}
                      onChange={(e: Event) => onAmbientBedChange(sd.key, (e.target as HTMLSelectElement).value)}
                    >
                      {AMBIENT_BED_CHOICES.map((c) => (
                        <option key={c.value} value={c.value}>{c.label}</option>
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
                      Preview
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

          {/* Module-level SFX cue strip (G6). Drop a lib-sfx payload below the
              slot strip to write into state.module_sfx_cues via
              /api/timeline/cues. Distinct from per-slot cues which travel
              inside stitch_save_job.slots[i].sfx_cues. */}
          <div
            class="mn-stitcher-module-timeline mn-drop-target"
            data-testid="stitcher-module-timeline"
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
