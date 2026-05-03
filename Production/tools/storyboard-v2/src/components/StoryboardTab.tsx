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
import { activeScope, scopeKey } from '../state/scope';
import { apiGet, pathappPatch } from '../api/client';
import { PhaseProducer } from './phase/PhaseProducer';

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
  lipsync?: { file?: string };
  phase_1?: { selected_option?: number; options?: Array<{ file?: string }> };
}

interface EventState {
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
// Per-beat editable card
// ----------------------------------------------------------------

interface BeatCardProps {
  index: number;
  beatId: string;
  beat: BeatState;
  eventId: string;
}

function BeatCard({ index, beatId, beat, eventId }: BeatCardProps) {
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
      <p
        ref={editRef}
        class="mn-beat-text mn-beat-editable"
        data-testid={`beat-text-${index}`}
        contentEditable
        spellcheck
        onInput={onInput}
        onBlur={onBlur}
      />
      <BeatMagicButtons index={index} beatId={beatId} beat={beat} eventId={eventId} />
    </li>
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
// Export buttons (Storyboard footer) — intro / resolution / standalone
// ----------------------------------------------------------------

type ExportRole = 'intro' | 'resolution' | 'standalone';

function ExportButtons() {
  const [status, setStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [detail, setDetail] = useState<string | null>(null);

  const onExport = async (role: ExportRole) => {
    setStatus('sending');
    setDetail(`role=${role}`);
    // /api/export is a synchronous POST that writes animation_selections.json
    // under event_dir. Pre-work pin already added in S2 (LD-460).
    // Note: /api/export currently takes no body — server reads selections
    // from state. We pass scope_event_id so the scope guard accepts our role
    // routing intent in the audit trail.
    const result = await pathappPatch(activeScope.value, 'state_snapshot', {
      // Snapshot pre-export so a failed export is recoverable.
      reason: `pre_export_${role}`,
    }, { skipSnapshot: true });
    // Then call /api/export directly via fetch (it's a no-body endpoint).
    // pathappPatch isn't ideal here because /api/export ignores body.
    try {
      const res = await fetch(`http://localhost:5111/api/export?role=${role}&event_id=${activeScope.value.event_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: activeScope.value.event_id, role }),
      });
      if (res.ok) {
        setStatus('ok');
        setDetail(`role=${role} exported (snapshot ${result.ok ? 'ok' : 'failed (non-fatal)'})`);
      } else {
        setStatus('error');
        const txt = await res.text().catch(() => '');
        setDetail(`HTTP ${res.status}: ${txt.slice(0, 120)}`);
      }
    } catch (e) {
      setStatus('error');
      setDetail(`network: ${String(e)}`);
    }
    setTimeout(() => setStatus((s) => (s === 'ok' ? 'idle' : s)), 3000);
  };

  return (
    <div class="mn-export-actions" data-testid="export-actions">
      <button
        type="button"
        class="mn-btn"
        data-testid="export-intro-btn"
        onClick={() => onExport('intro')}
        disabled={status === 'sending'}
      >
        Export Intro
      </button>
      <button
        type="button"
        class="mn-btn"
        data-testid="export-resolution-btn"
        onClick={() => onExport('resolution')}
        disabled={status === 'sending'}
      >
        Export Resolution
      </button>
      <button
        type="button"
        class="mn-btn"
        data-testid="export-standalone-btn"
        onClick={() => onExport('standalone')}
        disabled={status === 'sending'}
      >
        Export Standalone
      </button>
      <span
        class={`mn-export-status mn-export-${status}`}
        data-testid="export-status"
      >
        {status === 'idle' ? '' : status === 'sending' ? 'sending…' : detail}
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
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
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

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
  }, [state]);

  const eventId = activeScope.value.event_id;

  return (
    <section class="mn-tab-pane mn-storyboard-pane" data-testid="pane-storyboard">
      <header class="mn-pane-header">
        <h2>Storyboard</h2>
        <span class="mn-scope-chip" data-testid="storyboard-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
      </header>
      <div class="mn-phase-producers" data-testid="phase-producers">
        <PhaseProducer phase="b" />
        <PhaseProducer phase="a" />
      </div>
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
            />
          ))}
        </ol>
      )}
      <footer class="mn-pane-footer">
        <ExportButtons />
        <p class="mn-dim mn-readonly-banner" data-testid="storyboard-readonly">
          {beatList.length === 0
            ? 'Read-only — no beats to edit.'
            : `${beatList.length} beats — dialogue edit live (saves through pathappPatch).`}
        </p>
      </footer>
    </section>
  );
}
