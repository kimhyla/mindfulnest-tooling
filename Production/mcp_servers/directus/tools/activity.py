"""log_activity tool — typed wrapper for prod_activity_log writes.

Validates payload against live /fields/prod_activity_log; writes via
try_post_or_queue (LD-364 read-back-after-write). Most-frequent write tool;
typed schema eliminates the 'wrong field name' silent-failure class that
caused the original Rule 35 incident (notes-vs-action 2026-04-29 row 1410).
"""

from __future__ import annotations

from typing import Any

from lib.directus import (
    DirectusReadError,
    DirectusWriteError,
    SilentWriteFailure,
    try_post_or_queue,
)
from lib.payload_validator import (
    RetiredPayloadKeyError,
    SchemaProbeError,
    UnknownPayloadKeyError,
    validate_payload,
)

from tools.crud import _validation_error_response, _wrap_write_result


def register(mcp: Any) -> None:
    @mcp.tool(
        name="log_activity",
        description=(
            "Append a row to prod_activity_log. Use for: phase progress, deviation "
            "logs (per CLAUDE.md §0.9), bug fixes, agent run summaries, schema "
            "drift findings, smoke-test outcomes.\n\n"
            "Key fields:\n"
            "- action (str, REQUIRED): short slug like MCP_PHASE_C_VERIFY or "
            "  SCHEMA_DRIFT_DETECTED\n"
            "- details (dict, optional): structured payload (JSON column)\n"
            "- performed_by (str, optional): default 'claude_code'\n"
            "- module_id (int, optional): foreign key when relevant\n"
            "- voice_settings / script_version / kim_verdict / kim_feedback / "
            "  asset_id (optional fields specific to production-pipeline rows)\n\n"
            "Variants: same as directus_create. NOTE: actions ending in _COMPLETE "
            "trigger the DS-21 Phase F browser-smoke gate (see lib.directus."
            "try_post_or_queue) which can return browser_smoke_missing variants."
        ),
    )
    def log_activity(
        action: str,
        details: dict | None = None,
        performed_by: str = "claude_code",
        module_id: int | None = None,
        voice_settings: dict | None = None,
        script_version: str | None = None,
        kim_verdict: str | None = None,
        kim_feedback: str | None = None,
        asset_id: int | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"action": action, "performed_by": performed_by}
        if details is not None:
            payload["details"] = details
        if module_id is not None:
            payload["module_id"] = module_id
        if voice_settings is not None:
            payload["voice_settings"] = voice_settings
        if script_version is not None:
            payload["script_version"] = script_version
        if kim_verdict is not None:
            payload["kim_verdict"] = kim_verdict
        if kim_feedback is not None:
            payload["kim_feedback"] = kim_feedback
        if asset_id is not None:
            payload["asset_id"] = asset_id

        try:
            validated = validate_payload("prod_activity_log", payload, mode="strict")
            payload = validated["payload"]
        except (UnknownPayloadKeyError, RetiredPayloadKeyError, SchemaProbeError) as e:
            return _validation_error_response("prod_activity_log", e)

        try:
            result = try_post_or_queue("prod_activity_log", payload)
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
