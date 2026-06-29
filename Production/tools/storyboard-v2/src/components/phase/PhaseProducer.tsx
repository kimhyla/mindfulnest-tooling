// PhaseProducer — shared base for Phase A + Phase B producers.
// Per LD-462 PHASE_A_PRODUCER_V1 + LD-463 PHASE_B_PRODUCER_V1.
//
// ── DURABILITY RULES (PHASE_PRODUCER_AB_V1 — do not regress, 2026-06-12) ────
// Single component serves BOTH tabs. Enforced by verify_phase_producer_durability.sh
// + e2e/phase_waveform_playback.spec.ts (Phase A + B sections).
//
// Symptom fixes (all shared — never fork phase-a-only / phase-b-only playback UI):
//   OVERLAY-1  Gigantic overlays → app.css inline-block video wrapper + 35% bbox
//   OVERLAY-2  Pink frame on anim → WatercolorAnimOverlay canvas chromakey (not <video>)
//   OVERLAY-3  Still / frozen anim → loop MP4 + onPlayStateChange wave sync
//   PLAY-*     ▶/⏸, ghost audio, seek jump → WaveformTimeline + waveformPlaybackBus
//   STEM-*     Amber cut rectangle → WaveformTimeline stem cut (both phases)
//
// Preview with Overlay → waveform play from start on lipsync frame (same surface).
// Export to Stitcher → server ffmpeg bake (chromakey + stream_loop).
// ─────────────────────────────────────────────────────────────────────────────
//
// S4 SCOPE (this file): real producer UX — script editor, audio player
// (priority lipsync > mixed > stem), Send for Lipsync, lipsync video
// player, Export to Stitcher. Phase A: dry lipsync only — ambient in Stitcher.
// Stitcher, watercolor library + Animate-this. All wired through
// pathappPatch (snapshot + scope-guard + 409/423 handling).
//
// HONEST S5 DEFERRED: WaveSurfer.js v7 waveform display + click-to-drop
// watercolor onto timeline + cue popover with animation/duration/Delete.
// The button-based flow ships in S4; Kim can use it end-to-end now;
// timeline-as-direct-manipulation lands in S5.

import { useEffect, useRef, useState } from 'preact/hooks';
import { apiGet, pathappPatch } from '../../api/client';
import { activeScope, activeVideoRole, activeProjectType, activeMilestoneId } from '../../state/scope';
import { SERVER_BASE } from '../../api/endpoints';
import { stitcherRefreshTick } from '../../app';
import { writePersistedTrackSlot } from '../../utils/stitchTrackFocus';
import { stitchJobSessionKey } from '../../state/producerSessionKeys';
import {
  notifyStitchSlotExportApplied,
  stitchExportKeptExistingWarning,
} from '../../utils/stitchSlotVideoLineage';
import { serverRehydrateTick } from '../../state/refreshSignals';
import { SERVER_REHYDRATE_EVENT } from '../../state/serverRehydrate';
import { usePhaseWatercolorCues } from '../../hooks/usePhaseWatercolorCues';
import { usePhaseStemCut } from '../../hooks/usePhaseStemCut';
import { useProtectedPromptField } from '../../hooks/useProtectedPromptField';
import { WaveformTimeline, type WatercolorCue, type WaveformPlaybackControl } from './WaveformTimeline';
import { WatercolorAnimOverlay } from './WatercolorAnimOverlay';
import { CuePopover } from './CuePopover';
import {
  phaseLipsyncJobBusy,
  phaseLipsyncProgressMessage,
  phaseLipsyncTerminalBanner,
} from '../../phaseLipsyncJobContract';
import {
  coercePhaseBCedricBaseClipId,
  PHASE_B_CEDRIC_BASE_CLIP_CANONICAL,
} from '../../phaseBCedricContract';
import {
  coercePhaseAArloBaseClipId,
  PHASE_A_ARLO_AVATAR_STILL_LABEL,
  PHASE_A_ARLO_BASE_CLIP_CANONICAL,
} from '../../phaseAArloContract';
import { phaseWatercolorOverlayCssVars } from './phaseWatercolorOverlayGeometry';
import { PLAYBACK_VIDEO_ANTI_BANDING_CLASS, linkedMediaSameFilename } from '../../utils/playbackVideoPolicy';
import { watercolorFileUrl, watercolorOverlaySrc } from '../../utils/watercolorAssets';

// Schema translation for non-cue phase fields lives in pickPhaseSlice.
// Watercolor cues: PHASE_WATERCOLOR_CUE_AUTHORITY_V1 — usePhaseWatercolorCues hook.
import { BaseClipPicker } from './BaseClipPicker';
import { setDragData, type DragPayload } from '../../utils/dragdrop';

type PhaseAClipPosition = 'sitting';
const PHASE_A_CLIP_POSITIONS: ReadonlyArray<PhaseAClipPosition> = ['sitting'];
const PHASE_A_CLIP_LABELS: Record<PhaseAClipPosition, string> = {
  sitting: 'Arlo base (talking)',
};

interface WatercolorItem {
  key: string;
  filename: string;
  ext: string;
  kind: 'static' | 'animation' | string;
  /** Always an image URL (static PNG or base PNG for animation tiles) — safe for <img>. */
  thumb_url: string;
  /** For animations: MP4/MOV URL — used by server Preview with Overlay / Stitcher (not raw browser overlay). */
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
  lipsync_status?: string;
  lipsync_task_id?: string;
  lipsync_requires_regen?: boolean;
  voice_stem_cut_start_s?: number;
  voice_stem_cut_end_s?: number;
  /** @deprecated Legacy keep-region keys — ignored when cut keys present. */
  voice_stem_trim_start_s?: number;
  voice_stem_trim_back_s?: number;
  flyin_flyout_status?: string;
  stitched_file?: string;        // phase A only
  stitched_mtime?: number;
  script?: string;
  /** @deprecated Cues owned by usePhaseWatercolorCues — not hydrated via pickPhaseSlice. */
  watercolor_cues?: WatercolorCue[];
  // Phase A only — 3-clip handling per PHASE_A_THREE_CLIP_HANDLING_V1.
  chipper_flyin_clip_id?: string;
  chipper_sitting_clip_id?: string;
  chipper_flyout_clip_id?: string;
  /** Phase B — persisted lipsync base clip (phase_b_cedric_base_clip_id). */
  cedric_base_clip_id?: string;
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
  const lstid = get<string>('lipsync_task_id');        if (lstid) slice.lipsync_task_id = lstid;
  const lrr = get<boolean>('lipsync_requires_regen');  if (lrr) slice.lipsync_requires_regen = lrr;
  const tcs = get<number>('voice_stem_cut_start_s'); if (tcs !== undefined) slice.voice_stem_cut_start_s = tcs;
  const tce = get<number>('voice_stem_cut_end_s');   if (tce !== undefined) slice.voice_stem_cut_end_s = tce;
  const tss = get<number>('voice_stem_trim_start_s'); if (tss !== undefined) slice.voice_stem_trim_start_s = tss;
  const tsb = get<number>('voice_stem_trim_back_s');  if (tsb !== undefined) slice.voice_stem_trim_back_s = tsb;
  const ffst = get<string>('flyin_flyout_status');     if (ffst) slice.flyin_flyout_status = ffst;
  const st = get<string>('stitched_file');             if (st) slice.stitched_file = st;
  const stm = get<number>('stitched_mtime');           if (stm) slice.stitched_mtime = stm;
  const sc = get<string>('script');                    if (sc) slice.script = sc;
  if (phase === 'a') {
    const fi = get<string>('chipper_flyin_clip_id');   if (fi) slice.chipper_flyin_clip_id = fi;
    const si = get<string>('chipper_sitting_clip_id');
    if (si) slice.chipper_sitting_clip_id = coercePhaseAArloBaseClipId(si);
    const fo = get<string>('chipper_flyout_clip_id');  if (fo) slice.chipper_flyout_clip_id = fo;
  }
  if (phase === 'b') {
    const bci = get<string>('cedric_base_clip_id');
    slice.cedric_base_clip_id = coercePhaseBCedricBaseClipId(bci);
  }
  const ap = get<string>('ambient_preset_id'); if (ap) slice.ambient_preset_id = ap;
  return slice;
}

type AudioSourceLabel = 'lipsync' | 'mixed' | 'stem' | 'stitched';

type PhasePreviewFile = {
  name: string;
  label: AudioSourceLabel;
  kind: 'stitched' | 'lipsync';
};

function priorityAudioFile(
  slice: PhaseStateSlice,
): { name: string; label: AudioSourceLabel } | null {
  const stemMtime = slice.voice_stem_mtime ?? 0;
  const lipsyncMtime = slice.lipsync_mtime ?? 0;
  const lipsyncStale =
    Boolean(slice.lipsync_requires_regen) ||
    (slice.lipsync_status?.startsWith('error:') ?? false) ||
    (slice.lipsync_status === 'qa_failed') ||
    (stemMtime > 0 && lipsyncMtime > 0 && stemMtime > lipsyncMtime);

  // After stem regen, audition the fresh stem — not audio extracted from stale lipsync.
  if (slice.voice_stem_file && lipsyncStale) {
    return { name: slice.voice_stem_file, label: 'stem' };
  }
  if (slice.lipsync_file && !lipsyncStale) {
    return { name: slice.lipsync_file, label: 'lipsync' };
  }
  if (slice.mixed_audio_file) return { name: slice.mixed_audio_file, label: 'mixed' };
  if (slice.voice_stem_file) return { name: slice.voice_stem_file, label: 'stem' };
  if (slice.lipsync_file) return { name: slice.lipsync_file, label: 'lipsync' };
  return null;
}

/** Phase A LD-829 — fresh stitched is canonical for waveform + player; Phase B stays lipsync-first. */
function priorityAudioFileForPhase(
  slice: PhaseStateSlice,
  phase: 'a' | 'b',
): { name: string; label: AudioSourceLabel } | null {
  if (phase === 'a' && slice.stitched_file && !stitchedPreviewStale(slice)) {
    return { name: slice.stitched_file, label: 'stitched' };
  }
  return priorityAudioFile(slice);
}

function stitchedPreviewStale(slice: PhaseStateSlice): boolean {
  if (!slice.stitched_file) return false;
  const lm = slice.lipsync_mtime ?? 0;
  const sm = slice.stitched_mtime ?? 0;
  return lm > 0 && (sm === 0 || lm > sm);
}

/** Phase A canonical player: stitched when fresh, else lipsync while producing. */
function phaseAPreviewFile(slice: PhaseStateSlice): PhasePreviewFile | null {
  if (slice.stitched_file && !stitchedPreviewStale(slice)) {
    return { name: slice.stitched_file, label: 'stitched', kind: 'stitched' };
  }
  if (slice.lipsync_file) {
    return { name: slice.lipsync_file, label: 'lipsync', kind: 'lipsync' };
  }
  return null;
}

// ─────────────────────────────────────────────────────────────────────────

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
  // WaveSurfer play state — drives animated overlay loop + canvas redraw.
  const [waveIsPlaying, setWaveIsPlaying] = useState(false);
  // Ref to the lipsync <video> element so WaveformTimeline can sync seek/play/pause.
  // The <video> is muted; WaveSurfer owns the audio output.
  const videoRef = useRef<HTMLVideoElement>(null);
  const waveformPlaybackRef = useRef<WaveformPlaybackControl | null>(null);
  const wcUploadInputRef = useRef<HTMLInputElement>(null);
  // User toggled "Trim voice stem" — show stem on waveform + amber cut handles even
  // when a lipsync file would otherwise win audio priority.
  const [stemTrimMode, setStemTrimMode] = useState(false);

  const watercolorCues = usePhaseWatercolorCues({
    phase,
    scope: activeScope.value,
    watercolors,
    onPatchError: setStatusMsg,
  });

  const scriptField = useProtectedPromptField({
    fieldId: `phase_${phase}_script_${activeScope.value.event_id}`,
    externalText: stateSlice.script ?? '',
    onSave: async (text) => {
      const field = `phase_${phase}_script`;
      const res = await pathappPatch(activeScope.value, 'v2_module_patch', {
        field,
        value: text,
      });
      if (res.ok) {
        setStateSlice((s) => ({ ...s, script: text }));
      }
      return res.ok;
    },
  });

  const stemCut = usePhaseStemCut({
    phase,
    scope: activeScope.value,
    onPatchError: setStatusMsg,
  });

  const refreshAll = async (): Promise<boolean> => {
    const [wc, bc, st, ap] = await Promise.all([
      apiGet<WatercolorListResponse>('phase_watercolor_list'),
      apiGet<BaseClipsResponse>('phase_base_clips_list'),
      apiGet<EventStateResponse>('v2_event_state', { event_id: activeScope.value.event_id }),
      apiGet<AmbientPresetListResponse>('phase_b_ambient_preset_list'),
    ]);
    let nextSlice = stateSlice;
    if (st.ok && st.data) {
      nextSlice = pickPhaseSlice(st.data, phase);
      watercolorCues.adoptFromEventState(st.data);
      stemCut.adoptFromEventState(st.data);
      setStateSlice(nextSlice);
    } else if (!st.ok) {
      setStatusMsg(
        `⚠ Could not load Phase ${phase.toUpperCase()} state (HTTP ${st.status || 'network'}). `
        + 'Tabs refresh automatically when the server is back.',
      );
    }
    if (wc.ok && wc.data?.items) {
      const next = wc.data.items as WatercolorItem[];
      setWatercolors((prev) => {
        if (
          prev.length === next.length &&
          prev.every((p, i) => p.key === next[i].key && p.mtime === next[i].mtime)
        ) {
          return prev;
        }
        return next;
      });
    }
    if (bc.ok && bc.data?.items) {
      setBaseClips(bc.data.items);
      const phaseAChars = new Set(['arlo', 'chipper']);
      const wantedChar = phase === 'a' ? 'arlo' : 'cedric';
      const sittingId = phase === 'a'
        ? coercePhaseAArloBaseClipId(
            nextSlice.chipper_sitting_clip_id ?? PHASE_A_ARLO_BASE_CLIP_CANONICAL,
          )
        : undefined;
      const savedBaseClipId =
        phase === 'b'
          ? coercePhaseBCedricBaseClipId(
              nextSlice.cedric_base_clip_id ?? PHASE_B_CEDRIC_BASE_CLIP_CANONICAL,
            )
          : sittingId;
      const bySaved = savedBaseClipId
        ? bc.data.items.find((c) => c.id === savedBaseClipId)
        : undefined;
      const bySitting = sittingId
        ? bc.data.items.find((c) => c.id === sittingId)
        : undefined;
      const match = bySaved
        ?? bySitting
        ?? bc.data.items.find((c) => c.character === wantedChar)
        ?? bc.data.items.find((c) => c.character && phaseAChars.has(c.character));
      if (match) setSelectedBaseClip(match.id);
    }
    if (ap.ok && ap.data?.items) {
      setAmbientPresets(ap.data.items);
    }
    const hydrated = Boolean(st.ok && st.data);
    if (hydrated) {
      setStatusMsg((prev) => (
        prev?.startsWith('⚠ Could not load Phase') ? null : prev
      ));
    }
    return hydrated;
  };

  useEffect(() => {
    let cancelled = false;
    (async () => { if (!cancelled) await refreshAll(); })();
    return () => { cancelled = true; };
  }, [activeScope.value.event_id, phase, serverRehydrateTick.value]);

  useEffect(() => {
    const onRehydrate = () => { void refreshAll(); };
    window.addEventListener(SERVER_REHYDRATE_EVENT, onRehydrate);
    return () => window.removeEventListener(SERVER_REHYDRATE_EVENT, onRehydrate);
  }, [activeScope.value.event_id, phase]);

  useEffect(() => {
    const retry = () => { void refreshAll(); };
    window.addEventListener('focus', retry);
    document.addEventListener('visibilitychange', retry);
    return () => {
      window.removeEventListener('focus', retry);
      document.removeEventListener('visibilitychange', retry);
    };
  }, [activeScope.value.event_id, phase]);

  const lipsyncInFlight = phaseLipsyncJobBusy(
    stateSlice.lipsync_status,
    stateSlice.lipsync_task_id,
  );

  // Poll while server reports in-flight — survives tab unmount/remount.
  useEffect(() => {
    if (!lipsyncInFlight) return;
    void refreshAll();
    const id = setInterval(() => {
      void refreshAll();
    }, 15_000);
    return () => clearInterval(id);
  }, [lipsyncInFlight, activeScope.value.event_id, phase]);

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
        // RC1 fix: after animation completes, update any existing cue that used
        // the original static key to point at the new animated key, THEN refresh.
        const result = (e.data?.payload?.result ?? {}) as {
          watercolor_key?: string;  // original static key (e.g. "hands_rubbing")
          animated_path?: string;   // full server path to new MP4
        };
        const originalKey = result.watercolor_key ?? null;
        const animatedKey = result.animated_path
          ? result.animated_path.split('/').pop()?.replace(/\.[^.]+$/, '') ?? null
          : null;
        void (async () => {
          if (originalKey && animatedKey) {
            await watercolorCues.remapWatercolorKey(originalKey, animatedKey);
          }
          await refreshAll();
        })();
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
        scriptField.setText(data.script);
        setStateSlice((s) => ({ ...s, script: data.script! }));
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
    // Phase A + B: Avatar Pro — canonical still + voice stem (no base-clip loop).
    if (!stateSlice.voice_stem_file) {
      setStatusMsg(`Generate a Phase ${phase.toUpperCase()} voice stem first (Regen Audio).`);
      return;
    }
    setBusyAction('lipsync');
    setStatusMsg('Sending for Avatar Pro lipsync…');
    const lipsyncEp = phase === 'a' ? 'phase_a_lipsync' : 'phase_b_lipsync';
    const res = await pathappPatch(activeScope.value, lipsyncEp, { phase }, { fetchTimeoutMs: 180_000 });
    setBusyAction(null);
    if (res.ok) {
      if (res.status === 202) {
        await refreshAll();
        setStatusMsg(phaseLipsyncProgressMessage(phase));
      } else {
        setStatusMsg('✓ Lipsync complete');
        await refreshAll();
      }
    } else if (
      res.status === 409 &&
      (res.error_code === 'PHASE_A_LIPSYNC_RUNNING' ||
        res.error_code === 'PHASE_LIPSYNC_RUNNING' ||
        res.error_message?.includes('already running') ||
        (res.data as { error_code?: string; error_message?: string } | undefined)?.error_code ===
          'PHASE_A_LIPSYNC_RUNNING' ||
        (res.data as { error_message?: string } | undefined)?.error_message?.includes('already running'))
    ) {
      await refreshAll();
      setStatusMsg(phaseLipsyncProgressMessage(phase));
    } else if (res.error_code === 'CLIENT_BUNDLE_STALE') {
      setStatusMsg(
        `✗ ${res.error ?? 'Storyboard updated — hard refresh (Cmd+Shift+R), then Send for Avatar Pro again.'}`,
      );
    } else {
      const data = res.data as { hint?: string; error_message?: string } | undefined;
      setStatusMsg(
        `✗ Lipsync HTTP ${res.status}: ${data?.hint ?? data?.error_message ?? res.error ?? ''}`,
      );
    }
  };

  const onEnterStemTrimMode = () => {
    if (!stateSlice.voice_stem_file) {
      setStatusMsg('Generate a voice stem first.');
      return;
    }
    setStemTrimMode(true);
    setStatusMsg(
      '✂ Trim mode — gold handles on the waveform. Amber = section to REMOVE. Drag handles, then Apply Cut.',
    );
  };

  const onExitStemTrimMode = () => {
    setStemTrimMode(false);
    setStatusMsg(
      lipsyncFile
        ? 'Trim mode off — waveform shows lipsync audio again.'
        : 'Trim mode off.',
    );
  };

  const onClearStemCutSelection = async () => {
    setBusyAction('clear_cut');
    await stemCut.persistStemCut(0, 0);
    setBusyAction(null);
    setStatusMsg('Cut selection cleared — drag gold handles to mark a new region.');
  };

  const onApplyStemCut = async () => {
    const cutStart = stemCut.stemCutStartMs;
    const cutEnd = stemCut.stemCutEndMs;
    if (cutEnd <= cutStart + 250) {
      setStatusMsg('Drag the amber handles to mark the section to remove, then Apply Cut.');
      return;
    }
    setBusyAction('apply_cut');
    setStatusMsg('Applying stem cut (ffmpeg)…');
    const cutEp = phase === 'a' ? 'phase_a_apply_stem_cut' : 'phase_b_apply_stem_cut';
    const res = await pathappPatch(activeScope.value, cutEp, { phase });
    setBusyAction(null);
    if (res.ok) {
      const data = res.data as { file?: string; duration_s?: number } | undefined;
      setStatusMsg(
        `✓ Stem cut applied${data?.duration_s ? ` (${data.duration_s.toFixed(1)}s)` : ''} — send for lipsync when ready.`,
      );
      setStemTrimMode(false);
      stemCut.clearLocalCut();
      await refreshAll();
    } else {
      const data = res.data as { hint?: string; error_message?: string } | undefined;
      setStatusMsg(
        `✗ Apply Cut HTTP ${res.status}: ${data?.hint ?? data?.error_message ?? res.error ?? ''}`,
      );
    }
  };

  const onRejectLipsync = async () => {
    setBusyAction('reject_lipsync');
    setStatusMsg('Rejecting lipsync…');
    const rejectEp = phase === 'a' ? 'phase_a_reject_lipsync' : 'phase_b_reject_lipsync';
    const res = await pathappPatch(activeScope.value, rejectEp, { phase });
    setBusyAction(null);
    if (res.ok) {
      setStatusMsg('✓ Lipsync rejected — stem on waveform; drag amber handles to trim before resending.');
      await refreshAll();
    } else {
      const data = res.data as { hint?: string; error_message?: string } | undefined;
      setStatusMsg(
        `✗ Reject lipsync HTTP ${res.status}: ${data?.hint ?? data?.error_message ?? res.error ?? ''}`,
      );
    }
  };

  const onMixAudio = async () => {
    if (phase !== 'b') return;
    const presetId = stateSlice.ambient_preset_id?.trim();
    if (!presetId) {
      setStatusMsg('✗ Pick an ambient bed preset first (dropdown above).');
      return;
    }
    setBusyAction('mix');
    setStatusMsg('Mix Audio…');
    const res = await pathappPatch(activeScope.value, 'phase_b_mix_audio', {
      phase: 'b',
      ambient_preset_id: presetId,
    });
    setBusyAction(null);
    if (res.ok) {
      setStatusMsg('✓ Mix complete');
      await refreshAll();
    } else {
      setStatusMsg(`✗ Mix HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  const onPhaseARestitch = async () => {
    setBusyAction('restitch');
    setStatusMsg('Normalizing lipsync for export preview…');
    const res = await pathappPatch(activeScope.value, 'phase_a_restitch', {});
    setBusyAction(null);
    if (res.ok) {
      setStatusMsg('✓ Phase A normalized (dry — ambient added in Stitcher)');
      await refreshAll();
    } else {
      setStatusMsg(`✗ Restitch HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  const onRegenBaseClip = async () => {
    setBusyAction('regen_base');
    setStatusMsg('Kling idle base clip (~6 min)…');
    const res = await pathappPatch(activeScope.value, 'phase_a_regen_base_clip', {
      clip_id: stateSlice.chipper_sitting_clip_id ?? selectedBaseClip ?? PHASE_A_ARLO_BASE_CLIP_CANONICAL,
    });
    setBusyAction(null);
    if (res.ok && res.status === 202) {
      setStatusMsg('⏳ Base clip regenerating — Send for Avatar Pro when done');
    } else if (res.ok) {
      setStatusMsg('✓ Base clip regen complete');
      await refreshAll();
    } else {
      setStatusMsg(`✗ Base clip HTTP ${res.status}: ${res.error ?? ''}`);
    }
  };

  // ── Preview with Overlay ─────────────────────────────────────────────────
  // One surface: lipsync frame + canvas-chromakey animated overlays on cue timing.
  const onPreviewOverlay = () => {
    const overlayVideo =
      phase === 'a'
        ? phaseAPreviewFile(stateSlice)
        : lipsyncFile
          ? { name: lipsyncFile, label: 'lipsync' as const, kind: 'lipsync' as const }
          : null;
    if (!overlayVideo) {
      setStatusMsg('No preview video yet — run Send for Avatar Pro first.');
      return;
    }
    if (!priorityAudio) {
      setStatusMsg('No audio on timeline — generate a stem or finish lipsync first.');
      return;
    }
    document
      .querySelector(`[data-testid="phase-${phase}-lipsync-player"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    const ctl = waveformPlaybackRef.current;
    if (!ctl?.isReady) {
      setStatusMsg('Audio waveform still loading — wait a moment and try again.');
      return;
    }
    if (!ctl.play({ fromStart: true })) {
      setStatusMsg('Could not start preview — try the ▶ Play button on the waveform.');
      return;
    }
    const hasCues = watercolorCues.cues.length > 0;
    setStatusMsg(
      hasCues
        ? '▶ Previewing — animated overlays appear on the lipsync frame above.'
        : '▶ Previewing lipsync — drag watercolors onto the waveform when ready.',
    );
  };

  const onExportToStitcher = async () => {
    const srcFile = phase === 'a' ? (stateSlice.lipsync_file ?? stateSlice.stitched_file) : stateSlice.lipsync_file;
    if (!srcFile) {
      setStatusMsg(`No ${phase === 'a' ? 'lipsync' : 'lipsync'} mp4 yet — finish the producer flow first.`);
      return;
    }
    setBusyAction('export');
    setStatusMsg(
      phase === 'b'
        ? 'Exporting to Stitcher (baking watercolor overlays)…'
        : 'Exporting to Stitcher…',
    );
    const slotKey = phase === 'a' ? 'phase_a' : 'phase_b';

    const res = await pathappPatch<{
      job_name?: string;
      video_path?: string;
      overlay_baked?: boolean;
      warnings?: string[];
    }>(
      activeScope.value,
      'phase_export_stitcher',
      { phase },
    );
    setBusyAction(null);
    if (res.ok) {
      if (stitchExportKeptExistingWarning(res.data?.warnings)) {
        setStatusMsg('✗ Export did not replace stitch slot — stored video is newer');
        return;
      }
      writePersistedTrackSlot(
        stitchJobSessionKey(
          activeScope.value.event_id,
          activeProjectType.value,
          activeMilestoneId.value,
        ),
        slotKey,
      );
      notifyStitchSlotExportApplied(activeScope.value.event_id, slotKey);
      stitcherRefreshTick.value += 1;
      const baked = res.data?.overlay_baked ? ' (overlays baked in)' : '';
      setStatusMsg(`✓ Exported to Stitcher → ${slotKey} slot${baked} (open Stitcher tab to preview/bake)`);
    } else {
      setStatusMsg(`✗ Export HTTP ${res.status}: ${res.error ?? 'export failed'}`);
    }
  };

  const onDeleteWatercolor = async (key: string) => {
    if (!window.confirm(`Delete "${key}" from watercolor library?`)) return;
    const res = await pathappPatch(activeScope.value, 'phase_watercolor_delete', { key: key });
    if (res.ok) {
      setStatusMsg(`✓ Deleted "${key}"`);
      await refreshAll();
    } else {
      setStatusMsg(`✗ Delete failed: ${res.error ?? res.status}`);
    }
  };

  const onWatercolorUpload = async (e: Event) => {
    const files = (e.target as HTMLInputElement).files;
    if (!files || files.length === 0) return;
    let added = 0;
    for (const file of Array.from(files)) {
      try {
        const dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        });
        const image_b64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl;
        const res = await pathappPatch(activeScope.value, 'cr_upload', {
          filename: file.name,
          image_b64,
          tier: 'watercolor',
        });
        if (res.ok) added++;
        else setStatusMsg(`✗ Upload failed: ${res.error ?? res.status}`);
      } catch (err) {
        setStatusMsg(`✗ Upload error: ${String(err)}`);
      }
    }
    if (added > 0) {
      setStatusMsg(`✓ Added ${added} watercolor asset(s)`);
      await refreshAll();
    }
    if (wcUploadInputRef.current) wcUploadInputRef.current.value = '';
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

  const onCueClick = (cueId: string, anchor: { x: number; y: number }) => {
    setActiveCueId(cueId);
    setPopoverAnchor(anchor);
  };

  const onCueDelete = () => {
    if (!activeCueId) return;
    watercolorCues.onCueDelete(activeCueId);
    setActiveCueId(null);
    setPopoverAnchor(null);
  };

  const onStemCutChange = (cutStartMs: number, cutEndMs: number) => {
    void stemCut.persistStemCut(cutStartMs, cutEndMs);
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
    if (pos === 'sitting') return stateSlice.chipper_sitting_clip_id;
    return undefined;
  };

  const onPickPhaseAClip = async (pos: PhaseAClipPosition, clipId: string) => {
    const field = `phase_a_chipper_${pos}_clip_id`;
    setPickerPosition(null);
    setStateSlice((s) => ({
      ...s,
      [`chipper_${pos}_clip_id`]: clipId,
    } as PhaseStateSlice));
    if (pos === 'sitting') {
      setSelectedBaseClip(clipId);
    }
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

  const onSaveScript = async () => {
    const currentServer = stateSlice.script ?? '';
    const draft = scriptField.getText();
    if (draft === currentServer) {
      flashSaveBtn('✓ Already saved');
      return;
    }
    flashSaveBtn('Saving…');
    const ok = await scriptField.flushSave();
    if (ok) {
      flashSaveBtn('✓ Saved');
      setStatusMsg('✓ Script saved');
    } else {
      flashSaveBtn('✗ Error');
    }
  };

  const onGenerateStem = async () => {
    setBusyAction('stem');
    await scriptField.flushSave();
    const script = scriptField.getText();
    setStatusMsg('Generating stem from script…');
    const regenEp = phase === 'a' ? 'phase_a_regen_audio' : 'phase_b_regen_audio';
    const res = await pathappPatch(activeScope.value, regenEp, {
      phase,
      script,
    });
    setBusyAction(null);
    if (res.ok) {
      setStatusMsg('✓ Stem generated');
      await refreshAll();
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

  const priorityAudio = priorityAudioFileForPhase(stateSlice, phase);
  const waveformAudio =
    stemTrimMode && stateSlice.voice_stem_file
      ? { name: stateSlice.voice_stem_file, label: 'stem' as const }
      : priorityAudio;
  const lipsyncFile = stateSlice.lipsync_file ?? null;
  const previewVideo: PhasePreviewFile | null =
    phase === 'a'
      ? phaseAPreviewFile(stateSlice)
      : lipsyncFile
        ? { name: lipsyncFile, label: 'lipsync', kind: 'lipsync' }
        : null;
  const canEditStemCut = Boolean(stemTrimMode && stateSlice.voice_stem_file);
  const stemCutStartMs = stemCut.stemCutStartMs;
  const stemCutEndMs = stemCut.stemCutEndMs;
  const showRejectLipsync =
    Boolean(lipsyncFile) &&
    !lipsyncInFlight;
  const hasStemCut = stemCut.hasStemCut;
  const terminalLipsyncBanner = phaseLipsyncTerminalBanner(stateSlice.lipsync_status);
  const displayStatusMsg =
    lipsyncInFlight && !statusMsg?.startsWith('✗')
      ? phaseLipsyncProgressMessage(phase)
      : (statusMsg ?? terminalLipsyncBanner);
  const activeCue =
    activeCueId
      ? watercolorCues.cues.find((c) => c.id === activeCueId) ?? null
      : null;
  const linkedVideoMatchesWaveformAudio = Boolean(
    previewVideo &&
      waveformAudio &&
      previewVideo.kind === 'lipsync' &&
      linkedMediaSameFilename(previewVideo.name, waveformAudio.name),
  );

  return (
    <div
      class={`mn-phase-producer mn-phase-${phase}`}
      data-testid={`phase-producer-${phase}`}
      data-phase-producer-ab="PHASE_PRODUCER_AB_V1"
      data-phase-watercolor-cue-authority="PHASE_WATERCOLOR_CUE_AUTHORITY_V1"
      data-operator-edit-authority="OPERATOR_EDIT_AUTHORITY_V1"
      data-phase-watercolor-overlay="PHASE_WATERCOLOR_OVERLAY_V1"
      {...(phase === 'a' ? { 'data-phase-a-single-player': 'PHASE_A_SINGLE_PLAYER_V1' } : {})}
    >
      <div class='mn-phase-status-header'>
        <span class='mn-dim mn-phase-status-tag' data-testid={`phase-${phase}-status-header`}>
          {waveformAudio ? `audio: ${waveformAudio.label}` : 'no audio yet'}
          {stemTrimMode ? ' · trim mode' : ''}
          {lipsyncFile && !stemTrimMode && !lipsyncInFlight ? ' · lipsync ✓' : ''}
          {lipsyncInFlight ? ' · lipsync ⏳' : ''}
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
          ref={scriptField.textareaRef}
          rows={8}
          onFocus={scriptField.onFocus}
          onInput={scriptField.onInput}
          onBlur={() => {
            scriptField.onBlur();
            void onSaveScript();
          }}
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
            onClick={() => void onSaveScript()}
            disabled={saveBtnLabel === 'Saving…'}
          >
            {saveBtnLabel}
          </button>
        </div>

        {/* Waveform trim toolbar — enter trim mode to show amber cut on stem (not lipsync). */}
        {stateSlice.voice_stem_file ? (
          <div class="mn-phase-waveform-trim-toolbar" data-testid={`phase-${phase}-waveform-trim-toolbar`}>
            {stemTrimMode ? (
              <>
                <span class="mn-stem-trim-mode-badge" data-testid={`phase-${phase}-stem-trim-mode-badge`}>
                  ✂ Trim mode — voice stem on waveform
                </span>
                <button
                  type="button"
                  class="mn-btn mn-btn-primary"
                  data-testid={`phase-${phase}-apply-stem-cut-btn`}
                  onClick={onApplyStemCut}
                  disabled={busyAction !== null || !hasStemCut}
                  title="Remove the amber region from the voice stem (ffmpeg)"
                >
                  {busyAction === 'apply_cut' ? 'Cutting…' : 'Apply Cut'}
                </button>
                {hasStemCut ? (
                  <button
                    type="button"
                    class="mn-btn"
                    data-testid={`phase-${phase}-clear-stem-cut-btn`}
                    onClick={() => void onClearStemCutSelection()}
                    disabled={busyAction !== null}
                    title="Remove amber selection without changing the stem file"
                  >
                    {busyAction === 'clear_cut' ? 'Clearing…' : 'Clear selection'}
                  </button>
                ) : null}
                <span class="mn-dim mn-stem-trim-hint" data-testid={`phase-${phase}-stem-trim-hint`}>
                  Drag gold handles · amber = section to remove
                </span>
                <button
                  type="button"
                  class="mn-btn"
                  data-testid={`phase-${phase}-exit-stem-trim-btn`}
                  onClick={onExitStemTrimMode}
                  disabled={busyAction !== null}
                  title={
                    lipsyncFile
                      ? 'Return waveform to lipsync audio'
                      : 'Hide trim handles and return to normal waveform view'
                  }
                >
                  Exit trim mode
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  class="mn-btn mn-btn-trim-stem"
                  data-testid={`phase-${phase}-trim-voice-stem-btn`}
                  onClick={onEnterStemTrimMode}
                  disabled={busyAction !== null}
                  title="Switch waveform to voice stem and show amber cut handles"
                >
                  Trim voice stem
                </button>
                {lipsyncFile ? (
                  <span class="mn-dim mn-stem-trim-hint">
                    Lipsync is on the waveform now — click Trim voice stem to edit the stem cut.
                  </span>
                ) : null}
              </>
            )}
          </div>
        ) : null}

        {/* Audio waveform — WaveSurfer v7 timeline (LD-330 / LD-472).
            Priority: lipsync > mixed > stem (resolved by priorityAudioFileForPhase).
            stemTrimMode forces stem for cut editing. */}
        <WaveformTimeline
          audioSrc={waveformAudio ? fileUrl(waveformAudio.name) : null}
          sourceLabel={waveformAudio?.label ?? null}
          sourceFilename={waveformAudio?.name ?? null}
          cues={watercolorCues.cues}
          onCueClick={onCueClick}
          onWatercolorDrop={watercolorCues.onWatercolorDrop}
          onTimeUpdate={(ms) => setCurrentTimeMs(ms)}
          onPlayStateChange={setWaveIsPlaying}
          onCueRangeChange={watercolorCues.onCueRangeChange}
          stemCutStartMs={stemCutStartMs}
          stemCutEndMs={stemCutEndMs}
          stemCutEditable={canEditStemCut}
          onStemCutChange={onStemCutChange}
          {...(stemTrimMode
            ? {}
            : {
                linkedVideo: videoRef,
                linkedVideoFilename: previewVideo?.name ?? null,
              })}
          {...(linkedVideoMatchesWaveformAudio ? { linkedVideoMatchAudio: true } : {})}
          playbackControl={waveformPlaybackRef}
        />
        {activeCue && popoverAnchor ? (
          <CuePopover
            cue={activeCue}
            anchor={popoverAnchor}
            onPatch={watercolorCues.onCuePatch}
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

        {phase === 'b' ? (
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
        ) : null}

        {/* Action row: Phase A/B Avatar still chip + Send for Avatar Pro */}
        <div class="mn-phase-row">
          <span
            class="mn-dim mn-phase-avatar-still-chip"
            data-testid={`phase-${phase}-avatar-still-chip`}
          >
            {phase === 'a'
              ? PHASE_A_ARLO_AVATAR_STILL_LABEL
              : 'Cedric still (Avatar Pro) — canonical Jun 21 PNG'}
          </span>
          <button
            type="button"
            class="mn-btn"
            data-testid={`phase-${phase}-send-lipsync-btn`}
            onClick={onSendForLipsync}
            disabled={
              busyAction !== null ||
              lipsyncInFlight ||
              !stateSlice.voice_stem_file
            }
            title="Single Avatar Pro job on full voice stem (~10–50 min, billed per second). No segmented chunks."
          >
            {busyAction === 'lipsync'
              ? 'Sending…'
              : lipsyncInFlight
                ? 'Lipsync in progress…'
                : 'Send for Avatar Pro'}
          </button>
          {showRejectLipsync ? (
            <button
              type="button"
              class="mn-btn mn-btn-reject-lipsync"
              data-testid={`phase-${phase}-reject-lipsync-btn`}
              onClick={onRejectLipsync}
              disabled={busyAction !== null}
              title="Clear lipsync video and return waveform to voice stem for trimming"
            >
              {busyAction === 'reject_lipsync' ? 'Rejecting…' : 'Reject lipsync'}
            </button>
          ) : null}
          {phase === 'b' ? (
            <button
              type="button"
              class="mn-btn"
              data-testid={`phase-${phase}-mix-btn`}
              onClick={onMixAudio}
              disabled={busyAction !== null}
            >
              {busyAction === 'mix' ? 'Mixing…' : 'Mix Audio'}
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
          <button
            type="button"
            class="mn-btn mn-btn-preview-overlay"
            data-testid={`phase-${phase}-preview-overlay-btn`}
            onClick={onPreviewOverlay}
            disabled={busyAction !== null || !previewVideo}
            title="Play from the start — animated watercolors render on the lipsync frame above."
          >
            🎨 Preview with Overlay
          </button>
        </div>

        {/* Status line — server-driven in-flight message survives tab switches */}
        {displayStatusMsg ? (
          <div
            class={`mn-phase-status-line${lipsyncInFlight ? ' mn-phase-status-line--lipsync-pending' : ''}`}
            data-testid={`phase-${phase}-status`}
          >
            {displayStatusMsg}
          </div>
        ) : null}

        {/* Primary preview — one player per phase (Phase A: canonical stitched when fresh).
            Muted: WaveSurfer (above) owns audio. Waveform ▶/⏸ is the control point.
            Drag watercolors onto the waveform; overlays appear here during playback. */}
        <div
          class="mn-phase-lipsync mn-phase-lipsync-primary"
          data-testid={`phase-${phase}-lipsync-player`}
        >
          {previewVideo ? (
            <>
              <strong>
                {phase === 'a' && previewVideo.kind === 'stitched'
                  ? 'Preview (normalized dry lipsync — ambient added in Stitcher):'
                  : phase === 'a'
                    ? 'Preview (lipsync — dry voice only):'
                    : 'Preview (lipsync + overlay cues):'}
              </strong>
              <div
                class="mn-lipsync-video-wrapper"
                style={phaseWatercolorOverlayCssVars(phase)}
              >
                <video
                  ref={videoRef}
                  muted={!linkedVideoMatchesWaveformAudio}
                  playsInline
                  preload="auto"
                  class={`mn-lipsync-preview-video ${PLAYBACK_VIDEO_ANTI_BANDING_CLASS}`}
                  src={fileUrl(previewVideo.name)}
                />
                {watercolorCues.cues
                  .filter(
                    (cue) =>
                      currentTimeMs >= cue.offset_ms &&
                      currentTimeMs < cue.offset_ms + (cue.duration_ms ?? 3000),
                  )
                  .map((cue) => {
                    const wcItem = watercolors.find((w) => w.key === cue.watercolor_key);
                    const isAnimation =
                      wcItem?.kind === 'animation' ||
                      cue.watercolor_key.includes('_animated_');
                    const elapsed = currentTimeMs - cue.offset_ms;
                    const opacity = Math.min(1.0, elapsed / 300);

                    if (isAnimation) {
                      const animSrc = watercolorOverlaySrc(cue.watercolor_key, wcItem, { animation: true });
                      return (
                        <WatercolorAnimOverlay
                          key={cue.id}
                          src={animSrc}
                          elapsedMs={elapsed}
                          isWavePlaying={waveIsPlaying}
                          opacity={opacity}
                        />
                      );
                    }

                    const pngSrc = watercolorOverlaySrc(cue.watercolor_key, wcItem);

                    return (
                      <img
                        key={cue.id}
                        class="mn-lipsync-watercolor-overlay"
                        src={pngSrc}
                        alt=""
                        style={{ opacity }}
                      />
                    );
                  })}
              </div>
              <span class="mn-dim">{previewVideo.name}</span>
              {phase === 'a' && stateSlice.stitched_file && stitchedPreviewStale(stateSlice) ? (
                <div class="mn-phase-stitched-stale mn-dim" data-testid="phase-a-stitched-stale">
                  Stitched file ({stateSlice.stitched_file}) is older than current lipsync.
                  Run <strong>Normalize for export</strong> to refresh the preview.
                </div>
              ) : null}
              {phase === 'a' && !stateSlice.stitched_file && lipsyncFile ? (
                <div class="mn-dim" data-testid="phase-a-stitched-placeholder">
                  Export to Stitcher adds the ambient bed on the Phase A slot.
                </div>
              ) : null}
            </>
          ) : (
            <div
              class="mn-phase-lipsync-placeholder mn-dim"
              data-testid={`phase-${phase}-lipsync-placeholder`}
            >
              Lipsync preview appears here after &quot;Send for Avatar Pro&quot; completes.
            </div>
          )}
        </div>

        {/* Phase A clip section — fly-in/fly-out bookends (LD PHASE_A_THREE_CLIP_HANDLING_V1).
            Phase A/B lipsync uses Avatar Pro on canonical still + voice stem. */}
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
            <div class="mn-phase-a-clip-actions">
              <button
                type="button"
                class="mn-btn"
                data-testid="phase-a-restitch-btn"
                onClick={onPhaseARestitch}
                disabled={busyAction !== null}
                title="Normalize dry lipsync into phase_a_stitched_file (no ambient)"
              >
                {busyAction === 'restitch' ? 'Normalizing…' : 'Normalize for export'}
              </button>
              <button
                type="button"
                class="mn-btn mn-btn-small"
                data-testid="phase-a-regen-base-clip-btn"
                onClick={onRegenBaseClip}
                disabled={busyAction !== null}
                title="Regenerate Arlo wizard-desk idle base from still (~6 min Kling)"
              >
                Regen base clip
              </button>
            </div>
            <BaseClipPicker
              open={pickerPosition !== null}
              positionLabel={pickerPosition ? PHASE_A_CLIP_LABELS[pickerPosition] : ''}
              character="arlo"
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
          <div class="mn-phase-watercolor-header">
            <strong>Watercolors ({watercolors.length}):</strong>
            <label
              class="mn-library-upload-btn mn-phase-watercolor-add-btn"
              data-testid={`phase-${phase}-watercolor-add-btn`}
              title="Upload PNG to watercolor library"
            >
              <input
                ref={wcUploadInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                hidden
                onChange={(e: Event) => void onWatercolorUpload(e)}
                data-testid={`phase-${phase}-watercolor-add-input`}
              />
              + Add
            </label>
          </div>
          <div class="mn-phase-watercolor-grid">
            {watercolors.map((wc) => (
              <div
                class={`mn-phase-watercolor-tile${wc.kind === 'animation' ? ' mn-phase-watercolor-tile--animation' : ''}`}
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
                    src={watercolorFileUrl(wc.key)}
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
                <button
                  type="button"
                  class="mn-asset-tile-delete"
                  data-testid={`phase-${phase}-watercolor-delete-${wc.key}`}
                  aria-label={`Delete ${wc.key}`}
                  onClick={(e: MouseEvent) => {
                    e.stopPropagation();
                    void onDeleteWatercolor(wc.key);
                  }}
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
        </div>

        <p class="mn-readonly-banner">
          S4 wired: Suggest Script · Send for Avatar Pro · Export (Phase A dry → Stitcher ambient) ·
          Export to Stitcher · Animate-this. WaveSurfer waveform + drag-drop
          watercolor onto timeline = S5 polish.
        </p>
      </div>
    </div>
  );
}
