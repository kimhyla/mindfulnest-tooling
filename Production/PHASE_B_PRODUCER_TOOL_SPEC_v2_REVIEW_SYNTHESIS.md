# Spec v1 — Agent Review Synthesis

**Date:** April 17, 2026
**Reviews:** 4 advocate + 4 counter agents (8 total) on `PHASE_B_PRODUCER_TOOL_SPEC_v1.md`
**Status:** Synthesis complete — Kim decisions needed on flagged items before writing v2
**Phase 0:** `prod_preflight_reviews` id=44

---

## Summary

**Advocates endorsed the v1 spec's overall shape.** The 4-layer architecture, module-surface abstraction, constants-vs-variables carve, Flask-on-localhost approach, and Rule 18/15/19 governance framing all received endorsement.

**Counters found 25+ specific gaps — most are legitimate and must be fixed before Layer 0 coding starts.** No counter argued against the tool itself; all arguments were "the spec is under-specified, here's what to add."

Strongest endorsements:
- **Architecture:** §3.3 module surface + §1.3 constants table is the load-bearing abstraction
- **Data model:** Reusing `prod_audio_assets` + `prod_visual_assets` preserves the compliance gate invariant
- **Error handling:** Direct-query fallback for WaveSpeed polling codifies today's biggest learning
- **Governance:** Meaningfully stronger than today's scripts (April 14 audit found 7/9 skills had partial/zero registration)

**Net recommendation:** Accept 20 of 25 counter-agent amendments into spec v2. Flag 5 for Kim decision. Build proceeds after v2 approved.

---

## ACCEPT — direct amendments to spec v2 (20 items)

### Architecture
- **A1.** Add §3.3.1 "Inter-layer contracts" — define `LipSyncOutput` dataclass (path, duration_ms, fps, resolution, codec, sha256). Every layer validates prior layer's output shape before proceeding. No implicit trust between layers.
- **A2.** Replace hardcoded `constants.py` with `prod_production_profiles` Directus collection keyed by `(arc_id, profile_name)`. Default = `arc_1_default`. Every layer reads from active profile at job start.
- **A3.** Demote §1.3 constants to profile defaults with per-module overrides. Add `overrides_json` field on `prod_phase_b_sessions`. UI shows "Advanced" drawer (collapsed) exposing each.
- **A4.** Stage 4 library grid requires server-side pagination + tag filtering day one (not "filter toggle").
- **A5.** Add §7.1 "Same-origin hardening" — random per-session `X-PhaseB-Token` header on every mutating route, `@require_token` decorator on POST endpoints, 403 on missing header. Reason: screen-share-during-demos can expose localhost to any open Chrome tab's JS.

### Data model
- **D1.** Move pause annotations OFF `prod_scripts` INTO new `prod_script_pauses` collection with `script_id` + `script_version` + `pause_map_json` + content-hash. Prevents silent misalignment on script v1→v2.
- **D2.** `prod_phase_b_sessions` becomes append-only: add `session_version` + `supersedes_session_id` FK. Revisions create new row, never mutate old.
- **D3.** Timeline entries store `{asset_id, asset_content_hash, timecode_in, timecode_out}`. On load, verify hashes against `prod_visual_assets.content_hash`. Mismatch → `timeline_status=stale`, render blocked.
- **D4.** Split `asset_type=phase_b_library` into `phase_b_library_source` (owned by `library_gen.generate()`) and `phase_b_library_framed` (owned by Phase B Producer tool). Cross-ref via `derived_from_asset_id` FK. Resolves compliance gate one-owner rule.
- **D5.** Add `active_audio_asset_id` FK + `active_audio_kind` enum (`voice_stem`|`final_mix`) to session. UI reads only `active_audio_asset_id`. Resolves stem-vs-final ambiguity.
- **D6.** Add retention policy: `retention_status` enum (`active`|`superseded`|`failed`|`archive_candidate`) + `archive_eligible_at`. Nightly `phase_b_retention_sweep.py` cron. 14d/90d/7d thresholds.

### Governance
- **G1.** Expand §5.1 error matrix to include: OpenAI image-gen failures (rate/policy/5xx), disk-full, corrupt downloads (SHA256+duration probe), Directus schema drift (`/fields/{collection}` check), expired API key mid-session, browser session expiration (60s heartbeat), concurrent-edit collision with version tokens.
- **G2.** Rule 18 two-tier: Tier 1 decisions (structural — auto-register) vs Tier 2 activity (single edits — activity_log only). Add §6.4 classifier table. New keys: `ILLUSTRATION_LIBRARY_ADDED`, `ILLUSTRATION_LIBRARY_RETIRED`, `VOICE_PROFILE_OVERRIDE_PER_MODULE`.
- **G3.** Expand §5.3 to "Downstream Doc Impact Checklist" — 5 specific docs to PATCH before tool ships: PIPELINE_BRAIN, audio-producer SKILL.md, video-producer SKILL.md, SPEED-decision log, `.auto-memory/reference_project_files.md`. Hard gate.
- **G4.** Write `Production/governance/phase-b-producer-tool_governance.md` with 7 explicit checklist items: Rule 8.2 (lipsync source preservation), Rule 6 (illustration ≥600px), Rule 7 (Path A vs B), Rule 11 (verbatim dialogue), Rule 3 (.docx confirmation gate exemption for pipeline outputs), Registration Compliance Gate (5-check), voice profile lock (no override without `SHORTCUT_` decision).
- **G5.** Add §4.6 "Pre-Flight Re-Trigger Events": new pre-flight required when (a) adding a library illustration, (b) changing voice profile defaults, (c) new output format, (d) schema changes, (e) first use after >14 days idle.

### Error handling
- **E1.** Add §5.1a ffmpeg classification table: stderr regex → PERMANENT / TRANSIENT / UNKNOWN. Implement via `phase_b_pipeline.audio.FFmpegError` with `.classification` field.
- **E2.** §4.2 Stage 1 preview serialization: `/api/stage1/preview` returns HTTP 409 + `in_progress_sentence_id` if another preview is active. Client disables buttons. No queueing.
- **E3.** §4.4 retry-budget exhaustion writes HIGH-severity `prod_blockers` row. Dashboard-gate surfaces red at next session start. Flask app shows persistent red banner until dismissed.
- **E4.** Add §4.5a "Resume contract" — `compose.render_final` writes deterministic-named intermediates to `tmp/M{N}/compose/{clip_idx}_{start_ms}.mp4`. On crash, next run hashes/sizes check; reuses valid, re-renders missing.
- **E5.** Replace §6.2 "byte-identical" golden-path test with "determinism test" — freeze canonical `M1_golden_inputs.json` AFTER tool exists, run twice, assert identical outputs. Plus semantic-regression against POC v6: duration ±0.5s, audio RMS within 1dB, lipsync first/last frame MD5 stable.
- **E6.** Define exception hierarchy in §3.3: `PhaseBError` → `{ElevenLabsError, FFmpegError, LipSyncError, DirectusError}` each with `.transient: bool` and `.user_message: str`.

---

## KIM DECISIONS NEEDED — 5 items

### K1. Session locking mechanism (OQ4)

**Options:**
- (a) DB lock with 1-hour stale expiry (original spec §9)
- (b) Optimistic concurrency via `version_number` + heartbeat (counter recommendation)
- (c) Hybrid: optimistic concurrency on save + 5-min idle heartbeat releases lock

**My recommendation:** (c). Heartbeat every 60s from browser tab extends lock; idle >5min releases. On save, re-assert version — conflict → show diff UI, never silent overwrite. This matches what collaborative tools (Figma, Linear) do.

**Your call:** a / b / c?

### K2. Production profiles scope (A2)

**Option (a):** `prod_production_profiles` scoped only to Phase B (simpler, targeted).
**Option (b):** `prod_production_profiles` scoped to ALL production (Phase B, Phase A, narrative scenes, videos). Same collection, `profile_type` enum.

**Tradeoff:** (b) is better long-term architecture; (a) is faster to ship.

**My recommendation:** (a) for v1 launch, (b) as post-M2 migration task.

**Your call:** a / b?

### K3. Library illustration ownership split (D4)

Counter-agent recommends splitting `phase_b_library` into two asset_types: `source` (AI-generated raw) and `framed` (iron-wrapped for timeline).

**Questions:**
- Does Kim ever want to USE a source (un-framed) illustration directly in composition? If yes → keep both as active library.
- Or is the source strictly a build artifact that only the framed version matters for overlay?

**My recommendation:** split for auditability; treat framed as the "production" library Kim picks from. Source stays for regeneration without re-invoking AI.

**Your call:** split as proposed / keep unified?

### K4. Rule 18 auto-registration granularity (G2)

Counter proposes two-tier: structural decisions → `prod_locked_decisions`, single-edit activity → `prod_activity_log` only.

**Risk of high granularity (every pause edit):** decision bloat, 1000s of records per module.
**Risk of low granularity (only final approval):** loss of audit trail during iteration.

**My recommendation:** two-tier as counter proposed. Tier 1 keys trigger on milestones (stage completions, structural reorders). Tier 2 = all keystroke-level edits go to `prod_activity_log` only.

**Your call:** two-tier / keep granular as spec v1?

### K5. Build order — can we start Layer 0 work while amendments accumulate?

Amendments A1-A5, D1-D6, G1-G5, E1-E6 total ~60 concrete spec additions. Writing spec v2 = another 4-6 hours of my time. Layer 0 coding = 1 day minimum.

**Option (x):** Fully write v2 spec first, then code. Total: +2 days to tool arrival.
**Option (y):** Start Layer 0 coding NOW with v1 spec + accept list. Amend spec in parallel. Accept small rework risk on profile collection (A2) which affects early infra.
**Option (z):** Ship POC v6 first (lipsync finishes soon), Kim does the M1 listen-through / approval, THEN start v2 spec. Spec v2 lands in a future session.

**My recommendation:** (z). Today's focus is M1 POC landing cleanly. Spec v2 is a dedicated follow-up session where I can incorporate all amendments without lipsync distraction. Tomorrow's session = spec v2. Session after = Layer 0.

**Your call:** x / y / z?

---

## REJECT — 2 amendments I disagree with

### R1. Library grid pagination "required day one" (A4)
Counter cited this as blocking. I disagree as blocking — M1-M4 will have ≤20 library illustrations each. Pagination is a real concern at M20+ but premature for Layer 4 v1. Defer to v1.1.

### R2. Phase 0 re-trigger on "first use after >14 days idle" (G5)
Pragmatic concern but arbitrary threshold. Counter proposes this for the tool itself. I'd treat as "when Claude hasn't touched MindfulNest Phase B for 14+ days, re-read governance" which is already covered by the session-start 7-query protocol in `dashboard-gate`. Not a new trigger.

---

## Other notes from review

- The advocate for architecture called out §3.3's module surface + §1.3's constants table as "the load-bearing abstraction." Spec v2 should preserve and reinforce that.
- The advocate for data model highlighted the SINGLE strongest choice as reusing `prod_audio_assets` + `prod_visual_assets` (compliance gate preservation). Amendment D4 is compatible with this — it doesn't fragment the tables, it adds clearer ownership within them.
- The advocate for error handling cited the direct-query fallback as "the single largest step-function improvement." Today we lost ~40 min of debugging to WaveSpeed polling timeouts (confirmed by my own experience this session). Codifying this saves that time every module.

---

## Next action

Kim reviews this synthesis and answers K1-K5. Then:
1. If all decisions land today → I write spec v2 as a follow-up deliverable (~4-6 hours in next session)
2. POC v6 finishes today regardless (independent track)
3. Layer 0 coding starts only after spec v2 is Kim-approved
