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
  bg_state: `${SERVER_BASE}/api/bg/state`,
  patch_health: `${SERVER_BASE}/api/patch_health`,
  // S3 v3.1
  event_list: `${SERVER_BASE}/api/event/list`,
  phase_watercolor_list: `${SERVER_BASE}/api/phase/watercolor_list`,
  phase_base_clips_list: `${SERVER_BASE}/api/phase/base_clips_list`,
  production_map: `${SERVER_BASE}/api/production/map`,
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
  inject_image: `${SERVER_BASE}/api/inject-image`,
  cr_save_crop: `${SERVER_BASE}/api/cr/save-crop`,
  cr_library_delete: `${SERVER_BASE}/api/cr/library/delete`,
  v2_sidecar_write: `${SERVER_BASE}/api/v2/sidecar`,
  // Session 1.5 NEW endpoint — state snapshot before every v59 write (M1)
  state_snapshot: `${SERVER_BASE}/api/state/snapshot`,
  // Session 1.5 v3.1 NEW endpoint — atomic event swap + generation bump (LD-458)
  event_load: `${SERVER_BASE}/api/event/load`,
  // S3 v3.1 — phase + animate + stitcher mutations.
  phase_suggest_script: `${SERVER_BASE}/api/phase/suggest_script`,
  watercolor_animate: `${SERVER_BASE}/api/watercolor/animate`,
  stitch_loudnorm: `${SERVER_BASE}/api/stitch_editor/loudnorm`,
  // S4 v3.1 — Phase A/B producer mutations.
  phase_b_regen_audio: `${SERVER_BASE}/api/phase_b/regen_audio`,
  phase_b_mix_audio: `${SERVER_BASE}/api/phase_b/mix_audio`,
  phase_b_lipsync: `${SERVER_BASE}/api/phase_b/lipsync`,
  stitch_save_job: `${SERVER_BASE}/api/stitch_editor/job`,
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
]);

export function scopeKeyFor(endpoint: MutationEndpoint): 'event_id' | 'scope_event_id' {
  return BG_MUTATION_ENDPOINTS.has(endpoint) ? 'scope_event_id' : 'event_id';
}
