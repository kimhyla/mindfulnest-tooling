// API endpoint catalog. Rule 32 — absolute URLs on the serving origin.
// Single-server mode: every Event_N uses http://localhost:5111/?event=Event_N
// (see scopeAuthority SINGLE_STORYBOARD_PORT + DUAL_EVENT_DEDICATED_PORTS).

function resolveServerBase(): string {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }
  return 'http://localhost:5111';
}

export const SERVER_BASE = resolveServerBase();

// READ endpoints (Session 1 uses these for the placeholder render).
// Note: v2_event_state is intentionally a template; the server expects
// event_id in the URL path, not the query string. apiGet() substitutes
// {event_id} from the query dict into the URL before issuing the request.
export const READ_ENDPOINTS = {
  cr_library: `${SERVER_BASE}/api/cr/library`,
  cr_thumb: `${SERVER_BASE}/api/cr/thumb`,
  cr_full: `${SERVER_BASE}/api/cr/full`,
  v2_event_state: `${SERVER_BASE}/api/v2/event/{event_id}/state`,
  v2_sidecar: `${SERVER_BASE}/api/v2/storyboard/L.json`,
  // Note: bg_state pointer was historic; the actual handler is
  // /api/bg/session-state. bg_state retained to avoid breaking any older
  // dev tool that reads endpoints.ts; callers should use bg_session_state.
  bg_state: `${SERVER_BASE}/api/bg/session-state`,
  bg_session_state: `${SERVER_BASE}/api/bg/session-state`,
  bg_extract_beats_draft: `${SERVER_BASE}/api/bg/extract-beats/draft`,
  bg_segments: `${SERVER_BASE}/api/bg/segments`,
  // patch_health removed from READ_ENDPOINTS 2026-05-19 (P4): server route
  // is POST-only (CLAUDE.md Rule 36 §36.3 healthcheck violation reporter).
  // Moved to MUTATION_ENDPOINTS below. Audit C4-9.
  // S3 v3.1
  event_list: `${SERVER_BASE}/api/event/list`,
  phase_watercolor_list: `${SERVER_BASE}/api/phase/watercolor_list`,
  stitch_editor_library: `${SERVER_BASE}/api/stitch_editor/library`,
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
  bg_poll_arlo_o3_voice_status: `${SERVER_BASE}/api/bg/poll-arlo-o3-voice-status`,
  bg_poll_kling_native_lipsync_experiment_status: `${SERVER_BASE}/api/bg/poll-kling-native-lipsync-experiment-status`,
  bg_poll_export_to_stitcher: `${SERVER_BASE}/api/bg/poll-export-to-stitcher`,
  // S5.5e — Storyboard beat-level reads.
  // beat_audio is a templated path: GET /api/beat/audio/<beat_id>?event_id=...
  // apiGet() substitutes {beat_id} from the query dict before issuing.
  beat_audio: `${SERVER_BASE}/api/beat/audio/{beat_id}`,
  animate_status: `${SERVER_BASE}/api/animate/status`,
  lipsync_status: `${SERVER_BASE}/api/lipsync/status`,
  stitch_editor_jobs: `${SERVER_BASE}/api/stitch_editor/jobs`,
  stitch_editor_job: `${SERVER_BASE}/api/stitch_editor/job/{job_name}`,
  stitch_editor_beat_boundaries: `${SERVER_BASE}/api/stitch_editor/beat_boundaries`,
  stitch_bake_status: `${SERVER_BASE}/api/stitch_editor/bake/status`,
  stitch_module_final: `${SERVER_BASE}/api/stitch_editor/module_final`,
} as const;

// MUTATION endpoints — Session 1 ships ZERO callers of these; they exist
// only so Session 1.5 has a single place to wire scope guards. Per LD
// SCOPE_VALIDATION_V1 every server handler in this list MUST validate the
// request body's event_id against self.app.event_dir.name and return HTTP
// 409 on mismatch.
export const MUTATION_ENDPOINTS = {
  bg_accept_beats: `${SERVER_BASE}/api/bg/accept-beats`,
  bg_export_to_stitcher: `${SERVER_BASE}/api/bg/export-to-stitcher`,
  bg_set_active_context: `${SERVER_BASE}/api/bg/set-active-context`,
  bg_extract_beats: `${SERVER_BASE}/api/bg/extract-beats`,
  bg_extract_beats_plan: `${SERVER_BASE}/api/bg/extract-beats/plan`,
  bg_extract_beats_approve: `${SERVER_BASE}/api/bg/extract-beats/approve`,
  bg_extract_beats_draft_save: `${SERVER_BASE}/api/bg/extract-beats/draft/save`,
  bg_generate_kling_prompts: `${SERVER_BASE}/api/bg/generate-kling-prompts`,
  bg_inject_beats: `${SERVER_BASE}/api/bg/inject-beats`,
  bg_update_beat: `${SERVER_BASE}/api/bg/update-beat`,
  bg_align_element_ref: `${SERVER_BASE}/api/bg/align-element-ref`,
  bg_add_element_pose: `${SERVER_BASE}/api/bg/add-element-pose`,
  bg_set_element_identity: `${SERVER_BASE}/api/bg/set-element-identity`,
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
  // v2_sidecar_write removed 2026-05-19 (P4): declared with no server
  // handler, zero callers in the v2 client — latent landmine (audit C3-3).
  // patch_health moved here from READ_ENDPOINTS 2026-05-19 (P4): POST-only
  // per CLAUDE.md Rule 36 §36.3 client healthcheck-violation reporter.
  patch_health: `${SERVER_BASE}/api/patch_health`,
  // Session 1.5 NEW endpoint — state snapshot before every v59 write (M1)
  state_snapshot: `${SERVER_BASE}/api/state/snapshot`,
  // Session 1.5 v3.1 NEW endpoint — atomic event swap + generation bump (LD-458)
  event_load: `${SERVER_BASE}/api/event/load`,
  // S5.5c+e proper-fix +NewEvent — server-side event-dir creation
  event_create: `${SERVER_BASE}/api/event/create`,
  // EVENT_DEDICATED_SERVER_PROVISION_V1 — launchd agent for Event_N before port navigation
  event_provision_server: `${SERVER_BASE}/api/event/provision_server`,
  // S3 v3.1 — phase + animate + stitcher mutations.
  phase_suggest_script: `${SERVER_BASE}/api/phase/suggest_script`,
  watercolor_animate: `${SERVER_BASE}/api/watercolor/animate`,
  phase_watercolor_delete: `${SERVER_BASE}/api/phase/watercolor_delete`,
  phase_export_stitcher: `${SERVER_BASE}/api/phase/export_stitcher`,
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
  phase_b_reject_lipsync: `${SERVER_BASE}/api/phase_b/reject_lipsync`,
  phase_a_reject_lipsync: `${SERVER_BASE}/api/phase_a/reject_lipsync`,
  phase_b_apply_stem_cut: `${SERVER_BASE}/api/phase_b/apply_stem_cut`,
  phase_a_apply_stem_cut: `${SERVER_BASE}/api/phase_a/apply_stem_cut`,
  phase_a_regen_flyin_flyout: `${SERVER_BASE}/api/phase_a/regen_flyin_flyout`,
  phase_a_regen_base_clip: `${SERVER_BASE}/api/phase_a/regen_base_clip`,
  phase_b_regen_base_clip: `${SERVER_BASE}/api/phase_b/regen_base_clip`,
  phase_a_restitch: `${SERVER_BASE}/api/phase_a/restitch`,
  stitch_save_job: `${SERVER_BASE}/api/stitch_editor/job`,
  stitch_audio_extract: `${SERVER_BASE}/api/stitch_editor/audio_extract`,
  media_playback_resolve: `${SERVER_BASE}/api/media/playback_resolve`,
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
  bg_insert_beat: `${SERVER_BASE}/api/bg/insert-beat`,
  bg_submit_gpt_batch: `${SERVER_BASE}/api/bg/submit-gpt-batch`,
  bg_submit_arlo_o3_voice: `${SERVER_BASE}/api/bg/submit-arlo-o3-voice`,
  bg_submit_kling_native_lipsync_experiment: `${SERVER_BASE}/api/bg/submit-kling-native-lipsync-experiment`,
  bg_select_o3_video: `${SERVER_BASE}/api/bg/select-o3-video`,
  bg_render_still_clip: `${SERVER_BASE}/api/bg/render-still-clip`,
  bg_set_pipeline: `${SERVER_BASE}/api/bg/set-pipeline`,
  bg_kling_o3_trim: `${SERVER_BASE}/api/bg/kling-o3-trim`,
  bg_accept_option: `${SERVER_BASE}/api/bg/accept-option`,
  bg_accept_lib_image: `${SERVER_BASE}/api/bg/accept-lib-image`,
  cr_upload: `${SERVER_BASE}/api/cr/upload`,
  // S5.5e — Storyboard beat-level production controls (Phase C wiring).
  beat_regenerate_audio: `${SERVER_BASE}/api/beat/regenerate_audio`,
  animate: `${SERVER_BASE}/api/animate`,
  animate_redo: `${SERVER_BASE}/api/animate/redo`,
  select: `${SERVER_BASE}/api/select`,
  beat_add_options: `${SERVER_BASE}/api/beat/add_options`,
  // T1-Phase 2 + 3 (spec MAGIC_AND_ENDFRAME_FIXES_20260520_v1, LD-814):
  // end-frame iteration endpoints. Kim previews/uploads end frame BEFORE
  // Regen B+C; Regen B+C then REFUSES without an approved end_frame_path.
  beat_preview_end_frame: `${SERVER_BASE}/api/beat/preview_end_frame`,
  beat_upload_end_frame: `${SERVER_BASE}/api/beat/upload_end_frame`,
  beat_swap_to_a: `${SERVER_BASE}/api/beat/swap_to_a`,
  lipsync: `${SERVER_BASE}/api/lipsync`,
  lipsync_idle: `${SERVER_BASE}/api/lipsync_idle`,
  beat_use_as_final: `${SERVER_BASE}/api/beat/use_as_final`,
  // LD-761 STILL_AS_FINAL_FEATURE_SPEC_V1: Ken Burns rendered MP4 as final source.
  beat_use_still_as_final: `${SERVER_BASE}/api/beat/use_still_as_final`,
  beat_undo_final: `${SERVER_BASE}/api/beat/undo_final`,
  beat_delay: `${SERVER_BASE}/api/beat/delay`,
  beat_trim: `${SERVER_BASE}/api/beat/trim`,
  beat_zoom: `${SERVER_BASE}/api/beat/zoom`,
  // Authoring-workflow Pillar 7 cornerstone (C-7) — canonical beat-recovery
  // primitive. COPY default; move=true for cross-event/role moves. Per
  // LD BEAT_GRAFT_RECOVERY_MECHANISM_V1: pre-render-only invariant
  // (HTTP 400 on rendered media), audit JSONL + Directus mirror,
  // mutation_id idempotency + content fingerprint, pre-image backups.
  // Cross-event source requires server start with --source-event flag.
  beat_graft: `${SERVER_BASE}/api/beat/graft`,
  beat_done_toggle: `${SERVER_BASE}/api/beat/done_toggle`,
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
// NOT storyboard scope. The v59 client sends the storyboard scope as
// `scope_event_id` for ALL mutations (TECH_SPEC_PATHAPP_SCOPE_EVENT_ID_ONLY_V1).
// Server `_scope_body` coalesces scope_event_id || event_id for guards.
export const BG_MUTATION_ENDPOINTS: ReadonlySet<MutationEndpoint> = new Set<MutationEndpoint>([
  'bg_accept_beats',
  'bg_export_to_stitcher',
  'bg_set_active_context',
  'bg_extract_beats',
  'bg_extract_beats_plan',
  'bg_extract_beats_approve',
  'bg_extract_beats_draft_save',
  'bg_generate_kling_prompts',
  'bg_inject_beats',
  'bg_update_beat',
  'bg_align_element_ref',
  'bg_add_element_pose',
  'bg_set_element_identity',
  'bg_reorder_beats',
  // S5.5c Phase B0 — catalog completeness for Beat Generator full UI wiring.
  // All bg_* handlers use _scope_body and read storyboard scope from
  // scope_event_id (NOT event_id, which BG handlers reuse for segment number).
  'bg_delete_beat',
  'bg_add_beat',
  'bg_insert_beat',
  'bg_submit_gpt_batch',
  'bg_submit_kling_native_lipsync_experiment',
  'bg_render_still_clip',
  'bg_set_pipeline',
  'bg_accept_option',
  'bg_accept_lib_image',
]);

/** @deprecated Injection uses scope_event_id only; kept for docs/e2e references. */
export function scopeKeyFor(endpoint: MutationEndpoint): 'scope_event_id' {
  void endpoint;
  return 'scope_event_id';
}
