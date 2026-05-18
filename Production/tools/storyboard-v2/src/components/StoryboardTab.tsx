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
import {
  activeScope,
  activeTargetVideo,
  activeProjectType,
  activeMilestoneId,
  scopeKey,
} from '../state/scope';
import { apiGet, pathappPatch } from '../api/client';
import { SERVER_BASE } from '../api/endpoints';
import { makeDropTarget } from '../utils/dragdrop';
import { Spinner } from './ui/Spinner';
import { pushToast } from './ui/Toast';
import { Modal } from './ui/Modal';
import { BeatAudioPreview } from './BeatAudioPreview';

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
  // S5 — preferred video source for magic_video (lipsync, then animation).
  // file_mtime (epoch seconds, integer) is projected by the bootstrap endpoint
  // `_handle_v2_event_state` from os.stat(animation_clips/<lipsync.file>).
  // Compared against audio_regenerated_at to gate the ▶ lipsync play button
  // per LD STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1. Missing → defensive
  // "stale" default (older server, or file disappeared mid-render).
  lipsync?: { file?: string; status?: string; file_mtime?: number };
  // phase_1 is the server-canonical persistence root for per-beat animation
  // state. `audio_delay` (the Video Lead-in slider) lives here — bootstrap
  // /api/v2/event/<id>/state returns the raw state.json so this is where the
  // React render path must read from. Spec id=225 §5.1 Edit 4 +
  // STORYBOARD_AUDIO_DELAY_READ_NESTED_PATH_V2.
  phase_1?: {
    selected_option?: number;
    options?: Array<{ file?: string; status?: string }>;
    audio_delay?: number;
    // LD-749 POST_LIPSYNC_TRIM_FEATURE_SPEC_V1 (re-shipped 2026-05-17): server-
    // canonical persistence path for trim window. _handle_beat_trim writes
    // here; _serve_lipsync_trimmed reads here. Bootstrap returns raw state.json
    // so React must read trim from nested phase_1 (same as audio_delay per
    // LD-723). Legacy top-level `trim_in`/`trim_out` (LD-160) kept as fallback.
    trim_start?: number;
    trim_end?: number | null;
  };
  // S5.5e — fields read by the beat-level state machine (LD BEAT_LIFECYCLE_STATE_MACHINE_V1).
  // beat.final block is the "is final?" signal per Cursor v8 (NOT a use_as_final boolean).
  // Server writes this at production_server.py:10733-10747 with shape:
  //   { source: "raw_option" | "lipsync", source_option, file, approved_at }
  final?: {
    source?: string;
    source_option?: number;
    file?: string;
    approved_at?: string;
    // LD-761 + LD-777: Ken Burns still-as-final config persisted by server.
    // duration_s is the user-controlled hold (default 5.0s server-side,
    // range 0.5–60). image_path + cache_key written by
    // production_server.py:12856 _handle_use_still_as_final.
    image_path?: string;
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
  // LD-746 KIM_DONE_CHECKBOX_RESHIPPED_V1 (2026-05-17): per-beat "Kim
  // visually verified this beat" toggle. Server handler:
  // production_server.py _handle_beat_kim_done_set. UI counter at top of
  // StoryboardTab pane-header reads this across all beats and shows
  // "N/M done". Original LD-746 ship was caught as fabrication.
  kim_done?: boolean;
  // ISO8601 stamp when kim_done was last flipped to true (null on un-toggle).
  kim_done_at?: string | null;
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
  'Cedric', 'Chipper', 'Tessa', 'Luna', 'Benson',
  'Ember', 'Bork', 'Bramble', 'Grizzle', 'Oliver',
] as const;

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
  if (['pending', 'submitted', 'submitting', 'polling'].includes(b.lipsync?.status ?? '')) {
    return 'lipsync_pending';
  }
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
  beat: BeatState;
  /** Bumps when beat fields change (parent's refreshTick). Used as cacheBust for audio preview. */
  cacheBust?: string;
  /** Triggered after any successful mutation so parent can refresh state. */
  onMutated: () => void;
  previewOptIdx: number | null;
  onPreviewOption: (optIdx: number) => void;
  /**
   * LD-757 TRIM_VIDEO_PERSISTENT_MOUNT_AND_AUTOLOAD_V1 (re-shipped 2026-05-17
   * from stash@{1} 31e1bd292885): flips parent lipsyncMounted state to TRUE
   * so the lipsync <video> stays in the DOM across Preview cycles. Called
   * whenever Preview/Apply auto-load fires OR Kim clicks ▶ lipsync. Once
   * flipped, never flips back this session.
   */
  onEnsureLipsyncMounted: () => void;
}

function BeatButtonRow({ index, beatId, beat, cacheBust, onMutated, previewOptIdx, onPreviewOption, onEnsureLipsyncMounted }: BeatButtonRowProps) {
  const lifecycle = deriveBeatLifecycle(beat);
  const [busy, setBusy] = useState<string | null>(null); // which button is in-flight
  // LD-756 TRIM_INPUT_SEMANTICS_SECONDS_FROM_END_V1 (re-shipped 2026-05-17 from
  // stash@{1} 31e1bd292885). UI inputs now express "seconds to trim from
  // front" and "seconds to trim from back". Server-side semantics remain
  // absolute (LD-749/754/755 unchanged); the conversion happens client-side
  // at submit + preview + hydration time.
  //   front_input = trim_start (identical: seconds-from-start == absolute start)
  //   back_input  = videoEl.duration - trim_end (when trim_end != null)
  //   back_input  = 0.0 when trim_end is null ("use full clip")
  // Default 0.0 / 0.0 means no trim. The reverse-conversion is delay-hydrated
  // by the useEffect below once videoEl.duration is known (loadedmetadata).
  const [trimFront, setTrimFront] = useState<string>(
    String(beat.phase_1?.trim_start ?? beat.trim_in ?? '0.0'),
  );
  // trimBack starts as 0.0 (no trim) on first render; useEffect below
  // converts the persisted absolute trim_end to seconds-from-end once the
  // <video> reports loadedmetadata.
  const [trimBack, setTrimBack] = useState<string>('0.0');
  // L5 fix 2026-05-16 per STORYBOARD_AUDIO_DELAY_READ_NESTED_PATH_V2: server
  // persists at beat.phase_1.audio_delay (nested) and the bootstrap
  // /api/v2/event/<id>/state response returns the raw state.json — so the
  // value lives at the nested path on the React render path. The prior fix
  // (LD-694, 2026-05-14) read the FLATTENED `beat.audio_delay` shape which
  // is emitted only by /api/animate_status (different endpoint) — undefined
  // on bootstrap → slider always re-defaulted to 0.0. Read order:
  // phase_1.audio_delay (canonical) → audio_delay (flattened-poll fallback)
  // → delay_seconds (legacy) → '0.0'. See spec id=225 §5.1 Edit 1.
  const [delaySec, setDelaySec] = useState<string>(
    String(
      beat.phase_1?.audio_delay
        ?? beat.audio_delay
        ?? beat.delay_seconds
        ?? '0.0',
    ),
  );

  // LD STILL_AS_FINAL_HOLD_DURATION_CONTROL_V1 (LD-777, 2026-05-17):
  // user-controlled hold duration for Ken Burns still-as-final renders.
  // Default 5.0s (server-side default if body omits hold_duration_s).
  // Hydrates from beat.final.kenburns.duration_s when a still_image final
  // already exists; otherwise placeholder '5.0' is rendered. Empty input is
  // legitimate (omits the field; server applies its own default).
  //
  // INVARIANTS (per CLAUDE.md Rule 36 §36.1):
  //   - Input is CONTROLLED; effect updates state only when the persisted
  //     nested value changes (not on every render).
  //   - Re-hydrate fires after server PATCH so a re-render with the
  //     updated final block syncs the input to the persisted value.
  const [holdDuration, setHoldDuration] = useState<string>(
    String(beat.final?.kenburns?.duration_s ?? ''),
  );
  useEffect(() => {
    const persisted = beat.final?.kenburns?.duration_s;
    if (persisted !== undefined && persisted !== null) {
      setHoldDuration(String(persisted));
    }
  }, [beat.final?.kenburns?.duration_s]);

  // LD-756 TRIM_INPUT_SEMANTICS_SECONDS_FROM_END_V1 (re-shipped 2026-05-17):
  // keep inputs in sync with canonical persisted (absolute) values, performing
  // the absolute -> seconds-from-end reverse conversion for the back input
  // using the <video> element's known duration. If duration is not yet known
  // (e.g., user has not yet loaded the lipsync ▶), we leave trimBack at the
  // last-known value and re-converting on the duration-load event below.
  //
  // INVARIANTS (per CLAUDE.md Rule 36 §36.1):
  //   - Inputs are CONTROLLED; this updates state only when the persisted
  //     nested value changes (not on every render).
  //   - Front input is identical mapping (seconds-from-start == absolute
  //     start), so it's set unconditionally regardless of duration.
  //   - Back input requires videoEl.duration; if unavailable we skip
  //     the back-side update and let the duration-load effect retry.
  //   - Mid-edit Kim is preserved: onInput already fired set* before the
  //     apply request lands, so the post-apply re-sync is a no-op (value
  //     already matches). Last-write-wins matches LD-723 audio_delay pattern.
  useEffect(() => {
    const nestedStart = beat.phase_1?.trim_start;
    if (nestedStart !== undefined && nestedStart !== null) {
      setTrimFront(String(nestedStart));
    }
    const nestedEnd = beat.phase_1?.trim_end;
    if (nestedEnd === null || nestedEnd === undefined) {
      setTrimBack('0.0');
    } else {
      // Need duration to convert absolute -> seconds-from-end
      const videoEl = document.querySelector<HTMLVideoElement>(
        `[data-testid="beat-preview-video-${index}"]`,
      );
      const dur = videoEl?.duration;
      if (dur && isFinite(dur) && dur > 0) {
        const back = Math.max(0, dur - Number(nestedEnd));
        setTrimBack(back.toFixed(2));
      }
      // else: leave trimBack as-is; will be set on next loadedmetadata
    }
  }, [beat.phase_1?.trim_start, beat.phase_1?.trim_end, index]);

  // LD-756: listen for the lipsync <video>'s loadedmetadata so the back-input
  // can be hydrated from absolute trim_end once duration becomes available.
  // Without this, a user who opens the storyboard before clicking ▶ lipsync
  // sees back=0.0 even when state has a non-null trim_end.
  useEffect(() => {
    const nestedEnd = beat.phase_1?.trim_end;
    if (nestedEnd === null || nestedEnd === undefined) return;
    const videoEl = document.querySelector<HTMLVideoElement>(
      `[data-testid="beat-preview-video-${index}"]`,
    );
    if (!videoEl) return;
    const sync = () => {
      const dur = videoEl.duration;
      if (dur && isFinite(dur) && dur > 0) {
        const back = Math.max(0, dur - Number(nestedEnd));
        setTrimBack(back.toFixed(2));
      }
    };
    if (videoEl.readyState >= 1 && videoEl.duration && isFinite(videoEl.duration)) {
      sync();
      return;
    }
    videoEl.addEventListener('loadedmetadata', sync);
    return () => videoEl.removeEventListener('loadedmetadata', sync);
  }, [beat.phase_1?.trim_end, index, beat.lipsync?.file]);

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

  // LD-778 FALSE_POSITIVE_SUCCESS_TOAST_CLASS_KILL_V1 (re-shipped 2026-05-17
  // from stash@{1} 31e1bd292885 after git-reset wipe; line-by-line audited
  // against Directus LD-778 decision_text).
  //
  // Origin: Kim clicked "Still as Final" on beat_07 during a server-restart
  // race (PID 13331 -> 14611). Toast fired green "Still as Final ok" but
  // state.final stayed None and beat_07_still_final.mp4 was never written.
  // Root cause: this helper toasted success purely on HTTP 2xx (`result.ok`)
  // without inspecting response body. Any 200-with-empty-body (server-restart
  // race), 200-with-status:"noop" (undo_final), or future 200-with-status:
  // "error" would lie-toast.
  //
  // Class-kill (Rule 28): tighten the shared mutation channel itself rather
  // than refactor 8 per-button onClicks. Validation:
  //   (1) `result.ok` must be true (HTTP 2xx).
  //   (2) `result.data` must be parseable (not undefined/null).
  //   (3) `result.data.status`, when present, must equal "ok"
  //       (rejects "noop" / "error" / "warning" / "skipped").
  //   (4) Caller may pass `expectField` to require a named field in data
  //       (e.g., "file" for use_as_final — proves the final block wrote).
  // 'noop' surfaces as info (not error); other non-ok statuses surface as error.
  // Symmetric tightening applied to onRegenAudio inline below.
  const runMutation = async (
    label: string,
    endpoint: any,
    body: Record<string, unknown>,
    expectField?: string,
  ) => {
    setBusy(label);
    const result = await pathappPatch<Record<string, unknown>>(
      activeScope.value, endpoint, { beat_id: beatId, ...body },
    );
    setBusy(null);
    if (!result.ok) {
      pushToast({ kind: 'error', message: `${label} failed: ${result.error}`, source: `beat-${label}-error` });
      return false;
    }
    if (result.data === undefined || result.data === null) {
      pushToast({
        kind: 'error',
        message: `${label}: server returned no body (HTTP ${result.status}); not verified — retry`,
        source: `beat-${label}-unverified`,
      });
      return false;
    }
    const statusField = (result.data as Record<string, unknown>)['status'];
    if (typeof statusField === 'string' && statusField !== 'ok') {
      const msgField = (result.data as Record<string, unknown>)['message'];
      const detail = typeof msgField === 'string' ? msgField : statusField;
      const kind = statusField === 'noop' ? 'info' : 'error';
      pushToast({
        kind,
        message: `${label}: ${detail}`,
        source: `beat-${label}-${statusField}`,
      });
      if (kind === 'info') onMutated();
      return kind === 'info';
    }
    if (expectField && (result.data as Record<string, unknown>)[expectField] === undefined) {
      pushToast({
        kind: 'error',
        message: `${label}: server response missing '${expectField}' — not verified, retry`,
        source: `beat-${label}-missing-${expectField}`,
      });
      return false;
    }
    pushToast({ kind: 'success', message: `${label} ok`, source: `beat-${label}` });
    onMutated();
    return true;
  };

  const onRegenAudio = async () => {
    setBusy('Regen Audio');
    const result = await pathappPatch<{ ok?: boolean; tts_regen?: { audio_duration_s?: number; audio_file?: string }, duration_warning?: { message?: string; audio_duration_s?: number; kling_max_s?: number } }>(
      activeScope.value, 'beat_regenerate_audio', { beat_id: beatId },
    );
    setBusy(null);
    // LD-778 FALSE_POSITIVE_SUCCESS_TOAST_CLASS_KILL_V1: tightened symmetric
    // with runMutation. Server response uses {ok: true, tts_regen: {...}} on
    // success (NOT the status: "ok" convention — different shape). Validate:
    // HTTP 2xx + parseable body + body.ok !== false + tts_regen present
    // (proves audio file was written).
    if (result.ok && result.data && result.data.ok !== false && result.data.tts_regen) {
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
      // LD-778 FALSE_POSITIVE_SUCCESS_TOAST_CLASS_KILL_V1: refined message —
      // distinguishes network/HTTP failure from 200-with-empty-body case.
      const detail = !result.ok
        ? (result.error || `HTTP ${result.status}`)
        : (result.data === undefined || result.data === null)
          ? `server returned no body (HTTP ${result.status}); not verified — retry`
          : (result.data && (result.data as { ok?: boolean }).ok === false)
            ? 'server reported ok=false'
            : 'tts_regen missing from response — not verified, retry';
      pushToast({ kind: 'error', message: `Regen Audio failed: ${detail}`, source: 'beat-Regen Audio-error' });
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
      pushToast({ kind: 'error', message: `Animate failed: ${result.error}`, source: 'beat-animate-error' });
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
    runMutation('Select option', 'select', { option_index: optionIndex });
  const onAddOptions = async () => {
    if (lifecycle === 'lipsync_pending' && !window.confirm('This will discard current Options B & C and generate 2 fresh alternatives. Option A is preserved. A lipsync is queued — this may orphan it. Continue?')) return;
    const ok = await runMutation('Add options', 'beat_add_options', {});
    if (!ok) return;
    // Poll until all submitted options reach a terminal state (completed/failed).
    // Mirrors the onAnimate poll loop — Kling is async so the initial response
    // only shows "polling"; without this loop the user has to manually refresh.
    let polls = 0;
    const pollAddOptions = async () => {
      polls += 1;
      const res = await apiGet('v2_event_state', { event_id: activeScope.value.event_id });
      if (res.ok) onMutated();
      // Stop when all options are terminal or after 120 polls (~10 min).
      if (polls < 120) window.setTimeout(pollAddOptions, POLL_ANIMATE_MS);
    };
    window.setTimeout(pollAddOptions, POLL_ANIMATE_MS);
  };
  const onSwapToA = (fromSlot: number) =>
    runMutation('Move to A', 'beat_swap_to_a', { from_slot: fromSlot });
  const onLipsync = () => runMutation('Lipsync', 'lipsync', {});
  // LD-778 FALSE_POSITIVE_SUCCESS_TOAST_CLASS_KILL_V1: require 'file' in
  // response body — proves use_as_final actually wrote the final block.
  // Catches the origin Kim incident class (200 with empty body during
  // server-restart race).
  const onUseAsFinal = () => runMutation('Use as Final', 'beat_use_as_final', {}, 'file');
  // LD-761 STILL_AS_FINAL_FEATURE_SPEC_V1: render a Ken Burns MP4 from the
  // beat's image_override and mark it final (no Kling animation, no lipsync).
  // Use for beats that are intentionally stills (e.g. ambient establishing
  // shots, "leaves rustling softly, otherwise still" lines).
  // LD-777 STILL_AS_FINAL_HOLD_DURATION_CONTROL_V1: forward user-set hold
  // duration (parsed; empty/invalid → server default 5.0s). Mirrors trim-input
  // pattern: value consumed only on click, no separate "Apply" button.
  // LD-778 FALSE_POSITIVE_SUCCESS_TOAST_CLASS_KILL_V1: expectField='file' —
  // the server returns the rendered MP4 path; absence proves the render
  // didn't complete.
  const onUseStillAsFinal = () => {
    const body: Record<string, unknown> = {};
    const trimmed = holdDuration.trim();
    if (trimmed !== '') {
      const parsed = Number(trimmed);
      if (Number.isFinite(parsed)) {
        body['hold_duration_s'] = parsed;
      }
    }
    return runMutation('Still as Final', 'beat_use_still_as_final', body, 'file');
  };
  // LD-761: clear the final block (undo finalize). Files on disk untouched.
  // Server returns {status:"noop"} when no final block existed; runMutation
  // accepts that as success (no expectField — undo has no load-bearing
  // response field).
  const onUndoFinal = () => runMutation('Undo Final', 'beat_undo_final', {});
  // LD-756 TRIM_INPUT_SEMANTICS_SECONDS_FROM_END_V1 (re-shipped 2026-05-17 from
  // stash@{1} 31e1bd292885): inputs are "seconds to trim from front/back".
  // Convert to absolute timestamps (the on-disk schema in phase_1.trim_start/
  // trim_end and the _handle_beat_trim handler expectation) using
  // videoEl.duration.
  //
  // INVARIANTS:
  //   - Front input == absolute trim_start (identical mapping).
  //   - Back input is seconds-from-end → absolute trim_end = duration - back.
  //   - When back == 0.0 (or empty) → send trim_end: null ("use full clip").
  //   - When duration is not yet loaded and back > 0, FAIL LOUD with a toast
  //     guiding Kim to click ▶ lipsync manually (LD-756 fail-loud requirement).
  //   - If back == 0.0, we DO allow apply even with no loaded video — that
  //     case sends trim_end: null (no duration math required).
  //
  // expectField='beat' per LD-778: _handle_beat_trim returns {beat, trim_start,
  // trim_end?} — the `beat` field is the load-bearing proof the mutation landed.

  // LD-757 TRIM_VIDEO_PERSISTENT_MOUNT_AND_AUTOLOAD_V1 + LD-775
  // TRIM_AUTO_LOAD_LIPSYNC_ON_PREVIEW_APPLY_V1 (re-shipped 2026-05-17 from
  // stash@{1} 31e1bd292885):
  //   ensureLipsyncVideoLoaded() guarantees a playable <video data-testid=
  //   "beat-preview-video-${index}"> exists with readyState>=1 and a finite
  //   non-zero duration. Used by onApplyTrim + onPreviewTrim to eliminate the
  //   prior 2-click warm-up: Kim no longer has to click ▶ lipsync first.
  //
  // INVARIANTS (Rule 36 §36.1):
  //   - Selector class-based on data-testid (not parent-relative) → robust
  //     against future DOM reorganization.
  //   - Returns null on timeout (3s) — callers must handle null with the
  //     LD-756 fail-loud toast guiding manual ▶ lipsync click.
  //   - Calls onEnsureLipsyncMounted() to flip parent lipsyncMounted=true so
  //     the <video> persists across previewOptIdx resets (onEnded).
  //   - Idempotent: if previewOptIdx is already 0, onPreviewOption(0) is a
  //     no-op (parent's handlePreviewOption has the same-idx toggle guard).
  //   - 100ms poll cadence balances responsiveness against CPU; 3s ceiling
  //     matches the spawn brief's "non-blocking UI" constraint.
  const ensureLipsyncVideoLoaded = (): Promise<HTMLVideoElement | null> => {
    return new Promise((resolve) => {
      const sel = `[data-testid="beat-preview-video-${index}"]`;
      const existing = document.querySelector<HTMLVideoElement>(sel);
      if (existing && existing.readyState >= 1 && existing.duration > 0 && isFinite(existing.duration)) {
        resolve(existing);
        return;
      }
      // Trigger the same code path as ▶ lipsync button — mounts the <video>.
      // Also flip parent lipsyncMounted=true (LD-757 sticky mount).
      onEnsureLipsyncMounted();
      onPreviewOption(0);
      const deadline = Date.now() + 3000;
      const tick = () => {
        const el = document.querySelector<HTMLVideoElement>(sel);
        if (el && el.readyState >= 1 && el.duration > 0 && isFinite(el.duration)) {
          resolve(el);
          return;
        }
        if (Date.now() >= deadline) {
          resolve(null);
          return;
        }
        setTimeout(tick, 100);
      };
      setTimeout(tick, 100);
    });
  };

  const onApplyTrim = async () => {
    const front = parseFloat(trimFront);
    const back = parseFloat(trimBack);
    const frontSafe = isNaN(front) || front < 0 ? 0 : front;
    const backSafe = isNaN(back) || back < 0 ? 0 : back;

    let trimEndAbsolute: number | null = null;
    if (backSafe > 0) {
      let videoEl = document.querySelector<HTMLVideoElement>(
        `[data-testid="beat-preview-video-${index}"]`,
      );
      let dur = videoEl?.duration;
      if (!videoEl || !dur || !isFinite(dur) || dur <= 0) {
        // LD-757/775 TRIM_AUTO_LOAD_LIPSYNC_ON_PREVIEW_APPLY_V1: auto-trigger
        // lipsync load instead of failing immediately. Requires lipsync
        // result to exist on disk; otherwise nothing to load.
        if (beat.lipsync?.status === 'completed' && beat.lipsync?.file) {
          pushToast({
            kind: 'info',
            message: 'Loading lipsync…',
            source: `beat-${index}-trim-apply-autoload`,
          });
          videoEl = await ensureLipsyncVideoLoaded();
          dur = videoEl?.duration;
        }
      }
      if (!videoEl || !dur || !isFinite(dur) || dur <= 0) {
        // LD-756 fail-loud: auto-load timed out or lipsync not completed.
        pushToast({
          kind: 'error',
          message: 'Lipsync video failed to load — try clicking ▶ lipsync manually.',
          source: `beat-${index}-trim-apply-no-duration`,
        });
        return false;
      }
      trimEndAbsolute = Math.max(0, dur - backSafe);
      if (trimEndAbsolute <= frontSafe) {
        pushToast({
          kind: 'error',
          message: `Invalid trim: front (${frontSafe.toFixed(2)}s) + back (${backSafe.toFixed(2)}s) >= duration (${dur.toFixed(2)}s).`,
          source: `beat-${index}-trim-apply-invalid`,
        });
        return false;
      }
    }

    const ok = await runMutation('Trim', 'beat_trim', {
      trim_in: frontSafe,
      trim_out: trimEndAbsolute,
    }, 'beat');
    if (ok && beat.lipsync?.status === 'completed' && beat.lipsync?.file) {
      pushToast({
        kind: 'success',
        message: `Trim saved: ${frontSafe.toFixed(2)}s off front, ${backSafe.toFixed(2)}s off back. Preview to verify.`,
        source: `beat-${index}-trim-applied`,
      });
    }
    return ok;
  };

  // LD-755 TRIM_PREVIEW_BROWSER_SIDE_INSTANT_V1 (re-shipped 2026-05-17 from
  // stash@{1} 31e1bd292885): browser-side instant trim preview. Reads the
  // CURRENT input values (not persisted state), locates this beat's lipsync
  // <video> element via data-testid, seeks to absolute_start, attaches a
  // timeupdate listener that pauses at absolute_end (or video.duration if
  // back==0), and plays. ZERO server round-trip.
  //
  // INVARIANTS (per CLAUDE.md Rule 36 §36.1):
  //   - Targets the <video data-testid="beat-preview-video-${index}"> rendered
  //     by BeatImageHolder. If that testid changes, this preview breaks
  //     silently — keep the testid stable.
  //   - The video src is set by previewVideoSrc only when previewOptIdx !== null.
  //     If Kim has never clicked the lipsync ▶ button this session, the <video>
  //     has no src and the seek is a no-op. We detect this and toast guidance.
  //   - Listener cleanup: we store the handler reference on the element and
  //     remove it before attaching the next one — prevents listener pile-up
  //     across multiple Preview clicks.
  //   - Reads input values directly from trimFront/trimBack state (not from
  //     beat props) so Kim sees instant feedback on UNSAVED edits before Apply.
  //   - LD-756: inputs are seconds-from-front/back; convert at preview time.
  const onPreviewTrim = async () => {
    let videoEl = document.querySelector<HTMLVideoElement>(
      `[data-testid="beat-preview-video-${index}"]`,
    );
    if (!videoEl || !videoEl.src || videoEl.readyState < 1) {
      // LD-757/775 TRIM_AUTO_LOAD_LIPSYNC_ON_PREVIEW_APPLY_V1: auto-trigger
      // lipsync load instead of failing on a 2-click warm-up. Requires
      // lipsync result to exist on disk (otherwise nothing to load).
      if (beat.lipsync?.status === 'completed' && beat.lipsync?.file) {
        pushToast({
          kind: 'info',
          message: 'Loading lipsync…',
          source: `beat-${index}-trim-preview-autoload`,
        });
        videoEl = await ensureLipsyncVideoLoaded();
      }
      if (!videoEl || !videoEl.src || videoEl.readyState < 1) {
        pushToast({
          kind: 'info',
          message: 'Lipsync video failed to load — try clicking ▶ lipsync manually.',
          source: `beat-${index}-trim-preview-no-video`,
        });
        return;
      }
    }
    // TS narrowing: after the guards above, videoEl is definitely non-null.
    const video: HTMLVideoElement = videoEl!;
    const front = parseFloat(trimFront);
    const back = parseFloat(trimBack);
    const tInSafe = isNaN(front) || front < 0 ? 0 : front;
    const backSafe = isNaN(back) || back < 0 ? 0 : back;
    const dur = video.duration;
    if (!dur || !isFinite(dur) || dur <= 0) {
      // LD-756 fail-loud (post-autoload still no duration)
      pushToast({
        kind: 'error',
        message: 'Lipsync video duration not yet loaded — click ▶ lipsync first, then try Preview again.',
        source: `beat-${index}-trim-preview-no-duration`,
      });
      return;
    }
    const tOutSafe = backSafe > 0 ? Math.max(0, dur - backSafe) : dur;
    if (tOutSafe <= tInSafe) {
      pushToast({
        kind: 'error',
        message: `Invalid trim window: front (${tInSafe.toFixed(2)}s) + back (${backSafe.toFixed(2)}s) leaves nothing in duration (${dur.toFixed(2)}s).`,
        source: `beat-${index}-trim-preview-invalid`,
      });
      return;
    }
    // Detach any prior preview listener on this element to prevent pile-up.
    const prevHandler = (video as any).__trimPreviewHandler as
      | ((e: Event) => void)
      | undefined;
    if (prevHandler) {
      video.removeEventListener('timeupdate', prevHandler);
    }
    const handler = () => {
      if (video.currentTime >= tOutSafe) {
        video.pause();
        video.removeEventListener('timeupdate', handler);
        (video as any).__trimPreviewHandler = undefined;
      }
    };
    (video as any).__trimPreviewHandler = handler;
    video.addEventListener('timeupdate', handler);
    try {
      video.currentTime = tInSafe;
    } catch {
      /* seek failure on uninitialised video — handled by readyState check above */
    }
    video.play().catch(() => {});
    pushToast({
      kind: 'info',
      message: `Preview: ${tInSafe.toFixed(2)}s → ${isFinite(tOutSafe) ? tOutSafe.toFixed(2) + 's' : 'end'}`,
      source: `beat-${index}-trim-preview`,
    });
  };
  const onApplyDelay = () => {
    const d = parseFloat(delaySec);
    return runMutation('Delay', 'beat_delay', { delay_seconds: isNaN(d) ? 0 : d });
  };

  // Visibility per state-machine table (S5.5e spec §3.1).
  const showRegenAudio = ['draft', 'audio_generated', 'animated', 'selected', 'final'].includes(lifecycle);
  // Show Animate when audio exists (intro workflow) OR when image is assigned
  // without audio yet (resolution/Kling image-first pipeline per Rule 8.3).
  const showAnimate = lifecycle === 'audio_generated' || (lifecycle === 'draft' && !!beat.image_path);
  // count=2 is product-locked per server default; label reflects this.
  const showAddOptions = ['animated', 'selected', 'lipsync_pending', 'final'].includes(lifecycle);
  const showSelectedOptionRadios = ['animated', 'selected', 'lipsync_pending', 'final'].includes(lifecycle);
  // In final state: only show Lipsync if the beat was finalised via lipsync
  // (not use-as-final) AND an option is selected. Loose != null catches both
  // null and undefined (server may write either for unset selected_option).
  const showLipsync = (
    ['selected', 'lipsync_pending'].includes(lifecycle) ||
    (lifecycle === 'final' && beat.final?.source === 'lipsync')
  ) && beat.phase_1?.selected_option != null;
  const showUseAsFinal = ['audio_generated', 'animated', 'selected'].includes(lifecycle);
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
            const opt = beat.phase_1?.options?.[i];
            const optReady = !!(opt?.file && opt?.status !== 'pending' && opt?.status !== 'failed');
            return (
              <span key={oi} class="mn-beat-option-pair">
                <button
                  type="button"
                  class={`mn-btn mn-btn-small${selectedOption === oi ? ' is-active' : ''}`}
                  data-testid={`beat-${index}-select-option-${oi}`}
                  onClick={() => onSelectOption(oi)}
                  disabled={busy !== null}
                >
                  opt {oi}{selectedOption === oi ? ' ✓' : ''}
                </button>
                <button
                  type="button"
                  class={`mn-btn mn-btn-small mn-preview-btn${previewOptIdx === oi ? ' mn-preview-btn-active' : ''}`}
                  data-testid={`beat-${index}-preview-option-${oi}`}
                  onClick={() => onPreviewOption(oi)}
                  disabled={busy !== null || !opt?.file}
                  title={`Preview with audio: opt ${oi}`}
                >
                  {previewOptIdx === oi ? '⏸' : '▶'}
                </button>
                {oi > 1 ? (
                  <button
                    type="button"
                    class="mn-btn mn-btn-small"
                    data-testid={`beat-${index}-swap-to-a-${oi}`}
                    onClick={() => onSwapToA(oi)}
                    disabled={busy !== null || !optReady}
                    title={optReady ? `Promote opt ${oi} to slot A` : 'Option must finish generating first'}
                  >→A</button>
                ) : null}
              </span>
            );
          })}
        </span>
      ) : null}
      {showAddOptions ? (
        <span class="mn-beat-button-group" data-testid={`beat-${index}-regen-group`}>
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-add-options`}
            onClick={onAddOptions}
            disabled={busy !== null}
            title="Keep Option A, generate 2 fresh alternatives (B & C)"
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
              busy === 'Lipsync' ? <><Spinner size="sm" inline /> …</> : (lifecycle === 'final' ? '👄 Resend Lipsync' : '👄 Lipsync')
            )}
          </button>
        ) : null}
        {beat.lipsync?.status === 'completed' && beat.lipsync?.file ? (
          // F-STALE-LIPSYNC-UI-001 / LD STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1.
          // The button still renders for any completed lipsync with a file so
          // Kim can SEE that a stale artifact exists — but it is DISABLED with
          // a "stale" label when lipsync.file_mtime < audio_regenerated_at.
          // Audit-visible degradation per Rule 19, not a silent hide.
          // LD-757 TRIM_VIDEO_PERSISTENT_MOUNT_AND_AUTOLOAD_V1: fresh-branch
          // onClick also triggers parent lipsyncMounted=true so Preview
          // iterations don't unmount the <video> on onEnded.
          (() => {
            const freshness = computeLipsyncFreshness(beat);
            const isStale = freshness === 'stale';
            return (
              <button
                type="button"
                class={isStale ? 'mn-btn mn-btn-small mn-btn-stale' : 'mn-btn mn-btn-small'}
                data-testid={`beat-${index}-lipsync-play`}
                data-stale={isStale ? 'true' : 'false'}
                onClick={isStale ? undefined : () => {
                  onEnsureLipsyncMounted();
                  onPreviewOption(0);
                }}
                disabled={isStale}
                title={
                  isStale
                    ? 'Stale lipsync: cached output is older than the current audio. Re-run lipsync to refresh.'
                    : 'Preview lipsync result (video has audio baked in)'
                }
              >
                {isStale
                  ? '⚠ stale lipsync — re-run'
                  : previewOptIdx === 0
                  ? '⏸ lipsync'
                  : '▶ lipsync'}
              </button>
            );
          })()
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
        {/* LD-761 STILL_AS_FINAL_FEATURE_SPEC_V1: Ken Burns still-as-final.
            LD-777 STILL_AS_FINAL_HOLD_DURATION_CONTROL_V1: inline "Hold (s)"
            input controls clip duration (default 5.0s, range 0.5-60). Value
            consumed on button click; mirrors trim-input pattern (no separate
            Apply button). Audio delay control is a separate concern (Stitcher
            adelay) already shipped.

            Visibility: (a) beat is NOT finalized (initial path), OR (b) beat
            IS finalized AS still_image (re-render path — user wants to change
            Hold value and re-render without going through Undo Final first). */}
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
              title="Hold (s): how long the Ken Burns clip should last. Default 5.0s. Range 0.5-60. Re-click '📷 Still as Final' to re-render with the new hold value."
              style="width: 4em; margin-right: 4px"
            />
            <span class="mn-beat-button-group-label" style="margin-right:6px">Hold (s)</span>
            <button
              type="button"
              class="mn-btn mn-btn-small"
              data-testid={`beat-${index}-still-as-final`}
              onClick={onUseStillAsFinal}
              disabled={busy !== null}
              title={beat.final?.source === 'still_image'
                ? 'Re-render Ken Burns MP4 with the current Hold (s) value. Replaces existing still_image final.'
                : 'Render Ken Burns MP4 from the beat\'s still image and mark final (no animation). Hold duration from the input.'}
            >
              {busy === 'Still as Final' ? <><Spinner size="sm" inline /> …</> : (beat.final?.source === 'still_image' ? '📷 Re-render Still' : '📷 Still as Final')}
            </button>
          </>
        ) : null}
        {lifecycle === 'final' ? (
          <span class="mn-dim" data-testid={`beat-${index}-final-marker`}>
            ✓ final ({beat.final?.source ?? '?'})
          </span>
        ) : null}
        {/* LD-761: undo final shown whenever a final block exists. Clears
            beat.final; files on disk untouched (archival is separate). */}
        {lifecycle === 'final' ? (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-undo-final`}
            onClick={onUndoFinal}
            disabled={busy !== null}
            title="Clear the final block (files on disk untouched)"
          >
            {busy === 'Undo Final' ? <><Spinner size="sm" inline /> …</> : '↶ Undo Final'}
          </button>
        ) : null}
        {/* LD STILL_AS_FINAL_PREVIEW_BUTTON_V1: play the rendered Ken Burns MP4
            (silent video) + TTS audio in the persistent <video> element.
            Sentinel previewOptIdx === -1 routes to beat.final.file via the
            previewVideoSrc derivation. Audio path matches option preview
            (TTS player respected, audio_delay honored).
            Visible ONLY when final.source === 'still_image'. */}
        {lifecycle === 'final' && beat.final?.source === 'still_image' && beat.final?.file ? (
          <button
            type="button"
            class="mn-btn mn-btn-small"
            data-testid={`beat-${index}-still-final-preview`}
            onClick={() => onPreviewOption(-1)}
            disabled={busy !== null}
            title="Preview the rendered Ken Burns still-as-final MP4 (browser playback, no server re-render)"
          >
            {previewOptIdx === -1 ? '⏸ Preview Still' : '▶ Preview Still'}
          </button>
        ) : null}
      </span>

      {/* Trim / Delay group — LD-756 TRIM_INPUT_SEMANTICS_SECONDS_FROM_END_V1:
          inputs are "seconds to trim from front/back". 0.0 = no trim.
          Conversion to absolute timestamps happens at submit/preview time. */}
      <span class="mn-beat-button-group" data-testid={`beat-trim-group-${index}`}>
        <span class="mn-beat-button-group-label">Trim front (s):</span>
        <input
          type="text"
          class="mn-beat-trim-input"
          data-testid={`beat-${index}-trim-in`}
          value={trimFront}
          onInput={(e) => setTrimFront((e.target as HTMLInputElement).value)}
          aria-label="Trim front (s)"
          placeholder="0.0"
          title="Seconds to cut off the START of the video (e.g., 0.5 = drop first half-second)"
        />
        <span class="mn-beat-button-group-label" style="margin-left:8px">Trim back (s):</span>
        <input
          type="text"
          class="mn-beat-trim-input"
          data-testid={`beat-${index}-trim-out`}
          value={trimBack}
          onInput={(e) => setTrimBack((e.target as HTMLInputElement).value)}
          aria-label="Trim back (s)"
          placeholder="0.0"
          title="Seconds to cut off the END of the video (e.g., 0.5 = drop last half-second)"
        />
        {/* trim_back_from_end semantics marker — DO NOT REMOVE (Rule 24 verification anchor) */}
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-${index}-trim-preview`}
          onClick={onPreviewTrim}
          disabled={busy !== null}
          title="Instant browser preview of trim window (HTML5 seek + pause; no server fetch)"
        >
          preview
        </button>
        <button
          type="button"
          class="mn-btn mn-btn-small"
          data-testid={`beat-${index}-trim-apply`}
          onClick={onApplyTrim}
          disabled={busy !== null}
          title="Persist trim to state (Stitcher will use these values)"
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
  onInsertAfter: () => void;
  onDeleteBeat: () => void;
}

function BeatCard({ index, beatId, beat, eventId, onMutated, onInsertAfter, onDeleteBeat }: BeatCardProps) {
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
  const [previewOptIdx, setPreviewOptIdx] = useState<number | null>(null);
  // LD-757 TRIM_VIDEO_PERSISTENT_MOUNT_AND_AUTOLOAD_V1 (re-shipped 2026-05-17
  // from stash@{1} 31e1bd292885):
  //   lipsyncMounted is a STICKY sentinel: once Kim clicks ▶ lipsync OR
  //   Apply/Preview Trim auto-loads the lipsync, this flag flips to TRUE and
  //   never flips back this session. It keeps the lipsync src active in the
  //   tiered previewVideoSrc below so the <video> element stays in the DOM
  //   with metadata + buffer intact across iterations (no re-decode hits).
  // INVARIANTS (Rule 36 §36.1):
  //   - Sticky: once set to TRUE within a session, never flips back to FALSE.
  //   - Tier hierarchy in previewVideoSrc below: option-N preview src
  //     (previewOptIdx 1/2/3) takes precedence; otherwise lipsync src is used
  //     when previewOptIdx === 0 OR lipsyncMounted is TRUE.
  //   - Required: beat.lipsync?.file must exist; otherwise nothing to mount.
  const [lipsyncMounted, setLipsyncMounted] = useState(false);
  const ensureLipsyncMounted = useCallback(() => setLipsyncMounted(true), []);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Preview source resolution. Sentinel mapping:
  //   null = no preview active
  //   0    = lipsync result (ByteDance audio baked in, no separate TTS player)
  //   -1   = still-as-final Ken Burns MP4 (silent; TTS plays alongside)
  //          LD STILL_AS_FINAL_PREVIEW_BUTTON_V1
  //   >0   = phase_1.options[idx-1].file
  //
  // LD-749 §4.2 POST_LIPSYNC_TRIM_FEATURE_SPEC_V1 (re-shipped 2026-05-17 from
  // stash@{1} 31e1bd292885): when phase_1.trim_start or trim_end is set,
  // the lipsync preview must come from /api/beat/lipsync_trimmed (server
  // ffmpeg-clips the existing lipsync MP4 on-the-fly with a disk cache).
  // When no trim is set, fall back to the canonical /asset/ stream.
  //
  // LD LIPSYNC_PLAYBACK_SILENT_FAILURE_CLASS_KILL_V1 (2026-05-17): treat
  // trim_end===0 the same as trim_start===0 (no trim). Accepting any
  // numeric trim_end (including 0) routes to /api/beat/lipsync_trimmed,
  // which returns 404 JSON when no trim row exists for the beat — the
  // <video> element silently fails to decode the JSON body, leaves a
  // black screen, and the play button stays stuck in ⏸. trim_end must be
  // strictly > 0 to engage the trimmed endpoint.
  const _ts = beat.phase_1?.trim_start;
  const _te = beat.phase_1?.trim_end;
  const _hasTrim = (typeof _ts === 'number' && _ts > 0)
    || (typeof _te === 'number' && _te > 0);
  const _videoRole = activeTargetVideo.value;
  // LD-757 TIERED src:
  //   Tier 1   (option preview):       previewOptIdx === 1/2/3 → that option's file
  //   Tier 1.5 (still-final preview):  previewOptIdx === -1     → beat.final.file
  //   Tier 2   (lipsync sticky):       previewOptIdx === 0 OR lipsyncMounted → lipsync src
  //   Tier 3   (idle):                 none active → null (no <video> render)
  // Tier 2 is the persistence path — once lipsyncMounted flips true, the
  // lipsync src persists even after previewOptIdx resets to null (onEnded),
  // so the <video> element stays in the DOM and metadata is preserved.
  const _isLipsyncShown = previewOptIdx === 0 || lipsyncMounted;
  const previewVideoSrc = (previewOptIdx !== null && previewOptIdx > 0)
    ? `http://localhost:5111/asset/${beat.phase_1?.options?.[previewOptIdx - 1]?.file}?v=${beat._version ?? 0}`
    : (previewOptIdx === -1 && beat.final?.source === 'still_image' && beat.final?.file
        ? `http://localhost:5111/asset/${beat.final.file}?v=${beat._version ?? 0}`
        : (_isLipsyncShown
            ? (beat.lipsync?.file
                ? (_hasTrim
                    ? `http://localhost:5111/api/beat/lipsync_trimmed?beat_id=${beatId}&event_id=${eventId}&video_role=${_videoRole}&v=${beat._version ?? 0}`
                    : `http://localhost:5111/asset/${beat.lipsync.file}?v=${beat._version ?? 0}`)
                : null)
            : null));

  const previewAudioSrc = `http://localhost:5111/api/beat/audio/${beatId}?event_id=${eventId}`;

  // LD-764 LIPSYNC_PLAYBACK_SILENT_FAILURE_CLASS_KILL_V1 (re-shipped 2026-05-17
  // from stash@{1} 31e1bd292885): structural class-kill of "silent video
  // playback failure". Symptoms: ▶ button flips to ⏸ but no playback (black
  // screen), no error feedback, recovery requires page refresh. Mechanism:
  // native <video> 'error'/'stalled'/'abort' events currently have no handlers;
  // when src returns 404/JSON/decode-error the browser fires 'error' silently,
  // React state stays in pseudo-playing state, vid.play() rejects into a
  // swallowed .catch(()=>{}). Counter-mechanism: handlers below + watchdog.
  //
  // INVARIANTS (Rule 36 §36.1):
  //   - resetPlayState is the sole entrypoint for recovery; toasts route here.
  //   - Does NOT flip lipsyncMounted — <video> stays in DOM per LD-757 so the
  //     next click can retry without re-decode.
  //   - ctx param distinguishes "Lipsync playback" / "Still preview" /
  //     "Animation preview" so the toast names the preview kind correctly.
  const resetPlayState = useCallback((reason: string, kind: 'error' | 'info' = 'error', ctx: string = 'Playback') => {
    try { videoRef.current?.pause(); } catch {}
    try { audioRef.current?.pause(); } catch {}
    setPreviewOptIdx(null);
    pushToast({ kind, message: `${ctx}: ${reason}`, source: 'sb-lipsync-playback-fail' });
    // eslint-disable-next-line no-console
    console.warn(`[lipsync] beat_${beatId} resetPlayState ctx=${ctx} reason=${reason}`);
  }, [beatId]);

  // LD-769 VIDEO_PLAY_ABORTERROR_RACE_CLASS_KILL_V1 (re-shipped 2026-05-17
  // from stash@{1} 31e1bd292885): structural class-kill of "AbortError
  // stacked-toast" failure mode. Three compounding bugs (Rule 28):
  //  (A) No promise-chain discipline. vid.play() returns a Promise that
  //      resolves AFTER first frame; pause()/src-swap while pending REJECTS
  //      with AbortError.
  //  (B) handlePreviewOption synchronously pauses then setState; rapid clicks
  //      can interrupt a play() that just became pending.
  //  (C) AbortError surfaced as a toast indistinguishable from real failures.
  // Counter-mechanism: playPromiseRef holds in-flight play(); safePlay/
  // safePause await it; lastClickRef debounces; AbortError silenced.
  //
  // INVARIANTS (Rule 36 §36.1):
  //   - playPromiseRef is a ref (no re-renders on update).
  //   - safePlay/safePause are stable useCallback refs (touch only refs).
  //   - lastClickRef debouncing operates at click-handler entry only.
  const playPromiseRef = useRef<Promise<void> | null>(null);
  const lastClickRef = useRef<number>(0);

  // LD-775 OPT_PREVIEW_SILENT_SWALLOW_POSTREGEN_FIX_V1 (re-shipped 2026-05-17
  // from stash@{1} 31e1bd292885): cap the prior-play() await with a 500ms
  // timeout. The original LD-769 await of playPromiseRef.current can hang
  // FOREVER when the HTMLMediaElement's prior play() promise stays pending
  // (Regen Audio leaves an audio element mid-load; per HTML spec, the play()
  // promise resolves "when media has begun playing" — if loading is
  // abandoned, the promise never settles). 500ms is generous and below
  // user-perception. Force-clear stale ref and proceed if exceeded.
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
      // eslint-disable-next-line no-console
      console.warn(`[play-abort] beat_${beatId} ctx=prior-play-timeout cleared stale playPromiseRef @ ${new Date().toISOString()}`);
    }
  }, [beatId]);

  const safePlay = useCallback(async (el: HTMLMediaElement | null | undefined): Promise<void> => {
    if (!el) return;
    // Await any prior in-flight play() so pause/src-swap can't race it.
    await awaitPriorPlayWithTimeout();
    if (el.paused === false) return; // already playing
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
    // Await any pending play() so pause() can't trigger AbortError on it.
    await awaitPriorPlayWithTimeout();
    try { el.pause(); } catch { /* defensive */ }
  }, [awaitPriorPlayWithTimeout]);

  // AbortError classifier: distinguishes browser-aborted (silent, expected)
  // from real playback failures (toast-worthy).
  const handlePlayRejection = useCallback((err: unknown, context: string, toastCtx: string = 'Playback') => {
    const name = (err as { name?: string } | null)?.name ?? 'unknown';
    const playState = videoRef.current?.paused === false ? 'playing' : 'paused';
    // eslint-disable-next-line no-console
    console.warn(`[play-abort] beat_${beatId} ctx=${context} toastCtx=${toastCtx} cause=${name} playState=${playState} @ ${new Date().toISOString()}`);
    if (name === 'AbortError') {
      // Suppressed: AbortError is caused by a legitimate next action (src
      // swap, pause, unmount). Surfacing produced the 5-stacked-toast UX
      // failure Kim hit 2026-05-17 10:03. Logged above.
      return;
    }
    if (name === 'NotAllowedError') {
      resetPlayState('browser autoplay blocked — click again to start', 'error', toastCtx);
      return;
    }
    if (name === 'NotSupportedError') {
      resetPlayState('codec/format not supported', 'error', toastCtx);
      return;
    }
    // Unknown rejection — preserve LD-764 surfacing behaviour.
    resetPlayState(`browser refused to start (${name})`, 'error', toastCtx);
  }, [beatId, resetPlayState]);

  // Diagnostic: log every previewVideoSrc change. Helps debug this class
  // without needing to instrument at incident time.
  useEffect(() => {
    if (!previewVideoSrc) return;
    // eslint-disable-next-line no-console
    console.log(`[lipsync] beat_${beatId} src→${previewVideoSrc} @ ${new Date().toISOString()}`);
  }, [previewVideoSrc, beatId]);

  useEffect(() => {
    if (previewOptIdx === null) return;
    const vid = videoRef.current;
    const aud = audioRef.current;
    if (!vid) return;
    // previewOptIdx === 0 is the lipsync sentinel: ByteDance bakes AAC audio into the
    // output video. Playing the TTS audio player simultaneously doubles the dialogue.
    // For lipsync preview, play video only — do NOT start the separate audio element.
    const isLipsyncPreview = previewOptIdx === 0;
    // L5b fix 2026-05-16 per STORYBOARD_AUDIO_DELAY_READ_NESTED_PATH_V2:
    // read the persisted Video Lead-in from beat.phase_1.audio_delay (nested
    // canonical path the bootstrap returns) and defer audio.play() by that
    // many seconds so the preview matches what the rendered MP4 does
    // (server-side ffmpeg adelay filter bakes the same delay in). The prior
    // top-level `beat.audio_delay` read (LD-695, 2026-05-14) used the
    // FLATTENED shape from /api/animate_status — undefined on bootstrap →
    // audioDelaySec collapsed to 0 → setTimeout branch silently skipped →
    // audio played at t=0 simultaneously with video. See spec id=225 §5.1
    // Edit 2.
    const audioDelaySec = Number(
      beat.phase_1?.audio_delay
        ?? beat.audio_delay
        ?? beat.delay_seconds
        ?? 0,
    ) || 0;
    if (!isLipsyncPreview) {
      if (!aud) return;
      aud.currentTime = 0;
    }
    // LD-771 LIPSYNC_WATCHDOG_FALSE_POSITIVE_CLASS_KILL_V1 (re-shipped 2026-05-17
    // from stash@{1} 31e1bd292885): the 5s readyState-aware watchdog catches
    // the "play() resolved but video never decoded" case. Three FP sources
    // were removed: (1) startedAt anchored AFTER safePlay's internal await,
    // (2) 5s budget (was 2s), (3) success = readyState>=2 && !paused (was
    // currentTime > 0.05s, strictly stronger than "decoded first frame").
    // INVARIANTS (Rule 36): watchdogRef holds timer id; cleanup return paths
    // always clear it.
    const toastCtx = previewOptIdx === 0
      ? 'Lipsync playback'
      : previewOptIdx === -1
        ? 'Still preview'
        : 'Animation preview';
    const watchdogRef = { current: 0 as number };
    safePlay(vid).then(() => {
      // Anchor watchdog AFTER play() has actually been called (not before —
      // safePlay may have awaited a prior playPromiseRef). 5s is the real
      // budget for "did the browser start decoding".
      const startedAt = performance.now();
      watchdogRef.current = window.setTimeout(() => {
        const vidNow = videoRef.current;
        if (!vidNow) return;
        // Success = readyState>=2 (HAVE_CURRENT_DATA) && !paused.
        const playing = vidNow.readyState >= 2 && !vidNow.paused;
        if (!playing) {
          const elapsed = performance.now() - startedAt;
          // eslint-disable-next-line no-console
          console.warn(`[lipsync-watchdog] beat_${beatId} fired after ${elapsed.toFixed(0)}ms readyState=${vidNow.readyState} networkState=${vidNow.networkState} paused=${vidNow.paused} buffered=${vidNow.buffered.length}ranges`);
          resetPlayState(vidNow.paused ? 'video paused unexpectedly — click ▶ to retry' : 'video slow to load — click ▶ to retry', 'error', toastCtx);
        }
      }, 5000);
    }).catch((err) => handlePlayRejection(err, 'effect-play', toastCtx));
    if (!isLipsyncPreview && aud) {
      if (audioDelaySec > 0) {
        const ms = Math.round(audioDelaySec * 1000);
        // Hold the audio until the delay elapses; if Kim cancels the preview
        // (previewOptIdx changes) the effect's cleanup pauses both elements.
        const t = window.setTimeout(() => {
          aud.play().catch(() => {});
        }, ms);
        return () => {
          window.clearTimeout(t);
          if (watchdogRef.current) window.clearTimeout(watchdogRef.current);
        };
      }
      aud.play().catch(() => {});
    }
    return () => {
      if (watchdogRef.current) window.clearTimeout(watchdogRef.current);
    };
    // Dep array must reference the same path the effect actually reads —
    // without beat.phase_1?.audio_delay the effect would never re-fire when
    // Kim presses Delay apply and the parent re-renders with a new beat prop.
    // See spec id=225 §5.1 Edit 3.
  }, [previewOptIdx, beat.phase_1?.audio_delay, beat.audio_delay, beat.delay_seconds, resetPlayState, safePlay, handlePlayRejection]);

  useEffect(() => {
    return () => {
      videoRef.current?.pause();
      audioRef.current?.pause();
    };
  }, []);

  const handlePreviewOption = useCallback((optIdx: number) => {
    // Sentinel 0  = preview lipsync result. ByteDance audio baked in — never touch TTS player.
    // Sentinel -1 = preview still-as-final (Ken Burns MP4, silent video). TTS audio plays
    //               alongside, same as an option preview. LD STILL_AS_FINAL_PREVIEW_BUTTON_V1.

    // LD-769 VIDEO_PLAY_ABORTERROR_RACE_CLASS_KILL_V1: click debounce.
    // Rapid double-click on the same ▶ button (or rapid alternation across
    // opt 1/2/3) was a contributing factor to the 5-stacked-toast AbortError
    // UX failure. 250ms window ignores the second click if it lands inside
    // the first click's render/play cycle. Single click still feels instant.
    const nowTs = performance.now();
    if (nowTs - lastClickRef.current < 250) {
      // eslint-disable-next-line no-console
      console.warn(`[play-abort] beat_${beatId} ctx=debounce dropped opt=${optIdx} dt=${(nowTs - lastClickRef.current).toFixed(0)}ms`);
      return;
    }
    lastClickRef.current = nowTs;

    const isLipsyncPreview = optIdx === 0;
    const isStillFinalPreview = optIdx === -1;
    const file = isLipsyncPreview
      ? beat.lipsync?.file
      : (isStillFinalPreview
          ? beat.final?.file
          : beat.phase_1?.options?.[optIdx - 1]?.file);
    if (!file) return;
    const vid = videoRef.current;
    const aud = audioRef.current;
    if (previewOptIdx === optIdx) {
      // Toggle play/pause for the current preview. Use safePlay/safePause so
      // an in-flight play() promise can't race the toggle into AbortError.
      if (vid && !vid.paused) {
        safePause(vid).catch(() => {});
        if (!isLipsyncPreview) safePause(aud).catch(() => {});
      } else {
        safePlay(vid).catch((err) => handlePlayRejection(err, 'toggle-play'));
        if (!isLipsyncPreview) safePlay(aud).catch((err) => handlePlayRejection(err, 'toggle-play-aud'));
      }
      return;
    }
    // src is about to change (previewVideoSrc derives from previewOptIdx).
    // Per LD-769: await any in-flight play() BEFORE setState, otherwise the
    // React-driven src swap aborts the pending play and rejects with
    // AbortError. safePause does exactly this — awaits playPromiseRef, pauses.
    safePause(vid)
      .catch(() => {})
      .then(() => {
        if (!isLipsyncPreview) return safePause(aud).catch(() => {});
        return undefined;
      })
      .finally(() => {
        setPreviewOptIdx(optIdx);
      });
  }, [previewOptIdx, beat.phase_1?.options, beat.lipsync?.file, beat.final?.file, beatId, safePlay, safePause, handlePlayRejection]);

  const handlePreviewEnded = useCallback(() => {
    audioRef.current?.pause();
    // LD-757 TRIM_VIDEO_PERSISTENT_MOUNT_AND_AUTOLOAD_V1: resetting
    // previewOptIdx to null used to unmount the <video> because the prior
    // previewVideoSrc tied src directly to previewOptIdx !== null. The new
    // tiered logic keeps the lipsync src when lipsyncMounted === true, so
    // this reset only flips the play/pause UI state — the <video> stays in
    // the DOM with metadata + buffer intact. Next Preview just seeks.
    setPreviewOptIdx(null);
  }, []);

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

  // Speaker dropdown change handler (LD CHARACTER_DROPDOWN_RESTORED_V1).
  // Writes through pathappPatch (scope-validated mutation channel) — server
  // canonicalizes the value, dual-writes top-level + phase_1.speaker, and
  // sets text_modified_after_tts=true so the stale-TTS badge fires. No
  // auto-regen — Kim clicks Regen Audio to apply.
  const onSpeakerChange = async (e: Event) => {
    const target = e.target as HTMLSelectElement | null;
    const nextSpeaker = (target?.value ?? '').trim();
    if (!nextSpeaker || nextSpeaker === (beat.speaker ?? '')) return;
    const result = await pathappPatch(activeScope.value, 'beat_update_speaker', {
      beat: beatId,
      speaker: nextSpeaker,
    });
    if (result.ok) {
      // Trigger parent refresh so the new speaker + stale-TTS badge render.
      onMutated();
    } else {
      pushToast({
        kind: 'error',
        message: `Speaker save failed: ${result.error ?? 'unknown'}`,
        source: 'speaker-update',
      });
    }
  };

  // LD-746 KIM_DONE_CHECKBOX_RESHIPPED_V1 — checkbox change handler.
  // Posts to /api/beat/kim_done_set via pathappPatch. Optimistic UI:
  // toast on success/error, parent refresh on success so the top-of-tab
  // counter ("N/M done") updates synchronously without a separate poll.
  // INVARIANT (Rule 36 §36.1): server is the canonical truth; the checkbox
  // `checked` attribute reads beat.kim_done (server state), never local
  // setState — so on refresh the UI matches what's persisted.
  const onKimDoneChange = async (e: Event) => {
    const target = e.target as HTMLInputElement | null;
    if (!target) return;
    const next = !!target.checked;
    const result = await pathappPatch(activeScope.value, 'beat_kim_done_set', {
      beat: beatId,
      kim_done: next,
    });
    if (result.ok) {
      onMutated();
      pushToast({
        kind: 'info',
        message: next ? `Marked ${beatId} as Kim done` : `Cleared kim_done on ${beatId}`,
        source: 'kim-done',
      });
    } else {
      // Roll back the visual checkbox to the server-canonical value by
      // forcing a parent re-render — since `checked` reads beat.kim_done
      // and we never changed local state, this naturally restores it.
      onMutated();
      pushToast({
        kind: 'error',
        message: `Kim-done save failed: ${result.error ?? `HTTP ${result.status}`}`,
        source: 'kim-done-error',
      });
    }
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
        <span
          class={indicatorClass}
          data-testid={`beat-save-${index}`}
          data-save-status={status}
        >
          {indicatorLabel}
        </span>
        {/* LD-746 KIM_DONE_CHECKBOX_RESHIPPED_V1 — per-beat "visually verified"
            toggle. Posts to /api/beat/kim_done_set via pathappPatch. data-testid
            'kim-done-checkbox-N' is the smoke marker (manifest line 24). */}
        <label
          class="mn-kim-done-label"
          title={beat.kim_done_at ? `Kim verified at ${beat.kim_done_at}` : 'Mark beat as visually verified'}
        >
          <input
            type="checkbox"
            class="mn-kim-done-checkbox"
            data-testid={`kim-done-checkbox-${index}`}
            checked={beat.kim_done === true}
            onChange={onKimDoneChange}
            aria-label={`Mark beat ${beatId} as visually verified by Kim`}
          />
          <span class="mn-kim-done-glyph">{beat.kim_done ? '✓' : '○'}</span>
          <span class="mn-kim-done-text">{beat.kim_done ? 'Kim done' : 'Mark done'}</span>
        </label>
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
      />
      <BeatImageHolder
        index={index}
        beatId={beatId}
        beat={beat}
        eventId={eventId}
        onMutated={onMutated}
        previewVideoSrc={previewVideoSrc}
        videoRef={videoRef as RefObject<HTMLVideoElement>}
        onPreviewEnded={handlePreviewEnded}
        onPreviewError={(reason) => {
          // LD-764: derive toast prefix from previewOptIdx so the right
          // preview kind names itself in the toast.
          const onErrCtx = previewOptIdx === 0
            ? 'Lipsync playback'
            : previewOptIdx === -1
              ? 'Still preview'
              : 'Animation preview';
          if (reason) resetPlayState(reason, 'error', onErrCtx);
          else { try { videoRef.current?.pause(); } catch {} try { audioRef.current?.pause(); } catch {} setPreviewOptIdx(null); }
        }}
      />
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
        previewOptIdx={previewOptIdx}
        onPreviewOption={handlePreviewOption}
        onEnsureLipsyncMounted={ensureLipsyncMounted}
      />
      <BeatMagicButtons index={index} beatId={beatId} beat={beat} eventId={eventId} />
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
  /**
   * LD-764 LIPSYNC_PLAYBACK_SILENT_FAILURE_CLASS_KILL_V1 (re-shipped 2026-05-17
   * from stash@{1} 31e1bd292885): mandatory error surface. <video> 'error',
   * 'stalled', 'abort' events route here so the parent can resetPlayState.
   * Reason='' means "abort with no toast" (rapid src swap case).
   */
  onPreviewError?: (reason: string) => void;
}

function BeatImageHolder({ index, beatId, beat, eventId, onMutated, previewVideoSrc, videoRef, onPreviewEnded, onPreviewError }: BeatImageHolderProps) {
  const stillPath = beat.image_path;
  const hasImage = !!stillPath;
  const imgSrc = stillPath
    ? `${SERVER_BASE}/files?path=${encodeURIComponent(`Production/${eventId}/${stillPath}`)}`
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
      class={`mn-storyboard-image-drop-zone mn-drop-target${hasImage ? ' has-image' : ''}${previewVideoSrc ? ' mn-previewing' : ''}`}
      data-testid={`beat-image-zone-${index}`}
      data-beat-id={beatId}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
    >
      {previewVideoSrc ? (
        <video
          {...(videoRef ? { ref: videoRef } : {})}
          src={previewVideoSrc}
          class="mn-storyboard-preview-video"
          playsInline
          preload="auto"
          onEnded={onPreviewEnded}
          // LD-764 LIPSYNC_PLAYBACK_SILENT_FAILURE_CLASS_KILL_V1 (re-shipped
          // 2026-05-17 from stash@{1} 31e1bd292885): mandatory error
          // surface. The browser fires 'error' on src 404, decode failure,
          // codec issue, network drop, MIME mismatch (e.g. server returns
          // JSON instead of video/mp4 — the beat_11 root cause). 'stalled'
          // fires when loading halts > ~3s. 'abort' fires when load is
          // interrupted (rapid src change). All three route through
          // onPreviewError → resetPlayState → toast + previewOptIdx reset,
          // so the ⏸ button doesn't stay stuck.
          //
          // INVARIANTS (Rule 36 §36.1):
          //   - onError reads e.currentTarget.error.code (W3C HTMLMediaError
          //     codes 1-4). codes 4 (SRC_NOT_SUPPORTED) catches the JSON-
          //     instead-of-MP4 case.
          //   - onAbort passes empty reason '' → parent treats as "no
          //     toast, just reset state" (rapid src swap by tier logic).
          //   - onLoadedMetadata is diagnostic only — logs duration so
          //     future debug doesn't need instrumentation.
          //   - onPreviewError is optional; nullish-optional call (?.) so
          //     the <video> works in any future caller that doesn't pass it.
          onError={(e) => {
            const v = e.currentTarget as HTMLVideoElement;
            const code = v?.error?.code;
            const codeName = code === 1 ? 'aborted'
              : code === 2 ? 'network'
              : code === 3 ? 'decode'
              : code === 4 ? 'src not supported (likely 404/JSON)'
              : `unknown(${code})`;
            // eslint-disable-next-line no-console
            console.error(`[lipsync] beat_${beatId} <video> error code=${code} (${codeName}) src=${v?.currentSrc}`);
            onPreviewError?.(`load failed — ${codeName}`);
          }}
          onStalled={() => {
            // eslint-disable-next-line no-console
            console.warn(`[lipsync] beat_${beatId} <video> stalled`);
            onPreviewError?.('network stall — try again');
          }}
          onAbort={() => {
            // eslint-disable-next-line no-console
            console.warn(`[lipsync] beat_${beatId} <video> abort`);
            // No toast on abort — typically a rapid src swap by tier logic.
            // Still want play-state reset so ⏸ doesn't stay stuck.
            onPreviewError?.('');
          }}
          onLoadedMetadata={(e) => {
            const v = e.currentTarget as HTMLVideoElement;
            // eslint-disable-next-line no-console
            console.log(`[lipsync] beat_${beatId} <video> loadedmetadata duration=${v.duration}s readyState=${v.readyState}`);
          }}
          data-testid={`beat-preview-video-${index}`}
        />
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
    const u = new URL(`${SERVER_BASE}/magic`);
    u.searchParams.set('mode', 'magic_still');
    u.searchParams.set('beat_id', beatId);
    u.searchParams.set('source_image_path', `Production/${eventId}/${stillPath}`);
    u.searchParams.set('return_endpoint', '/api/storyboard/magic_still');
    u.searchParams.set('scope_event_id', eventId);
    window.open(u.toString(), '_blank');
  };

  const openMagicVideo = () => {
    if (!videoPath) return;
    const u = new URL(`${SERVER_BASE}/magic`);
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
  const [deleteConfirmBeatId, setDeleteConfirmBeatId] = useState<string | null>(null);

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
      pushToast({ kind: 'error', message: `Delete failed: ${result.error}`, source: 'sb-delete-error' });
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
      pushToast({ kind: 'error', message: `Add failed: ${result.error}`, source: 'sb-add-error' });
    }
  };

  // LD-746 KIM_DONE_CHECKBOX_RESHIPPED_V1 — counter for "N/M done" surfaced
  // in the pane header. Reads beat.kim_done across the current beatList.
  // INVARIANT (Rule 36 §36.1): counter derives from beatList, which derives
  // from server state.videos[role].beats — same source as the checkbox checked
  // state. Cannot drift across the two views.
  const kimDoneTotal = beatList.length;
  const kimDoneCount = beatList.filter((b) => b.kim_done === true).length;

  return (
    <section class="mn-tab-pane mn-storyboard-pane" data-testid="pane-storyboard">
      <header class="mn-pane-header">
        <h2>Storyboard</h2>
        <span class="mn-scope-chip" data-testid="storyboard-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
        {/* LD-746 — "N/M done" counter. Reads beat.kim_done across beatList.
            data-testid 'kim-done-counter' is the canonical hook for the
            counter; the per-beat checkbox testid 'kim-done-checkbox-N' is the
            smoke marker. */}
        {kimDoneTotal > 0 ? (
          <span
            class={`mn-kim-done-counter${kimDoneCount === kimDoneTotal ? ' mn-kim-done-counter-complete' : ''}`}
            data-testid="kim-done-counter"
            data-kim-done-count={kimDoneCount}
            data-kim-done-total={kimDoneTotal}
            title={`${kimDoneCount} of ${kimDoneTotal} beats marked Kim-done`}
          >
            {kimDoneCount}/{kimDoneTotal} done
          </span>
        ) : null}
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
              onInsertAfter={() => void onAddBeat(b.beat_id)}
              onDeleteBeat={() => setDeleteConfirmBeatId(b.beat_id)}
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
