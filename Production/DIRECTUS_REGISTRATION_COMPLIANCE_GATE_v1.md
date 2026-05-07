# Directus Registration Compliance Gate v1

**Created:** April 14, 2026
**Purpose:** Mandatory quality gate for all MindfulNest production skills that produce assets
**Enforcement:** Referenced in CLAUDE.md. Applies whenever skill-creator creates or modifies a production skill.

---

## When This Gate Applies

This gate is MANDATORY for any skill that lives in the MindfulNest production pipeline — meaning it produces, transforms, or delivers files, assets, audio, video, JSON configs, scripts, storyboards, or any other production artifact. If the skill only reads/queries data (like dashboard-gate) or is a meta-skill (like skill-creator itself), the gate does not apply.

## Why This Exists

On April 14, 2026, a full audit of all 11 MindfulNest production skills revealed that 7 of 9 asset-producing skills had zero or partial Directus registration. Skills were built incrementally across sessions, and no one checked whether they registered their outputs. The result: files existed on disk but the system of record (Directus) didn't know about them — silent data loss that compounded across sessions. This gate prevents that from ever happening again.

See `Production/LESSONS_LEARNED_DIRECTUS_REGISTRATION_AUDIT_April2026.md` for the full root cause analysis.

---

## The 5-Check Gate

Before marking any MindfulNest production skill as complete, verify ALL five checks pass:

### Check 1: Does this skill produce files or assets?

Read the skill end-to-end. List every output: files written to disk, API responses saved, configs generated, audio rendered, images created, HTML built. If the skill produces NO outputs (it only queries, validates, or orchestrates without creating files), mark this check as N/A and skip the remaining checks.

### Check 2: For EACH output, is there a REGISTER block?

Every production output must have an explicit registration block formatted as:

```
**REGISTER: [Output description] → Directus (MANDATORY)**
```

The block must contain TWO curl POST commands (the Two-Write Rule):

1. **Asset collection write** — registers the file in the appropriate Directus collection (`prod_audio_assets`, `prod_visual_assets`, `prod_scripts`, `prod_phase_a_scenes`, or `prod_module_json`) with metadata including at minimum: `module_id`, the collection-specific type field (`asset_type`, `script_type`, etc.), `file_path`, and `status`.

2. **Activity log write** — logs the action in `prod_activity_log` with: `module_id`, `action` (descriptive string), `performed_by` ("claude"), and `details` (JSON with relevant context like iteration count, tool used, version, etc.).

**Exception — sub-skills:** If this skill is a sub-utility whose outputs are consumed by a parent orchestrator skill *within the same skill execution* (e.g., scene-to-production produces shot breakdowns that video-producer consumes in the same production run), it should log ACTIVITY ONLY (no asset registration) to avoid duplication. The parent skill registers the final asset. Document which parent skill owns the asset registration. **Clarification:** If a skill produces outputs that are consumed by another skill in a *separate* execution (e.g., different session, different pipeline run), that skill IS the final producer and MUST register the asset — the "sub-skill" exception only applies to same-execution chains.

### Check 3: Do the field names match the live Directus schema?

For each registration curl in the skill, verify field names against the live schema:

```bash
BASE="https://directus-production-3460.up.railway.app"
TOKEN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"EMAIL","password":"PASSWORD"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['access_token'])")
# Check fields for any collection:
curl -s "$BASE/fields/{COLLECTION_NAME}" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import json,sys; [print(f['field']) for f in json.load(sys.stdin)['data']]"
```

Read credentials from `Production/API_KEYS_MASTER.md`. Every field name in the skill's curl commands must appear in the schema output. Zero mismatches required.

**Schema drift warning:** Run this check at DEPLOYMENT TIME, not just at creation time. Directus collections can evolve between sessions (fields added, renamed, or removed). A skill that passed Check 3 when created may fail after schema changes. Always re-verify before first use in a new session.

### Check 4: Is there exactly ONE skill responsible for each asset_type?

Consult the ownership table below. If this skill registers an `asset_type` that another skill already owns, there's a conflict. Resolution: the downstream/final skill owns the registration; the upstream skill logs activity only.

**Current ownership (as of April 14, 2026):**

| Asset Type | Owning Skill | NOT Registered By |
|-----------|-------------|-------------------|
| `tts_dialogue` | video-producer | elevenlabs-tts |
| `voice_stem` | audio-producer | phase-b-writer |
| `flux_still` | video-producer | scene-to-production |
| `animation_clip` | video-producer | scene-to-production |
| `lipsync_clip` | video-producer | (no overlap) |
| `final_video` | video-producer | (no overlap) |
| `complete_mix` | audio-producer | video-producer |
| `storyboard_html` | storyboard-producer | (no overlap) |
| `phase_b_meditation` (script) | phase-b-writer | audio-producer |
| `intake_brief` (script) | intake-briefer | (no overlap) |
| Phase A scenes | phase-a-designer | video-producer |
| Module JSON | module-json-builder | video-producer |

If the new skill introduces a NEW asset_type not in this table, add it here and in `DIRECTUS_REGISTRATION_PATCH_PLAN_v1.md`.

### Check 5: Does each REGISTER block include a progression gate?

After each registration curl, the skill must include:

1. **Verification query** — confirms the registration succeeded by querying the collection for the just-created record
2. **"Do not proceed" gate** — explicit text blocking progression to the next step until registration is confirmed
3. **Failure protocol** — what to do if registration fails:
   - Re-authenticate on 401 (JWT token expired, 15-min TTL)
   - Retry once on 500
   - On persistent failure: log to local file (`Production/Event_{N}/PENDING_REGISTRATIONS.json`) and warn Kim
   - Production can continue but pending registrations must be resolved before session ends

### Check 6 — Wrapper Compliance (added 2026-04-26 per LD-421)

**Question:** Does this skill use `Production/tools/registered_write.py` for ALL file-write operations that produce media (.mp4 / .mp3 / .wav / .png / .webp / .jpg) under `Production/`?

**Required:** YES. Direct `ffmpeg -y output.mp4` / `imageio.imwrite()` / raw `open(... 'wb')` / `cv2.VideoWriter` / `shutil.copy(media)` writes that bypass the wrapper are FORBIDDEN. The wrapper performs atomic Two-Write Rule registration: `prod_assets` POST + `prod_activity_log` POST + sandboxed-path validation + SHA256 dedup.

**Whitelist (writes that don't need the wrapper):** paths containing `_temp_`, `_sandbox`, `/tests/`, `debug_`, `_tmp_`, or `_previews` — these are scratchpads, not deliverables.

**Verification:**
1. Grep the skill file (`SKILL.md`) AND any underlying tool script (`Production/tools/*.py` it invokes) for `from Production.tools import registered_write` (or `import registered_write`) — must be present in at least one of them.
2. Grep for direct media writes outside the wrapper — none allowed unless on a whitelisted path.
3. Smoke test: invoke the skill on test data → produce one media file → verify a row appears in `prod_assets` via `python3 Production/tools/find_asset.py --phrase "<unique iteration_notes token>"`.

**Cross-platform requirement (LD-367):** Both the wrapper and any helper resolve `MINDFULNEST_PROJECT_ROOT` env var first, then fall back to `platform.system()`-branched defaults (Mac default vs Windows default). Hardcoded user-specific paths (`/Users/kimberlysmith/...` or `C:\Users\ECDS Clinical\...`) must NOT appear outside that branching block.

**Validator:** `python3 Production/scripts/check_compliance_gate_6.py --all-skills --verbose`

**Failure handling:** Skill cannot be marked complete until all three sub-checks pass.

---

## Gate Result

**If all 6 checks pass:** The skill is production-ready from a Directus registration standpoint. Proceed with deployment.

**If ANY check fails:** The skill is NOT production-ready. Add the missing registration blocks before deploying.

**Templates:** Reference the patched skills as gold-standard registration patterns:
- `video-producer/SKILL.md` — 7 registration blocks (most comprehensive example)
- `audio-producer/SKILL.md` — 2 registration blocks with Kim listen-through approval flow
- `phase-b-writer/SKILL.md` — Script registration with Kim verdict PATCH template
- `storyboard-producer/SKILL.md` — Visual asset registration with audit-fail blocker path
- `visible-magic/SKILL.md` + `Production/tools/magic_compositor.py` — Wrapper-paired registration via `MagicCompositor._maybe_register()` (Check 6 reference implementation, 2026-04-26 LD-422 wiring)

---

## Reference Documents

| Document | Location | What It Provides |
|----------|----------|-----------------|
| Patch Plan v1 | `Production/DIRECTUS_REGISTRATION_PATCH_PLAN_v1.md` | Patch templates, ownership table, field schemas |
| Lessons Learned | `Production/LESSONS_LEARNED_DIRECTUS_REGISTRATION_AUDIT_April2026.md` | Root cause analysis, Two-Write Rule explanation, what NOT to register |
| Dashboard Ops | `.claude/skills/dashboard-ops/SKILL.md` | Directus API patterns, auth flow, collection schemas |
| Pipeline Brain | `Production/PIPELINE_BRAIN_v1.md` | Full pipeline architecture, skill dependencies |
