"""Generic CRUD tools: directus_search, directus_get, directus_create.

All writes go through try_post_or_queue (LD-364 read-back-after-write).
prod_* writes additionally go through validate_payload (Rule 35).
"""

from __future__ import annotations

from typing import Any

from lib.directus import (
    DirectusReadError,
    DirectusWriteError,
    SilentWriteFailure,
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
            "mismatches": result.get("mismatches", []),
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
        if collection.startswith("prod_"):
            try:
                validated = validate_payload(collection, payload, mode="strict")
                payload = validated["payload"]
            except (UnknownPayloadKeyError, RetiredPayloadKeyError, SchemaProbeError) as e:
                return _validation_error_response(collection, e)
        try:
            result = try_post_or_queue(collection, payload)
            return _wrap_write_result(result)
        except SilentWriteFailure as e:
            return {
                "ok": False,
                "silent_write_failure": True,
                "collection": e.collection,
                "item_id": e.item_id,
                "mismatches": e.mismatches,
            }
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
            "Note: PATCH does NOT trigger the DS-21 Phase F browser-smoke gate "
            "currently (gate fires only on prod_activity_log _COMPLETE POSTs). If "
            "governance ever needs PATCH gating, surface as a Phase 2 spec amendment."
        ),
    )
    def directus_patch(collection: str, item_id: int, payload: dict) -> dict:
        if collection.startswith("prod_"):
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
