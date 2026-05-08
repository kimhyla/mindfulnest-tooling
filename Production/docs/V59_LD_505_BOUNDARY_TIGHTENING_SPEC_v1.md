# V59 LD-505 Boundary Tightening Migration Spec — v1

**Date:** 2026-05-08
**Produced by:** tech-spec skill (two-Opus-agent debate + synthesis)
**Status:** SPEC DRAFT — awaiting Cursor cross-review before lock
**Supersedes:** LD-264 `PRODUCTION_TOOLS_STAYS_IN_DROPBOX` (active soft, 2026-04-18) — this spec proposes new LD `LD_505_BOUNDARY_TIGHTENING_V1` to override

---

## §0 — Mandatory Operating Mode (per tech-spec skill update 2026-05-06)

The session executing this spec MUST:

### §0.1 Phase 0 classification (Tier A/B/C)

This task is **Tier C** (architectural, governed-file scope, multi-system). Spawn 4+4 advocate+counter-agents per Rule 19 / `execute` skill. Write `prod_preflight_reviews` row before Phase 1.

### §0.2 Six-Layer Verification Contract (DS-13)

For every spec deliverable:
1. UI exists (handoff readable, scripts present, files in expected paths)
2. UI→backend wiring (server can be invoked from new tooling clone path)
3. Backend processing (server starts, opens state files, serves on port 5111)
4. State propagation (Directus rows updated, file_path migration completes)
5. UI re-render (browser smoke against http://localhost:5111/ shows storyboard)
6. Intent→outcome smoke (Kim's actual workflow runs end-to-end on the new layout)

### §0.3 Eight Risk Classes for Silent Failure (DS-14)

Watch list for this migration:
- AI-driven: none in scope
- Multi-stage pipelines: production_server.py runtime path resolution
- Async: Directus batch PATCH (35 rows) with read-back-after-write per Rule 35
- Drag-drop: storyboard SPA continues to function (verify via browser smoke)
- Side-effect captures: cron / launchd installations may need re-registration
- Cost displays: N/A
- Conditional rendering: scope_event_id behavior continues to work
- State persistence: `.mn-context/`, memory dir, production_state.json all migrate cleanly

### §0.4 Authoring Discipline (DS-15) — 12 rules

Apply throughout execution; relevant subset for this migration:
- No assumed paths — verify every path before referencing
- No assumed file existence — `test -f` before reading
- No assumed branch state — `git branch --show-current` before committing
- No silent-failure-class commands — Rule 35 read-back on every Directus write
- No memory-only references — every claim must be [CONFIRMED]/[INFERRED]/[GUESSED]
- No half-merged state — branches are either fully resolved or explicitly archived

### §0.5 Don't Rely on Memory or Guess (DS-16, Kim 2026-05-06 directive)

Every assumption gets a verification command. If the verification command can't be written, the assumption itself is suspect.

### §0.6 Tail-End Independent Verifier Subagent (DS-17)

After Phase G (final verification), spawn a fresh agent to independently verify:
- Tooling repo on GitHub has expected structure
- Dropbox-resident `.git/` is truly removed
- Production server runs from tooling clone successfully
- All 35 Directus prod_assets rows have project-relative paths
- Memory dir symlink is intact and resolving

### §0.7 Standing Rules Reference

CLAUDE.md Rules: 5 (Dropbox-synced workflow), 15 (reference docs sync), 18 (LD auto-registration), 19 (no shortcuts), 20 (decision capture), 24 (confidence annotation), 27 (delete obsolete workarounds), 29 (server staleness), 31 (Directus before disk), 32 (absolute localhost URLs), 33 (verify server+file before "try it now"), 34 (asset findability), 35 (Directus schema verification)

### §0.8 Standing Escape Hatches (DS-19) — 10 STOP conditions

1. Cannot resolve Directus 403/404 on prod_assets PATCH after retry → STOP
2. Tooling repo push fails on GitHub → STOP (auth issue, not migration issue)
3. Memory dir symlink test fails (Claude Code can't load memory from new path) → STOP
4. Production server fails to start from tooling clone → STOP
5. Browser smoke fails post-migration (storyboard 404 or 500) → STOP
6. Dropbox sync conflicts mid-execution → STOP, wait for sync to settle
7. Git operation hangs > 5 min → STOP, investigate (don't kill arbitrarily)
8. Required env var (MINDFULNEST_ROOT, MN_DROPBOX_ROOT) not set on PC → STOP
9. LD-264 supersede write returns silent_write_failure after 2 retries → STOP
10. Tail-end verifier reports any [GUESSED] tag in critical-path claims → STOP, re-verify

### §0.9 Deviation Logging Pattern (DS-18)

When a deviation from this spec is necessary mid-execution: log inline as `## DEVIATION: <name>` block in the morning report, with: a1) what was deviated from, a2) what was actually done, b) why the deviation was necessary. Honest documentation > silent compliance.

### §0.10 Browser Smoke Discipline

Final verification MUST include actual browser hard-reload (Cmd+Shift+R) of http://localhost:5111/ from a fresh browser tab + click-through of Beat Generator drag-drop + Storyboard tab + at least one other tab. If overnight session with no human eyes: programmatic curl substitute, flagged in morning report.

---

## §1 — Task

Tighten the LD-505 canonical-code boundary by **eliminating the Dropbox-resident `.git/` directory** at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.git`. After this migration, `~/Projects/mindfulnest-tooling` is the **sole git tree** for MindfulNest production code. Dropbox-mounted paths continue to hold:
- `Production/Event_*/` media (audio, video, images, masters)
- `Canon/` narrative `.docx` files
- Runtime state files (production_state.json, beat_generator_state.json, sidecars)
- Secrets (`Production/API_KEYS_MASTER.md`)

Production server (`production_server.py`) runs from tooling clone with `--event-dir` pointing into the Dropbox-mounted tree.

Cross-machine model:
- Code: `git push/pull` between Mac (`~/Projects/mindfulnest-tooling`) and PC (equivalent path) via GitHub.
- Content: continues via Dropbox auto-sync.

This eliminates the divergence-vector that produced the 29-file uncommitted-divergence problem (commit 95e4462 on Dropbox-resident `claude/preserve-uncommitted-divergence-20260507`) without violating LD-283 size budgets, LD-505 media-not-in-git boundary, or Rule 3 .docx workflow.

---

## §2 — Governing Decisions

This spec is built on top of and explicitly compatible with:

| Decision | Status | How this spec respects it |
|---|---|---|
| **LD-264 PRODUCTION_TOOLS_STAYS_IN_DROPBOX** | active soft, 2026-04-18 | **SUPERSEDED** by new LD_505_BOUNDARY_TIGHTENING_V1 — see §3 for reasoning the 2026-04-18 debate didn't have access to |
| **LD-505 TOOLING_REPO_CREATED_V1** | active HARD, 2026-05-04 | Honored — tooling repo continues as canonical CODE; this spec tightens the boundary, doesn't redraw it |
| **LD-541 STORYBOARD_DEPLOY_PROCESS_V1** | active SOFT, 2026-05-04 | Honored — deploy_storyboard_v59.sh continues to be the only allowed deploy bridge; rsync semantics simplify post-migration since tooling is sole source |
| **LD-283 SIZE_BUDGET_PER_MODULE_V1** | active HIGH | Honored — media stays in Dropbox, never in git or git-LFS, no per-module ceiling violations |
| **LD-280 RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1** | active HIGH | Honored — atomic MP4 production pipeline runs unchanged from tooling clone with Dropbox-mounted event-dir |
| **LD-421/422 ASSET_FINDABILITY_OVERHAUL_V1/_BUILD_V1** | active HIGH | Honored — registered_write.py + find_asset.py continue to work; 35 prod_assets.file_path rows batch-PATCHed to project-relative |
| **LD-368 WINDOWS_DROPBOX_ATOMIC_RENAME_RETRY_V1** | active MEDIUM | Honored — Windows PC continues to need this for tools writing to Dropbox-mounted paths (server state writes) |
| **LD-367 DIRECTUS_ADMIN_CLIENT_CROSS_PLATFORM_PATH_V1** | active MEDIUM | Honored — _candidate_keys_paths() already handles cross-platform; no change needed |
| **LD-327 APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1** | active HIGH | Honored — credential resolution from `Production/API_KEYS_MASTER.md` (Dropbox-mounted) continues; env override available |
| **LD-185 DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA** | active HIGH | Honored — multi-repo precedent respected |
| **LD-121 MINDFULNEST_GIT_REPO** | active CRITICAL | Honored — `mindfulnest-ios` stays in its own repo |
| **LD-544 MAIN_APP_CICD_GREENFIELD_DESIGN_V1** | active HARD | Honored — main RN app CI/CD stays separate from tooling repo CI/CD; this migration is tooling-only |
| **LD-545 SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1** | active HARD, 2026-05-07 | Honored — closes when gap-fix lands; migration runs after gap-fix |
| **LD-437 CLAUDE_MD_SPLIT_20260427** | active HIGH | Honored — both CLAUDE.md and CLAUDE_NARRATIVE_REFERENCE.md remain at project root (which now means tooling repo's relative-to-cwd resolver, since cwd will be tooling) |
| **LD-124 PREFLIGHT_PROTOCOL_STEP_0** | active CRITICAL | Honored — Phase 0 cron `weekly_preflight_audit.py` updated to read from new tooling-clone path |
| **CLAUDE.md Rule 3** | unchanged | Honored — .docx workflow continues with Dropbox version history fallback |
| **CLAUDE.md Rule 5** | unchanged | Honored — Dropbox-synced workflow continues for content; "Resource deadlock avoided" UX remains for cloud-only content files |

---

## §3 — Approach

### Why supersede LD-264

The 2026-04-18 debate that produced LD-264 concluded "marginal benefit, ~4 hours" for migrating Production/tools/ out of Dropbox. That conclusion was correct given what the debate had access to at that time. New information not available 2026-04-18:

1. **The 29-file divergence (commit 95e4462, 2026-05-07)** is a structural symptom of having two `.git/` trees — a class of problem the 2026-04-18 debate did not anticipate. The "marginal benefit" framing assumed the cost was static; in fact, the cost compounds as drift accumulates.

2. **LD-505 (2026-05-04) created a tooling repo specifically to enable v59 e2e CI** — a context the 2026-04-18 debate did not have. The migration from there is no longer "move to git for marginal benefit"; it's "complete the migration that LD-505 already started, eliminating the parallel `.git/` that re-created the original problem."

3. **The gap-fix Phase G pre-commit hook (V59_CICD_GAP_FIX_SPEC_v1.md)** is structurally incompatible with two parallel `.git/` trees — it can only enforce in one. This migration is required for gap-fix to deliver on its mechanical guarantee.

The new LD `LD_505_BOUNDARY_TIGHTENING_V1` documents these reasons and explicitly supersedes LD-264 with `superseded_by_id` linkage.

### Architectural model after migration

```
~/Projects/mindfulnest-tooling/         ← SOLE git tree, GitHub remote
├── Production/
│   ├── tools/                           ← all .py code, including production_server.py
│   ├── lib/                             ← Directus client, paths, etc.
│   ├── scripts/                         ← deploy, audit, backup scripts
│   ├── docs/                            ← all .md specs and handoffs
│   ├── governance/                      ← skill governance files
│   └── tests/                           ← test code
├── .claude/skills/                      ← project-level skills (was in Dropbox tree)
├── CLAUDE.md
└── CLAUDE_NARRATIVE_REFERENCE.md

/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/
├── Production/
│   ├── Event_1/                         ← media + state (NOT in git, never has been per LD-505 .gitignore)
│   ├── Event_2/
│   ├── Character_Assets/masters/        ← FLUX-generated masters
│   └── API_KEYS_MASTER.md               ← secrets (NOT in git per LD-327)
├── Canon/                               ← Kim's .docx narrative source
├── Arc Skeletons/                       ← .md and .docx skeleton authoring
└── (NO .git/ directory — eliminated)

~/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/
                                          ← OLD memory hash directory
~/.claude/projects/<NEW HASH>/memory      ← symlinked back to old hash directory
                                          ← preserves memory across cwd change
```

Production server invocation post-migration:
```bash
cd ~/Projects/mindfulnest-tooling
python3 Production/tools/production_server.py \
  --event-dir "$DROPBOX_ROOT/Production/Event_1" \
  --storyboard storyboard_v59_prod.html \
  --event-id Event_1
```

Where `$DROPBOX_ROOT="/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"` is exported in shell rc.

### Cross-machine workflow post-migration

**Mac (home):**
- Code: `~/Projects/mindfulnest-tooling/` — `git pull` to sync from GitHub
- Content: Dropbox-mounted as before

**PC (work):**
- Code: `C:\Users\<user>\Projects\mindfulnest-tooling\` — `git pull` to sync from GitHub
- Content: Dropbox-mounted as before
- Windows-specific: `Production/lib/atomic_json_write.py` retry helper (LD-368) continues to apply to state writes
- Bootstrap: `Production/scripts/setup_bypass_permissions.py` (per memory `project_windows_bypass_pending.md`)

---

## §4 — Implementation Steps

Phased execution. Each phase ends with verification before next phase begins.

### Phase A — Pre-flight + Preservation (~30 min)

1. Verify all dependent prerequisites are complete:
   - V59 CI/CD gap-fix has merged to main (per timing decision)
   - 22-file divergence reconciliation has merged to main
   - Working trees in BOTH `.git/` directories are clean (no uncommitted)
   - `lsof -ti:5111` returns the storyboard server PID (not yet killed)
2. Snapshot the Dropbox-resident `.git/` BEFORE any destructive operation:
   ```bash
   cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
   tar czf "$HOME/dropbox_git_snapshot_$(date -u +%Y%m%d_%H%M%S).tar.gz" .git/
   ```
3. Push all named branches from Dropbox-resident `.git/` to tooling repo as preservation refs:
   ```bash
   cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
   for BRANCH in $(git branch | grep -v '^\*' | sed 's/^  //'); do
     git push origin "${BRANCH}:archive/dropbox-resident/${BRANCH}"
   done
   git push origin "claude/preserve-uncommitted-divergence-20260507:archive/dropbox-resident/preserve-uncommitted-divergence-20260507"
   ```
   This preserves all 9+ Dropbox-resident branches as `archive/dropbox-resident/*` namespace in tooling repo.
4. Verify push succeeded:
   ```bash
   cd ~/Projects/mindfulnest-tooling
   git fetch origin
   git branch -r | grep "archive/dropbox-resident"
   ```
5. Register `prod_activity_log` row:
   - action: `migration_phase_a_preflight_complete`
   - details: list of preserved branches, snapshot tar.gz path

### Phase B — LD Supersede + Pre-Migration Directus Updates (~45 min)

1. Register `LD_505_BOUNDARY_TIGHTENING_V1` LD per Rule 18:
   ```python
   from Production.lib.directus import try_post_or_queue
   result = try_post_or_queue('prod_locked_decisions', {
       'decision_key': 'LD_505_BOUNDARY_TIGHTENING_V1',
       'decision_name': 'Eliminate Dropbox-resident .git/; tooling repo as sole code tree',
       'severity': 'HARD',
       'scope_domain': 'production',
       'task_category': 'tech_stack',
       'enforcement_type': 'code_invariant',
       'status': 'active',
       'date_locked': '<execution date>',
       'source_document': 'Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md',
       'decision_text': '<full text from §3 reasoning>',
       'notes': 'Supersedes LD-264 (active soft, 2026-04-18). New context not available 2026-04-18: 29-file divergence problem class, LD-505 tooling repo creation, gap-fix Phase G pre-commit hook structural requirement. See spec §3.'
   })
   ```
2. PATCH LD-264 to `superseded_by_id` = LD_505_BOUNDARY_TIGHTENING_V1's id, status = 'superseded':
   ```python
   from Production.lib.directus_admin_client import DirectusAdminClient
   c = DirectusAdminClient()
   ld_264 = c.get_items('prod_locked_decisions', filters={'decision_key': {'_eq': 'PRODUCTION_TOOLS_STAYS_IN_DROPBOX'}}, fields=['id'])
   c.patch_item('prod_locked_decisions', ld_264[0]['id'], {
       'superseded_by_id': new_ld_id,
       'status': 'superseded',
       'date_superseded': '<execution date>'
   })
   ```
3. Read-back-after-write verify both writes per Rule 35.
4. Batch PATCH 35 `prod_assets.file_path` rows from Dropbox-absolute to project-relative:
   ```python
   c = DirectusAdminClient()
   DROPBOX_PREFIX = '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/'
   absolute_assets = c.get_items('prod_assets', filters={'file_path': {'_starts_with': DROPBOX_PREFIX}}, fields=['id', 'file_path'])
   for asset in absolute_assets:
       new_path = asset['file_path'].replace(DROPBOX_PREFIX, '')
       c.patch_item('prod_assets', asset['id'], {'file_path': new_path})
       # read-back-after-write per Rule 35
       verify = c.get_items('prod_assets', filters={'id': {'_eq': asset['id']}}, fields=['file_path'])
       assert verify[0]['file_path'] == new_path
   ```
5. Verify post-PATCH count of Dropbox-absolute rows = 0.
6. Register `prod_activity_log` row:
   - action: `migration_phase_b_directus_updates_complete`
   - details: ld_count_registered=1, ld_count_superseded=1, prod_assets_patched=35

### Phase C — Path Sweep in Tooling Repo (~2-3 hrs)

1. Identify all hardcoded Dropbox paths in tooling repo:
   ```bash
   cd ~/Projects/mindfulnest-tooling
   grep -rln "Library/CloudStorage/Dropbox" --include="*.py" --include="*.sh" --include="*.ts" --include="*.tsx" --include="*.json" > /tmp/dropbox_path_files.txt
   wc -l /tmp/dropbox_path_files.txt
   ```
2. Categorize hits:
   - Comments / docs: leave as-is, will be obvious historical references
   - Default fallback values: replace with `os.environ.get('MN_DROPBOX_ROOT', '<existing default>')` pattern
   - Actual hardcoded references: replace with env var resolution
3. Update `Production/lib/paths.py` to centralize cross-platform resolution:
   - Read `MN_DROPBOX_ROOT` env var (fall back to platform-specific defaults if unset)
   - Read `MN_TOOLING_ROOT` env var (defaults to `Path(__file__).parent.parent.parent` resolved to tooling clone root)
   - All scripts that need Dropbox content paths import from `paths.py` rather than hardcoding
4. Update `Production/scripts/deploy_storyboard_v59.sh` (already env-overridable per LD-541):
   - Already supports `MN_TOOLING_ROOT` and `MN_DROPBOX_ROOT` — verify no other hardcoded paths
5. Update `Production/scripts/_weekly_snapshot_wrapper.sh` and `Production/scripts/install_backup_crons.sh` to read env vars instead of hardcoded paths.
6. Update `.claude/skills/execute/SKILL.md` (4 hardcoded path references) — replace with env var or relative-to-cwd patterns.
7. Compile + test:
   - `python3 -m py_compile Production/tools/production_server.py`
   - `python3 -m py_compile Production/lib/paths.py`
   - `python3 -c "from Production.lib.paths import DROPBOX_ROOT, TOOLING_ROOT; print(DROPBOX_ROOT, TOOLING_ROOT)"`
8. Commit on tooling repo: `git commit -m "phase-c: path sweep — replace hardcoded Dropbox paths with env-var resolution"`
9. Push to GitHub.

### Phase D — Memory Directory Symlink (~10 min)

1. Determine new project hash (after migration, cwd will be tooling repo, so hash will change):
   ```bash
   # Claude Code derives hash from cwd; the new hash directory will be:
   # ~/.claude/projects/-Users-kimberlysmith-Projects-mindfulnest-tooling
   # OLD hash directory:
   OLD_HASH_DIR="$HOME/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files"
   NEW_HASH_DIR="$HOME/.claude/projects/-Users-kimberlysmith-Projects-mindfulnest-tooling"
   ```
2. Create symlink for memory subdirectory specifically (not the entire hash dir, to avoid Claude Code's other artifacts colliding):
   ```bash
   mkdir -p "$NEW_HASH_DIR"
   ln -s "$OLD_HASH_DIR/memory" "$NEW_HASH_DIR/memory"
   ```
3. Verify Claude Code reads memory from new hash dir:
   - Open a fresh Claude session in `~/Projects/mindfulnest-tooling`
   - Type a query that should hit MEMORY.md (e.g., "what did we do in the side-fix session")
   - Confirm memory loads correctly
4. If symlink doesn't work (Claude Code may resolve paths differently), fall back to copy:
   ```bash
   cp -R "$OLD_HASH_DIR/memory/" "$NEW_HASH_DIR/memory/"
   ```
   With caveat: now there are two copies; future writes only land in one. Document this as a known limitation.

### Phase E — Eliminate Dropbox-Resident .git/ (~15 min)

1. Final pre-deletion verification:
   - All branches preserved in tooling repo `archive/dropbox-resident/*` namespace (per Phase A step 3)
   - `git status` in Dropbox tree shows clean OR all uncommitted intentionally accepted as lost
   - Snapshot tar.gz from Phase A step 2 is intact at `$HOME/dropbox_git_snapshot_*.tar.gz`
2. Remove `.git/` directory:
   ```bash
   cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
   rm -rf .git
   ```
3. Verify removal:
   ```bash
   test ! -d "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.git" && echo "REMOVED" || echo "STILL PRESENT"
   ```
4. Update Dropbox tree's `.gitignore` (if present at root) to add a comment:
   ```
   # Dropbox tree is no longer a git working tree.
   # All version control happens in ~/Projects/mindfulnest-tooling.
   # See LD_505_BOUNDARY_TIGHTENING_V1.
   ```
   (Don't delete `.gitignore` itself — it's referenced by tools that may still consult it for patterns; leaving it as documentation is harmless.)
5. Register `prod_activity_log` row:
   - action: `migration_phase_e_dropbox_git_eliminated`
   - details: snapshot path, branch preservation count, deletion confirmed timestamp

### Phase F — Production Server Restart from Tooling Clone (~20 min)

1. Stop the existing production server (running from Dropbox tree pre-migration):
   ```bash
   PID=$(lsof -ti:5111)
   kill $PID
   sleep 2
   lsof -ti:5111 || echo "PORT FREE"
   ```
2. Start production server from tooling clone with Dropbox-anchored event-dir:
   ```bash
   export MN_DROPBOX_ROOT="/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
   cd ~/Projects/mindfulnest-tooling
   python3 Production/tools/production_server.py \
     --event-dir "$MN_DROPBOX_ROOT/Production/Event_1" \
     --storyboard storyboard_v59_prod.html \
     --event-id Event_1 \
     > /tmp/storyboard_server.log 2>&1 &
   ```
3. Verify server is alive:
   ```bash
   sleep 3
   lsof -ti:5111  # should return new PID
   curl -s http://localhost:5111/ | head -10  # should serve storyboard SPA
   ```
4. Browser smoke (per §0.10):
   - Open browser to http://localhost:5111/, hard-reload
   - Click Beat Generator tab, drag library image to BG ref → toast fires (Bug 1 fix still works)
   - Click Storyboard tab → loads beat list
   - Click at least one other tab to verify general health
5. Update server-restart cron / launchd if any (currently the server is started manually; no cron).
6. Register `prod_activity_log` row:
   - action: `migration_phase_f_server_restarted_from_tooling_clone`
   - details: new PID, lstart, browser smoke result

### Phase G — Final Verification + Tail-End Verifier (~30 min)

1. Run independent tail-end verifier subagent (per §0.6):
   - Confirm tooling repo on GitHub has all expected branches including `archive/dropbox-resident/*`
   - Confirm Dropbox-resident `.git/` is truly removed
   - Confirm production server runs from tooling clone successfully
   - Confirm all 35 Directus prod_assets rows have project-relative paths (re-query)
   - Confirm memory dir symlink resolves correctly
   - Confirm CLAUDE.md and CLAUDE_NARRATIVE_REFERENCE.md are accessible from tooling clone path
2. Update reference docs registry per Rule 15:
   - PATCH `prod_reference_docs` rows whose `file_path` points to a path that's now relative-to-tooling vs relative-to-Dropbox if needed (sample 20 rows; spot-check)
3. Update memory file index `MEMORY.md` to add a session entry:
   - `[Session <YYYY-MM-DD HH:MM>](session_<TS>.md) — LD-505 boundary tightening migration complete`
4. Write migration completion morning report to:
   - `Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_MORNING_REPORT_<TS>.md`
5. Register final `prod_activity_log` row:
   - action: `migration_complete`
   - details: all phases A-G timestamps, any deviations, final verification results

---

## §5 — Files Created / Modified

### Created
- `Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md` (this file)
- `Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_MORNING_REPORT_<TS>.md` (Phase G output)
- `~/dropbox_git_snapshot_<TS>.tar.gz` (Phase A snapshot)
- `~/.claude/projects/-Users-kimberlysmith-Projects-mindfulnest-tooling/memory/` (symlinked to old hash dir)

### Modified (in tooling repo)
- `Production/lib/paths.py` — centralized env-var path resolution
- `Production/scripts/_weekly_snapshot_wrapper.sh` — env var resolution
- `Production/scripts/install_backup_crons.sh` — env var resolution
- `Production/scripts/deploy_storyboard_v59.sh` — verify env-var-only (already partially done)
- `.claude/skills/execute/SKILL.md` — replace 4 hardcoded path references
- Any other files surfaced by Phase C step 1 grep
- `.gitignore` (tooling) — verify continues to exclude `Production/Event_*/` etc.

### Removed
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.git/` — entire directory
- (None other — content side preserved entirely)

---

## §6 — Directus Writes Required

| Collection | Operation | Count | Purpose |
|---|---|---|---|
| `prod_locked_decisions` | INSERT | 1 | Register `LD_505_BOUNDARY_TIGHTENING_V1` |
| `prod_locked_decisions` | PATCH | 1 | Mark LD-264 as superseded |
| `prod_assets` | PATCH | 35 | Convert Dropbox-absolute file_path to project-relative |
| `prod_reference_docs` | PATCH | up to 96 (likely much fewer) | Spot-check + update any rows with absolute Dropbox paths (currently 0 verified by Agent A; safety check) |
| `prod_activity_log` | INSERT | 7 | One per phase (A-G) milestone |

All writes via `try_post_or_queue` from `Production/lib/directus.py` with read-back-after-write per Rule 35.

Schema gotchas to honor:
- `prod_locked_decisions` does NOT have `closure_date` field — use `notes` field
- `prod_locked_decisions` REQUIRES `source_document` field
- `prod_locked_decisions.severity` is uppercase (HARD/SOFT post-2026-05-04 migration)
- `prod_assets` does NOT have `role` field
- `prod_blockers.severity` is lowercase

---

## §7 — Error Cases and Handling

Per Rule 19 (no error paths left open):

| Failure mode | Handling |
|---|---|
| GitHub push fails (auth, rate limit, network) | Halt, surface specific error. Do NOT proceed to Phase E (would lose preservation refs). |
| Dropbox-resident branch listing returns empty | Investigate before push — could indicate corrupted .git/. Halt. |
| `try_post_or_queue` returns silent_write_failure on LD register | Retry once, then halt and surface. Do NOT proceed without LD registered. |
| `prod_assets` PATCH fails on any of 35 rows | Halt at first failure. Investigate. Do NOT proceed (split-state). |
| `rm -rf .git/` returns permission error | Halt. Investigate (Dropbox lock, sync conflict). Restart Dropbox if needed. |
| Production server fails to start from tooling clone | Halt. Diagnose path resolution. Restore previous server if needed: `cd "$DROPBOX_ROOT" && python3 Production/tools/production_server.py ...`. Investigate root cause before re-attempting. |
| Browser smoke fails post-restart (404 or 500) | Halt. Check server logs. Likely hardcoded path missed in Phase C sweep. |
| Memory symlink doesn't resolve | Fall back to copy (with documented limitation). Continue. |
| Tail-end verifier reports any [GUESSED] tag | Halt, re-verify the specific claim. Do NOT close migration as complete. |

---

## §8 — Verification

Phase G verifier checks (independent agent, per §0.6):

1. **Tooling repo GitHub state:**
   ```bash
   cd ~/Projects/mindfulnest-tooling
   git fetch origin
   git branch -r | grep -c "archive/dropbox-resident/" >= 9  # 9+ preserved branches
   git remote -v  # confirms GitHub remote present
   ```
2. **Dropbox `.git/` removal:**
   ```bash
   test ! -d "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.git"
   ```
3. **Production server health:**
   ```bash
   PID=$(lsof -ti:5111)
   ps -o lstart= -p $PID  # server start time
   ps -o command= -p $PID | grep "mindfulnest-tooling"  # confirms running from tooling clone
   curl -sf http://localhost:5111/ > /dev/null  # SPA serves
   ```
4. **Directus state:**
   - LD `LD_505_BOUNDARY_TIGHTENING_V1` exists, status=active
   - LD `PRODUCTION_TOOLS_STAYS_IN_DROPBOX` exists, status=superseded, superseded_by_id correct
   - `prod_assets` rows with file_path starting with `/Users/kimberlysmith` count = 0
5. **Memory dir resolution:**
   - Open fresh Claude Code session in `~/Projects/mindfulnest-tooling`
   - Confirm MEMORY.md auto-loads (recent session digests visible)
6. **Cross-platform readiness (Mac side only initially; PC verification deferred to bootstrap session):**
   - `python3 Production/tools/production_server.py --help` runs cleanly
   - `python3 -c "from Production.lib.paths import DROPBOX_ROOT, TOOLING_ROOT"` runs cleanly
7. **Reference doc consistency:**
   - `Production/tools/sync_reference_docs.py` (Rule 15) reports 0 drift OR documented expected drift

---

## §9 — Rollback

If migration fails mid-execution:

### Pre-Phase E (before .git/ removal)
- All operations are additive or recoverable. Roll back by reverting commits in tooling repo + restoring Directus rows from backup.
- Specific:
  - Phase B Directus changes: PATCH LD `LD_505_BOUNDARY_TIGHTENING_V1` to status=`failed_rollback`; PATCH LD-264 to status=`active`, superseded_by_id=null. Rebuild prod_assets.file_path back to Dropbox-absolute.
  - Phase C path sweep: `git revert <commit>` in tooling repo.

### Post-Phase E (after .git/ removal)
- Restore from snapshot:
  ```bash
  cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
  tar xzf "$HOME/dropbox_git_snapshot_<TS>.tar.gz"
  ls -la .git/  # verify restored
  ```
- This restores the Dropbox-resident `.git/` to pre-migration state. All branches and history preserved.

### Catastrophic (snapshot also lost)
- Tooling repo on GitHub has all preserved branches as `archive/dropbox-resident/*`. Re-clone tooling repo to a fresh directory; cherry-pick or rebase any work needed.
- Dropbox version history retains content files for 30 days minimum (Rule 5).

Rollback time: 5-10 min for pre-Phase E; 15-30 min for post-Phase E snapshot restore.

---

## §10 — Out of Scope (V1)

This spec explicitly does NOT include:

1. **Migration of `MindfulNest/` (the React Native shipping app)** — stays in `mindfulnest-ios` repo per LD-121 + LD-544.
2. **Migration of media files to git-LFS, S3, or Cloudflare R2** — media stays in Dropbox-mounted `Production/Event_*/`. The eventual app delivery target is **Cloudflare R2** per LD `CDN_CLOUDFLARE_R2_V1` (locked 2026-04-27, supersedes any prior Firebase Storage / S3 / CloudFront references). That migration is a separate Stream F work item.
3. **Migration of `.docx` narrative files** — stays in Dropbox-mounted `Canon/`.
4. **Restructuring of Directus collections** — schema unchanged; only `file_path` values updated.
5. **Restructuring of asset organization** — `Production/Event_*/audio/`, `video/`, `visuals/`, `masters/` directory structure unchanged.
6. **Restructuring of memory directory layout** — symlink only; underlying files unchanged.
7. **Refactor of `production_server.py`** — code unchanged; only invocation path/cwd changes.
8. **Setup of new CI/CD beyond what gap-fix already installs** — gap-fix delivers the CI/CD; this spec doesn't add to it.
9. **Reconciliation of the 22 code files in the existing 29-file divergence** — handled in separate session per V59_GAP_FIX_HANDOFF_20260508.md §2.
10. **Implementation of Option B fix for Bug 2 + Bug 4** — separate session post-migration per V59_GAP_FIX_HANDOFF_20260508.md sequencing.
11. **Manual-drop-on-options regression port** — separate session.
12. **Tab smoke for other 6 surfaces** — separate session.
13. **Future migration of media to Cloudflare R2** — eventual follow-up per locked LD `CDN_CLOUDFLARE_R2_V1` (Stream F per master tech spec v6 §2). Stream F upload pipeline + manifest atomic publish is a separate tech-spec item, NOT this migration. R2 chosen over Firebase Storage / S3 / CloudFront ($0 egress vs ~$840/yr at 7 TB scale per master spec §0.2).

---

## §11 — Cross-machine Setup (PC bootstrap)

Out of scope for the migration session itself, but documented here for the eventual PC bootstrap session:

1. Install Git, Python 3.11+, Node.js 18+, gh CLI.
2. `git clone https://github.com/kimhyla/mindfulnest-tooling.git C:\Users\<user>\Projects\mindfulnest-tooling`
3. Set env vars in PowerShell profile or system env:
   - `MN_TOOLING_ROOT=C:\Users\<user>\Projects\mindfulnest-tooling`
   - `MN_DROPBOX_ROOT=C:\Users\<user>\Dropbox\Claude Mindfulnest Project Files` (or wherever Dropbox is mounted on PC)
4. `pip install -r Production/requirements.txt` (in tooling clone)
5. Verify Dropbox is fully synced (not "online only") for `Production/Event_*/` and `Canon/`
6. Run `Production/scripts/setup_bypass_permissions.py` (per memory `project_windows_bypass_pending.md`)
7. Verify production server runs:
   ```powershell
   cd $env:MN_TOOLING_ROOT
   python Production/tools/production_server.py --event-dir "$env:MN_DROPBOX_ROOT/Production/Event_1" --storyboard storyboard_v59_prod.html --event-id Event_1
   ```

---

## §12 — Operational Implications

### Daily workflow changes (Mac home + PC work)

**Mac:**
- Editing code: `cd ~/Projects/mindfulnest-tooling`, edit, `git commit`, `git push`
- Editing .docx: open from Dropbox-mounted `Canon/`, edit in Word, save (Dropbox auto-syncs)
- Running storyboard server: `cd ~/Projects/mindfulnest-tooling && python3 Production/tools/production_server.py --event-dir "$MN_DROPBOX_ROOT/Production/Event_1" ...`

**PC:**
- Same workflow with Windows path conventions and `setup_bypass_permissions.py` bootstrap

### Things that look different vs status quo

1. **Two terminals to maintain context in** — `~/Projects/mindfulnest-tooling/` for code work; Dropbox path for content/state inspection
2. **Explicit `git pull` before starting work** — Dropbox auto-sync no longer carries code; need to pull
3. **Explicit `git push` after committing** — to sync to PC

### Things that DON'T change

1. Browser URL: still `http://localhost:5111/`
2. Production server invocation pattern (just from a different cwd)
3. .docx editing workflow
4. Asset registry usage
5. Skill triggers and behavior
6. Directus integration (cred resolution, registration, queries)
7. Memory file behavior (symlinked from new hash dir)
8. Cross-machine content sync (Dropbox)

---

## §13 — Estimated execution time

| Phase | Time estimate |
|---|---|
| A — Pre-flight + preservation | 30 min |
| B — LD supersede + Directus updates | 45 min |
| C — Path sweep | 2-3 hrs |
| D — Memory symlink | 10 min |
| E — Eliminate Dropbox `.git/` | 15 min |
| F — Server restart | 20 min |
| G — Verification | 30 min |
| **Total** | **~5-6 hrs** (Mac side) |
| PC bootstrap (separate session) | +1-2 hrs |

Phase C (path sweep) is the largest variable. If the tooling repo has more hardcoded Dropbox paths than the agents estimated, this could extend to 4-5 hrs.

---

## §14 — Pre-Execution Discipline Checklist (per skill update 2026-05-06)

Before starting Phase A, the executing session must verify:

- [ ] V59 CI/CD gap-fix has merged to main (per timing decision)
- [ ] 22-file divergence reconciliation has completed and merged
- [ ] LD-545 SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 is status=superseded
- [ ] Both `.git/` working trees are clean (no uncommitted changes that would be lost)
- [ ] Storyboard server is running and accessible at http://localhost:5111/
- [ ] GitHub auth is valid (`gh auth status`)
- [ ] Directus is reachable (smoke test: `python3 -c "from Production.lib.directus_admin_client import DirectusAdminClient; c=DirectusAdminClient(); print(c.get_items('prod_modules', limit=1))"`)
- [ ] Dropbox sync is healthy (no pending uploads/downloads)
- [ ] At least 5 GB free disk space (for snapshot + push operations)
- [ ] Both home Mac and work PC dates of last sync are < 24 hrs apart
- [ ] Kim is available for the ~5-6 hr execution window (or has explicitly authorized overnight)
- [ ] No other production session is running concurrently

After each phase:
- [ ] Phase completion `prod_activity_log` row written
- [ ] Phase tag committed in tooling repo (`git tag migration-phase-<letter>-complete`)
- [ ] Verification step from §8 passes for that phase
- [ ] Any deviations logged per §0.9

---

## §15 — Items I May Have Missed (mandatory honest gap-flag)

This spec is comprehensive but the following may need future amendment or are flagged as known limitations:

1. **PC bootstrap detail.** §11 outlines but doesn't fully spec the PC migration. Treat as a separate dependent session that runs after Mac migration completes. May surface PC-specific issues (path separator conventions, line ending conversions, OneDrive vs Dropbox mounting differences) not anticipated here.

2. **Cron / launchd update completeness.** Phase C addresses 3 known cron-relevant scripts. If other automated tasks exist (LaunchAgents at user level, scheduled tasks on PC, Directus scheduled writes from `weekly_preflight_audit.py`), they may need separate updating. Suggest a verification step: `launchctl list | grep -i mindfulnest` and `crontab -l` on Mac.

3. **`.dropbox` xattr handling.** Per Agent A finding: Dropbox-resident `.git/` is xattr-tagged `com.dropbox.ignored=1` to prevent Dropbox from corrupting the index. After migration, this xattr is irrelevant (no `.git/` to ignore). Removing `.git/` should also remove the xattr inherently, but verify with `xattr -l` if any concern.

4. **Active session handoffs.** If a Claude Code session is in progress at migration time, its in-memory state (skill loaded, file references, MEMORY.md auto-load) may not survive cwd change. Suggest: complete or save all active sessions before Phase D.

5. **Outstanding `pending_directus_writes.json` queue entries.** If any queued writes exist at migration time, they should be drained before Phase B's batch PATCH operations to avoid race conditions. Add to Phase A pre-flight check.

6. **Test that `~/Projects/mindfulnest-tooling/.git/` is itself git-friendly to operations from inside Dropbox.** Edge case: if Kim later opens a Claude Code session in the Dropbox path (out of habit), the session will not find a git repo and may behave oddly. Documentation update needed.

7. **Verify symlink works on macOS Spotlight indexing.** Spotlight may follow symlinks differently than expected. If memory dir symlink causes Spotlight to index the same files twice or report inconsistent results, may need to set `mdimporter`/Spotlight excludes.

8. **The 41 open `prod_blockers` reference Dropbox paths in their description text.** Phase B doesn't update these (description is prose, not a path field). Consider a separate sweep to update or accept as historical context.

9. **Skills at `.claude/skills/` may have additional hardcoded paths beyond `execute/SKILL.md`.** Phase C step 6 covers execute skill's 4 hits but a broader sweep is prudent: `grep -rln "Library/CloudStorage" .claude/skills/`.

10. **The `mn-context` skill's session_events.jsonl path resolution.** This file is at `.mn-context/session_events.jsonl` relative to project root. Migration changes "project root" depending on which tree the session sees as root. Verify the skill resolves correctly in the tooling clone.

11. **Production pipeline gaps explicitly named in master tech spec v6 §2 — NOT addressed by this migration.** Three Stream B + Stream F items NOT STARTED:
   - **`assemble_module.py`** — single-MP4 stitcher (LD-284 normalization + concat + universal-phrasing resolver). Per v6 §2: "primary gap to first end-to-end module ship." Mandatory Event 0 spike before M2-M59 production proceeds.
   - **SHA-256 `content_hash` generation + Directus registration.** Per APP_ARCHITECTURE_MASTER §5 + master spec v6 §14, every shipped module MP4 must have content_hash registered for app-side cache verification.
   - **`phase_boundaries` manifest field** — `[{name, start_ms, end_ms}]` per phase (intro / phase_a / phase_b / win_video). Required for app's "Start Magic Spell Again" button per master spec §5.
   - **Cloudflare R2 upload pipeline + manifest atomic publish (Stream F).** Per locked LD `CDN_CLOUDFLARE_R2_V1`. Joint G1 blocker with Stream B + Stream C catalog wiring.
   - These are tracked in `prod_blockers` as G1 blockers; tech-spec session pending separate from this migration.

12. **Doppler secret manager migration is locked but NOT in this spec's scope.** Per master spec v6 §8.3 + LDs 208/227, Doppler replaces `Production/API_KEYS_MASTER.md` as the secret manager. NOT gate-blocking (G2 family beta target) but architecturally locked. Tracked separately in `prod_blockers` for execution post-migration.

13. **Watch list mechanical enforcement** — master spec v6 §8.4 (forbidden vendor SDKs: ads/track/mixpanel/amplitude/facebook/admob/firebase-ads) + §9 (anti-pattern watch list: runtime composition, multi-file expo-video, runtime TTS) require CI-level enforcement. Currently honored by Claude self-discipline + CLAUDE.md Rule 22. Mechanical enforcement is gap-fix Phase G (pre-commit hook) + Phase H (security scan) scope additions. Tracked in new LD `WATCH_LIST_MECHANICAL_ENFORCEMENT_V1`.

14. **Governance doc cascade pending from 2026-04-18.** Per master spec v6 lineage, the cascade for LDs 280/281/282 was queued but never executed. CLAUDE.md was updated (6 references); Bible v13_10/v13_11/v13_13 + 4 SKILL.md files (phase-b-writer, video-expander, scene-to-production, video-producer) reference obsolete patterns. Tracked in `prod_blockers` for separate cleanup session post-gap-fix.

---

## §16 — Reference Index

All files cited in this spec:

| Path | Purpose |
|---|---|
| `Production/lib/paths.py` | Centralized path resolution (created/updated in Phase C) |
| `Production/lib/directus.py` | `try_post_or_queue` for Directus writes (Rule 35) |
| `Production/lib/directus_admin_client.py` | DirectusAdminClient for queries and PATCH |
| `Production/lib/atomic_json_write.py` | Windows atomic-rename retry helper (LD-368) |
| `Production/tools/production_server.py` | The server (~17K lines, mostly path-portable already) |
| `Production/scripts/deploy_storyboard_v59.sh` | Deploy script (already env-overridable per LD-541) |
| `Production/scripts/_weekly_snapshot_wrapper.sh` | Weekly snapshot cron (Phase C update) |
| `Production/scripts/install_backup_crons.sh` | Cron installer (Phase C update) |
| `Production/scripts/weekly_preflight_audit.py` | Phase 0 audit cron (LD-124) |
| `Production/scripts/setup_bypass_permissions.py` | Windows bootstrap (per memory `project_windows_bypass_pending.md`) |
| `Production/tools/sync_reference_docs.py` | Reference doc registry sync (Rule 15) |
| `Production/scripts/asset_findability_hook.py` | Asset findability hook A (LD-421) |
| `Production/scripts/asset_lookup_hook.py` | Asset findability hook B (LD-421) |
| `.claude/skills/execute/SKILL.md` | Execute skill (Phase C update — 4 hardcoded path references) |
| `~/Projects/mindfulnest-tooling/` | Tooling repo working tree (becomes sole git tree) |
| `~/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/` | Old memory hash directory |
| `~/.claude/projects/-Users-kimberlysmith-Projects-mindfulnest-tooling/memory/` | New memory hash directory (symlinked to old) |
| `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` | Gap-fix spec (must be complete before migration) |
| `Production/docs/V59_GAP_FIX_HANDOFF_20260508.md` | Gap-fix handoff |
| `Production/docs/V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md` | Side-fix outcome (Bug 1 + Bug 2/4 state) |
| `Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_MORNING_REPORT_<TS>.md` | This migration's morning report (Phase G output) |
| `~/dropbox_git_snapshot_<TS>.tar.gz` | Phase A snapshot (rollback insurance) |
| `Production/API_KEYS_MASTER.md` | Secrets file (Dropbox-mounted, NOT in git per LD-327) |

---

**End of spec.**

`[CONFIRMED — spec authored 2026-05-08 via tech-spec skill protocol (dual-Opus-agent debate + synthesis), structured per §0/§14/§15/§16 mandatory format, all factual claims tagged with confidence annotation per Rule 24, Kim locked Option A + symlink + sequencing 2026-05-08.]`

`[NEXT STEP: Cursor cross-review. Paste this spec into Cursor with prompt: "Review this migration spec for MindfulNest. What did this miss? What's the highest-risk assumption? What would a senior infra engineer at a real company change?" Then return findings here for Phase 5 amendments before lock.]`
