# phase-a-designer governance

**Rule 17 scope.** This file is the self-administered checklist the
phase-a-designer skill walks before Phase A authoring work begins. It does
not programmatically enforce — it's a structured rereading of the governing
docs, scoped to Phase A.

## Before editing any Phase A artifact

1. **Am I in Claude Code terminal CLI?** (Rule 19 Hardened Session Protocol +
   LD-261). Storyboard_v38_prod.html + production_server.py are governed
   files; PreToolUse docx-hook + Phase-0 reminder hooks only fire in
   terminal CLI. If in Cowork/Desktop, STOP and move to Terminal.app.

2. **Have I read the full decision_text of the governing LDs?**
   (feedback_read_full_ld_text.md — titles alone hide the rules.)
   Minimum set to pull full text on:
   - LD-302 ARCH_V3_PHASE_B_A_SYNTHESIS_20260419
   - LD-303 PREVIEW_STITCHED_V3_SHIPPED_20260419
   - LD-349 PHASE_A_GUIDE_BIRD_DEMOS_ARC_1_V1 (2026-04-20)
   - LD-350 PHASE_A_NO_FIXED_DURATION_CEILING_V1 (2026-04-20)
   - LD-280 RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1
   - LD-183 LORE_UPDATE_WIZARD_BIRD_RENAME_20260417

3. **Chipper / Cedric naming — canonical** (LD-183). No Pip, no Guide Bird,
   no Myrrhin in new authoring surface. Legacy aliases (`_SPEAKER_ALIAS`)
   handle backward-compat — no need to rename every L[] entry.

4. **Chipper DEMOS Phase A** (LD-349) — child does NOT perform the action.
   Session decision 14 was the operational flip; LD-349 closes formally.

5. **No Phase A duration ceiling** (LD-350). Phase A runtime varies per
   module. SIZE_BUDGET_PER_MODULE_V1 (LD-283) still governs overall
   module size — don't confuse runtime vs. size.

## Before editing storyboard_v38_prod.html

1. **Rule 7 Path B discipline** (CLAUDE.md §Rule 7):
   - Behavior-only changes (JS/CSS) → Path B (JS-only patch via Python
     patcher under `Production/tools/patchers/`)
   - Image/structural changes → Path A (run `build_storyboard.py`)
   - Combined → Path A first, THEN Path B
2. **SHA256 base64-integrity gate** — extract all base64 images before
   patching, verify byte-identical list after. Hand-rolling HTML, base64
   injection, guessing disk paths is FORBIDDEN.
3. **Render hooks after `_baseRender()`** — else DOM is destroyed and
   hooks silently drop (preflight 136 lesson).
4. **Pre-rebuild browser-edit gate** — ask Kim to Export Locked Sequence
   if any rebuild is imminent. Rebuild from stale disk = silent data loss
   (April 13 2026 disaster).
5. **Backup first** — timestamped `.bak_*` under `.storyboard_backups/`
   with 10-file prune. Atomic rename via `os.replace()` after Node syntax
   check on extracted script regions.

## Before editing production_server.py

1. **Additive only** for new routes. Don't modify existing phase-parameterized
   routes — they're load-bearing for Phase B which is already shipped.
2. **Whitelist new state fields** in `_V2_MODULE_ALLOWED_FIELDS` + add
   validator in `_V2_MODULE_FIELD_VALIDATORS`.
3. **Two-Write Rule** (Rule 18) — every output MP3/MP4 + state change →
   prod_assets row + prod_activity_log row.

## TTS / Chipper voice profile

1. **Current Chipper profile (prod_voice_profiles id=2):**
   `7o9pyvsN0ob5GO6LBQp6`, stability 0.30, similarity 0.80, style 0.30,
   eleven_v3.
2. **New conversational settings (Kim approved 2026-04-20):**
   stability 0.25, similarity 0.75, style 0.55. Lighter v3 emotion tags
   (`[chuckles]`, `[cheerful]`, `[whispers]`) replace prescriptive scene
   prefixes.
3. **Persistence** — voice sliders in Phase A panel write to
   prod_voice_profiles id=2 (Kim approved option A). Cedric (id=1) is
   untouched.
4. **Rule 22** — ElevenLabs TTS is PRODUCTION-PIPELINE only. No app-side
   runtime TTS. Phase A audio is baked into the atomic MP4 per LD-280.

## V1 spec anchor

- **v4 is canonical** (Kim confirmed 2026-04-20) — Buy-In + Phase A merged
  into one segment. v3 storyboards are superseded.
- `phase_a_script` (existing state field) is the authoring surface (one
  big text area, like Phase B). Do NOT add `phase_a_instruction_cues_json`.
- `module_M{N}_config.json.phaseAConfig.instructionCues[]` remains as
  module-level structured reference; not edited by storyboard UI.

## Anti-patterns — DO NOT repeat

- Don't hand-roll HTML
- Don't guess disk image paths (Rule 7 "never guess" — image selections may
  not match filenames on disk)
- Don't layer patches on broken baselines — restore from `.bak_*` first,
  then patch cleanly (Preflight 132 lesson)
- Don't edit module_M{N}_config.json directly; go through the storyboard +
  server write path
- Don't ship voice-slider UI without declaring persistence semantics (Kim
  approved option A = persistent, so declare in governing LD)

## Phase A panel build — voice sliders shipped 2026-04-20 (LD PHASE_A_PANEL_VOICE_SLIDERS_V1)

Status: SHIPPED. Kim's tightened scope locked 2026-04-20 is now in code:

- **Single `phase_a_script` textarea** — reused; `id="phase-a-script"` is
  rendered by `renderPanel("a", ...)` at storyboard_v38_prod.html ~line 2762
  and was already wired by LD-303 patch_v38_phase_b.py.
- **One Regen button** — `phase-a-regen-btn` (~line 2769) is already wired
  to `POST /api/phase_b/regen_audio` with `{phase: "a", script: "..."}`
  via `wireButtons("a")` (~line 3097-3131). The handler at
  production_server.py:7401-7524 branches on phase and writes to
  `phase_a_voice_stem_<TS>.mp3`. No phase-B clobber risk.
- **Persistent voice sliders** — three sliders (stability /
  similarity_boost / style) injected ONLY into the Phase A panel by
  `Production/tools/patchers/phase_a_panel_patcher.py`. Sentinel-anchored
  (`PHASE_A_PANEL_PATCH_START v1 (sliders)` … `PHASE_A_PANEL_PATCH_END v1`)
  for clean idempotent re-patch. `PROFILE_ID = 2` hardcoded (Chipper).
  250ms trailing-edge debounce on `change` (not `input`) — slider drag is
  cheap; PATCH only fires on pointerup.
- **New server routes** (additive to production_server.py):
  - `GET /api/voice/profile/<id>` — hydrate sliders from
    prod_voice_profiles by id. Allow-list ids {1,2,3} (Cedric, Chipper,
    Tessa). Phase A panel currently uses id=2 only.
  - `POST /api/voice/profile_update` — body `{"id":2,"stability":...,
    "similarity_boost":...,"style":...}`. Whitelisted fields only;
    floats clamped to [0.0, 1.0]; PATCHes Directus via the same
    `lib/directus.py` DirectusClient that `_load_voice_profiles_from_directus`
    uses; force-refreshes `_VOICE_PROFILE_CACHE` so the next regen sees
    the new values.

### Out of scope (Phase 1 panel) — keep CLI-only

- Kling regen from UI
- ByteDance LipSync from UI
- ffmpeg compose from UI
- Watercolor cues editor for Phase A (route exists; UI wiring deferred)

### Patcher discipline (Rule 7 Path B)

`Production/tools/patchers/phase_a_panel_patcher.py`:

- Sentinel-anchored injection before `</body></html>`
- SHA256 base64 image manifest pre/post (22 URIs verified byte-identical)
- `node --check` on the injected IIFE before write
- `.storyboard_backups/storyboard_v38_prod.html.bak_phase_a_panel_<TS>` with
  10-file prune scoped to this label only (other patchers' backups untouched)
- Atomic `os.replace`
- Idempotent: aborts if sentinel exists; `--force-replace` excises and
  re-inserts. `--dry-run` available.

### Phase 0 verdict (4+4 advocate/counter, 2026-04-20)

Resolved counters:
- C1 id mix-up → hardcoded `PROFILE_ID = 2` JS-side + server allow-list
  guard. Read-back confirmation toast shows character_name from server.
- C2 phase param clobber → verified `_handle_phase_b_regen_audio` branches
  on `phase`. No risk.
- C3 PATCH storm → 250ms trailing-edge debounce; `change` not `input`.
- C4 re-patch double-insert → sentinel idempotency in patcher.

### Server restart required

The running server (port 5111) caches code at startup. After this patch,
restart via `POST /api/server/restart` or relaunch from
`start_production_server.command` to pick up the new routes. The
storyboard HTML is fresh on disk and will load the new sliders on next
browser refresh — but they will fail to hydrate until the server has
restarted.

Last updated: 2026-04-20 (panel-build extension).
