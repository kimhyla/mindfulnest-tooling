# mindfulnest-tooling

Production tooling for the MindfulNest project. Hosts the storyboard-v2 Preact client + the Python `production_server.py` orchestrator + supporting libs.

This is a **tooling-only** repo — no app code, no media, no shipped assets. The production iOS app lives at `kimhyla/mindfulnest-ios` (per LD-121); this repo exists to enable CI enforcement of integration tests on the production tooling itself (per LD-185 separate-repos pattern).

## Layout

```
Production/
  tools/
    storyboard-v2/         Preact + Vite + Playwright client
      e2e/                 Playwright tests
      src/                 Component source
    production_server.py   HTTP orchestrator (port 5111)
    {beat_generator,kling_startend_pipeline,lipsync_sender,
     ffmpeg_utils,magic_compositor,registered_write,...}.py
    lib/                   tools-local subpackage (credentials, ffmpeg_stitch)
  lib/                     Project-shared subpackage
    {atomic_json_write,directus,directus_admin_client,credential_store,...}.py
  scripts/                 One-shot maintenance + audit scripts
  docs/                    Spec + handoff documents
.github/workflows/
  smoke.yml                Smoke CI — npm ci + npm run build (Phase 5 of repo setup)
```

## First-time setup (every fresh clone, every machine)

Install the git hooks once per clone:

```bash
bash Production/scripts/setup-git-hooks.sh
```

Idempotent — safe to re-run. Installs:

- `.git/hooks/pre-commit` — blocks divergent Dropbox runtime edits (LD `PRE_COMMIT_DROPBOX_EDIT_GATE_V1`). Bypass: `MN_SKIP_DROPBOX_EDIT_GATE=1 git commit ...`
- `.git/hooks/pre-push` — blocks untracked source files + local TS build errors before push (LD `GIT_HOOK_INFRASTRUCTURE_CROSS_MACHINE_V1`, prevents the 2026-05-14 cropper.ts class of 36hr-red-CI). Bypass: `git push --no-verify`

Templates live at `Production/scripts/git_hooks/`. The `.git/hooks/` directory itself is git-ignored by design — hooks must be installed per-clone. Works on Mac directly and on Windows via Git-Bash (ships with Git for Windows).

## Development

Local Mac dev with Dropbox synced:

```bash
cd Production/tools/storyboard-v2
npm install
npm run build       # tsc -b && vite build
npm run dev         # vite dev server on http://localhost:5173
```

The Python server reads `Production/API_KEYS_MASTER.md` from the synced Dropbox path automatically. For non-Dropbox environments (CI, fresh clones), copy `.env.example` → `.env` and fill in real values.

## Provenance

- Initial extract from canonical Dropbox tree on 2026-05-03 (preflight #200, LD `TOOLING_REPO_CREATED_V1`).
- Canonical working tree remains the Dropbox folder — this repo is the CI-shipping subset only.
- Setup results doc: `Production/docs/TOOLING_REPO_SETUP_RESULTS.md` in the Dropbox tree.

## Related repositories

- `kimhyla/mindfulnest-ios` — production iOS app code (do NOT touch from this repo)
- `kimhyla/MindfulNest`, `kimhyla/mindfulnest`, `kimhyla/mindfulnest-app` — legacy Firebase repos (do NOT touch)

## Key locked decisions honored

- LD-121 `MINDFULNEST_GIT_REPO` — iOS app repo is separate
- LD-185 `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA` — separate-repos-for-separate-concerns pattern
- LD-327 `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1` — autonomous sessions in this tree must use env vars or `cd` back to the Dropbox tree for Directus writes
- Rule 19 — no shortcuts in shippable code
