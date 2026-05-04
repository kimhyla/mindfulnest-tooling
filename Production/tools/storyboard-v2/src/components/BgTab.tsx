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
import { makeDropTarget } from '../utils/dragdrop';
import { Spinner } from './ui/Spinner';
import { Select } from './ui/Select';
import { pushToast } from './ui/Toast';

// ----------------------------------------------------------------
// Types — derived from server handler shapes (production_server.py:8627+)
// ----------------------------------------------------------------

interface GptOption {
  key: string;
  local_path?: string;
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

// ----------------------------------------------------------------
// Constants
// ----------------------------------------------------------------

// Per LD-440 GPT_IMAGE_2_PRIMARY_MODEL_V1 — gpt-image-2 published unit cost.
const PER_IMAGE_COST_USD = 0.04;
const POLL_INTERVAL_MS = 10000; // 10s per Cursor v8 Q6

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
  const [loading, setLoading] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [pollResults, setPollResults] = useState<Record<string, GptOption[]>>({});
  const [acceptStatus, setAcceptStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [extractStatus, setExtractStatus] = useState<'idle' | 'sending'>('idle');
  // Running cost across this session (only counts batches submitted from this UI).
  const [runningCostUsd, setRunningCostUsd] = useState<number>(0);
  const [lastBatchCostUsd, setLastBatchCostUsd] = useState<number>(0);

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

      const stateRes = await apiGet<BgSessionState>('bg_session_state');
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
      setLoading(false);
    };

    const depKey = [
      arcNumber,
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

  const refreshState = async () => {
    const stateRes = await apiGet<BgSessionState>('bg_session_state');
    if (stateRes.ok && stateRes.data) {
      setBeats(stateRes.data.beats ?? []);
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

  const onDeleteBeat = async (beatId: string) => {
    const ok = window.confirm(`Delete beat ${beatId}?`);
    if (!ok) return;
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

  const onGenerateBatch = async (beatId: string) => {
    if (activeJobId) {
      pushToast({ kind: 'info', message: 'A batch is still running.', source: 'bg-busy' });
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

  const onAcceptAll = async () => {
    if (beats.length === 0) {
      pushToast({ kind: 'info', message: 'No beats to accept.', source: 'bg-accept-all-empty' });
      return;
    }
    setAcceptStatus('sending');
    // Cursor v8 Q9 — partial-failure idempotent retry: the server is the source
    // of truth for pipeline_stage; the client just submits the current
    // selections. Re-running Accept All is safe (server merges).
    const acceptedBeats = beats
      .filter((b) => b.accepted_image_key)
      .map((b) => ({ beat_id: b.beat_id }));
    const [event_id] = (activeSegment || '|').split('|');
    const result = await pathappPatch(activeScope.value, 'bg_accept_beats', {
      beats: acceptedBeats,
      segment: Number(event_id) || 0,
    });
    if (result.ok) {
      setAcceptStatus('ok');
      pushToast({
        kind: 'success',
        message: `Accepted ${acceptedBeats.length} beats to Storyboard`,
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
          placeholder={segments.length === 0 ? 'Loading…' : 'Select segment'}
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
              busy={activeJobId !== null}
              onDelete={() => onDeleteBeat(b.beat_id)}
              onUpdateText={(t) => onUpdateBeatText(b.beat_id, t)}
              onGenerate={() => onGenerateBatch(b.beat_id)}
              onAccept={(optionKey) => onAcceptOption(b.beat_id, optionKey)}
            />
          ))}
        </ol>
      )}

      <footer class="mn-pane-footer">
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid="bg-accept-all-btn"
          onClick={onAcceptAll}
          disabled={beats.length === 0 || acceptStatus === 'sending'}
        >
          {acceptStatus === 'sending' ? (
            <><Spinner size="sm" inline /> Sending…</>
          ) : 'Accept All to Storyboard'}
        </button>
        <span
          class={`mn-bg-accept-status mn-bg-accept-${acceptStatus}`}
          data-testid="bg-accept-status"
          data-accept-status={acceptStatus}
        >
          {acceptStatus === 'ok' ? `✓ Accepted ${beats.filter((b) => b.accepted_image_key).length} beats` : ''}
        </span>
      </footer>
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
  onDelete: () => void;
  onUpdateText: (next: string) => void;
  onGenerate: () => void;
  onAccept: (optionKey: string) => void;
}

function BeatGenCard({
  index, beat, pollResultForBeat, busy,
  onDelete, onUpdateText, onGenerate, onAccept,
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
    const src = liveOptions ?? persistedOptions;
    const padded: (GptOption | null)[] = [...src];
    while (padded.length < 3) padded.push(null);
    return padded.slice(0, 3); // hard cap at 3 — never 9 (LD BEAT_GEN_3_OPTIONS_NOT_GRID_V1)
  })();

  return (
    <li class="mn-bg-beat-card" data-testid={`bg-beat-card-${index}`} data-beat-id={beat.beat_id}>
      <div class="mn-bg-beat-meta">
        <span class="mn-bg-beat-index">#{index + 1}</span>
        <span class="mn-bg-beat-anchor">{beat.beat_id}</span>
        {beat.speaker ? <span class="mn-beat-speaker">{beat.speaker}</span> : null}
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

      {chips.length > 0 ? (
        <div class="mn-bg-stage-chips" data-testid={`bg-beat-chips-${index}`}>
          <span>Stage:</span>
          {chips.map((c) => (
            <span key={c} class="mn-bg-stage-chip">
              <span>{c}</span>
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
        />
        <BgRefSlot
          label="BG ref"
          refImg={beat.bg_ref_image ?? null}
          testId={`bg-bg-ref-${index}`}
          beatId={beat.beat_id}
          refField="bg_ref_image"
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
          ) : 'Generate 3 options'}
        </button>
      </div>

      {/* 3-options row — 1×3 layout (NOT 3×3 matrix) */}
      <div class="mn-bg-options-row" data-testid={`bg-options-row-${index}`}>
        {optionsToShow.map((opt, i) => (
          <BgOptionTile
            key={opt?.key ?? `slot-${i}`}
            optionIndex={i}
            beatIndex={index}
            beatId={beat.beat_id}
            option={opt}
            selected={!!opt && opt.key === beat.accepted_image_key}
            onClick={() => opt?.key && onAccept(opt.key)}
          />
        ))}
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
}

function BgRefSlot({ label, refImg, testId, beatId, refField }: BgRefSlotPropsExt) {
  const hasImage = !!refImg && (refImg.thumb_b64 || refImg.key);
  // R2 fix: drop target for library-image drag → POST bg_update_beat with the
  // ref field (reference_image or bg_ref_image) per server _BG_BEAT_WRITABLE
  // (production_server.py:8744).
  const dropHandlers = makeDropTarget(
    async (payload) => {
      if (payload.kind !== 'lib-image') return;
      const result = await pathappPatch(activeScope.value, 'bg_update_beat', {
        beat_id: beatId,
        [refField]: {
          key: payload.lib_key,
          abs_path: payload.abs_path ?? '',
        },
      });
      if (!result.ok) {
        pushToast({
          kind: 'error',
          message: `${label} drop failed: ${result.error ?? `HTTP ${result.status}`}`,
          source: 'bg-ref-drop-error',
        });
      } else {
        pushToast({
          kind: 'success',
          message: `${label} set: ${payload.lib_key}`,
          source: 'bg-ref-drop',
        });
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
      {refImg?.thumb_b64 ? (
        <img src={refImg.thumb_b64} alt={label} />
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
}

function BgOptionTile({ beatIndex, optionIndex, option, selected, onClick, beatId }: BgOptionTilePropsExt) {
  // R2.1 fix: drop target for library-image drag → POST bg_accept_lib_image
  // with server-accurate body shape (spec §4.3): {beat_id, key, filename,
  // abs_path, slot_index}. slot_index = optionIndex (0/1/2).
  const dropHandlers = makeDropTarget(
    async (payload) => {
      if (payload.kind !== 'lib-image') return;
      const result = await pathappPatch(activeScope.value, 'bg_accept_lib_image', {
        beat_id: beatId,
        key: payload.lib_key,
        filename: payload.filename ?? '',
        abs_path: payload.abs_path ?? '',
        slot_index: optionIndex,
      });
      if (!result.ok) {
        pushToast({
          kind: 'error',
          message: `Drop failed: ${result.error ?? `HTTP ${result.status}`}`,
          source: 'bg-option-drop-error',
        });
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
  const tooltip = keyMissing ? 'Option missing key — regenerate beat' : undefined;
  return (
    <div
      class={`mn-bg-option mn-drop-target${selected ? ' is-selected' : ''}${keyMissing ? ' is-disabled' : ''}`}
      data-testid={`bg-option-${beatIndex}-${optionIndex}`}
      data-option-key={option.key ?? ''}
      onClick={keyMissing ? undefined : onClick}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
      title={tooltip}
    >
      {option.thumb_b64 ? (
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
          aria-label={tooltip ?? `option ${optionIndex + 1}`}
          data-testid={`bg-option-radio-${beatIndex}-${optionIndex}`}
        />
        {' '}option {optionIndex + 1}
      </label>
    </div>
  );
}
