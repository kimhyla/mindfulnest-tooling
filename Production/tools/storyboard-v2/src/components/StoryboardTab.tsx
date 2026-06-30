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

import { useCallback, useEffect, useMemo, useRef, useState } from 'preact/hooks';
import type { RefObject } from 'preact';
import { Fragment } from 'preact';
import {
  activeScope,
  activeTargetVideo,
  activeProjectType,
  activeMilestoneId,
  scopeKey,
} from '../state/scope';
import { apiGet, expectField, pathappPatch, type ExpectFieldSpec } from '../api/client';
import { formatMutationError } from '../api/mutationErrors';
import { stitcherRefreshTick } from '../app';
import {
  ensureStoryboardSession,
  storyboardError,
  storyboardLoading,
  storyboardSessionHasCache,
  storyboardState,
} from '../state/storyboardSessionStore';
import {
  clearStoryboardDialogueShadow,
  useStoryboardDialogueField,
} from '../hooks/useStoryboardDialogueField';
import { useStoryboardTrimFields } from '../hooks/useStoryboardTrimFields';
import { SERVER_BASE, MUTATION_ENDPOINTS as ENDPOINTS } from '../api/endpoints';
import { makeDropTarget } from '../utils/dragdrop';
import { useDropTargetCapture } from '../hooks/useDropTargetCapture';
import { Spinner } from './ui/Spinner';
import { BeatMagicButtons } from './BeatMagicButtons';
import { pushToast } from './ui/Toast';
import { Modal } from './ui/Modal';
import { BeatAudioPreview } from './BeatAudioPreview';
import { BeatCompositePreview } from './BeatCompositePreview';
import { PLAYBACK_VIDEO_ANTI_BANDING_CLASS } from '../utils/playbackVideoPolicy';
import { SuggestParentheticalDropdown } from './SuggestParentheticalDropdown';

interface BeatState {
  speaker?: string;
  text?: string;
  image_path?: string;
  _version?: number;
  text_last_updated_at?: string;
  audio_file?: string;
  text_modified_after_tts?: boolean;
  // F-STALE-LIPSYNC-UI-001 / LD STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1.
  // ISO8601 timestamp written by the TTS regen path
  // (production_server.py `_handle_audio_generate_v4`). The ▶ lipsync
  // freshness gate compares parse(audio_regenerated_at) against
  // lipsync.file_mtime to decide whether the cached lipsync output is
  // current versus the audio. Absent on legacy beats (treated as 0).
  audio_regenerated_at?: string;
  audio_duration_s?: number;
  // S5 v3.1 — magic trail composite paths (per LD-468/469).
  magic_still_path?: string;
  magic_video_path?: string;
  // Bug-B3 (spec §2 Topic-2, 2026-05-20): file_exists enrichment for orphan-
  // reference detection. Set by server-side _read_state_with_file_flags to
  // false when state references a magic_*_path file that no longer exists on
  // disk. UI gates playback on these so we don't 404 silently.
  magic_still_path_exists?: boolean;
  magic_video_path_exists?: boolean;
  // Topic 1 (spec §2): approved end-frame PNG for Kling start-end pipeline.
  // Set by /api/beat/preview_end_frame or /api/beat/upload_end_frame.
  // Consumed by _handle_add_options_startend (refuses if absent/missing).
  end_frame_path?: string;
  end_frame_path_exists?: boolean;
  // S5 — preferred video source for magic_video (lipsync, then animation).
  // file_mtime (epoch seconds, integer) is projected by the bootstrap endpoint
  // `_handle_v2_event_state` from os.stat(animation_clips/<lipsync.file>).
  // Compared against audio_regenerated_at to gate the ▶ lipsync play button
  // per LD STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1. Missing → defensive
  // "stale" default (older server, or file disappeared mid-render).
  lipsync?: { file?: string; status?: string; file_mtime?: number; file_exists?: boolean; method?: string; task_id?: string;
    /** audio_processing block from server — trim_start here is lipsync_start at generation (ts_used). */
    audio_processing?: { trim_start?: number; audio_delay?: number; [key: string]: unknown } };
  // phase_1 is the server-canonical persistence root for per-beat animation
  // state. `audio_delay` (the Video Lead-in slider) lives here — bootstrap
  // /api/v2/event/<id>/state returns the raw state.json so this is where the
  // React render path must read from. Spec id=225 §5.1 Edit 4 +
  // STORYBOARD_AUDIO_DELAY_READ_NESTED_PATH_V2.
  phase_1?: {
    selected_option?: number;
    options?: Array<{ file?: string; status?: string; file_exists?: boolean }>;
    audio_delay?: number;
    trim_start?: number;
    trim_end?: number | null;
    trim_back?: number | null;  // Relative back-trim (seconds from end). Server computes effective_end = raw_dur - trim_back. Added 2026-05-23.
    fade_after_ms?: number | null;
  };
  // S5.5e — fields read by the beat-level state machine (LD BEAT_LIFECYCLE_STATE_MACHINE_V1).
  // beat.final block is the "is final?" signal per Cursor v8 (NOT a use_as_final boolean).
  // Server writes this at production_server.py:10733-10747 with shape:
  //   { source: "raw_option" | "lipsync", source_option, file, approved_at }
  final?: {
    source?: string;
    source_option?: number;
    file?: string;
    file_exists?: boolean;
    approved_at?: string;
    // LD-761 + LD-777: Ken Burns still-as-final config persisted by server.
    image_path?: string;
    image_path_exists?: boolean;
    cache_key?: string;
    kenburns?: {
      zoom_start?: number;
      zoom_end?: number;
      pan_x_start?: number;
      pan_x_end?: number;
      pan_y_start?: number;
      pan_y_end?: number;
      duration_s?: number;
    };
    zoom_applied?: boolean;
    pre_zoom_file?: string;
  };
  // Trim/delay (LD-160). Optional — older beats may not carry these.
  trim_in?: number;
  trim_out?: number | string;
  // CANONICAL persistence path is `phase_1.audio_delay` (production_server.py
  // L14780 `_handle_beat_delay` writes here; ffmpeg_stitch.py L682
  // `compute_cache_hash` reads here). The bootstrap endpoint
  // `_handle_v2_event_state` (production_server.py L15411) returns the raw
  // state.json, so on the React render path `beat.phase_1.audio_delay` is
  // where the value lives. The top-level `audio_delay` below is the
  // FLATTENED shape returned only by `_handle_animate_status` polling
  // (production_server.py L12943) — present on the polling response but
  // NOT on bootstrap. Read order is therefore:
  //   beat.phase_1.audio_delay → beat.audio_delay → beat.delay_seconds → 0
  // Fixed 2026-05-16 per spec id=225 §5.1 + LD
  // STORYBOARD_AUDIO_DELAY_READ_NESTED_PATH_V2 (supersedes LD-694/695/698).
  audio_delay?: number;     // flattened shape from polling endpoint only
  delay_seconds?: number;   // legacy alias, deprecated
  // V59 Phase 6 — Kim-reviewed-done flag (spec line 120).
  kim_done?: boolean;
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
// Canonical speaker roster (LD CHARACTER_DROPDOWN_RESTORED_V1).
// Mirrors content-lockfiles/voice_profiles.toml `[characters.*]` table +
// the legacy build_storyboard.py BG_SPEAKERS list (line 1941). 10 entries
// total: 2 storyteller voices + 6 creatures + 2 Arc 1 NPCs.
// Source of truth: prod_voice_profiles Directus collection. Keep this list
// in sync — drift is a CI-checkable error (C13 Test D lockfile correctness).
const KNOWN_SPEAKERS: readonly string[] = [
  'Cedric', 'Arlo', 'Tessa', 'Lorelai', 'Benson',
  'Ember', 'Bork', 'Bramble', 'Grizzle', 'Oliver',
] as const;

function endFrameAddendumKey(eventId: string, beatId: string): string {
  return `mn:v59:endframe-addendum:${eventId}:${beatId}`;
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
  // Kim 2026-05-20: lipsync_pending MUST take precedence over final. A beat
  // can have an old final (raw_option from a prior session) while a new
  // lipsync is in flight — if we return 'final' first, the polling effect
  // never fires (it's gated on lifecycle === 'lipsync_pending') and the UI
  // never refetches state to discover the lipsync completed. Symptom: Kim
  // submits Send for Lipsync, lipsync completes server-side, but no "▶
  // lipsync" button appears in the UI until manual hard-refresh.
  if (['pending', 'submitted', 'submitting', 'polling'].includes(b.lipsync?.status ?? '')) {
    return 'lipsync_pending';
  }
  // Cursor v8: beat.final block presence IS the "final" signal.
  if (b.final && b.final.file) return 'final';
  const hasOptions = !!(b.phase_1?.options && b.phase_1.options.length > 0);
  const hasSelected = b.phase_1?.selected_option !== undefined && hasOptions;
  if (hasSelected) return 'selected';
  if (hasOptions) return 'animated';
  if (b.audio_file) return 'audio_generated';
  return 'draft';
}

// F-STALE-LIPSYNC-UI-001 / LD STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1.
//
// Decides whether a completed lipsync output is FRESH (≥ audio_regenerated_at)
// or STALE (older than the current audio).
//
// Return value:
//   'fresh'  → ▶ lipsync button enabled; click plays the cached output
//   'stale'  → ▶ lipsync button disabled; label shows "⚠ stale lipsync — re-run"
//
// Defensive defaults (Rule 19 — audit-visible degradation, not silent hide):
//   - lipsync.file_mtime missing (older server hasn't deployed the additive
//     server field yet, or file disappeared mid-stat) → 'stale'
//   - audio_regenerated_at missing/unparseable → 'fresh' (we cannot prove
//     staleness, and refusing to play a known-completed lipsync because of
//     a missing legacy field would be a regression)
//
// The freshness signal is computed every render from the bootstrap response;
// it does NOT depend on the legacy `lipsync.audio_changed` flag (Decision 181)
// which has at least one known miss path (beat_08 in Event_1 carries
// audio_changed=null despite a month-old file vs today's audio_regenerated_at).
export type LipsyncFreshness = 'fresh' | 'stale';

export function computeLipsyncFreshness(b: BeatState): LipsyncFreshness {
  // T2 (LD STALE_LIPSYNC_ON_ASSIGN_IMAGE_V1, 2026-05-20): if the server flagged
  // lipsync.image_changed=true (drag-drop re-assigned image while completed
  // lipsync exists), surface as stale. Kim drags the old library tile back
  // to revert — no undo button by design.
  if ((b.lipsync as { image_changed?: boolean } | undefined)?.image_changed) {
    return 'stale';
  }
  const fileMtimeS = b.lipsync?.file_mtime;
  if (typeof fileMtimeS !== 'number' || !Number.isFinite(fileMtimeS)) {
    // Defensive: server didn't include file_mtime → treat as stale so Kim
    // never plays an unverified cache (the audit-visible failure mode is
    // preferred to a silently-misleading green play button per Rule 19).
    return 'stale';
  }
  const audioRegen = b.audio_regenerated_at;
  if (!audioRegen) {
    // Legacy beat with no audio_regenerated_at — we can't prove staleness.
    // Trust the on-disk artifact rather than block valid playback.
    return 'fresh';
  }
  const audioRegenMs = Date.parse(audioRegen);
  if (!Number.isFinite(audioRegenMs)) {
    return 'fresh';
  }
  const fileMtimeMs = fileMtimeS * 1000;
  // Equal mtimes treated as fresh — a regen that landed on the same epoch
  // second as the lipsync (vanishingly rare in practice) is not stale.
  return fileMtimeMs >= audioRegenMs ? 'fresh' : 'stale';
}

const POLL_ANIMATE_MS = 5000;
const POLL_LIPSYNC_MS = 10000;

interface BeatButtonRowProps {
  index: number;
  beatId: string;
  eventId: string;
  beat: BeatState;
  /** Bumps when beat fields change (parent's refreshTick). Used as cacheBust for audio preview. */
  cacheBust?: string;
  /** Triggered after any successful mutation so parent can refresh state. */
  onMutated: () => void;
  previewOptIdx: number | null;
  onPreviewOption: (optIdx: number, magicKind?: 'still' | 'video' | null) => void;
  /** LD-757: flip parent lipsyncMounted so the lipsync <video> stays mounted. */
  onEnsureLipsyncMounted: () => void;
  /** T1-Phase 6: active video role for preview_end_frame + upload_end_frame POST bodies. */
  videoRole: string;
}

function BeatButtonRow({ index, beatId, eventId, beat, cacheBust, onMutated, previewOptIdx, onPreviewOption, onEnsureLipsyncMounted, videoRole }: BeatButtonRowProps) {
  const lifecycle = deriveBeatLifecycle(beat);
  const [busy, setBusy] = useState<string | null>(null); // which button is in-flight
  // Bug-B2 (spec §2 Topic-2, 2026-05-20): gate the ✨ magic badges on
  // file_exists enrichment (Bug-B3 server-side) so orphan references don't
  // show a misleading "magic" indicator.
  const _magicStillOk = !!(beat.magic_still_path && beat.magic_still_path_exists !== false);
  const _magicVideoOk = !!(beat.magic_video_path && beat.magic_video_path_exists !== false);

  // T1-Phase 6 (spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1, LD-814) — end-frame UI:
  // Kim previews/uploads the ChatGPT end frame here BEFORE Regen B+C; the
  // server-side Phase 4 refuses Regen B+C unless an approved end_frame_path
  // exists on disk. Addendum textarea is one-shot per click (auto-clears).
  const [endFrameAddendum, setEndFrameAddendum] = useState<string>(() => {
    try {
      return sessionStorage.getItem(endFrameAddendumKey(eventId, beatId)) ?? '';
    } catch {
      return '';
    }
  });
  const endFrameDirtyRef = useRef(false);
  useEffect(() => {
    if (endFrameDirtyRef.current) return;
    try {
      setEndFrameAddendum(sessionStorage.getItem(endFrameAddendumKey(eventId, beatId)) ?? '');
    } catch {
      setEndFrameAddendum('');
    }
  }, [eventId, beatId]);
  // pendingEndFrameOp keyed by beat_id per cursor R2 (multiple beats may be
  // in-flight simultaneously; using boolean only-while-this-beat-pending).
  const [pendingEndFrameOp, setPendingEndFrameOp] = useState<boolean>(false);
  const _endFrameOk = !!(beat.end_frame_path && beat.end_frame_path_exists !== false);
  const _endFrameThumbUrl = _endFrameOk
    ? `${SERVER_BASE}/files?path=${encodeURIComponent(`Production/${eventId}/end_frames/${beat.end_frame_path}`)}&v=${beat._version ?? 0}`
    : null;

  const _onPreviewEndFrame = async () => {
    if (pendingEndFrameOp) return;
    setPendingEndFrameOp(true);
    try {
      const url = ENDPOINTS.beat_preview_end_frame;
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope_event_id: eventId,
          scope_video_role: videoRole,  // best-effort; server enforces
          beat_id: beatId,
          ...(endFrameAddendum.trim() ? { prompt_addendum: endFrameAddendum.trim() } : {}),
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) {
        pushToast({
          kind: 'error',
          message: `Preview end frame failed: ${data?.error_message || data?.error || `HTTP ${resp.status}`}`,
          source: 'preview-end-frame',
        });
        return;
      }
      pushToast({
        kind: 'success',
        message: `End frame ${_endFrameOk ? 'replaced' : 'generated'} → ${data.end_frame_path} (${data.size_bytes} B). Click again to iterate.`,
        source: 'preview-end-frame',
      });
      setEndFrameAddendum('');  // auto-clear per spec §2 T1-Phase 6
      try {
        sessionStorage.removeItem(endFrameAddendumKey(eventId, beatId));
      } catch {
        // ignore
      }
      endFrameDirtyRef.current = false;
      onMutated();
    } catch (e) {
      pushToast({
        kind: 'error',
        message: `Preview end frame: ${(e as Error).message}`,
        source: 'preview-end-frame',
      });
    } finally {
      setPendingEndFrameOp(false);
    }
  };

  // Kim 2026-05-21: end-frame upload moved from a file-picker button to a
  // drop zone that ONLY accepts library tiles. The prior file-picker
  // bypassed the cropping step — Kim's flow requires the source to be
  // 4:3 cropped first (in Cropper / library). Now Kim uploads to library →
  // crops → drags the cropped tile here.
  const _uploadEndFrameFromB64 = async (
    fileB64: string,
    mime: string,
    sourceLabel: string,
  ) => {
    if (pendingEndFrameOp) return;
    setPendingEndFrameOp(true);
    try {
      const resp = await fetch(ENDPOINTS.beat_upload_end_frame, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope_event_id: eventId,
          scope_video_role: videoRole,
          beat_id: beatId,
          file_b64: fileB64,
          mime,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) {
        pushToast({
          kind: 'error',
          message: `Upload end frame failed: ${data?.error_message || data?.error || `HTTP ${resp.status}`}`,
          source: 'upload-end-frame',
        });
        return;
      }
      pushToast({
        kind: 'success',
        message: `End frame ← ${sourceLabel} (${data.size_bytes} B)`,
        source: 'upload-end-frame',
      });
      setEndFrameAddendum('');
      onMutated();
    } catch (err) {
      pushToast({
        kind: 'error',
        message: `Upload end frame: ${(err as Error).message}`,
        source: 'upload-end-frame',
      });
    } finally {
      setPendingEndFrameOp(false);
    }
  };

  const _endFrameDropHandlers = makeDropTarget(
    async (payload) => {
      if (payload.kind !== 'lib-image') return;
      const absPath = payload.abs_path;
      if (!absPath) {
        pushToast({
          kind: 'error',
          message: 'Drop a cropped library tile (master tiles aren\'t cropped to 4:3).',
          source: 'end-frame-drop-no-path',
        });
        return;
      }
      try {
        // /api/cr/full returns JSON {ok, data_uri: "data:image/webp;base64,<...>"}
        // — NOT raw binary. Parse the data URI to extract mime + base64.
        const resp = await fetch(
          `${SERVER_BASE}/api/cr/full?abs_path=${encodeURIComponent(absPath)}`,
        );
        if (!resp.ok) {
          pushToast({
            kind: 'error',
            message: `Couldn't read library tile (HTTP ${resp.status})`,
            source: 'end-frame-drop-fetch',
          });
          return;
        }
        const data = await resp.json().catch(() => ({}));
        const dataUri: string | undefined = data?.data_uri;
        if (!dataUri || !dataUri.startsWith('data:')) {
          pushToast({
            kind: 'error',
            message: `Library tile fetch returned unexpected payload (no data_uri).`,
            source: 'end-frame-drop-noduri',
          });
          return;
        }
        // Format: "data:image/webp;base64,<b64>"
        const commaIdx = dataUri.indexOf(',');
        const headerPart = commaIdx >= 0 ? dataUri.slice(5, commaIdx) : 'image/webp;base64';
        const fileB64 = commaIdx >= 0 ? dataUri.slice(commaIdx + 1) : '';
        const mime = headerPart.split(';')[0] || 'image/webp';
        if (!fileB64) {
          pushToast({
            kind: 'error',
            message: 'Library tile data_uri had no base64 body.',
            source: 'end-frame-drop-empty',
          });
          return;
        }
        await _uploadEndFrameFromB64(fileB64, mime, payload.lib_key);
      } catch (err) {
        pushToast({
          kind: 'error',
          message: `End-frame drop failed: ${(err as Error).message}`,
          source: 'end-frame-drop-error',
        });
      }
    },
    (p) => p.kind === 'lib-image',
  );
  const endFrameDropRef = useRef<HTMLDivElement>(null);
  useDropTargetCapture(endFrameDropRef, _endFrameDropHandlers, [_endFrameDropHandlers]);

  // LD-739/740 GREENFIELD: silent-click-on-busy-button class kill.
  // Synchronous handler throws are caught and surfaced as an error toast —
  // unhandled exceptions in a void-cast call would bubble to the Preact
  // event boundary as console-only errors with no user feedback (AI review
  // 2026-05-18 PR #61 non-blocking finding). Async rejections are owned by
  // the handler itself (handlePlayRejection / runMutation toast paths).
  const guardedClick = (label: string, handler: () => unknown) => () => {
    if (busy !== null) {
      pushToast({
        kind: 'warning',
        message: `${label}: wait — ${busy} is in-flight.`,
        source: `beat-${index}-${label}-busy-guard`,
        ttlMs: 2500,
      });
      return;
    }
    try {
      void handler();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      pushToast({
        kind: 'error',
        message: `${label} failed: ${msg}`,
        source: `beat-${index}-${label}-throw`,
      });
    }
  };
  // LD-756 TRIM_INPUT_SEMANTICS_SECONDS_FROM_END_V1 (locked 2026-05-17,
  // shipped 2026-05-20): UI inputs are seconds-FROM-FRONT + seconds-FROM-END
  // so Kim doesn't have to compute total-duration minus desired-end-time.
  // Server still stores absolute trim_start + trim_end timestamps. Conversion
  // happens at 3 client-side points: hydration useEffect (below), onApplyTrim,
  // onPreviewTrim. Duration source: beat.audio_duration_s (populated after
  // first TTS regen; lipsync video duration is audio_duration_s + ~0.4s
  // tailroom per LD-779 — close enough for trim semantics).
  const trimFields = useStoryboardTrimFields(beatId, beat);
  const {
    trimFrontSec,
    trimBackSec,
    delaySec,
    setTrimFrontSec,
    setTrimBackSec,
    setDelaySec,
    onTrimFrontFocus,
    onTrimFrontBlur,
    onTrimBackFocus,
    onTrimBackBlur,
    onDelayFocus,
    onDelayBlur,
  } = trimFields;
  const [holdDuration, setHoldDuration] = useState<string>(
    String(beat.final?.kenburns?.duration_s ?? ''),
  );
  useEffect(() => {
    const persisted = beat.final?.kenburns?.duration_s;
    if (persisted !== undefined && persisted !== null) {
      setHoldDuration(String(persisted));
    }
  }, [beat.final?.kenburns?.duration_s]);

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

  const runMutation = async (
    label: string,
    endpoint: any,
    body: Record<string, unknown>,
    expect?: ExpectFieldSpec[],
  ) => {
    setBusy(label);
    const result = await pathappPatch(activeScope.value, endpoint, { beat_id: beatId, ...body });
    setBusy(null);
    if (result.ok && expect) {
      const check = expectField(result.data, expect);
      if (!check.ok) {
        pushToast({
          kind: 'error',
          message: `${label}: response missing/invalid field '${check.failing}'`,
          source: `beat-${label}-expect-fail`,
        });
        return false;
      }
    }
    if (result.ok) {
      pushToast({ kind: 'success', message: `${label} ok`, source: `beat-${label}` });
      onMutated();
    } else {
      const msg = formatMutationError(result, `${label} failed`);
      if (msg) {
        pushToast({ kind: 'error', message: msg, source: `beat-${label}-error` });
      }
    }
    return result.ok;
  };

  const onRegenAudio = async () => {
    setBusy('Regen Audio');
    const result = await pathappPatch<{ tts_regen?: { audio_duration_s?: number }, duration_warning?: { message?: string; audio_duration_s?: number; kling_max_s?: number } }>(
      activeScope.value, 'beat_regenerate_audio', { beat_id: beatId },
    );
    setBusy(null);
    if (result.ok) {
      pushToast({ kind: 'success', message: 'Regen Audio ok', source: 'beat-Regen Audio' });
      // Fix B (client) — surface server-side duration warning when audio
      // exceeds the Kling v3 10s ceiling. Symmetric with Fix A: don't silently
      // accept a payload that signals downstream-blocked state.
      const warning = result.data?.duration_warning;
      if (warning && typeof warning.message === 'string') {
        pushToast({
          kind: 'warning',
          message: `Audio over cap: ${warning.message}`,
          source: 'beat-Regen Audio-warning',
        });
      }
      onMutated();
    } else {
      const msg = formatMutationError(result, 'Regen Audio failed');
      if (msg) {
        pushToast({ kind: 'error', message: msg, source: 'beat-Regen Audio-error' });
      }
    }
    return result.ok;
  };
  const onAnimate = async () => {
    setBusy('Animate');
    const result = await pathappPatch<{ submitted?: number; skipped?: Array<{ beat?: string; reason?: string; opt?: number }>; status?: string }>(
      activeScope.value, 'animate', { beat_id: beatId },
    );
    setBusy(null);
    if (!result.ok) {
      const msg = formatMutationError(result, 'Animate failed');
      if (msg) {
        pushToast({ kind: 'error', message: msg, source: 'beat-animate-error' });
      }
      return;
    }
    // Fix A — inspect submitted/skipped before declaring success + polling.
    // Server returns HTTP 200 with {submitted, skipped, status} even when the
    // animation request was rejected pre-flight (e.g. Rule 8.5 audio > 10s
    // Kling ceiling). Previously the client only checked result.ok and
    // started a blind 60-iteration poll loop, hiding the real reason from Kim.
    const submitted = result.data?.submitted ?? 0;
    const skipped = Array.isArray(result.data?.skipped) ? result.data!.skipped! : [];
    if (submitted === 0 && skipped.length > 0) {
      const first = skipped[0];
      const reason = first?.reason || 'unknown reason';
      const extra = skipped.length > 1 ? ` (+${skipped.length - 1} more)` : '';
      pushToast({
        kind: 'error',
        message: `Animate skipped: ${reason}${extra}`,
        source: 'beat-animate-skipped',
      });
      return;
    }
    if (submitted === 0 && skipped.length === 0) {
      pushToast({ kind: 'info', message: 'Nothing to animate.', source: 'beat-animate-noop' });
      return;
    }
    // submitted > 0 — normal path. If there are partial skips, log to console
    // (don't double-toast; the success toast covers the dominant signal).
    if (skipped.length > 0) {
      console.warn(`[onAnimate] ${beatId}: ${submitted} submitted, ${skipped.length} skipped`, skipped);
    }
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
  };
  const onSelectOption = (optionIndex: number) =>
    // production_server.py::_handle_select — {"ok": bool, "lipsync_source_changed": ...}
    runMutation('Select option', 'select', { option_index: optionIndex }, [
      { key: 'ok', equals: true },
    ]);
  const onAddOptions = async () => {
    if (lifecycle === 'lipsync_pending' && !window.confirm('This will discard current Options B & C and generate 2 fresh alternatives. Option A is preserved. A lipsync is queued — this may orphan it. Continue?')) return;
    // production_server.py::_handle_add_options_startend — ok/beat/path/...
    const ok = await runMutation('Add options', 'beat_add_options', {}, [
      { key: 'ok', equals: true },
      { key: 'beat', type: 'string' },
    ]);
    if (!ok) return;
    // Poll until all submitted options reach a terminal state (completed/failed).
    // Mirrors the onAnimate poll loop — Kling is async so the initial response
    // only shows "polling"; without this loop the user has to manually refresh.
    let polls = 0;
    const pollAddOptions = async () => {
      polls += 1;
      const res = await apiGet('v2_event_state', { event_id: activeScope.value.event_id });
      if (res.ok) onMutated();
      // Stop when all options are terminal or after 120 polls (~10 min)
      // [INFERRED — 120 × POLL_ANIMATE_MS ≈ 10 min].
      if (polls < 120) window.setTimeout(pollAddOptions, POLL_ANIMATE_MS);
    };
    window.setTimeout(pollAddOptions, POLL_ANIMATE_MS);
  };
  const onSwapToA = (fromSlot: number) =>
    // beats_v2.py::handle_v2_beat_swap_to_a — status/beat/from_slot/...
    runMutation('Move to A', 'beat_swap_to_a', { from_slot: fromSlot }, [
      { key: 'status', equals: 'swapped' },
      { key: 'beat', type: 'string' },
    ]);
  // LD-778 4-gate body validation. Specs reflect ACTUAL handler response shapes
  // (verified by reading the server source, not the spec ideal):
  //   - /api/lipsync (vendor_jobs.handle_lipsync_submit) returns
  //     {"status": "submitted", "beat": ..., "clip": ..., "audio": ...,
  //      "audio_processing": ..., "video_trimmed_to_s": ..., "trim_start": ...,
  //      "trim_end": ..., "cost": ..., "message": ...}
  //     → gate on {status: string-present, beat: string-present}; don't
  //       hard-equals 'submitted' because dedup/cached paths may return
  //       different status strings (status existence + beat existence is enough
  //       for the 4-gate's purpose: kill silent-success-with-empty-body class).
  //   - /api/beat/use_as_final (_handle_use_as_final in production_server.py)
  //     returns {"status": "ok", "beat": ..., "file": ..., "final": ...}
  //     → gate on {status equals 'ok', beat: string-present}.
  //   - /api/beat/use_still_as_final returns {"status": "ok", "beat": ...,
  //     "file": ..., "cache_hit": ..., "hold_duration_s": ...} — same spec as
  //     use_as_final.
  //   - /api/beat/undo_final (handle_beat_undo_final in beats_legacy.py — new
  //     handler I added) returns {"ok": true, "beat": ...} — no status field.
  //     → gate on {ok equals true, beat: string-present}.
  //
  // The earlier "fix" that uniformly used `ok===true` was wrong for the
  // status-shaped handlers (most of them). This revision matches each
  // handler's actual response.
  const onLipsync = () =>
    runMutation('Lipsync', 'lipsync', {}, [
      { key: 'status', type: 'string' },
      { key: 'beat', type: 'string' },
    ]);
  // 🐦 Idle LipSync — Kling i2v idle (same start+end frame) → Kling LipSync.
  // Avoids ByteDance hallucinated arm-gestures on cartoon bird wings.
  // Server: /api/lipsync_idle → vendor_jobs.handle_lipsync_idle (async, fires + returns).
  const onLipsyncIdle = () =>
    runMutation('Idle LipSync', 'lipsync_idle', {}, [
      { key: 'status', type: 'string' },
    ]);
  const onUseAsFinal = () =>
    runMutation('Use as Final', 'beat_use_as_final', {}, [
      { key: 'status', equals: 'ok' },
      { key: 'beat', type: 'string' },
    ]);
  // Kim 2026-05-20 follow-up: explicit "Use Lipsync as Final" — sets
  // final.source = 'lipsync', final.file = lipsync.file. Server-side support
  // added in _handle_use_as_final via body.source='lipsync'.
  const onUseLipsyncAsFinal = () =>
    runMutation('Use Lipsync as Final', 'beat_use_as_final', { source: 'lipsync' }, [
      { key: 'status', equals: 'ok' },
      { key: 'beat', type: 'string' },
    ]);
  const onUseStillAsFinal = () => {
    const body: Record<string, unknown> = {};
    const trimmed = holdDuration.trim();
    if (trimmed !== '') {
      const parsed = Number(trimmed);
      if (Number.isFinite(parsed)) {
        body['hold_duration_s'] = parsed;
      }
    }
    return runMutation('Still as Final', 'beat_use_still_as_final', body, [
      { key: 'status', equals: 'ok' },
      { key: 'beat', type: 'string' },
    ]);
  };
  const onUndoFinal = () =>
    runMutation('Undo Final', 'beat_undo_final', {}, [
      { key: 'ok', equals: true },
      { key: 'beat', type: 'string' },
    ]);
  const onToggleZoom = () => {
    runMutation(
      beat.final?.zoom_applied ? 'Remove Zoom' : 'Apply Zoom',
      'beat_zoom',
      {},
    );
  };
  const trimPreviewListenerRef = useRef<((this: HTMLVideoElement, ev: Event) => void) | null>(null);
  const onPreviewTrim = async () => {
    // BUG-D fix (Kim 2026-05-20): Preview Trim was racing — calling
    // ensureLipsyncMounted (setState, async) then immediately querySelector
    // (DOM not yet updated). Also wrong source: per LD-749 trim is
    // post-lipsync, so video.src must be lipsync.file not final.file.
    // Lipsync existence is the precondition; surfaces a clear error toast
    // if missing rather than silent "playback blocked".
    if (!beat.lipsync?.file || beat.lipsync.file_exists === false) {
      pushToast({
        kind: 'error',
        message: 'Preview Trim needs a completed lipsync — click Send for Lipsync first',
        source: `beat-${index}-trim-preview-no-lipsync`,
      });
      return;
    }
    onEnsureLipsyncMounted();
    // Wait for the lipsync <video> to mount in the DOM (setLipsyncMounted
    // triggers re-render asynchronously). Poll up to 500ms.
    const findVideo = (): HTMLVideoElement | null =>
      document.querySelector(`[data-testid="beat-${index}-lipsync-video"]`) as HTMLVideoElement | null;
    let video = findVideo();
    if (!video) {
      const deadline = Date.now() + 500;
      while (Date.now() < deadline) {
        await new Promise((r) => requestAnimationFrame(() => r(null)));
        video = findVideo();
        if (video) break;
      }
    }
    if (!video) {
      pushToast({
        kind: 'error',
        message: 'Preview Trim: video element did not mount within 500ms',
        source: `beat-${index}-trim-preview-missing`,
      });
      return;
    }
    // LD-749 post-lipsync trim: source is lipsync.file (NOT final.file).
    const lipsyncSrc = `${SERVER_BASE}/asset/${beat.lipsync.file}?v=${beat._version ?? 0}`;
    const needsSrcSwap = video.src !== lipsyncSrc;
    if (needsSrcSwap) {
      video.src = lipsyncSrc;
      // Wait for the new src to reach loadedmetadata before seeking + playing.
      try {
        await new Promise<void>((resolve, reject) => {
          const onReady = () => { video!.removeEventListener('loadedmetadata', onReady); video!.removeEventListener('error', onErr); resolve(); };
          const onErr = () => { video!.removeEventListener('loadedmetadata', onReady); video!.removeEventListener('error', onErr); reject(new Error('lipsync video load error')); };
          video.addEventListener('loadedmetadata', onReady, { once: true });
          video.addEventListener('error', onErr, { once: true });
          // Defensive timeout — don't hang the click handler indefinitely.
          setTimeout(() => { video!.removeEventListener('loadedmetadata', onReady); video!.removeEventListener('error', onErr); reject(new Error('lipsync video load timeout')); }, 5000);
        });
      } catch (err) {
        pushToast({
          kind: 'error',
          message: `Preview Trim: ${err instanceof Error ? err.message : String(err)}`,
          source: `beat-${index}-trim-preview-load`,
        });
        return;
      }
    }
    // LD-756 conversion: front input is seconds-from-front (= absolute trim_in).
    // back input is seconds-from-end, so absolute trim_out = duration - back.
    const frontSec = parseFloat(trimFrontSec);
    const trimInSec = isNaN(frontSec) ? 0 : Math.max(0, frontSec);
    const backSec = parseFloat(trimBackSec);
    const backSecSafe = isNaN(backSec) ? 0 : Math.max(0, backSec);
    let tOut: number | null = null;
    if (backSecSafe > 0) {
      const dur = Number.isFinite(video!.duration) ? video!.duration : (beat.audio_duration_s ?? NaN);
      if (Number.isFinite(dur)) {
        tOut = Math.max(trimInSec + 0.01, dur - backSecSafe);
      }
    }
    if (trimPreviewListenerRef.current) {
      video.removeEventListener('timeupdate', trimPreviewListenerRef.current);
    }
    const onTimeUpdate = () => {
      const end = tOut === null
        ? (Number.isFinite(video!.duration) ? video!.duration : Infinity)
        : tOut;
      if (video!.currentTime >= end) {
        video!.pause();
        video!.removeEventListener('timeupdate', onTimeUpdate);
        trimPreviewListenerRef.current = null;
      }
    };
    trimPreviewListenerRef.current = onTimeUpdate;
    video.currentTime = trimInSec;
    video.addEventListener('timeupdate', onTimeUpdate);
    try {
      await video.play();
    } catch (err) {
      pushToast({
        kind: 'error',
        message: `Preview Trim: ${err instanceof Error ? err.message : 'playback blocked'}`,
        source: `beat-${index}-trim-preview-play`,
      });
    }
  };
  const onApplyTrim = () => {
    // LD-756 conversion: front = absolute trim_in. back > 0 means trim N
    // seconds from the back → absolute trim_out = duration - back. back == 0
    // means no end trim → trim_out = null. Fail loud per spec if user typed
    // back > 0 without a known duration (audio_duration_s populates after
    // first TTS regen; if missing, prompt for that).
    const frontSec = parseFloat(trimFrontSec);
    const front = isNaN(frontSec) ? 0 : Math.max(0, frontSec);
    const backSec = parseFloat(trimBackSec);
    const back = isNaN(backSec) ? 0 : Math.max(0, backSec);
    // BUG FIX (2026-05-23): previously computed trim_out = audio_duration_s - back, which is
    // WRONG because audio_duration_s ≠ video clip duration. For beats with short audio on a long
    // clip (e.g. 1.52s audio on 5s clip, back=1.01 → trim_out=0.51), the server received an
    // absurdly small trim window and either errored or silently dropped the back-trim intent.
    //
    // Fix: send trim_back (relative seconds from end) so the server computes
    // effective_end = raw_dur - trim_back using ffprobe — no video duration needed here.
    // beats_legacy.py::handle_beat_trim stores trim_back + clears stale trim_end.
    // vendor_jobs.py reads trim_back to set correct effective_end for lipsync submission.
    return runMutation('Trim', 'beat_trim', {
      trim_in: front,
      trim_back: back,  // 0 = no back trim; server clears stale trim_end
    }, [
      { key: 'beat', type: 'string' },
      { key: 'trim_start', type: 'number' },
    ]);
  };
  const onApplyDelay = () => {
    const d = parseFloat(delaySec);
    // beats_legacy.py::handle_beat_delay — beat/audio_delay
    return runMutation('Delay', 'beat_delay', { delay_seconds: isNaN(d) ? 0 : d }, [
      { key: 'beat', type: 'string' },
      { key: 'audio_delay', type: 'number' },
    ]);
  };

  // Visibility per state-machine table (S5.5e spec §3.1).
  const showRegenAudio = ['draft', 'audio_generated', 'animated', 'selected', 'final'].includes(lifecycle);
  // Show Animate when audio exists (intro workflow) OR when image is assigned
  // without audio yet (resolution/Kling image-first pipeline per Rule 8.3).
  const showAnimate = lifecycle === 'audio_generated' || (lifecycle === 'draft' && !!beat.image_path);
  // count=2 is product-locked per server default; label reflects this.
  // Include 'audio_generated' so the end-frame drop zone + Generate end frame
  // button are available BEFORE the first Animate click — lets Kim pre-load an
  // end frame and have it used on the very first generation (fresh beats after
  // storyboard reset land at audio_generated, not animated).
  const showAddOptions = ['draft', 'audio_generated', 'animated', 'selected', 'lipsync_pending', 'final'].includes(lifecycle);
  const showSelectedOptionRadios = ['animated', 'selected', 'lipsync_pending', 'final'].includes(lifecycle);
  // Kim 2026-05-20 follow-up: previous gate hid the lipsync button whenever
  // lifecycle was 'final' AND final.source != 'lipsync' (e.g. raw_option from
  // a →A swap, OR still_image from Use-as-Final Ken Burns). That blocked the
  // legitimate workflow of UPGRADING a finalized raw beat into a lipsync.
  //
  // New gate: show whenever ANY animation option is selected. The button's
  // label adapts to state (Send for Lipsync vs ▶ lipsync vs ▶ ⚠ stale lipsync)
  // so it surfaces the right action regardless of whether the beat is pre-
  // lipsync, mid-lipsync, or already lipsynced. The only hide cases now are:
  //   - lifecycle 'draft' / 'audio_generated' / 'animated' (nothing selected yet)
  //   - selected_option not set (defensive — shouldn't happen for selected+)
  //
  // Loose != null catches both null and undefined (server may write either
  // for unset selected_option).
  const showLipsync = (
    beat.phase_1?.selected_option != null &&
    ['selected', 'lipsync_pending', 'final'].includes(lifecycle)
  );
  const showUseAsFinal = ['audio_generated', 'animated', 'selected'].includes(lifecycle);
  const showPreview = lifecycle !== 'draft';

  const optionCount = beat.phase_1?.options?.length ?? 0;
  const selectedOption = beat.phase_1?.selected_option ?? null;
  // Which file will be submitted to lipsync (needed for button tooltip + label).
  const selectedOptFile: string | null =
    selectedOption !== null && beat.phase_1?.options?.[selectedOption - 1]?.file
      ? (beat.phase_1!.options![selectedOption - 1].file ?? null)
      : null;
  // F-BEAT-PREVIEW-001 / COMPOSITE_PREVIEW_PERSISTENT_20260524:
  // Show composite preview (animation + delayed TTS) whenever a selected animation
  // option exists — regardless of whether lipsync.file is present.
  // Kim uses the composite preview as a timing reference tool BEFORE resending
  // lipsync, including when reviewing an existing lipsync to decide if delay needs
  // adjusting. Hiding it once lipsync.file exists breaks this workflow.
  //
  // Rule: show composite preview if:
  //   • lifecycle is past 'selected' (animation options exist)
  //   • selected_option is set (there is a clip to preview)
  //   • final.source is NOT 'still_image' (still-as-final has no animation to preview)
  //
  // The BeatCompositePreview component itself returns null when videoSrc/audioSrc
  // are missing, so no additional guard needed here.
  const showCompositePreview = (
    ['animated', 'selected', 'lipsync_pending', 'final'].includes(lifecycle) &&
    beat.phase_1?.selected_option != null &&
    beat.final?.source !== 'still_image'
  );

  return (
    <div class="mn-beat-button-row" data-testid={`beat-button-row-${index}`} data-lifecycle={lifecycle}>
      {/* Phase 1 — animation options (visible in animated/selected) */}
      {showSelectedOptionRadios && optionCount > 0 ? (
        <span class="mn-beat-button-group" data-testid={`beat-options-group-${index}`}>
          <span class="mn-beat-button-group-label">Phase 1:</span>
          {Array.from({ length: optionCount }).map((_, i) => {
            const oi = i + 1;
            const opt = beat.phase_1?.options?.[i];
            // Bug fix 2026-05-19: server-enriched `file_exists` reflects
            // disk reality. If state references an option file Kim has
            // manually archived (e.g., still-as-final supersession), the
            // ▶ preview would 404 and the <video> would surface a generic
            // "codec/format not supported" toast. Treat archived options
            // as not-ready and disable ▶ + →A with an explicit label.
            const fileMissing = Boolean(opt?.file) && opt?.file_exists === false;
            const optReady = !!(opt?.file && !fileMissing && opt?.status !== 'pending' && opt?.status !== 'failed');
            return (
              <span key={oi} class="mn-beat-option-pair">
                <button
                  type="button"
                  class={`mn-btn mn-btn-small${selectedOption === oi ? ' is-active' : ''}`}
                  data-testid={`beat-${index}-select-option-${oi}`}
                  onClick={guardedClick('Select option', () => onSelectOption(oi))}
                  aria-disabled={busy !== null}
                >
                  opt {oi}{selectedOption === oi ? ' ✓' : ''}{fileMissing ? ' (archived)' : ''}{
                    /* Kim 2026-05-20 follow-up: 🏁 FINAL badge next to the
                       option that is currently the Stitcher's source video
                       for this beat. final.source must be raw_option AND
                       final.source_option === oi. */
                    beat.final?.source === 'raw_option' && beat.final?.source_option === oi
                      ? ' 🏁 FINAL'
                      : ''
                  }
                </button>
                <button
                  type="button"
                  class={`mn-btn mn-btn-small mn-preview-btn${previewOptIdx === oi ? ' mn-preview-btn-active' : ''}`}
                  data-testid={`beat-${index}-preview-option-${oi}`}
                  onClick={guardedClick('Preview option', () => onPreviewOption(oi))}
                  aria-disabled={busy !== null}
                  disabled={!opt?.file || fileMissing}
                  title={fileMissing ? `opt ${oi} was archived — regenerate to restore` : `Preview with audio: opt ${oi}`}
                >
                  {previewOptIdx === oi ? '⏸' : '▶'}
                </button>
                {oi > 1 ? (
                  <button
                    type="button"
                    class="mn-btn mn-btn-small"
                    data-testid={`beat-${index}-swap-to-a-${oi}`}
                    onClick={guardedClick('Move to A', () => onSwapToA(oi))}
                    aria-disabled={busy !== null}
                    disabled={!optReady}
                    title={optReady ? `Promote opt ${oi} to slot A` : fileMissing ? 'Option file was archived' : 'Option must finish generating first'}
                  >→A</button>
                ) : null}
              </span>
            );
          })}
        </span>
      ) : null}
      {showCompositePreview ? (
        <BeatCompositePreview
          index={index}
          beatId={beatId}
          eventId={eventId}
          beat={beat}
          audioDelay={delaySec}
        />
      ) : null}
      {showAddOptions ? (
        <span class="mn-beat-button-group" data-testid={`beat-${index}-regen-group`}>
          {/* T1-Phase 6 — end-frame iteration controls. Kim previews/uploads
              an end frame FIRST, then clicks Regen B+C. Server (Phase 4)
              refuses Regen B+C unless approved end_frame_path exists. */}
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-preview-end-frame`}
            onClick={_onPreviewEndFrame}
            disabled={pendingEndFrameOp || busy !== null}
            title={
              _endFrameOk
                ? "Re-generate the end frame via ChatGPT, REPLACING the current one. If you typed an addendum, it'll be appended to the canonical prompt for this single call. ~$0.04 per click — click as many times as needed."
                : "Generate the end frame via ChatGPT (the 'second image' Kling animates toward). ~$0.04. If you've typed an addendum, it'll be appended for this call only."
            }
          >
            {pendingEndFrameOp
              ? <><Spinner size="sm" inline /> …</>
              : _endFrameOk
                  ? '🔄 Re-generate end frame'
                  : '✏ Generate end frame'}
          </button>
          <div
            ref={endFrameDropRef}
            class={`mn-end-frame-drop mn-drop-target${pendingEndFrameOp ? ' is-busy' : ''}`}
            data-testid={`beat-${index}-end-frame-drop`}
            title="Drag a 4:3-cropped library tile here to use it as the end frame. (Upload to Library → Crop in Cropper → drag the cropped tile here.) Free."
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              minWidth: '140px',
              padding: '6px 10px',
              border: '1.5px dashed #4a8a4a',
              borderRadius: '4px',
              fontSize: '11px',
              color: '#a8d8a8',
              background: 'rgba(74, 138, 74, 0.08)',
              cursor: 'copy',
            }}
          >
            {pendingEndFrameOp ? (
              <><Spinner size="sm" inline /> …</>
            ) : (
              '📥 Drop library tile (4:3) here'
            )}
          </div>
          <input
            type="text"
            class="mn-beat-trim-input"
            data-testid={`beat-${index}-end-frame-addendum`}
            value={endFrameAddendum}
            onInput={(e) => {
              const next = (e.target as HTMLInputElement).value;
              endFrameDirtyRef.current = true;
              setEndFrameAddendum(next);
              try {
                sessionStorage.setItem(endFrameAddendumKey(eventId, beatId), next);
              } catch {
                // ignore
              }
            }}
            disabled={pendingEndFrameOp || busy !== null}
            placeholder="e.g. ensure all accessories remain (glasses, backpack)"
            title="One-shot prompt addendum sent to ChatGPT. Clears after each Preview click."
            style={{ minWidth: '320px', marginLeft: '4px' }}
          />
          {_endFrameOk && _endFrameThumbUrl ? (
            // Kim 2026-05-20 follow-up: hover-to-enlarge so the 50x50 thumb
            // can be inspected at a useful size. wrapper.hover triggers the
            // child .mn-end-frame-large to render at 360x360 fixed-position
            // overlay. Click thumb in a new tab is the fallback for an even
            // bigger view (browser handles via target="_blank").
            <a
              class="mn-end-frame-thumb-wrap"
              href={_endFrameThumbUrl}
              target="_blank"
              rel="noopener noreferrer"
              data-testid={`beat-${index}-end-frame-thumb-link`}
              title={`Current end frame: ${beat.end_frame_path}\nHover to enlarge · Click to open full-size in a new tab.\nTo replace: edit the addendum field + click '🔄 Re-generate end frame' (or drag a 4:3-cropped library tile onto the drop zone to use your own).`}
              style={{
                position: 'relative',
                display: 'inline-block',
                marginLeft: '4px',
                verticalAlign: 'middle',
                lineHeight: 0,
              }}
            >
              <img
                src={_endFrameThumbUrl}
                alt={`end frame for ${beatId}`}
                data-testid={`beat-${index}-end-frame-thumb`}
                class="mn-end-frame-thumb"
                style={{
                  width: '50px',
                  height: '50px',
                  objectFit: 'cover',
                  border: '1px solid #4a8a4a',
                  display: 'block',
                }}
              />
              <img
                src={_endFrameThumbUrl}
                alt=""
                aria-hidden="true"
                class="mn-end-frame-large"
                style={{
                  // Resting state: invisible + non-interactive + flat scale.
                  // Hover CSS lifts opacity to 1 (with !important so this inline
                  // style can't accidentally pin it back to 0). Using opacity
                  // (not display:none) so the element is always laid out and
                  // can't be hidden by a parent overflow clip. position:fixed
                  // attaches to viewport — completely escapes any ancestor
                  // overflow:hidden, scroll, transform, etc.
                  position: 'fixed',
                  top: '80px',
                  right: '80px',
                  width: '400px',
                  height: '400px',
                  objectFit: 'contain',
                  border: '3px solid #4a8a4a',
                  background: '#000',
                  borderRadius: '6px',
                  boxShadow: '0 12px 32px rgba(0,0,0,0.7)',
                  opacity: 0,
                  visibility: 'hidden',
                  transition: 'opacity 120ms, visibility 120ms',
                  zIndex: 1000,
                  pointerEvents: 'none',
                }}
              />
            </a>
          ) : (
            <span
              class="mn-dim"
              data-testid={`beat-${index}-end-frame-empty`}
              style={{ fontSize: '10px', marginLeft: '4px', fontStyle: 'italic' }}
            >
              (no end frame yet)
            </span>
          )}
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-add-options`}
            onClick={guardedClick('Add options', onAddOptions)}
            disabled={pendingEndFrameOp || !_endFrameOk}
            aria-disabled={busy !== null || pendingEndFrameOp || !_endFrameOk}
            title={_endFrameOk
              ? "Keep Option A, generate 2 fresh alternatives (B & C) using approved end frame. ~$0.90"
              : "Preview or upload an end frame first (T1-Phase 4 server refuses without one)"}
          >
            🔄 Regenerate B + C
          </button>
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
              onClick={guardedClick('Regen Audio', onRegenAudio)}
              aria-disabled={busy !== null}
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
            onClick={guardedClick('Regen Audio', onRegenAudio)}
            aria-disabled={busy !== null}
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
            onClick={guardedClick('Animate', onAnimate)}
            aria-disabled={busy !== null}
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
            onClick={guardedClick('Lipsync', onLipsync)}
            aria-disabled={busy !== null}
            disabled={lifecycle === 'lipsync_pending'}
            title={
              // Always show which option + filename will be submitted — prevents
              // the "lipsynced wrong option after regen" class of errors (Kim 2026-05-24).
              beat.lipsync?.file
                ? selectedOptFile
                    ? `Re-send to Kling lipsync using opt ${selectedOption} (${selectedOptFile}) — replaces current lipsync`
                    : "Re-send the selected option to Kling lipsync (replaces the current lipsync render)"
                : selectedOptFile
                    ? `Send to Kling lipsync using opt ${selectedOption} (${selectedOptFile})`
                    : "Send the selected option to Kling lipsync (generates the first lipsync mp4 for this beat)"
            }
          >
            {lifecycle === 'lipsync_pending' ? (
              <><Spinner size="sm" inline /> in progress</>
            ) : (
              busy === 'Lipsync' ? <><Spinner size="sm" inline /> …</> : (
                // Always include which option number in Resend label so Kim can see
                // at a glance if she needs to select a different option first.
                beat.lipsync?.file
                  ? `👄 Resend Lipsync${selectedOption !== null ? ` (opt ${selectedOption})` : ''}`
                  : '👄 Send for Lipsync'
              )
            )}
          </button>
        ) : null}
        {/* 🐦 Idle LipSync — available on ALL beats.
            Runs Kling i2v (same start+end = idle) → ByteDance LipSync.
            Useful for any beat where you want minimal animation + clean lipsync
            (originally designed for Chipper wing/arm hallucination avoidance,
            but equally valid for Tessa or any creature). */}
        {lifecycle !== 'lipsync_pending' ? (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            style="background:#1a6b5c;color:#fff"
            data-testid={`beat-${index}-lipsync-idle`}
            onClick={guardedClick('Idle LipSync', onLipsyncIdle)}
            aria-disabled={busy !== null}
            title="Kling idle animation (same start+end frame) → ByteDance LipSync. Minimal head motion, clean mouth sync."
          >
            {busy === 'Idle LipSync' ? <><Spinner size="sm" inline /> …</> : (
              beat.lipsync?.method === 'idle_kling_lipsync' ? '🐦 Re-Idle LipSync' : '🐦 Idle LipSync'
            )}
          </button>
        ) : null}
        {beat.lipsync?.status === 'completed' && beat.lipsync?.file ? (
          // F-STALE-LIPSYNC-UI-001 / LD STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1.
          // The button still renders for any completed lipsync with a file so
          // Kim can SEE that a stale artifact exists — but it is DISABLED with
          // a "stale" label when lipsync.file_mtime < audio_regenerated_at.
          // Audit-visible degradation per Rule 19, not a silent hide.
          (() => {
            const freshness = computeLipsyncFreshness(beat);
            const isStale = freshness === 'stale';
            // BUG-C fix (Kim 2026-05-20): stale lipsync should STILL be
            // playable — Kim wants to see prior work even when an image
            // was reassigned or audio was regenerated. Stale only affects
            // the LABEL (warning prefix), not the disabled state.
            return (
              <button
                type="button"
                class={isStale ? 'mn-btn mn-btn-small mn-btn-stale' : 'mn-btn mn-btn-small'}
                data-testid={`beat-${index}-lipsync-play`}
                data-stale={isStale ? 'true' : 'false'}
                onClick={() => {
                  onEnsureLipsyncMounted();
                  onPreviewOption(0);
                }}
                title={
                  isStale
                    ? 'Stale lipsync: cached output may not match the current image/audio. Click to play the prior render anyway; click Regen B+C → Send for Lipsync to refresh.'
                    : 'Preview lipsync result (video has audio baked in)'
                }
              >
                {isStale
                  ? (previewOptIdx === 0 ? '⏸ ⚠ stale lipsync' : '▶ ⚠ stale lipsync')
                  : previewOptIdx === 0
                  ? '⏸ lipsync'
                  : '▶ lipsync'}{
                  /* Kim 2026-05-20: 🏁 FINAL badge when the Stitcher's
                     final source is this lipsync mp4. */
                  beat.final?.source === 'lipsync' && beat.final?.file === beat.lipsync?.file
                    ? ' 🏁 FINAL'
                    : ''
                }
              </button>
            );
          })()
        ) : null}
        {showUseAsFinal ? (
          <button
            type="button"
            class="mn-btn mn-btn-small mn-btn-primary"
            data-testid={`beat-${index}-use-as-final`}
            onClick={guardedClick('Use as Final', onUseAsFinal)}
            aria-disabled={busy !== null}
            title="Mark current selection as final without lipsync (Spec A)"
          >
            {busy === 'Use as Final' ? <><Spinner size="sm" inline /> …</> : '✓ Use as Final'}
          </button>
        ) : null}
        {/* Kim 2026-05-20 follow-up: "Use Lipsync as Final" button — appears
            whenever a completed lipsync exists AND final isn't already lipsync.
            Lets Kim promote the lipsync mp4 to be the canonical final video
            for the Stitcher (was previously not possible — Use as Final
            always picked the selected raw_option). */}
        {beat.lipsync?.status === 'completed' && beat.lipsync?.file && beat.final?.source !== 'lipsync' ? (
          <button
            type="button"
            class="mn-btn mn-btn-small mn-btn-primary"
            data-testid={`beat-${index}-use-lipsync-as-final`}
            onClick={guardedClick('Use Lipsync as Final', onUseLipsyncAsFinal)}
            aria-disabled={busy !== null}
            title="Promote the lipsync mp4 to be the Stitcher's final source for this beat (overwrites any raw_option/still_image final)."
          >
            {busy === 'Use Lipsync as Final' ? <><Spinner size="sm" inline /> …</> : '👄 Use Lipsync as Final'}
          </button>
        ) : null}
        {/* Kim 2026-05-20 follow-up: Undo Final is now allowed for ALL final
            source types (raw_option / lipsync / still_image), not just still.
            Server endpoint broadened to match. The underlying mp4 stays on
            disk; only the beat.final block is cleared. */}
        {lifecycle === 'final' && beat.final?.source !== 'still_image' ? (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-undo-final-generic`}
            onClick={guardedClick('Undo Final', onUndoFinal)}
            aria-disabled={busy !== null}
            title={`Clear the final block (current source: ${beat.final?.source ?? '?'}). The mp4 stays on disk — you can re-finalize via Use as Final / Use Lipsync as Final / Still as Final.`}
          >
            {busy === 'Undo Final' ? <><Spinner size="sm" inline /> …</> : '↩ Undo Final'}
          </button>
        ) : null}
        {beat.final?.file && (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            onClick={guardedClick(beat.final?.zoom_applied ? 'Remove Zoom' : 'Apply Zoom', onToggleZoom)}
            aria-disabled={busy !== null}
            title={beat.final?.zoom_applied
              ? 'Remove zoom — restore original final clip'
              : 'Apply slow Ken Burns zoom (1.0→1.15×) to final clip — $0, ~15–30s per beat'}
            data-testid={`beat-${index}-zoom-toggle`}
          >
            {busy === 'Apply Zoom' || busy === 'Remove Zoom' ? <><Spinner size="sm" inline /> …</> : (beat.final?.zoom_applied ? '✕ zoom' : '↑ zoom')}
          </button>
        )}
        {(lifecycle !== 'final' || beat.final?.source === 'still_image') ? (
          <>
            <input
              type="text"
              class="mn-beat-trim-input"
              data-testid={`beat-${index}-still-hold-input`}
              value={holdDuration}
              onInput={(e) => setHoldDuration((e.target as HTMLInputElement).value)}
              aria-label="Hold seconds for Ken Burns still-as-final"
              placeholder="5.0"
              title="Hold (s): Ken Burns clip duration. Default 5.0s."
              style="width: 4em; margin-right: 4px"
            />
            <span class="mn-beat-button-group-label" style="margin-right:6px">Hold (s)</span>
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-${index}-still-as-final`}
              onClick={guardedClick('Still as Final', onUseStillAsFinal)}
              aria-disabled={busy !== null}
              title={beat.final?.source === 'still_image'
                ? 'Re-render Ken Burns MP4 with the current Hold (s) value.'
                : 'Render Ken Burns MP4 from the beat still image and mark final.'}
            >
              {busy === 'Still as Final' ? <><Spinner size="sm" inline /> …</> : (beat.final?.source === 'still_image' ? '📷 Re-render Still' : '📷 Still as Final')}
            </button>
            {beat.final?.source === 'still_image' ? (
              <button
                type="button"
                class="mn-btn mn-btn-small"
                data-testid={`beat-${index}-undo-final`}
                onClick={guardedClick('Undo Final', onUndoFinal)}
                aria-disabled={busy !== null}
                title="Clear Ken Burns still-as-final and return beat to non-final state"
              >
                {busy === 'Undo Final' ? <><Spinner size="sm" inline /> …</> : '↩ Undo Final'}
              </button>
            ) : null}
          </>
        ) : null}
        {lifecycle === 'final' && beat.final?.source === 'still_image' && beat.final?.file ? (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-still-final-preview`}
            onClick={guardedClick('Preview Still', () => onPreviewOption(-1))}
            aria-disabled={busy !== null}
            title={_magicStillOk
              ? "Preview the magic-on-still composite (✨ magic_still_path)"
              : "Preview the rendered Ken Burns still-as-final MP4"}
          >
            {previewOptIdx === -1 ? '⏸ Preview Still' : '▶ Preview Still'}{
              /* Kim 2026-05-20: 🏁 FINAL badge when the Stitcher's final source
                 is this still-image render. Parity with raw_option + lipsync
                 cases above — every final source type shows the badge. */
              beat.final?.source === 'still_image' ? ' 🏁 FINAL' : ''
            }
          </button>
        ) : null}
        {/* Bug-B2 (spec §2 Topic-2): ✨ magic badge — appears next to Preview Still
            when a magic_still_path is set + file exists on disk. Mirrors the
            magic_video case below. No new button (Kim already has many). */}
        {_magicStillOk ? (
          <span
            class="mn-magic-badge"
            data-testid={`beat-${index}-magic-still-badge`}
            title={`magic_still_path: ${beat.magic_still_path}`}
            style={{
              display: 'inline-block',
              marginLeft: '4px',
              padding: '0 4px',
              borderRadius: '3px',
              background: 'rgba(180, 130, 220, 0.25)',
              color: '#d8b8ee',
              fontSize: '10px',
              fontWeight: 700,
              pointerEvents: 'none',
            }}
          >
            ✨ magic
          </span>
        ) : null}
        {_magicVideoOk ? (
          <span
            class="mn-magic-badge"
            data-testid={`beat-${index}-magic-video-badge`}
            title={`magic_video_path: ${beat.magic_video_path}`}
            style={{
              display: 'inline-block',
              marginLeft: '4px',
              padding: '0 4px',
              borderRadius: '3px',
              background: 'rgba(180, 130, 220, 0.25)',
              color: '#d8b8ee',
              fontSize: '10px',
              fontWeight: 700,
              pointerEvents: 'none',
            }}
          >
            ✨ magic·v
          </span>
        ) : null}
        {lifecycle === 'final' ? (() => {
          // Kim 2026-05-20 follow-up: when a beat's image_path changes via
          // drag-drop AFTER a still_image final was rendered, the final.image_path
          // still points at the OLD image — final.file is now STALE relative
          // to the assigned image. Surface that explicitly so Kim knows to click
          // Re-render Still. Path-stem comparison (both sides are .png base names).
          const _stemOf = (p?: string) => p ? (p.split('/').pop() || '').replace(/\.(png|webp|jpe?g)$/i, '') : '';
          const _currentStem = _stemOf(beat.image_path);
          const _finalStem = _stemOf(beat.final?.image_path);
          const _finalIsStillImageStale = (
            beat.final?.source === 'still_image' &&
            _finalStem && _currentStem && _finalStem !== _currentStem
          );
          // Magic_still goes stale by the same mechanism — the magic was rendered
          // from a specific start image. If image changed, magic is stale.
          // (We don't have the exact reference, but if magic_still_path exists
          // AND final is still_image stale, the magic was rendered from the
          // same prior image — same staleness window.)
          return (
            <span
              class="mn-dim"
              data-testid={`beat-${index}-final-marker`}
              title={
                _finalIsStillImageStale
                  ? `STALE: the rendered final mp4 was made from "${_finalStem}.png" but the current assigned image is "${_currentStem}". Click Re-render Still to refresh. This file (beat.final.file) is what the Stitcher will compose into the video — refresh before stitching.`
                  : `This is what the Stitcher will compose into the video. Source: ${beat.final?.source ?? '?'}. File: ${beat.final?.file ?? '?'}.`
              }
              style={_finalIsStillImageStale ? { color: '#d8a020', fontWeight: 'bold' } : undefined}
            >
              {_finalIsStillImageStale
                ? `⚠ stale final (${beat.final?.source ?? '?'} — re-render)`
                : `✓ final (${beat.final?.source ?? '?'})`}
            </span>
          );
        })() : null}
      </span>

      {/* Trim / Delay group — LD-756: seconds-from-front + seconds-from-end */}
      <span class="mn-beat-button-group" data-testid={`beat-trim-group-${index}`}>
        <span class="mn-beat-button-group-label">Trim front:</span>
        <input
          type="text"
          class="mn-beat-trim-input"
          data-testid={`beat-${index}-trim-front`}
          value={trimFrontSec}
          onFocus={onTrimFrontFocus}
          onBlur={onTrimFrontBlur}
          onInput={(e) => setTrimFrontSec((e.target as HTMLInputElement).value)}
          aria-label="Seconds to trim from the front (0.0 = no trim)"
          placeholder="0.0"
          title="Seconds to trim from the front of the clip"
        />
        <span class="mn-dim">s · back:</span>
        <input
          type="text"
          class="mn-beat-trim-input"
          data-testid={`beat-${index}-trim-back`}
          value={trimBackSec}
          onFocus={onTrimBackFocus}
          onBlur={onTrimBackBlur}
          onInput={(e) => setTrimBackSec((e.target as HTMLInputElement).value)}
          aria-label="Seconds to trim from the end (0.0 = no trim)"
          placeholder="0.0"
          title="Seconds to trim from the END of the clip (NOT an absolute timestamp)"
        />
        <span class="mn-dim">s</span>
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-${index}-trim-apply`}
          onClick={guardedClick('Trim', onApplyTrim)}
          aria-disabled={busy !== null}
        >
          apply
        </button>
        {beat.final?.file ? (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-trim-preview`}
            onClick={guardedClick('Preview Trim', onPreviewTrim)}
            aria-disabled={busy !== null}
            title="Browser-side seek preview between trim in/out (no server round-trip)"
          >
            Preview Trim
          </button>
        ) : null}
        <span class="mn-beat-button-group-label" style="margin-left:8px">Delay:</span>
        <input
          type="text"
          class="mn-beat-trim-input"
          data-testid={`beat-${index}-delay`}
          value={delaySec}
          onFocus={onDelayFocus}
          onBlur={onDelayBlur}
          onInput={(e) => setDelaySec((e.target as HTMLInputElement).value)}
          aria-label="Delay seconds"
          placeholder="0.0"
        />
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-${index}-delay-apply`}
          onClick={guardedClick('Delay', onApplyDelay)}
          aria-disabled={busy !== null}
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
  videoRole: string;  // Bug-A1 (spec §2 Topic-2): scope_video_role threaded to magic URL builders
  onMutated: () => void;
  onInsertAfter: () => void;
  onDeleteBeat: () => void;
}

function BeatCard({ index, beatId, beat, eventId, videoRole, onMutated, onInsertAfter, onDeleteBeat }: BeatCardProps) {
  const initialText = beat.text ?? '';
  const dialogueField = useStoryboardDialogueField({
    eventId,
    beatId,
    externalText: initialText,
  });
  const {
    editRef,
    onInput: onDialogueInput,
    onFocus: onDialogueFocus,
    onBlur: onDialogueBlur,
    readText,
    setDomText,
  } = dialogueField;
  const [status, setStatus] = useState<SaveStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(beat.text_last_updated_at ?? null);
  const [previewOptIdx, setPreviewOptIdx] = useState<number | null>(null);
  const [magicPreviewKind, setMagicPreviewKind] = useState<'still' | 'video' | null>(null);
  // LD-757: sticky sentinel — once set, lipsync <video> stays mounted across previews.
  const [lipsyncMounted, setLipsyncMounted] = useState(false);
  const ensureLipsyncMounted = useCallback(() => setLipsyncMounted(true), []);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Preview source: 0 = lipsync, -1 = still-as-final, >0 = animation option.
  const _isLipsyncShown = previewOptIdx === 0 || lipsyncMounted;
  const _finalFileSrc = beat.final?.file
    ? `${SERVER_BASE}/asset/${beat.final.file}?v=${beat._version ?? 0}`
    : null;
  // P3 LD-505 Phase C: gate every preview src on file_exists !== false
  // so archived/missing files don't 404 → "codec/format not supported".
  // Server-side enrichment populates file_exists on options/lipsync/final.
  const _optChosen = (previewOptIdx !== null && previewOptIdx > 0)
    ? beat.phase_1?.options?.[previewOptIdx - 1]
    : null;
  const _optOk = !!(_optChosen?.file && _optChosen?.file_exists !== false);
  const _lsOk = !!(beat.lipsync?.file && beat.lipsync?.file_exists !== false);
  // Bug-B1 (spec §2 Topic-2, 2026-05-20): magic preview must take priority
  // over still-as-final on Preview Still click. magic outputs are written to
  // event_dir/ (NOT clips_dir/), so they're served via /files?path=... NOT
  // /asset/ (which only serves clips_dir). Gate on magic_*_path_exists
  // (Bug-B3 enrichment) to avoid orphan-reference 404s.
  const _magicStillOk = !!(beat.magic_still_path && beat.magic_still_path_exists !== false);
  const _magicVideoOk = !!(beat.magic_video_path && beat.magic_video_path_exists !== false);
  const _magicStillSrc = _magicStillOk
    ? `${SERVER_BASE}/files?path=${encodeURIComponent(`Production/${eventId}/${beat.magic_still_path}`)}&v=${beat._version ?? 0}`
    : null;
  const _magicVideoSrc = _magicVideoOk
    ? `${SERVER_BASE}/files?path=${encodeURIComponent(`Production/${eventId}/${beat.magic_video_path}`)}&v=${beat._version ?? 0}`
    : null;
  // BUG-A fix (Kim 2026-05-20): the prior fallback `(_finalFileSrc ?? null)`
  // made <video> render by default whenever beat.final.file existed,
  // occluding the <img> element. Result: drag-drop landed on server but
  // Kim saw no visual change because the video was on top of the image.
  // The fix: default to null — <video> only renders on EXPLICIT user
  // action (▶ opt N, ▶ Preview Still, ▶ lipsync, Preview Trim). The IMG
  // is the resting display.
  //
  // Bug-B1 priority chain at previewOptIdx === -1 (Preview Still button):
  //   1. magic_still_path (if still_image final + magic applied)
  //   2. magic_video_path (if video-based final + magic applied)
  //   3. beat.final.file (still_image OR raw_option fallback)
  //   4. null (no preview available)
  // magic_* served via /files NOT /asset (writes to event_dir, not clips_dir).
  // previewVideoSrc is ONLY non-null when there is an ACTIVE preview (previewOptIdx !== null).
  // This ensures the still image always shows when not actively previewing, even when
  // lipsyncMounted=true (LD-757). The LD-757 buffer lives in lipsyncBufferSrc below.
  const previewVideoSrc = previewOptIdx === null
    ? null
    : (previewOptIdx > 0 && _optOk)
        ? `${SERVER_BASE}/asset/${_optChosen!.file}?v=${beat._version ?? 0}`
        : (previewOptIdx === -1
            ? ((magicPreviewKind === 'video'
                ? (_magicVideoSrc ?? _magicStillSrc)
                : magicPreviewKind === 'still'
                  ? (_magicStillSrc ?? _magicVideoSrc)
                  : (_magicVideoSrc ?? _magicStillSrc))
              ?? (beat.final?.source === 'still_image' && beat.final?.file && beat.final?.file_exists !== false
                  ? _finalFileSrc
                  : null))
            : (_lsOk
                ? `${SERVER_BASE}/asset/${beat.lipsync!.file}?v=${beat._version ?? 0}`
                : null));

  // LD-757: when lipsyncMounted=true but no active preview, keep the lipsync <video>
  // in DOM as display:none so decoded frames stay buffered for instant replay.
  const lipsyncBufferSrc = (_isLipsyncShown && _lsOk && previewVideoSrc === null)
    ? `${SERVER_BASE}/asset/${beat.lipsync!.file}?v=${beat._version ?? 0}`
    : null;

  const previewAudioSrc = `${SERVER_BASE}/api/beat/audio/${beatId}?event_id=${eventId}`;

  const resetPlayState = useCallback((reason: string, kind: 'error' | 'info' = 'error', ctx: string = 'Playback') => {
    try { videoRef.current?.pause(); } catch { /* defensive */ }
    try { audioRef.current?.pause(); } catch { /* defensive */ }
    setPreviewOptIdx(null);
    pushToast({ kind, message: `${ctx}: ${reason}`, source: 'sb-playback-fail' });
  }, []);

  const playPromiseRef = useRef<Promise<void> | null>(null);
  const lastClickRef = useRef<number>(0);

  // LD-769/775: await prior play() with 500ms cap, then start next play().
  const awaitPriorPlayWithTimeout = useCallback(async (): Promise<void> => {
    const prior = playPromiseRef.current;
    if (!prior) return;
    let timedOut = false;
    await Promise.race([
      prior.catch(() => {}),
      new Promise<void>((resolve) => setTimeout(() => { timedOut = true; resolve(); }, 500)),
    ]);
    if (timedOut && playPromiseRef.current === prior) {
      playPromiseRef.current = null;
    }
  }, []);

  const safePlay = useCallback(async (el: HTMLMediaElement | null | undefined): Promise<void> => {
    if (!el) return;
    await awaitPriorPlayWithTimeout();
    if (el.paused === false) return;
    const p = el.play();
    playPromiseRef.current = p;
    try {
      await p;
    } finally {
      if (playPromiseRef.current === p) playPromiseRef.current = null;
    }
  }, [awaitPriorPlayWithTimeout]);

  const safePause = useCallback(async (el: HTMLMediaElement | null | undefined): Promise<void> => {
    if (!el) return;
    await awaitPriorPlayWithTimeout();
    try { el.pause(); } catch { /* defensive */ }
  }, [awaitPriorPlayWithTimeout]);

  const handlePlayRejection = useCallback((err: unknown, _context: string, toastCtx: string = 'Playback') => {
    const name = (err as { name?: string } | null)?.name ?? 'unknown';
    if (name === 'AbortError') return;
    if (name === 'NotAllowedError') {
      resetPlayState('browser autoplay blocked — click again to start', 'error', toastCtx);
      return;
    }
    if (name === 'NotSupportedError') {
      resetPlayState('codec/format not supported', 'error', toastCtx);
      return;
    }
    resetPlayState(`browser refused to start (${name})`, 'error', toastCtx);
  }, [resetPlayState]);

  useEffect(() => {
    if (previewOptIdx === null) return;
    const vid = videoRef.current;
    const aud = audioRef.current;
    if (!vid) return;
    const isLipsyncPreview = previewOptIdx === 0;
    const audioDelaySec = Number(
      beat.phase_1?.audio_delay
        ?? beat.audio_delay
        ?? beat.delay_seconds
        ?? 0,
    ) || 0;
    // Kim 2026-05-21: trim must apply on lipsync playback — Kim's mental model
    // is that ▶ lipsync plays the canonical Stitcher output. Stored as absolute
    // trim_start (seek-to) + trim_end (pause-at) in the ORIGINAL audio
    // timeline. The lipsync mp4 has a DIFFERENT timeline (ByteDance preroll
    // padding + our 1.5s tail extension), so absolute trim_end can't be
    // applied directly to vid.currentTime — that cuts off mid-word.
    //
    // For lipsync we translate back-trim into the lipsync mp4 timeline:
    //   back_offset = audio_duration - trim_end   (what user typed in s·back)
    //   pause_at    = lipsync_mp4.duration - back_offset
    // TRIM_SEEK_FIX_20260524: front-trim is now applied server-side (lipsync_start =
    // trim_start + audio_delay in vendor_jobs.py). We no longer seek the lipsync <video>
    // to trim_start — removed trimStartSec. Back-trim (RAF-based pauseAt) is unchanged.
    // New canonical: trim_back is stored directly as relative seconds (2026-05-23 fix).
    // Legacy fallback: derive from audio_duration - trim_end (for old beats without trim_back).
    const trimBackDirect = beat.phase_1?.trim_back;
    const trimEndRaw = beat.phase_1?.trim_end ?? beat.trim_out;
    const trimEndSec: number | null =
      trimEndRaw === null || trimEndRaw === undefined
        ? null
        : (Number.isFinite(Number(trimEndRaw)) ? Number(trimEndRaw) : null);
    const audioDur = Number(beat.audio_duration_s ?? 0) || 0;
    const backOffsetSec = (typeof trimBackDirect === 'number' && trimBackDirect > 0)
      ? trimBackDirect  // New: trim_back IS the offset — no calculation needed
      : (trimEndSec !== null && audioDur > 0)
        ? Math.max(0, audioDur - trimEndSec)  // Legacy: reverse-calculate from audio_duration - trim_end
        : 0;
    // MAGIC_VIDEO_AUDIO_GUARD (Bug 2 fix 2026-05-28): magic_video has lipsync
    // audio baked in. Playing TTS audio on top doubles the dialogue.
    // Guard matches the lipsync guard pattern: if the video being previewed
    // already carries its own audio (optIdx === -1 AND magic_video_path valid),
    // suppress the separate TTS audio element entirely.
    const hasMagicVideoAudio = previewOptIdx === -1 && magicPreviewKind === 'video' && _magicVideoOk;
    if (!isLipsyncPreview && !hasMagicVideoAudio) {
      if (!aud) return;
      aud.currentTime = 0;
    }
    const toastCtx = previewOptIdx === 0
      ? 'Lipsync playback'
      : previewOptIdx === -1
        ? 'Still preview'
        : 'Animation preview';
    // Apply trim to lipsync preview only (audio+video baked into one file).
    // For opt N + still previews, audio and video are separate elements and
    // the existing aud.currentTime=0 reset path doesn't carry trim semantics.
    //
    // Kim 2026-05-21: switched from `timeupdate` listener to RAF polling.
    // `timeupdate` fires only every 200-500ms per browser spec, so back-trim
    // values <200ms slip past — we'd hit the natural file end before the
    // listener fired. RAF runs at display refresh (~16ms), so sub-100ms
    // back-trim windows are honored precisely.
    let rafId: number | null = null;
    let onPlayListener: (() => void) | null = null;
    if (isLipsyncPreview) {
      // LIPSYNC_SEEK_FIX_20260524: seek to max(0, currentLipsyncStart - genLipsyncStart).
      // genLipsyncStart = beat.lipsync.audio_processing.trim_start (lipsync_start at generation
      // = trim_start + audio_delay at submit time, stored by server as ts_used).
      // currentLipsyncStart = current trim_start + current audio_delay.
      // Delta = how far to seek into the existing file to honor current trim settings.
      //
      // Why not always 0: if Kim generated lipsync at trim_start=0 and later changes
      // trim_start=3, the file is NOT pre-trimmed — seeking to 0 shows 3s of unwanted
      // animation before speech. Seeking to 3 shows the correct start.
      //
      // Why not always trim_start: if Kim re-sent lipsync WITH trim baked in (lipsync_start=1.5)
      // and current trim_start=1.5, seekTo = 1.5-1.5 = 0. Correct.
      //
      // Old files without audio_processing: genLipsyncStart defaults to 0,
      // seekTo = currentLipsyncStart (same as pre-TRIM_SEEK_FIX behavior).
      //
      // IDLE_LIPSYNC_SEEK_FIX_20260524: idle lipsync files are generated with
      // audio_delay=0 — the ByteDance job receives TTS starting at t=0 of the
      // idle Kling clip. audio_delay (beat.phase_1.audio_delay) is a COMPOSITE
      // PREVIEW parameter only and is NOT baked into the idle file. Including it
      // in currentLipsyncStart would seek to t=N on a freshly-mounted video that
      // has no buffered data there, causing NotSupportedError from play().
      {
        const isIdleLipsync = (beat.lipsync as { source?: string } | undefined)?.source === 'idle_lipsync';
        const genLipsyncStart = Number(beat.lipsync?.audio_processing?.trim_start ?? 0) || 0;
        const currentTrimStart = Number(beat.phase_1?.trim_start ?? beat.trim_in ?? 0) || 0;
        // For idle lipsync: audio_delay is NOT in the file — always start at trim_start only.
        // For regular lipsync: audio_delay is baked in at submission time.
        const currentLipsyncStart = isIdleLipsync
          ? currentTrimStart
          : currentTrimStart + audioDelaySec;
        const lipsyncSeekTo = Math.max(0, currentLipsyncStart - genLipsyncStart);
        try { vid.currentTime = lipsyncSeekTo; } catch { /* defensive */ }
      }
      // Translate back-trim into lipsync-mp4 timeline. vid.duration is only
      // valid after loadedmetadata fires; gate accordingly. If we never see
      // a finite duration, fall back to NO back-trim (don't truncate the
      // speech) — safer than cutting mid-word per Kim's symptom.
      if (backOffsetSec > 0) {
        const computeAndApplyBack = () => {
          const dur = Number(vid.duration);
          if (!Number.isFinite(dur) || dur <= 0) {
            console.warn(`[lipsync-trim] ${beatId}: vid.duration not ready (${vid.duration}); back-trim NOT applied`);
            return;
          }
          const pauseAt = Math.max(0.01, dur - backOffsetSec);
          console.log(`[lipsync-trim] ${beatId}: audioDur=${audioDur} trimEnd=${trimEndSec} back_offset=${backOffsetSec.toFixed(3)}s lipsync_dur=${dur.toFixed(3)}s pause_at=${pauseAt.toFixed(3)}s`);
          const tick = () => {
            if (!vid || vid.paused || vid.ended) {
              rafId = null;
              return;
            }
            if (vid.currentTime >= pauseAt) {
              console.log(`[lipsync-trim] ${beatId}: pausing at ${vid.currentTime.toFixed(3)}s (target ${pauseAt.toFixed(3)}s)`);
              try { vid.pause(); } catch { /* defensive */ }
              // BUG FIX: reset to 0 so next play starts from the beginning, not the trim
              // endpoint. Also reset previewOptIdx so the button shows ▶ (ready to play).
              try { vid.currentTime = 0; } catch { /* defensive */ }
              setPreviewOptIdx(null);
              rafId = null;
              return;
            }
            rafId = requestAnimationFrame(tick);
          };
          onPlayListener = () => {
            if (rafId === null) rafId = requestAnimationFrame(tick);
          };
          vid.addEventListener('play', onPlayListener);
          // Kick off immediately if already playing (race with safePlay).
          if (!vid.paused) {
            if (rafId === null) rafId = requestAnimationFrame(tick);
          }
        };
        if (Number.isFinite(vid.duration) && vid.duration > 0) {
          computeAndApplyBack();
        } else {
          vid.addEventListener('loadedmetadata', computeAndApplyBack, { once: true });
        }
      } else {
        console.log(`[lipsync-trim] ${beatId}: no back trim (audioDur=${audioDur} trimEnd=${trimEndSec})`);
      }
    }
    safePlay(vid).catch((err) => handlePlayRejection(err, 'effect-play', toastCtx));
    if (!isLipsyncPreview && !hasMagicVideoAudio && aud) {
      if (audioDelaySec > 0) {
        const ms = Math.round(audioDelaySec * 1000);
        const t = window.setTimeout(() => {
          aud.play().catch(() => {});
        }, ms);
        return () => {
          window.clearTimeout(t);
          if (rafId !== null) cancelAnimationFrame(rafId);
          if (onPlayListener) vid.removeEventListener('play', onPlayListener);
        };
      }
      aud.play().catch(() => {});
    }
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      if (onPlayListener) vid.removeEventListener('play', onPlayListener);
    };
  }, [previewOptIdx, magicPreviewKind, beat.phase_1?.audio_delay, beat.audio_delay, beat.delay_seconds, beat.phase_1?.trim_start, beat.phase_1?.trim_end, beat.phase_1?.trim_back, beat.trim_in, beat.trim_out, beat.audio_duration_s, _magicVideoOk, safePlay, handlePlayRejection]);

  useEffect(() => {
    return () => {
      videoRef.current?.pause();
      audioRef.current?.pause();
    };
  }, []);

  const handlePreviewOption = useCallback((optIdx: number, magicKind?: 'still' | 'video' | null) => {
    const nowTs = performance.now();
    if (lastClickRef.current > 0 && nowTs - lastClickRef.current < 250) return;
    lastClickRef.current = nowTs;

    if (optIdx === -1) {
      setMagicPreviewKind(magicKind === undefined ? null : magicKind);
    }

    const isLipsyncPreview = optIdx === 0;
    const isStillFinalPreview = optIdx === -1;
    const previewMagicKind = optIdx === -1
      ? (magicKind === undefined ? magicPreviewKind : magicKind)
      : null;
    // MAGIC_VIDEO_AUDIO_GUARD (Bug 2 fix 2026-05-28): suppress TTS audio when
    // the preview video already has baked-in lipsync audio (magic_video case).
    const hasMagicVideoAudio = isStillFinalPreview && previewMagicKind === 'video' && _magicVideoOk;
    const file = isLipsyncPreview
      ? beat.lipsync?.file
      : (isStillFinalPreview
          // Bug-B1 fix: magic_still_path / magic_video_path satisfy the guard
          // even when beat.final?.file is absent (e.g. beat not yet in 'final'
          // lifecycle). previewVideoSrc resolves magic_*_path via the priority
          // chain; we just need a truthy value here to avoid the early return.
          ? (beat.magic_still_path || beat.magic_video_path || beat.final?.file)
          : beat.phase_1?.options?.[optIdx - 1]?.file);
    if (!file) return;
    const vid = videoRef.current;
    const aud = audioRef.current;
    if (previewOptIdx === optIdx) {
      if (vid && !vid.paused) {
        safePause(vid).catch(() => {});
        if (!isLipsyncPreview && !hasMagicVideoAudio) safePause(aud).catch(() => {});
        // LIPSYNC_PLAY_STOP_20260524: always reset to ▶ state on explicit user
        // stop click. Prior code left previewOptIdx=0 (pause-to-resume intent) but
        // a stalled video has vid.paused===false yet never advances — user sees ⏸
        // with nothing playing and no escape. Resetting to null here makes ⏸
        // a reliable "stop" button: next ▶ click always restarts cleanly.
        setPreviewOptIdx(null);
      } else {
        // BUG FIX: if the video has ended, currentTime is at duration — play() immediately
        // re-fires 'ended' with no visible frames. Reset to 0 first so replay works.
        if (vid?.ended) {
          try { vid.currentTime = 0; } catch { /* defensive — some browsers throw on seeks */ }
        }
        safePlay(vid).catch((err) => handlePlayRejection(err, 'toggle-play'));
        if (!isLipsyncPreview && !hasMagicVideoAudio) safePlay(aud).catch((err) => handlePlayRejection(err, 'toggle-play-aud'));
      }
      return;
    }
    safePause(vid).catch(() => {});
    if (!isLipsyncPreview && !hasMagicVideoAudio) safePause(aud).catch(() => {});
    setPreviewOptIdx(optIdx);
  }, [previewOptIdx, magicPreviewKind, beat.phase_1?.options, beat.lipsync?.file, beat.final?.file, beat.magic_still_path, beat.magic_video_path, beat.magic_video_path_exists, _magicVideoOk, safePlay, safePause, handlePlayRejection]);

  const handlePreviewEnded = useCallback(() => {
    // MAGIC_STILL_AUDIO_TAIL_FIX (Kim 2026-05-27): magic_still video (previewOptIdx === -1)
    // may be shorter than the beat audio (e.g. 4.0s video vs 4.24s TTS).
    // When video ends before audio, DO NOT stop the audio — freeze at last frame
    // and let audio run to its natural end. Audio's 'ended' event (handleAudioEnded)
    // will reset the UI once audio completes.
    const aud = audioRef.current;
    if (previewOptIdx === -1 && aud && !aud.ended && !aud.paused) {
      // Video ended early; audio still playing — keep playing state, return early.
      // Browser already paused the <video> at its last frame automatically.
      return;
    }
    aud?.pause();
    // BUG FIX: reset currentTime so next play() starts from beginning, not the end.
    // If the video stays mounted (LD-757 lipsyncMounted), play() on currentTime=duration
    // immediately re-fires 'ended' with no visible frames.
    if (videoRef.current) {
      try { videoRef.current.currentTime = 0; } catch { /* defensive */ }
    }
    // LD-757: reset UI only; lipsyncMounted keeps <video> in DOM.
    setPreviewOptIdx(null);
  }, [previewOptIdx]);

  // MAGIC_STILL_AUDIO_TAIL_FIX (Kim 2026-05-27): fires when audio outlasts the
  // magic_still video. handlePreviewEnded returned early to let audio continue;
  // now that audio has finished naturally, reset play state.
  const handleAudioEnded = useCallback(() => {
    // Hold the still frame for 2s after audio ends, then reset UI.
    // Gives the viewer a moment to "land" on the final frame before it disappears.
    window.setTimeout(() => {
      if (videoRef.current) {
        try { videoRef.current.currentTime = 0; } catch { /* defensive */ }
      }
      setPreviewOptIdx(null);
    }, 2000);
  }, []);

  // LIPSYNC_PLAY_STOP_20260524: reset play state when the <video> element fires
  // an error event. Without this, a 404 / codec decode error fires 'error' but
  // nothing handles it — previewOptIdx stays 0 and the button is permanently
  // stuck as ⏸. Surface the error message via resetPlayState (toast + null reset).
  const onPreviewVideoError = useCallback(() => {
    const vid = videoRef.current;
    const code = vid?.error?.code;
    const msg = vid?.error?.message || `MEDIA_ERR code=${code ?? '?'}`;
    console.warn(`[StoryboardTab] ${beatId} <video> error:`, vid?.error);
    resetPlayState(`video load failed: ${msg}`, 'error', 'Lipsync playback');
  }, [resetPlayState, beatId]);

  const onSpeakerChange = async (e: Event) => {
    const target = e.target as HTMLSelectElement | null;
    const nextSpeaker = (target?.value ?? '').trim();
    if (!nextSpeaker || nextSpeaker === (beat.speaker ?? '')) return;
    const result = await pathappPatch(activeScope.value, 'beat_update_speaker', {
      beat: beatId,
      speaker: nextSpeaker,
    });
    if (result.ok) {
      onMutated();
    } else {
      const msg = formatMutationError(result, 'Speaker save failed');
      if (msg) {
        pushToast({
          kind: 'error',
          message: msg,
          source: 'speaker-update',
        });
      }
    }
  };

  const onBlur = async () => {
    onDialogueBlur();
    const next = readText();
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
      clearStoryboardDialogueShadow(eventId, beatId);
      pushToast({ kind: 'success', message: 'Dialogue saved', source: 'beat-dialogue-save' });
      setTimeout(() => setStatus((s) => (s === 'saved' ? 'idle' : s)), 2000);
    } else {
      setStatus('error');
      setErrorMsg(result.error ?? `HTTP ${result.status}`);
    }
  };

  const onPauseTag = async () => {
    const current = readText() || beat.text || '';
    const newText = current.includes('[pause]') ? current : `${current} [pause]`.trim();
    setDomText(newText);
    setStatus('saving');
    setErrorMsg(null);
    const result = await pathappPatch(activeScope.value, 'beat_update_text', {
      beat: beatId,
      text: newText,
    }, { skip_tts_regen: true });
    if (result.ok) {
      setStatus('saved');
      clearStoryboardDialogueShadow(eventId, beatId);
      pushToast({ kind: 'success', message: 'Pause tag saved (TTS skipped)', source: 'beat-pause-tag' });
      onMutated();
      setTimeout(() => setStatus((s) => (s === 'saved' ? 'idle' : s)), 2000);
    } else {
      setStatus('error');
      setErrorMsg(result.error ?? `HTTP ${result.status}`);
    }
  };

  const onParentheticalPick = async (p: string) => {
    const current = readText() || beat.text || '';
    const newText = current ? `${p} ${current}` : p;
    setDomText(newText);
    setStatus('saving');
    setErrorMsg(null);
    const result = await pathappPatch(activeScope.value, 'beat_update_text', {
      beat: beatId,
      text: newText,
    });
    if (result.ok) {
      setStatus('saved');
      setSavedAt(new Date().toISOString());
      clearStoryboardDialogueShadow(eventId, beatId);
      onMutated();
      setTimeout(() => setStatus((s) => (s === 'saved' ? 'idle' : s)), 2000);
    } else {
      setStatus('error');
      setErrorMsg(result.error ?? `HTTP ${result.status}`);
      const msg = formatMutationError(result, 'Parenthetical insert failed');
      if (msg) {
        pushToast({
          kind: 'error',
          message: msg,
          source: 'parenthetical-insert',
        });
      }
    }
  };

  const onKimDoneToggle = async () => {
    const result = await pathappPatch(activeScope.value, 'beat_done_toggle', { beat_id: beatId });
    if (result.ok) {
      onMutated();
    } else {
      const msg = formatMutationError(result, 'Kim done toggle failed');
      if (msg) {
        pushToast({
          kind: 'error',
          message: msg,
          source: 'kim-done-toggle',
        });
      }
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

  const storyboardStillPath = beat.image_path
    ? `Production/${eventId}/${beat.image_path}`
    : null;
  let storyboardVideoPath: string | undefined;
  if (beat.lipsync?.file) storyboardVideoPath = beat.lipsync.file;
  else if (beat.phase_1?.options && beat.phase_1.selected_option !== undefined) {
    const opt = beat.phase_1.options[beat.phase_1.selected_option - 1];
    if (opt?.file) storyboardVideoPath = opt.file;
  }

  return (
    <li
      class="mn-beat-card"
      data-testid={`beat-card-${index}`}
      data-beat-id={beatId}
    >
      <div class="mn-beat-meta">
        <span class="mn-beat-index">#{index + 1}</span>
        <span class="mn-beat-anchor">{beatId}</span>
        <select
          class="mn-beat-speaker"
          data-testid={`beat-speaker-${index}`}
          value={beat.speaker ?? ''}
          onChange={onSpeakerChange}
          aria-label={`Speaker for beat ${beatId}`}
          title="Change speaker (triggers stale TTS — click Regen Audio to apply)"
        >
          {(beat.speaker && !KNOWN_SPEAKERS.includes(beat.speaker)) ? (
            // Preserve legacy/unknown speaker value so the field doesn't
            // silently switch to the first option on load. Kim can pick a
            // canonical name to migrate. Two-write speaker dual-store keeps
            // the on-disk value canonicalized at every beat-touch.
            <option value={beat.speaker}>{beat.speaker}</option>
          ) : null}
          {!beat.speaker ? <option value="">— speaker —</option> : null}
          {KNOWN_SPEAKERS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {beat.text_modified_after_tts ? (
          <span class="mn-beat-stale-tts" data-testid={`beat-stale-tts-${index}`}>
            stale TTS
          </span>
        ) : null}
        <label class="mn-kim-done-wrap" title={beat.kim_done ? 'Kim marked done — uncheck to unset' : 'Click to mark beat as Kim-reviewed-done'}>
          <input
            type="checkbox"
            data-testid={`kim-done-checkbox-${beatId}`}
            checked={!!beat.kim_done}
            onChange={() => void onKimDoneToggle()}
          />
          <span class="kim-done-label">{beat.kim_done ? '✓ Kim done' : 'Kim done?'}</span>
        </label>
        <span
          class={indicatorClass}
          data-testid={`beat-save-${index}`}
          data-save-status={status}
        >
          {indicatorLabel}
        </span>
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`sb-delete-beat-${index}`}
          onClick={onDeleteBeat}
          aria-label={`Delete beat ${beatId}`}
          title="Delete this beat"
          style="margin-left:auto"
        >
          ✕
        </button>
      </div>
      <audio
        ref={audioRef}
        src={previewAudioSrc}
        preload="auto"
        style={{ display: 'none' }}
        data-testid={`beat-audio-hidden-${index}`}
        onEnded={handleAudioEnded}
      />
      <BeatImageHolder
        index={index}
        beatId={beatId}
        beat={beat}
        eventId={eventId}
        onMutated={onMutated}
        previewVideoSrc={previewVideoSrc}
        lipsyncBufferSrc={lipsyncBufferSrc}
        videoRef={videoRef as RefObject<HTMLVideoElement>}
        onPreviewEnded={handlePreviewEnded}
        onPreviewVideoError={onPreviewVideoError}
        onImageReassigned={() => {
          // T4-3 (2026-05-19): dismiss lipsync preview on drag-drop image
          // re-assign so the new image becomes immediately visible.
          // Without this, lipsync video (LD-757-persistent once mounted)
          // occludes the IMG element and visually the drop looks like a no-op.
          setPreviewOptIdx(null);
          setLipsyncMounted(false);
        }}
      />
      <div class="mn-beat-text-row">
        <SuggestParentheticalDropdown onPick={(p) => void onParentheticalPick(p)} />
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-pause-tag-${index}`}
          onClick={() => void onPauseTag()}
          title="Insert [pause] without TTS regen"
        >
          [pause]
        </button>
        <p
          ref={editRef}
          class="mn-beat-text mn-beat-editable"
          data-testid={`beat-text-${index}`}
          contentEditable
          spellcheck
          onInput={onDialogueInput}
          onFocus={onDialogueFocus}
          onBlur={onBlur}
        />
      </div>
      <BeatButtonRow
        index={index}
        beatId={beatId}
        eventId={eventId}
        beat={beat}
        videoRole={videoRole}
        {...(savedAt ? { cacheBust: savedAt } : {})}
        onMutated={onMutated}
        previewOptIdx={previewOptIdx}
        onPreviewOption={handlePreviewOption}
        onEnsureLipsyncMounted={ensureLipsyncMounted}
      />
      <BeatMagicButtons
        index={index}
        beatId={beatId}
        eventId={eventId}
        videoRole={videoRole}
        stillImagePath={storyboardStillPath}
        videoSourcePath={storyboardVideoPath ?? null}
        magicStillPath={beat.magic_still_path}
        magicVideoPath={beat.magic_video_path}
        onPreviewMagicStill={() => handlePreviewOption(-1, 'still')}
        onPreviewMagicVideo={() => handlePreviewOption(-1, 'video')}
        onMagicStillCleared={() => { onMutated(); }}
      />
      <div class="mn-sb-insert-after" data-testid={`sb-insert-after-${index}`}>
        <button
          class="mn-btn mn-btn-small mn-sb-insert-after-btn"
          data-testid={`sb-insert-after-btn-${index}`}
          onClick={onInsertAfter}
          aria-label={`Insert beat after ${beatId}`}
          title="Insert beat after this one"
        >
          + Insert beat
        </button>
      </div>
    </li>
  );
}

// ----------------------------------------------------------------
// CC-16 — Storyboard image-holder drop zone (Phase A primitive; Phase B SB-14
// extends).
//
// Per spec §4 Phase A: define `mn-storyboard-image-drop-zone` CSS class +
// onDrop handler accepting `lib-image` payload. The actual <img> rendering
// + Assign/Inject buttons land in Phase B SB-14; Phase A stands up the drop
// surface so library-tile drag works end-to-end and Phase B can layer on
// the rest without changing this component's drop contract.
//
// Per LD-656 PHASED_DELIVERY_PRIMITIVE_HOOKS_S5_5C_V1: this is phased
// architecture, NOT a Rule 19 shortcut. Phase A scope is complete; Phase B
// SB-14 is separate scope with its own ship plan.
// ----------------------------------------------------------------

interface BeatImageHolderProps {
  index: number;
  beatId: string;
  beat: BeatState;
  eventId: string;
  onMutated: () => void;
  previewVideoSrc?: string | null;
  videoRef?: RefObject<HTMLVideoElement>;
  onPreviewEnded?: () => void;
  /** LIPSYNC_PLAY_STOP_20260524: called when the <video> element fires an error
   * event (404, codec failure) so BeatCard can reset previewOptIdx to null. */
  onPreviewVideoError?: () => void;
  /** T4-3 (2026-05-19): on successful drag-drop image-assign, parent dismisses
   * lipsync preview so the new image becomes visible. Once `lipsyncMounted`
   * flips true (LD-757 persistence), the IMG element stops rendering — only
   * the lipsync VIDEO shows. Drop succeeds in state but visually nothing
   * changes because the video is occluding. */
  onImageReassigned?: () => void;
  /** LD-757: lipsync URL to keep buffered in a hidden <video> when no preview is active.
   * Non-null only when lipsyncMounted=true && previewVideoSrc===null. */
  lipsyncBufferSrc?: string | null;
}

function BeatImageHolder({ index, beatId, beat, eventId, onMutated, previewVideoSrc, lipsyncBufferSrc, videoRef, onPreviewEnded, onPreviewVideoError, onImageReassigned }: BeatImageHolderProps) {
  const stillPath = beat.image_path;
  const hasImage = !!stillPath;
  // Blocker #145 / DS-22: image_override persisted but thumb stayed stale when
  // image_path unchanged or browser cached same URL — bust on beat._version.
  const imgSrc = stillPath
    ? `${SERVER_BASE}/files?path=${encodeURIComponent(`Production/${eventId}/${stillPath}`)}&v=${beat._version ?? 0}`
    : undefined;

  const dropHandlers = makeDropTarget(
    async (payload) => {
      if (payload.kind !== 'lib-image') return;
      // 6-Layer wiring: backend handler is `_handle_assign_image` in
      // production_server.py (registered route `assign_image` on pathappPatch
      // dispatch table). [INFERRED — verify against production_server.py at
      // commit time; line drifts with file edits.] Coverage:
      // e2e/storyboard_v59_assign_image_drop.spec.ts asserts the drop →
      // PATCH `assign_image` → server-side onMutated() round-trip.
      // BUG-A UX clarifier (Kim 2026-05-20): if user drops the SAME image
      // that's already on the beat, the visual won't change because the
      // assigned image didn't change. Compare prior image_path stem so the
      // toast tells Kim "no change" instead of misleading "assigned".
      const priorStem = beat.image_path
        ? beat.image_path.split('/').pop()?.replace(/\.(webp|png|jpe?g)$/i, '')
        : undefined;
      const isSameImage = priorStem === payload.lib_key;
      const result = await pathappPatch(activeScope.value, 'assign_image', {
        beat: beatId,
        image_key: payload.lib_key,
      });
      if (result.ok) {
        pushToast({
          kind: isSameImage ? 'info' : 'success',
          message: isSameImage
            ? `Image ${payload.lib_key} was already on ${beatId} — no visual change`
            : `Image ${payload.lib_key} assigned to ${beatId}`,
          source: 'sb-image-drop',
        });
        // T4-3: dismiss lipsync preview so the new image is visible.
        // Without this, the lipsync video keeps occluding the IMG element
        // (LD-757 persistence) and the user sees no visual change.
        onImageReassigned?.();
        // BUG-A in-use highlight refresh: fire global event so LibraryPanel
        // re-fetches its in-use set + highlights the now-active tile.
        window.dispatchEvent(new CustomEvent('mn:image-assigned', {
          detail: { beat_id: beatId, image_key: payload.lib_key },
        }));
        onMutated();
      } else {
        const msg = formatMutationError(result, 'Image assign failed');
        if (msg) {
          pushToast({
            kind: 'error',
            message: msg,
            source: 'sb-image-drop-error',
          });
        }
      }
    },
    (p) => p.kind === 'lib-image',
  );
  const dropRef = useRef<HTMLDivElement>(null);
  useDropTargetCapture(dropRef, dropHandlers, [dropHandlers]);

  return (
    <div
      ref={dropRef}
      class={`mn-storyboard-image-drop-zone mn-drop-target${hasImage ? ' has-image' : ''}${previewVideoSrc ? ' mn-previewing' : ''}`}
      data-testid={`beat-image-zone-${index}`}
      data-beat-id={beatId}
    >
      {(previewVideoSrc || lipsyncBufferSrc) ? (
        <div data-testid={`beat-preview-video-${index}`} style={{ display: 'contents' }}>
          {/* Single video element: visible when actively previewing (previewVideoSrc),
              display:none when only buffering (lipsyncBufferSrc). LD-757 keeps decoded
              frames in browser memory for instant replay without file reload. */}
          <video
            {...(videoRef ? { ref: videoRef } : {})}
            src={previewVideoSrc ?? lipsyncBufferSrc!}
            class={`mn-storyboard-preview-video ${PLAYBACK_VIDEO_ANTI_BANDING_CLASS}`}
            style={previewVideoSrc ? undefined : { display: 'none' }}
            playsInline
            preload="auto"
            onEnded={onPreviewEnded}
            onError={onPreviewVideoError}
            data-testid={`beat-${index}-lipsync-video`}
          />
          {/* Show still image when video is in buffer-only mode (hidden) */}
          {!previewVideoSrc && hasImage && imgSrc && (
            <img
              src={imgSrc}
              alt={`beat ${beatId} image`}
              class="mn-storyboard-image-thumb"
              loading="lazy"
            />
          )}
        </div>
      ) : hasImage && imgSrc ? (
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
      stitcherRefreshTick.value += 1; // notify StitcherTab to re-fetch after auto-populate
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
// FadeDivider — crossfade control between beats
// ----------------------------------------------------------------

function FadeDivider({
  beatId,
  eventId,
  videoRole,
  fadeMs,
  onMutated,
}: {
  beatId: string;
  eventId: string;
  videoRole: string;
  fadeMs: number | null | undefined;
  onMutated: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const effectiveFade = fadeMs ?? 0;

  const handleClick = async () => {
    if (saving) return;
    const next = effectiveFade === 0 ? 500 : 0;
    setSaving(true);
    try {
      // Endpoint: /api/v2/beat/<beat_id>/patch — handles _V2_ALLOWED_FIELDS including fade_after_ms.
      // Scope keys: event_id (legacy alias for scope_event_id per scope_router.py:129) +
      //             scope_video_role / scope_target_video (LD-461 canonical pair).
      // Rule 32: absolute URL required (file:// launch context).
      await fetch(`${SERVER_BASE}/api/v2/beat/${encodeURIComponent(beatId)}/patch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_id: eventId,
          scope_video_role: videoRole,
          scope_target_video: videoRole,
          field: 'fade_after_ms',
          value: next === 0 ? null : next,
        }),
      });
      onMutated();
    } finally {
      setSaving(false);
    }
  };

  const hasFade = effectiveFade > 0;

  return (
    <li
      class={'mn-beat-fade-divider' + (hasFade ? ' mn-beat-fade-divider--active' : '')}
      onClick={handleClick}
      title={hasFade ? effectiveFade + 'ms crossfade — click to remove' : 'Click to add 500ms crossfade'}
      role="button"
      aria-label={hasFade ? effectiveFade + 'ms crossfade active' : 'No fade — click to add'}
      style={{ cursor: saving ? 'wait' : 'pointer' }}
    >
      <span class="mn-beat-fade-label">
        {saving ? '…' : hasFade ? '↔ ' + effectiveFade + 'ms fade' : '+ fade'}
      </span>
    </li>
  );
}

// ----------------------------------------------------------------
// Main tab
// ----------------------------------------------------------------

export function StoryboardTab() {
  const state = storyboardState.value as EventState | null;
  const error = storyboardError.value;
  const loading = storyboardLoading.value && !storyboardSessionHasCache();
  const [refreshTick, setRefreshTick] = useState(0);
  const [deleteConfirmBeatId, setDeleteConfirmBeatId] = useState<string | null>(null);
  // Batch end-frame generator state (spec BATCH_END_FRAME_GENERATE_20260520_v1, LD-815)
  const [batchInFlight, setBatchInFlight] = useState<boolean>(false);
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number; failed: number; skipped: number } | null>(null);
  const batchCancelRef = useRef<boolean>(false);

  // Local mutation refresh — scope/rehydrate handled by ProducerSessionCoordinator.
  useEffect(() => {
    if (refreshTick <= 0) return;
    void ensureStoryboardSession(
      activeScope.value.event_id,
      activeProjectType.value,
      activeMilestoneId.value,
      { force: true },
    );
  }, [refreshTick]);

  // S5 — refresh on path_picker submit success.
  // Security (CodeQL js/missing-origin-check alert #1, real source line):
  // gate postMessage on e.origin === window.location.origin to refuse
  // cross-origin senders (malicious iframes / window openers).
  // MED-5: drop the falsy `e.origin &&` short-circuit so a
  // missing-Origin sender (file:// frames, certain native callers) is
  // also rejected. Strict equality only.
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
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

  // Batch end-frame generator (spec BATCH_END_FRAME_GENERATE_20260520_v1, LD-815).
  // Filter: beats in CURRENT activeTargetVideo partition with selected_option set,
  // image_path set+exists, and end_frame_path missing/non-existent. Excludes
  // image-missing beats (cursor R1 — else wasted START_IMAGE_REQUIRED toasts).
  const batchEligibleBeats = useMemo(() => {
    if (!state) return [] as Array<{ beat_id: string }>;
    const role = activeTargetVideo.value;
    const beats = (state.videos as any)?.[role]?.beats || {};
    const result: Array<{ beat_id: string }> = [];
    for (const [bid, b] of Object.entries(beats) as Array<[string, any]>) {
      if (b?.phase_1?.selected_option == null) continue;
      if (!b?.image_path || b?.image_path_exists === false) continue;
      if (b?.end_frame_path && b?.end_frame_path_exists !== false) continue;
      result.push({ beat_id: bid });
    }
    return result;
  }, [state, activeTargetVideo.value, refreshTick]);

  const onBatchEndFrames = async () => {
    if (batchInFlight) return;
    const candidateList = [...batchEligibleBeats];  // freeze list at click time
    if (candidateList.length === 0) return;
    // Freeze scope at batch start — cursor R1 defense vs stale React closure
    // mid-loop. Even if Kim somehow changes VideoSelector via keyboard during
    // the loop, this iteration uses the role she clicked Batch in.
    const frozenRole = activeTargetVideo.value;
    const frozenEventId = activeScope.value.event_id;

    if (candidateList.length > 5) {
      const cost = (candidateList.length * 0.04).toFixed(2);
      const ok = window.confirm(
        `This will generate end frames for ${candidateList.length} beats via OpenAI gpt-image-1.\n\n` +
        `Estimated cost: ~$${cost} (${candidateList.length} × $0.04).\n\n` +
        `Sequential, ~5–15 sec per beat. Keep this tab open until the batch completes — closing/navigating away stops the loop.\n\n` +
        `Continue?`
      );
      if (!ok) return;
    }

    batchCancelRef.current = false;
    setBatchInFlight(true);
    setBatchProgress({ done: 0, total: candidateList.length, failed: 0, skipped: 0 });

    let done = 0;
    let failed = 0;
    let skipped = 0;
    for (const item of candidateList) {
      if (batchCancelRef.current) {
        pushToast({ kind: 'info', message: `Batch cancelled. Processed ${done}/${candidateList.length}.`, source: 'batch-endframe' });
        break;
      }
      // Per-iteration freshness re-read — someone else may have generated
      // this beat's end_frame_path between batch-start and this iteration.
      try {
        const freshRes = await apiGet<EventState>('v2_event_state', { event_id: frozenEventId });
        if (freshRes.ok && freshRes.data) {
          const freshBeat = (freshRes.data.videos as any)?.[frozenRole]?.beats?.[item.beat_id];
          if (freshBeat?.end_frame_path && freshBeat?.end_frame_path_exists !== false) {
            skipped += 1;
            setBatchProgress({ done, total: candidateList.length, failed, skipped });
            continue;
          }
        }
      } catch {
        // Freshness fetch failure is non-fatal — proceed with click-time decision.
      }
      try {
        const resp = await fetch(ENDPOINTS.beat_preview_end_frame, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scope_event_id: frozenEventId,
            scope_video_role: frozenRole,
            beat_id: item.beat_id,
          }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data?.ok) {
          failed += 1;
          pushToast({
            kind: 'error',
            message: `Batch ${item.beat_id} failed: ${data?.error_message || data?.error || `HTTP ${resp.status}`}`,
            source: 'batch-endframe',
          });
        } else {
          done += 1;
          // Live thumbnail refresh — per-iteration onMutated equivalent.
          setRefreshTick((n) => n + 1);
        }
      } catch (e) {
        failed += 1;
        pushToast({
          kind: 'error',
          message: `Batch ${item.beat_id}: ${(e as Error).message}`,
          source: 'batch-endframe',
        });
      }
      setBatchProgress({ done, total: candidateList.length, failed, skipped });
    }

    setBatchInFlight(false);
    setBatchProgress(null);
    batchCancelRef.current = false;
    pushToast({
      kind: failed === 0 ? 'success' : 'warning',
      message: `Batch end frames complete: ✓ ${done} · ✗ ${failed} · ⏭ ${skipped} (of ${candidateList.length})`,
      source: 'batch-endframe',
    });
  };

  const onCancelBatch = () => {
    batchCancelRef.current = true;
  };

  const executeDeleteBeat = async () => {
    const beatId = deleteConfirmBeatId;
    if (!beatId) return;
    setDeleteConfirmBeatId(null);
    const result = await pathappPatch(activeScope.value, 'v2_beat_delete', {
      beat_id: beatId,
    });
    if (result.ok) {
      pushToast({ kind: 'info', message: `Beat ${beatId} deleted`, source: 'sb-delete' });
      setRefreshTick((n) => n + 1);
    } else {
      const msg = formatMutationError(result, 'Delete failed');
      if (msg) {
        pushToast({ kind: 'error', message: msg, source: 'sb-delete-error' });
      }
    }
  };

  const onAddBeat = async (afterBeatId: string) => {
    const result = await pathappPatch(activeScope.value, 'v2_beat_create', {
      insert_after: afterBeatId,
    });
    if (result.ok) {
      pushToast({ kind: 'info', message: 'Beat added', source: 'sb-add' });
      setRefreshTick((n) => n + 1);
    } else {
      const msg = formatMutationError(result, 'Add failed');
      if (msg) {
        pushToast({ kind: 'error', message: msg, source: 'sb-add-error' });
      }
    }
  };

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
        <>
          {/* Batch end-frame generator (spec BATCH_END_FRAME_GENERATE_20260520_v1, LD-815).
              Single click → loops over every beat in current video role that
              has selected_option + image but no end_frame_path. */}
          <div
            class="mn-batch-endframe-bar"
            data-testid="batch-endframe-bar"
            style={{
              padding: '8px 12px',
              marginBottom: '8px',
              background: 'rgba(74, 138, 138, 0.08)',
              border: '1px solid rgba(74, 138, 138, 0.3)',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            {batchInFlight && batchProgress ? (
              <>
                <span style={{ fontSize: '12px' }}>
                  <Spinner size="sm" inline /> Batch end frames: {batchProgress.done} of {batchProgress.total}
                  {batchProgress.failed > 0 ? ` · ✗ ${batchProgress.failed}` : ''}
                  {batchProgress.skipped > 0 ? ` · ⏭ ${batchProgress.skipped}` : ''}
                </span>
                <button
                  type="button"
                  class="mn-btn mn-btn-small"
                  data-testid="batch-endframe-cancel"
                  onClick={onCancelBatch}
                  title="Stop submitting new beats. Any OpenAI call already in flight will complete."
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                type="button"
                class="mn-btn mn-btn-small"
                data-testid="batch-endframe-button"
                onClick={onBatchEndFrames}
                disabled={batchEligibleBeats.length === 0}
                title={
                  batchEligibleBeats.length === 0
                    ? 'All beats in this video already have an end frame, or no beats have a selected option + start image.'
                    : `Generate end frames via ChatGPT for ${batchEligibleBeats.length} beat(s) sequentially. ~$0.04 × ${batchEligibleBeats.length} = ~$${(batchEligibleBeats.length * 0.04).toFixed(2)}. Keep this tab open until complete. Each iteration re-reads state for freshness.`
                }
              >
                ✏ Batch end frames ({batchEligibleBeats.length} beat{batchEligibleBeats.length === 1 ? '' : 's'})
              </button>
            )}
          </div>
          <ol class="mn-beat-list" data-testid="beat-list">
            {beatList.map((b, i) => (
              <Fragment key={b.beat_id}>
                <BeatCard
                  index={i}
                  beatId={b.beat_id}
                  beat={b}
                  eventId={eventId}
                  videoRole={activeTargetVideo.value}
                  onMutated={() => setRefreshTick((n) => n + 1)}
                  onInsertAfter={() => void onAddBeat(b.beat_id)}
                  onDeleteBeat={() => setDeleteConfirmBeatId(b.beat_id)}
                />
                {i < beatList.length - 1 && (
                  <FadeDivider
                    beatId={b.beat_id}
                    eventId={eventId}
                    videoRole={activeTargetVideo.value}
                    fadeMs={b.phase_1 ? b.phase_1.fade_after_ms : null}
                    onMutated={() => setRefreshTick((n) => n + 1)}
                  />
                )}
              </Fragment>
            ))}
          </ol>
        </>
      )}
      <footer class="mn-pane-footer">
        <SendOutButton />
        <p class="mn-dim mn-readonly-banner" data-testid="storyboard-readonly">
          {beatList.length === 0
            ? 'Read-only — no beats to edit.'
            : `${beatList.length} beats — dialogue edit live (saves through pathappPatch).`}
        </p>
      </footer>
      <Modal
        id="sb-delete-beat"
        title="Delete beat?"
        open={deleteConfirmBeatId !== null}
        onClose={() => setDeleteConfirmBeatId(null)}
        footer={
          <>
            <button
              type="button"
              class="mn-btn mn-btn-danger"
              data-testid="sb-delete-beat-confirm"
              onClick={() => void executeDeleteBeat()}
            >
              Delete
            </button>
            <button
              type="button"
              class="mn-btn"
              data-testid="sb-delete-beat-cancel"
              onClick={() => setDeleteConfirmBeatId(null)}
            >
              Cancel
            </button>
          </>
        }
      >
        <p>Delete <strong>{deleteConfirmBeatId}</strong>? This cannot be undone.</p>
      </Modal>
    </section>
  );
}
