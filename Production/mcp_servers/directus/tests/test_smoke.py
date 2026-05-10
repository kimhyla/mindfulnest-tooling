"""End-to-end smoke tests for the Directus MCP server.

Run from server dir with venv active:
    .venv/bin/python -m pytest tests/ -v

These hit LIVE Directus. Requires DIRECTUS_ADMIN_EMAIL / DIRECTUS_ADMIN_PASSWORD
in env (typically via doppler run --) or readable Production/API_KEYS_MASTER.md.

Test sentinel cleanup: any decision_key starting with TEST_DELETE_ME_ is
PATCHed to status=superseded by the post-test fixture. Activity log rows
named TEST_* are not deleted (audit trail append-only per directus_delete
protected-collection rule).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

# Make Production/ importable from tooling layout.
_THIS = Path(__file__).resolve()
_PRODUCTION = _THIS.parent.parent.parent.parent
sys.path.insert(0, str(_PRODUCTION))
sys.path.insert(0, str(_THIS.parent.parent))

from lib.directus_admin_client import DirectusAdminClient  # noqa: E402

import server  # noqa: E402 — server.py at MCP server dir root


def _call(name: str, args: dict) -> dict:
    """Helper: invoke an MCP tool synchronously, return structured_content dict."""
    res = asyncio.run(server.mcp.call_tool(name, args))
    return res.structured_content


# -----------------------------------------------------------------------------
# Sanity / inventory
# -----------------------------------------------------------------------------


def test_tool_inventory_has_all_phase_1_and_2_tools():
    """Phase 1 (6) + Phase 2 (4) = 10 tools."""
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        # Phase 1 MVP
        "directus_search",
        "directus_get",
        "directus_create",
        "schema_describe",
        "log_activity",
        "lock_decision",
        # Phase 2 (added 2026-05-10 same-session per Cursor cross-review)
        "directus_patch",
        "directus_delete",
        "directus_invalidate_schema",
        "register_asset",
        "find_asset",
        "preflight_review",
    }
    missing = expected - names
    assert not missing, f"Missing tools: {missing}; got {names}"


# -----------------------------------------------------------------------------
# Read-side
# -----------------------------------------------------------------------------


def test_search_returns_known_locked_decision():
    res = _call(
        "directus_search",
        {
            "collection": "prod_locked_decisions",
            "filters": {"decision_key": {"_eq": "POST_ITEM_VERIFIED_V1"}},
            "fields": ["id", "decision_key", "status", "severity"],
            "limit": 1,
        },
    )
    assert res["ok"] is True
    assert res["count"] == 1
    row = res["rows"][0]
    assert row["id"] == 364
    assert row["status"] == "active"
    assert row["severity"] == "HIGH"


def test_get_known_id_round_trip():
    res = _call("directus_get", {"collection": "prod_locked_decisions", "item_id": 364})
    assert res["ok"] is True
    assert res["row"]["decision_key"] == "POST_ITEM_VERIFIED_V1"


def test_get_nonexistent_returns_not_found():
    res = _call(
        "directus_get",
        {"collection": "prod_activity_log", "item_id": 99999999},
    )
    assert res["ok"] is False
    assert res.get("not_found") is True


def test_schema_describe_prod_activity_log_has_11_fields():
    res = _call("schema_describe", {"collection": "prod_activity_log"})
    assert res["ok"] is True
    assert res["field_count"] == 11
    names = {f["name"] for f in res["fields"]}
    assert {"action", "details", "performed_by"} <= names


# -----------------------------------------------------------------------------
# Write-side: validation + structural Rule 35 enforcement
# -----------------------------------------------------------------------------


def test_create_with_unknown_field_rejected_at_validator():
    """The whole point of the MCP — Rule 35 silent-write killed at boundary."""
    res = _call(
        "directus_create",
        {
            "collection": "prod_activity_log",
            "payload": {
                "action": "TEST_SHOULD_FAIL_VALIDATION",
                "notes": "this field doesn't exist on prod_activity_log",
                "performed_by": "claude_test",
            },
        },
    )
    assert res["ok"] is False
    assert res.get("validation_error") is True
    assert "notes" in res.get("unknown_keys", [])


def test_log_activity_positive_write_round_trip():
    res = _call(
        "log_activity",
        {
            "action": "TEST_MCP_PYTEST_POSITIVE",
            "details": {"test": "test_smoke", "uuid": str(uuid.uuid4())},
            "performed_by": "claude_test",
        },
    )
    assert res["ok"] is True
    assert isinstance(res["id"], int)

    # Verify via directus_get
    verify = _call(
        "directus_get",
        {
            "collection": "prod_activity_log",
            "item_id": res["id"],
            "fields": ["id", "action", "performed_by"],
        },
    )
    assert verify["ok"] is True
    assert verify["row"]["action"] == "TEST_MCP_PYTEST_POSITIVE"
    assert verify["row"]["performed_by"] == "claude_test"


def test_create_unknown_field_on_prod_blockers():
    res = _call(
        "directus_create",
        {
            "collection": "prod_blockers",
            "payload": {
                "title": "test should fail",
                "severity": "low",
                "bogus_field_pytest": "should be rejected",
            },
        },
    )
    assert res["ok"] is False
    assert res.get("validation_error") is True
    assert "bogus_field_pytest" in res.get("unknown_keys", [])


# -----------------------------------------------------------------------------
# UPSERT via try_patch_or_queue
# -----------------------------------------------------------------------------


@pytest.fixture
def sentinel_decision_key():
    """Provides a unique sentinel key + cleans up after."""
    key = f"TEST_DELETE_ME_PYTEST_{uuid.uuid4().hex[:12].upper()}"
    yield key
    # Cleanup: PATCH any sentinel rows to superseded (not delete — protected
    # collection per directus_delete rule).
    client = DirectusAdminClient()
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"decision_key": {"_eq": key}},
        fields=["id"],
        limit=2,
    )
    for r in rows:
        client.patch_item(
            "prod_locked_decisions",
            r["id"],
            {
                "status": "superseded",
                "is_current": False,
                "date_superseded": "2026-05-10",
                "notes": "pytest sentinel cleanup",
            },
        )


def test_lock_decision_upsert_create_then_patch(sentinel_decision_key):
    key = sentinel_decision_key
    common = {
        "decision_key": key,
        "decision_name": f"pytest sentinel {key}",
        "decision_text": "pytest sentinel — first call creates",
        "task_category": "process_governance",
        "severity": "LOW",
        "source_document": "Production/mcp_servers/directus/tests/test_smoke.py",
    }
    first = _call("lock_decision", dict(common))
    assert first["ok"] is True
    assert first.get("upserted") == "created"
    first_id = first["id"]

    second = _call(
        "lock_decision",
        {**common, "decision_text": "pytest sentinel — second call PATCHes"},
    )
    assert second["ok"] is True
    assert second.get("upserted") == "patched"
    assert second["id"] == first_id  # same row


# -----------------------------------------------------------------------------
# Destructive tool gates
# -----------------------------------------------------------------------------


def test_directus_delete_rejects_protected_collection():
    res = _call(
        "directus_delete",
        {"collection": "prod_locked_decisions", "item_id": 1, "confirm_destructive": True},
    )
    assert res["ok"] is False
    assert res.get("gate_failed") == "protected_collection"


def test_directus_delete_rejects_without_env_var():
    """Use a non-protected collection to test the env-var gate."""
    saved = os.environ.pop("MN_MCP_ALLOW_DESTRUCTIVE", None)
    try:
        res = _call(
            "directus_delete",
            {
                "collection": "prod_session_decisions",
                "item_id": 99999999,
                "confirm_destructive": True,
            },
        )
        assert res["ok"] is False
        assert res.get("gate_failed") == "env_var"
    finally:
        if saved is not None:
            os.environ["MN_MCP_ALLOW_DESTRUCTIVE"] = saved


def test_directus_delete_rejects_without_confirm_flag():
    os.environ["MN_MCP_ALLOW_DESTRUCTIVE"] = "1"
    try:
        res = _call(
            "directus_delete",
            {
                "collection": "prod_session_decisions",
                "item_id": 99999999,
                "confirm_destructive": False,
            },
        )
        assert res["ok"] is False
        assert res.get("gate_failed") == "confirm"
    finally:
        del os.environ["MN_MCP_ALLOW_DESTRUCTIVE"]


# -----------------------------------------------------------------------------
# Schema invalidate
# -----------------------------------------------------------------------------


def test_invalidate_schema_collection_specific():
    # Prime the cache
    _call("schema_describe", {"collection": "prod_activity_log"})
    # Then flush
    res = _call("directus_invalidate_schema", {"collection": "prod_activity_log"})
    assert res["ok"] is True
    assert res.get("flushed") == "prod_activity_log"


def test_invalidate_schema_all():
    _call("schema_describe", {"collection": "prod_locked_decisions"})
    res = _call("directus_invalidate_schema", {})
    assert res["ok"] is True
    assert res.get("flushed") == "all"
