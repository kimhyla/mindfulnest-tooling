// PhaseProducer — shared base for Phase A + Phase B producers.
// Per LD-462 PHASE_A_PRODUCER_V1 + LD-463 PHASE_B_PRODUCER_V1.
//
// S4 SCOPE (this file): real producer UX — script editor, audio player
// (priority lipsync > mixed > stem), Send for Lipsync, lipsync video
// player, Mix Audio (Phase A only — auto-fires stitch), Export to
// Stitcher, watercolor library + Animate-this. All wired through
// pathappPatch (snapshot + scope-guard + 409/423 handling).
//
// HONEST S5 DEFERRED: WaveSurfer.js v7 waveform display + click-to-drop
// watercolor onto timeline + cue popover with animation/duration/Delete.
// The button-based flow ships in S4; Kim can use it end-to-end now;
// timeline-as-direct-manipulation lands in S5.

import { useEffect, useState } from 'preact/hooks';
import { apiGet, pathappPatch } from '../../api/client';
import { activeScope } from '../../state/scope';
import { SERVER_BASE } from '../../api/endpoints';
import { WaveformTimeline, type WatercolorCue } from './WaveformTimeline';

interface WatercolorItem {
  key: string;
  filename: string;
  ext: string;
  kind: 'static' | 'animation' | string;
  thumb_url: string;
  mtime: number;
  size_bytes: number;
}
interface WatercolorListResponse {
  ok: boolean;
  items?: WatercolorItem[];
  count?: number;
}

interface BaseClipItem {
  id: string;
  filename: string;
  ext: string;
  character: string | null;
  duration_s: number | null;
}
interface BaseClipsResponse {
  ok: boolean;
  items?: BaseClipItem[];
  count?: number;
}

interface PhaseStateSlice {
  voice_stem_file?: string;
  voice_stem_mtime?: number;
  mixed_audio_file?: string;
  mixed_audio_mtime?: number;
  lipsync_file?: string;
  lipsync_mtime?: number;
  stitched_file?: string;        // phase A only
  stitched_mtime?: number;
  script?: string;
  watercolor_cues?: WatercolorCue[];
}
interface EventStateResponse {
  beats?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PhaseProducerProps {
  phase: 'a' | 'b';
}

function pickPhaseSlice(state: EventStateResponse, phase: 'a' | 'b'): PhaseStateSlice {
  const get = <T,>(suffix: string): T | undefined =>
    state[`phase_${phase}_${suffix}`] as T | undefined;
  const slice: PhaseStateSlice = {};
  const vs = get<string>('voice_stem_file');           if (vs) slice.voice_stem_file = vs;
  const vsm = get<number>('voice_stem_mtime');         if (vsm) slice.voice_stem_mtime = vsm;
  const mx = get<string>('mixed_audio_file');          if (mx) slice.mixed_audio_file = mx;
  const mxm = get<number>('mixed_audio_mtime');        if (mxm) slice.mixed_audio_mtime = mxm;
  const ls = get<string>('lipsync_file');              if (ls) slice.lipsync_file = ls;
  const lsm = get<number>('lipsync_mtime');            if (lsm) slice.lipsync_mtime = lsm;
  const st = get<string>('stitched_file');             if (st) slice.stitched_file = st;
  const stm = get<number>('stitched_mtime');           if (stm) slice.stitched_mtime = stm;
  const sc = get<string>('script');                    if (sc) slice.script = sc;
  const cues = get<WatercolorCue[]>('watercolor_cues_json');
  if (Array.isArray(cues)) slice.watercolor_cues = cues;
  return slice;
}

type AudioSourceLabel = 'lipsync' | 'mixed' | 'stem';

function priorityAudioFile(
  slice: PhaseStateSlice,
): { name: string; label: AudioSourceLabel } | null {
  if (slice.lipsync_file) return { name: slice.lipsync_file, label: 'lipsync' };
  if (slice.mixed_audio_file) return { name: slice.mixed_audio_file, label: 'mixed' };
  if (slice.voice_stem_file) return { name: slice.voice_stem_file, label: 'stem' };
  return null;
}

function fileUrl(name: string): string {
  // Server's /files endpoint serves arbitrary event_dir files via ?path=.
  // Path is scope-bound: derived from activeScope.value.event_id so the same
  // app works for Event_1, Event_e2e_fixture, or any other event without a
  // hardcoded literal (F17 gate / spec §19.10 #2).
  const eventId = activeScope.value.event_id;
  return `${SERVER_BASE}/files?path=${encodeURIComponent(`Production/${eventId}/${name}`)}`;
}

export function PhaseProducer({ phase }: PhaseProducerProps) {
  const [collapsed, setCollapsed] = useState(true);
  const [watercolors, setWatercolors] = useState<WatercolorItem[]>([]);
  const [baseClips, setBaseClips] = useState<BaseClipItem[]>([]);
  const [stateSlice, setStateSlice] = useState<PhaseStateSlice>({});
  const [scriptDraft, setScriptDraft] = useState<string>('');
  const [suggesting, setSuggesting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [selectedBaseClip, setSelectedBaseClip] = useState<string>('');

  const refreshAll = async () => {
    const [wc, bc, st] = await Promise.all([
      apiGet<WatercolorListResponse>('phase_watercolor_list'),
      apiGet<BaseClipsResponse>('phase_base_clips_list'),
      apiGet<EventStateResponse>('v2_event_state', { event_id: activeScope.value.event_id }),
    ]);
    if (wc.ok && wc.data?.items) setWatercolors(wc.data.items);
    if (bc.ok && bc.data?.items) {
      setBaseClips(bc.data.items);
      // Auto-select character match for the active phase.
      const wantedChar = phase === 'a' ? 'chipper' : 'cedric';
      const match = bc.data.items.find((c) => c.character === wantedChar);
      if (match) setSelectedBaseClip((prev) => prev || match.id);
    }
    if (st.ok && st.data) {
      const slice = pickPhaseSlice(st.data, phase);
      setStateSlice(slice);
      if (slice.script) setScriptDraft(slice.script);
    }
  };

  useEffect(() => {
    if (collapsed) return;
    let cancelled = false;
    (async () => { if (!cancelled) await refreshAll(); })();
    return () => { cancelled = true; };
  }, [collapsed]);

  // Listen for "magic or animate complete" postMessage from path_picker.html
  // (S5 LD-468/469/470 — supersedes S4 mn:watercolor-animated).
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      const t = e.data?.type;
      if (t === 'mn-magic-or-animate-complete' || t === 'mn:watercolor-animated') {
        refreshAll();
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [phase]);

  const phaseLabel = phase === 'a' ? 'Phase A (Chipper)' : 'Phase B (Cedric)';

  const onSuggest = async () => {
    setSuggesting(true);
    setStatusMsg(null);
    const res = await pathappPatch(activeScope.value, 'phase_suggest_script', { phase });
    setSuggesting(false);
    if (res.ok && res.data) {
      const data = res.data as { script?: string; tokens_in?: number; tokens_out?: number };
      if (data.script) {
        setScriptDraft(data.script);
        setStatusMsg(
          `✓ Script suggested (${data.tokens_in ?? '?'} in / ${data.tokens_out ?? '?'} out tokens)`,
        );
      } else {
        setStatusMsg('Script suggestion empty — server returned no text');
      }
    } else {
      const data = res.data as { code?: string; message?: string } | undefined;
      if (data?.code === 'ANTHROPIC_API_KEY_MISSING') {
        setStatusMsg('⚠ Anthropic API key not configured. Add to Doppler + restart.');
      } else {
        setStatusMsg(`error: HTTP ${res.status} ${res.error ?? ''}`);
      }
    }
  };

  const onSendForLipsync = async () => {
    if (!selectedBaseClip) {
      setStatusMsg('Pick a base clip first.');
      return;
    }
    setBusyAction('lipsync');
    setStatusMsg('Sending for lipsync…');
    const res = await pathappPatch(activeScope.value, 'phase_b_lipsync', {
      phase,
      base_clip_id: selectedBaseClip,
    });
    setBusyAction(null);
    if (res.ok) {
      setStatusMsg('✓ Lipsync complete');
      await refreshAll();
    } else {
      const data = res.data as { hint?: string } | undefined;
      setStatusMsg(`✗ Lipsync HTTP ${res.status}: ${data?.hint ?? res.error ?? ''}`);
    }
  };

  const onMixAudio = async () => {
    setBusyAction('mix');
    setStatusMsg('Mix Audio (Phase A auto-fires stitch)…');
    const res = await pathappPatch(activeScope.value, 'phase_b_mix_audio', { phase });
    setBusyAction(null);
    if (res.ok) {
      setStatusMsg('✓ Mix complete (Phase A stitch auto-fired)');
      await refreshAll();
    } else {
      setStatusMsg(`✗ Mix HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  const onExportToStitcher = async () => {
    // The export source for Phase B is the lipsync mp4; for Phase A it's
    // the stitched mp4.
    const srcFile = phase === 'a' ? stateSlice.stitched_file : stateSlice.lipsync_file;
    if (!srcFile) {
      setStatusMsg(`No ${phase === 'a' ? 'stitched' : 'lipsync'} mp4 yet — finish the producer flow first.`);
      return;
    }
    setBusyAction('export');
    setStatusMsg('Exporting to Stitcher…');
    const res = await pathappPatch(activeScope.value, 'stitch_save_job', {
      job_name: `phase_${phase}_${activeScope.value.event_id}`,
      slot: phase === 'a' ? 'phase_a' : 'phase_b',
      video_path: `Production/${activeScope.value.event_id}/${srcFile}`,
    });
    setBusyAction(null);
    if (res.ok) {
      setStatusMsg('✓ Exported to Stitcher (see Stitcher tab to bake)');
    } else {
      setStatusMsg(`✗ Export HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  const onAnimateThis = (key: string) => {
    // S5 v3.1 — explicit mode=watercolor_animate (LD-470).
    const url = new URL(`${SERVER_BASE}/magic`);
    url.searchParams.set('mode', 'watercolor_animate');
    url.searchParams.set('watercolor_key', key);
    url.searchParams.set('return_endpoint', '/api/watercolor/animate');
    url.searchParams.set('scope_event_id', activeScope.value.event_id);
    window.open(url.toString(), '_blank');
  };

  const audioFile = priorityAudioFile(stateSlice);
  const lipsyncFile = stateSlice.lipsync_file ?? null;

  return (
    <details
      class={`mn-phase-producer mn-phase-${phase}`}
      data-testid={`phase-producer-${phase}`}
      open={!collapsed}
      onToggle={(e: Event) => {
        const t = e.target as HTMLDetailsElement;
        setCollapsed(!t.open);
      }}
    >
      <summary class="mn-phase-summary">
        {phaseLabel}
        <span class="mn-dim mn-phase-status-tag">
          {audioFile ? `audio: ${audioFile.label}` : 'no audio yet'}
          {lipsyncFile ? ' · lipsync ✓' : ''}
        </span>
      </summary>

      <div class="mn-phase-body">
        {/* Script editor + Suggest */}
        <div class="mn-phase-row">
          <button
            type="button"
            class="mn-btn"
            data-testid={`phase-${phase}-suggest-btn`}
            onClick={onSuggest}
            disabled={suggesting}
          >
            {suggesting ? 'Suggesting…' : 'Suggest Script'}
          </button>
          <span class="mn-dim">
            {phase === 'a' ? 'reads Phase B + module context' : 'reads arc skeleton + therapeutic'}
          </span>
        </div>
        <textarea
          class="mn-phase-script-editor"
          data-testid={`phase-${phase}-script-editor`}
          rows={8}
          value={scriptDraft}
          onInput={(e: Event) => setScriptDraft((e.target as HTMLTextAreaElement).value)}
          placeholder={`Phase ${phase.toUpperCase()} script…`}
        />

        {/* Audio waveform — WaveSurfer v7 timeline (LD-330 / LD-472).
            Priority: lipsync > mixed > stem (resolved by priorityAudioFile). */}
        <WaveformTimeline
          audioSrc={audioFile ? fileUrl(audioFile.name) : null}
          sourceLabel={audioFile?.label ?? null}
          sourceFilename={audioFile?.name ?? null}
          cues={stateSlice.watercolor_cues ?? []}
        />

        {/* Lipsync video player */}
        {lipsyncFile ? (
          <div class="mn-phase-lipsync" data-testid={`phase-${phase}-lipsync-player`}>
            <strong>Lipsync video:</strong>
            <video
              controls
              src={fileUrl(lipsyncFile)}
              style={{ maxHeight: '40vh', display: 'block' }}
            />
            <span class="mn-dim">{lipsyncFile}</span>
          </div>
        ) : null}

        {/* Action row: Base clip select + Send for Lipsync + Mix Audio + Export */}
        <div class="mn-phase-row">
          <label class="mn-dim" for={`phase-${phase}-baseclip`}>Base clip:</label>
          <select
            id={`phase-${phase}-baseclip`}
            data-testid={`phase-${phase}-baseclip-select`}
            value={selectedBaseClip}
            onChange={(e: Event) => setSelectedBaseClip((e.target as HTMLSelectElement).value)}
          >
            <option value="">— select —</option>
            {baseClips
              .filter((c) => phase === 'a' ? c.character === 'chipper' : c.character === 'cedric')
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id} ({c.duration_s ?? '?'}s)
                </option>
              ))}
          </select>
          <button
            type="button"
            class="mn-btn"
            data-testid={`phase-${phase}-send-lipsync-btn`}
            onClick={onSendForLipsync}
            disabled={busyAction !== null || !selectedBaseClip}
          >
            {busyAction === 'lipsync' ? 'Sending…' : 'Send for Lipsync'}
          </button>
          {phase === 'a' ? (
            <button
              type="button"
              class="mn-btn"
              data-testid={`phase-${phase}-mix-btn`}
              onClick={onMixAudio}
              disabled={busyAction !== null}
            >
              {busyAction === 'mix' ? 'Mixing…' : 'Mix Audio (auto-stitch)'}
            </button>
          ) : null}
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid={`phase-${phase}-export-btn`}
            onClick={onExportToStitcher}
            disabled={busyAction !== null}
          >
            {busyAction === 'export' ? 'Exporting…' : 'Export to Stitcher'}
          </button>
        </div>

        {/* Status line */}
        {statusMsg ? (
          <div
            class="mn-phase-status-line"
            data-testid={`phase-${phase}-status`}
          >
            {statusMsg}
          </div>
        ) : null}

        {/* Watercolor library + Animate-this */}
        <div class="mn-phase-watercolor-list" data-testid={`phase-${phase}-watercolors`}>
          <strong>Watercolors ({watercolors.length}):</strong>
          <div class="mn-phase-watercolor-grid">
            {watercolors.map((wc) => (
              <div class="mn-phase-watercolor-tile" key={wc.key}>
                <img
                  src={wc.thumb_url}
                  alt={wc.filename}
                  class="mn-phase-watercolor-thumb"
                  loading="lazy"
                />
                <span class="mn-phase-watercolor-name">{wc.key}</span>
                {wc.kind === 'animation' ? (
                  <span class="mn-phase-watercolor-anim-tag">animated</span>
                ) : null}
                <button
                  type="button"
                  class="mn-btn mn-btn-small"
                  data-testid={`phase-${phase}-animate-${wc.key}`}
                  onClick={() => onAnimateThis(wc.key)}
                  disabled={wc.kind === 'animation'}
                  title={wc.kind === 'animation' ? 'already animated' : 'open path-picker to animate'}
                >
                  {wc.kind === 'animation' ? '✓ animated' : 'Animate this'}
                </button>
              </div>
            ))}
          </div>
        </div>

        <p class="mn-readonly-banner">
          S4 wired: Suggest Script · Send for Lipsync · Mix Audio (Phase A) ·
          Export to Stitcher · Animate-this. WaveSurfer waveform + drag-drop
          watercolor onto timeline = S5 polish.
        </p>
      </div>
    </details>
  );
}
