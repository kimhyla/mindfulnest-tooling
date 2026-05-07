# Lessons Learned: Directus Registration Audit — April 14, 2026

**Session type:** Infrastructure audit + skill patching  
**Duration:** ~3 hours  
**Outcome:** 2 skills patched (video-producer, audio-producer), full audit of remaining 9 skills, patch plan for 6 more

---

## 1. What Happened

During a strategy review session, Kim asked for a full inventory of what was actually registered in Directus. The query returned healthy numbers: 57 visual assets, 34 audio assets, 5 scripts, 6 modules, 2 voice profiles, 11 locked decisions, 14 session decisions. Everything looked fine on the surface.

Then we audited the production skills themselves — asking not "what's in the registry?" but "what SHOULD be in the registry?" — and found a systemic gap. The video-producer skill, which is the most asset-intensive skill in the pipeline (producing TTS dialogue, FLUX stills, animation clips, lip-sync clips, final videos, module JSON, and activity logs), had ZERO Directus registration instructions for any of its 7+ output types. Audio-producer was missing voice stem and final mix registration. When we extended the audit to all 11 production skills, 7 of 9 had zero or partial registration.

## 2. Root Causes

**No shared registration standard at skill-creation time.** Skills were built incrementally across multiple sessions (March 28 – April 14, 2026). The Two-Write Rule existed in dashboard-gate (the behavioral gatekeeper skill), but it was written as a runtime enforcement rule, not a skill-authoring requirement. Each skill author (always Claude, in different session contexts) built what was needed for that session's production work without considering whether future sessions could find the outputs.

**Consumption-first mindset.** The pipeline registered assets when it CONSUMED them (storyboard-producer queried the registry to find images; audio-producer checked module stage status), not when it CREATED them. This meant the consumption side worked perfectly — but creation-side registration was invisible because no one was querying for assets that didn't exist yet.

**Sub-skill vs. parent-skill ambiguity.** elevenlabs-tts generates TTS files, but video-producer also generates TTS files (by calling ElevenLabs). Who registers them? Without a clear ownership rule, neither did. The audit resolved this: the parent orchestrator (video-producer, audio-producer) registers final assets; sub-utilities (elevenlabs-tts, scene-to-production) log activity only.

**skill-creator had no compliance gate.** The skill-creator skill — the meta-tool that builds and modifies other skills — had no check for "does this skill register its outputs?" It validated trigger words, description quality, and structural format, but not Directus integration. The most important operational requirement was invisible to the quality gate.

## 3. The Two-Write Rule (What It Is and Why It Works)

Every production output must receive two Directus writes:

1. **Asset collection write** — registers the file in the appropriate collection (`prod_audio_assets`, `prod_visual_assets`, `prod_scripts`, `prod_phase_a_scenes`, or `prod_module_json`) with metadata: module_id, asset_type, file_path, status, version, and descriptive notes.

2. **Activity log write** — logs the action in `prod_activity_log` with: module_id, action description, performed_by, details (JSON with iteration count, tool used, cost, etc.).

The two writes serve different purposes. The asset write answers "what exists?" — it's the registry that lets future sessions find and reuse outputs. The activity log answers "what happened?" — it's the audit trail that lets Kim (or a future Claude session) understand the sequence of decisions.

An asset without an activity log entry is findable but unexplained. An activity log entry without an asset registration is documented but unfindable. Both are failure modes. The Two-Write Rule eliminates both.

## 4. How We Diagnosed It

**Phase 1 — Inventory query.** Queried all Directus collections to see what was registered. This gave a false sense of completeness because we were asking "what do we have?" instead of "what should we have?"

**Phase 2 — Skill-level audit.** Two independent agents read video-producer and audio-producer end-to-end, mapping every output to its registration status. This was the breakthrough — the gap was immediately obvious when viewed from the skill's perspective rather than the database's perspective.

**Phase 3 — Full sweep.** Five audit agents + five counter-agents covered all 11 skills. The counter-agents were critical for avoiding over-patching — they identified cases where sub-skills shouldn't register (to avoid duplication with parent skills) and prioritized fixes into three tiers.

## 5. How We Fixed It (The Pattern)

For each skill, the patch follows a consistent format:

```markdown
**REGISTER: Step X output → Directus (MANDATORY)**

For EACH [output type]:
\```bash
# 1. Register in [collection]
curl -s -X POST "$BASE/items/[collection]" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ fields matching live schema }'

# 2. Log in prod_activity_log
curl -s -X POST "$BASE/items/prod_activity_log" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ action, details, performed_by }'
\```
**Do not proceed to Step X+1 until registered.**
```

Key elements: explicit curl templates with real field names (validated against live Directus schema), a gate that blocks progression until registration succeeds, and a failure protocol (retry on 401, log to local file on persistent failure, warn Kim).

**Verification protocol:** After patching, independent agents re-read the files to confirm all blocks are present. Then a Python script cross-checks every field name used in the patches against the live Directus schema — zero mismatches means the patches will work the first time they're executed.

## 6. What We're NOT Registering (And Why)

Not every intermediate artifact deserves a Directus entry. The counter-agents established this principle:

**Register:** Final deliverables that Kim reviews, assets consumed by downstream skills, artifacts that represent locked decisions (approved scripts, validated JSON, approved stills).

**Don't register:** Working drafts that will be superseded within the same session, research dossiers and vocabulary cards (clinical working documents), timing calculations and body test notes (ephemeral process artifacts).

**Activity-log only (no asset registration):** Sub-skill outputs that feed into a parent skill which registers the final form. Example: scene-to-production produces shot breakdowns that video-producer consumes — video-producer registers the resulting stills and clips, not the shot breakdown text.

## 7. Ownership Rule: One Asset Type, One Registering Skill

The most important architectural decision from this audit:

**Every `asset_type` value must have exactly one skill responsible for registering it.** If two skills produce the same asset_type for the same module, consolidate to the downstream (final) skill. This prevents duplicate entries and ownership confusion.

| Asset Type | Owning Skill | NOT Registered By |
|-----------|-------------|-------------------|
| `tts_dialogue` | video-producer | elevenlabs-tts |
| `voice_stem` | audio-producer | phase-b-writer |
| `flux_still` | video-producer | scene-to-production |
| `animation_clip` | video-producer | scene-to-production |
| `complete_mix` | audio-producer | video-producer (removed) |
| `phase_b_meditation` | phase-b-writer | audio-producer |
| `storyboard_html` | storyboard-producer | (no overlap) |
| Module JSON | module-json-builder | video-producer (to be removed) |

## 8. Prevention: What Changes Going Forward

**skill-creator compliance gate (to be added).** Before any skill is marked complete, skill-creator must verify: (1) does this skill produce outputs? (2) For each output, is there a REGISTER block? (3) Does each block include both writes? (4) Do field names match the live schema? (5) Is there exactly one skill per asset_type? Failure = skill is not production-ready.

**Session-start staleness scan expansion.** The existing staleness scan (CLAUDE.md) checks for document drift. It should also check: "Are there files in Production/Event_*/ that don't have corresponding Directus entries?" This catches registration failures from previous sessions.

**Dashboard-gate enforcement.** Dashboard-gate already enforces the 7-query protocol at session start. It should also enforce: "Before any asset is created, confirm registration plan. After any asset is created, confirm registration was executed." The behavioral gatekeeper needs to be the registration gatekeeper too.

## 9. Files Produced This Session

| File | Location | Purpose |
|------|----------|---------|
| video-producer SKILL.md (patched) | `.claude/skills/video-producer/SKILL.md` | 7 registration blocks + protocol section added |
| audio-producer SKILL.md (patched) | `.claude/skills/audio-producer/SKILL.md` | 2 registration blocks + approval flow added |
| DIRECTUS_REGISTRATION_PATCH_PLAN_v1.md | `Production/` | Explicit instructions for patching remaining 6 skills |
| This lessons learned document | `Production/` | Root cause analysis + prevention plan |

## 10. Key Metrics

- **Skills audited:** 11 (all production skills)
- **Skills with critical gaps:** 7 (64%)
- **Skills patched this session:** 2 (video-producer, audio-producer)
- **Registration blocks added:** 9 total (7 video-producer + 2 audio-producer)
- **Field-name mismatches found:** 0 (all 13 curl templates validated against live schema)
- **Skills fully compliant before audit:** 2 (narrative-generator, dashboard-gate)
- **Remaining patches queued:** 4 Tier 1 + 2 Tier 2
- **Estimated time for remaining patches:** 2-3 hours
