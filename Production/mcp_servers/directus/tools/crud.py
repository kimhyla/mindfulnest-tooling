"""Generic CRUD tools: directus_search, directus_get, directus_create,
directus_patch, directus_delete.

All writes go through try_post_or_queue / try_patch_or_queue
(LD-364 read-back-after-write). prod_* writes additionally go through
validate_payload (Rule 35).

directus_delete is GATED behind:
- env var MN_MCP_ALLOW_DESTRUCTIVE=1 (must be explicit)
- a per-collection allowlist that EXCLUDES prod_locked_decisions, prod_assets,
  app_*, coppa_* (those are governance/audit/compliance — never auto-deleted)
- confirm_destructive=True flag in the call

Per Cursor cross-review finding 6B + CLAUDE.md "Destructive db operations"
prohibition (per-action explicit Kim authorization required).
"""

from __future__ import annotations

import os
from typing import Any

from lib.directus import (
    DirectusReadError,
    DirectusWriteError,
    try_patch_or_queue,
    try_post_or_queue,
)
from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError
from lib.payload_validator import (
    RetiredPayloadKeyError,
    SchemaProbeError,
    UnknownPayloadKeyError,
    validate_payload,
)


def _coerce_for_mcp_result(obj: Any, _depth: int = 0) -> Any:
    """Make arbitrary nested objects safe for FastMCP/Pydantic result serialization.

    Per Cursor finding 3B: silent_write_failure.mismatches contains arbitrary
    Python types (datetime, sets, custom dataclasses, raw JSON-decoded blobs)
    in the sent/got fields. FastMCP-3.x serializes via Pydantic; arbitrary
    objects fail validation. Coerce to str/repr safely.
    """
    if _depth > 10:  # depth limit guard against pathological cycles
        return repr(obj)[:200]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_coerce_for_mcp_result(x, _depth + 1) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _coerce_for_mcp_result(v, _depth + 1) for k, v in obj.items()}
    return repr(obj)[:500]


def _wrap_write_result(result: Any) -> dict:
    """Convert try_post_or_queue's return shape into structured tool result variants.

    try_post_or_queue can return:
    - A successful row dict (has 'id', no sentinel keys)
    - {queued: True, path: ...} on offline
    - {queued: False, silent_write_failure: True, item_id, mismatches, error}
    - {queued: False, browser_smoke_missing|browser_smoke_gate_unverifiable: True, ...}
    """
    if not isinstance(result, dict):
        return {"unexpected_result_shape": True, "raw": repr(result)[:500], "ok": False}
    if result.get("queued") is True:
        return {"queued": True, "path": result.get("path"), "ok": False}
    if result.get("silent_write_failure"):
        return {
            "ok": False,
            "silent_write_failure": True,
            "item_id": result.get("item_id"),
            "mismatches": _coerce_for_mcp_result(result.get("mismatches", [])),
            "error": result.get("error"),
        }
    if result.get("browser_smoke_missing"):
        return {
            "browser_smoke_missing": True,
            "phase_key": result.get("phase_key"),
            "error": result.get("error"),
            "ok": False,
        }
    if result.get("browser_smoke_gate_unverifiable"):
        return {
            "browser_smoke_gate_unverifiable": True,
            "phase_key": result.get("phase_key"),
            "error": result.get("error"),
            "ok": False,
        }
    # Successful row
    return {"ok": True, "row": result, "id": result.get("id")}


def _validation_error_response(coll: str, exc: Exception) -> dict:
    if isinstance(exc, UnknownPayloadKeyError):
        return {
            "validation_error": True,
            "kind": "unknown_keys",
            "collection": coll,
            "unknown_keys": exc.keys,
            "ok": False,
        }
    if isinstance(exc, RetiredPayloadKeyError):
        return {
            "validation_error": True,
            "kind": "retired_key",
            "collection": coll,
            "field": exc.field,
            "retire_date": exc.retire_date,
            "ok": False,
        }
    if isinstance(exc, SchemaProbeError):
        return {
            "schema_unavailable": True,
            "collection": coll,
            "error": str(exc),
            "ok": False,
        }
    return {"validation_error": True, "kind": "unknown", "error": str(exc), "ok": False}


def register(mcp: Any) -> None:
    """Register CRUD tools onto the FastMCP instance."""

    @mcp.tool(
        name="directus_search",
        description=(
            "Search rows in any Directus collection (prod_*, app_*, coppa_*). "
            "Read-only. Filters use Directus filter syntax e.g. {'id': {'_eq': 42}}. "
            "Returns up to 100 rows; default 25."
        ),
    )
    def directus_search(
        collection: str,
        filters: dict | None = None,
        fields: list[str] | None = None,
        sort: str | None = None,
        limit: int = 25,
    ) -> dict:
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 1
        try:
            client = DirectusAdminClient()
            rows = client.get_items(
                collection,
                filters=filters,
                fields=fields,
                sort=sort,
                limit=limit,
            )
            return {"ok": True, "rows": rows, "count": len(rows)}
        except DirectusAdminError as e:
            return {
                "ok": False,
                "directus_error": True,
                "status": e.status,
                "body": e.body[:500],
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}

    @mcp.tool(
        name="directus_get",
        description=(
            "Fetch a single row by id from any Directus collection. Read-only. "
            "Returns {ok: true, row: {...}} on success or {ok: false, not_found: true} "
            "on 404."
        ),
    )
    def directus_get(
        collection: str,
        item_id: int,
        fields: list[str] | None = None,
    ) -> dict:
        try:
            client = DirectusAdminClient()
            row = client.get_item(collection, item_id, fields=fields)
            if row is None:
                return {"ok": False, "not_found": True}
            return {"ok": True, "row": row}
        except DirectusAdminError as e:
            if e.status == 404 or e.status == 403:
                # Directus 403 on missing row is also "not found" (permission filter).
                return {"ok": False, "not_found": True, "status": e.status}
            return {
                "ok": False,
                "directus_error": True,
                "status": e.status,
                "body": e.body[:500],
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}

    @mcp.tool(
        name="directus_create",
        description=(
            "Create a row in any Directus collection. For prod_* collections, payload "
            "is schema-validated against live /fields with 15-min cache (rejects unknown "
            "field names, retired fields, payloads exceeding override caps). All writes "
            "use read-back-after-write per LD-364. On any write failure returns a "
            "structured variant — NEVER silent success.\n\n"
            "Variants: {ok: true, row, id} | {ok: false, queued, path} | "
            "{ok: false, validation_error, unknown_keys|retired_key} | "
            "{ok: false, silent_write_failure, mismatches} | "
            "{ok: false, directus_error, status, body} | "
            "{ok: false, browser_smoke_missing, ...} (for prod_activity_log "
            "*_COMPLETE actions per DS-21)."
        ),
    )
    def directus_create(collection: str, payload: dict) -> dict:
        if (
            collection.startswith("prod_")
            or collection.startswith("app_")
            or collection.startswith("coppa_")
        ):
            try:
                validated = validate_payload(collection, payload, mode="strict")
                payload = validated["payload"]
            except (UnknownPayloadKeyError, RetiredPayloadKeyError, SchemaProbeError) as e:
                return _validation_error_response(collection, e)
        try:
            result = try_post_or_queue(collection, payload)
            return _wrap_write_result(result)
        except (DirectusWriteError, DirectusReadError) as e:
            return {
                "ok": False,
                "directus_error": True,
                "msg": f"{type(e).__name__}: {e}",
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}

    @mcp.tool(
        name="directus_patch",
        description=(
            "Update fields on an existing row in any Directus collection. For prod_* "
            "collections, payload is schema-validated against live /fields. All writes "
            "use read-back-after-write per LD-364 (via try_patch_or_queue). On any "
            "failure returns a structured variant — NEVER silent success.\n\n"
            "Variants: same as directus_create. Use this for: closing blockers "
            "(is_resolved=True), superseding LDs (status='superseded'), updating "
            "asset records, or any field-level update on existing rows.\n\n"
            "Note: PATCH does not trigger the DS-21 Phase F browser-smoke gate; "
            "the gate fires only on prod_activity_log _COMPLETE POSTs. Extending "
            "gate coverage to PATCH would require a separate spec amendment."
        ),
    )
    def directus_patch(collection: str, item_id: int, payload: dict) -> dict:
        if (
            collection.startswith("prod_")
            or collection.startswith("app_")
            or collection.startswith("coppa_")
        ):
            try:
                validated = validate_payload(collection, payload, mode="strict")
                payload = validated["payload"]
            except (UnknownPayloadKeyError, RetiredPayloadKeyError, SchemaProbeError) as e:
                return _validation_error_response(collection, e)
        try:
            result = try_patch_or_queue(collection, item_id, payload)
            return _wrap_write_result(result)
        except (DirectusWriteError, DirectusReadError) as e:
            return {
                "ok": False,
                "directus_error": True,
                "msg": f"{type(e).__name__}: {e}",
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}

    @mcp.tool(
        name="directus_delete",
        description=(
            "DESTRUCTIVE — delete a row by id. Triple-gated:\n"
            "1. env var MN_MCP_ALLOW_DESTRUCTIVE=1 must be set\n"
            "2. confirm_destructive=True must be passed\n"
            "3. collection must NOT be in the protected list "
            "(prod_locked_decisions, prod_assets, prod_visual_assets, "
            "prod_audio_assets, prod_reference_docs, prod_modules, app_*, "
            "coppa_*)\n\n"
            "Per CLAUDE.md prohibitions list 'Destructive db operations' + "
            "Cursor cross-review finding 6B. For protected collections, use "
            "directus_patch to mark status='superseded' / is_current=false / "
            "is_resolved=true instead. Audit-trail rows should not be deleted; "
            "they are append-only by governance design.\n\n"
            "Variants: {ok: true, deleted: true, collection, item_id} | "
            "{ok: false, gate_failed: 'env_var'|'confirm'|'protected_collection', "
            "msg}."
        ),
    )
    def directus_delete(collection: str, item_id: int, confirm_destructive: bool = False) -> dict:
        protected = {
            "prod_locked_decisions",
            "prod_assets",
            "prod_visual_assets",
            "prod_audio_assets",
            "prod_reference_docs",
            "prod_modules",
            "prod_activity_log",
            "prod_preflight_reviews",
        }
        if collection in protected or collection.startswith("app_") or collection.startswith("coppa_"):
            return {
                "ok": False,
                "gate_failed": "protected_collection",
                "msg": (
                    f"Collection {collection!r} is protected from automated "
                    f"deletion. Use directus_patch to mark superseded / "
                    f"is_current=false / is_resolved=true instead. "
                    f"Audit-trail rows are append-only by governance design."
                ),
            }
        if os.environ.get("MN_MCP_ALLOW_DESTRUCTIVE") != "1":
            return {
                "ok": False,
                "gate_failed": "env_var",
                "msg": (
                    "MN_MCP_ALLOW_DESTRUCTIVE=1 not set in MCP server env. "
                    "Per CLAUDE.md prohibitions list, destructive operations "
                    "require per-action explicit Kim authorization. Set the "
                    "env var in the MCP launch config (Doppler or "
                    "claude_desktop_config) only when explicitly authorized."
                ),
            }
        if not confirm_destructive:
            return {
                "ok": False,
                "gate_failed": "confirm",
                "msg": "confirm_destructive=True required.",
            }
        try:
            client = DirectusAdminClient()
            client.delete_item(collection, item_id)
            return {"ok": True, "deleted": True, "collection": collection, "item_id": item_id}
        except DirectusAdminError as e:
            return {
                "ok": False,
                "directus_error": True,
                "status": e.status,
                "body": e.body[:500],
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}
