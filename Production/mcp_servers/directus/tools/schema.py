"""Schema introspection tool: schema_describe.

Read-only. Wraps DirectusAdminClient.fields() and returns formatted field
metadata for any collection. Reuses the validator's 15-min schema cache.
"""

from __future__ import annotations

from typing import Any

from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError


def register(mcp: Any) -> None:
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
