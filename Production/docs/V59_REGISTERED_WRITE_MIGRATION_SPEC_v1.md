# V59 Registered-Write MCP Activation Spec — v1

**Authored:** 2026-05-10
**Author:** Claude (spawn-task `AUTONOMY_REGISTERED_WRITE_CROSS_REPO_MIGRATION_20260510`)
**Authority:** parent-session spawn prompt + LD-505 (boundary tightening) + CLAUDE.md Rule 19 (no shortcuts; no error paths) + CLAUDE.md Rule 34 (asset findability)
**Phase 0 preflight:** `prod_preflight_reviews` id=213 (Tier C, approved)
**Cross-session coord:** `app_activity_log` id=2559 + work-zone claim id=431
**Reference doc:** `prod_reference_docs` id=210

---

## §0 Title revision

The spawn prompt was titled "registered-write cross-repo migration" on the assumption that `Production/tools/registered_write.py` did NOT exist in the tooling-mcp tree and needed to be copied from Dropbox. **First-pass investigation confirmed this assumption was wrong** — the file already existed in tooling-mcp, but with a single broken import line. The actual fix is a **1-line bug fix + 3 supporting changes**, not a file-copy migration. The spec title is updated to "MCP Activation" to reflect that.

(I attempted the Dropbox-copy approach first and got 17 tests passing, but the diffs surfaced that I had **regressed** tooling-mcp's cleaner architecture — the tooling version uses `Production.lib.paths.DROPBOX_ROOT` for cross-platform path resolution; the Dropbox version uses hardcoded paths. Reverted that overwrite and re-implemented as the 1-line fix below. Documented in §6 as a deviation per DS-19.)

## §1 Problem statement

Today, the Directus MCP server's `register_asset` and `find_asset` tools at `Production/mcp_servers/directus/tools/assets.py` use **lazy imports** of `Production.tools.registered_write` (function-body imports inside `register_asset()` and `find_asset()`).

Tooling-mcp DOES have `Production/tools/registered_write.py` — but it has a broken import on line 30:

```python
from Production.tools.lib import credentials, directus
```

`Production/tools/lib/` does NOT exist in the tooling tree. The tooling tree's actual directory name is `Production/tools/credentials_lib/`. This is a stale import (likely a rename was applied to the directory but not to the consumer).

**Why this is silent today:** the import is masked by the lazy-import pattern in `tools/assets.py`. The MCP server boots, all 12 tools register successfully (the `mcp.tool(...)` decorator runs without ever triggering registered_write's module body), but the **first invocation** of `register_asset` or `find_asset` raises `ModuleNotFoundError: No module named 'Production.tools.lib'` from inside the function body. Per CLAUDE.md Rule 19 ("the app must work flawlessly at the end; do not leave any path open for error"), this is a structural fail-late hazard.

## §2 Six architectural decisions

The spawn prompt asked the spec to resolve six points. Resolutions below.

### §2.1 Where in tooling repo should `registered_write.py` live?

**Decision:** `Production/tools/registered_write.py` (already there; not moved).

The file already exists at the canonical path. No move needed.

### §2.2 Should `credentials_lib/` be COPIED or refactored to a single canonical location?

**Decision:** Neither — it already exists at `Production/tools/credentials_lib/` in tooling. Just fix `registered_write.py` to import from the correct directory name.

The tooling-mcp `credentials_lib/` is structurally cleaner than the Dropbox `credentials_lib/`:
- Tooling `__init__.py` exports the public API (`load_credentials`, `DirectusClient`, `DirectusError`, `parse_module_id`, `DirectusAdminClient`, `DirectusAdminError`)
- Tooling `directus_admin_client.py` uses Python relative imports (`from .credentials import ...`)
- Tooling `directus.py` uses correct module-qualified imports

The Dropbox version uses hardcoded paths and bare imports (older pattern). **Both versions coexist; this PR does not unify them.** See §4 FOLLOWUP-1.

### §2.3 Migration impact on existing DirectusAdminClient callsites

**Decision:** Zero impact. `Production.lib.directus_admin_client.DirectusAdminClient` (which the 88 callsites use) is at `Production/lib/directus_admin_client.py` and is not modified. The `credentials_lib/directus_admin_client.py` is a separate file used only by `registered_write.py` (the dual-lib situation pre-existing per `tools/assets.py` module docstring).

### §2.4 Backward-compat: shim or delete in Dropbox?

**Decision:** Both copies coexist (no Dropbox change). Standard LD-505 pattern. The Dropbox `registered_write.py` has a different (older) import pattern but works in its own context with its own `credentials_lib/`. The 28 Dropbox callsites remain functional in their own tree. Future PR can run a sync script.

### §2.5 Where do tests live?

**Decision:**
- `Production/mcp_servers/directus/tests/test_smoke.py` is updated:
  - Tightened `test_tool_inventory_has_all_expected_tools` to also assert `assert len(names) == 12` and `not extra` (no surprise tools)
  - Added new test `test_registered_write_module_importable_at_mcp_root()` that imports `Production.tools.registered_write` directly and verifies the public API surface — fail-loud regression guard
- No live Directus round-trip register_asset test in this PR (would pollute `prod_assets`; deferred per §4 FOLLOWUP-3)

### §2.6 LD impact

**Decision:** Lock new LD `MCP_REGISTERED_WRITE_MIGRATED_TO_TOOLING_V1` (severity HIGH) closing the LD-505 gap for this code unit. **No amendment to LD-505** — its statement of intent already covers `registered_write.py` as code; this fix realizes that intent.

## §3 Migration steps (the actual minimum-correct fix)

Five files changed. Diff totals: ~4 lines added in registered_write.py (1 substantive + comment), ~5 in server.py, ~10 in tools/assets.py, ~30 in test_smoke.py, ~140 new for this spec.

1. **Edit** `Production/tools/registered_write.py` line 30:
   - `from Production.tools.lib import credentials, directus` → `from Production.tools.credentials_lib import credentials, directus`
   - Add inline comment referencing this LD.
2. **Edit** `Production/mcp_servers/directus/server.py`:
   - After existing `sys.path.insert(0, str(_PRODUCTION_ROOT))`, add `sys.path.insert(0, str(_TOOLING_ROOT))` so the `Production` PEP 420 namespace package resolves for the eager import in `tools/assets.py`. (`_TOOLING_ROOT` was already computed but never inserted.)
3. **Edit** `Production/mcp_servers/directus/tools/assets.py`:
   - Add top-of-module imports: `from Production.tools.registered_write import register_asset as _reg, search as _search`
   - Remove the now-redundant lazy `from Production.tools.registered_write import ...` lines from inside `register_asset()` and `find_asset()` function bodies
   - Update module docstring to reflect that the imports are now eager (fail-fast at MCP boot, not fail-late at tool invocation)
4. **Edit** `Production/mcp_servers/directus/tests/test_smoke.py`:
   - Mirror the server.py sys.path setup: add `sys.path.insert(0, str(_TOOLING))` so pytest collection works
   - Tighten the existing tool-inventory test to assert `len(names) == 12` AND no extra tools (was: subset assertion only)
   - Add `test_registered_write_module_importable_at_mcp_root()` that imports `Production.tools.registered_write` directly + verifies public API + verifies `Production.tools.credentials_lib` submodules importable
5. **Verify** end-to-end:
   - py_compile clean across all 4 touched files ✓ (verified)
   - pytest 17 passed in 22.70s ✓ (was 16; +1 = the new importability test)
   - Live MCP boot smoke: `mcp.list_tools()` returns 12 tools including `register_asset` and `find_asset` ✓
6. **Commit + push** to `feature/directus-mcp-phase1-20260510` (no force-push, explicit file staging, no `-A` per cross_session_coord row 422 trap-prevention).

## §4 Out-of-scope follow-ups

These are explicitly NOT done in this PR. Surfaced for future work.

| ID | Follow-up | Trigger / motivation |
|----|-----------|---------|
| FOLLOWUP-1 | **Dual-lib unification.** Reconcile `Production.tools.credentials_lib.directus` with `Production.lib.directus` into a single canonical Directus client. Migrate `registered_write.py` to use `Production.lib.directus` and delete `credentials_lib/`. Three-way drift currently exists (tooling tools/credentials_lib/directus.py 21600b vs tooling lib/directus.py 28989b vs Dropbox tools/credentials_lib/directus.py 21612b). | Lib has PR #23 round-3 fixes credentials_lib lacks. Drift compounds over time. |
| FOLLOWUP-2 | **Auto-deploy Dropbox copy from tooling.** Script that copies `Production/tools/registered_write.py` + `Production/tools/credentials_lib/` from tooling-mcp into Dropbox on commit so the 28 Dropbox callsites stay current without manual sync. | Dropbox copy can drift from tooling copy if dev edits tooling and forgets to sync. |
| FOLLOWUP-3 | **Live register_asset round-trip test.** Add a Directus integration test that creates a real `prod_assets` row via tempfile + asserts schema validation + cleans up via PATCH (`prod_assets` is protected, no delete). | Coverage gap: today no test exercises the full register_asset code path through Directus. The new `test_registered_write_module_importable_at_mcp_root` proves the import chain only — not that Directus writes succeed. |
| FOLLOWUP-4 | **Standalone unit tests for registered_write.py.** Test SHA256 dedup, module_id validation, asset_type enum check, queue fallback path. | Currently zero unit-level test surface for the wrapper. |

## §5 Risk register + mitigation

| Risk | Severity | Mitigation |
|------|----------|------------|
| `git add -A` accidentally sweeps untracked Kling files (`Production/lib/rule_8_validator.py`, `Production/mcp_servers/wavespeed_kling/`) | HIGH (data loss / scope violation per cross_session_coord row 422) | Explicit-name `git add` only. Never `-A`, never `.`. Verified staged files via `git diff --cached --stat` before commit. |
| Force-push or branch divergence with `serene-ellis-dd314b`'s commits | HIGH (loses their PR #23 round-3 fixes) | `git pull --ff-only origin feature/directus-mcp-phase1-20260510` before push. Already up-to-date verified. |
| Eager import of `credentials_lib.credentials` at MCP boot fails on dev machines without Doppler creds | MEDIUM (MCP server won't start) | `credentials.py` lazy-loads creds on first call (verified by reading the module). Module-level imports do not trigger credential resolution. |
| Pytest test count increases by 1 (16 → 17), but other tests already pass the inventory check might mask a regression | LOW | New importability test is additive; existing 16 tests must still pass. Verified: `17 passed in 22.70s`. |
| Dropbox-tree edits accidentally land in commit | MEDIUM (DS-27 dual-canonical-roots violation) | All work in `~/Projects/mindfulnest-tooling-mcp/`. Zero edits to Dropbox files. Commit driver in tooling-mcp git. |
| Initial wrong-direction implementation (Dropbox-overwrite) regressed tooling-mcp's cleaner architecture | (RESOLVED) | Reverted via `git checkout HEAD -- Production/tools/registered_write.py Production/tools/credentials_lib/`. Per DS-19 deviation log: see §6 below. |

## §6 Deviation log (DS-19)

**Deviation:** Spawn prompt described the work as "move `Production/tools/registered_write.py` + dependency module... into the tooling repo." First-pass implementation took this literally, copying both from Dropbox. Investigation post-copy revealed the tooling tree already had cleaner versions of the same files (different code paths: tooling uses `Production.lib.paths.DROPBOX_ROOT`, Dropbox uses hardcoded platform-conditional paths). Overwriting the tooling versions with Dropbox versions would have been a regression.

**Resolution:** Reverted via `git checkout HEAD -- Production/tools/registered_write.py Production/tools/credentials_lib/` (clean revert; no commits had landed). Re-implemented as a 1-line bug fix to the existing tooling registered_write.py (`Production.tools.lib` → `Production.tools.credentials_lib`).

**Why the spawn prompt was incorrect:** the parent session likely inferred from the lazy-import pattern in `tools/assets.py` that registered_write.py was missing from tooling. In fact it was present but had a broken import. The lazy-import pattern was masking a separate bug. Both the parent's diagnosis (tools should be unconditionally registered) and the parent's prescription (eager import) were correct; only the prescribed implementation method (file copy) was unnecessary.

**Lesson logged for future autonomy work:** Before doing a "copy file X from tree A to tree B," verify tree B's actual current state. `find` + `ls -la` of the FULL target directory (not just the parent listing — which can truncate alphabetically) is the structural check. The truncated `ls` early in this session ended at "_option_c_prototype_exec" alphabetically and didn't reach `registered_write.py`, masking its presence.

## §7 Success criteria (from spawn prompt)

- [ ] `claude mcp list` from any worktree shows `directus: ✓ Connected` after merge — out of session scope; post-merge validation
- [x] `register_asset` and `find_asset` are unconditionally registered (test asserts `len(names) == 12` AND `not extra`)
- [x] All existing 88 DirectusAdminClient callsites still work (orthogonal — no `Production/lib/*` files touched)
- [x] Locked spec doc explains architectural decision (this doc, revised)
- [x] `prod_preflight_reviews` row exists (id=213)
- [x] `app_activity_log` completion row will exist (`spawn_20260510_registered_write_migration_complete` — written at end)
- [x] `prod_locked_decisions` LD will exist (`MCP_REGISTERED_WRITE_MIGRATED_TO_TOOLING_V1`)
- [x] Parent session can read the completion row (message-bus per autonomy default 4)

## §8 Confidence annotations (Rule 24)

- 5 tooling-mcp callsites of `registered_write.py` `[CONFIRMED against grep -rl output]`
- 28 Dropbox callsites including worktrees `[CONFIRMED against grep -rl output]`
- 88 DirectusAdminClient callsites figure `[GUESSED — from spawn prompt; not verified by me, but irrelevant since this fix is orthogonal to that surface]`
- Three-way directus.py drift `[CONFIRMED against ls -la output for all three files]`
- Eager-import works at MCP boot after server.py change `[CONFIRMED against live `mcp.list_tools()` smoke + 17/17 pytest pass]`
- Original tooling registered_write.py was broken `[CONFIRMED — pytest collection raised ModuleNotFoundError on `Production.tools.lib` after revert; before any of my edits]`
- LD-505 says canonical code in tooling `[INFERRED — LD-505 text not directly verified in this session]`
- serene-ellis-dd314b PR #23 round-3 commits already pushed `[CONFIRMED against `git log` showing HEAD == origin]`
- Untracked Kling files in worktree `[CONFIRMED against `git status --porcelain` output]`

## §9 Changelog

- 2026-05-10 v1 (initial draft): described the work as a Dropbox-copy migration. Authored before mid-flight discovery that tooling already had the file.
- 2026-05-10 v1 (revision after deviation): rewritten to reflect actual implementation as a 1-line bug fix + supporting changes. Added §0 title revision, §6 deviation log, updated §3 migration steps, updated §4 follow-ups (dropped FOLLOWUP-2's premise; kept dual-lib unification).
