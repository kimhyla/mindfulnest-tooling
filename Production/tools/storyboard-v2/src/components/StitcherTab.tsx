// StitcherTab — Session 5 v3.1 full UI per LD-471 STITCHER_FULL_UI_V1.
//
// 4-slot strip: intro → Phase A → Phase B → resolution. Each slot shows:
//   * Slot label + assigned video filename (if any)
//   * Per-slot ambient bed dropdown (NEW field ambient_bed_per_segment)
//   * Preview button → calls _handle_stitch_preview
//   * Bake button → calls _handle_stitch_bake
//   * Loudnorm toggle → calls /api/stitch_editor/loudnorm
//
// Standalone mode: when active job is single-slot, only one row renders.
//
// All actions go through pathappPatch so scope guards + snapshot fire.

import { useEffect, useState } from 'preact/hooks';
import { activeScope, scopeKey } from '../state/scope';
import { pathappPatch } from '../api/client';
import { SERVER_BASE } from '../api/endpoints';

type SlotKey = 'intro' | 'phase_a' | 'phase_b' | 'resolution';

const SLOT_DEFS: Array<{ key: SlotKey; label: string }> = [
  { key: 'intro', label: 'Intro' },
  { key: 'phase_a', label: 'Phase A' },
  { key: 'phase_b', label: 'Phase B' },
  { key: 'resolution', label: 'Resolution' },
];

interface StitchSlot {
  video_path?: string;
  ambient_bed?: string;
  loudnorm_already_applied?: boolean;
}

interface StitchJob {
  name?: string;
  slots?: Record<string, StitchSlot>;
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

export function StitcherTab() {
  const [job, setJob] = useState<StitchJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busySlot, setBusySlot] = useState<{ slot: SlotKey; action: string } | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [standaloneMode, setStandaloneMode] = useState(false);

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
        <div class="mn-stitcher-strip" data-testid="stitcher-strip">
          {slotsToShow.map((sd) => {
            const slot = job.slots?.[sd.key];
            const busy = busySlot?.slot === sd.key;
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
      )}

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
