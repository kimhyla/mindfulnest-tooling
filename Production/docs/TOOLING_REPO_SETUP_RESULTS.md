# TOOLING_REPO_SETUP_RESULTS — 2026-05-03

**Status:** [CONFIRMED against gh CLI + Directus] complete. Smoke CI green. Repo ready for the v59 S5.5c+e proper-fix session.

**Provenance:**
- preflight #200 (`tooling-repo-setup-20260503`)
- LD `TOOLING_REPO_CREATED_V1` registered in `prod_locked_decisions`
- activity log `TOOLING_REPO_SETUP_COMPLETE` written to `prod_activity_log`

---

## What was created

| Item | Value |
|---|---|
| Repo URL | https://github.com/kimhyla/mindfulnest-tooling |
| Visibility | PRIVATE |
| Default branch | `main` |
| Working tree (Mac) | `/Users/kimberlysmith/Projects/mindfulnest-tooling` |
| Initial commit SHA | `b582f44` (extract) + `faa25ca` (smoke workflow) |
| Smoke CI workflow | `.github/workflows/smoke.yml` (npm ci + npm run build) |
| Smoke run URL | https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25299958182 |
| Smoke run conclusion | success (21 seconds, ubuntu-latest) |
| Repo size on disk | 6.6 MB (working tree) / under 5 MB (git tree minus .git) |

## Subset that was copied

| Source (Dropbox tree) | Target (new tree) | Notes |
|---|---|---|
| `Production/tools/storyboard-v2/` | `Production/tools/storyboard-v2/` | Excludes `node_modules`, `dist`, `test-results` |
| `Production/tools/` (Python files + `lib/` subpkg) | `Production/tools/` | Excludes `*.bak*`, `archive/`, `__pycache__/`, media exts |
| `Production/lib/` | `Production/lib/` | Project-shared subpackage (`atomic_json_write`, `directus`, `directus_admin_client`, `credential_store`, `wavespeed_poll_client`) |
| `Production/scripts/` | `Production/scripts/` | One-shot maintenance scripts |
| `Production/docs/` | `Production/docs/` | Includes the proper-fix spec |

Total: 355 files, 137,717 lines.

## Critical Python deps verified working from new tree

`production_server.py --help` succeeds — proves all module-level + sibling imports resolve from new tree:

- `from lib.atomic_json_write import atomic_json_write` ✓ (resolves to `Production/lib/atomic_json_write.py`)
- `from ffmpeg_utils import strip_audio` ✓ (resolves to `Production/tools/ffmpeg_utils.py`)
- `from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC` ✓
- `from kling_startend_pipeline import (...)` ✓
- Lazy imports: `from credentials import load_credentials` (via `Production/tools/lib/credentials.py`), `from credential_store import get_secret_optional` (via `Production/lib/credential_store.py`), `from registered_write import register_asset` (via `Production/tools/registered_write.py`) — all source files present.

`production_server.py --smoke-test` proceeds past all imports + arg parsing + state-manager init, then halts at `Directus lock unreachable` because the new tree has no API_KEYS_MASTER.md (.gitignored — secrets stay out). This is **expected behavior** documented in the env requirements below.

## Cred / env requirements (per LD-327)

`/Users/kimberlysmith/Projects/mindfulnest-tooling/.env.example` enumerates required env vars. Summary:

| Env Var | Required for | Local-Mac fallback |
|---|---|---|
| `DIRECTUS_URL` / `DIRECTUS_ADMIN_EMAIL` / `DIRECTUS_ADMIN_PASSWORD` | Directus writes (audit trail) | `directus_admin_client._candidate_keys_paths` falls back to `~/Library/CloudStorage/Dropbox/.../API_KEYS_MASTER.md` |
| `WAVESPEED_API_KEY` | Animation (Kling) | API_KEYS_MASTER.md (Dropbox) |
| `BFL_API_KEY` | FLUX Kontext stills | API_KEYS_MASTER.md |
| `ELEVENLABS_API_KEY` | TTS | API_KEYS_MASTER.md |
| `OPENAI_API_KEY` | GPT stills (beat generator) | API_KEYS_MASTER.md |

CI runners do NOT have the Dropbox folder. For CI runs of anything beyond `npm run build`, use GitHub Actions secrets.

## What the proper-fix session needs

### Path resolution for `playwright.config.ts:webServer.command`

The proper-fix spec Phase 1.4 specifies:
```typescript
webServer: {
  command: 'python3 ../../../Production/tools/production_server.py --event-dir ../../../Production/Event_1 --storyboard storyboard_v59_prod.html --event-id Event_1',
  url: 'http://localhost:5111/api/health',
  timeout: 30 * 1000,
  reuseExistingServer: !process.env.CI,
},
```

**This path resolves correctly from the new tree** — `Production/tools/storyboard-v2/playwright.config.ts` → `../../../Production/tools/production_server.py` resolves to `~/Projects/mindfulnest-tooling/Production/tools/production_server.py`. ✓

**Open issue for proper-fix Phase 1:** `Production/Event_1/` is `.gitignore`d (media). Proper-fix Phase 1 must create a tracked `Event_e2e_fixture/` (small, mediafree) for Playwright tests, and update the webServer `--event-dir` to point at the fixture. The proper-fix spec already calls this out as part of Phase 1.

### CI workflow location

The proper-fix spec Phase 1.3 says: install `Production/github_actions/playwright_e2e.yml` (canonical source) AND copy/symlink to `.github/workflows/playwright_e2e.yml`. The new tree has the `.github/workflows/` directory created (smoke.yml lives there); proper-fix Phase 1.3 just adds another file alongside it.

### Working tree path for execution

All proper-fix session work happens at: `/Users/kimberlysmith/Projects/mindfulnest-tooling`

NOT in the Dropbox tree. The Dropbox tree remains the canonical authoring tree (specs, docs, locked decisions). The new tree is the CI-shipping subset.

### Directus cred handling for the proper-fix session

Per LD-327, when the proper-fix session runs from `~/Projects/mindfulnest-tooling/`:
- The Mac CloudStorage Dropbox path fallback in `directus_admin_client.py` will resolve `~/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md` and read creds from there. **This works for local Mac dev.**
- Alternative: prefix Directus-writing scripts with `cd /Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude\ Mindfulnest\ Project\ Files && python3 ...` to use the Dropbox lib path.
- For CI: required env vars must be set as GitHub Actions secrets (not in scope this session).

## Out-of-scope items (proper-fix session work)

- `Event_e2e_fixture/` creation (proper-fix Phase 1)
- `playwright.config.ts:webServer` field (proper-fix Phase 1.4)
- Full `playwright_e2e.yml` workflow (proper-fix Phase 1.3)
- R1-R5 fixes (proper-fix Phase 3)
- All 5 NEW LDs (proper-fix Phase 8): `MANDATORY_E2E_GATE_V1`, `CI_PLAYWRIGHT_ON_COMMIT_V1`, `BROWSER_SMOKE_REDEFINED_V1`, etc.
- Modifying the Dropbox folder's git state

## Commands the proper-fix session should run first

```bash
# Sync this tree with origin
cd ~/Projects/mindfulnest-tooling && git pull

# Create the proper-fix branch
git checkout -b claude/s5_5ce-proper-fix

# Install storyboard-v2 deps (one-time per machine)
cd Production/tools/storyboard-v2 && npm install
npx playwright install --with-deps chromium

# Verify existing scaffold builds clean
npm run build
```

## Honored locked decisions

- LD-121 `MINDFULNEST_GIT_REPO` — iOS app is at `kimhyla/mindfulnest-ios`; this repo is separate.
- LD-185 `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA` — separate-repos pattern for separate concerns.
- LD-327 `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1` — cred loading explicit in `.env.example` + this doc.
- Rule 19 — no shortcuts; smoke workflow is real CI not theater.
- Rule 24 — confidence annotations applied below.

## Confidence-tagged claims

- [CONFIRMED against `gh repo view` JSON] Repo is private, default branch is `main`, exists at https://github.com/kimhyla/mindfulnest-tooling.
- [CONFIRMED against `gh run view 25299958182 --json conclusion`] Smoke CI run conclusion = `success`.
- [CONFIRMED against `du -sh ~/Projects/mindfulnest-tooling`] Working tree is 6.6MB.
- [CONFIRMED against `python3 production_server.py --help` from new tree] All module-level imports resolve.
- [CONFIRMED against `git ls-files | grep media-exts`] Zero media files committed.
- [INFERRED — verify] CI run for the next session's Playwright workflow will succeed at the install/build steps that the smoke workflow already validated. The Playwright-specific steps (test execution) are net new and unproven until proper-fix Phase 1 ships.
