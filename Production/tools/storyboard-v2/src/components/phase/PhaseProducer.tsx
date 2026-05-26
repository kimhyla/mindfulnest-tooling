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

import { useEffect, useRef, useState } from 'preact/hooks';
import { apiGet, pathappPatch } from '../../api/client';
import { activeScope, activeVideoRole } from '../../state/scope';
import { SERVER_BASE } from '../../api/endpoints';
import { WaveformTimeline, type WatercolorCue } from './WaveformTimeline';
import { CuePopover } from './CuePopover';

// ── Schema translation: frontend ↔ server ───────────────────────────────────
// Server (bake pipeline) expects: {id, key, timestamp_ms, animation, duration_ms, cue_type, volume}
// Frontend uses:                  {id, watercolor_key, offset_ms, duration_ms, animation_type, volume}
// Schema translation is performed server-side by _v2_validate_watercolor_cues_json so the
// client sends the raw frontend array and the validator normalises before storage.
function fromServerSchema(raw: Record<string, unknown>): WatercolorCue {
  return {
    id: String(raw['id'] ?? `cue_${Math.random().toString(36).slice(2, 10)}`),
    watercolor_key: String(raw['key'] ?? raw['watercolor_key'] ?? ''),
    offset_ms: Number(raw['timestamp_ms'] ?? raw['offset_ms'] ?? 0),
    duration_ms: Number(raw['duration_ms'] ?? 3000),
    animation_type: String(raw['animation'] ?? raw['animation_type'] ?? 'fade_in'),
    volume: Number(raw['volume'] ?? 1.0),
  };
}
import { BaseClipPicker } from './BaseClipPicker';
import { setDragData, type DragPayload } from '../../utils/dragdrop';

type PhaseAClipPosition = 'flyin' | 'sitting' | 'flyout';
const PHASE_A_CLIP_POSITIONS: ReadonlyArray<PhaseAClipPosition> = ['flyin', 'sitting', 'flyout'];
const PHASE_A_CLIP_LABELS: Record<PhaseAClipPosition, string> = {
  flyin: 'Fly-in',
  sitting: 'Sitting',
  flyout: 'Fly-out',
};

interface WatercolorItem {
  key: string;
  filename: string;
  ext: string;
  kind: 'static' | 'animation' | string;
  /** Always an image URL (static PNG or base PNG for animations) — safe for <img>. */
  thumb_url: string;
  /** For animations: the actual MP4/MOV URL (black-bg, Stitcher use only — NOT used for browser overlay per LD-821). */
  animation_url?: string | null;
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

interface AmbientPreset {
  preset_id: string;
  file_size_bytes: number;
}
interface AmbientPresetListResponse {
  ok: boolean;
  items?: AmbientPreset[];
  count?: number;
}

interface PhaseStateSlice {
  voice_stem_file?: string;
  voice_stem_mtime?: number;
  mixed_audio_file?: string;
  mixed_audio_mtime?: number;
  lipsync_file?: string;
  lipsync_mtime?: number;
  lipsync_status?: string;   // "polling" | "done" | "error: ..." from background thread
  stitched_file?: string;        // phase A only
  stitched_mtime?: number;
  script?: string;
  watercolor_cues?: WatercolorCue[];
  // Phase A only — 3-clip handling per PHASE_A_THREE_CLIP_HANDLING_V1.
  chipper_flyin_clip_id?: string;
  chipper_sitting_clip_id?: string;
  chipper_flyout_clip_id?: string;
  // S5.5f — ambient bed preset (LD AMBIENT_PRESET_SELECTOR_INPRODUCER_V1).
  ambient_preset_id?: string;
}
interface EventStateResponse {
  beats?: Record<string, unknown>;
  [key: string]: unknown;
}
/** Therapeutic brief generated server-side alongside the script suggestion.
 *  Per Kim 2026-05-25: goal = experience + clinical end; must_hits = ordered
 *  steps; what_to_evoke = internal state/feeling; watch_outs = contraindications. */
interface TherapeuticBrief {
  goal: string;
  must_hits: string[];
  what_to_evoke: string[];
  watch_outs: string[];
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
  const lst = get<string>('lipsync_status');           if (lst) slice.lipsync_status = lst;
  const st = get<string>('stitched_file');             if (st) slice.stitched_file = st;
  const stm = get<number>('stitched_mtime');           if (stm) slice.stitched_mtime = stm;
  const sc = get<string>('script');                    if (sc) slice.script = sc;
  // phase_b_watercolor_cues_json is stored on the server as a JSON STRING.
  // get<> returns it as a string (or sometimes a pre-parsed array if state
  // was written locally). Parse + translate schema in either case.
  const rawCues = get<unknown>('watercolor_cues_json');
  let cuesArr: WatercolorCue[] | undefined;
  try {
    const parsed: unknown = typeof rawCues === 'string' ? JSON.parse(rawCues)
      : Array.isArray(rawCues) ? rawCues : undefined;
    if (Array.isArray(parsed)) {
      cuesArr = (parsed as Record<string, unknown>[]).map(fromServerSchema);
    }
  } catch { /* malformed JSON — treat as no cues */ }
  if (cuesArr) slice.watercolor_cues = cuesArr;
  if (phase === 'a') {
    const fi = get<string>('chipper_flyin_clip_id');   if (fi) slice.chipper_flyin_clip_id = fi;
    const si = get<string>('chipper_sitting_clip_id'); if (si) slice.chipper_sitting_clip_id = si;
    const fo = get<string>('chipper_flyout_clip_id');  if (fo) slice.chipper_flyout_clip_id = fo;
  }
  const ap = get<string>('ambient_preset_id'); if (ap) slice.ambient_preset_id = ap;
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

// NOTE: PhaseProducer always renders its full content without collapse.
// Phase B and Phase A each own an entire tab — collapsing the full tab body
// is wrong UX. <details>/<summary> removed 2026-05-25. Do NOT re-introduce
// a collapsed-by-default wrapper here.
export function PhaseProducer({ phase }: PhaseProducerProps) {
  const [watercolors, setWatercolors] = useState<WatercolorItem[]>([]);
  const [baseClips, setBaseClips] = useState<BaseClipItem[]>([]);
  const [stateSlice, setStateSlice] = useState<PhaseStateSlice>({});
  const [scriptDraft, setScriptDraft] = useState<string>('');
  const [suggesting, setSuggesting] = useState(false);
  const [therapeuticBrief, setTherapeuticBrief] = useState<TherapeuticBrief | null>(null);
  const [showBrief, setShowBrief] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [saveBtnLabel, setSaveBtnLabel] = useState<string>('Save Script');
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [selectedBaseClip, setSelectedBaseClip] = useState<string>('');
  const [activeCueId, setActiveCueId] = useState<string | null>(null);
  const [popoverAnchor, setPopoverAnchor] = useState<{ x: number; y: number } | null>(null);
  const [pickerPosition, setPickerPosition] = useState<PhaseAClipPosition | null>(null);
  const [ambientPresets, setAmbientPresets] = useState<AmbientPreset[]>([]);
  // Playback position in ms — updated by WaveformTimeline via onTimeUpdate.
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  // True while Kling lipsync is processing in the background (202 submitted).
  const [lipsyncing, setLipsyncing] = useState(false);
  // Mtime of lipsync_file at the moment we submitted — used to detect when
  // a NEW lipsync result lands (mtime changes → job done).
  const lipsyncMtimeBefore = useRef<number | null>(null);
  // Ref to the lipsync <video> element so WaveformTimeline can sync seek/play/pause.
  // The <video> is muted; WaveSurfer owns the audio output.
  const videoRef = useRef<HTMLVideoElement>(null);

  const refreshAll = async () => {
    const [wc, bc, st, ap] = await Promise.all([
      apiGet<WatercolorListResponse>('phase_watercolor_list'),
      apiGet<BaseClipsResponse>('phase_base_clips_list'),
      apiGet<EventStateResponse>('v2_event_state', { event_id: activeScope.value.event_id }),
      apiGet<AmbientPresetListResponse>('phase_b_ambient_preset_list'),
    ]);
    if (wc.ok && wc.data?.items) {
      const next = wc.data.items as WatercolorItem[];
      setWatercolors((prev) => {
        // Skip the state swap when the library hasn't changed — prevents the
        // thumbnail blink caused by Preact reconciling a fresh-identity array
        // on every 30s lipsync poll. Compare by key+mtime (cheap; server sends
        // mtime from f.stat().st_mtime). A new animation landing changes mtime,
        // so real updates still trigger a re-render.
        if (
          prev.length === next.length &&
          prev.every((p, i) => p.key === next[i].key && p.mtime === next[i].mtime)
        ) {
          return prev; // Same reference → Preact bails out of reconcile
        }
        return next;
      });
    }
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
    if (ap.ok && ap.data?.items) setAmbientPresets(ap.data.items);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => { if (!cancelled) await refreshAll(); })();
    return () => { cancelled = true; };
  }, [activeScope.value.event_id, phase]);

  // Auto-poll every 30s while Kling lipsync is processing in background.
  useEffect(() => {
    if (!lipsyncing) return;
    const id = setInterval(async () => {
      await refreshAll();
    }, 30_000);
    return () => clearInterval(id);
  }, [lipsyncing]);

  // Detect when lipsync_mtime changes (success) OR lipsync_status = "error:…" (failure).
  useEffect(() => {
    if (!lipsyncing) return;
    // Error path: background thread wrote "error: <reason>" to state.
    const status = stateSlice.lipsync_status;
    if (status && status.startsWith('error:')) {
      setLipsyncing(false);
      setStatusMsg(`✗ Lipsync failed: ${status.replace(/^error:\s*/, '')}`);
      return;
    }
    // Success path: mtime changed → new file landed.
    const currentMtime = stateSlice.lipsync_mtime ?? null;
    const before = lipsyncMtimeBefore.current;
    if (currentMtime !== null && currentMtime !== before) {
      setLipsyncing(false);
      setStatusMsg('✓ Lipsync complete — video ready.');
    }
  }, [stateSlice.lipsync_mtime, stateSlice.lipsync_status, lipsyncing]);

  // Listen for "magic or animate complete" postMessage from path_picker.html
  // (S5 LD-468/469/470 — supersedes S4 mn:watercolor-animated).
  // Security (CodeQL js/missing-origin-check alert #2, real source line):
  // gate on e.origin === window.location.origin to refuse cross-origin
  // senders (malicious iframes / window openers).
  // MED-5: drop the falsy `e.origin &&` short-circuit so a
  // missing-Origin sender (file:// frames, certain native callers) is
  // also rejected. Strict equality only.
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      const t = e.data?.type;
      if (t === 'mn-magic-or-animate-complete' || t === 'mn:watercolor-animated') {
        refreshAll();
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [phase]);

  const onSuggest = async () => {
    setSuggesting(true);
    setStatusMsg(null);
    const res = await pathappPatch(activeScope.value, 'phase_suggest_script', { phase });
    setSuggesting(false);
    if (res.ok && res.data) {
      const data = res.data as {
        script?: string;
        therapeutic_brief?: TherapeuticBrief;
        tokens_in?: number;
        tokens_out?: number;
      };
      if (data.script) {
        setScriptDraft(data.script);
        setStatusMsg(
          `✓ Script suggested (${data.tokens_in ?? '?'} in / ${data.tokens_out ?? '?'} out tokens)`,
        );
      } else {
        setStatusMsg('Script suggestion empty — server returned no text');
      }
      if (data.therapeutic_brief) {
        setTherapeuticBrief(data.therapeutic_brief);
        setShowBrief(true);   // auto-open on first suggest
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
    // PA-9 (Phase A): lipsync MUST target the sitting clip (the talking-head
    // segment), not whatever clip happens to be in the base-clip dropdown.
    // Phase A is a 3-clip sequence (fly-in / sitting / fly-out); only the
    // sitting clip carries the dialogue audio. Per LD-375 PHASE_A_CANONICAL_PIPELINE_V1.
    // Phase B is single-clip Cedric — selectedBaseClip is the canonical target.
    const lipsyncClipId =
      phase === 'a'
        ? stateSlice.chipper_sitting_clip_id ?? selectedBaseClip
        : selectedBaseClip;
    if (!lipsyncClipId) {
      setStatusMsg(
        phase === 'a'
          ? 'Pick a sitting clip first (Phase A 3-clip picker → sitting slot).'
          : 'Pick a base clip first.',
      );
      return;
    }
    setBusyAction('lipsync');
    setStatusMsg('Sending for lipsync…');
    const lipsyncEp = phase === 'a' ? 'phase_a_lipsync' : 'phase_b_lipsync';
    const res = await pathappPatch(activeScope.value, lipsyncEp, {
      phase,
      base_clip_id: lipsyncClipId,
    });
    setBusyAction(null);
    if (res.ok) {
      if (res.status === 202) {
        // Kling is processing in the background — record mtime before submit
        // so we can detect when the new file lands, then start polling.
        lipsyncMtimeBefore.current = stateSlice.lipsync_mtime ?? null;
        setLipsyncing(true);
        setStatusMsg('⏳ Lipsync submitted — Kling processing (~1-4 min). Will auto-update when done.');
      } else {
        setStatusMsg('✓ Lipsync complete');
        await refreshAll();
      }
    } else {
      const data = res.data as { hint?: string } | undefined;
      setStatusMsg(`✗ Lipsync HTTP ${res.status}: ${data?.hint ?? res.error ?? ''}`);
    }
  };

  const onMixAudio = async () => {
    setBusyAction('mix');
    setStatusMsg('Mix Audio (Phase A auto-fires stitch)…');
    const mixEp = phase === 'a' ? 'phase_a_mix_audio' : 'phase_b_mix_audio';
    const res = await pathappPatch(activeScope.value, mixEp, { phase });
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
    // [CONFIRMED against api/endpoints.ts SERVER_BASE constant — magic_picker is co-hosted on the production_server.py origin; relative path here resolves identically to ${SERVER_BASE}/api/watercolor/animate]
    url.searchParams.set('return_endpoint', '/api/watercolor/animate');
    url.searchParams.set('scope_event_id', activeScope.value.event_id);
    // scope_video_role is required by /api/watercolor/animate (LD-474 VIDEO_ROLE_PER_REQUEST_V1).
    // path_picker.html reads it from the URL param; without it the POST returns video_role_invalid.
    url.searchParams.set('scope_video_role', activeVideoRole.value);
    window.open(url.toString(), '_blank');
  };

  // ── Watercolor cue authoring (Phase C) ──────────────────────────────────
  // All cue mutations write the FULL phase_X_watercolor_cues_json array via
  // v2_module_patch (whitelisted field; server-side _V2_MODULE_FIELD_VALIDATORS
  // checks shape). Optimistic UI: setStateSlice locally then refresh on success.
  const cueField = `phase_${phase}_watercolor_cues_json`;

  const persistCues = async (next: WatercolorCue[]) => {
    setStateSlice((s) => ({ ...s, watercolor_cues: next }));
    // Send raw frontend-schema array. The server validator (_v2_validate_watercolor_cues_json)
    // accepts a list directly, normalises to server schema, and stores as JSON string.
    // Tests F7–F9 assert body['value'] is an array with frontend keys (watercolor_key,
    // offset_ms, animation_type) — JSON.stringify was breaking that contract.
    const res = await pathappPatch(activeScope.value, 'v2_module_patch', {
      field: cueField,
      value: next,
    });
    if (!res.ok) {
      setStatusMsg(`✗ cue patch HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  const onWatercolorDrop = (lib_key: string, offset_ms: number) => {
    const newCue: WatercolorCue = {
      id: `cue_${Math.random().toString(36).slice(2, 10)}`,
      watercolor_key: lib_key,
      offset_ms,
      duration_ms: 3000,
      animation_type: 'fade_in',
      volume: 1.0,
    };
    const next = [...(stateSlice.watercolor_cues ?? []), newCue];
    void persistCues(next);
  };

  const onCueClick = (cueId: string, anchor: { x: number; y: number }) => {
    setActiveCueId(cueId);
    setPopoverAnchor(anchor);
  };

  const onCuePatch = (updated: WatercolorCue) => {
    const next = (stateSlice.watercolor_cues ?? []).map((c) =>
      c.id === updated.id ? updated : c,
    );
    void persistCues(next);
  };

  const onCueResize = (cueId: string, newDurationMs: number) => {
    const next = (stateSlice.watercolor_cues ?? []).map((c) =>
      c.id === cueId ? { ...c, duration_ms: newDurationMs } : c,
    );
    void persistCues(next);
  };

  const onCueDelete = () => {
    if (!activeCueId) return;
    const next = (stateSlice.watercolor_cues ?? []).filter((c) => c.id !== activeCueId);
    setActiveCueId(null);
    setPopoverAnchor(null);
    void persistCues(next);
  };

  const onCuePopoverClose = () => {
    setActiveCueId(null);
    setPopoverAnchor(null);
  };

  const onWatercolorDragStart = (e: DragEvent, key: string) => {
    const payload: DragPayload = {
      kind: 'lib-watercolor',
      lib_key: key,
      animation_type: 'fade_in',
    };
    setDragData(e, payload);
  };

  // ── Phase A 3-clip handling (Phase D) ──────────────────────────────────
  const phaseAClipId = (pos: PhaseAClipPosition): string | undefined => {
    if (pos === 'flyin') return stateSlice.chipper_flyin_clip_id;
    if (pos === 'sitting') return stateSlice.chipper_sitting_clip_id;
    return stateSlice.chipper_flyout_clip_id;
  };

  const onPickPhaseAClip = async (pos: PhaseAClipPosition, clipId: string) => {
    const field = `phase_a_chipper_${pos}_clip_id`;
    setPickerPosition(null);
    setStateSlice((s) => ({
      ...s,
      [`chipper_${pos}_clip_id`]: clipId,
    } as PhaseStateSlice));
    const res = await pathappPatch(activeScope.value, 'v2_module_patch', {
      field,
      value: clipId,
    });
    if (!res.ok) {
      setStatusMsg(`✗ ${field} HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  const phaseATotalDurationS = (): number => {
    let total = 0;
    for (const pos of PHASE_A_CLIP_POSITIONS) {
      const id = phaseAClipId(pos);
      const clip = baseClips.find((c) => c.id === id);
      total += clip?.duration_s ?? 0;
    }
    return total;
  };

  // ── Script persist on blur (PB-1 / PA-1) ─────────────────────────────
  // Save scriptDraft to server only when value actually changed since last
  // refresh (avoid spurious writes when user just tab-focuses the textarea).
  // Server whitelist accepts phase_a_script + phase_b_script via
  // v2_module_patch (production_server.py:4035, 4048, 4157, 4170).
  // Closes inventory v2 PB-1 + PA-1 WIRED-BUT-BROKEN class.
  const flashSaveBtn = (label: string) => {
    setSaveBtnLabel(label);
    setTimeout(() => setSaveBtnLabel('Save Script'), 2000);
  };

  const onScriptBlur = async () => {
    const currentServer = stateSlice.script ?? '';
    if (scriptDraft === currentServer) {
      flashSaveBtn('✓ Already saved');
      return;
    }
    flashSaveBtn('Saving…');
    const field = `phase_${phase}_script`;
    const res = await pathappPatch(activeScope.value, 'v2_module_patch', {
      field,
      value: scriptDraft,
    });
    if (res.ok) {
      setStateSlice((s) => ({ ...s, script: scriptDraft }));
      flashSaveBtn('✓ Saved');
      setStatusMsg('✓ Script saved');
    } else {
      flashSaveBtn(`✗ Error ${res.status}`);
      setStatusMsg(`✗ Script save HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  // ── Voice stem (Phase E) — Cursor v8 Q5: misnamed regen_audio writes voice_stem files.
  const onGenerateStem = async () => {
    setBusyAction('stem');
    // Save scriptDraft to server BEFORE generating — prevents refreshAll() from
    // overwriting the textarea with the stale server version (race: blur-save and
    // refreshAll compete; generation wins and resets scriptDraft to old script).
    const currentServer = stateSlice.script ?? '';
    if (scriptDraft !== currentServer) {
      setStatusMsg('Saving script…');
      const field = `phase_${phase}_script`;
      const saveRes = await pathappPatch(activeScope.value, 'v2_module_patch', {
        field,
        value: scriptDraft,
      });
      if (saveRes.ok) {
        setStateSlice((s) => ({ ...s, script: scriptDraft }));
      }
      // Continue even if save fails — generation uses scriptDraft directly.
    }
    setStatusMsg('Generating stem from script…');
    const regenEp = phase === 'a' ? 'phase_a_regen_audio' : 'phase_b_regen_audio';
    const res = await pathappPatch(activeScope.value, regenEp, {
      phase,
      script: scriptDraft,
    });
    setBusyAction(null);
    if (res.ok) {
      setStatusMsg('✓ Stem generated');
      await refreshAll();
      // Phase B only: auto-submit for lipsync — cedric_idle_study_v1 is already
      // auto-selected. stream_loop on the server stretches it to match audio duration.
      if (phase === 'b' && selectedBaseClip) {
        setStatusMsg('✓ Stem generated — auto-sending for lipsync…');
        await onSendForLipsync();
      }
    } else {
      setStatusMsg(`✗ Stem HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  // ── Ambient preset (Phase E) ─────────────────────────────────────────
  const onPickAmbientPreset = async (presetId: string) => {
    const field = `phase_${phase}_ambient_preset_id`;
    setStateSlice((s) => {
      const next: PhaseStateSlice = { ...s };
      if (presetId) next.ambient_preset_id = presetId;
      else delete next.ambient_preset_id;
      return next;
    });
    const res = await pathappPatch(activeScope.value, 'v2_module_patch', {
      field,
      value: presetId,
    });
    if (!res.ok) {
      setStatusMsg(`✗ ${field} HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  const audioFile = priorityAudioFile(stateSlice);
  const lipsyncFile = stateSlice.lipsync_file ?? null;
  const activeCue =
    activeCueId
      ? (stateSlice.watercolor_cues ?? []).find((c) => c.id === activeCueId) ?? null
      : null;

  return (
    <div class={`mn-phase-producer mn-phase-${phase}`} data-testid={`phase-producer-${phase}`}>
      <div class='mn-phase-status-header'>
        <span class='mn-dim mn-phase-status-tag' data-testid={`phase-${phase}-status-header`}>
          {audioFile ? `audio: ${audioFile.label}` : 'no audio yet'}
          {lipsyncFile ? ' · lipsync ✓' : ''}
        </span>
      </div>

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
          {therapeuticBrief && (
            <button
              type="button"
              class={`mn-btn mn-brief-toggle-btn${showBrief ? ' mn-brief-toggle-btn--active' : ''}`}
              data-testid={`phase-${phase}-brief-toggle-btn`}
              onClick={() => setShowBrief(v => !v)}
              title="Toggle therapeutic brief"
            >
              📋 {showBrief ? 'Hide Brief' : 'Brief'}
            </button>
          )}
          <span class="mn-dim">
            {phase === 'a' ? 'reads Phase B + module context' : 'reads arc skeleton + therapeutic'}
          </span>
        </div>
        {/* Therapeutic brief panel — persists in state, toggled by 📋 button */}
        {therapeuticBrief && showBrief && (
          <div class="mn-brief-panel" data-testid={`phase-${phase}-brief-panel`}>
            <div class="mn-brief-section">
              <span class="mn-brief-title">🎯 Therapeutic goal</span>
              <p class="mn-brief-goal">{therapeuticBrief.goal}</p>
            </div>
            <div class="mn-brief-section">
              <span class="mn-brief-title">✅ Must-hits</span>
              <ul class="mn-brief-list">
                {therapeuticBrief.must_hits.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
            <div class="mn-brief-section">
              <span class="mn-brief-title">💡 What to evoke</span>
              <ul class="mn-brief-list">
                {therapeuticBrief.what_to_evoke.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
            <div class="mn-brief-section">
              <span class="mn-brief-title">⚠️ Watch-outs</span>
              <ul class="mn-brief-list">
                {therapeuticBrief.watch_outs.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
        <textarea
          class="mn-phase-script-editor"
          data-testid={`phase-${phase}-script-editor`}
          rows={8}
          value={scriptDraft}
          onInput={(e: Event) => setScriptDraft((e.target as HTMLTextAreaElement).value)}
          onBlur={onScriptBlur}
          placeholder={`Phase ${phase.toUpperCase()} script…`}
        />
        {/* Explicit save — onBlur only fires on focus-leave; this lets Kim
            paste a script and commit it without clicking elsewhere.
            Button label self-reports: Saving… → ✓ Saved / ✗ Error / ✓ Already saved */}
        <div class="mn-phase-row">
          <button
            type="button"
            class="mn-btn"
            data-testid={`phase-${phase}-save-script-btn`}
            onClick={onScriptBlur}
            disabled={saveBtnLabel === 'Saving…'}
          >
            {saveBtnLabel}
          </button>
        </div>

        {/* Audio waveform — WaveSurfer v7 timeline (LD-330 / LD-472).
            Priority: lipsync > mixed > stem (resolved by priorityAudioFile). */}
        <WaveformTimeline
          audioSrc={audioFile ? fileUrl(audioFile.name) : null}
          sourceLabel={audioFile?.label ?? null}
          sourceFilename={audioFile?.name ?? null}
          cues={stateSlice.watercolor_cues ?? []}
          onCueClick={onCueClick}
          onWatercolorDrop={onWatercolorDrop}
          onTimeUpdate={(ms) => setCurrentTimeMs(ms)}
          onCueResize={onCueResize}
          linkedVideo={videoRef}
        />
        {activeCue && popoverAnchor ? (
          <CuePopover
            cue={activeCue}
            anchor={popoverAnchor}
            onPatch={onCuePatch}
            onDelete={onCueDelete}
            onClose={onCuePopoverClose}
          />
        ) : null}

        {/* S5.5f Phase E — Voice stem (Generate-from-script) + Ambient preset.
            File-upload UI is OUT OF SCOPE per spec §3.6 + Cursor v8 Q5;
            'Generate stem' calls the misnamed but real /api/phase_b/regen_audio
            handler which writes phase_<a|b>_voice_stem_*.mp3 server-side. */}
        <div class="mn-phase-stem-row">
          <button
            type="button"
            class="mn-btn"
            data-testid={`phase-${phase}-generate-stem-btn`}
            onClick={onGenerateStem}
            disabled={busyAction !== null}
            title="POST /api/phase_b/regen_audio with phase + script"
          >
            {busyAction === 'stem' ? 'Generating…' : 'Generate stem from script'}
          </button>
          <span class="mn-dim">writes phase_{phase}_voice_stem_*.mp3</span>
        </div>

        <div class="mn-phase-ambient-section">
          <label class="mn-dim" for={`phase-${phase}-ambient`}>Ambient bed:</label>
          <select
            id={`phase-${phase}-ambient`}
            data-testid={`phase-${phase}-ambient-preset-select`}
            value={stateSlice.ambient_preset_id ?? ''}
            onChange={(e: Event) =>
              void onPickAmbientPreset((e.target as HTMLSelectElement).value)
            }
          >
            <option value="">— none —</option>
            {ambientPresets.map((p) => (
              <option key={p.preset_id} value={p.preset_id}>
                {p.preset_id}
              </option>
            ))}
          </select>
          {ambientPresets.length === 0 ? (
            <span class="mn-dim">no presets in audio_library/ambient/</span>
          ) : null}
        </div>

        {/* Lipsync video player — shows approved video after Send for Lipsync completes.
            Muted: WaveSurfer (above) owns audio playback and is the master clock.
            videoRef is passed to WaveformTimeline as linkedVideo so seek/play/pause
            from the waveform drive the video position — this is how watercolor cue
            placement timestamps (offset_ms) map to visible video frames. */}
        <div class="mn-phase-lipsync" data-testid={`phase-${phase}-lipsync-player`}>
          {lipsyncFile ? (
            <>
              <strong>Lipsync video:</strong>
              <div class="mn-lipsync-video-wrapper">
                {/* muted: WaveSurfer owns audio. controls REMOVED intentionally:
                  native controls let Kim pause video without WaveSurfer knowing → desync.
                  WaveformTimeline ⏸/▶ is the single control point. */}
              <video
                  ref={videoRef}
                  muted
                  src={fileUrl(lipsyncFile)}
                  style={{ maxHeight: '20vh', display: 'block' }}
                />
                {(stateSlice.watercolor_cues ?? [])
                  .filter(
                    (cue) =>
                      currentTimeMs >= cue.offset_ms &&
                      currentTimeMs < cue.offset_ms + (cue.duration_ms ?? 3000),
                  )
                  .map((cue) => {
                    // PNG+JS-opacity overlay (LD-821 WATERCOLOR_OVERLAY_PNG_CSS_ARCHITECTURE_V1).
                    // We use the source PNG (not the MP4) so there is no black-background /
                    // mix-blend-mode hack. The server's thumb_url already resolves animated keys
                    // to their base PNG — no new endpoint needed.
                    const wcItem = watercolors.find((w) => w.key === cue.watercolor_key);
                    // Resolve PNG source: prefer server-provided thumb_url (handles animated→base
                    // resolution server-side). Fallback to direct watercolor endpoint for any cue
                    // whose key isn't yet in the loaded list (e.g. freshly animated, list not
                    // yet refreshed).
                    const pngSrc =
                      wcItem?.thumb_url ??
                      `${SERVER_BASE}/api/phase_b/watercolor/${encodeURIComponent(cue.watercolor_key)}`;

                    // JS-computed opacity: fade-in 500ms, hold, fade-out 600ms.
                    // currentTimeMs updates ~100ms via audioprocess — smooth enough for a fade.
                    const elapsed = currentTimeMs - cue.offset_ms;
                    const FADE_IN_MS = 500;
                    const FADE_OUT_MS = 600;
                    const MAX_OPACITY = 0.88;
                    let opacity: number;
                    if (elapsed < FADE_IN_MS) {
                      opacity = (elapsed / FADE_IN_MS) * MAX_OPACITY;
                    } else if (elapsed > (cue.duration_ms ?? 3000) - FADE_OUT_MS) {
                      opacity = Math.max(0, (((cue.duration_ms ?? 3000) - elapsed) / FADE_OUT_MS) * MAX_OPACITY);
                    } else {
                      opacity = MAX_OPACITY;
                    }

                    return (
                      <img
                        key={cue.id}
                        class="mn-lipsync-watercolor-overlay"
                        src={pngSrc}
                        alt=""
                        style={{ opacity, mixBlendMode: 'multiply' as const }}
                      />
                    );
                  })}
              </div>
              <span class="mn-dim">{lipsyncFile}</span>
            </>
          ) : (
            <div class="mn-phase-lipsync-placeholder mn-dim" data-testid={`phase-${phase}-lipsync-placeholder`}>
              Lipsync video will appear here after "Send for Lipsync" completes.
            </div>
          )}
        </div>

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

        {/* Phase A 3-clip section — only when phase==='a' (LD PHASE_A_THREE_CLIP_HANDLING_V1).
            Phase B is single-clip via the existing baseclip select above. */}
        {phase === 'a' ? (
          <div class="mn-phase-a-clip-section" data-testid="phase-a-clip-section">
            <strong>Phase A clips</strong>
            <div class="mn-phase-a-clip-grid">
              {PHASE_A_CLIP_POSITIONS.map((pos) => {
                const id = phaseAClipId(pos);
                const clip = baseClips.find((c) => c.id === id);
                return (
                  <div
                    key={pos}
                    class="mn-phase-a-clip-slot"
                    data-testid={`phase-a-clip-slot-${pos}`}
                    data-clip-id={id ?? ''}
                  >
                    <div class="mn-phase-a-clip-label">{PHASE_A_CLIP_LABELS[pos]}</div>
                    <div class="mn-phase-a-clip-meta mn-dim">
                      {clip ? `${clip.id} (${clip.duration_s ?? '?'}s)` : 'no clip'}
                    </div>
                    <button
                      type="button"
                      class="mn-btn mn-btn-small"
                      data-testid={`phase-a-clip-pick-${pos}`}
                      onClick={() => setPickerPosition(pos)}
                    >
                      Pick clip
                    </button>
                  </div>
                );
              })}
            </div>
            <div class="mn-phase-a-clip-total mn-dim">
              Total: {phaseATotalDurationS().toFixed(1)}s
            </div>
            <button
              type="button"
              class="mn-btn"
              data-testid="phase-a-restitch-btn"
              onClick={onMixAudio}
              disabled={busyAction !== null}
              title="Re-stitch fly-in / sitting / fly-out into phase_a_stitched_file"
            >
              {busyAction === 'mix' ? 'Re-stitching…' : 'Re-stitch (Phase A)'}
            </button>
            <BaseClipPicker
              open={pickerPosition !== null}
              positionLabel={pickerPosition ? PHASE_A_CLIP_LABELS[pickerPosition] : ''}
              character="chipper"
              clips={baseClips}
              onPick={(id) => {
                if (pickerPosition) void onPickPhaseAClip(pickerPosition, id);
              }}
              onClose={() => setPickerPosition(null)}
            />
          </div>
        ) : null}

        {/* Watercolor library + Animate-this */}
        <div class="mn-phase-watercolor-list" data-testid={`phase-${phase}-watercolors`}>
          <strong>Watercolors ({watercolors.length}):</strong>
          <div class="mn-phase-watercolor-grid">
            {watercolors.map((wc) => (
              <div
                class="mn-phase-watercolor-tile"
                key={wc.key}
                data-testid={`phase-${phase}-watercolor-tile-${wc.key}`}
                draggable
                onDragStart={(e: DragEvent) => onWatercolorDragStart(e, wc.key)}
              >
                {/* LD-203 — white interior wraps the centered art. */}
                <div class="mn-phase-watercolor-thumb-wrap">
                  {/* thumb_url is always a static PNG image (server resolves base PNG for animations).
                      This avoids the black-first-frame problem with animation MP4s in thumbnails. */}
                  <img
                    src={wc.thumb_url}
                    alt={wc.filename}
                    class="mn-phase-watercolor-thumb"
                    loading="lazy"
                  />
                </div>
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
    </div>
  );
}
