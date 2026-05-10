"""Schema introspection tool: schema_describe.

Read-only. Wraps DirectusAdminClient.fields() and returns formatted field
metadata for any collection. Reuses the validator's 15-min schema cache.
"""

from __future__ import annotations

from typing import Any

from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError


def register(mcp: Any) -> None:
    @mcp.tool(
        name="directus_invalidate_schema",
        description=(
            "Force-flush the schema cache for one collection (or all). Useful "
            "when Kim has just added a Directus field via the admin UI and "
            "the MCP server's 15-min TTL hasn't expired yet. Read-only on "
            "Directus side; only mutates the in-memory cache.\n\n"
            "Args:\n"
            "- collection (str, optional): if omitted, flushes all cached "
            "  collections.\n\n"
            "Returns: {ok: true, flushed: 'all' | <collection>, "
            "remaining_cached: list[str]}."
        ),
    )
    def directus_invalidate_schema(collection: str | None = None) -> dict:
        try:
            from lib.payload_validator import (
                _SCHEMA_CACHE,  # noqa: SLF001
                invalidate_schema_cache,
            )
            before = list(_SCHEMA_CACHE.keys())
            invalidate_schema_cache(collection)
            after = list(_SCHEMA_CACHE.keys())
            return {
                "ok": True,
                "flushed": collection or "all",
                "before_cached": before,
                "remaining_cached": after,
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}

    @mcp.tool(
        name="schema_describe",
        description=(
            "Describe the field schema for a Directus collection. Read-only. Returns "
            "{collection, field_count, fields: [{name, type, required, is_primary_key, "
            "interface, options}]}. Use this BEFORE composing payloads for "
            "directus_create / log_activity / lock_decision / directus_patch to "
            "verify field names against live schema (per CLAUDE.md Rule 35)."
        ),
    )
    def schema_describe(collection: str) -> dict:
        try:
            client = DirectusAdminClient()
            raw_fields = client.fields(collection)
            simplified = []
            for f in raw_fields:
                schema = f.get("schema") or {}
                meta = f.get("meta") or {}
                simplified.append(
                    {
                        "name": f.get("field"),
                        "type": f.get("type"),
                        "is_primary_key": bool(schema.get("is_primary_key")),
                        "is_nullable": bool(schema.get("is_nullable", True)),
                        "required": bool(meta.get("required") or not schema.get("is_nullable", True)),
                        "interface": meta.get("interface"),
                        "default_value": schema.get("default_value"),
                        "options": meta.get("options"),
                    }
                )
            return {
                "ok": True,
                "collection": collection,
                "field_count": len(simplified),
                "fields": simplified,
            }
        except DirectusAdminError as e:
            return {
                "ok": False,
                "directus_error": True,
                "status": e.status,
                "body": e.body[:500],
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "internal_error": True,
                "msg": f"{type(e).__name__}: {e}",
            }
