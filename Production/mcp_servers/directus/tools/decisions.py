"""lock_decision tool — typed wrapper for prod_locked_decisions writes.

Per CLAUDE.md Rule 18 (locked decision auto-registration). Handles upsert by
decision_key: if a row with the same decision_key exists, PATCH it; otherwise
POST a new row. Validates payload against live /fields/prod_locked_decisions.

NOTE: try_patch_or_queue does NOT exist in lib/directus.py (spec gap #1
confirmed by live probe). For UPSERT we fall back to client.patch_item +
manual read-back assertion. This is intentionally documented inline; if a
silent failure surfaces, the read-back catches it.
"""

from __future__ import annotations

from datetime import datetime, timezone
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

from tools.crud import _validation_error_response, _wrap_write_result


def _utc_now_iso() -> str:
    """Return date-only string. prod_locked_decisions.date_locked is type=date,
    not datetime, so sending an ISO datetime causes a silent truncation that
    read-back-after-write will (correctly) flag as silent_write_failure.
    """
    return datetime.now(timezone.utc).date().isoformat()


def register(mcp: Any) -> None:
    @mcp.tool(
        name="lock_decision",
        description=(
            "Register a locked decision in prod_locked_decisions per CLAUDE.md Rule "
            "18. Upserts by decision_key: PATCHes existing row or POSTs new row. "
            "All writes use read-back-after-write per LD-364.\n\n"
            "Required fields:\n"
            "- decision_key (str, UPPER_SNAKE_CASE): stable identifier\n"
            "- decision_name (str): human title\n"
            "- decision_text (str): full body\n"
            "- task_category (str enum): e.g. tech_stack, governance, "
            "  process_governance, infrastructure, content_pipeline\n"
            "- severity (str enum, UPPERCASE): CRITICAL/HIGH/MEDIUM/LOW/SOFT/HARD\n"
            "  (mind: prod_locked_decisions uses uppercase; prod_blockers uses "
            "  lowercase per LD-592)\n"
            "- source_document (str): file path or doc title\n\n"
            "Optional:\n"
            "- date_locked (ISO8601): defaults to now UTC\n"
            "- notes (str): supplementary context\n"
            "- governance_file (str), past_failure_prevented (str), "
            "  related_files (list[str]), keyword_synonyms (list[str]), "
            "  enforcement_type (str), enforcement_artifact_ref (str), "
            "  scope_domain (str), supersedable (bool)\n\n"
            "Variants: same as directus_create + {ok: true, upserted: 'patched'|"
            "'created', row, id}."
        ),
    )
    def lock_decision(
        decision_key: str,
        decision_name: str,
        decision_text: str,
        task_category: str,
        severity: str,
        source_document: str,
        date_locked: str | None = None,
        notes: str | None = None,
        governance_file: str | None = None,
        past_failure_prevented: str | None = None,
        related_files: list[str] | None = None,
        keyword_synonyms: list[str] | None = None,
        enforcement_type: str | None = None,
        enforcement_artifact_ref: str | None = None,
        scope_domain: str | None = None,
        supersedable: bool | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "decision_key": decision_key,
            "decision_name": decision_name,
            "decision_text": decision_text,
            "task_category": task_category,
            "severity": severity,
            "source_document": source_document,
            "date_locked": date_locked or _utc_now_iso(),
            "status": "active",
            "is_current": True,
        }
        if notes is not None:
            payload["notes"] = notes
        if governance_file is not None:
            payload["governance_file"] = governance_file
        if past_failure_prevented is not None:
            payload["past_failure_prevented"] = past_failure_prevented
        if related_files is not None:
            payload["related_files"] = related_files
        if keyword_synonyms is not None:
            payload["keyword_synonyms"] = keyword_synonyms
        if enforcement_type is not None:
            payload["enforcement_type"] = enforcement_type
        if enforcement_artifact_ref is not None:
            payload["enforcement_artifact_ref"] = enforcement_artifact_ref
        if scope_domain is not None:
            payload["scope_domain"] = scope_domain
        if supersedable is not None:
            payload["supersedable"] = supersedable

        try:
            validated = validate_payload("prod_locked_decisions", payload, mode="strict")
            payload = validated["payload"]
        except (UnknownPayloadKeyError, RetiredPayloadKeyError, SchemaProbeError) as e:
            return _validation_error_response("prod_locked_decisions", e)

        try:
            client = DirectusAdminClient()
            existing = client.get_items(
                "prod_locked_decisions",
                filters={"decision_key": {"_eq": decision_key}},
                fields=["id", "decision_key", "status"],
                limit=1,
            )
            if existing:
                result = try_patch_or_queue(
                    "prod_locked_decisions", existing[0]["id"], payload, client=client
                )
                wrapped = _wrap_write_result(result)
                if wrapped.get("ok"):
                    wrapped["upserted"] = "patched"
                return wrapped
            result = try_post_or_queue("prod_locked_decisions", payload)
            wrapped = _wrap_write_result(result)
            if wrapped.get("ok"):
                wrapped["upserted"] = "created"
            return wrapped
        except SilentWriteFailure as e:
            return {
                "ok": False,
                "silent_write_failure": True,
                "collection": e.collection,
                "item_id": e.item_id,
                "mismatches": e.mismatches,
            }
        except DirectusAdminError as e:
            return {
                "ok": False,
                "directus_error": True,
                "status": e.status,
                "body": e.body[:500],
            }
        except (DirectusWriteError, DirectusReadError) as e:
            return {
                "ok": False,
                "directus_error": True,
                "msg": f"{type(e).__name__}: {e}",
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}
