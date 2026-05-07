// StoryboardTab — main beat editing surface (Session 2 feature-complete v1).
// Hydrates from /api/v2/event/<event_id>/state. Renders state.beats (dict
// keyed by beat_id) as numbered cards. Per-beat dialogue is editable
// inline; saves go through pathappPatch which performs scope check + state
// snapshot + 409/423 handling.
//
// Behavioral parity preserved (PATCH_BEHAVIORAL_PARITY_AUDIT_v1 rows 1, 25):
//   * Per-row save state machine: idle -> saving (yellow) -> saved (green)
//                                       OR -> error (red)
//   * localStorage shadow on every keystroke (24h TTL key per beat)
//   * Recovery: on mount, surface any localStorage drafts that differ from server text
//
// Note: beforeunload guard + 503 fallback are S3 polish (parity-audit out-of-scope here).

import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import {
  activeScope,
  activeTargetVideo,
  activeProjectType,
  activeMilestoneId,
  scopeKey,
} from '../state/scope';
import { apiGet, pathappPatch } from '../api/client';
import { makeDropTarget } from '../utils/dragdrop';
import { Spinner } from './ui/Spinner';
import { pushToast } from './ui/Toast';
import { BeatAudioPreview } from './BeatAudioPreview';

interface BeatState {
  speaker?: string;
  text?: string;
  image_path?: string;
  _version?: number;
  text_last_updated_at?: string;
  audio_file?: string;
  text_modified_after_tts?: boolean;
  // S5 v3.1 — magic trail composite paths (per LD-468/469).
  magic_still_path?: string;
  magic_video_path?: string;
  // S5 — preferred video source for magic_video (lipsync, then animation).
  lipsync?: { file?: string; status?: string };
  phase_1?: { selected_option?: number; options?: Array<{ file?: string }> };
  // S5.5e — fields read by the beat-level state machine (LD BEAT_LIFECYCLE_STATE_MACHINE_V1).
  // beat.final block is the "is final?" signal per Cursor v8 (NOT a use_as_final boolean).
  // Server writes this at production_server.py:10733-10747 with shape:
  //   { source: "raw_option" | "lipsync", source_option, file, approved_at }
  final?: {
    source?: string;
    source_option?: number;
    file?: string;
    approved_at?: string;
  };
  // Trim/delay (LD-160). Optional — older beats may not carry these.
  trim_in?: number;
  trim_out?: number | string;
  delay_seconds?: number;
}

interface VideoPartition {
  video_role?: string;
  video_label?: string | null;
  beats?: Record<string, BeatState>;
  display_order?: string[];
  completed_mp4_path?: string | null;
}

interface EventState {
  // S5.5d (v3): primary source — videos.<role>.beats
  videos?: Record<string, VideoPartition>;
  // Legacy fallback — top-level beats (pre-S5.5b state shape)
  beats?: Record<string, BeatState>;
  L?: Array<{ id?: string; beat_id?: string; speaker?: string; text?: string }>;
  _module_version?: number;
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

// localStorage shadow key per beat (24h TTL — checked on read).
function shadowKey(eventId: string, beatId: string): string {
  return `mn:v59:shadow:${eventId}:${beatId}`;
}
const SHADOW_TTL_MS = 24 * 3600 * 1000;

function readShadow(eventId: string, beatId: string): string | null {
  try {
    const raw = localStorage.getItem(shadowKey(eventId, beatId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { text: string; ts: number };
    if (Date.now() - parsed.ts > SHADOW_TTL_MS) {
      localStorage.removeItem(shadowKey(eventId, beatId));
      return null;
    }
    return parsed.text;
  } catch {
    return null;
  }
}

function writeShadow(eventId: string, beatId: string, text: string): void {
  try {
    localStorage.setItem(
      shadowKey(eventId, beatId),
      JSON.stringify({ text, ts: Date.now() }),
    );
  } catch {
    // localStorage full / disabled — ignore (best-effort safety net).
  }
}

function clearShadow(eventId: string, beatId: string): void {
  try {
    localStorage.removeItem(shadowKey(eventId, beatId));
  } catch {
    // ignore
  }
}

// ----------------------------------------------------------------
// S5.5e — Beat lifecycle state machine + button row (LD BEAT_LIFECYCLE_STATE_MACHINE_V1)
// ----------------------------------------------------------------

type BeatLifecycle =
  | 'draft'              // no audio yet
  | 'audio_generated'    // TTS done, no animation
  | 'animated'           // 3 options exist, no selection
  | 'selected'           // option chosen, no lipsync
  | 'lipsync_pending'    // in flight
  | 'final';             // beat.final block present (lipsync done OR use-as-final)

function deriveBeatLifecycle(b: BeatState): BeatLifecycle {
  // Cursor v8: beat.final block presence IS the "final" signal.
  if (b.final && b.final.file) return 'final';
  if (b.lipsync?.status === 'pending' || b.lipsync?.status === 'submitted') {
    return 'lipsync_pending';
  }
  const hasOptions = !!(b.phase_1?.options && b.phase_1.options.length > 0);
  const hasSelected = b.phase_1?.selected_option !== undefined && hasOptions;
  if (hasSelected) return 'selected';
  if (hasOptions) return 'animated';
  if (b.audio_file) return 'audio_generated';
  return 'draft';
}

const POLL_ANIMATE_MS = 5000;
const POLL_LIPSYNC_MS = 10000;

interface BeatButtonRowProps {
  index: number;
  beatId: string;
  beat: BeatState;
  /** Bumps when beat fields change (parent's refreshTick). Used as cacheBust for audio preview. */
  cacheBust?: string;
  /** Triggered after any successful mutation so parent can refresh state. */
  onMutated: () => void;
}

function BeatButtonRow({ index, beatId, beat, cacheBust, onMutated }: BeatButtonRowProps) {
  const lifecycle = deriveBeatLifecycle(beat);
  const [busy, setBusy] = useState<string | null>(null); // which button is in-flight
  const [trimIn, setTrimIn] = useState<string>(String(beat.trim_in ?? '0.0'));
  const [trimOut, setTrimOut] = useState<string>(String(beat.trim_out ?? 'full'));
  const [delaySec, setDelaySec] = useState<string>(String(beat.delay_seconds ?? '0.0'));

  // ----------------------------------------------------------------
  // Polling (animate + lipsync)
  // ----------------------------------------------------------------

  useEffect(() => {
    // We can't know if a poll is needed without a job_id — the legacy server
    // tracks jobs internally. We poll status periodically when in the
    // 'lipsync_pending' state to refresh the lifecycle.
    if (lifecycle !== 'lipsync_pending') return;
    let cancelled = false;
    let timer: number | null = null;
    const tick = async () => {
      if (cancelled) return;
      const res = await apiGet('lipsync_status', { beat_id: beatId });
      if (cancelled) return;
      if (res.ok) onMutated();
      timer = window.setTimeout(tick, POLL_LIPSYNC_MS);
    };
    timer = window.setTimeout(tick, POLL_LIPSYNC_MS);
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [lifecycle, beatId]);

  const runMutation = async (label: string, endpoint: any, body: Record<string, unknown>) => {
    setBusy(label);
    const result = await pathappPatch(activeScope.value, endpoint, { beat_id: beatId, ...body });
    setBusy(null);
    if (result.ok) {
      pushToast({ kind: 'success', message: `${label} ok`, source: `beat-${label}` });
      onMutated();
    } else {
      pushToast({ kind: 'error', message: `${label} failed: ${result.error}`, source: `beat-${label}-error` });
    }
    return result.ok;
  };

  const onRegenAudio = () => runMutation('Regen Audio', 'beat_regenerate_audio', {});
  const onAnimate = async () => {
    setBusy('Animate');
    const result = await pathappPatch(activeScope.value, 'animate', { beat_id: beatId });
    setBusy(null);
    if (result.ok) {
      pushToast({ kind: 'info', message: 'Animation submitted (poll status)', source: 'beat-animate' });
      // Spawn poll loop until status returns 3 options.
      let polls = 0;
      const pollAnim = async () => {
        polls += 1;
        const r = await apiGet('animate_status', { beat_id: beatId });
        if (r.ok) onMutated();
        if (polls < 60) window.setTimeout(pollAnim, POLL_ANIMATE_MS);
      };
      window.setTimeout(pollAnim, POLL_ANIMATE_MS);
    } else {
      pushToast({ kind: 'error', message: `Animate failed: ${result.error}`, source: 'beat-animate-error' });
    }
  };
  const onSelectOption = (optionIndex: number) =>
    runMutation('Select option', 'select', { option_index: optionIndex });
  const onAddOptions = () => runMutation('Add options', 'beat_add_options', {});
  const onLipsync = () => runMutation('Lipsync', 'lipsync', {});
  const onUseAsFinal = () => runMutation('Use as Final', 'beat_use_as_final', {});
  const onApplyTrim = () => {
    const tIn = parseFloat(trimIn);
    const tOut = trimOut === 'full' ? null : parseFloat(trimOut);
    return runMutation('Trim', 'beat_trim', {
      trim_in: isNaN(tIn) ? 0 : tIn,
      trim_out: tOut,
    });
  };
  const onApplyDelay = () => {
    const d = parseFloat(delaySec);
    return runMutation('Delay', 'beat_delay', { delay_seconds: isNaN(d) ? 0 : d });
  };

  // Visibility per state-machine table (S5.5e spec §3.1).
  const showRegenAudio = ['draft', 'audio_generated', 'animated', 'selected', 'final'].includes(lifecycle);
  const showAnimate = ['audio_generated'].includes(lifecycle);
  const showAddOptions = ['animated'].includes(lifecycle);
  const showSelectedOptionRadios = ['animated', 'selected'].includes(lifecycle);
  const showLipsync = ['selected', 'lipsync_pending'].includes(lifecycle);
  const showUseAsFinal = ['audio_generated', 'selected'].includes(lifecycle);
  const showPreview = lifecycle !== 'draft';

  const optionCount = beat.phase_1?.options?.length ?? 0;
  const selectedOption = beat.phase_1?.selected_option ?? null;

  return (
    <div class="mn-beat-button-row" data-testid={`beat-button-row-${index}`} data-lifecycle={lifecycle}>
      {/* Phase 1 — animation options (visible in animated/selected) */}
      {showSelectedOptionRadios && optionCount > 0 ? (
        <span class="mn-beat-button-group" data-testid={`beat-options-group-${index}`}>
          <span class="mn-beat-button-group-label">Phase 1:</span>
          {Array.from({ length: optionCount }).map((_, i) => {
            const oi = i + 1;
            return (
              <button
                key={oi}
                type="button"
                class={`mn-btn mn-btn-small${selectedOption === oi ? ' is-active' : ''}`}
                data-testid={`beat-${index}-select-option-${oi}`}
                onClick={() => onSelectOption(oi)}
                disabled={busy !== null}
              >
                opt {oi}{selectedOption === oi ? ' ✓' : ''}
              </button>
            );
          })}
          {showAddOptions ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-${index}-add-options`}
              onClick={onAddOptions}
              disabled={busy !== null}
            >
              + Add options
            </button>
          ) : null}
        </span>
      ) : null}

      {/* Audio group */}
      {showPreview ? (
        <span class="mn-beat-button-group" data-testid={`beat-audio-group-${index}`}>
          <span class="mn-beat-button-group-label">Audio:</span>
          <BeatAudioPreview
            beatId={beatId}
            {...(cacheBust !== undefined ? { cacheBust } : (beat.text_last_updated_at !== undefined ? { cacheBust: beat.text_last_updated_at } : {}))}
            testId={`beat-${index}`}
            disabled={!beat.audio_file}
          />
          {showRegenAudio ? (
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-${index}-regen-audio`}
              onClick={onRegenAudio}
              disabled={busy !== null}
              title="Re-generate TTS for this beat"
            >
              {busy === 'Regen Audio' ? <><Spinner size="sm" inline /> …</> : '🎙 Regen Audio'}
            </button>
          ) : null}
        </span>
      ) : showRegenAudio ? (
        <span class="mn-beat-button-group">
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-regen-audio`}
            onClick={onRegenAudio}
            disabled={busy !== null}
          >
            {busy === 'Regen Audio' ? <><Spinner size="sm" inline /> …</> : '🎙 Regen Audio'}
          </button>
        </span>
      ) : null}

      {/* Pipeline group */}
      <span class="mn-beat-button-group" data-testid={`beat-pipeline-group-${index}`}>
        <span class="mn-beat-button-group-label">Pipeline:</span>
        {showAnimate ? (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-animate`}
            onClick={onAnimate}
            disabled={busy !== null}
            title="Submit to Kling animation (3 options)"
          >
            {busy === 'Animate' ? <><Spinner size="sm" inline /> …</> : '🎬 Animate'}
          </button>
        ) : null}
        {showLipsync ? (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-lipsync`}
            onClick={onLipsync}
            disabled={busy !== null || lifecycle === 'lipsync_pending'}
            title="Send selected option for ByteDance lipsync"
          >
            {lifecycle === 'lipsync_pending' ? (
              <><Spinner size="sm" inline /> in progress</>
            ) : (
              busy === 'Lipsync' ? <><Spinner size="sm" inline /> …</> : '👄 Lipsync'
            )}
          </button>
        ) : null}
        {showUseAsFinal ? (
          <button
            type="button"
            class="mn-btn mn-btn-small mn-btn-primary"
            data-testid={`beat-${index}-use-as-final`}
            onClick={onUseAsFinal}
            disabled={busy !== null}
            title="Mark current selection as final without lipsync (Spec A)"
          >
            {busy === 'Use as Final' ? <><Spinner size="sm" inline /> …</> : '✓ Use as Final'}
          </button>
        ) : null}
        {lifecycle === 'final' ? (
          <span class="mn-dim" data-testid={`beat-${index}-final-marker`}>
            ✓ final ({beat.final?.source ?? '?'})
          </span>
        ) : null}
      </span>

      {/* Trim / Delay group */}
      <span class="mn-beat-button-group" data-testid={`beat-trim-group-${index}`}>
        <span class="mn-beat-button-group-label">Trim:</span>
        <input
          type="text"
          class="mn-beat-trim-input"
          data-testid={`beat-${index}-trim-in`}
          value={trimIn}
          onInput={(e) => setTrimIn((e.target as HTMLInputElement).value)}
          aria-label="Trim in seconds"
          placeholder="0.0"
        />
        <span class="mn-dim">→</span>
        <input
          type="text"
          class="mn-beat-trim-input"
          data-testid={`beat-${index}-trim-out`}
          value={trimOut}
          onInput={(e) => setTrimOut((e.target as HTMLInputElement).value)}
          aria-label="Trim out (number or 'full')"
          placeholder="full"
        />
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-${index}-trim-apply`}
          onClick={onApplyTrim}
          disabled={busy !== null}
        >
          apply
        </button>
        <span class="mn-beat-button-group-label" style="margin-left:8px">Delay:</span>
        <input
          type="text"
          class="mn-beat-trim-input"
          data-testid={`beat-${index}-delay`}
          value={delaySec}
          onInput={(e) => setDelaySec((e.target as HTMLInputElement).value)}
          aria-label="Delay seconds"
          placeholder="0.0"
        />
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-${index}-delay-apply`}
          onClick={onApplyDelay}
          disabled={busy !== null}
        >
          apply
        </button>
      </span>
    </div>
  );
}

// ----------------------------------------------------------------
// Per-beat editable card
// ----------------------------------------------------------------

interface BeatCardProps {
  index: number;
  beatId: string;
  beat: BeatState;
  eventId: string;
  onMutated: () => void;
}

function BeatCard({ index, beatId, beat, eventId, onMutated }: BeatCardProps) {
  const initialText = beat.text ?? '';
  // CRITICAL: contenteditable must be UNCONTROLLED. State-driven children on a
  // contenteditable trigger a re-render on every keystroke, which clobbers
  // the DOM text node and resets the cursor to position 0. The user-visible
  // bug is that typed characters appear REVERSED (because each new char goes
  // in at position 0 after cursor reset). Fix: render initialText ONCE via
  // ref, never set children from state, read text on blur.
  const editRef = useRef<HTMLParagraphElement | null>(null);
  const [status, setStatus] = useState<SaveStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(beat.text_last_updated_at ?? null);

  // Hydrate the ref's initial text + recover from localStorage if a fresher draft.
  useEffect(() => {
    const draft = readShadow(eventId, beatId);
    if (editRef.current) {
      if (draft !== null && draft !== initialText) {
        editRef.current.innerText = draft;
      } else {
        editRef.current.innerText = initialText;
      }
    }
  }, []);

  const onInput = () => {
    const next = editRef.current?.innerText ?? '';
    writeShadow(eventId, beatId, next);
  };

  const onBlur = async () => {
    const next = editRef.current?.innerText ?? '';
    if (next === initialText) {
      setStatus('idle');
      return;
    }
    setStatus('saving');
    setErrorMsg(null);
    const result = await pathappPatch(activeScope.value, 'beat_update_text', {
      beat: beatId,
      text: next,
    });
    if (result.ok) {
      setStatus('saved');
      setSavedAt(new Date().toISOString());
      clearShadow(eventId, beatId);
      // Auto-fade to idle after 2s.
      setTimeout(() => setStatus((s) => (s === 'saved' ? 'idle' : s)), 2000);
    } else {
      setStatus('error');
      setErrorMsg(result.error ?? `HTTP ${result.status}`);
    }
  };

  const indicatorClass =
    status === 'saving'
      ? 'mn-save-indicator mn-save-saving'
      : status === 'saved'
        ? 'mn-save-indicator mn-save-saved'
        : status === 'error'
          ? 'mn-save-indicator mn-save-error'
          : 'mn-save-indicator';

  const indicatorLabel =
    status === 'saving'
      ? 'Saving…'
      : status === 'saved'
        ? '✓ Saved'
        : status === 'error'
          ? '✗ ' + (errorMsg ?? 'error')
          : savedAt
            ? `last save ${savedAt.slice(11, 19)}Z`
            : '';

  return (
    <li
      class="mn-beat-card"
      data-testid={`beat-card-${index}`}
      data-beat-id={beatId}
    >
      <div class="mn-beat-meta">
        <span class="mn-beat-index">#{index + 1}</span>
        <span class="mn-beat-anchor">{beatId}</span>
        <span class="mn-beat-speaker">{beat.speaker ?? 'speaker'}</span>
        {beat.text_modified_after_tts ? (
          <span class="mn-beat-stale-tts" data-testid={`beat-stale-tts-${index}`}>
            stale TTS
          </span>
        ) : null}
        <span
          class={indicatorClass}
          data-testid={`beat-save-${index}`}
          data-save-status={status}
        >
          {indicatorLabel}
        </span>
      </div>
      <BeatImageHolder index={index} beatId={beatId} beat={beat} eventId={eventId} onMutated={onMutated} />
      <p
        ref={editRef}
        class="mn-beat-text mn-beat-editable"
        data-testid={`beat-text-${index}`}
        contentEditable
        spellcheck
        onInput={onInput}
        onBlur={onBlur}
      />
      <BeatButtonRow
        index={index}
        beatId={beatId}
        beat={beat}
        {...(savedAt ? { cacheBust: savedAt } : {})}
        onMutated={onMutated}
      />
      <BeatMagicButtons index={index} beatId={beatId} beat={beat} eventId={eventId} />
    </li>
  );
}

// ----------------------------------------------------------------
// CC-16 — Storyboard image-holder drop zone (PREP for Phase B SB-14).
//
// Per spec §4 Phase A: define `mn-storyboard-image-drop-zone` CSS class +
// onDrop handler accepting `lib-image` payload. The actual <img> rendering
// + Assign/Inject buttons land in Phase B SB-14; Phase A stands up the drop
// surface so library-tile drag works end-to-end and Phase B can layer on
// the rest without changing this component's drop contract.
// ----------------------------------------------------------------

interface BeatImageHolderProps {
  index: number;
  beatId: string;
  beat: BeatState;
  eventId: string;
  onMutated: () => void;
}

function BeatImageHolder({ index, beatId, beat, eventId, onMutated }: BeatImageHolderProps) {
  const stillPath = beat.image_path;
  const hasImage = !!stillPath;
  const imgSrc = stillPath
    ? `http://localhost:5111/files?path=${encodeURIComponent(`Production/${eventId}/${stillPath}`)}`
    : undefined;

  const dropHandlers = makeDropTarget(
    async (payload) => {
      if (payload.kind !== 'lib-image') return;
      const result = await pathappPatch(activeScope.value, 'assign_image', {
        beat: beatId,
        image_key: payload.lib_key,
      });
      if (result.ok) {
        pushToast({
          kind: 'success',
          message: `Image ${payload.lib_key} assigned to ${beatId}`,
          source: 'sb-image-drop',
        });
        onMutated();
      } else {
        pushToast({
          kind: 'error',
          message: `Image assign failed: ${result.error ?? `HTTP ${result.status}`}`,
          source: 'sb-image-drop-error',
        });
      }
    },
    (p) => p.kind === 'lib-image',
  );

  return (
    <div
      class={`mn-storyboard-image-drop-zone mn-drop-target${hasImage ? ' has-image' : ''}`}
      data-testid={`beat-image-zone-${index}`}
      data-beat-id={beatId}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
    >
      {hasImage && imgSrc ? (
        <img
          src={imgSrc}
          alt={`beat ${beatId} image`}
          class="mn-storyboard-image-thumb"
          loading="lazy"
        />
      ) : (
        <span class="mn-dim mn-storyboard-image-placeholder">drop library image here</span>
      )}
    </div>
  );
}

// ----------------------------------------------------------------
// BeatMagicButtons — S5 v3.1 magic trail triggers (LDs 468/469)
// ----------------------------------------------------------------

interface BeatMagicProps {
  index: number;
  beatId: string;
  beat: BeatState;
  eventId: string;
}

function BeatMagicButtons({ index, beatId, beat, eventId }: BeatMagicProps) {
  const stillPath = beat.image_path;
  // Pick primary video: lipsync preferred, else selected animation option.
  let videoPath: string | undefined;
  if (beat.lipsync?.file) videoPath = beat.lipsync.file;
  else if (beat.phase_1?.options && beat.phase_1.selected_option !== undefined) {
    const opt = beat.phase_1.options[beat.phase_1.selected_option - 1];
    if (opt?.file) videoPath = opt.file;
  }

  const hasMagicStill = !!beat.magic_still_path;
  const hasMagicVideo = !!beat.magic_video_path;

  const openMagicStill = () => {
    if (!stillPath) return;
    const u = new URL('http://localhost:5111/magic');
    u.searchParams.set('mode', 'magic_still');
    u.searchParams.set('beat_id', beatId);
    u.searchParams.set('source_image_path', `Production/${eventId}/${stillPath}`);
    u.searchParams.set('return_endpoint', '/api/storyboard/magic_still');
    u.searchParams.set('scope_event_id', eventId);
    window.open(u.toString(), '_blank');
  };

  const openMagicVideo = () => {
    if (!videoPath) return;
    const u = new URL('http://localhost:5111/magic');
    u.searchParams.set('mode', 'magic_video');
    u.searchParams.set('beat_id', beatId);
    u.searchParams.set('source_video_path', `Production/${eventId}/${videoPath}`);
    if (stillPath) {
      u.searchParams.set('source_image_path', `Production/${eventId}/${stillPath}`);
    }
    u.searchParams.set('return_endpoint', '/api/storyboard/magic_video');
    u.searchParams.set('scope_event_id', eventId);
    window.open(u.toString(), '_blank');
  };

  return (
    <div class="mn-beat-magic-row" data-testid={`beat-magic-row-${index}`}>
      {stillPath ? (
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-magic-still-${index}`}
          onClick={openMagicStill}
          disabled={hasMagicStill}
          title={hasMagicStill ? 'magic on still already exists' : 'Add magic trail on still (LD-468)'}
        >
          {hasMagicStill ? '✓ magic on still' : '🌟 Add magic on still'}
        </button>
      ) : null}
      {videoPath ? (
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-magic-video-${index}`}
          onClick={openMagicVideo}
          disabled={hasMagicVideo}
          title={hasMagicVideo ? 'magic on video already exists' : 'Add magic trail on video (LD-469)'}
        >
          {hasMagicVideo ? '✓ magic on video' : '🎬 Add magic on video'}
        </button>
      ) : null}
    </div>
  );
}

// ----------------------------------------------------------------
// Send Out as MP4 (Storyboard footer) — S5.5d v3 pipeline.
// Replaces legacy ExportButtons per Rule 27 + STORYBOARD_SEND_OUT_PROVENANCE_V1.
// Calls POST /api/scene/assemble — Stage 1 finalizes each beat (cached);
// Stage 2 mirrors _handle_preview_stitched orchestration to assemble the
// scene + register scene_concat_mp4 asset.
// ----------------------------------------------------------------

interface SceneAssembleResponse {
  ok?: boolean;
  asset_id?: number;
  completed_mp4_path?: string;
  assemble_hash?: string;
  beat_count?: number;
  file_size_bytes?: number;
  bitrate_bps?: number;
  duration_s?: number;
  size_warning?: string | null;
  cache_stats?: Record<string, number>;
  error?: string;
}

function SendOutButton() {
  const [status, setStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [detail, setDetail] = useState<string | null>(null);

  const onSendOut = async () => {
    setStatus('sending');
    const role = activeTargetVideo.value;
    setDetail(`role=${role} assembling…`);
    // S5.5e §3.5 (Cursor v8): MIGRATED from raw fetch to pathappPatch — keeps
    // the call inside the single mutation channel + auto-injects scope keys
    // (scope_event_id OR scope_milestone_id, scope_target_video, scope_version)
    // per LD-461. The endpoint is registered as 'scene_assemble' in
    // MUTATION_ENDPOINTS.
    const result = await pathappPatch<SceneAssembleResponse>(
      activeScope.value, 'scene_assemble', {
        scope_target_video: role,
        fade_between_beats_ms: 0,
      },
    );
    const data = result.data ?? {};
    if (result.ok && data.ok) {
      setStatus('ok');
      const stats = data.cache_stats ?? {};
      const statsStr = Object.entries(stats)
        .filter(([_, v]) => v !== 0)
        .map(([k, v]) => `${k}=${v}`)
        .join(' ');
      setDetail(
        `✓ asset_id=${data.asset_id} hash=${data.assemble_hash?.slice(0, 10)}` +
        ` beats=${data.beat_count} size=${Math.round((data.file_size_bytes ?? 0) / 1024)}KB` +
        (statsStr ? ` stats={${statsStr}}` : '') +
        (data.size_warning ? ` ⚠ ${data.size_warning}` : ''),
      );
    } else {
      setStatus('error');
      setDetail(`HTTP ${result.status}: ${data.error ?? result.error ?? 'unknown'}`);
    }
    setTimeout(() => setStatus((s) => (s === 'ok' ? 'idle' : s)), 5000);
  };

  return (
    <div class="mn-export-actions" data-testid="send-out-actions">
      <button
        type="button"
        class="mn-btn"
        data-testid="send-out-mp4-btn"
        onClick={onSendOut}
        disabled={status === 'sending'}
        title="Finalize each beat + xfade-concat into a registered scene_concat_mp4 asset"
      >
        {status === 'sending' ? 'Sending…' : 'Send Out as MP4'}
      </button>
      <span
        class={`mn-export-status mn-export-${status}`}
        data-testid="send-out-status"
      >
        {status === 'idle' ? '' : detail}
      </span>
    </div>
  );
}

// ----------------------------------------------------------------
// Main tab
// ----------------------------------------------------------------

export function StoryboardTab() {
  const [state, setState] = useState<EventState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  // R1 fix per spec §5 Phase 3.1 — explicit scope signals in dep array,
  // first-run-sync via prevDepsRef, 200ms debounce on subsequent runs (Q6).
  const prevFetchDepsRef = useRef<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    const fetchState = async () => {
      const res = await apiGet<EventState>('v2_event_state', {
        event_id: activeScope.value.event_id,
      });
      if (cancelled) return;
      setLoading(false);
      if (res.ok && res.data) {
        setState(res.data);
        setError(null);
      } else {
        setError(res.error ?? 'unknown error');
      }
    };

    const depKey = [
      refreshTick,
      activeScope.value.event_id,
      activeProjectType.value,
      activeMilestoneId.value ?? '',
    ].join('|');

    if (prevFetchDepsRef.current === null) {
      prevFetchDepsRef.current = depKey;
      fetchState();
    } else if (prevFetchDepsRef.current !== depKey) {
      prevFetchDepsRef.current = depKey;
      timer = window.setTimeout(fetchState, 200);
    }

    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [
    refreshTick,
    activeScope.value.event_id,
    activeProjectType.value,
    activeMilestoneId.value,
  ]);

  // S5 — refresh on path_picker submit success.
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.type === 'mn-magic-or-animate-complete') {
        setRefreshTick((n) => n + 1);
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, []);

  const beatList = useMemo(() => {
    if (!state) return [];
    // S5.5d (v3): primary source — state.videos[<role>].beats
    const role = activeTargetVideo.value;
    const partition = state.videos?.[role];
    if (partition?.beats && Object.keys(partition.beats).length > 0) {
      // DISPLAY_ORDER_STRICT_V1 — when display_order is a present LIST,
      // honor it strictly (including the empty-list case which renders zero
      // beats). Only when display_order is genuinely missing — undefined,
      // or non-list legacy data shapes — do we fall through to the
      // Object.entries sorted-by-beat_id legacy renderer. The Array.isArray
      // gate is the defensive form of spec v2 §2.3 Part 1's
      // `!== undefined` check; it correctly handles the historical fixture
      // partition-ordering integer (e.g. `display_order: 1`) as legacy.
      if (Array.isArray(partition.display_order)) {
        return partition.display_order
          .filter((bid) => partition.beats?.[bid])
          .map((beat_id) => ({ beat_id, ...partition.beats![beat_id] }));
      }
      return Object.entries(partition.beats)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([beat_id, b]) => ({ beat_id, ...b }));
    }
    // Legacy fallback — top-level beats (pre-S5.5b state shape)
    if (state.beats && Object.keys(state.beats).length > 0) {
      return Object.entries(state.beats)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([beat_id, b]) => ({ beat_id, ...b }));
    }
    if (state.L) {
      return state.L.map((b, i) => {
        const beat_id = b.beat_id ?? b.id ?? `beat_${String(i + 1).padStart(2, '0')}`;
        const out: BeatState & { beat_id: string } = { beat_id };
        if (b.speaker !== undefined) out.speaker = b.speaker;
        if (b.text !== undefined) out.text = b.text;
        return out;
      });
    }
    return [];
  }, [state, activeTargetVideo.value]);

  const eventId = activeScope.value.event_id;

  return (
    <section class="mn-tab-pane mn-storyboard-pane" data-testid="pane-storyboard">
      <header class="mn-pane-header">
        <h2>Storyboard</h2>
        <span class="mn-scope-chip" data-testid="storyboard-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
      </header>
      {/* S5.5d (v3 architecture revision, 2026-05-03):
          Phase A and Phase B are now top-level dedicated tabs (not siblings
          inside Storyboard). The PhaseProducer component still exists and is
          rendered by tabs/PhaseATab.tsx + tabs/PhaseBTab.tsx. */}
      {loading ? (
        <p class="mn-loading" data-testid="storyboard-loading">
          Loading event state&hellip;
        </p>
      ) : error ? (
        <div class="mn-empty" data-testid="storyboard-error">
          <p class="mn-warn">Could not reach /api/v2/event-state.</p>
          <p class="mn-dim">{error}</p>
        </div>
      ) : beatList.length === 0 ? (
        <div class="mn-empty" data-testid="storyboard-empty">
          <p>No beats in this event yet.</p>
        </div>
      ) : (
        <ol class="mn-beat-list" data-testid="beat-list">
          {beatList.map((b, i) => (
            <BeatCard
              key={b.beat_id}
              index={i}
              beatId={b.beat_id}
              beat={b}
              eventId={eventId}
              onMutated={() => setRefreshTick((n) => n + 1)}
            />
          ))}
        </ol>
      )}
      <footer class="mn-pane-footer">
        <SendOutButton />
        <p class="mn-dim mn-readonly-banner" data-testid="storyboard-readonly">
          {beatList.length === 0
            ? 'Read-only — no beats to edit.'
            : `${beatList.length} beats — dialogue edit live (saves through pathappPatch).`}
        </p>
      </footer>
    </section>
  );
}
