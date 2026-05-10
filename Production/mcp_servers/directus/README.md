# MindfulNest Directus MCP Server

Schema-validated MCP server that exposes 12 tools for read/write access to MindfulNest's Directus instance. Runs as local stdio; FastMCP's remote-HTTP transport is supported by the framework but not enabled in this deployment.

Spec: `Production/docs/V59_DIRECTUS_MCP_SERVER_SPEC_v1.md` (Dropbox tree)
LDs: `DIRECTUS_MCP_SERVER_PHASE1_V1` (660), `DIRECTUS_MCP_SERVER_PHASE2_V1` (663)
prod_reference_docs id: 207

---

## Why this exists

Eliminates the Rule 35 "silent-write-failure" class STRUCTURALLY. Wrong field names → schema rejection at the MCP tool boundary, not silent_write_failure visible only after `try_post_or_queue` read-back. Writes go through `validate_payload` (live `/fields/<collection>` cache) + `try_post_or_queue` (LD-364 read-back-after-write). Same offline queue (`pending_directus_writes.json`) and Phase F browser-smoke gate (DS-21) as the existing 88 callsite path.

## Tools

| Tool | Read/write | Purpose |
|---|---|---|
| `directus_search` | read | Filtered query against any collection. |
| `directus_get` | read | Fetch by id. |
| `schema_describe` | read | Live `/fields/<coll>` introspection (with 15-min cache). |
| `directus_invalidate_schema` | read | Flush the in-process schema cache; next call re-fetches `/fields`. |
| `find_asset` | read | Lookup helper for `prod_assets`. |
| `log_activity` | write | Typed wrapper for `prod_activity_log`. |
| `lock_decision` | write | Upsert by `decision_key` for `prod_locked_decisions`. |
| `directus_create` | write | Generic create for any collection (prod_*/app_*/coppa_*). |
| `directus_patch` | write | Generic update by id, schema-validated. |
| `directus_delete` | write | Generic delete; gated by an explicit destructive-auth flag. |
| `register_asset` | write | Typed wrapper for `prod_assets`. |
| `preflight_review` | write | Typed wrapper for `prod_preflight_reviews`. |

All write tools return structured variants:
- `{ok: true, row, id}` on success
- `{ok: false, validation_error: true, unknown_keys}` on schema rejection
- `{ok: false, silent_write_failure: true, mismatches}` on read-back drift
- `{ok: false, queued: true, path}` on offline (queue replays at next session)
- `{ok: false, browser_smoke_missing}` on DS-21 gate fire

## Install (macOS)

```bash
cd ~/Projects/mindfulnest-tooling/Production/mcp_servers/directus
./install/install_macos.sh
```

The script:
1. Installs Python 3.12 via pyenv if missing
2. Creates venv + installs `fastmcp` + `pydantic`
3. Wires up Claude Code via `claude mcp add directus -- doppler run -- ...`
4. Prints the Claude Desktop config snippet for `~/Library/Application Support/Claude/claude_desktop_config.json`

## Install (Windows)

```powershell
cd ~\Projects\mindfulnest-tooling\Production\mcp_servers\directus
./install/install_windows.ps1
```

(Untested on Windows as of 2026-05-10; verify on first run.)

## Run manually

```bash
.venv/bin/python server.py        # local stdio, expects MCP client (Claude Code/Desktop) to spawn it
```

## Architecture

```
┌─────────────────────┐    ┌──────────────────────┐    ┌─────────────────────────┐
│ Claude Code/Desktop │───▶│ FastMCP stdio server │───▶│ tools/{crud,activity,...}│
│ cursor-agent (TBD)  │    │ server.py            │    │ @mcp.tool decorators    │
└─────────────────────┘    └──────────────────────┘    └────────────┬────────────┘
                                                                    │
                                                                    ▼
                                            ┌──────────────────────────────────────┐
                                            │ Production/lib/                      │
                                            │  - payload_validator.validate_payload│
                                            │  - directus.try_post_or_queue        │
                                            │  - directus_admin_client             │
                                            └──────────────────────────────────────┘
```

The MCP server is glue. It does NOT re-implement schema validation, read-back, or auth. It composes the existing 88-callsite-tested infrastructure behind a tool-contract boundary that's harder to bypass.

## Coexistence

- 88 callsites of `directus_admin_client` keep working unchanged.
- 88 callsites of `try_post_or_queue` keep working unchanged.
- The MCP server is ADDITIVE; you can use it from Claude tool calls OR call the lib directly from any Python script. Both routes share the same offline queue, same read-back semantics, same Phase F gate.

## INVARIANTS (Rule 36)

- All writes go through `try_post_or_queue` or `try_patch_or_queue` (LD-364 read-back-after-write).
- All `prod_*` writes go through `validate_payload` (Rule 35 schema validation).
- Schema cache TTL = 15 min (mirrors `lib.payload_validator._SCHEMA_TTL_SEC`); `directus_invalidate_schema` flushes without restart.
- `prod_locked_decisions.date_locked` is type=date, NOT datetime — `lock_decision` tool sends date-only ISO format.
- Server runs as local stdio. FastMCP supports remote-HTTP transport but this deployment doesn't enable it; cursor-agent sandbox compatibility with bearer-auth HTTPS endpoints would gate any future move to remote.
- `lib.directus.queue_write_offline` holds an `fcntl.flock` on `pending_directus_writes.json`; the 20-parallel-writer regression test in `tests/test_concurrent_offline_queue.py` validates concurrent-writer safety.

## Smoke evidence (2026-05-10)

Live Directus probes from `.venv/bin/python` against production Directus:

- B.1 ✓ — `mcp.list_tools()` returns 6 tools.
- B.2 ✓ — `directus_search('prod_locked_decisions', filters={'decision_key': {'_eq':'POST_ITEM_VERIFIED_V1'}})` returns LD-364 row.
- B.3 ✓ — `directus_get('prod_locked_decisions', 364)` returns same row.
- B.4 ✓ — `schema_describe('prod_activity_log')` returns 11 fields including `action`, `details`, `performed_by`.
- B.5 ✓ — `directus_get('prod_activity_log', 99999999)` returns `{ok: false, not_found: true}`.
- C.1 ✓ — `directus_create('prod_activity_log', {action, notes:'...', ...})` returns `{validation_error: true, unknown_keys: ['notes']}`. **The Rule 35 silent-write-failure class is now structurally caught at the tool boundary.**
- C.2 ✓ — `log_activity` positive write created prod_activity_log id=2275; verified via directus_get.
- C.4 ✓ — `lock_decision` UPSERT: first call creates (id=658), second call patches the same row (`upserted: 'patched'`).
- C.5 ✓ — Sentinel id=658 cleaned up to status=superseded, is_current=false.
- C.6 ✓ — `directus_create('prod_blockers', {bogus_field: '...'})` rejected with `{validation_error: true, unknown_keys: ['bogus_field']}`.

## Operational notes

- **Schema-cache TTL is 15 min.** When a Directus field is added, worst-case lag before the MCP picks it up is 15 min. Use `directus_invalidate_schema` for an instant flush, or restart the server.
- **Cursor-agent sandbox + remote HTTPS.** Whether cursor-agent's sandbox reaches a public HTTPS endpoint with a bearer header is an empirical question that hasn't been exercised yet; the answer would govern any future move from local stdio to remote transport. Recorded as an open investigation, not a limitation of the current deployment.
- **Platform support.** macOS install (`install_macos.sh`) is exercised. Windows install (`install_windows.ps1`) ships alongside it but has not yet been run on a Windows machine; first invocation on the work PC is the validation step. The `project_directus_mcp_windows_install_pending.md` user-memory file fires a reminder when that machine transition is detected.
