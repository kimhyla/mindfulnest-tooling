# Event_e2e_fixture — Playwright fixture for `e2e/s5_5ce_proper_fix.spec.ts`

**Created:** 2026-05-03 (proper-fix Phase 1 §17)
**LDs:** `MANDATORY_E2E_GATE_V1`, `CI_PLAYWRIGHT_ON_COMMIT_V1`

This directory holds a minimal, deterministic event fixture for Playwright e2e tests in `Production/tools/storyboard-v2/e2e/`. It exists so tests verify the **code**, not Kim's mutable production data (per spec §17 fixture-pinning).

## Layout

- `.pristine/production_state.json` — canonical v3-shape state, copied over the live state file by `e2e/global-setup.ts` before every test run.
- `.pristine/storyboard_v59_prod.html` — placeholder satisfying `production_server.py --storyboard` CLI flag.
- `production_state.json` — **generated** at test-run by globalSetup; gitignored.
- `production_spend.json`, `.backups/`, `clips_dir/` — generated at runtime by `StateManager._init_files`; gitignored.

## State seed

| Video | Beats | Why |
|---|---|---|
| `intro` | 3 (`beat_01`, `beat_02`, `beat_03`) | R1.1 asserts "switching to resolution clears beats; switching back restores them" |
| `resolution` | 0 | Same — R1.1 empty-partition test |
| `phase_a` | status=`pending` | Tabs render without errors |
| `phase_b` | status=`pending` | Tabs render without errors |

## Library seeding

`BG_STILLS_DIR` is project-level (`Production/beat_generator_stills/sources/`), not event-scoped. `e2e/global-setup.ts` writes a single 1×1 transparent PNG named `e2e_fixture_test.png` into that directory at the start of each test run, and `global-teardown.ts` removes it at exit. This satisfies R2 (drag-drop) and R5 (library tile sizing) without polluting any of Kim's authored library state.

## How to invoke locally

```bash
cd Production/tools/storyboard-v2
# Playwright spawns production_server.py via webServer config in playwright.config.ts:
npx playwright test
```

The webServer command points `--event-dir` at this fixture, so the running server reads `production_state.json` from this directory (the copy that globalSetup just wrote).

## Why .pristine/ exists

Tests mutate `production_state.json` in normal operation (beat-text edits, scope changes). Without a pristine snapshot, every run leaves `git status` dirty. globalSetup copies `.pristine/production_state.json` over the live file before each run, restoring a known good state.
