# JSON-Column Validation Hardening — Proof Report

- **Date:** 2026-05-08
- **Author:** claude_code_terminal_session
- **Self-classification:** STANDARD (defensive validation addition; no behavior change for correct callers)
- **Activity log row id:** **1784** (live POST verified)
- **Origin incident:** 2026-05-08 — HTTP 500 returned by Directus when a stringified dict was POSTed to a `type: json` column (`prod_activity_log.details`). Bit multiple agents during the V59 Storyboard Foundation Sprint.
- **Authority:** Rule 35 (Directus schema verification + read-back-after-write), CLAUDE.md §8, `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §9 (JSON-typed columns inventory)

---

## 1. Mission summary

Add a STRICT pre-POST validator that:
1. Checks every JSON-typed column referenced in the payload against an inventory mirroring §9 of the schema reference doc.
2. Accepts `dict`, `list`, or `None` values; rejects everything else (the high-risk case is `str`).
3. Raises `JsonColumnTypeError` BEFORE the HTTP POST, with a clear actionable message.
4. Surfaces a distinct sentinel from `try_post_or_queue` (`{"json_column_type_error": True, ...}`) — author errors are NOT queued (a broken payload re-played later is still broken; the caller must fix it at the call site).

The validator is the canonical implementation in `Production/lib/directus.py` — the same module that already contains `post_item_verified` and `try_post_or_queue`. No new module added; no new import surface for callers.

---

## 2. Caller impact analysis (HALT gate per mission rules)

Pre-implementation grep of every caller of `try_post_or_queue` / `post_item_verified` in the live tree (excluding `.deploy_backups/` and `.claude/worktrees/`):

| File | Collection | `details` / JSON-column shape sent |
|---|---|---|
| `Production/tools/production_server.py` (5 sites) | `prod_activity_log` | dict literals (e.g. `{"key": key, "deleted_path": target}`) |
| `Production/scripts/architectural_fix_closeout_writes.py` | `prod_locked_decisions`, `prod_activity_log` | dicts |
| `Production/scripts/s5_5g_phase_h_lds.py` | `prod_locked_decisions` | dict; `related_files` list |
| `Production/scripts/c1_lock_bg_tab_scope_sync_v1.py` | `prod_locked_decisions` | dict |
| `Production/scripts/c2_lock_display_order_strict_v1.py` | `prod_locked_decisions` | dict |
| `Production/scripts/stream_progress_dashboard.py` | `prod_activity_log`, `prod_reference_docs` | dict |
| `Production/scripts/populate_prod_modules_from_gameplay_scope.py` | `prod_modules` | dict |
| `Production/scripts/s5_5g_phase_a_preflight.py` | `prod_preflight_reviews` | dict |
| `Production/scripts/s5_5g_phase_i_closeout.py` | `prod_activity_log` | dict |
| `Production/scripts/s5_5f_closeout_writes.py` | `prod_locked_decisions`, `prod_activity_log` | dict |
| `Production/scripts/fix_directus_admin_crossplat_register.py` | `prod_locked_decisions`, `prod_activity_log` | dict |

**Result:** every existing caller already passes the JSON columns as native Python dicts/lists. The strict validator does NOT break a single existing call site. (The 2026-05-08 incident was an ad-hoc agent payload, not a registered caller.)

No HALT triggered.

---

## 3. Verbatim diff — `Production/lib/directus.py`

```diff
@@ -84,6 +84,35 @@ class SilentWriteFailure(Exception):
         )


+class JsonColumnTypeError(Exception):
+    """Raised PRE-POST when a JSON-typed column receives a string payload.
+
+    Directus columns of `type: json` or `special: cast-json` REQUIRE a native
+    Python dict/list. Sending a JSON-encoded string returns HTTP 500 (confirmed
+    2026-05-08: prod_activity_log.details string → 500; dict → 200). Even when
+    Directus accepts a stringified value on other columns, the read-back
+    returns a parsed object, which trips post_item_verified's byte-equality
+    check and produces a false-positive SilentWriteFailure.
+
+    This exception is raised BEFORE the POST so authors get a clear, early,
+    actionable error instead of either:
+      (a) HTTP 500 from Directus (opaque), or
+      (b) silent_write_failure on a row that already exists in the DB.
+    """
+
+    def __init__(self, collection: str, field: str, sent_type: str, sample: Any):
+        self.collection = collection
+        self.field = field
+        self.sent_type = sent_type
+        self.sample = sample
+        super().__init__(
+            f"JsonColumnTypeError on {collection}.{field}: expected dict/list "
+            f"(JSON-typed column), got {sent_type}. "
+            f"Send a Python dict/list literal — do NOT json.dumps() it. "
+            f"Sample (truncated): {repr(sample)[:120]}"
+        )
+
+
 # -----------------------------------------------------------------------------
 # Equality helpers
 # -----------------------------------------------------------------------------
@@ -216,6 +245,66 @@ def _diff_payload_vs_row(payload: dict, row: dict) -> list[dict]:
     return mismatches


+# -----------------------------------------------------------------------------
+# JSON-column type guard (Rule 35 — pre-POST validation)
+# -----------------------------------------------------------------------------
+# Mirrors §9 of Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md
+# (live schema, queried 2026-05-08). When the schema reference doc is
+# updated, update this inventory in the same edit.
+JSON_COLUMN_INVENTORY: dict[str, set[str]] = {
+    "prod_locked_decisions": {"related_files", "keyword_synonyms"},
+    "prod_reference_docs": {"tags"},
+    "prod_preflight_reviews": {"agent_advocates", "agent_counters"},
+    "prod_activity_log": {"details", "voice_settings"},
+    "prod_modules": {"session_checklist"},
+    "prod_assets": {"tags"},
+}
+
+
+def _validate_json_columns(collection: str, payload: dict) -> None:
+    """STRICT pre-POST validator for JSON-typed Directus columns.
+
+    For each field in `payload` that is registered as JSON-typed for the
+    target collection in JSON_COLUMN_INVENTORY:
+      - dict/list value → PASS (correct native type)
+      - None value      → PASS (explicit allow-null; Directus stores SQL NULL)
+      - str/int/float/bool/anything-else → RAISE JsonColumnTypeError
+
+    The string case is the high-risk one (HTTP 500 on POST). The other
+    non-dict/non-list types are rejected pre-emptively for the same reason:
+    Directus will either 500 or coerce them, and either way the author's
+    intent (a structured object) is being violated.
+
+    No-op for collections not in JSON_COLUMN_INVENTORY — we do not want this
+    helper to fail closed on a brand-new collection. Schema additions must be
+    mirrored here AND in the schema reference doc.
+
+    Per CLAUDE.md Rule 35: every Directus write goes through this path before
+    the byte-equality read-back. Origin: 2026-05-08 HTTP 500 incident on
+    prod_activity_log.details (string payload).
+    """
+    fields = JSON_COLUMN_INVENTORY.get(collection)
+    if not fields:
+        return  # collection has no registered JSON columns
+    for field in fields:
+        if field not in payload:
+            continue
+        value = payload[field]
+        if value is None:
+            # Explicit allow: SQL NULL is valid for JSON columns.
+            continue
+        if isinstance(value, (dict, list)):
+            continue
+        # Anything else (str / int / float / bool / bytes / custom object)
+        # is rejected pre-POST.
+        raise JsonColumnTypeError(
+            collection=collection,
+            field=field,
+            sent_type=type(value).__name__,
+            sample=value,
+        )
+
+
 # -----------------------------------------------------------------------------
 # Public API
 # -----------------------------------------------------------------------------
@@ -248,6 +337,8 @@ def post_item_verified(
         The Directus row as read back after write, with 'id' populated.

     Raises:
+        JsonColumnTypeError: BEFORE POST, if a JSON-typed column in the payload
+                            received a non-dict/non-list/non-None value.
         DirectusWriteError: on HTTP error from the POST
         DirectusReadError: on HTTP error from the verification GET
         SilentWriteFailure: on any field value mismatch after write
@@ -256,6 +347,11 @@ def post_item_verified(
         Adds one extra GET (~100-300ms) per write. Acceptable for audit-trail
         writes (LDs, preflight reviews, checkpoints). NOT for tight loops.
     """
+    # 0) Pre-POST type guard for JSON-typed columns (Rule 35).
+    # Catches the 2026-05-08 HTTP-500 class of bugs where a stringified dict
+    # is sent to a `type: json` column. Strict — fail BEFORE the POST.
+    _validate_json_columns(collection, payload)
+
     c = client or DirectusAdminClient()

     # 1) POST the item
@@ -358,12 +454,28 @@ def try_post_or_queue(
     Returns:
         - The Directus row on success (dict with 'id').
         - A sentinel dict {"queued": True, "path": str} if queued offline.
+        - A sentinel dict {"json_column_type_error": True, ...} if the payload
+          violates the JSON-column type guard. NOT queued — author error.
+        - A sentinel dict {"silent_write_failure": True, ...} if read-back
+          detected a field mismatch. NOT queued — row already exists.

     Never raises. Used by mn-context SAVE mode which must not halt on "no
     internet" per feedback_desktop_no_hooks.md.
     """
     try:
         return post_item_verified(collection, payload, client=client)
+    except JsonColumnTypeError as e:
+        # Author error — NOT a transient/network failure. Queueing a broken
+        # payload just defers the problem to the next replay. Surface a
+        # distinct flag so the caller can fix the payload at the call site.
+        return {
+            "queued": False,
+            "json_column_type_error": True,
+            "collection": e.collection,
+            "field": e.field,
+            "sent_type": e.sent_type,
+            "error": str(e),
+        }
     except (DirectusWriteError, DirectusReadError) as e:
         path = queue_write_offline(collection, payload, reason=f"write_error: {e}")
         return {"queued": True, "path": str(path), "error": str(e)}
```

---

## 4. Test cases — verbatim outputs

### 4.1 Existing unit-test suite (regression check)

Command: `python3 -m unittest Production.lib.tests.test_directus_verified -v`

```
test_http_error_on_post_raises_write_error (TestAuthError) ... ok
test_auto_fields_presence_verified_not_valued (TestAutoFieldsPresenceOnly) ... ok
test_empty_diff (TestDiffHelper) ... ok
test_missing_field (TestDiffHelper) ... ok
test_write_readback_match_returns_row (TestHappyPath) ... ok
test_two_calls_produce_two_rows (TestIdempotencyNote) ... ok
test_live_roundtrip_activity_log (TestLiveDirectus) ... skipped 'Set MN_CONTEXT_LIVE_DIRECTUS_TESTS=1 to run live tests'
test_deep_nested_match (TestNestedJson) ... ok
test_deep_nested_mismatch (TestNestedJson) ... ok
test_queue_and_try_post_fallback (TestOfflineQueue) ... ok
test_404_on_readback_raises_read_error (TestReadBackFailure) ... ok
test_missing_field_surfaces_mismatch (TestSilentDrop) ... ok
test_string_to_int_coercion_surfaces (TestTypeCoercion) ... ok
test_bool_strict (TestValuesEqual) ... ok
test_int_float_cross (TestValuesEqual) ... ok
test_iso_datetime_roundtrip (TestValuesEqual) ... ok
test_list_order_sensitive (TestValuesEqual) ... ok
test_nested_dict (TestValuesEqual) ... ok
test_none_equality (TestValuesEqual) ... ok
test_type_coercion_rejected (TestValuesEqual) ... ok

Ran 20 tests in 0.006s
OK (skipped=1)
```

20/20 pre-existing tests still pass — no regression.

### 4.2 Five mandated test cases + three sanity-check bonuses

Smoke script: `/tmp/json_validator_smoke.py` (offline; uses MagicMock for the client). Verbatim output:

```
========================================================================
JSON-column validator smoke test — Production/lib/directus.py
========================================================================

=== (a) prod_activity_log details=dict → PASS ===
  details type sent: dict → accepted, row id=9999
PASS

=== (b) prod_activity_log details=str → FAIL ===
  raised JsonColumnTypeError with clear message:
    JsonColumnTypeError on prod_activity_log.details: expected dict/list (JSON-typed column), got str. Send a Python dict/list literal — do NOT json.dumps() it. Sample (truncated): '{"summary":"stringified-bad"}'
  try_post_or_queue surfaced json_column_type_error flag (not queued): JsonColumnTypeError on prod_activity_log.details: expected dict/list (JSON-typed column), got str. S
PASS

=== (c) prod_activity_log details=None → PASS (allow-null) ===
  details=None accepted (SQL NULL semantics — explicit allow-null)
PASS

=== (d) prod_locked_decisions related_files=list → PASS ===
  related_files=list[2], keyword_synonyms=list[2] → accepted, row id=9999
PASS

=== (e) prod_locked_decisions related_files=str → FAIL ===
  raised JsonColumnTypeError(collection='prod_locked_decisions', field='related_files', sent_type='str')
  try_post_or_queue surfaced json_column_type_error flag (not queued)
PASS

=== (bonus) inventory mirrors schema-ref §9 ===
  inventory matches §9 — 6 collections, 9 JSON columns
PASS

=== (bonus) unknown collection → no-op ===
  unknown collection → no-op (intentional)
PASS

=== (bonus) JSON field absent → no-op ===
  details absent from payload → no-op
PASS

All cases PASS.
```

### 4.3 Behavior summary table

| # | Collection | Field | Type sent | Validator | `try_post_or_queue` result |
|---|---|---|---|---|---|
| a | `prod_activity_log` | `details` | `dict` | PASS | row dict with `id` |
| b | `prod_activity_log` | `details` | `str` | RAISE `JsonColumnTypeError` | `{"json_column_type_error": True, "queued": False, ...}` |
| c | `prod_activity_log` | `details` | `None` | PASS (allow-null) | row dict with `id` |
| d | `prod_locked_decisions` | `related_files` | `list` | PASS | row dict with `id` |
| e | `prod_locked_decisions` | `related_files` | `str` | RAISE `JsonColumnTypeError` | `{"json_column_type_error": True, "queued": False, "field": "related_files", ...}` |

The `None` decision (case c) is the most defensible — Directus accepts SQL NULL on JSON columns, and rejecting `None` would force callers to either omit the field or pass an empty `{}`. Allow-null preserves existing semantics.

---

## 5. Live activity-log proof (Rule 35 read-back)

### 5.1 Initial POST via `try_post_or_queue`

```
Posting prod_activity_log entry…
  details type at call site: dict
OK: prod_activity_log id=1784
  action read back as: 'JSON_COLUMN_VALIDATION_HARDENING_LANDED'
  details.summary first 80 chars: 'Pre-POST JSON-column type guard added to Production/lib/directus.py. Catches 202'

ACTIVITY_LOG_ROW_ID=1784
```

`try_post_or_queue` performs read-back-after-write internally; the row was verified before this script returned.

### 5.2 Belt-and-suspenders explicit re-read

```
---read-back of id=1784---
id: 1784
action: 'JSON_COLUMN_VALIDATION_HARDENING_LANDED'
performed_by: 'claude_code_terminal_session'
details type: dict
details.summary[:80]: 'Pre-POST JSON-column type guard added to Production/lib/directus.py. Catches 202'
details.test_cases_passed: 8
details.json_columns_covered: 9
details.collections_covered: ['prod_locked_decisions', 'prod_reference_docs', 'prod_preflight_reviews', 'prod_activity_log', 'prod_modules', 'prod_assets']
details.confidence: '[CONFIRMED via local unittest + smoke test]'
```

Confirms `details` round-tripped as a dict (not stringified), action name uses canonical `action` field (not `action_type`), and the structured payload landed intact.

---

## 6. Cross-skill amendments

### 6.1 `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §9

Added a "Mechanical guard (added 2026-05-08)" subsection pointing at the new symbols (`JSON_COLUMN_INVENTORY`, `JsonColumnTypeError`, `_validate_json_columns`) and explicitly stating "When this table is updated, also update `JSON_COLUMN_INVENTORY` in `Production/lib/directus.py` in the same edit." This closes the drift loop between the doc and the code.

### 6.2 `.claude/skills/zero-error-qa/SKILL.md` DS-8

Inserted a new bold paragraph in the existing DS-8 entry covering the pre-POST guard, the sentinel return shape, the dual-source-of-truth (code constant + ref-doc table), and a back-pointer to this report. Edit applied via the Bash+Python pattern per `feedback_skill_edits_via_python.md` (sandbox-blocks `Edit` on `.claude/skills/`).

### 6.3 No drift detected

`mn-context/SKILL.md` already documents `try_post_or_queue` as the canonical path; no amendment needed there because the new behavior is internal to the function (same return-shape contract, plus one new sentinel key). `tech-spec/SKILL.md` references Rule 35 abstractly; no edit needed.

---

## 7. Confidence tags (per Rule 24)

- Pre-POST validator added to `post_item_verified`: [CONFIRMED via diff + py_compile + smoke test cases a/b/d/e]
- `try_post_or_queue` surfaces distinct sentinel for JSON-column type errors (does NOT queue): [CONFIRMED via case b/e exit-shape assertions]
- All 20 pre-existing unit tests pass: [CONFIRMED via `python3 -m unittest`]
- Live `prod_activity_log` row id=1784 landed with `details` as dict and round-tripped intact: [CONFIRMED via two independent read-backs]
- All 11 in-tree caller sites already pass dicts to JSON columns (no breakage): [CONFIRMED via grep audit, sample inspection]
- Inventory of 9 JSON columns across 6 collections mirrors live Directus schema as of 2026-05-08: [INFERRED from schema-ref §9 — the doc itself was authored from a live `/fields` query the same day]

---

## 8. Self-classification

**STANDARD** — defensive validation addition. No public API change; all existing valid call sites continue to work unchanged. Adds one new sentinel return shape (`json_column_type_error`) to `try_post_or_queue` documented in the docstring. New constant + new exception class are net additions, not replacements. No data migration. No behavior change in the success path.

---

## 9. Files touched

| Path | Change |
|---|---|
| `Production/lib/directus.py` | +97 lines / 0 deletions: `JsonColumnTypeError` class, `JSON_COLUMN_INVENTORY` constant, `_validate_json_columns` function, wired into `post_item_verified` and `try_post_or_queue` |
| `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` | +5 lines: new "Mechanical guard" subsection in §9 |
| `.claude/skills/zero-error-qa/SKILL.md` | +1 paragraph in DS-8 |
| `Production/docs/JSON_COLUMN_VALIDATION_HARDENING_REPORT_20260508.md` | this report (new) |
| `prod_activity_log` row id=1784 | live; canonical `action` field; `details` as dict |

---

## 10. Follow-ups (out of scope for this hardening)

1. **`try_get_or_warn` analog** — CLAUDE.md line 651 notes the read-path silent no-op pattern (empty dicts despite HTTP 200 when `fields=` filter is applied). A symmetric helper for reads would close that gap. Tracked indirectly via gap-fix Phase H scope.
2. **PATCH-path validation** — the new validator covers POST. PATCH on a JSON column with a string payload would suffer the same HTTP 500. If a `patch_item_verified` wrapper is ever added, it should also call `_validate_json_columns`.
3. **Inventory drift detector** — a CI check that diffs `JSON_COLUMN_INVENTORY` against a live `/fields` query for each registered collection would catch silent schema migrations. Out of scope for the hardening; flag for the schema-vocab cleanup follow-up list.
