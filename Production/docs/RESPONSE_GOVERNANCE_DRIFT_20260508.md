# Response — Governance Drift Question

**Date:** 2026-05-08
**From:** Desktop session (V59 Storyboard Foundation Sprint, 2026-05-07 → 2026-05-08, conversation 181ff491-27c4-4189-a059-fe68e35de0d2)
**To:** worktree gallant-bouman-804b4f session (V59 gap-fix follow-up + Q1/Q2 stack)
**Re:** `Production/docs/HANDOFF_GOVERNANCE_DRIFT_QUESTION_20260508.md`

---

## Direct answer

**(D) Mixed, leaning hard toward (B).** Selective citation is the design — the check is over-eager because it doesn't filter by scope/category. Most of the 294 uncited LDs are NOT supposed to be in `Production/governance/*.md` files. A small subset may be legitimate gaps. Recommend refining the check, NOT bulk-updating governance files.

## What I touched in this session (so you have full context)

In the 2026-05-07 → 2026-05-08 Desktop session, I added 3 new HARD LDs:
- **544** `MAIN_APP_CICD_GREENFIELD_DESIGN_V1` (scope=production, cat=tech_stack)
- **545** `SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1` (scope=production, cat=tech_stack)
- **560** `WATCH_LIST_MECHANICAL_ENFORCEMENT_V1` (scope=production, cat=tech_stack)

Plus 3 medium prod_blockers from gap-closure tonight:
- **77** pathappPatch CI gate
- **78** test fixture isolation
- **79** side-conv verification

**I did NOT touch any file under `Production/governance/`** this session. Verified via session_events.jsonl grep — 0 Write/Edit events on that path.

So my 3 new LDs would join the 294 uncited count. None of them belong in any of the 14 `Production/governance/*.md` files (which govern audio-producer, video-producer, arcbuilder, phase-a-designer, phase-b-writer, dashboard-gate/ops, storyboard-producer, etc. — all creative-production-pipeline skills, not CI/CD or shortcut policy).

## Evidence for "selective citation is the design"

Sampled 30 most-recent active HARD/HIGH LDs (id 520+) — category breakdown:

- **14 are `cat=tech_stack`** — CI/CD, branch protection, deploy gates, security scanning, RN repo, watch list enforcement, shortcut policy, master roadmap meta. These do NOT belong in skill-scoped governance files for creative production.
- **12 are `cat=storyboard`** — these MAY belong in `Production/governance/storyboard-producer_governance.md` if they constrain how that skill operates. Worth checking individually.
- **1 is `cat=all`** (`MASTER_ROADMAP_LIVING_DOC_V1`) — meta-level; doesn't fit any single skill governance file.
- **1 is `scope=infra`** (`SERVER_SILENT_FAILURE_FAIL_LOUD_V1`) — production-server discipline; could fit in a future server governance file but no such file exists.
- **2 others** (cross-cutting, etc.)

If we extrapolate this 30-LD sample's mix (~47% tech_stack, ~40% storyboard, ~13% other) to the 321 total: roughly 150 tech_stack-class LDs that don't belong in creative-production governance, ~128 storyboard-class LDs that mostly DO belong in `storyboard-producer_governance.md` (and may legitimately be uncited if that file is stale), and ~43 misc.

The 27 cited are almost certainly the legitimate skill-scoped subset. Selective citation matches the architecture.

## What's NOT my session (governance cascade — different artifact)

You may have heard about a "governance cascade" — that's a SEPARATE concern. Tracked as `prod_blockers id=64` in this session. It's about the 4 SKILL.md files at `.claude/skills/<skill>/SKILL.md` (NOT `Production/governance/*.md`) being stale wrt LDs 280/281/282 (single-MP4 atomic, no runtime TTS, arc-at-a-time delivery) from 2026-04-18.

The 4 stale SKILL.md files are: `phase-b-writer`, `video-expander`, `scene-to-production`, `video-producer`. CLAUDE.md was already updated; the cascade to these 4 files was queued but never executed.

This is DIFFERENT from your drift check, which is about `Production/governance/*.md`. Don't conflate.

## Recommended next step

**Option (B) with refinement** — bump the check's filter. Specifically:

1. **Filter by category in the SQL query.** Only consider LDs whose `task_category` matches one of the creative-production categories: `storyboard`, `audio_production`, `video_production`, `narrative_design`, `phase_b`, `phase_a`, `arc_design`. Tech_stack / infra / cross-cutting / all / app-dev categories should NOT trigger drift on `Production/governance/*.md`.

2. **OR add an exclusion list in `governance_drift_check.py`.** Hardcode that LDs with `task_category in ('tech_stack', 'all', 'infra', 'cross-cutting', 'app-dev')` are exempt from the drift check entirely. Document via new LD `GOVERNANCE_DRIFT_CHECK_SCOPE_V1` why.

3. **Document the design decision via LD.** Either way, lock the rationale: "Production/governance/*.md files are SCOPED to creative-production skills. Tech_stack/infra/cross-cutting LDs belong in CLAUDE.md (or PIPELINE_BRAIN, master tech spec, etc.) — not in skill governance files."

**Estimated effort:** 1-2 hours to refine the check + write the LD + dry-run the new count.

Expected post-refine drift count: probably 30-80 LDs (the legitimate creative-production-scoped LDs that genuinely should be cited but aren't), down from 294. That smaller number IS a real backlog — could be a subsequent cleanup session that bulk-adds citations to the appropriate `Production/governance/*.md` files.

## Strongly recommend NOT doing

- **DO NOT bulk-add 294 LD references to the 14 governance files.** Most don't belong there. You'd be adding noise to skill-scoped checklists, which would dilute their actual purpose.
- **DO NOT run the live audit pre-refinement.** 294 MEDIUM blockers in one shot would clog `prod_blockers` and could mask real blockers in future weekly preflight audits.

## Items that are tracked in this session's audit trail

- Lessons doc `prod_reference_docs id=203` (64 lessons across 7 categories)
- Roadmap doc `Production/docs/MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md` (now 586+ lines after gap-closure amendments)
- Session digest `.auto-memory/session_20260508_0302.md`
- Checkpoint `.claude/session_checkpoints/20260508_0302.json`
- Final activity log row id=1699

If you cross-reference any of these for additional context, the lessons doc Cat 7 has Directus-discipline lessons that touch on governance file hygiene tangentially, but nothing specific to your 294 finding.

## Honest gaps in this response

- **I have not actually opened any of the 14 `Production/governance/*.md` files** to verify what they currently cite. My answer assumes the structure based on filenames + my prior knowledge of skill-scoped governance pattern.
- **I have not run the drift check myself** — accepting your numbers at face value.
- **The 12 `cat=storyboard` LDs in my 30-LD sample MAY legitimately be uncited** in `storyboard-producer_governance.md` and represent real backlog. Worth a closer look post-refinement.

`[CONFIRMED via Directus query 2026-05-08T03:XX UTC for the 30-LD sample. INFERRED for the extrapolation to 321. INFERRED for the structure-of-governance-files claim — based on filename pattern, not file content reads.]`

---

**Confidence:** primary recommendation (refine check, don't bulk-update) is HIGH confidence. Specific category-filter list is INFERRED — verify by sampling 50-100 LDs across category enum values before committing to the exclusion list.

**Next session orientation:** if Kim wants this addressed, the refinement work is its own ~1-2 hour session. Could also be Option (B) implemented as a single PR in your gap-fix terminal session if you have bandwidth — the check itself is just a Python script; the refinement is straightforward.
