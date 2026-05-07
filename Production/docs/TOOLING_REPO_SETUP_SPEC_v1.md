# Tooling Repo Setup — Tech Spec v1

**Date:** 2026-05-03
**Classification:** ARCHITECTURAL PRECONDITION — must complete before S5.5c+e proper-fix session can run with real CI enforcement
**Predecessor:** `STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md` halted at Phase 0 due to no GitHub remote on Dropbox tree
**Consumers:** S5.5c+e proper-fix (next session); all future v59 storyboard sessions

## §1 Why this is its own session

The Dropbox project folder has no GitHub remote. Cursor v11's load-bearing structural fix for proper-fix (`.github/workflows/playwright_e2e.yml` enforcing Playwright e2e on every commit) is impossible without one. Three workarounds were rejected: (a) pre-commit hook (still local-only enforcement; doesn't address Cursor v9's "process smell"); (b) defer Phase 4 with CRITICAL blocker (papers over the gap); (c) push storyboard tooling into `kimhyla/mindfulnest-ios` (pollutes the iOS app repo per LD `MINDFULNEST_GIT_REPO`). The structurally-clean answer is a dedicated tooling repo following the established pattern from LD `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA`.

## §2 Discovery findings (verified by direct code inspection)

### §2.1 production_server.py dependency graph

`production_server.py` imports:
- **stdlib only** for everything except:
- `from lib.atomic_json_write import atomic_json_write` (Production/lib)
- `from ffmpeg_utils import strip_audio` (Production/tools sibling)
- `from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC` (Production/tools sibling)
- `from kling_startend_pipeline import (...)` (Production/tools sibling)

The 3 sibling tools modules (`ffmpeg_utils.py`, `lipsync_sender.py`, `kling_startend_pipeline.py`) only import stdlib + `lib.atomic_json_write`. Self-contained chain.

**`sys.path` manipulations** at top of `production_server.py:54-58`:
```python
sys.path.insert(0, os.path.dirname(__file__))  # Production/tools/
_PROD_DIR_FOR_SHARED_LIB = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, _PROD_DIR_FOR_SHARED_LIB)  # Production/
```

So the runtime expectation is: `Production/tools/` and `Production/` are both on `sys.path`. The new repo must replicate this layout.

### §2.2 Env vars / credentials

`production_server.py` reads (selected):
- `MINDFULNEST_T1_ENABLED` (default "1")
- `PRODUCTION_SERVER_SINGLE_MACHINE` (default off)
- `MINDFULNEST_WRITE_PATH`
- `WAVESPEED_API_KEY`, `ELEVENLABS_API_KEY`, `EVOLINK_API_KEY` (only used by code paths exercising those APIs)
- `DIRECTUS_ADMIN_PASSWORD` (used by Directus lock client at line 2227+)

`Production/lib/credential_store.py` resolves env vars first (Doppler-friendly), then falls back to parsing `Production/API_KEYS_MASTER.md`. **API_KEYS_MASTER.md must NEVER be pushed to GitHub.**

For CI: env vars come from GitHub Secrets → workflow env → process env. The legacy `.md` fallback path is unused in CI.

### §2.3 Existing test scaffold

`Production/tools/storyboard-v2/playwright.config.ts` baseURL: `process.env.STORYBOARD_BASE_URL ?? 'http://localhost:5111'`. **No `webServer:` config.** Tests run against an externally-started server today. The proper-fix session's Phase 1.4 ADDS `webServer:` — that's not this session's job.

5 e2e specs exist (`smoke.spec.ts`, `behavioral-parity.spec.ts`, `rollback.spec.ts`, `touchpoint-a.spec.ts`, `helpers.ts`). Per proper-fix Phase 0.4, they need to actually run cleanly before proper-fix Phase 2 writes new tests — but that's also not this session's job.

### §2.4 Size and content boundaries

| Path | Size | This session |
|---|---|---|
| `Production/Event_1/` | 7.2 GB | EXCLUDE (media) |
| `Production/Phase_B_Style_Guide/` | 286 MB | EXCLUDE (media) |
| `Production/Character_Assets/` | 249 MB | EXCLUDE (media) |
| `Production/Backgrounds/` | 141 MB | EXCLUDE (media) |
| Other character/media dirs | 50-150 MB each | EXCLUDE |
| `Production/tools/storyboard-v2/node_modules/` | 82 MB | EXCLUDE (gitignored) |
| `Production/tools/storyboard-v2/src/` | 272 KB | INCLUDE |
| `Production/tools/storyboard-v2/e2e/` | 52 KB | INCLUDE |
| `Production/tools/storyboard-v2/dist/` | 124 KB | EXCLUDE (gitignored; built in CI) |
| `Production/tools/production_server.py` | 764 KB | INCLUDE |
| `Production/tools/ffmpeg_utils.py`, `lipsync_sender.py`, `kling_startend_pipeline.py` | <100 KB total | INCLUDE |
| `Production/lib/` (excl `__pycache__`, `tests`) | <50 KB | INCLUDE |
| `Production/API_KEYS_MASTER.md` | varies | **NEVER INCLUDE** |
| `Production/scripts/` | varies | EXCLUDE (not exercised by Playwright; proper-fix Phase 3.4 touches `populate_prod_modules_from_gameplay_scope.py` but that's a one-shot data migration, not a test target) |

Estimated final repo size after copy + .gitignore: **<2 MB**.

### §2.5 gh CLI auth

`gh auth status` confirms `kimhyla` logged in with token scopes `gist`, `read:org`, `repo`, `workflow`. Sufficient for `gh repo create --private` + workflow files. ✓

## §3 Locked decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Repo name: **`kimhyla/mindfulnest-tooling`**, PRIVATE | Matches `kimhyla/mindfulnest-ios` naming convention; private per LD `MINDFULNEST_GIT_REPO` |
| 2 | Working tree: **`~/Projects/mindfulnest-tooling/`** (outside Dropbox) | Per established pattern (`mindfulnest-ios` at `~/Projects/MindfulNest`); Dropbox + `.git/` historically conflicts |
| 3 | **Mirror `Production/` directory structure** in new repo | Replicates the `sys.path` layout production_server.py expects; the proper-fix spec's webServer config works without rewriting |
| 4 | **Subset boundary** (canonical-in-tooling): `Production/tools/storyboard-v2/` + `Production/tools/{production_server.py, ffmpeg_utils.py, lipsync_sender.py, kling_startend_pipeline.py}` + `Production/lib/{atomic_json_write.py, credential_store.py, directus.py, directus_admin_client.py, wavespeed_poll_client.py, __init__.py}` | Minimum to run server + e2e tests; everything else stays Dropbox-canonical |
| 5 | **Sync strategy:** tooling repo is canonical for boundary files; Dropbox copies become DEPRECATED MIRRORS (no manual edits going forward in the boundary). Outside the boundary, Dropbox is canonical | Single source of truth per file; manual `cp` only when boundary files change |
| 6 | **Fixture location:** `Production/Event_e2e_fixture/` lives in TOOLING repo (not Dropbox). Created by proper-fix session Phase 1, NOT this session | Tests live with their fixtures |
| 7 | **Cred plumbing:** GitHub Secrets → workflow env. NEVER push `Production/API_KEYS_MASTER.md`. `.env.example` documents required vars without secrets | Per LD `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1` |
| 8 | **Workflow scope this session: SMOKE ONLY** (`npm ci` + `npm run build`). Full Playwright workflow is proper-fix Phase 1.3 work | Proves CI plumbing works end-to-end without taking on test-server-spawn complexity |
| 9 | **Dropbox folder git state: UNTOUCHED.** No remote added; no config changes | Dropbox stays Dropbox; tooling repo is the GitHub presence |
| 10 | **Out of scope:** all proper-fix work (R1-R5 fixes, +NewEvent, fixture creation, Playwright workflow, 5 NEW LDs) | Scope discipline; this session is precondition only |

## §4 Approach

This session is **pure infrastructure setup**. No bug fixes. No architectural changes to the working tree. The deliverable is a green CI run on a new repo + a clear handoff to proper-fix.

## §5 Implementation phases

### Phase 0 — Pre-flight

**0.1.** Read this spec + LDs `MINDFULNEST_GIT_REPO`, `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA`, `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1` (full `decision_text`).

**0.2.** Verify gh CLI: `gh auth status` shows logged in with `repo` + `workflow` scopes. (Already verified in Discovery.)

**0.3.** Verify `~/Projects/mindfulnest-tooling/` does NOT yet exist.

**0.4.** Verify Dropbox folder git state: `git remote -v` should remain empty after this session.

**0.5.** Write `prod_preflight_reviews` row via `try_post_or_queue` per Rule 35:
- `task_id`: `"tooling-repo-setup-20260503"`
- `task_type`: `"infrastructure"`
- references S5.5c+e preflight #199 as predecessor (this is what blocked the proper-fix session)
- read-back to confirm

### Phase 1 — Initialize working tree + .gitignore

**1.1.** `mkdir -p ~/Projects/mindfulnest-tooling && cd ~/Projects/mindfulnest-tooling && git init -b main`

**1.2.** Write `.gitignore` BEFORE any copy:
```gitignore
# Node / build
node_modules/
dist/
test-results/
playwright-report/

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/

# Editor / OS
.DS_Store
.vscode/
.idea/

# Secrets — NEVER commit
.env
.env.local
.doppler/
Production/API_KEYS_MASTER.md

# Media (defense in depth — boundary should already exclude these)
*.mp4
*.mov
*.wav
*.mp3
*.png
*.jpg
*.jpeg
*.gif
*.pdf
*.psd

# Dropbox artifacts
.dropbox
.dropbox.attr

# Production data dirs (not part of subset boundary)
Production/Event_*
Production/Magic
Production/Milestones
Production/Sessions
Production/_previews
Production/Voice_Profiles
Production/tts_cache
Production/Cache
Production/Character_Assets
Production/Backgrounds
Production/Phase_B_Style_Guide
Production/test_harness
Production/beat_generator_stills
Production/stitch_editor_cache
Production/Grizzle
Production/Oliver
Production/Luna
Production/Bork
Production/The_King
Production/Willow
Production/scripts
```

**1.3.** Write `.env.example` documenting required env vars (no secrets):
```
# Required for production_server.py — supply via GitHub Secrets in CI
DIRECTUS_URL=https://...
DIRECTUS_ADMIN_EMAIL=...
DIRECTUS_ADMIN_PASSWORD=...

# Optional — only needed by code paths that hit these APIs
WAVESPEED_API_KEY=...
ELEVENLABS_API_KEY=...
EVOLINK_API_KEY=...
OPENAI_API_KEY=...

# Server flags
MINDFULNEST_T1_ENABLED=1
PRODUCTION_SERVER_SINGLE_MACHINE=
MINDFULNEST_WRITE_PATH=
```

### Phase 2 — Copy subset

**2.1.** Use `rsync` (faster + flag-friendly) to copy with structure preserved:

```bash
DROPBOX_PROD="/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
TOOLING="$HOME/Projects/mindfulnest-tooling"

# Mirror Production/ structure (creates Production/tools/ + Production/lib/)
mkdir -p "$TOOLING/Production/tools" "$TOOLING/Production/lib"

# storyboard-v2 (excluding node_modules/dist/test-results)
rsync -a --exclude=node_modules --exclude=dist --exclude=test-results --exclude=playwright-report \
  "$DROPBOX_PROD/tools/storyboard-v2/" "$TOOLING/Production/tools/storyboard-v2/"

# Server + sibling Python files
cp "$DROPBOX_PROD/tools/production_server.py" "$TOOLING/Production/tools/"
cp "$DROPBOX_PROD/tools/ffmpeg_utils.py" "$TOOLING/Production/tools/"
cp "$DROPBOX_PROD/tools/lipsync_sender.py" "$TOOLING/Production/tools/"
cp "$DROPBOX_PROD/tools/kling_startend_pipeline.py" "$TOOLING/Production/tools/"

# lib/ (excluding __pycache__ + tests)
rsync -a --exclude=__pycache__ --exclude=tests \
  "$DROPBOX_PROD/lib/" "$TOOLING/Production/lib/"
```

**2.2.** Verify NOT copied:
- `find Production -name "API_KEYS_MASTER*"` returns nothing
- `du -sh .` returns < 5 MB
- `find . -size +1M` returns nothing surprising

**2.3.** If `du -sh .` > 5 MB: STOP, surface to Kim, review .gitignore.

### Phase 3 — Sanity check imports

**3.1.** From `~/Projects/mindfulnest-tooling/Production/tools/`:
```bash
cd ~/Projects/mindfulnest-tooling
python3 -c "
import sys
sys.path.insert(0, 'Production/tools')
sys.path.insert(0, 'Production')
import production_server
print('OK: production_server imported')
"
```

**3.2.** If import fails:
- Capture the error
- Identify the missing module
- Either: copy that file from Dropbox to tooling repo (extending subset)
- Or: STOP and surface — extending subset means a discovery-phase miss, worth pausing for

**3.3.** Repeat with: `python3 -c "import lib.directus; import lib.directus_admin_client; print('OK')"` from tooling repo root with `sys.path` including `Production/`.

### Phase 4 — Smoke workflow

**4.1.** Create `.github/workflows/smoke.yml`:
```yaml
name: smoke

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install client deps
        working-directory: Production/tools/storyboard-v2
        run: npm ci
      - name: TypeScript build
        working-directory: Production/tools/storyboard-v2
        run: npm run build
```

**4.2.** Create `README.md` (brief; ~30 lines) explaining the repo's purpose, boundary with Dropbox, and pointer to `STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md` for the next phase of work.

### Phase 5 — Initial commit + push

**5.1.** `git add . && git commit -m "Initial extract from Dropbox tooling tree (smoke workflow only)"`

**5.2.** `gh repo create kimhyla/mindfulnest-tooling --private --source=. --push --description "Storyboard v59 tooling — CI-bound mirror of Production/{tools/storyboard-v2,tools/server,lib} from Dropbox canonical working tree"`

**5.3.** Verify: `gh repo view kimhyla/mindfulnest-tooling --json url,visibility` confirms private + URL.

### Phase 6 — Verify CI green

**6.1.** Wait up to 5 min: `gh run list --repo kimhyla/mindfulnest-tooling --limit 1`

**6.2.** When complete: `gh run view <run-id> --repo kimhyla/mindfulnest-tooling`

**6.3.** If GREEN: continue. If RED: diagnose (Node version mismatch, path issue, missing dep). Fix, push, retry. If can't fix in 30 min: STOP, surface.

**6.4.** Capture run URL for handoff doc.

### Phase 7 — Document for proper-fix session

**7.1.** Write `Production/docs/TOOLING_REPO_SETUP_RESULTS.md` (in DROPBOX, not in tooling repo):

```markdown
# Tooling Repo Setup — Results

**Completed:** 2026-05-03
**Spec:** `TOOLING_REPO_SETUP_SPEC_v1.md`

## Repo
- URL: https://github.com/kimhyla/mindfulnest-tooling
- Visibility: PRIVATE
- Working tree: ~/Projects/mindfulnest-tooling/
- Initial commit: <sha>
- Smoke run: <gh run URL>, status: green

## Subset shipped
- Production/tools/storyboard-v2/ (excl node_modules/dist/test-results)
- Production/tools/{production_server.py, ffmpeg_utils.py, lipsync_sender.py, kling_startend_pipeline.py}
- Production/lib/{atomic_json_write, credential_store, directus, directus_admin_client, wavespeed_poll_client, __init__}.py

## Env vars required for proper-fix CI workflow
- DIRECTUS_URL, DIRECTUS_ADMIN_EMAIL, DIRECTUS_ADMIN_PASSWORD (REQUIRED — Directus locks)
- WAVESPEED_API_KEY, ELEVENLABS_API_KEY (optional — only if test exercises those API paths)
- MINDFULNEST_T1_ENABLED=1 (default)

To set in GitHub Secrets:
gh secret set DIRECTUS_URL --repo kimhyla/mindfulnest-tooling
... etc.

## Sync rules going forward
- Tooling repo is CANONICAL for boundary files (subset shipped)
- Dropbox copies of boundary files are DEPRECATED MIRRORS — don't edit
- All other files: Dropbox is canonical
- Manual `cp` from tooling repo to Dropbox required only if boundary files need to be visible to Dropbox-tree tools

## What proper-fix session does next
1. Open fresh terminal, cd to ~/Projects/mindfulnest-tooling/
2. Run proper-fix spec Phase 0-8 in TOOLING REPO working tree (not Dropbox)
3. Phase 1.3 installs `.github/workflows/playwright_e2e.yml` IN THIS REPO
4. Phase 1's fixture pinning step creates Production/Event_e2e_fixture/ IN THIS REPO
5. CI runs against THIS repo automatically
```

### Phase 8 — Directus + closeout

**8.1.** Write LD `TOOLING_REPO_CREATED_V1` (HIGH) via `try_post_or_queue`:
- `decision_key`: `TOOLING_REPO_CREATED_V1`
- `severity`: HIGH
- `decision_text`: includes repo URL, working tree path, smoke run URL, boundary list, references LDs `MINDFULNEST_GIT_REPO`, `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA`, `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1`
- `enforcement_type`: `governed_file` (so future handoff-writing sessions see it before referencing the wrong working tree)

**8.2.** Write LD `TOOLING_REPO_SUBSET_BOUNDARY_V1` (HIGH):
- Captures the canonical-in-tooling vs canonical-in-Dropbox boundary
- Lists exact files in scope
- Locks the sync rule

**8.3.** Write `prod_activity_log` row `TOOLING_REPO_SETUP_COMPLETE` with summary + run URL + handoff-doc-id.

**8.4.** Final report to Kim (concise, ≤200 words):
- Repo URL
- Smoke status
- Path to results doc
- Exact next-action: "Open fresh terminal, paste proper-fix-revised handoff (Claude will produce next)"

## §6 Files created

### Tooling repo (~/Projects/mindfulnest-tooling/)
- `.gitignore`
- `.env.example`
- `README.md`
- `.github/workflows/smoke.yml`
- `Production/tools/storyboard-v2/` (copy)
- `Production/tools/{production_server, ffmpeg_utils, lipsync_sender, kling_startend_pipeline}.py` (copies)
- `Production/lib/*.py` (copies)

### Dropbox tree
- `Production/docs/TOOLING_REPO_SETUP_RESULTS.md` (NEW)
- `Production/docs/TOOLING_REPO_SETUP_SPEC_v1.md` (this file; pre-existing)

### Directus
- `prod_locked_decisions`: 2 NEW LDs
- `prod_preflight_reviews`: 1 row
- `prod_activity_log`: phase rows + COMPLETE row

## §7 Verification gates (10)

| Gate | Check |
|---|---|
| G1 | `gh auth status` returns logged in with `repo` + `workflow` scopes |
| G2 | `~/Projects/mindfulnest-tooling/` exists with `.git/` |
| G3 | `du -sh ~/Projects/mindfulnest-tooling` < 5 MB |
| G4 | `find ~/Projects/mindfulnest-tooling -name "API_KEYS_MASTER*"` returns nothing |
| G5 | `python3 -c "import production_server"` from tooling repo (with sys.path patched) succeeds |
| G6 | `gh repo view kimhyla/mindfulnest-tooling` confirms private + URL |
| G7 | `gh run list` shows smoke workflow run; latest is green |
| G8 | Dropbox folder `git remote -v` is still empty |
| G9 | 2 NEW LDs registered + read-back |
| G10 | `Production/docs/TOOLING_REPO_SETUP_RESULTS.md` exists in DROPBOX with all required fields |

## §8 Error cases

| Failure | Handling |
|---|---|
| `gh auth status` not logged in | STOP; tell Kim to `gh auth login`; do NOT attempt to log in on her behalf |
| `~/Projects/mindfulnest-tooling/` already exists | STOP; ask Kim — may be leftover from prior attempt |
| `production_server` import fails in new tree | Capture error; identify missing file; STOP and surface — discovery missed something |
| Repo size > 5 MB after copy | STOP; review .gitignore; likely a media leak |
| `gh repo create` fails (auth, name conflict, billing) | STOP; surface |
| Smoke workflow red | Diagnose; fix; retry. If unfixable in 30 min: STOP, surface |
| Need to modify Dropbox folder's git state for ANY reason | STOP; this session must not touch it |
| `cp`/`rsync` errors due to file locks (Dropbox sync) | Wait 30s + retry. If persistent: STOP, surface (Dropbox may be mid-sync) |
| Network failure during `gh repo create` or `git push` | Retry once; if persistent: STOP, surface |

## §9 Out of scope

- Bug fixes (R1-R5)
- + New Event UI/server (proper-fix session)
- Playwright workflow (proper-fix session)
- Event_e2e_fixture creation (proper-fix session)
- Doppler integration (future session if needed)
- Sync-script automation between Dropbox + tooling (manual `cp` is the rule for now; automation if pain emerges)
- Migrating Dropbox folder to be a git remote consumer (out of scope; Dropbox stays remoteless)

## §10 Dependencies

- gh CLI authed with `repo` + `workflow` scopes (verified in Discovery)
- Internet (for `gh repo create` + `git push` + GitHub Actions run)
- Dropbox folder Production/ tree intact (read-only; this session doesn't modify)

## §11 Notes for the executing session

- This is **infrastructure setup, not code work.** No design decisions remain. Execute the phases.
- **Discovery already done.** Spec §2 captures everything; don't re-discover. If reality diverges from §2, STOP and surface.
- **Dropbox folder is READ-ONLY** for this session. If a phase requires writing to Dropbox, only `Production/docs/TOOLING_REPO_SETUP_RESULTS.md` is allowed.
- **The tooling repo's working tree is at `~/Projects/mindfulnest-tooling/`, NOT inside Dropbox.** All `cd` commands targeting "the repo" mean that path.
- **No secrets in the repo.** API_KEYS_MASTER.md, .env, .doppler/, anything-keys-shaped — gitignored AND defense-in-depth checked at G4.
- **Smoke workflow only.** Full Playwright workflow is the proper-fix session's deliverable. Don't combine.
- **Per Rule 19:** no shortcuts. If imports fail in Phase 3, surface — don't quietly add files until things work.
- **Per Rule 29:** server staleness check is N/A here (server isn't running in CI for smoke).
- **Per Rule 35:** every Directus write via `try_post_or_queue` with read-back.
- **End-of-session report ≤ 200 words.** Kim is exhausted; she needs the URL + status + next-action, not a phase-by-phase narrative.

---

**End of Tooling Repo Setup Spec v1.**
