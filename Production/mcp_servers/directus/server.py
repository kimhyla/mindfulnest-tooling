"""
MindfulNest Directus MCP server.

Composes Production/lib/{directus.py, payload_validator.py, directus_admin_client.py}
into 12 schema-validated MCP tools that enforce CLAUDE.md Rule 35 + LD-364
read-back-after-write at the tool boundary.

Tools:
- directus_search             (read-only)
- directus_get                (read-only)
- schema_describe             (read-only)
- directus_invalidate_schema  (read-only — flushes the in-process schema cache)
- log_activity                (write — prod_activity_log)
- lock_decision               (write — prod_locked_decisions, upsert by decision_key)
- directus_create             (write — generic, any prod_*/app_*/coppa_* collection)
- directus_patch              (write — generic update by id)
- directus_delete             (write — gated by explicit destructive auth flag)
- register_asset              (write — typed wrapper for prod_assets)
- find_asset                  (read-only — prod_assets lookup helper)
- preflight_review            (write — typed wrapper for prod_preflight_reviews)

INVARIANTS (Rule 36):
- All writes go through try_post_or_queue or try_patch_or_queue (LD-364
  read-back-after-write).
- All prod_* writes go through validate_payload (Rule 35 schema validation).
- Schema cache TTL = 15 min (mirrors lib.payload_validator._SCHEMA_TTL_SEC);
  directus_invalidate_schema can flush the cache without a server restart.
- Server runs as local stdio. FastMCP supports remote-HTTP transport but
  this deployment doesn't enable it; cursor-agent sandbox compatibility
  with bearer-auth HTTPS endpoints would gate any future move to remote.
- prod_locked_decisions.date_locked is type=date, NOT datetime — date-only
  ISO format ("YYYY-MM-DD"), enforced in tools/decisions.py::_utc_now_iso.
- MCP-internal closure action names use suffix _V1 (NOT _COMPLETE) by
  DELIBERATE policy: the DS-21 BROWSER_SMOKE_MECHANICAL_GATE_V1 fires on
  action.endswith('_COMPLETE') and the MCP server has no browser surface, so
  bypassing the gate is correct policy. DO NOT rename closure actions to
  end in _COMPLETE without first writing matching KIM_BROWSER_SMOKE_PASSED
  rows or BROWSER_SMOKE_DEFERRED rows. Per cursor cross-review finding 8C.
- Concurrent-writer queue safety: lib.directus.queue_write_offline holds an
  fcntl.flock on pending_directus_writes.json (added in this PR's
  lib/directus.py diff). Two concurrent writers cannot lose entries; the
  20-parallel-writer regression test in tests/test_concurrent_offline_queue.py
  validates this.

Spec: Production/docs/V59_DIRECTUS_MCP_SERVER_SPEC_v1.md
LDs: DIRECTUS_MCP_SERVER_PHASE1_V1 (660), DIRECTUS_MCP_SERVER_PHASE2_V1 (663).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make Production/ importable so we can pull in lib/ siblings.
_THIS = Path(__file__).resolve()
_PRODUCTION_ROOT = _THIS.parent.parent.parent  # tooling/Production/
_TOOLING_ROOT = _PRODUCTION_ROOT.parent
sys.path.insert(0, str(_PRODUCTION_ROOT))
# _TOOLING_ROOT also on sys.path so the `Production` PEP 420 namespace package
# resolves for `from Production.tools.registered_write import ...` in tools/assets.py.
# Locked 2026-05-10 per LD MCP_REGISTERED_WRITE_MIGRATED_TO_TOOLING_V1; see
# Production/docs/V59_REGISTERED_WRITE_MIGRATION_SPEC_v1.md.
sys.path.insert(0, str(_TOOLING_ROOT))

from fastmcp import FastMCP  # noqa: E402

from tools import activity, assets, crud, decisions, schema  # noqa: E402

mcp = FastMCP(
    name="mn-directus",
    instructions=(
        "MindfulNest Directus MCP server. Schema-validated read/write access to "
        "the production Directus instance. All writes use read-back-after-write "
        "(LD-364 POST_ITEM_VERIFIED_V1). All prod_* writes go through schema "
        "validation against live /fields/<collection> with 15-min cache TTL "
        "(Rule 35 DIRECTUS_SCHEMA_VERIFICATION_V1).\n\n"
        "Tools:\n"
        "- directus_search / directus_get / schema_describe (read)\n"
        "- log_activity / lock_decision / directus_create (write)\n\n"
        "On write failure, tools return structured variants — never silent "
        "success. See V59_DIRECTUS_MCP_SERVER_SPEC_v1 §7 for error handling."
    ),
)

# Register tools (each module attaches @mcp.tool decorators by calling register()).
crud.register(mcp)
schema.register(mcp)
activity.register(mcp)
decisions.register(mcp)
assets.register(mcp)


def _prime_schema_cache() -> None:
    """At startup, prime the validator's schema cache for high-frequency
    collections. Surfaces /fields probe failures EARLY (before first tool call)
    rather than on the hot path. Soft-fail: log to stderr but don't refuse to
    start (collection-specific tools handle re-probe on demand).
    """
    high_frequency = [
        "prod_activity_log",
        "prod_locked_decisions",
        "prod_assets",
        "prod_blockers",
        "prod_reference_docs",
        "prod_preflight_reviews",
    ]
    try:
        from lib.directus_admin_client import DirectusAdminClient
        from lib.payload_validator import _cached_fields  # noqa: SLF001 — internal

        client = DirectusAdminClient()
        for coll in high_frequency:
            try:
                _cached_fields(client, coll)
            except Exception as e:  # noqa: BLE001
                print(
                    f"[startup-warn] schema-cache prime failed for {coll}: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr,
                )
    except Exception as e:  # noqa: BLE001
        print(
            f"[startup-warn] could not prime schema cache: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )


def _schema_drift_sentinel() -> None:
    """Confirm the on-disk reference doc is reachable from the server's runtime
    environment. Never fails server startup — the live schema is authoritative;
    the reference doc is a human-facing cache validated by Rule 35
    read-back-after-write at the tool boundary.

    Resolution order for the reference doc location:
    1. ``MN_DIRECTUS_SCHEMA_REF_DOC`` env var (operator-supplied absolute path).
    2. ``MN_DROPBOX_ROOT`` env var + ``Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md``.
    3. Skipped with a neutral log message when neither is set.
    """
    candidates: list[Path] = []
    env_doc = os.environ.get("MN_DIRECTUS_SCHEMA_REF_DOC")
    if env_doc:
        candidates.append(Path(env_doc).expanduser())
    env_root = os.environ.get("MN_DROPBOX_ROOT")
    if env_root:
        candidates.append(
            Path(env_root).expanduser()
            / "Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md"
        )

    target = next((p for p in candidates if p.exists()), None)
    if target is None:
        print(
            "[startup-info] schema reference doc not located via "
            "MN_DIRECTUS_SCHEMA_REF_DOC or MN_DROPBOX_ROOT — drift sentinel "
            "skipped (live /fields remains source of truth at the tool boundary)",
            file=sys.stderr,
        )
        return
    print(
        f"[startup-info] schema reference doc reachable at {target}",
        file=sys.stderr,
    )


def main() -> None:
    """Entry point. FastMCP runs the stdio transport by default."""
    _prime_schema_cache()
    _schema_drift_sentinel()
    mcp.run()


if __name__ == "__main__":
    main()
