#!/usr/bin/env python3
"""
Create Directus collection `prod_preflight_reviews`.

Part 1A of Meta-Enforcement Institution (indexed-riding-lake plan).

This collection stores the audit record for every task run through
zero-error-qa Phase 0 (Pre-Flight Protocol). A weekly audit joins this
against app_activity_log to detect any work that bypassed Phase 0.

Idempotent: if the collection already exists, the script reports and
exits cleanly. Field creation is also idempotent (skips existing fields).

Usage:
    cd "<project root>"
    python3 Production/scripts/create_prod_preflight_reviews.py
"""

import sys
import os

# Allow importing from Production/tools/lib
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "tools"))
sys.path.insert(0, TOOLS_DIR)

from credentials_lib.credentials import load_credentials  # noqa: E402
from credentials_lib.directus import DirectusClient, DirectusError  # noqa: E402


COLLECTION_NAME = "prod_preflight_reviews"

COLLECTION_PAYLOAD = {
    "collection": COLLECTION_NAME,
    "meta": {
        "collection": COLLECTION_NAME,
        "icon": "verified",
        "note": "Audit record for zero-error-qa Phase 0 (Pre-Flight Protocol). Every task classified as routine/architectural writes one row here BEFORE work begins. Weekly audit joins against app_activity_log to catch skips.",
        "hidden": False,
        "singleton": False,
    },
    "schema": {
        "name": COLLECTION_NAME,
    },
}

# Fields are created one at a time after the collection exists.
FIELDS = [
    # id is auto-created when schema is provided; Directus adds it automatically
    # for non-singletons, but we define it explicitly to be safe.
    {
        "field": "task_id",
        "type": "string",
        "schema": {"is_nullable": False, "is_unique": True},
        "meta": {"interface": "input", "required": True, "note": "UUID or slug — must match app_activity_log.task_id"},
    },
    {
        "field": "task_type",
        "type": "string",
        "schema": {"is_nullable": False},
        "meta": {
            "interface": "select-dropdown",
            "options": {"choices": [
                {"text": "trivial", "value": "trivial"},
                {"text": "routine", "value": "routine"},
                {"text": "architectural", "value": "architectural"},
            ]},
            "required": True,
            "note": "trivial=0 agents, routine=1+1, architectural=4+4",
        },
    },
    {
        "field": "task_description",
        "type": "text",
        "schema": {"is_nullable": False},
        "meta": {"interface": "input-multiline", "required": True},
    },
    {
        "field": "claude_summary",
        "type": "text",
        "schema": {"is_nullable": False},
        "meta": {"interface": "input-multiline", "required": True, "note": "3-sentence pre-flight summary"},
    },
    {
        "field": "agent_advocates",
        "type": "json",
        "schema": {"is_nullable": True},
        "meta": {"interface": "input-code", "options": {"language": "json"}, "note": "Array of advocate responses (0/1/4 entries)"},
    },
    {
        "field": "agent_counters",
        "type": "json",
        "schema": {"is_nullable": True},
        "meta": {"interface": "input-code", "options": {"language": "json"}, "note": "Array of counter-agent critiques (0/1/4 entries)"},
    },
    {
        "field": "synthesis",
        "type": "text",
        "schema": {"is_nullable": True},
        "meta": {"interface": "input-multiline", "note": "Claude's synthesis after addressing CRITICAL/HIGH weaknesses"},
    },
    {
        "field": "approved_to_proceed",
        "type": "boolean",
        "schema": {"is_nullable": False, "default_value": False},
        "meta": {"interface": "boolean", "required": True, "note": "Must be true before Phase 1 runs"},
    },
    {
        "field": "approved_at",
        "type": "timestamp",
        "schema": {"is_nullable": True},
        "meta": {"interface": "datetime"},
    },
    {
        "field": "created_at",
        "type": "timestamp",
        "schema": {"is_nullable": False, "default_value": "CURRENT_TIMESTAMP"},
        "meta": {"interface": "datetime", "special": ["date-created"], "readonly": True},
    },
    {
        "field": "related_activity_log_id",
        "type": "integer",
        "schema": {"is_nullable": True},
        "meta": {"interface": "input", "note": "FK to app_activity_log — populated after task completes"},
    },
]


def collection_exists(client):
    try:
        client._ensure_auth()
        client._request("GET", f"/collections/{COLLECTION_NAME}")
        return True
    except DirectusError as e:
        if e.status in (403, 404):
            return False
        raise


def field_exists(client, field_name):
    try:
        client._ensure_auth()
        client._request("GET", f"/fields/{COLLECTION_NAME}/{field_name}")
        return True
    except DirectusError as e:
        if e.status in (403, 404):
            return False
        raise


def main():
    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"],
        creds["directus_email"],
        creds["directus_password"],
    )

    print(f"[preflight] Directus: {creds['directus_url']}")
    client.authenticate()
    print("[preflight] Authenticated.")

    # Step 1: Create collection (if missing)
    if collection_exists(client):
        print(f"[preflight] Collection '{COLLECTION_NAME}' already exists — skipping create.")
    else:
        print(f"[preflight] Creating collection '{COLLECTION_NAME}'...")
        client._request("POST", "/collections", data=COLLECTION_PAYLOAD)
        print(f"[preflight] Collection created.")

    # Step 2: Create fields (idempotent)
    created, skipped = 0, 0
    for field in FIELDS:
        name = field["field"]
        if field_exists(client, name):
            print(f"[preflight]   field '{name}' exists — skip")
            skipped += 1
            continue
        print(f"[preflight]   creating field '{name}' ({field['type']})...")
        client._request("POST", f"/fields/{COLLECTION_NAME}", data=field)
        created += 1

    print(f"[preflight] Fields: {created} created, {skipped} already existed.")

    # Step 3: Verify schema by reading it back
    schema = client._request("GET", f"/fields/{COLLECTION_NAME}")
    field_names = sorted(f["field"] for f in schema.get("data", []))
    print(f"[preflight] Final field list: {field_names}")

    # Step 4: Required field presence check
    required = {f["field"] for f in FIELDS}
    missing = required - set(field_names)
    if missing:
        print(f"[preflight] ERROR — missing fields after create: {missing}")
        sys.exit(2)

    print(f"[preflight] DONE — '{COLLECTION_NAME}' ready with {len(required)} defined fields.")


if __name__ == "__main__":
    main()
