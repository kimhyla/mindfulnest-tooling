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
import { Modal } from './ui/Modal';
import { Spinner } from './ui/Spinner';
import { Select } from './ui/Select';
import { pushToast } from './ui/Toast';

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
  // F-BG-001 fix: initial state is `true` because the data-load useEffect
  // fires synchronously on first mount (prevDepsRef === null branch) and
  // immediately sets loading=true. Without `true` here, the first paint
  // would falsely show the loaded-empty placeholder "(no segments yet)"
  // for one frame before the fetch starts.
  const [loading, setLoading] = useState(true);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [pollResults, setPollResults] = useState<Record<string, GptOption[]>>({});
  const [acceptStatus, setAcceptStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
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

  // BG-34/35 — Accept All warn modal (lists unset beats) + confirm modal
  // (Lock in N selections...). Replaces direct mutation; gates on user
  // acknowledgement of unset beats per Kim 2026-05-06 lock.
  const onAcceptAll = () => {
    if (beats.length === 0) {
      pushToast({ kind: 'info', message: 'No beats to accept.', source: 'bg-accept-all-empty' });
      return;
    }
    const ready = beats.filter((b) => b.accepted_image_key);
    const unset = beats.filter((b) => !b.accepted_image_key).map((b) => b.beat_id);
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
              busy={activeJobId !== null}
              onDelete={() => onDeleteBeat(b.beat_id)}
              onUpdateText={(t) => onUpdateBeatText(b.beat_id, t)}
              onGenerate={() => onGenerateBatch(b.beat_id)}
              onAccept={(optionKey) => onAcceptOption(b.beat_id, optionKey)}
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
              {modalState.readyCount === 1 ? '' : 's'} will be sent to Storyboard.
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
            This sends accepted beats to Storyboard.
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
  onDelete: () => void;
  onUpdateText: (next: string) => void;
  onGenerate: () => void;
  onAccept: (optionKey: string) => void;
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
  index, beat, pollResultForBeat, busy,
  onDelete, onUpdateText, onGenerate, onAccept,
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
          ) : 'Generate 3 options'}
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
            selected={!!opt && opt.key === beat.accepted_image_key}
            onClick={() => opt?.key && onAccept(opt.key)}
            onRefresh={onRefresh}
            onPatchOptionTile={onPatchOptionTile}
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
}

function BgOptionTile({
  beatIndex, optionIndex, option, selected, onClick, beatId, onRefresh, onPatchOptionTile,
}: BgOptionTilePropsExt) {
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
