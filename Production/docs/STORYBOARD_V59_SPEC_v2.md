# Technical Spec: Storyboard v59 — Path C Greenfield Rewrite (v2)
**Date:** 2026-05-02
**Produced by:** tech-spec skill (v1 + Cursor cross-review findings + Kim's Q1/Q2 simplifications)
**Status:** Awaiting Cursor cross-review v2 before Session 1.5 execution
**Supersedes:** `STORYBOARD_V59_SPEC_v1.md` (this is the canonical reference going forward)

---

## Changelog vs v1

| Section | v1 → v2 change |
|---|---|
| §3 Approach | Added "v58/v59 split-brain rules" subsection (Kim's one-at-a-time mode); distinguished mutation vs read channel |
| §4 Steps | Diffed against ACTUAL `production_server.py` state — 13 handlers already guarded (LD-456 shipped); 16 still unguarded; `allow_missing` policy clarified |
| §4.S1.5 | Added concurrency model for `/api/event/load` (generation counter + per-request event_dir snapshot) |
| §4.S1.5 | Dropped UA-based isolation lock (M6) — superseded by `--storyboard` flag pinning per Kim's Q1 |
| §4.S3 | Watercolor library v58 backport REMOVED — v59-only feature per Kim's Q2 |
| §6 Mitigations | M6 reframed to "server-flag pinning"; M7/M8 unchanged |
| §7 Errors | Added localStorage quota mitigation (LRU + max bytes per beat + storage.estimate) |
| §8 Verification | All verification curls fixed — use `scope_event_id` correctly; added negative tests that cannot pass spuriously |
| §10 Out of Scope | Added: v58 backport of dynamic watercolor list; UA-based session isolation |
| §12 (NEW) | Handler matrix appendix — every `_handle_*` with current scope status |

---

## 1. Task

Replace the 9,751-line `Production/Event_1/storyboard_v58_prod.html` monolith (24 accumulated Path B patches, 149 IIFE markers, 9 functions wrapped 3+ times) with a Preact + @preact/signals + Vite + TypeScript app at `Production/tools/storyboard-v2/`. The build emits `storyboard_v59_prod.html` so cutover uses the existing `production_server.py --storyboard <filename>` CLI flag. Server stays largely untouched — 13 handlers already have LD-456 scope guards; 16 more handlers need them added; ~7 new endpoints. Goal: structural elimination of the wrap-chain bug class + workflow improvements (inline cropper modal, unified speakers, scope tokens, save-state visibility, "Animate this" on watercolors, "Suggest Script" buttons, multi-event-aware loading, Production Map view, universal autosave, explicit export buttons) + foundation for adding Phase A and Phase B producer panels in v59.

**Operating mode (per Kim's Q1/Q2 confirmation):** Single-user, one-version-at-a-time. Kim only ever works in the latest version. Server is pinned to ONE storyboard via `--storyboard` flag at any moment. v58 stays bit-identical for emergency rollback only.

---

## 2. Governing Decisions

(Same as v1 — no changes. See v1 §2 for full table.)

**New LDs to register during execution (unchanged from v1):**
- `STORYBOARD_V59_SPEC_V1` (rev to V2 — this doc)
- `MULTI_EVENT_SERVER_V1` (renamed → `EVENT_LOAD_GENERATION_LOCK_V1` to reflect actual mechanism)
- `UNIVERSAL_AUTOSAVE_V1`
- `PHASE_A_PRODUCER_V1`
- `PHASE_B_PRODUCER_V1`
- `WATERCOLOR_ANIMATE_THIS_V1`
- `PRODUCTION_MAP_V1`
- `EXPORT_TO_STITCHER_V1`

---

## 3. Approach

### 3.1 Frontend rewrite scope is bounded

Only the 9,751-line HTML monolith gets replaced. The 12,550-line `production_server.py` mostly stays — its 91 `_handle_*` endpoints, the magic compositor, the Kling/FLUX/ByteDance/ElevenLabs integrations, the asset pipeline, the 21-collection Directus schema all remain unchanged except for: (a) ~16 new scope guard call sites added to currently-unguarded handlers, (b) HTML-patching made conditional on filename pattern in 3 handlers, (c) ~7 new endpoints, (d) `/api/event/load` concurrency mechanism.

### 3.2 Mutation channel vs read channel (clarification per Cursor)

- **`pathappPatch(scope, field, value)`** — the SOLE mutation channel. Every state-changing call goes through it. Components NEVER call `fetch()` for writes. This is what enables universal autosave + scope-token discipline + localStorage shadow + state snapshot.
- **`apiGet(scope, path, params?)`** — the read helper. Used for: audio stream URLs, file blobs, WaveSurfer audio loads, library list fetches, Production Map queries, anything that doesn't mutate state. Plain GETs allowed via `apiGet` — no shadow, no snapshot, no guard.
- **WaveSurfer's internal audio fetch** — uses `<audio src="...">` directly via DOM. Not routed through either helper. That's fine — it's a stream, not a mutation.

### 3.3 Single mutation channel implementation

`pathappPatch` sequence:
1. Optimistically update the relevant signal store
2. Write a localStorage shadow IMMEDIATELY (before network) — keyed by `(event_id, beat_id, field)`, includes timestamp + value
3. Call `POST /api/state/snapshot` to back up state.json (fire-and-forget; failure logged but doesn't block)
4. POST the mutation to the appropriate server endpoint with full scope payload `{event_id, scope_event_id, beat_id, version, field, value}`
5. On 200: clear the shadow entry, show green checkmark
6. On 4xx/5xx: keep shadow visible, show red banner with retry button + error detail
7. On 423 Locked (stale event generation): force re-hydrate from server, show "event switched mid-flight, retry?" banner
8. On page reload: replay any uncleared shadows after re-hydrating from server

### 3.4 Scope tokens make multi-event safe

Every signal store is keyed by `{event_id, beat_id, version}`. Switching events allocates a fresh store rather than mutating shared state — cross-event leak structurally impossible client-side. The same scope token rides on every server request as `scope_event_id` (mapping to the existing LD-456 mechanism). Server's existing `_assert_event_scope` rejects with HTTP 409 if `body['scope_event_id'] != self.app.event_dir.name`.

**`allow_missing` policy** (clarifies Cursor's finding):
- Existing 13 guarded handlers: keep `allow_missing=True` (legacy v58 client compat — must not break Kim's running session during transition)
- NEW 16 guards added in Session 1.5: also `allow_missing=True` initially, BUT v59 client ALWAYS sends `scope_event_id` so the v59 path always validates
- Session 5 (post-cutover): flip select critical handlers to `allow_missing=False` to enforce — but only after v58 is fully retired

### 3.5 `/api/event/load` concurrency model

`production_server.py` uses ThreadingHTTPServer. Switching `self.app.event_dir` mid-flight could corrupt cross-event state. Mechanism:

1. Add `self.app.event_generation: int = 0` counter to AppContext
2. `/api/event/load` increments generation, swaps `event_dir`, reloads `state` — all under a single `threading.Lock` (`self.app.event_load_lock`)
3. Every other handler captures `current_generation = self.app.event_generation` at entry as a local
4. After any read of `self.app.event_dir` or `self.app.state`, re-check: if `self.app.event_generation != current_generation`, abort with HTTP 423 Locked + `{error: "event_changed_mid_request", current_generation, your_generation}`
5. v59 client receives 423 → re-hydrates from new event → retries the operation if Kim confirms
6. Long-running operations (lipsync, magic compositor) capture `event_dir` at task spawn and use the captured value — they don't re-check generation; the captured event_dir is what the operation completes against (file paths already resolved)

This is lighter than a full mutex per handler and doesn't serialize all requests — only `/api/event/load` itself is serialized; other handlers do an O(1) generation compare.

### 3.6 Persistence contract (state.json + sidecar; HTML conditional)

v59's HTML shell is empty (just a Vite bundle loader). Server's existing HTML-patching code in `_handle_assign_image:6276`, `_handle_beat_update_text:8276`, `_handle_inject_image:6393` made conditional on filename pattern: when target HTML contains v58-shape markers (`var L=[...]`, `var IN=`, `TH["..."]`, `gallery div.ic`), patch HTML AND state. When target is v59-shape (no markers found via grep), patch state.json + sidecar ONLY. Returns `html_patched: bool, mode: "v58" | "v59"` in response so client can verify.

**v59 ALWAYS writes `.L.json` sidecar on every mutation** — guarantees v58 fallback can re-hydrate from sidecar even if HTML is stale.

### 3.7 v58/v59 split-brain rules (per Kim's Q1)

Kim only ever works in the latest version. Rules:
- Server pinned to ONE storyboard at a time via `--storyboard` flag
- Switching versions = stop server + restart with new flag + hard-refresh browser
- Never two browser tabs against the same server with different storyboards (server only knows one; the "wrong" tab shows stale data — annoying but not corrupting)
- After cutover, default flag = v59. Emergency rollback to v58 = same flag-flip procedure (~30 sec)
- After rollback, v58 sees: dialogue/image/beat edits (via state.json) ✅ — but does NOT see new v59-created animated watercolors ❌ (v58's `WATERCOLOR_LIBRARY` is hardcoded at build time)

### 3.8 Phase A and Phase B producers in scope (not deferred)

Same as v1. Producers ported with explicit improvements: voice sliders removed, ambient bed moved to Stitcher, "Suggest Script" button, "Animate this" button on watercolors, explicit export buttons, `phase_a_canonical_<TS>.mp4` renamed to `phase_a_stitched_<TS>.mp4`.

### 3.9 "Animate this" bridge — v59-only (per Kim's Q2)

Same as v1 mechanism. v58 will NOT see new animated watercolors after rollback (acceptable — Kim only works in latest). Saves the v58 backport work that Cursor flagged as a parallel-run gap.

### 3.10 Production Map

Same as v1.

---

## 4. Implementation Steps

### Session 1 — DONE (commit 23812d9)
(Same as v1.)

### Session 1.5 — Server scope guards (16 NEW handlers) + persistence contract + concurrency lock + new endpoints (~3-4 hours, revised UP from 2 due to scope expansion)

1. Open `prod_preflight_reviews` row.
2. Register `STORYBOARD_V59_SPEC_V1` (rev2) + `EVENT_LOAD_GENERATION_LOCK_V1` + `UNIVERSAL_AUTOSAVE_V1` LDs.
3. **Add scope guards to 16 currently-unguarded handlers** (NOT 13 — those are already done). Use existing `_assert_event_scope({event_id: body.get("scope_event_id")}, allow_missing=True)` pattern:
   - `_handle_v2_event_state` @L9405 — also validate URL `event_id` param matches server
   - `_handle_v2_sidecar` @L9349
   - `_handle_bg_delete_beat` @L5720
   - `_handle_select` @L8849
   - `_handle_v2_patch` @L9010
   - `_handle_animate` @L7705
   - `_handle_add_options` @L7936
   - `_handle_phase_b_regen_audio` @L11557
   - `_handle_phase_b_mix_audio` @L11829
   - `_handle_phase_b_lipsync` @L12237
   - `_handle_phase_b_preview` @L12419
   - `_handle_magic_submit_path` @L4798
   - `_handle_stitch_save_job` @L10907
   - `_handle_stitch_bake` @L11396
   - `_handle_export` @L8901
   - `_handle_preview_stitched` @L9696
4. **Audit `_handle_bg_reorder_beats` segment_index inconsistency** (L5486). Flag as latent bug; do NOT fix in this scope; add tracking entry to `prod_blockers`.
5. **Add `/api/event/load` concurrency mechanism** per §3.5:
   - `self.app.event_generation: int = 0`
   - `self.app.event_load_lock: threading.Lock`
   - `/api/event/load` increments + swaps under lock
   - Add helper `self._check_event_generation(captured_gen)` returning HTTP 423 on stale
   - Wire into 5-10 of the most state-mutating handlers as proof-of-concept (full rollout via grep checklist tracked in handler matrix appendix §12)
6. **Make HTML-patching conditional** on filename pattern in `_handle_assign_image:6276`, `_handle_beat_update_text:8276`, `_handle_inject_image:6393`. v58-shape (markers found) → patch HTML+state; v59-shape (no markers) → state-only. Log mode in response.
7. **v59 client ALWAYS writes `.L.json` sidecar** on every mutation that touches dialogue/image fields (guarantees v58 emergency-rollback hydration). Server endpoint `_write_sidecar_L_json` already exists at L3599.
8. Add `POST /api/state/snapshot` endpoint per v1.
9. Add `POST /api/event/load` endpoint per v1 + the concurrency mechanism from step 5.
10. **DROP M6 isolation lock** (UA-based) — replaced by `--storyboard` flag pinning per Kim's Q1.
11. Wire v59 client's `pathappPatch` to: (a) call `/api/state/snapshot` before mutation, (b) include `scope_event_id` in body, (c) handle 423 by re-hydrating + retry-prompt.
12. **Verification (CORRECTED — uses `scope_event_id`):**
    - ✅ `curl -X POST http://localhost:5111/api/bg/accept-beats -H "Content-Type: application/json" -d '{"scope_event_id":"Event_2","beats":[],"segment":0}'` returns HTTP 409 (NOT just `event_id` — must use `scope_event_id` for BG handlers)
    - ✅ `curl -X POST http://localhost:5111/api/v2/beat/beat_01/patch -H "Content-Type: application/json" -d '{"event_id":"Event_2","field":"text","value":"x"}'` returns HTTP 409
    - ✅ `curl -X POST http://localhost:5111/api/state/snapshot -H "Content-Type: application/json" -d '{"event_id":"Event_1"}'` returns snapshot path + sha256
    - ✅ `curl -X POST http://localhost:5111/api/event/load -H "Content-Type: application/json" -d '{"arc_number":1,"event_id":"Event_1","module_id":"M1"}'` returns active event + new generation number
    - ✅ Concurrency proof: spawn 2 parallel `/api/event/load` calls + verify generation counter is sequential (not interleaved)
    - ✅ NEW negative test: `curl -X POST http://localhost:5111/api/bg/accept-beats -d '{"beats":[]}'` (NO scope_event_id) returns 200 because `allow_missing=True` — confirms current behavior; v59 client tested separately to verify it ALWAYS sends scope_event_id
    - ✅ Session 1 Playwright smoke still green
    - ✅ Manual: dialogue edit in v59 → reload → persists; flag-flip to v58 → visible (via state.json hydration); flag-flip to v59 → still there

### Session 2 — Touchpoint A flows + behavioral parity audit + 4 tabs feature complete (~3-4 hours)

(Same as v1 except:)
- 24 patches (verified — Cursor was right; v1 said 62 erroneously) → ~30 unique behaviors → **45 Playwright tests** (Cursor's recommendation, not 30)
- Add explicit "manual gap" list for behaviors that can't be E2E-tested (CSS regressions, observer ordering, Fix-W telemetry)

### Sessions 2.5 / 2.7 / 2.9 / 3 / 3.5 / 4 / 5

(Same as v1 except:)
- Session 3 watercolor library: **v59-only feature** (no v58 backport)
- Session 5 post-cutover cleanup: also flip `allow_missing=False` on critical handlers; document the `_assert_event_scope` enforcement matrix in `prod_locked_decisions`

---

## 5. Files Created / Modified

(Same as v1 with these additions/changes:)

| Path | Action | Why |
|---|---|---|
| `Production/tools/production_server.py` | Modify (~80-200 lines, revised UP from 50-150) | 16 NEW scope guards + concurrency lock + 7 new endpoints + HTML-patch conditional |
| `Production/tools/storyboard-v2/src/api/client.ts` | Modify | Add 423 Locked handler with re-hydrate + retry-prompt; ALWAYS include `scope_event_id` in body |
| `Production/tools/storyboard-v2/src/utils/shadow-write.ts` | Modify | Add LRU eviction + max bytes per beat (32KB) + `navigator.storage.estimate()` quota check + warn-at-80%-full |

---

## 6. Directus Writes Required

(Same as v1.)

---

## 7. Error Cases and Handling

(Same as v1 except, NEW:)

| Failure | Detection | Response |
|---|---|---|
| Event changed mid-request (generation stale) | Handler's `_check_event_generation(captured_gen)` returns False | HTTP 423 Locked + `{error: "event_changed_mid_request", current_generation, your_generation}`; client re-hydrates |
| localStorage quota exceeded | `navigator.storage.estimate()` returns >80% used OR write throws QuotaExceededError | LRU evict oldest shadow entries down to 50% used; warn Kim with banner; if eviction can't recover, block writes with explicit "storage full — please reload to clear" error |
| `/api/v2/event/<id>/state` URL/server mismatch | New URL validation in `_handle_v2_event_state` | HTTP 409 with clear message; client re-hydrates |
| Magic compositor render fails for "Animate this" | Background thread catches exception | Job marked `failed` in `_MAGIC_JOBS`; library refresh shows nothing new; Kim sees error toast in v59 |

---

## 8. Verification

(Same as v1 except all curls in Session 1.5 verification gate corrected to use `scope_event_id` per Cursor's CRITICAL #2 finding.)

---

## 9. Rollback

(Same as v1 + Kim's clarification: only ever works in latest version, so rollback is a one-flag procedure.)

---

## 10. Out of Scope (V1)

(Same as v1 plus NEW:)

- **v58 backport of `GET /api/phase/watercolor_list`** — v58 will NOT see runtime-added watercolors. Acceptable per Kim's Q2 (only works in latest).
- **UA-based / session-token client isolation lock** — superseded by `--storyboard` flag pinning per Kim's Q1.
- **Flipping `allow_missing=False`** on existing 13 LD-456 guards — done in Session 5 post-cutover, not in 1.5 (would break legacy compat mid-transition).
- **Fixing `_handle_bg_reorder_beats` segment_index inconsistency** — latent bug, tracked separately in `prod_blockers`.

---

## 11. Cursor Cross-Review Questions (v2)

The v1 spec already had Cursor v1 review (CRITICAL/HIGH findings folded into this v2). New questions for Cursor v2:

1. **Generation-counter concurrency model** in §3.5: is it sufficient, or do we need a heavier mutex? Specifically: are there handler patterns where the captured `current_generation` could be stale by the time a downstream operation completes (e.g., if a handler kicks off a background thread)?
2. **`allow_missing=True` policy clarification** in §3.4: is keeping legacy compat for the existing 13 guards (and the 16 new ones) acceptable until Session 5 cutover? Or should v59 enforce immediately on the new 16 (since v59 always sends scope)?
3. **Handler matrix in §12** — did I miss any `_handle_*` that touches `mutate_state` or writes under `event_dir`? Specifically check timeline endpoints, sfx, voice profile endpoints.
4. **localStorage quota policy** in §7: LRU + max bytes per beat + estimate-based warning — sufficient, or are there mobile/Safari quirks worth handling?
5. **Phase B before Phase A** session ordering: confirmed correct per Phase A's Suggest-Script consumer dependency on Phase B output.
6. **`.L.json` sidecar always-write** in step 7 of Session 1.5: any race condition risk if v59 writes sidecar concurrently with another v59 write to the same field? (Single-user mode mitigates this but worth confirming.)
7. **HTML-patching mode return field** (`html_patched: bool, mode: "v58" | "v59"`): does the v59 client need to act on this differently, or is it just for verification?
8. **`_handle_v2_event_state` URL validation** in step 3: what's the right behavior when URL `event_id` matches server but body has no scope? Pass through, since URL is the auth?

---

## 12. Handler Matrix Appendix (NEW — Cursor's request)

Every `_handle_*` that touches `mutate_state` or writes under `event_dir`. Status reflects code as of grep on 2026-05-02.

| Handler | Line | Currently guarded? | Action in S1.5 |
|---|---|---|---|
| `_handle_assign_image` | 6492 | ✅ Yes (LD-456) | None |
| `_handle_beat_update_text` | 8528 | ✅ Yes (LD-456) | Make HTML-patch conditional on filename |
| `_handle_inject_image` | 6626 | ✅ Yes (LD-456) | Make HTML-patch conditional on filename |
| `_handle_cr_save_crop` | 6338 | ✅ Yes (LD-456) | None |
| `_handle_bg_set_active_context` | 5520 | ✅ Yes (uses scope_event_id) | None |
| `_handle_bg_extract_beats` | 5553 | ✅ Yes (uses scope_event_id) | None |
| `_handle_bg_inject_beats` | 5597 | ✅ Yes (uses scope_event_id) | None |
| `_handle_bg_update_beat` | 5668 | ✅ Yes (uses scope_event_id) | None |
| `_handle_bg_reorder_beats` | 5700 | ✅ Yes (uses scope_event_id) | Flag latent segment_index bug |
| `_handle_bg_accept_beats` | 5752 | ✅ Yes (uses scope_event_id) | None |
| `_handle_bg_delete_beat` | 5720 | ❌ No | **ADD guard** |
| `_handle_v2_event_state` | 9405 | ❌ No | **ADD guard + URL validation** |
| `_handle_v2_sidecar` | 9349 | ❌ No | **ADD guard** |
| `_handle_v2_patch` | 9010 | ❌ No | **ADD guard** (critical — this is the canonical write path) |
| `_handle_select` | 8849 | ❌ No | **ADD guard** |
| `_handle_animate` | 7705 | ❌ No | **ADD guard** |
| `_handle_add_options` | 7936 | ❌ No | **ADD guard** |
| `_handle_phase_b_regen_audio` | 11557 | ❌ No | **ADD guard** |
| `_handle_phase_b_mix_audio` | 11829 | ❌ No | **ADD guard** |
| `_handle_phase_b_lipsync` | 12237 | ❌ No | **ADD guard** |
| `_handle_phase_b_preview` | 12419 | ❌ No | **ADD guard** |
| `_handle_magic_submit_path` | 4798 | ❌ No | **ADD guard** |
| `_handle_stitch_save_job` | 10907 | ❌ No | **ADD guard** |
| `_handle_stitch_bake` | 11396 | ❌ No | **ADD guard** |
| `_handle_export` | 8901 | ❌ No | **ADD guard** |
| `_handle_preview_stitched` | 9696 | ❌ No | **ADD guard** |
| `_handle_storyboard_switch` | 7258 | (intentional cross-event) | Audit; likely OK |
| `_handle_voice_profile_get` | 11701 | (read-only) | None |
| `_handle_voice_profile_update` | 11745 | (Chipper id=2 only; cross-event safe) | None |
| `_handle_state` (read) | (various) | (read-only) | None |
| `_handle_files_serve` | 6063 | (static file) | None |
| `_handle_lipsync_submit` (per-beat) | 6818 | ⚠️ TODO verify | Audit in S1.5 |

**Total: 13 already guarded + 16 to add + 1 to audit = 30 handlers reviewed.** The 16-handler add is the bulk of Session 1.5 server work.

---

**End of spec v2. Awaiting Cursor cross-review v2.**
