# LD-505 Pre-Phase-A Triage Audit — 2026-05-10

**Author:** Claude (suspicious-lamarr-fa21b2 worktree, read-only audit mode)
**Generated:** 2026-05-09 (date is the spec target; Kim's prompt named the file `_20260510.md`)
**Mode:** Option A — read-only. NO commits, discards, gitignore writes, or rm operations performed by this session.
**Successor:** main session (gallant-bouman-804b4f) executes on these findings.

---

## 0. Phase 0 / DS-19 escape-hatch findings (read these first)

The original triage spec assumed a stable working tree of ~863 stale-but-discardable files. Reality differs in four material ways. The execution session must factor these in BEFORE running any destructive op.

### F-1. Dropbox repo has NO git remote (local-only)

```
$ git -C "<DROPBOX>" remote -v
(empty)
```

Spec says "create branch... apply, push, PR" against this repo. **Impossible** — no upstream. The dual-canonical-roots pattern requires routing PR-bound code commits to **`~/Projects/mindfulnest-tooling`** (which has GitHub remote), and Dropbox-tree commits stay strictly local. The audit doc you are reading reflects this constraint.

### F-2. The 38 "modified" files are an in-progress tooling-sync, NOT stale leftovers

mtime distribution of modified files:
- **35 files** touched at **2026-05-09 15:36** (same-second batch — automated edit run)
- **`Production/scripts/weekly_preflight_audit.py`** at **17:28**
- **`Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md`** at **18:16** (this session's amendment per the Kim-supplied prompt)

Sample diff (`registered_write.py`, representative of the 15:36 batch):
```diff
-from Production.tools.lib import credentials, directus
+from Production.tools.credentials_lib import credentials, directus
```

**Cross-repo verification:**
- Tooling repo HAS `Production/tools/credentials_lib/` (5 files: `__init__.py`, `credentials.py`, `directus.py`, `directus_admin_client.py`, `ffmpeg_stitch.py`)
- Tooling repo does NOT have `Production/tools/lib/`
- Dropbox repo HAS `Production/tools/lib/` (the 4 RM + 1 R rename entries are exactly the 5 files moving lib/→credentials_lib/)
- The 35 same-second files are import-path updates aligning with the rename
- `Production/scripts/weekly_preflight_audit.py` in Dropbox is **byte-identical** (`diff -q` empty) to tooling's uncommitted version

**Interpretation:** an automated sync brought Dropbox into alignment with tooling's already-completed `lib/`→`credentials_lib/` refactor + an LD-576 matcher tightening. This is mid-flight infrastructure work, not stale debris.

### F-3. Branch + worktree state contradicts spec's mental model

- Main checkout HEAD: `feature/payload-validator-v4-impl-20260509` (38 commits ahead of `main`)
- Last commit: `0bb4242 Payload Validator v4-D implementation per spec` (clean +1125 LOC, only 2 files: `Production/lib/payload_validator.py` + tests)
- **12 worktrees** share this `.git/` (9 active claude/ worktrees + main + 1 prunable Windows + this audit's worktree). Concurrent Claude sessions can collide on shared index ops.
- A previous "preserve uncommitted edits as snapshot" commit exists on this branch: `95e4462 preserve: snapshot uncommitted Dropbox-tree edits (BG-37 audit + C-9 registered_write refactor + 28 client/server files)` — proves Kim's pattern is to bundle batches as preserve commits rather than per-file triage.

### F-4. Status entry count drifted 863 → 868 in <30 min during audit setup

Suggests something is writing while audit runs. Confirms F-3's collision risk. Execution session should either pause concurrent worktree activity OR use `git stash --include-untracked` snapshot before commits.

---

## 1. Executive summary — disposition rollup

| Bucket | Count | Recommended disposition |
|---|---:|---|
| **Tier 1A** — 35 modified import-path updates (15:36 batch, lib→credentials_lib) | 35 | **PRESERVE-COMMIT-DROPBOX-LOCAL** as one bundle commit on current feature branch (matches `95e4462` precedent). Tooling already canonical. |
| **Tier 1B** — 5 R/RM rename entries (lib→credentials_lib physical move) | 5 | **PRESERVE-COMMIT-DROPBOX-LOCAL** (same bundle as 1A) |
| **Tier 1C** — `weekly_preflight_audit.py` (17:28) | 1 | **TOOLING-FIRST** — see Tier 7. Land tooling commit, then commit Dropbox copy as sync. |
| **Tier 1D** — `V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md` (18:16) | 1 | **COMMIT-DROPBOX-LOCAL** (real session amendment, +156/−82) |
| **Tier 1E** — `STORYBOARD_V59_S5_5_G_SPEC_v1.md` (15:36) | 1 | **COMMIT-DROPBOX-LOCAL** (with Tier 1A bundle) |
| **Tier 2** — `.claude/skills/` (39 entries: 37 dirs + 2 md + zero-error-qa backups) | 39 | **GITIGNORE** entire `.claude/skills/` (Claude Code local config; not source-of-truth content) — but VERIFY first that the canonical skill source lives elsewhere. See §4. |
| **Tier 3** — `Production/Event_1/` (327 entries) | 327 | **BULK GITIGNORE** — production output (126 .html, 65 .md, 48 .json, 41 .py, 23 .txt + binaries incl `Claude.dmg`). Pattern: `Production/Event_*/`. Whitelist exceptions only if you have a specific canonical file to track. |
| **Tier 4** — `Production/docs/` (99 entries) | 99 | **COMMIT-DROPBOX-LOCAL** for ~85; **DISCARD** for ~10 superseded tech-spec versions; **SURFACE** for ~4. See §6. |
| **Tier 5** — `Production/tools/` (45 entries: 16 ts duplicate of tooling + 19 docs + 4 json state + ...) | 45 | **MIXED** — see §7. 16 storyboard-v2/e2e/*.ts duplicates of tooling = DISCARD-AS-TOOLING-CANONICAL or PRESERVE; 19 .md = COMMIT; .lock + state files = GITIGNORE. |
| **Tier 6A** — Root-level legacy *.md / *.html / *.txt (~190) | ~190 | **MOVE-TO-`archive/`+GITIGNORE** OR **DISCARD**. April-2026 era reports/handoffs that should never have been at repo root. |
| **Tier 6B** — Root-level recent (May 2026) *.md (~10) | ~10 | **COMMIT-DROPBOX-LOCAL** (move into `Production/docs/` first if doing it cleanly; or commit at root then move) |
| **Tier 6C** — Root-level untracked content directories (22 dirs) | 22 | **GITIGNORE** all (`Marketing/`, `Old Versions/`, `Research/`, `Session Logs/`, `Module Demos/`, `Parent Coach/`, `App Design/`, `Business/`, `Clinical/`, `Cropper/`, `Canon/`, `Arc Skeletons/`, `Claude Code History backup 2026-04-15/`, `archive/`, `.deploy_backups/`, `content-lockfiles/`, `scripts/`, `video_pipeline/`, `case-study-skill/`, `email-nurture/`, `website-copy-skill/`, `Claude ElevenLabs Phase B Module Sounds/`). Working/content dirs not source code. |
| **Tier 6D** — Root-level loose state/temp/lock/log/tmp/conflicted files | ~9 | **DISCARD** + **GITIGNORE** the patterns. (`server_restart.log`, `Production/tmp*.tmp`, `*conflicted copy*`, `desktop (2).ini`, `feedback.json`, `fal_lora_result.txt`, `test_write.txt`, `mindfulnest_full_schema.sql`, `storyboard_sequence_2026-04-16.json`, `crop_manifest_M1_e1.json`, `crop_manifest_M1_e1 (1).json`, `animation_selections.json`, `animation_selections (1).json`, `dashboard-ops-eval-viewer.html`, `*.skill/`, `ziR6fyTf/`) |
| **Tier 7** — Tooling repo: `weekly_preflight_audit.py` M + `test_pr_merge_closure_matcher.py` ?? | 2 | **REVIEW + COMMIT-TOOLING + PUSH + PR**. LD-576-amend-1 matcher-tightening regression suite. Self-contained. See §9. |

### Headline numbers

- 868 Dropbox dirty entries → after triage, target ≤5 entries (the audit doc itself + any items moved to deferral list)
- 2 tooling dirty entries → after Tier 7 PR merge, target 0
- Estimated commits in execution session: **5–8** in Dropbox + **1 tooling PR**
- Estimated `.gitignore` additions: **8–12 patterns** covering Event_*, .claude/skills/, root content dirs, lock/tmp/state patterns

---

## 2. Operating constraints for the execution session

1. **Coordinate with concurrent worktrees first.** 12 worktrees share this `.git/`. Before any commit/discard, confirm no other Claude session is mid-flight in another worktree. Run `git -C "<DROPBOX>" worktree list` and check for active sessions in `.claude/sessions/`.

2. **Use `git stash --include-untracked` as safety net** before any discard or `git clean`. Per spec:
   ```bash
   git -C "<DROPBOX>" stash push --include-untracked -m "pre-triage-snapshot-$(date -u +%Y%m%d_%H%M%S)"
   git -C "<DROPBOX>" stash apply
   ```

3. **Tooling-first ordering for Tier 1C + Tier 7:** push tooling PR FIRST (the `weekly_preflight_audit.py` change + LD-576 matcher test), then merge, then commit the Dropbox sync as one preserve commit. This avoids divergence.

4. **Per LD-505, canonical CODE = tooling.** Any 1A/1B/1C/Tier-7 code path that lands in tooling can be DISCARDED in Dropbox safely (Phase E will eliminate Dropbox `.git/` anyway). The `PRESERVE-COMMIT-DROPBOX-LOCAL` recommendation is the conservative fallback if you want a rollback point before Phase E.

5. **Do not use `git clean -fd`** anywhere — too aggressive given the conflicted-copy + content-dir mix. Use targeted `rm` after `.gitignore` additions take effect.

6. **`.gitignore` additions land FIRST**, then verify `git status --short | wc -l` drops appropriately, then commit the `.gitignore` change separately as a focused commit.

---

## 3. Tier 1 detail — 38 M + 5 R/RM (43 entries)

### Tier 1A: 35 lib→credentials_lib import-path updates (commit 15:36 batch)

Recommendation: ONE bundle commit on `feature/payload-validator-v4-impl-20260509`:
```
preserve: lib→credentials_lib import-path sync (35 files) + LD-505 spec amendment

Mirrors tooling repo's already-completed credentials_lib relocation (LD-227 Phase 1).
All edits are mechanical 1-line import path swaps.
```

Files (full list, all status `M`):
```
Production/scripts/_preflight_governance_bundle_20260416.py
Production/scripts/create_prod_preflight_reviews.py
Production/scripts/orphaned_ideas_rescue_cascade_20260417.py
Production/scripts/phase0_blocker_3_9_preflight.py
Production/scripts/phase5_blocker_3_9_directus.py
Production/scripts/stage3_security_rules_first_cascade.py
Production/tools/_option_c_prototype_exec/01_phase0_preflight.py
Production/tools/_option_c_prototype_exec/02_amend_ld204.py
Production/tools/_option_c_prototype_exec/04_schema.py
Production/tools/_option_c_prototype_exec/05_views.py
Production/tools/_option_c_prototype_exec/06_roles.py
Production/tools/_option_c_prototype_exec/07_seed.py
Production/tools/_option_c_prototype_exec/08_wire_dragdrop.py
Production/tools/_option_c_prototype_exec/10_flow.py
Production/tools/_option_c_prototype_exec/14_visual_assets_schema.py
Production/tools/_option_c_prototype_exec/_clients.py
Production/tools/_option_c_prototype_exec/prototype_kling_adapter.py
Production/tools/find_asset.py
Production/tools/kling_startend_pipeline.py
Production/tools/phase_a_tts.py
Production/tools/pipeline.py
Production/tools/production_server.py
Production/tools/production_server_pre_spec_ab_backup.py
Production/tools/recover_stuck_tasks.py
Production/tools/regen_tts_beat_06_09.py
Production/tools/register_preflight_bugs_1_2.py
Production/tools/registered_write.py
Production/tools/tests/test_per_beat_fade_override.py
Production/tools/tests/test_phase_b_panel.py
Production/tools/tests/test_preview_stitched.py
Production/tools/tests/test_preview_stitched_real_ffmpeg.py
Production/tools/tests/test_scope_router_scrambled.py
Production/tools/tests/test_swap_to_a.py
Production/tools/tests/test_tier1a_debounce.py
Production/tools/upload_module.py
```

Note: `Production/docs/STORYBOARD_V59_S5_5_G_SPEC_v1.md` is also in the 15:36 batch (Tier 1E). Bundle it with this commit.

### Tier 1B: 5 lib→credentials_lib rename entries

```
RM Production/tools/lib/__init__.py             -> Production/tools/credentials_lib/__init__.py
RM Production/tools/lib/credentials.py          -> Production/tools/credentials_lib/credentials.py
RM Production/tools/lib/directus.py             -> Production/tools/credentials_lib/directus.py
RM Production/tools/lib/directus_admin_client.py-> Production/tools/credentials_lib/directus_admin_client.py
R  Production/tools/lib/ffmpeg_stitch.py        -> Production/tools/credentials_lib/ffmpeg_stitch.py
```

Bundle with Tier 1A. Same commit.

### Tier 1C: `weekly_preflight_audit.py` (17:28)

`diff -q` confirms Dropbox copy is byte-identical to tooling's uncommitted version. Contains the LD-576-amend-1 matcher-tightening logic (PR-merge auto-close regression fix).

**Path: tooling-first.** See §9 (Tier 7).

After tooling PR lands: commit Dropbox copy as separate `sync from tooling: weekly_preflight_audit.py LD-576-amend-1` commit OR include in Tier 1A bundle if you accept temporary divergence.

### Tier 1D: `V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md` (18:16)

Real session amendment. +156 / −82. Per the Kim-supplied prompt: "Phase A prereq #2 dropped per Kim 2026-05-07 sequencing".

Recommendation: **separate commit** on this branch:
```
docs(ld505): Phase A prereq #2 sequencing decision per Kim 2026-05-07
```

OR bundle with 1A — your call. Separate is cleaner for audit trail.

### Tier 1E: `STORYBOARD_V59_S5_5_G_SPEC_v1.md` (15:36)

Touched in same-second batch as Tier 1A. Likely a co-edit. Bundle with 1A.

---

## 4. Tier 2 detail — `.claude/skills/` (39 entries)

```
.claude/skills/MindfulNest_CRI_Parent_System_Business_Model_v1.md
.claude/skills/MindfulNest_Viral_Adoption_Strategy.md
.claude/skills/_backups_20260411/                            (skill snapshot from April)
.claude/skills/<37 skill subdirectories>/
.claude/skills/zero-error-qa/SKILL.md.backup_phase75_ds23_25_20260508T123109Z
.claude/skills/zero-error-qa/SKILL.md.pre_discipline_standards_1777931940
```

These are local Claude Code skill definitions. Two of them (`zero-error-qa` `.backup_*` files) are timestamped backups that should not be tracked.

**OPEN KIM DECISION (D-1):** Should `.claude/skills/` be tracked OR gitignored?
- **Track it** if these skills are version-controlled source-of-truth (Kim's custom skills authored over time, dated backups suggest yes).
- **Gitignore it** if these are runtime-loaded plugins managed by `setup-cowork` / Claude Code installer (the `_backups_*` and `.backup_phase75_*` files suggest the directory has runtime mutation, not pure source).

Recommendation: **GITIGNORE `.claude/skills/`** (matches the `.gitignore`'s defensive posture for runtime artifacts), then a future task creates a separate canonical skills repo (or syncs to tooling) if Kim wants version control. Status quo right now: untracked + uncommitted = effectively the same as gitignored.

If gitignored: also gitignore `.claude/session_scratchpad.json`, `.claude/scheduled_tasks.lock`, `.claude/LATEST_CHECKPOINT.json`, `.claude/session_checkpoints/`, `.claude/hooks/` (also untracked, runtime artifacts).

Keep `.claude/settings.json` and `.claude/settings.local.json` decision as-is (already in `.gitignore` typically; current state has the conflicted-copy variant which should be discarded).

---

## 5. Tier 3 detail — `Production/Event_1/` (327 entries) + `Event_2/` (5 entries)

Production output. Mix of:
- Generated stills + animations (`gemini_stills/`, `kling_clips/`, `composite/`, `animation_clips_final/`, `variants/`)
- TTS audio output dirs (`tts_emotional/`, `story_scene_tts/`, `story_scene_tts_v2/`)
- Storyboard HTML versions (storyboard_v27_*, storyboard_v43_*_backup.html — many timestamped backups)
- State JSON (production_state.*.json + multiple `.backup.*` variants)
- Scripts that produced the output (`shot6_pass1_generation.py`, etc.)
- Documentation generated alongside (LESSONS_LEARNED_*, HANDOFF_PROMPT_EVENT1_v1..v4.md)
- Binaries: `Claude.dmg` (definitely should never be in git)

### Recommendation: bulk `.gitignore`

Add to `.gitignore`:
```
# Production outputs (per LD-505 pre-Phase-A audit, 2026-05-10)
Production/Event_*/
!Production/Event_*/README.md
!Production/Event_*/state.json    # if a single canonical state file is desired
```

Verify: after gitignore commits, `git status --short` should drop ~327 + ~4 = 331 entries.

Whitelist exceptions are optional — only add if there's a specific file you want tracked. Default safe pattern: ignore everything under `Event_*/`.

### Event_2 specifics (5 entries):

```
Production/Event_2/README.md                                         (untracked — COMMIT if real)
Production/Event_2/_option_c_prototype/                              (subdirectory — GITIGNORE)
Production/Event_2/production_spend.json                             (state — GITIGNORE)
Production/Event_2/storyboard_v1_prod.html                           (output — GITIGNORE)
Production/Event_2/storyboard_v59_prod_PRECOPY_BACKUP_20260505_*.html (timestamped backup — DISCARD or GITIGNORE)
```

### Edge case: `Claude.dmg` at `Production/Event_1/Claude.dmg`

This is a **binary installer** (.dmg). It should never have been in the working tree. Recommendation: **DISCARD** (`rm`) — not just gitignore. This is the kind of artifact that bloats Dropbox sync without need.

---

## 6. Tier 4 detail — `Production/docs/` (99 untracked + 2 modified)

99 *.md/*.txt/*.json/*.jsonl files, mostly timestamped 20260508 (yesterday).

### Pattern groups identified

**6.1 Tech specs with multiple versions (DISCARD older, COMMIT latest):**
- `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1..v4.md` — v4 is canonical (it's the spec the just-committed payload validator implements). **Commit v4, discard v1-v3 OR move to `Production/docs/archive/`.**
- `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1..v3.md` — same pattern. Commit latest version, archive earlier.
- `DS_26_MECHANICAL_GATE_TECH_SPEC_v1..v3.md` — same.
- `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_*.md` (3 versions) — same.
- `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_*.md` (10 versions!) — same. Commit latest, archive rest. 10 versions of the same spec is a smell — surface to Kim for whether all 10 represent meaningful supersession or some are noise.

**6.2 Cursor-review handoff docs (COMMIT all):**
- `HANDOFF_CURSOR_REVIEW_*.md` (~10 files) — review handoffs are session artifacts; track them.

**6.3 Single-version reports + spec docs (COMMIT all):**
- `BACKUP_CHAIN_BLOCKERS_FIX_REPORT_20260508.md`
- `CALENDAR_DEP_TRIGGERS_WIRED_REPORT_20260508.md`
- `CLOUDSTORAGE_MOVE_REPORT_20260508.md`
- `CURSOR_AGENT_CLI_INTEGRATION_REF.md`
- `DIRECTUS_ADMIN_CLIENT_DEDUP_REPORT_20260508.md`
- `DIRECTUS_AGENT_CREDENTIAL_RELIABILITY_DIAGNOSIS_20260508.md`
- `DS23_24_25_V3_IMPL_HANDOFF_REPORT_20260508.md`
- `DS27_DUAL_PATH_REFACTOR_AND_SCHEMA_SPEC_V2_REPORT_20260508.md`
- `DS_23_24_25_V3_AMENDMENT_REPORT_20260508.md`
- `DS_28_DEPENDENCY_ORDER_RULE_REPORT_20260508.md`
- `G5_BACKUP_FDA_FIX_REPORT_20260508.md`
- `GOVERNANCE_DRIFT_CHECK_FIX_REPORT_20260508.md`
- `HANDOFF_AMENDMENTS_PROOF_REPORT_20260508.md`
- `WEEKLY_PREFLIGHT_AUDIT_MOVE_REPORT_20260508.md`
- `V2_HANDOFF_PATH_AUDIT_REPORT_20260508.md`
- `STOP_HOOK_CD_PREFIX_VARIANT_REPORT_20260508.md`
- `SESSION_HOUSEKEEPING_REPORT_20260508.md`
- `SUPABASE_PASSWORD_ROTATION_RUNBOOK_*.md`
- `Q1_PART2_*.md` (Conditional reviewer specs)
- `SCHEMA_VOCAB_MIGRATION_SNAPSHOT_20260509.md` (×2 — diff before commit)
- `PERIODIC_CLASS_TECH_SPEC_*.md` + `PATCH_FORWARD_PERIODIC_TECH_SPEC_*.md`
- `HANDOFF_TEMPLATE_*.md`

**6.4 The 2 modified files in `Production/docs/`:**
- `STORYBOARD_V59_S5_5_G_SPEC_v1.md` (Tier 1E — bundle with 1A)
- `V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md` (Tier 1D — separate commit)

**6.5 Loose entries:**
- `.cursor_review_block_authoring_workflow_v1.txt` — likely transient. Either commit or discard.
- A `.jsonl` and `.json` in this dir — sample before deciding.

**Recommended commit:**
```
docs: capture 2026-05-08 session artifacts (~85 files)

- Tech specs: payload validator v4, DS_23_24_25 v3, DS_26 v3, schema vocab migration latest
- Reports: backup chain, calendar deps, cloudstorage move, directus dedup, governance drift, etc.
- Cursor review handoffs: ~10 files
- Earlier tech-spec versions (v1-v3) moved to Production/docs/archive/
```

---

## 7. Tier 5 detail — `Production/tools/` (45 untracked)

### 7.1 Storyboard-v2 e2e tests (16 *.ts files) — duplicates of tooling

Verified all 16 exist at the same paths in tooling repo:
```
Production/tools/storyboard-v2/e2e/architectural_fix.spec.ts
Production/tools/storyboard-v2/e2e/beat_graft_red.spec.ts
Production/tools/storyboard-v2/e2e/global-setup.ts
Production/tools/storyboard-v2/e2e/global-teardown.ts
Production/tools/storyboard-v2/e2e/retroactive_s1_beat_lifecycle.spec.ts
Production/tools/storyboard-v2/e2e/retroactive_s2_pathapp_patch.spec.ts
Production/tools/storyboard-v2/e2e/retroactive_s3_storyboard_refresh.spec.ts
Production/tools/storyboard-v2/e2e/retroactive_s4_magic_compositor.spec.ts
Production/tools/storyboard-v2/e2e/retroactive_s5_library_rendering.spec.ts
Production/tools/storyboard-v2/e2e/retroactive_s6_scope_boundary.spec.ts
Production/tools/storyboard-v2/e2e/s5_5ce_proper_fix.spec.ts
Production/tools/storyboard-v2/e2e/s5_5f_smoke.spec.ts
Production/tools/storyboard-v2/e2e/s5_5g_smoke.spec.ts
Production/tools/storyboard-v2/e2e/scope_router_red.spec.ts
Production/tools/storyboard-v2/e2e/storyboard-v59-bg-scope-sync.spec.ts
Production/tools/storyboard-v2/e2e/storyboard-v59-display-order-empty.spec.ts
```

Disposition: **DISCARD** (tooling is canonical). OR if Kim wants to preserve a Dropbox copy: include in the Tier 1A `preserve` bundle.

### 7.2 Documentation (19 *.md files)

```
Production/tools/ANIMATION_REVIEW_FEATURES.md
Production/tools/ANIMATION_REVIEW_INDEX.md
Production/tools/ASSET_VALIDATION_INTEGRATION_GUIDE.md
Production/tools/BUILD_ANIMATION_REVIEW_GUIDE.md
Production/tools/FFMPEG_UTILS_INTEGRATION.md
Production/tools/FFMPEG_UTILS_MIGRATION.md
Production/tools/GPT_STILLS_TECH_SPEC_v1.md
Production/tools/MAGIC_PATH_PICKER_SKILL_SPEC_v1.md
Production/tools/MAGIC_PHASE2_SPEC_v1.md
Production/tools/PATCH_V43_SPEC.md
Production/tools/README_ANIMATION_REVIEW.md
Production/tools/README_STORYBOARD.md
Production/tools/VISIBLE_MAGIC_IMPLEMENTATION_HANDOFF_v1.md
Production/tools/VISIBLE_MAGIC_LESSONS_LEARNED_v1.md
Production/tools/VISIBLE_MAGIC_LESSONS_LEARNED_v2.md
Production/tools/VISIBLE_MAGIC_TECH_SPEC_v1.md
Production/tools/skeleton_to_beats_SKILL.md
```

Plus `requirements.txt`. Disposition: **COMMIT-DROPBOX-LOCAL**. These are tool-co-located documentation; legitimate to track.

### 7.3 State + lock files (4 entries) — GITIGNORE

```
Production/tools/magic_clip_registry.json     (registry state — GITIGNORE)
Production/tools/stitch_editor_state.json     (May 3 mtime — runtime state, GITIGNORE)
Production/tools/stitch_editor_state.lock    (Apr 26 mtime — process lock, GITIGNORE)
Production/tools/scene_registry.yaml          (review intent — could be source-of-truth, SURFACE TO KIM)
```

### 7.4 Templates + samples (3 entries)

```
Production/tools/sample_animation_manifest.json  (sample data — COMMIT)
Production/tools/sample_animation_review.html    (sample output — COMMIT or GITIGNORE)
Production/tools/stitch_editor.html              (real source — COMMIT)
Production/tools/stitch_editor_template.html     (real source — COMMIT)
```

---

## 8. Tier 6 detail — root-level untracked (~209 + 22 dirs)

### 8.1 Recent (May 2026) root-level *.md (~10) — COMMIT-DROPBOX-LOCAL

```
LESSONS_LEARNED_May02_2026_Storyboard_Wrap_Chain_Reckoning.md
LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md
LESSONS_LEARNED_May06_2026_v59_Features_Build_And_CICD_Discovery.md
LESSONS_LEARNED_May08_2026_v59_Storyboard_Foundation_Sprint.md
```

(Plus a few others if grep widens to all dates.)

Recommendation: **move to `Production/docs/` first** (cleaner repo root), then commit. Avoid leaving lessons-learned files at root level — that's part of why root has 209 stragglers.

### 8.2 Legacy April-2026 root-level files (~190) — ARCHIVE OR DISCARD

Patterns: `A1_*`, `ANIMATION_*`, `ARC_1_*`, `BLENDER_*`, `BROWSER_TEST_RESULTS_*`, `BUGFIX_*`, `CLAUDE_*` (some), `CRI_PACKAGING_*`, `CLAUDE_CODE_HANDOFF_*`, `DECISIONS_*`, `EXECUTION_PROOF_*`, `FOLLOWUP_*`, `FOLDER_REORG_*`, `GAMEPLAY_SCOPE_v1..v3.md`, `GOVERNANCE_BASELINE_*`, `HANDOFF_*` (~50 files), `HYBRID_LIPSYNC_*`, `INTERACTION_LESSONS_*`, `LESSONS_LEARNED_April*`, `LIPSYNC_*`, `LIP_SYNC_*`, `MINDFULNEST_*` (~10 files), `MORNING_REPORT_*`, `MVP_TIMELINE_*`, `MYRRHIN_TEACHER_*`, `NANO_BANANA_*`, `NORMALIZATION_*`, `NORMALIZE_*`, `OVERNIGHT_*`, `PARALLEL_STREAMS_*`, `PATH_A_*`, `PATH_B_*`, `PENDING_LORE_*`, `PER_BEAT_FADE_*`, `PHASE1_*`, `PHASE_A_*`, `PHASE_B_*`, `PIPELINE_*`, `PREVIEW_STITCHED_*`, `PRODUCTION_PLAN_*`, `QA_VALIDATION_*`, `README_BLENDER_*`, `REPAIR_PRISM_*`, `RESEARCH_CLAUDE_SCREENWRITING_*`, `SCOPE_REVERSAL_*`, `SCREENWRITING_*`, `SERVICES_LANDSCAPE_*`, `SESSION_*` (~10 files), `SHIP_READINESS_*`, `SIZE_BUDGET_AUDIT_*`, `STAGE3_*` (~8 files), `STALENESS_*`, `STILLGEN_*`, `STREAM_*`, `STYLE_TRANSFER_*`, `SUPABASE_OPERATIONS_*`, `TECH_*`, `TRACK_C_*`, `V1_SCOPE_*`, `VIDEO_*`, `VISUAL_*`, `WA_C16_*`, `WA_C3b_*`.

**OPEN KIM DECISION (D-2):** what to do with these ~190 legacy files at repo root?

Options:
- **(a) Move to `archive/legacy_2026Q2/` + COMMIT** — preserves history, cleans root
- **(b) DISCARD wholesale** — they're outdated handoffs from completed/abandoned sessions, may not be referenced anywhere
- **(c) GITIGNORE root-level *.md / *.html / *.txt patterns** — keeps them on disk but out of git

Recommend **(a)** — these files are linked from `prod_locked_decisions` rows + memory entries; preserving them in `archive/` retains those references.

### 8.3 Root-level untracked content directories (22 dirs) — GITIGNORE

```
Arc Skeletons/                                   — story content (Kim-authored)
App Design/                                      — design content
Business/                                        — business content
Canon/                                           — narrative canon
Clinical/                                        — clinical content
Cropper/                                         — tool/output dir
Marketing/                                       — marketing content
Module Demos/                                    — demo outputs
Old Versions/                                    — version backups
Parent Coach/                                    — content
Research/                                        — research content
Session Logs/                                    — log content
.deploy_backups/                                 — backup dir (HIDDEN)
archive/                                         — archive dir
content-lockfiles/                               — lockfiles
scripts/                                         — top-level scripts? (verify)
video_pipeline/                                  — pipeline workdir
Claude Code History backup 2026-04-15/           — timestamped backup
Claude ElevenLabs Phase B Module Sounds/         — audio assets
case-study-skill/                                — skill dir at root (orphan? See D-3)
email-nurture/                                   — skill dir at root (orphan)
website-copy-skill/                              — skill dir at root (orphan)
```

**OPEN KIM DECISION (D-3):** the 3 root-level `*-skill/` directories (`case-study-skill/`, `email-nurture/`, `website-copy-skill/`) have NO counterpart in `.claude/skills/`. Each contains a `references/` subdirectory. Is this an old skill-org pattern that's being migrated to `.claude/skills/`? Or are these reference-archive directories that should stay at root?

Recommend: GITIGNORE the 22 dirs en masse with patterns like:
```
# Top-level content / working / backup directories (per LD-505 audit)
/Arc Skeletons/
/App Design/
/Business/
/Canon/
/Clinical/
/Cropper/
/Marketing/
/Module Demos/
/Old Versions/
/Parent Coach/
/Research/
/Session Logs/
/.deploy_backups/
/archive/
/content-lockfiles/
/video_pipeline/
/Claude Code History backup 2026-04-15/
/Claude ElevenLabs Phase B Module Sounds/
/case-study-skill/
/email-nurture/
/website-copy-skill/
/scripts/                  # verify first — there's also a Production/scripts/
```

Use leading `/` so these are anchored to repo root only (pattern won't match `Production/Cropper/` if that exists elsewhere).

### 8.4 Loose state/temp/log/conflicted files at root (~9-12) — DISCARD + GITIGNORE patterns

```
.pending_directus_writes.resolved_20260419_c395dce5.jsonl   (already in .gitignore via *resolved_* — verify)
desktop (2).ini                                              (Windows OS metadata — DISCARD)
fal_lora_result.txt                                          (LoRA result — DISCARD or move)
feedback.json                                                (transient — DISCARD)
firebase-debug (Kimberly's conflicted copy 2026-04-18 1).log (DISCARD)
mindfulnest_full_schema.sql                                  (schema dump — likely DISCARD; canonical schema lives in Directus)
server_restart.log                                           (DISCARD + add *.log to .gitignore)
storyboard_sequence_2026-04-16.json                          (DISCARD or move to Production/Event_1/)
test_write.txt                                               ("test content" — clearly a transient test artifact, DISCARD)
ziR6fyTf/                                                    (looks like a random temp dir — investigate before discard, but probably DISCARD)
crop_manifest_M1_e1.json + crop_manifest_M1_e1 (1).json      (1 + 1 conflicted copy — keep one, discard conflict)
animation_selections.json + animation_selections (1).json    (same — conflict copy)
dashboard-ops-eval-viewer.html                               (eval viewer html — DISCARD or commit if real)
dashboard-ops.skill / dashboard-gate.skill / storyboard-producer.skill (.skill dir entries — orphan skill bundles, SURFACE TO KIM)
```

`.gitignore` patterns to add covering this category:
```
*conflicted copy*
*conflicted_copy*
*.log
*.tmp
desktop.ini
"desktop (*.ini"
.pending_directus_writes*    # already there
```

---

## 9. Tier 7 detail — tooling repo (2 entries)

### Files

```
~/Projects/mindfulnest-tooling on feature/codeql-cleanup-20260509:
 M Production/scripts/weekly_preflight_audit.py     (+194 / -34)
?? Production/tests/test_pr_merge_closure_matcher.py
```

### What this is

LD-576-amend-1 PR-merge auto-close matcher tightening. The test docstring states explicitly:
> Pins the LD-565 / PR-#8 false-close scenario from 2026-05-09 so the matcher cannot regress to scraping arbitrary UPPER_SNAKE tokens from decision_text.

### Recommendation

1. **Read both files end-to-end** (the modified weekly_preflight_audit.py + the new test file)
2. **Run the test:**
   ```bash
   cd ~/Projects/mindfulnest-tooling/Production
   PYTHONPATH=. python3 -m unittest tests.test_pr_merge_closure_matcher -v
   ```
3. **If green:**
   - The current branch `feature/codeql-cleanup-20260509` already has this work staged conceptually but needs renaming OR a separate branch. Suggest creating `feature/ld576-matcher-tightening-20260509`:
     ```bash
     git -C ~/Projects/mindfulnest-tooling checkout -b feature/ld576-matcher-tightening-20260509
     git -C ~/Projects/mindfulnest-tooling add Production/scripts/weekly_preflight_audit.py Production/tests/test_pr_merge_closure_matcher.py
     git -C ~/Projects/mindfulnest-tooling commit -m "fix(ld576-amend-1): tighten PR-merge closure matcher; add regression test"
     git -C ~/Projects/mindfulnest-tooling push -u origin feature/ld576-matcher-tightening-20260509
     gh pr create --repo <tooling-repo> ...
     ```
4. **If red:** WIP commit with `[WIP]` prefix, draft PR, flag in execution session's final report.

5. **After tooling PR merges:** sync the same file states back into Dropbox tree as Tier 1C commit.

### Note re: branch context

The current branch `feature/codeql-cleanup-20260509` may have an OPEN PR already from a prior session. Check `gh pr list --repo <tooling-repo>` first. If an open PR exists for the codeql cleanup, the LD-576 work might be intended to ride along — confirm with Kim before opening a separate PR.

---

## 10. Recommended execution sequence (for main session in `gallant-bouman-804b4f`)

Estimated 5 commits in Dropbox + 1 tooling PR + ~10 `.gitignore` additions. ~60-90 min if no surprises.

```
Step 0  : Confirm no other Claude session is mid-write in the 11 other worktrees.
          Take stash --include-untracked safety snapshot.
          Resolve D-1, D-2, D-3 with Kim if not pre-decided.

Step 1  : TOOLING — handle Tier 7
          1a. Read weekly_preflight_audit.py + test_pr_merge_closure_matcher.py
          1b. Run test (must pass)
          1c. Branch + commit + push + open PR in tooling
          1d. Wait for CI green
          1e. (Optional) merge if Kim authorizes

Step 2  : DROPBOX — Tier 1 bundle
          Commit message:
            preserve: lib→credentials_lib import-path sync (35 files)
              + Storyboard S5.5g spec touch + LD-505 spec amendment
          Includes: 35 modified .py files (Tier 1A) + 5 R/RM rename entries (1B)
                  + STORYBOARD_V59_S5_5_G_SPEC_v1.md (1E)
                  + V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md (1D, OR separate commit)

Step 3  : DROPBOX — Tier 1C sync (after tooling PR lands)
          One-line commit pulling in weekly_preflight_audit.py byte-identical to tooling.

Step 4  : DROPBOX — .gitignore additions (Tier 2 + 3 + 6C + state patterns)
          Single commit: chore(gitignore): add Event_*, .claude/skills/, root content dirs, runtime state patterns
          Verify: git status --short count drops to <50 after this commit.

Step 5  : DROPBOX — Tier 4 docs commit
          docs: capture 2026-05-08 session artifacts (~85 files)
          Includes the Tier 4 commit-list. Move v1-v3 superseded specs to Production/docs/archive/ in same commit.

Step 6  : DROPBOX — Tier 6A archive move
          chore: move ~190 legacy 2026-04 root-level docs to archive/legacy_2026Q2/
          Plus Tier 6B recent files moved to Production/docs/.

Step 7  : DROPBOX — Tier 6D loose-file cleanup
          chore: remove conflicted-copy + transient files at repo root
          Plus the audit doc itself (this file) gets committed.

Step 8  : Verify: git status --short count should be ≤5
          Document any remaining items as deferral list with explanation.

Step 9  : DIRECTUS — write activity log + update LD-505 with Phase A precondition status:
          POST prod_activity_log:
            action: 'pre-ld505-phase-a-triage-complete'
            details: { triage_audit_doc, commits_made, deferrals, ready_for_phase_a: bool }
          Per Rule 35: re-GET to confirm row landed.

Step 10 : Final summary message to Kim — triage report PR URL (tooling), commit list (Dropbox local),
          deferral items, ready-or-not status for LD-505 Phase A.
```

---

## 11. Open Kim decisions (block execution session)

| ID | Question | Why it matters | Recommended default if Kim silent |
|---|---|---|---|
| **D-1** | Should `.claude/skills/` be tracked or gitignored? | 39 entries either get committed or ignored; affects future skill version-control story | **GITIGNORE** (matches `.gitignore` defensive posture; runtime artifacts) |
| **D-2** | Disposition for ~190 legacy April-2026 root-level files | Either preserve (archive/) or discard | **MOVE-TO-`archive/legacy_2026Q2/`** (preserves references from LDs/memory) |
| **D-3** | Are root-level `case-study-skill/`, `email-nurture/`, `website-copy-skill/` orphans or canonical? | Affects whether to gitignore-discard or preserve | **GITIGNORE** (orphan; no `.claude/skills/` counterpart; safer) |
| **D-4** | For Tier 1 + Tier 1C: tooling-first PR sequencing OR temporary divergence | Affects whether weekly_preflight_audit.py commits in same Dropbox bundle as 1A or separately | **TOOLING-FIRST** (cleaner, no divergence) |
| **D-5** | OK to discard `Production/Event_1/Claude.dmg` outright? | Binary installer should never be in git or working tree | **DISCARD** |
| **D-6** | OK to discard the 16 storyboard-v2 e2e *.ts duplicates of tooling? | Tooling is canonical per LD-505 | **DISCARD** (faster path to clean tree; tooling has them) |
| **D-7** | Is `feature/codeql-cleanup-20260509` (tooling current branch) part of an open PR? | Affects whether LD-576 work piggybacks or gets its own branch | **Check `gh pr list` first; default to separate branch if no existing PR** |
| **D-8** | OK to gitignore 22 root-level content dirs? | Makes content invisible to git but they remain on disk for working access | **YES** (they shouldn't be in git; Dropbox filesystem is the source-of-truth, not the repo) |

---

## 12. Risk register for execution session

| Risk | Severity | Mitigation |
|---|---|---|
| Concurrent worktree writes during triage | HIGH | Pause other Claude sessions before Step 1; use stash safety snapshot |
| Discard of file that turns out to be needed | HIGH | Stash safety snapshot; default to `git rm --cached` (gitignore preserves on disk) over `rm` until confident |
| Tier 1A bundle commits something not actually in import-sync batch | MED | Per-file `git diff` audit before commit; not all 35 files are guaranteed mechanical 1-line changes (registered_write.py is, others may differ) — sample 5 random files first |
| Tier 6A archive move creates broken refs in committed LDs/memory | MED | Search for path references in `prod_locked_decisions` + memory before moving; update where found |
| `.gitignore` pattern over-matches (e.g. `Production/Event_*/` accidentally hides intentional Event_1/state.json) | LOW | Whitelist with `!` syntax; verify with `git check-ignore` after commit |
| Tooling PR Step 1 conflicts with existing open PR on `feature/codeql-cleanup-20260509` | MED | D-7 above — check first |
| LD-505 spec edit (Tier 1D) conflicts with main branch when merged | LOW | Local-only commit on feature branch; no merge attempt yet |

---

## 13. State capture for audit reproducibility

- Branch: `feature/payload-validator-v4-impl-20260509`
- HEAD: `0bb4242 Payload Validator v4-D implementation per spec`
- Commits ahead of `main`: 38
- Working tree: 868 entries (38 M + 825 ?? + 1 R + 4 RM)
- Tooling repo branch: `feature/codeql-cleanup-20260509`
- Tooling working tree: 2 entries (1 M + 1 ??)
- Audit raw inventory: `/tmp/triage_inventory_20260510.tsv` (TSV: `<status>\t<top-dir>\t<orig>\t<path>`, null-delim parsed)

## 14. Files this audit explicitly does NOT touch

Per Option A constraints:
- No commits performed in either repo
- No `.gitignore` writes
- No `git stash`, `git rm`, `git clean`, `rm`, `mv` operations
- No Directus writes (the prompt called for `prod_activity_log` rows; that's the execution session's job, not audit's)
- This audit doc itself is the ONLY new file created (1 added entry to Dropbox `??` count)

---

**End of audit. Execution session: read this top-to-bottom, resolve D-1..D-8 with Kim, then proceed through §10 step sequence.**
