// API endpoint catalog. Rule 32 — absolute http://localhost:5111 URLs only;
// never relative paths. Every fetch in this app routes through one of these.

export const SERVER_BASE = 'http://localhost:5111';

// READ endpoints (Session 1 uses these for the placeholder render).
// Note: v2_event_state is intentionally a template; the server expects
// event_id in the URL path, not the query string. apiGet() substitutes
// {event_id} from the query dict into the URL before issuing the request.
export const READ_ENDPOINTS = {
  cr_library: `${SERVER_BASE}/api/cr/library`,
  cr_full: `${SERVER_BASE}/api/cr/full`,
  v2_event_state: `${SERVER_BASE}/api/v2/event/{event_id}/state`,
  v2_sidecar: `${SERVER_BASE}/api/v2/storyboard/L.json`,
  // Note: bg_state pointer was historic; the actual handler is
  // /api/bg/session-state. bg_state retained to avoid breaking any older
  // dev tool that reads endpoints.ts; callers should use bg_session_state.
  bg_state: `${SERVER_BASE}/api/bg/session-state`,
  bg_session_state: `${SERVER_BASE}/api/bg/session-state`,
  bg_segments: `${SERVER_BASE}/api/bg/segments`,
  patch_health: `${SERVER_BASE}/api/patch_health`,
  // S3 v3.1
  event_list: `${SERVER_BASE}/api/event/list`,
  phase_watercolor_list: `${SERVER_BASE}/api/phase/watercolor_list`,
  phase_base_clips_list: `${SERVER_BASE}/api/phase/base_clips_list`,
  // S5.5f — ambient bed preset inventory.
  phase_b_ambient_preset_list: `${SERVER_BASE}/api/phase_b/ambient_preset_list`,
  production_map: `${SERVER_BASE}/api/production/map`,
  // S5.5b new — Bug 4 fix + VideoSelector data source
  event_current: `${SERVER_BASE}/api/event/current`,
  video_list: `${SERVER_BASE}/api/video/list`,
  // S5.5d (v3 architecture revision, 2026-05-03)
  project_list: `${SERVER_BASE}/api/project/list`,
  milestones_list: `${SERVER_BASE}/api/milestones/list`,
  admin_inflight_count: `${SERVER_BASE}/api/admin/inflight_count`,
  // S5.5c — Beat Generator GPT batch poll (read).
  bg_poll_gpt_status: `${SERVER_BASE}/api/bg/poll-gpt-status`,
  // S5.5e — Storyboard beat-level reads.
  // beat_audio is a templated path: GET /api/beat/audio/<beat_id>?event_id=...
  // apiGet() substitutes {beat_id} from the query dict before issuing.
  beat_audio: `${SERVER_BASE}/api/beat/audio/{beat_id}`,
  animate_status: `${SERVER_BASE}/api/animate/status`,
  lipsync_status: `${SERVER_BASE}/api/lipsync/status`,
} as const;

// MUTATION endpoints — Session 1 ships ZERO callers of these; they exist
// only so Session 1.5 has a single place to wire scope guards. Per LD
// SCOPE_VALIDATION_V1 every server handler in this list MUST validate the
// request body's event_id against self.app.event_dir.name and return HTTP
// 409 on mismatch.
export const MUTATION_ENDPOINTS = {
  bg_accept_beats: `${SERVER_BASE}/api/bg/accept-beats`,
  bg_set_active_context: `${SERVER_BASE}/api/bg/set-active-context`,
  bg_extract_beats: `${SERVER_BASE}/api/bg/extract-beats`,
  bg_inject_beats: `${SERVER_BASE}/api/bg/inject-beats`,
  bg_update_beat: `${SERVER_BASE}/api/bg/update-beat`,
  bg_reorder_beats: `${SERVER_BASE}/api/bg/reorder-beats`,
  assign_image: `${SERVER_BASE}/api/assign-image`,
  beat_update_text: `${SERVER_BASE}/api/beat/update_text`,
  // Character speaker dropdown — per-beat speaker mutation (LD CHARACTER_DROPDOWN_RESTORED_V1).
  // Mirrors beat_update_text contract (event_id scope key, beat body field). Server
  // canonicalizes the value via _canonicalize_speaker, dual-writes top-level +
  // phase_1.speaker (SPEAKER_DUAL_STORE_DEPRECATION_V1), and sets
  // text_modified_after_tts=true on change so the stale-TTS badge fires.
  beat_update_speaker: `${SERVER_BASE}/api/beat/update_speaker`,
  inject_image: `${SERVER_BASE}/api/inject-image`,
  cr_save_crop: `${SERVER_BASE}/api/cr/save-crop`,
  cr_library_delete: `${SERVER_BASE}/api/cr/library/delete`,
  v2_sidecar_write: `${SERVER_BASE}/api/v2/sidecar`,
  // Session 1.5 NEW endpoint — state snapshot before every v59 write (M1)
  state_snapshot: `${SERVER_BASE}/api/state/snapshot`,
  // Session 1.5 v3.1 NEW endpoint — atomic event swap + generation bump (LD-458)
  event_load: `${SERVER_BASE}/api/event/load`,
  // S5.5c+e proper-fix +NewEvent — server-side event-dir creation
  event_create: `${SERVER_BASE}/api/event/create`,
  // S3 v3.1 — phase + animate + stitcher mutations.
  phase_suggest_script: `${SERVER_BASE}/api/phase/suggest_script`,
  watercolor_animate: `${SERVER_BASE}/api/watercolor/animate`,
  stitch_loudnorm: `${SERVER_BASE}/api/stitch_editor/loudnorm`,
  // V59 architectural-fix Wave 1 (F-S2-001) — StitcherTab Preview/Bake
  // routed via pathappPatch. stitch_save_job already exists below.
  stitch_preview: `${SERVER_BASE}/api/stitch_editor/preview`,
  stitch_bake: `${SERVER_BASE}/api/stitch_editor/bake`,
  // S4 v3.1 — Phase A/B producer mutations.
  phase_b_regen_audio: `${SERVER_BASE}/api/phase_b/regen_audio`,
  phase_a_regen_audio: `${SERVER_BASE}/api/phase_a/regen_audio`,
  phase_b_mix_audio: `${SERVER_BASE}/api/phase_b/mix_audio`,
  phase_a_mix_audio: `${SERVER_BASE}/api/phase_a/mix_audio`,
  phase_b_lipsync: `${SERVER_BASE}/api/phase_b/lipsync`,
  phase_a_lipsync: `${SERVER_BASE}/api/phase_a/lipsync`,
  stitch_save_job: `${SERVER_BASE}/api/stitch_editor/job`,
  // S5.5g — module-level SFX cue upsert (separate from per-slot sfx_cues
  // which travel inside stitch_save_job.slots[i].sfx_cues per audit doc §3).
  timeline_cue_upsert: `${SERVER_BASE}/api/timeline/cues`,
  // S5.5f — top-level state writes via the v2 module-patch handler.
  // Whitelisted fields: see _V2_MODULE_ALLOWED_FIELDS in production_server.py.
  // Used for phase_X_watercolor_cues_json, phase_X_ambient_preset_id, the
  // Phase A 3-clip slots, etc. Cursor v8 Beyond #2 — added to MUTATION_ENDPOINTS.
  v2_module_patch: `${SERVER_BASE}/api/v2/module/patch`,
  // S5.5b new — VideoSelector + partition create
  video_set_active: `${SERVER_BASE}/api/video/set_active`,
  video_create: `${SERVER_BASE}/api/video/create`,
  // S5.5d (v3 architecture revision, 2026-05-03)
  milestones_create: `${SERVER_BASE}/api/milestones/create`,
  milestone_load: `${SERVER_BASE}/api/milestones/load`,
  // Storyboard-tab beat insert/delete — writes to production state via mutate_video_state.
  // NOT BG endpoints: use event_id scope key (not scope_event_id).
  v2_beat_create: `${SERVER_BASE}/api/v2/beat/create`,
  v2_beat_delete: `${SERVER_BASE}/api/v2/beat/delete`,
  beat_finalize: `${SERVER_BASE}/api/beat/finalize`,
  scene_assemble: `${SERVER_BASE}/api/scene/assemble`,
  admin_drain_start: `${SERVER_BASE}/api/admin/drain_start`,
  admin_drain_end: `${SERVER_BASE}/api/admin/drain_end`,
  // S5.5c — Beat Generator full UI wiring (Phase B0 catalog completeness).
  bg_delete_beat: `${SERVER_BASE}/api/bg/delete-beat`,
  bg_add_beat: `${SERVER_BASE}/api/bg/add-beat`,
  bg_submit_gpt_batch: `${SERVER_BASE}/api/bg/submit-gpt-batch`,
  bg_accept_option: `${SERVER_BASE}/api/bg/accept-option`,
  bg_accept_lib_image: `${SERVER_BASE}/api/bg/accept-lib-image`,
  cr_upload: `${SERVER_BASE}/api/cr/upload`,
  // S5.5e — Storyboard beat-level production controls (Phase C wiring).
  beat_regenerate_audio: `${SERVER_BASE}/api/beat/regenerate_audio`,
  animate: `${SERVER_BASE}/api/animate`,
  animate_redo: `${SERVER_BASE}/api/animate/redo`,
  select: `${SERVER_BASE}/api/select`,
  beat_add_options: `${SERVER_BASE}/api/beat/add_options`,
  beat_swap_to_a: `${SERVER_BASE}/api/beat/swap_to_a`,
  lipsync: `${SERVER_BASE}/api/lipsync`,
  beat_use_as_final: `${SERVER_BASE}/api/beat/use_as_final`,
  // LD-761 STILL_AS_FINAL_FEATURE_SPEC_V1: Ken Burns rendered MP4 as final source.
  // Server: production_server.py:12682 _handle_use_still_as_final. Body:
  //   {beat, scope_event_id, scope_video_role, hold_duration_s?} → returns
  // 200 {file, kenburns:{...}, cache_key, ...}. UI gates on 'file' (LD-778).
  beat_use_still_as_final: `${SERVER_BASE}/api/beat/use_still_as_final`,
  // LD-761: clear the final block; files on disk untouched. Server:
  // production_server.py:12918 _handle_undo_final. Returns 200 with
  // {status: "noop"} when no final block existed (legitimate no-op,
  // not an error — runMutation handles this without expectField).
  beat_undo_final: `${SERVER_BASE}/api/beat/undo_final`,
  beat_delay: `${SERVER_BASE}/api/beat/delay`,
  beat_trim: `${SERVER_BASE}/api/beat/trim`,
  // LD-746 KIM_DONE_CHECKBOX_RESHIPPED_V1 — per-beat "Kim verified" toggle.
  // Server handler: production_server.py _handle_beat_kim_done_set.
  // Body: {beat: "beat_NN", kim_done: bool}. Sets top-level `kim_done` +
  // `kim_done_at` on the beat dict. UI counter at top of storyboard reads
  // all beats and shows "N/M done".
  beat_kim_done_set: `${SERVER_BASE}/api/beat/kim_done_set`,
  // Authoring-workflow Pillar 7 cornerstone (C-7) — canonical beat-recovery
  // primitive. COPY default; move=true for cross-event/role moves. Per
  // LD BEAT_GRAFT_RECOVERY_MECHANISM_V1: pre-render-only invariant
  // (HTTP 400 on rendered media), audit JSONL + Directus mirror,
  // mutation_id idempotency + content fingerprint, pre-image backups.
  // Cross-event source requires server start with --source-event flag.
  beat_graft: `${SERVER_BASE}/api/beat/graft`,
} as const;

export type ReadEndpoint = keyof typeof READ_ENDPOINTS;
export type MutationEndpoint = keyof typeof MUTATION_ENDPOINTS;

// Convenience union — used by the client when it needs to accept either.
export type Endpoint = ReadEndpoint | MutationEndpoint;

export function isMutationEndpoint(e: Endpoint): e is MutationEndpoint {
  return e in MUTATION_ENDPOINTS;
}

// LD-461 SCOPE_BODY_HELPER_V1 — handler convention.
// BG endpoints have an `event_id` body field that means BG segment number,
// NOT storyboard scope. The v59 client must send the storyboard scope as
// `scope_event_id` for these endpoints. Non-BG endpoints accept either
// `event_id` or `scope_event_id` (the server's _scope_body helper coalesces).
export const BG_MUTATION_ENDPOINTS: ReadonlySet<MutationEndpoint> = new Set<MutationEndpoint>([
  'bg_accept_beats',
  'bg_set_active_context',
  'bg_extract_beats',
  'bg_inject_beats',
  'bg_update_beat',
  'bg_reorder_beats',
  // S5.5c Phase B0 — catalog completeness for Beat Generator full UI wiring.
  // All bg_* handlers use _scope_body and read storyboard scope from
  // scope_event_id (NOT event_id, which BG handlers reuse for segment number).
  'bg_delete_beat',
  'bg_add_beat',
  'bg_submit_gpt_batch',
  'bg_accept_option',
  'bg_accept_lib_image',
]);

export function scopeKeyFor(endpoint: MutationEndpoint): 'event_id' | 'scope_event_id' {
  return BG_MUTATION_ENDPOINTS.has(endpoint) ? 'scope_event_id' : 'event_id';
}
