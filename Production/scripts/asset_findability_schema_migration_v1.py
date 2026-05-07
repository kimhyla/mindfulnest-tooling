#!/usr/bin/env python3
"""
Asset Findability schema migration v1 (LD-421 build, 2026-04-26).
Additive only. Idempotent — safe to re-run.

Adds 14 fields to prod_assets, creates prod_asset_aliases, adds asset_id FK to prod_activity_log.
Phase 0 amendment: pre-check uses >= 9 (floor check), not == 9 (strict equality).
"""
import sys
import os

# Add project root to path
PROJECT_ROOT = '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files'
sys.path.insert(0, PROJECT_ROOT)

from Production.tools.lib import credentials, directus

NEW_PROD_ASSETS_FIELDS = [
    # Verdict + approval
    {"field": "kim_verdict", "type": "string",
     "schema": {"data_type": "character varying", "is_nullable": True, "default_value": None},
     "meta": {"interface": "select-dropdown", "options": {"choices": [
         {"text": "Pending", "value": "pending"},
         {"text": "Approved", "value": "approved"},
         {"text": "Rejected", "value": "rejected"},
         {"text": "Superseded", "value": "superseded"},
     ]}}},
    {"field": "kim_approved_at", "type": "timestamp",
     "schema": {"data_type": "timestamp with time zone", "is_nullable": True}},
    {"field": "kim_feedback", "type": "text",
     "schema": {"data_type": "text", "is_nullable": True}},
    # Lineage + supersession
    {"field": "is_current", "type": "boolean",
     "schema": {"data_type": "boolean", "is_nullable": True, "default_value": True}},
    {"field": "parent_asset_id", "type": "integer",
     "schema": {"data_type": "integer", "is_nullable": True}},
    {"field": "superseded_by_id", "type": "integer",
     "schema": {"data_type": "integer", "is_nullable": True}},
    # Scoping
    {"field": "event_id", "type": "integer",
     "schema": {"data_type": "integer", "is_nullable": True}},
    {"field": "beat_id", "type": "string",
     "schema": {"data_type": "character varying", "is_nullable": True}},
    {"field": "library", "type": "boolean",
     "schema": {"data_type": "boolean", "is_nullable": True, "default_value": False}},
    # Discovery
    {"field": "colloquial_name", "type": "text",
     "schema": {"data_type": "text", "is_nullable": True}},
    {"field": "tags", "type": "json",
     "schema": {"data_type": "json", "is_nullable": True, "default_value": "[]"}},
    {"field": "iteration_notes", "type": "text",
     "schema": {"data_type": "text", "is_nullable": True}},
    # Provenance + integrity
    {"field": "sha256", "type": "string",
     "schema": {"data_type": "character varying", "is_nullable": True}},
    {"field": "file_size_bytes", "type": "bigInteger",
     "schema": {"data_type": "bigint", "is_nullable": True}},
    {"field": "produced_by_skill", "type": "string",
     "schema": {"data_type": "character varying", "is_nullable": True}},
]

PROD_ASSET_ALIASES_COLLECTION = {
    "collection": "prod_asset_aliases",
    "schema": {"name": "prod_asset_aliases"},
    "meta": {"icon": "label", "note": "Natural-language phrase aliases for assets"},
}

PROD_ASSET_ALIASES_FIELDS = [
    {"field": "id", "type": "integer", "schema": {"is_primary_key": True, "has_auto_increment": True}},
    {"field": "asset_id", "type": "integer",
     "schema": {"data_type": "integer", "is_nullable": False}},
    {"field": "alias_text", "type": "text",
     "schema": {"data_type": "text", "is_nullable": False}},
    {"field": "alias_kind", "type": "string",
     "schema": {"data_type": "character varying", "is_nullable": True, "default_value": "kim_phrase"}},
    {"field": "created_at", "type": "timestamp",
     "schema": {"data_type": "timestamp with time zone", "is_nullable": True}},
]

ACTIVITY_LOG_FK = {
    "field": "asset_id", "type": "integer",
    "schema": {"data_type": "integer", "is_nullable": True}
}


def run(dry_run=False):
    creds = credentials.load_credentials()
    client = directus.DirectusClient(creds['directus_url'], creds['directus_email'], creds['directus_password'])

    print("=== Asset Findability Schema Migration v1 ===")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")

    # Pre-check: floor check (Phase 0 amendment)
    existing_fields = client._request('GET', '/fields/prod_assets')['data']
    field_count = len(existing_fields)
    print(f"Pre-check: prod_assets has {field_count} fields")
    if field_count < 9:
        print(f"ERROR: Expected at least 9 fields, found {field_count}. Aborting.")
        return False
    if field_count > 9:
        existing_names = [f['field'] for f in existing_fields]
        new_field_names = [f['field'] for f in NEW_PROD_ASSETS_FIELDS]
        unexpected = [n for n in existing_names if n not in ['id', 'module_id', 'asset_type', 'asset_name',
                      'file_path', 'status', 'notes', 'created_at', 'updated_at'] + new_field_names]
        if unexpected:
            print(f"WARNING: Found unexpected fields: {unexpected}")
            print("Continuing anyway (additive migration)...")
    print("Pre-check PASSED.\n")

    # Add fields to prod_assets
    existing_field_names = {f['field'] for f in existing_fields}
    added = 0
    skipped = 0
    for f in NEW_PROD_ASSETS_FIELDS:
        if f['field'] in existing_field_names:
            print(f"  SKIP (exists): prod_assets.{f['field']}")
            skipped += 1
            continue
        if dry_run:
            print(f"  WOULD ADD: prod_assets.{f['field']}")
        else:
            try:
                client._request('POST', '/fields/prod_assets', data=f)
                print(f"  ADDED: prod_assets.{f['field']}")
                added += 1
            except Exception as e:
                print(f"  ERROR adding prod_assets.{f['field']}: {e}")
                return False

    print(f"\nprod_assets: added {added}, skipped {skipped}")

    # Create prod_asset_aliases collection if needed
    existing_collections = {c['collection'] for c in client._request('GET', '/collections')['data']}
    if 'prod_asset_aliases' not in existing_collections:
        if dry_run:
            print("\n  WOULD CREATE: prod_asset_aliases collection + 5 fields")
        else:
            try:
                client._request('POST', '/collections', data=PROD_ASSET_ALIASES_COLLECTION)
                print("\n  CREATED: prod_asset_aliases collection")
                for f in PROD_ASSET_ALIASES_FIELDS:
                    if f['field'] == 'id':
                        continue  # Auto-created
                    client._request('POST', '/fields/prod_asset_aliases', data=f)
                    print(f"    ADDED: prod_asset_aliases.{f['field']}")
            except Exception as e:
                print(f"  ERROR creating prod_asset_aliases: {e}")
                return False
    else:
        print("\n  SKIP (exists): prod_asset_aliases collection")

    # Add asset_id FK to prod_activity_log
    activity_fields = {f['field'] for f in client._request('GET', '/fields/prod_activity_log')['data']}
    if 'asset_id' not in activity_fields:
        if dry_run:
            print("\n  WOULD ADD: prod_activity_log.asset_id FK")
        else:
            try:
                client._request('POST', '/fields/prod_activity_log', data=ACTIVITY_LOG_FK)
                print("\n  ADDED: prod_activity_log.asset_id FK")
            except Exception as e:
                print(f"  ERROR adding prod_activity_log.asset_id: {e}")
                return False
    else:
        print("\n  SKIP (exists): prod_activity_log.asset_id")

    print("\n  NOTE: Full-text index on iteration_notes deferred to Postgres direct.")
    print("  At <200 rows currently, _icontains filter is fast enough.")

    print(f"\n{'DRY RUN complete.' if dry_run else 'MIGRATION COMPLETE.'}")
    return True


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    success = run(dry_run=dry_run)
    sys.exit(0 if success else 1)
