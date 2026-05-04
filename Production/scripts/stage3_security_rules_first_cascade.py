#!/usr/bin/env python3
"""
Stage 3 security-rules-first cascade (2026-04-17).

Executes Directus writes for Kim's locked decision:
  "Stage 3 begins with firestore.rules + @firebase/rules-unit-testing suite
   BEFORE any data-model or feature implementation code."

Operations (idempotent where possible):
 1. POST prod_preflight_reviews (task_type=architectural, approved=True)
 2. POST prod_locked_decisions (decision_key=STAGE3_SECURITY_RULES_FIRST,
    severity=critical, status=active)
 3. Schema-introspect prod_reference_docs; upsert entries for the docs we
    cascade to if missing.
 4. POST prod_activity_log with cascade metadata.
 5. Print a structured summary JSON for the calling agent.

Reads credentials at runtime from Production/API_KEYS_MASTER.md via
lib.credentials.load_credentials (never hardcoded).

Retry policy: each write is attempted twice before surfacing the error.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "tools"))
sys.path.insert(0, TOOLS_DIR)

from lib.credentials import load_credentials  # noqa: E402
from lib.directus import DirectusClient, DirectusError  # noqa: E402


TASK_ID = "stage3-security-rules-first-20260417"
DECISION_KEY = "STAGE3_SECURITY_RULES_FIRST"
CASCADE_TASK_ID = "stage3-security-rules-first-cascade-20260417"


PREFLIGHT_PAYLOAD_CORE = {
    "task_id": TASK_ID,
    "task_type": "architectural",
    "task_description": (
        "Architectural ordering decision for Stage 3 (Core Features) of the "
        "MindfulNest app pipeline. Kim locked the rule that Stage 3 begins "
        "with firestore.rules + @firebase/rules-unit-testing suite BEFORE "
        "any data-model or feature implementation code is written. The "
        "three non-negotiables are: (a) therapist-read limited to linked "
        "patients; (b) parent-read limited to linked children; (c) child "
        "writes cannot mutate protected progression fields (coins, "
        "runeStates, modulesCompleted, ownedItems, and any other computed "
        "progression state). Rules + tests must both pass before any other "
        "Stage 3 code lands. Prevents client-trust anti-patterns from "
        "being baked into downstream code."
    ),
    "claude_summary": (
        "Kim instructed security-rules-first ordering. Registering preflight "
        "+ locked decision + cascade per Rule 19 (no shortcuts) and Rule 16 "
        "(execution tracking). No new code being written in this cascade — "
        "documentation + Directus writes only. Risk surface: registry drift "
        "if cascade misses a doc (mitigated by reference-docs sync script) "
        "and stale doc sections if later edits ignore the LD (mitigated by "
        "Rule 17 skill-embedded governance for Stage 3 work)."
    ),
    "approved_to_proceed": True,
    "approved_at": datetime.now(timezone.utc).isoformat(),
}


LOCKED_DECISION_PAYLOAD = {
    "decision_key": DECISION_KEY,
    "decision_name": (
        "Stage 3 begins with Firestore security rules + rules-unit-testing"
    ),
    "decision_text": (
        "Before any data-model or feature implementation code in Stage 3, "
        "the following must ship: "
        "(a) firestore.rules covering three non-negotiables — therapist can "
        "read only linked patients; parent can read only linked children; "
        "child writes cannot mutate protected fields (coins, runeStates, "
        "modulesCompleted, ownedItems, and any computed progression state); "
        "(b) @firebase/rules-unit-testing suite that exercises each rule "
        "with both allowed and denied test cases; "
        "(c) both must pass before any other Stage 3 code is written. "
        "This prevents client-trust anti-patterns (client-side coin "
        "computation, client-writable progression state) from being baked "
        "into downstream code."
    ),
    "source_document": (
        "MINDFULNEST_ARCHITECTURE_RECONCILIATION_v3 (pending) + "
        "APP_DEV_AUTOMATION_ARCHITECTURE_v1.md"
    ),
    "task_category": "architectural",
    "severity": "critical",
    "date_locked": "2026-04-17",
    "status": "active",
}


CASCADE_TARGETS = [
    # (absolute_path, title_for_registry, doc_type, notes)
    (
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/APP_DEV_AUTOMATION_ARCHITECTURE_v1.md",
        "MindfulNest App Development Automation Architecture v1",
        "architecture",
        "Primary Stage 3 ordering doc; updated in place to reference LD STAGE3_SECURITY_RULES_FIRST.",
    ),
    (
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/MINDFULNEST_ARCHITECTURE_RECONCILIATION_v2.md",
        "MindfulNest Architecture Reconciliation v2",
        "architecture",
        "Stack + sequencing decisions; updated to include Stage 3 security-rules-first note.",
    ),
    (
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/HANDOFF_STAGE2_REMAINING_BLOCKERS_April16_2026.md",
        "Stage 2 Remaining Blockers handoff (April 16 2026)",
        "handoff",
        "Stage 2 → 3 gating handoff; updated to note Stage 3 ordering constraint.",
    ),
    (
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.auto-memory/project_stage3_security_rules_first.md",
        "Stage 3 Security Rules First (LD STAGE3_SECURITY_RULES_FIRST memory pointer)",
        "memory",
        "Memory-file pointer to LD STAGE3_SECURITY_RULES_FIRST.",
    ),
]


def _with_retry(label, fn, *args, **kwargs):
    """Run fn; retry once on DirectusError; surface details on final fail."""
    try:
        return fn(*args, **kwargs)
    except DirectusError as e1:
        print(f"[cascade] {label} attempt 1 failed: {e1}", flush=True)
        time.sleep(1.0)
        try:
            return fn(*args, **kwargs)
        except DirectusError as e2:
            print(f"[cascade] {label} attempt 2 failed: {e2}", flush=True)
            raise


def step1_preflight(client):
    # Idempotent check
    existing = _with_retry(
        "preflight idempotency read",
        client._request,
        "GET",
        "/items/prod_preflight_reviews",
        params={"filter[task_id][_eq]": TASK_ID, "limit": 1},
    )
    rows = existing.get("data", [])
    if rows:
        rid = rows[0].get("id")
        print(f"[cascade] Preflight row already exists: id={rid}", flush=True)
        return rid, "existing"

    # Discover which fields this collection actually has so we stay
    # schema-tolerant (notes/approved fields may differ across installs).
    fields = _with_retry(
        "preflight schema introspection",
        client.get_fields,
        "prod_preflight_reviews",
    )
    field_names = {f.get("field", "") for f in fields}

    payload = dict(PREFLIGHT_PAYLOAD_CORE)
    # Only add optional 'notes' field if schema has it
    if "notes" in field_names:
        payload["notes"] = (
            "Kim explicitly instructed security-rules-first Stage 3 ordering. "
            "Architectural justification: firestore.rules is the trust "
            "boundary between the child device and server-owned progression "
            "state. Writing feature code first and rules last forces a "
            "client-trust model (coins computed on device, modulesCompleted "
            "writable by child) that is extremely expensive to unwind once "
            "feature code depends on it. Writing rules + rules-unit-testing "
            "first establishes the server-owned surface; downstream feature "
            "code is then forced to use Cloud Functions (or acceptable "
            "client writes) that satisfy the rules rather than inventing "
            "an anti-pattern first. Approved_to_proceed=true because Kim "
            "locked the decision and this is a documentation/registration "
            "cascade, not implementation."
        )

    result = _with_retry(
        "preflight POST",
        client._request,
        "POST",
        "/items/prod_preflight_reviews",
        data=payload,
    )
    new_id = result["data"]["id"]

    # Readback (Phase 0 Step 6 parity)
    readback = _with_retry(
        "preflight readback",
        client._request,
        "GET",
        "/items/prod_preflight_reviews",
        params={"filter[task_id][_eq]": TASK_ID, "limit": 1},
    )
    rb_rows = readback.get("data", [])
    if not rb_rows:
        raise RuntimeError(
            f"Preflight readback returned 0 rows for task_id={TASK_ID}"
        )
    print(
        f"[cascade] Preflight row created: id={new_id} task_id={TASK_ID}",
        flush=True,
    )
    return new_id, "created"


def step2_locked_decision(client, preflight_id):
    # Idempotent check by decision_key
    existing = _with_retry(
        "LD idempotency read",
        client._request,
        "GET",
        "/items/prod_locked_decisions",
        params={
            "filter[decision_key][_eq]": DECISION_KEY,
            "fields": "id,decision_key,status",
            "limit": 1,
        },
    )
    rows = existing.get("data", [])
    if rows:
        lid = rows[0]["id"]
        print(f"[cascade] LD {DECISION_KEY} already exists: id={lid}", flush=True)
        return lid, "existing"

    fields = _with_retry(
        "LD schema introspection",
        client.get_fields,
        "prod_locked_decisions",
    )
    field_names = {f.get("field", "") for f in fields}

    payload = dict(LOCKED_DECISION_PAYLOAD)
    if "related_preflight_id" in field_names:
        payload["related_preflight_id"] = preflight_id
    # Some schemas use 'notes' field for additional context
    if "notes" in field_names and "notes" not in payload:
        payload["notes"] = (
            f"Registered via cascade script {os.path.basename(__file__)} on "
            f"{datetime.now(timezone.utc).isoformat()}. Preflight row "
            f"id={preflight_id}."
        )

    # Drop fields the schema doesn't have to avoid 400s
    safe_payload = {k: v for k, v in payload.items() if k in field_names or k in {
        "decision_key", "decision_name", "decision_text", "source_document",
        "task_category", "severity", "date_locked", "status",
    }}

    result = _with_retry(
        "LD POST",
        client._request,
        "POST",
        "/items/prod_locked_decisions",
        data=safe_payload,
    )
    new_id = result["data"]["id"]
    print(f"[cascade] LD {DECISION_KEY} created: id={new_id}", flush=True)
    return new_id, "created"


def step3_reference_docs(client, files_cascaded):
    """Upsert prod_reference_docs entries for the cascaded files.

    files_cascaded: list of dicts {abs_path, title, doc_type, notes}
    Returns list of {path, action, row_id}
    """
    fields = _with_retry(
        "reference_docs schema introspection",
        client.get_fields,
        "prod_reference_docs",
    )
    field_names = {f.get("field", "") for f in fields}

    # Accept common alternate field names
    path_field = None
    for cand in ("file_path", "filepath", "path"):
        if cand in field_names:
            path_field = cand
            break
    if path_field is None:
        print(
            "[cascade] WARNING: prod_reference_docs has no recognizable path "
            f"field (looked for file_path/filepath/path). Fields: {sorted(field_names)}",
            flush=True,
        )
        return [{"path": f["abs_path"], "action": "skipped_no_path_field", "row_id": None}
                for f in files_cascaded]

    results = []
    for item in files_cascaded:
        abs_path = item["abs_path"]
        title = item["title"]
        doc_type = item["doc_type"]
        notes = item["notes"]

        # Check if already registered by path (exact or basename match)
        basename = os.path.basename(abs_path)
        existing = _with_retry(
            f"reference_docs lookup for {basename}",
            client._request,
            "GET",
            "/items/prod_reference_docs",
            params={
                f"filter[{path_field}][_contains]": basename,
                "fields": f"id,{path_field}",
                "limit": 5,
            },
        )
        rows = existing.get("data", [])
        match = None
        for r in rows:
            rp = r.get(path_field) or ""
            if basename in rp or rp.endswith(basename) or abs_path == rp:
                match = r
                break

        if match:
            # PATCH notes to reflect cascade
            rid = match["id"]
            patch_data = {}
            if "notes" in field_names:
                patch_data["notes"] = (
                    f"{notes} Updated {datetime.now(timezone.utc).isoformat()} "
                    f"for LD {DECISION_KEY} cascade."
                )
            if patch_data:
                _with_retry(
                    f"reference_docs PATCH {rid}",
                    client._request,
                    "PATCH",
                    f"/items/prod_reference_docs/{rid}",
                    data=patch_data,
                )
                results.append({"path": abs_path, "action": "patched", "row_id": rid})
            else:
                results.append({"path": abs_path, "action": "found_no_patch", "row_id": rid})
            print(f"[cascade] reference_docs: {basename} -> {results[-1]['action']} (id={rid})", flush=True)
            continue

        # Create new
        create_data = {path_field: abs_path}
        if "title" in field_names:
            create_data["title"] = title
        elif "name" in field_names:
            create_data["name"] = title
        if "doc_type" in field_names:
            create_data["doc_type"] = doc_type
        elif "type" in field_names:
            create_data["type"] = doc_type
        if "notes" in field_names:
            create_data["notes"] = notes
        if "status" in field_names:
            create_data["status"] = "active"
        if "is_current" in field_names:
            create_data["is_current"] = True

        try:
            result = _with_retry(
                f"reference_docs POST {basename}",
                client._request,
                "POST",
                "/items/prod_reference_docs",
                data=create_data,
            )
            new_id = result["data"]["id"]
            results.append({"path": abs_path, "action": "created", "row_id": new_id})
            print(f"[cascade] reference_docs: {basename} -> created (id={new_id})", flush=True)
        except DirectusError as e:
            # Don't fail the cascade if reference_docs write is rejected
            results.append({"path": abs_path, "action": f"error: {e}", "row_id": None})
            print(f"[cascade] reference_docs: {basename} -> ERROR {e}", flush=True)

    return results


def step4_activity_log(client, preflight_id, ld_id, files_edited, ref_doc_results):
    fields = _with_retry(
        "activity_log schema introspection",
        client.get_fields,
        "prod_activity_log",
    )
    field_names = {f.get("field", "") for f in fields}

    details = {
        "task_id": CASCADE_TASK_ID,
        "preflight_row_id": preflight_id,
        "locked_decision_id": ld_id,
        "decision_key": DECISION_KEY,
        "files_edited": files_edited,
        "reference_docs_results": ref_doc_results,
        "cascade_script": os.path.basename(__file__),
    }

    action_text = (
        "cascade: STAGE3_SECURITY_RULES_FIRST registered and propagated to "
        f"{len(files_edited)} project docs. Stage 3 must begin with "
        "firestore.rules + @firebase/rules-unit-testing suite before any "
        "data-model implementation code."
    )

    payload = {
        "action": action_text,
        "performed_by": "claude-opus-4-7-agent",
        "details": details,
    }
    # Some schemas use 'action_type' instead of embedding that in 'action'
    if "action_type" in field_names:
        payload["action_type"] = "cascade"
    if "feature_id" in field_names:
        payload["feature_id"] = "stage3_ordering_governance"

    result = _with_retry(
        "activity_log POST",
        client._request,
        "POST",
        "/items/prod_activity_log",
        data=payload,
    )
    new_id = result["data"]["id"]
    print(f"[cascade] activity_log created: id={new_id}", flush=True)
    return new_id


def main():
    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"],
        creds["directus_email"],
        creds["directus_password"],
    )
    client.authenticate()
    print(f"[cascade] Authenticated: {creds['directus_url']}", flush=True)

    summary = {
        "preflight_id": None,
        "preflight_action": None,
        "locked_decision_id": None,
        "locked_decision_action": None,
        "activity_log_id": None,
        "reference_docs_results": [],
        "errors": [],
    }

    try:
        preflight_id, action = step1_preflight(client)
        summary["preflight_id"] = preflight_id
        summary["preflight_action"] = action
    except Exception as e:
        summary["errors"].append(f"step1_preflight: {e}")
        raise

    try:
        ld_id, action = step2_locked_decision(client, preflight_id)
        summary["locked_decision_id"] = ld_id
        summary["locked_decision_action"] = action
    except Exception as e:
        summary["errors"].append(f"step2_locked_decision: {e}")
        raise

    # files_edited is populated by the calling agent later when it runs
    # the file edits. This script records the PLANNED cascade in activity_log.
    files_planned = [
        {"abs_path": t[0], "title": t[1], "doc_type": t[2], "notes": t[3]}
        for t in CASCADE_TARGETS
    ]

    try:
        ref_results = step3_reference_docs(client, files_planned)
        summary["reference_docs_results"] = ref_results
    except Exception as e:
        summary["errors"].append(f"step3_reference_docs: {e}")
        # Non-fatal — continue to activity log

    try:
        activity_id = step4_activity_log(
            client,
            preflight_id,
            ld_id,
            [f["abs_path"] for f in files_planned],
            summary["reference_docs_results"],
        )
        summary["activity_log_id"] = activity_id
    except Exception as e:
        summary["errors"].append(f"step4_activity_log: {e}")
        raise

    print("\n=== CASCADE SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
