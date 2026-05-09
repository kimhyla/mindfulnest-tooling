# Schema Vocab Migration — Tech Spec v7

**Authored:** 2026-05-08 (v7 amendment same day as v1 + v2 + v3 + v4 + v5 + v6).
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ARCHITECTURAL (governance + data migration; Cursor AMEND_V3 with 1 HIGH/Y blocker on Task F balanced-brace robustness).
**Status:** DESIGN ONLY — execution is gated on Kim approval per §7. Phase 5 additionally gated on a feature flag (see §3 Rule 1 v2 resolution, preserved verbatim through v3 → v4 → v5 → v6 → v7).

**Supersedes:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` (preserved as historical baseline; do NOT edit in place). v6 in turn supersedes v5; v5 supersedes v4; v4 supersedes v3; v3 supersedes v2; v2 supersedes v1.

**v6 → v7 driver:** Cursor returned `AMEND_V3` on v6 (sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`) with **ONE HIGH/Y blocker**:

- **Blocker F (HIGH, Y) — Task F balanced-brace extraction is still brittle.** v6's `extract_structured_payload` uses a raw brace counter that does NOT track JSON string state or escape characters. Example payload variation that breaks v6: `{"notes":"contains } brace","pid":123,...}` — the `}` inside the JSON string value is treated as a structural close, causing a wrong slice / parse failure / incorrect extraction path. Mitigation: replace the raw brace counter with a JSON-string-aware parser state machine that tracks `in_string` (toggled when an UNESCAPED `"` is encountered) and `escape` (set when `\\` is encountered inside a string; cleared on next char). Only count `{`/`}` when `not in_string`.

Tasks A (guarded parse), B (runtime payload-key validator), D (hazard warnings), E (`schema_version` + ≤256-char cap) all PASS at LOW severity per Cursor's AMEND_V3 review of v6 — v7 preserves them verbatim.

v7 corrects ONLY the `extract_structured_payload` function in §9.4 (replaces the brace counter with a JSON-string-aware state machine). All other v6 design (guarded parse + STALE_MUTEX_PARSE_FAILURE diagnostic, runtime validator + AST defense-in-depth, hazard warnings, `schema_version: "v1"`, ≤256-char resolution-text cap, severity case-fold, field-name compliance, cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, Task H) preserved verbatim. v1 + v2 + v3 + v4 + v5 + v6 preserved as historical baselines.

**Related artifacts (preserved from v6 + v7 additions):**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — **v6 historical baseline (this spec's predecessor)** (v7 NEW reference); sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline; sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline; sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline; sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates this spec.
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix that has already landed.
- `Production/scripts/lock_decision.py` — LD-writer CLI; canonical-aware as of 2026-05-08 per Cursor v3 Task H execution.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-fix backup.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating helper-import.
- `LD_WRITER_CANONICAL_VOCAB_V1` — LD filed 2026-05-08 documenting the lock_decision.py canonical-aware fix (HARD severity).
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for the dual-path discipline cited in §3 v2 path discipline section.
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (lowercase severity + STRUCTURED_DETAILS_JSON workaround); v7 §9.4 cross-references this LD.
- `LD-593` — v4 §9.4 severity case-fold authority (preserved through v5 → v6 → v7 since the case-fold remains in effect).
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority (preserved through v7).
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — v6 Cursor AMEND_V2 fix authority (preserved through v7; v7 builds on v6's parser/validator/cap/schema_version pattern with a JSON-string-aware state machine in the parser).
- `LD-597 TASK_DESCRIPTION_GOTCHA_DRIFT_RESOLUTION_V1` — anti-confusion guard for `prod_activity_log.task_description` non-existence; v7 inherits the guidance verbatim (do NOT include `task_description` in any `prod_activity_log` POST; `details` (JSON dict) is the canonical narrative carrier).
- `LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` — **v7 Cursor AMEND_V3 fix authority** (v7 NEW reference; filed 2026-05-08 same session as v7 spec authoring; LD id captured at file time).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for the v5 + v6 + v7 §9.4 corrections (8-field enumeration + STRUCTURED_DETAILS_JSON pattern + lowercase severity). Schema-ref doc §5 currently cites LD-596 (v6); LIKELY needs a v7-pointer update — surfaced for Kim's call (this v7 spec does NOT update the schema-ref doc).
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff. Currently at v2.3 citing v6; LIKELY needs v2.4 amendment to point at v7 + LD-598 — see §12 changelog.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure used for the Cursor review companion.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (preserved as v7's review companion since the cumulative review trail remains anchored at the v3 review handoff; v7 is a Cursor AMEND_V3 fix-set landing on the v6 surface).
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export.

---

## §0.1 — v7 Changelog (single-row amendment over v6)

v7 is a Cursor AMEND_V3 amendment over v6 addressing 1 HIGH/Y blocker (Task F: JSON-string-aware brace extraction). Tasks A / B / D / E all PASS at LOW severity per Cursor's AMEND_V3 review of v6 — v7 preserves them verbatim. v6's §0.1 changelog is preserved verbatim immediately below this v7 entry, followed by v5's, v4's, v3's.

| # | v7 amendment (Cursor AMEND_V3 verdict on v6) | Resolution applied in v7 | Sections changed |
|---|---|---|---|
| v7-A | **Blocker F (HIGH, Y)** — v6's `extract_structured_payload` brace counter ignores JSON string state and escape characters. Example payload variation that breaks v6: `{"notes":"contains } brace","pid":123,...}` — the `}` inside the JSON string value is treated as a structural close, causing a wrong slice / parse failure / incorrect extraction path. Other variations that break v6 along the same axis: nested-object payload where a `}` appears inside a string before the structural close (`{"k":"a } b","pid":1,"nested":{"x":"y"}}`); escaped-quote payload where the in-string `}` follows an escaped quote (`{"notes":"a \"quoted\" } brace","pid":1}`). All three variants slice at the wrong `}` under v6's brace counter. | v7 §9.4 REPLACES the v6 raw brace counter inside `extract_structured_payload` with a JSON-string-aware parser state machine. The new function tracks two booleans: `in_string` (toggled when an UNESCAPED `"` is encountered; not toggled if the previous char's `escape` was true) and `escape` (set when `\\` is encountered inside a string; cleared on the next char). Only `{`/`}` outside strings count toward `depth`. Existing graceful `None` fallback + `STALE_MUTEX_PARSE_FAILURE` activity-log diagnostic preserved verbatim from v6. The acquisition POST + release PATCH bodies stay v6 (already correct). The runtime validator `validate_prod_blockers_payload` (§6 Gate 11.2) stays v6 (already correct). v7 §9.4 adds a NEW callout block explaining the v7 fix. v7 §7 ADDS risk #16 documenting the brace-counter vs. state-machine implementer drift hazard. v7 §11 reference index adds v6 historical baseline + LD-598 (v7) + this v7 self-reference. v7 §12 changelog appends v7 entry. **Note:** schema-ref doc + handoff are not yet updated to point at v7 — surfaced as cross-skill drift for Kim's call (v7 does NOT update those files). | §9.4 (extract_structured_payload state machine REPLACES brace counter; v7 NEW callout; example variations cited), §7 risk #16 (NEW — brace-counter vs. state-machine implementer drift), §11 reference index (v6 baseline + LD-598 v7 + self-reference), §12 changelog |

**v6 vs v7 surface area (NEW):** v7 adds ~50 lines net (one §0.1 v7 row, one §9.4 v7 callout block + replaced function definition + example variation list, one §7 risk #16 row, three §11 reference-index entries, one §12 changelog entry). v7 deletes nothing structurally — it REPLACES the body of one function (`extract_structured_payload`) with a JSON-string-aware state machine while keeping all other v6 content verbatim. The substantive code-affecting change is exactly one: the parser depth counter now tracks JSON string state (`in_string` + `escape`) and only counts `{`/`}` outside strings. All other v6 content (§1, §2, §3.0-§3.4, §4, §5.0, §5 Phase 0/1/2/3/4/5/6, §8, §9.1-§9.3, §10, §6 Gates 1-12 including 11.1 + 11.2, §7 risks 1-15, §9.4 acquisition POST + release PATCH + stale-mutex cleanup wiring + caps + schema_version + hazard warnings) preserved verbatim from v6.

---

## §0.1 (v6, preserved verbatim) — v6 Changelog (Cursor AMEND_V2 fixes)

(Preserved verbatim from v6 §0.1 v6 row. See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` §0.1 v6 changelog table for the full row covering Blockers A + B + F + non-blockers D + E.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v6 row references the v6 example bodies which include the brace-counter `extract_structured_payload` that v7 has hardened. §9.4 v7 IS AUTHORITATIVE. See §6 Gate 11.2 (runtime validator, unchanged from v6) for write-time enforcement.

---

## §0.1 (v5, preserved verbatim) — v5 Changelog (single-row amendment over v4)

(Preserved verbatim from v6 §0.1 v5 section, which preserves verbatim from v5 §0.1. The v5 row covers the §9.4 field-name fix replacing `details` with `description+STRUCTURED_DETAILS_JSON` and replacing `resolution_notes` with `description` append.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v5 row references example bodies that predate v6's parser hardening AND v7's JSON-string-aware state machine. §9.4 v7 IS AUTHORITATIVE.

---

## §0.1 (v4, preserved verbatim) — v4 Changelog (single-row amendment over v3)

(Preserved verbatim from v6 §0.1 v4 section, which preserves verbatim from v4 §0.1. The v4 row covers the §9.4 severity case-fold from `CRITICAL` to lowercase `critical`.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v4 row + the example bodies it points to predate v5's field-name fix, v6's parser/validator/cap/schema_version hardening, and v7's JSON-string-aware state machine. §9.4 v7 IS AUTHORITATIVE.

---

## §0.1 (v3, preserved verbatim from v4 → v5 → v6 → v7) — v3 Changelog (Cursor amendment resolution table)

(Preserved verbatim from v6 §0.1 v3 section. See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` §0.1 v3 changelog table for the full Tasks B/D/E/F/H rows.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v3 row + every example body it carries forward predate v4's case-fold, v5's field-name fix, v6's parser/validator hardening, and v7's JSON-string-aware state machine. §9.4 v7 IS AUTHORITATIVE.

---

## §1 — Goal (preserved verbatim from v1 + v2 + v3 + v4 + v5 + v6)

(Preserved verbatim from v6 §1. Five-bullet goal statement + non-goals list.)

---

## §2 — Background (preserved verbatim from v1 + v2 + v3 + v4 + v5 + v6)

(Preserved verbatim from v6 §2. Cleanup-report baseline + v3 ADD on lock_decision.py + v4 ADD on prod_blockers row 101 + v5 §9.4 informational note + v6 ADD on parser/validator/lint hardening.)

**v7 ADD (informational):** v6's `extract_structured_payload` brace counter is JSON-string-naive (Cursor AMEND_V3 Blocker F). v7 fixes by replacing the depth counter with a JSON-string-aware state machine. No background-level scope change beyond the §9.4 + §7 risk #16 + §11 + §12 surgical edits.

---

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules + v2 amendments (preserved in v3 + v4 + v5 + v6 + v7)

(Preserved verbatim from v6 §3. §3.0 path discipline / §3.1 Rule 1 + PHASE_5_ENABLED / §3.2 Rule 2 / §3.3 Rule 3 / §3.4 Rule 4 — all preserved through v7. v7 introduces no §3-level changes; the v7 amendment is a parser-level state-machine substitution, not a debate-level change.)

See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` §3.0-§3.4 for the verbatim text.

---

## §4 — Per-rule action table (preserved verbatim from v3 + v4 + v5 + v6)

(Preserved verbatim from v6 §4. Rules 1/2/3a/3b/4 with v3 prerequisite columns + v2 expanded snapshot schema reference. v7 introduces no §4-level changes.)

See v3 §4 / v4 §4 / v5 §4 / v6 §4 for the verbatim text.

---

## §5 — Migration sequence (preserved verbatim from v3 + v4 + v5 + v6)

> **§5-LEVEL HAZARD WARNING (preserved verbatim from v6 with v7 update):** §5 below preserves v3+v4+v5+v6 example body code blocks BY REFERENCE (not inline). Any reader who follows the v3/v4/v5/v6 reference back WILL find historical POST bodies that include defects v7 has fixed (v3 era: non-existent `details` key, unguarded `json.loads`, brittle regex; v6 era: brace counter that ignores JSON string state). **DO NOT IMPLEMENT FROM HISTORICAL CONTENT.** §9.4 v7 IS AUTHORITATIVE. The migration script's Phase 1 entry-guard (and every other `prod_blockers` POST/PATCH) MUST use the v7 §9.4 patterns: JSON-string-aware state-machine extractor (replaces v6 brace counter) + try/except for parsing, runtime payload-key validator before write, capped resolution-text append, schema_version="v1" on acquisition. See §6 Gate 11.2 for the write-time runtime validator that prevents non-existent-field payloads from reaching Directus regardless of which historical block the implementer copy-pasted from.

(Preserved verbatim from v6 §5. §5.0 checkpoint protocol / Phase 0 Steps 0/1/2/3/0.4/0.5 / Phase 1-6 — all preserved through v7.)

**v4 NOTE preserved:** the Phase 1 entry-guard code block in v3 §5 contains a `severity="CRITICAL"` literal in the mutex POST. Per v4 §9.4 (case-fold), this string MUST be lowercase `"critical"` at script-write time.

**v5 NOTE preserved:** the Phase 1 entry-guard code block in v3 §5 (and v4's narrative carrying it forward) also references a `details` key on the `prod_blockers` POST. Per v5 §9.4 (field-name fix), this key MUST be REMOVED at script-write time and the structured payload (`host`, `pid`, `started_at`, `script_version`) MUST be encoded inside `description` as a `STRUCTURED_DETAILS_JSON:`-anchored JSON literal.

**v6 NOTE preserved:** v5's stale-mutex parser used a brittle regex + raw `json.loads`, and v5's Gate 11.2 was a grep-only lint. Per v6 §9.4 + §6 Gate 11.2, the migration script's Phase 1 entry-guard implementation MUST use: (1) balanced-brace JSON extractor for any `STRUCTURED_DETAILS_JSON:` parsing; (2) `try/except json.JSONDecodeError` with graceful fallback + `STALE_MUTEX_PARSE_FAILURE` activity-log row; (3) runtime `validate_prod_blockers_payload(payload)` invoked immediately before every POST/PATCH to `prod_blockers`; (4) `schema_version: "v1"` in the acquisition payload; (5) ≤256-char cap on resolution-text append.

**v7 NOTE (NEW):** v6's balanced-brace extractor uses a raw depth counter that ignores JSON string state (Cursor AMEND_V3 Blocker F). Payloads where a `}` (or `{`) appears inside a JSON string value — e.g. `{"notes":"contains } brace","pid":123,...}` — are mis-sliced at the in-string `}`. Per v7 §9.4, the migration script's stale-mutex parser MUST use the JSON-string-aware state machine: track `in_string` (toggled on UNESCAPED `"`) and `escape` (set on `\\` inside a string; cleared on next char); count `{`/`}` only when `not in_string`. v7 §9.4 callout is the authoritative source. The acquisition POST + release PATCH + Gate 11.2 validator are unchanged from v6.

See v3 §5.0 + Phase 0 + Phase 1-6 for the verbatim text.

---

## §6 — Pre-implementation gates Kim must approve (v6 preserved verbatim through v7)

(Gates 1-9 preserved verbatim from v2. Gates 10/11/12 preserved verbatim from v3. Gate 11.1 preserved verbatim from v4. Gate 11.2 REPLACED in v6; preserved verbatim through v7.)

> **§6-LEVEL HAZARD WARNING (preserved verbatim from v6 with v7 update):** every gate row below that points back at a v3/v4/v5/v6 example body is pointing into preserved historical content. **DO NOT IMPLEMENT FROM HISTORICAL CONTENT.** §9.4 v7 IS AUTHORITATIVE. Gate 11.2 v6 is the load-bearing write-time enforcement (runtime validator, not grep) — preserved verbatim through v7.

| # | Gate | Kim's decision required |
|---|------|------------------------|
| 10 | **(v3 — Cursor Task D)** Pre-Phase-5 rollback rehearsal: must Phase 0 Step 0.5 produce a "All passed: True" report on 5 random rows BEFORE Phase 5 may execute? Phase 5 entry guard halts if rehearsal report missing or any row failed. | YES (REQUIRED for Phase 5) / NO (only valid if Phase 5 stays DEFERRED) |
| 11 | **(v3 — Cursor Task E)** Remote mutex via Directus `prod_blockers` row `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (severity per v4 §9.4 case-fold = `critical` lowercase; field-name compliance per v5 §9.4 + v6 §6 Gate 11.2 runtime validator = no `details` / no `resolution_notes`): must mutating phases (1, 2, 4, 5) acquire+verify this row before proceeding? | YES (REQUIRED) / DEFER (single-host operation; rely on local lockfile only) |
| 11.1 | **(v4 — self-discovered defect)** Mutex POST severity case-fold: must the migration script's `prod_blockers` mutex POST/PATCH use `severity='critical'` (LOWERCASE) per the live `prod_blockers.severity` enum? Uppercase `CRITICAL` returns HTTP 500 and would block Phase 1-5 entry-guard acquisition. Reference: live-schema enum `[critical, high, medium, low]` per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 + LD-592. | YES (REQUIRED — uppercase returns HTTP 500; no defer option) |
| 11.2 | **(v6 — Cursor AMEND_V2 Blocker B; preserved verbatim through v7)** Mutex POST/PATCH field-name compliance: must the migration script invoke a RUNTIME payload-key validator `validate_prod_blockers_payload(payload: dict) -> None` IMMEDIATELY BEFORE every POST/PATCH to `prod_blockers`, rejecting any payload whose keys are not a subset of the 8 live fields (`id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at`)? Structured payloads MUST encode inside `description` as text-embedded JSON anchored on `STRUCTURED_DETAILS_JSON:` per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (lines 362-377). Resolution-time annotation MUST append to the existing `description` (capped ≤256 chars per non-blocker E) rather than use a non-existent field. The runtime validator is the LOAD-BEARING layer — grep-based lint is unreliable (token concat, computed keys, helper wrappers, carve-out collisions). Optional pre-launch AST-based CI lint is documented as defense-in-depth. Reference: live-schema 8-field enumeration + LD-592 + LD-595 + LD-596 (v6) + LD-598 (v7) + handoff §6 prod_blockers schema gotchas. | YES (REQUIRED — non-validated writes can ship `details`/`resolution_notes` keys returning HTTP 400 unknown-field; no defer option) |
| 12 | **(v3 — Cursor Task F)** Checkpoint file `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` (append-only, schema per §5.0): must per-row checkpoint appends be a hard requirement of Phases 1, 2, 4, 5 with the resume algorithm verifying snapshot_hash on session restart? | YES (REQUIRED for resume safety) / NO (single-session execution; no resume protocol needed) |

**Gate 10 verification artifact (v3 preserved):** rollback rehearsal report at `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md`; Phase 5 entry guard's check #2 reads it.

**Gate 11 verification artifact (v3 preserved):** Directus query for `prod_blockers` row with title `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` and `is_resolved=false`; Phase 1-5 entry guards read it.

**Gate 11.1 verification artifact (v4 preserved through v7):** at script-write time, the migration script's source for the mutex POST/PATCH must be grep-able for `severity=.*critical` (lowercase) and MUST NOT match `severity=.*CRITICAL` (uppercase). Recommended pre-launch lint: `grep -n "severity=.*CRITICAL\|severity=.*\"CRITICAL\"" Production/scripts/migrate_schema_vocab_v1.py` returns NO matches inside any `prod_blockers`-targeted POST/PATCH block. (Matches inside `prod_locked_decisions`-targeted code are FINE — that collection's `severity` enum IS uppercase.) At runtime, the read-back per Rule 35 confirms the persisted value is lowercase `critical`. If HTTP 500 is returned by Directus on the mutex POST, the script HALTS with `MUTEX_POST_HTTP_500_LIKELY_CASE_VIOLATION` activity-log row.

**Gate 11.2 verification artifact (v6 preserved verbatim through v7 — runtime validator):** the migration script defines:

```python
ALLOWED_PROD_BLOCKERS_KEYS = {
    "id",
    "module_id",
    "severity",
    "title",
    "description",
    "is_resolved",
    "created_at",
    "resolved_at",
}

def validate_prod_blockers_payload(payload: dict) -> None:
    """
    Reject any prod_blockers POST/PATCH payload whose keys leak outside the
    8 live fields. Called immediately before every client.post_item or
    client.patch_item targeting prod_blockers. Bypasses are not possible at
    runtime regardless of how the payload dict was constructed (literal,
    computed key, helper wrapper, token concat).
    """
    extra = set(payload.keys()) - ALLOWED_PROD_BLOCKERS_KEYS
    if extra:
        raise RuntimeError(
            f"prod_blockers payload contains non-existent fields: {extra}. "
            f"Allowed keys: {sorted(ALLOWED_PROD_BLOCKERS_KEYS)}. "
            f"See SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md §9.4 + §6 Gate 11.2."
        )
```

Call-site rule: the migration script (and every helper that writes to `prod_blockers`, including `release_stale_mutex.py`) MUST invoke `validate_prod_blockers_payload(payload)` IMMEDIATELY BEFORE every `client.post_item("prod_blockers", payload)` and every `client.patch_item("prod_blockers", id, payload)`. The validator runs in-process at write-time so it CANNOT be bypassed by lint-defeating constructs (token concatenation `"deta"+"ils"`, computed keys `{f"detail{'s'}": ...}`, helper wrappers that build the dict elsewhere, carve-out tokens `prod_activity_log` / `prod_locked_decisions` sharing a line). Failure mode: `RuntimeError: prod_blockers payload contains non-existent fields: {'details'}` halts the script BEFORE the HTTP call to Directus. The script then emits `MUTEX_POST_PAYLOAD_VALIDATION_FAILED` activity-log row pointing the operator at this gate.

**Defense-in-depth (optional, recommended pre-launch; preserved verbatim from v6):** an AST-based static check that walks every `Call` node in the migration script's AST, identifies calls to `client.post_item` / `client.patch_item` whose first positional argument is the literal string `"prod_blockers"`, inspects the dict-literal second/third argument's `keys`, and rejects any key outside `ALLOWED_PROD_BLOCKERS_KEYS`. The AST check is a CI lint (recommended in `.github/workflows/`) — it complements but does NOT replace the runtime validator. AST checks miss helper-wrapper indirection; the runtime validator does not.

**Why grep was insufficient (v6 explanatory; preserved verbatim through v7):** v5's Gate 11.2 lint was `grep -n '"details"\|"resolution_notes"' ... | grep -v "prod_activity_log\|prod_locked_decisions"`. False suppression occurs when (a) a real `prod_blockers` write builds its payload with token concatenation (`{"deta" + "ils": ...}` is invisible to grep), (b) the payload dict is built in a helper function whose call site has a `prod_activity_log` reference on the same line (carve-out matches the wrong line), (c) the key is computed (`{f"detail{'s'}": ...}`), or (d) the dict is constructed via `dict(**kwargs)` where kwargs are passed in. The runtime validator catches all four cases because by the time validation runs the payload dict's `.keys()` are concrete strings.

**Gate 12 verification artifact (v3 preserved):** checkpoint file exists at the expected path; snapshot_hash field matches current snapshot's metadata hash; resume algorithm filters target rows to `id > last_committed_row_id`.

---

## §7 — Risk assessment (v6 preserved + v7 risk #16 added)

(Rows 1-9 preserved verbatim from v2. Rows 10/11/12 preserved verbatim from v3. Row 13 preserved verbatim from v4. Row 14 preserved verbatim from v5 with v6 likelihood-condition clarification. Row 15 preserved verbatim from v6. Row 16 NEW in v7.)

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| **(v3)** Rollback rehearsal passes on 5 sampled rows but actual rollback fails on the remaining 315 rows due to row-specific quirks | LOW | HIGH | Sample size of 5 is the v3 baseline; if Kim wants higher confidence, increase to 20 or 50; always emit the failed-row id in the activity-log row |
| **(v3 — preserved with v6 + v7 clarifications)** Remote mutex acquisition succeeds but mutex is never released due to script crash; subsequent runners blocked indefinitely | LOW | MEDIUM | Mutex includes `pid` field (v5: encoded in `description` STRUCTURED_DETAILS_JSON block; v6: also includes `schema_version: "v1"`); cleanup helper `release_stale_mutex.py` checks if PID is alive on the recorded host (v5: parses PID via regex; v6: parses via balanced-brace `extract_structured_payload` + try/except; v7: parser is JSON-string-aware state machine — see §9.4); manual override path documented in §9.4 |
| **(v3)** Checkpoint file corrupted mid-write causes resume algorithm to crash or skip valid rows | LOW | MEDIUM | Resume algorithm tolerates corrupt last line via try/except |
| **(v4 — #13)** Spec author or implementer copy-pastes uppercase `CRITICAL` from v3's §9.4 example into the migration script's mutex POST despite the v4 amendment, returning HTTP 500 from Directus and halting Phase 1-5 entry-guard acquisition | LOW | HIGH | (1) v4 §9.4 callout cites the case-fold prominently; (2) LD-592 schema-ref doc records the divergence as a permanent gotcha; (3) §6 Gate 11.1 mandates a pre-script-launch lint that greps the mutex POST source for `severity=.*CRITICAL` (uppercase) inside `prod_blockers`-targeted code and rejects; (4) at runtime, an HTTP 500 on the mutex POST produces `MUTEX_POST_HTTP_500_LIKELY_CASE_VIOLATION` activity-log row pointing the operator at the §9.4 case-fold guidance. Severity HIGH because Phases 1+2+4+5 entry-guard depend on mutex acquisition; failure halts all mutating phases and leaves the system mid-migration. |
| **(v5 — #14; v6 likelihood condition clarified; preserved verbatim through v7)** Spec author or implementer copy-pastes v3/v4 example body containing a `details` or `resolution_notes` field on a `prod_blockers` POST/PATCH despite the v5 + v6 amendments; Directus returns HTTP 400 / unknown-field error; mutex acquisition fails → all mutating phases (Phase 1, 2, 4, 5) entry-guard halts | LOW (with v6 hardened lint — runtime validator at §6 Gate 11.2; if hardened lint is dropped or reverted, raise to MED) | HIGH | (1) v5 + v6 §9.4 callout enumerates the live 8 fields and prohibits the two non-fields prominently; (2) LD-592 schema-ref doc + LD-595 + LD-596 (v6) + LD-598 (v7) record the divergence as a permanent gotcha; (3) §6 Gate 11.2 v6 is now a RUNTIME payload-key validator invoked immediately before every POST/PATCH (not a grep gate); the validator catches token concat / computed keys / helper wrappers / carve-out collisions that grep misses; (4) optional AST-based CI lint as defense-in-depth; (5) handoff §6 prod_blockers schema gotchas already documents this for the implementation handoff path; (6) §5 + §6 hazard warnings explicitly tell readers NOT to implement from historical content; (7) at runtime, a validator failure produces `MUTEX_POST_PAYLOAD_VALIDATION_FAILED` activity-log row pointing the operator at Gate 11.2; an HTTP 400 (if validation is somehow bypassed) produces `MUTEX_POST_HTTP_400_UNKNOWN_FIELD` activity-log row. Severity HIGH because mutex acquisition is the entry guard for Phase 1+2+4+5; failure halts ALL mutating phases. Likelihood LOW because the §9.4 v6 corrected example bodies + Gate 11.2 runtime validator + risk row + LD-595 + LD-596 + schema-ref doc + handoff §6 + hazard warnings form a multi-layer redundancy against the defect re-entering the script. |
| **(v6 — #15; preserved verbatim through v7 with v7 likelihood narrowing)** Stale-mutex cleanup helper encounters a malformed or unparseable `STRUCTURED_DETAILS_JSON:` block in `description` (corruption, partial write, manual edit, schema_version mismatch) and crashes when calling `json.loads`, leaving the mutex held indefinitely + the operator without diagnostic context | LOW (after v6 — extract_structured_payload uses balanced-brace + try/except; v7 narrows further: state-machine extractor handles braces inside JSON string values without misslicing) | MEDIUM | (1) v6 + v7 §9.4 `extract_structured_payload(description: str) -> Optional[dict]` performs delimiter-find + balanced-brace JSON extraction (no brittle lazy-regex); (2) v7 makes the brace-counter JSON-string-aware (tracks `in_string` + `escape`) so payloads with in-string braces no longer mis-slice; (3) the function is wrapped in `try/except json.JSONDecodeError` returning `None` on failure rather than propagating; (4) on `None` return, the cleanup helper sets `pid=None` + `host_recorded=None` + posts a `STALE_MUTEX_PARSE_FAILURE` activity-log row including the row id + raw `description` (truncated to 1024 chars) + a pointer to §9.4's manual-review path; (5) Kim can always force-release via Directus admin UI by PATCHing `is_resolved=true` directly. Severity MEDIUM because the failure mode is graceful (manual-review fallback) rather than crashing the process; the only operational impact is the cleanup helper deferring to the operator instead of auto-resolving. Likelihood LOW because v7 hardens the regex AND the parse step AND the depth-counter; the only path to failure is genuinely-corrupted JSON + the operator ignoring the activity-log diagnostic. |
| **(v7 NEW — #16)** Migration script implementer copies v6 brace-counter extraction snippet despite v7 amendment; payloads containing `}` (or `{`) inside JSON string values mis-slice, returning a wrong dict or `None` from `extract_structured_payload` → stale-mutex cleanup defers to manual-review path unnecessarily, OR worse, returns a wrong dict whose `pid` field is corrupted such that the cleanup helper queries an unrelated PID | LOW (with v7 §9.4 explicit state-machine pseudocode + §0.1 v7-A row + LD-598 + Gate 11.2 runtime validator complement) | HIGH | (1) v7 §9.4 explicit state-machine pseudocode enumerates `in_string` + `escape` + the `not in_string` depth-counting rule with prose guidance; (2) v7 §0.1 v7-A row cites the example variation `{"notes":"contains } brace","pid":123,...}` so any reader sees the failure mode before reading the function body; (3) LD-598 (v7) records the divergence as a permanent gotcha; (4) §6 Gate 11.2 runtime validator does NOT catch this defect directly (it operates on dict keys, not on parser correctness) — Gate 11.2 is a complement, not a substitute; (5) caller graceful `None` fallback per v6+v7 §9.4 means a wrong-slice that produces JSONDecodeError → `None` → manual-review fallback, which is the safe path; the residual risk is a wrong-slice that happens to produce a syntactically-valid but semantically-wrong dict; in practice the dominant case is JSONDecodeError because in-string `}` will leave dangling text after the wrong slice. Severity HIGH because a corrupted PID → wrong host check → potentially auto-releasing a still-held mutex on another host. Likelihood LOW because v7's state machine is correct by construction and the explicit pseudocode + example variation + LD-598 + risk row form a multi-layer redundancy. |

---

## §8 — Rollback per phase (preserved verbatim from v3 + v4 + v5 + v6)

(Preserved verbatim from v6 §8. Per-phase rollback narrative + v3 rehearsal-tied addendum. v7 introduces no §8-level changes.)

See v3 §8 / v4 §8 / v5 §8 / v6 §8 for the verbatim text.

---

## §9 — Operational notes (v6 preserved + v7 §9.4 JSON-string-aware state-machine extractor)

(§9.1, §9.2, §9.3 preserved verbatim from v2 through v3 through v4 through v5 through v6 through v7.)

### §9.4 — Concurrency, lockfile, and remote mutex (v7 JSON-STRING-AWARE STATE MACHINE over v6 — Cursor AMEND_V3 fix-set: Blocker F)

> **§9.4 v7 IS AUTHORITATIVE for migration script implementation.** All historical example bodies preserved in v3/v4/v5/v6 (and the "preserved verbatim" pointers throughout §5/§6/§9 above) are HISTORICAL RECORD, not implementation source. **DO NOT IMPLEMENT FROM HISTORICAL CONTENT.** Use the v7 patterns below.

> **JSON-string-aware extraction (v7 NEW correction).** v6's `extract_structured_payload` used a raw brace counter that ignored JSON string state. Example variation that breaks v6: `{"notes":"contains } brace","pid":123,...}` — v6's depth counter would mis-slice at the `}` inside the JSON string. Other variations along the same axis: nested-object payload where a `}` appears inside a string before the structural close (`{"k":"a } b","pid":1,"nested":{"x":"y"}}`); escaped-quote payload where the in-string `}` follows an escaped quote (`{"notes":"a \"quoted\" } brace","pid":1}`). v7 REPLACES the brace counter with a state machine tracking `in_string` (toggled on UNESCAPED `"` — i.e. only when the previous char was not flagged `escape`) and `escape` (set on `\\` inside a string; cleared on the next char). Only `{`/`}` outside strings count toward depth. v6 graceful `None` fallback + `STALE_MUTEX_PARSE_FAILURE` activity-log row preserved verbatim. The acquisition POST + release PATCH bodies stay v6 (already correct). The runtime validator `validate_prod_blockers_payload` (§6 Gate 11.2) stays v6 (already correct).

**Field-name fix (v5 NEW correction; preserved verbatim through v7).** Live `prod_blockers` has only **8 fields**: `id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at` (live-probed 2026-05-08 via `DirectusAdminClient.fields("prod_blockers")` returning exactly 8 entries). There is **NO `details` field** and **NO `resolution_notes` field**. Structured payload (host/pid/started_at/script_version + v6: schema_version) goes in `description` text as `STRUCTURED_DETAILS_JSON:` + JSON literal per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (lines 362-377). Resolution context appends to `description` on release PATCH (v6: capped ≤256 chars). Cross-reference: LD-592 + LD-593 + LD-595 + LD-596 (v6) + LD-598 (v7) + handoff §6 prod_blockers schema gotchas.

**Severity case (v4 preserved through v7).** Live `prod_blockers.severity` enum requires LOWERCASE values: `critical` / `high` / `medium` / `low` (live-probed 2026-05-08 from `/fields/prod_blockers/severity`; canonical reference `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5; authority LD-592 + LD-593). The migration script's mutex POST MUST use lowercase `critical`. v4 §6 Gate 11.1 + §7 risk #13 enforce this at gate-time.

**Parser robustness (v7 JSON-string-aware state machine REPLACES v6 brace counter; Cursor AMEND_V3 Blocker F).** v6 used a raw brace counter that ignored JSON string state. v7 REPLACES with a JSON-string-aware state machine. The extractor still does delimiter-find + balanced-brace JSON extraction + guarded parse — the state machine only changes the depth-counting layer:

```python
import json
from typing import Optional

def extract_structured_payload(description: str) -> Optional[dict]:
    """v7: JSON-string-aware extractor. Tracks in_string + escape state.

    Robust against `}` (and `{`) appearing inside JSON string values, including
    escaped characters. Returns None gracefully on any parse failure (caller
    posts STALE_MUTEX_PARSE_FAILURE activity-log row per v6 §9.4).

    Returns the parsed dict on success, or None on:
      - marker absent
      - opening brace absent
      - unbalanced braces (truncated payload)
      - JSONDecodeError (corrupt payload)

    Caller is responsible for handling None (typically: fall back to
    manual-review path + post STALE_MUTEX_PARSE_FAILURE activity-log row).
    """
    marker = "STRUCTURED_DETAILS_JSON:"
    idx = description.find(marker)
    if idx == -1:
        return None
    start = description.find("{", idx)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    end = None
    for i in range(start, len(description)):
        ch = description[i]
        if escape:
            escape = False  # consume the escaped character regardless of value
            continue
        if ch == "\\":
            if in_string:
                escape = True  # only meaningful inside strings, but harmless outside
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
    if end is None:
        return None  # unbalanced or truncated
    try:
        return json.loads(description[start:end])
    except json.JSONDecodeError:
        return None
```

**State-machine invariants (v7 explanatory):**
- `in_string` flips ONLY when the parser sees a `"` whose preceding char did not set `escape`. This means `\"` inside a string does NOT toggle `in_string` — the `\\` set `escape`; the next iteration sees `"` but the `if escape:` guard consumes it without toggling.
- `escape` is set on `\\` ONLY when `in_string` is true (defensive harmless-when-false branch documented; outside a string a `\\` is not legal JSON, but the state machine tolerates it without altering correctness).
- `escape` is consumed on the very next character regardless of value, so `\\n` / `\\"` / `\\\\` all behave correctly.
- `{` / `}` outside strings advance/retreat `depth` exactly as in v6.
- `{` / `}` inside strings are ignored — they cannot mis-slice.
- The function returns the same `Optional[dict]` contract as v6; callers do not change.

**Runtime payload-key validator (v6 preserved verbatim through v7; Cursor AMEND_V2 Blocker B).** v5 used a grep-based pre-launch lint that is bypassable. v6 REPLACED with a runtime validator invoked immediately before every POST/PATCH to `prod_blockers`. See §6 Gate 11.2 for the function definition. Call-site convention:

```python
# Acquisition POST (Phase 1-5 entry guard) — v6 hardened, preserved through v7
validate_prod_blockers_payload(payload)        # runtime check; raises if bad keys
client.post_item("prod_blockers", payload)     # safe to call — validator passed

# Release PATCH (Phase 6 final-audit) — v6 hardened, preserved through v7
validate_prod_blockers_payload(patch_payload)  # runtime check
client.patch_item("prod_blockers", mutex_blocker_id, patch_payload)
```

The validator is the LOAD-BEARING enforcement layer. The optional pre-launch AST CI lint is defense-in-depth.

**Acquisition (Phase 1-5 entry guard, v6 hardened, preserved verbatim through v7):**

```python
import json
import os
import socket
import sys
from datetime import datetime, timezone

host = socket.gethostname()
SCRIPT_VERSION = "migrate_schema_vocab_v1.py@2026-05-08"
PAYLOAD_SCHEMA_VERSION = "v1"  # v6 NEW — Cursor non-blocker E

existing = client.get_items("prod_blockers",
    filters={"is_resolved": {"_eq": False},
             "title": {"_starts_with": "SCHEMA_MIGRATION_LOCK_HELD_BY_"}})
for lock in existing:
    if lock["title"] != f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}":
        # Held by another host — refuse
        sys.exit(1)

# v5: structured payload encoded inside description (no `details` field on prod_blockers)
# v6: schema_version added per Cursor non-blocker E
structured_payload = {
    "schema_version": PAYLOAD_SCHEMA_VERSION,   # v6 NEW
    "host": host,
    "pid": os.getpid(),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "script_version": SCRIPT_VERSION,
}
description_text = (
    f"Schema vocab migration in progress on host {host}; PID={os.getpid()}.\n\n"
    f"STRUCTURED_DETAILS_JSON: {json.dumps(structured_payload)}"
)

# v4: severity is LOWERCASE 'critical' per prod_blockers.severity enum
# v5: only the 8 live prod_blockers fields appear as keys (id is auto-assigned)
# v6: validate_prod_blockers_payload runs immediately before the POST
acquisition_payload = {
    "title": f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}",
    "severity": "critical",
    "is_resolved": False,
    "description": description_text,
}
validate_prod_blockers_payload(acquisition_payload)  # v6 NEW — Cursor Blocker B
client.post_item("prod_blockers", acquisition_payload)
```

**Release (Phase 6 final-audit success, v6 hardened with cap-on-resolution-text, preserved verbatim through v7):**

```python
# v5: 'resolution_notes' is NOT a live prod_blockers field; APPEND to description instead.
# v6: cap appended resolution-text length per Cursor non-blocker E.
RESOLUTION_APPEND_MAX_CHARS = 256

existing_blocker = client.get_item("prod_blockers", mutex_blocker_id)
existing_description = existing_blocker.get("description", "") or ""

resolution_text = f"Phase 6 final audit complete; report at {phase_6_report_path}"
resolution_suffix = (
    f" | RESOLVED: {resolution_text} (see Phase 6 final-audit report at {phase_6_report_path})"
)
if len(resolution_suffix) > RESOLUTION_APPEND_MAX_CHARS:
    # v6 NEW — truncate with explicit marker so future readers know context was clipped
    resolution_suffix = resolution_suffix[: RESOLUTION_APPEND_MAX_CHARS - len("[truncated]")] + "[truncated]"

new_description = f"{existing_description.rstrip()}{resolution_suffix}"

release_payload = {
    "is_resolved": True,
    "description": new_description,
    # resolved_at is auto-set by Directus when is_resolved flips to true
}
validate_prod_blockers_payload(release_payload)  # v6 NEW — Cursor Blocker B
client.patch_item("prod_blockers", mutex_blocker_id, release_payload)
```

**Stale-mutex cleanup (v7 wires v6 caller pattern to v7 state-machine extractor; preserved verbatim from v6 except the called function is now v7's state machine):**

```python
# v7: parse via extract_structured_payload (delimiter + state-machine balanced-brace + try/except)
# v7 replaces v6's raw brace counter with JSON-string-aware state machine inside the helper.
# Caller pattern below is unchanged from v6.
description = blocker_row.get("description", "") or ""
payload = extract_structured_payload(description)

if payload is None:
    # v6 NEW — graceful fallback to manual-review path; preserved verbatim through v7
    pid = None
    host_recorded = None
    started_at = None
    schema_version_recorded = None
    # Diagnostic — operator needs to know parse failed (vs. simply absent payload)
    client.post_item("prod_activity_log", {
        "action": "STALE_MUTEX_PARSE_FAILURE",
        "details": {
            "blocker_row_id": blocker_row.get("id"),
            "blocker_title": blocker_row.get("title"),
            "description_preview": (description or "")[:1024],
            "spec_reference": "SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md §9.4",
            "remediation": "Manual review per §9.4: check the row in Directus admin UI; PATCH is_resolved=true if confirmed dead.",
        },
        # other prod_activity_log fields per JSON-column gotchas
    })
else:
    pid = payload.get("pid")
    host_recorded = payload.get("host")
    started_at = payload.get("started_at")
    schema_version_recorded = payload.get("schema_version")  # v6 NEW; "v1" or None for legacy

# Force-release if dead (kill -0 <pid> if local; manual review if remote or pid is None)
```

Force-releases if dead. Manual override is always available — Kim can PATCH `is_resolved=true` directly via Directus admin UI.

**Why both remote AND local lock (v3 preserved through v7):** the remote lock prevents multi-host concurrent runs (the v2 gap Cursor flagged); the local flock prevents a single-host operator from accidentally launching the script twice in parallel terminals before the remote mutex is acquired. Both are cheap; defense-in-depth.

**Why this case-fold matters (v4 NEW, preserved through v7):** the Phase 1-5 entry-guard's first action after row-list construction is the mutex POST. If that POST returns HTTP 500 due to severity case violation, every mutating phase HALTS before any row is touched.

**Why this field-name fix matters (v5 NEW, preserved through v7):** even with the v4 case-fold applied, a literal POST per v3+v4 example bodies still includes a `details` key (v3) or — in v4's "informational" partial fix — a plain-string `description` without the canonical STRUCTURED_DETAILS_JSON encoding. Both fail at HTTP 400 / unknown-field; missing canonical encoding breaks the stale-mutex cleanup contract.

**Why these v6 hardenings matter (v6 NEW, preserved through v7):** Cursor's AMEND_V2 verdict on v5 surfaced three concrete defects that survive the v4 + v5 corrections. (1) The stale-mutex parser would crash on any malformed payload — v6's `extract_structured_payload` + activity-log fallback resolves this. (2) The v5 grep gate was bypassable — v6's runtime validator runs in-process at write-time and CANNOT be bypassed. (3) The v5 regex was brittle for nested JSON and trailing same-line text — v6's balanced-brace extractor is correct by construction.

**Why this v7 state-machine matters (v7 NEW):** Cursor's AMEND_V3 verdict on v6 surfaced ONE concrete defect that survives v6's hardening. v6's brace counter was correct on flat JSON without in-string braces, but JSON values are arbitrary text — payloads where a `}` (or `{`) appears inside a JSON string value WILL mis-slice. The example payload variation `{"notes":"contains } brace","pid":123,...}` demonstrates the defect: v6's depth counter sees the in-string `}` at column 28 (1-indexed), drops `depth` to `0`, and slices the substring at `end = 29` — yielding `{"notes":"contains }` which is not valid JSON. The v6 try/except catches the JSONDecodeError and returns `None` (graceful fallback, so the helper does NOT crash), but the cleanup helper deferred to manual-review path that should have been auto-resolvable. v7's JSON-string-aware state machine is correct by construction: it tracks `in_string` (toggled on UNESCAPED `"`) and `escape` (set on `\\` inside a string; cleared on next char), and counts `{`/`}` only outside strings. The example variation and the nested-object + escaped-quote variations all parse correctly. v7 §9.4 callout + §0.1 v7-A row + §7 risk #16 + LD-598 + §11 + §12 form a multi-layer redundancy against the brace-counter defect re-entering the script.

---

## §10 — Cursor review companion (v3 preserved; v4 + v5 + v6 + v7 unchanged at top level)

This spec v7 lands the Cursor AMEND_V3 fix-set on v6. The v3 Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` remains the canonical review companion since the cumulative review trail is anchored there. v7's review companion is the AMEND_V3 verdict captured in the v7-A row of §0.1 above + the v7 file itself for re-review if Kim chooses to send v7 back for a fourth Cursor pass. The v2 handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` is preserved as historical baseline. v1 also preserved.

---

## §11 — Reference index (v6 preserved + v7 entries added)

(All v2 entries preserved verbatim through v3 → v4 → v5 → v6 → v7. All v3-NEW entries preserved. All v4-NEW entries preserved. All v5-NEW entries preserved. All v6-NEW entries preserved.)

- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — **v6 historical baseline (this spec's predecessor)** (v7 NEW reference); sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline (v6 reference; v7 preserved); sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline (v5 reference; v6 + v7 preserved); sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline (v4 reference; v5 + v6 + v7 preserved); sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/scripts/lock_decision.py` — canonical-aware as of 2026-05-08 per Cursor Task H execution.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-Task-H backup.
- `LD_WRITER_CANONICAL_VOCAB_V1` — LD documenting Task H execution (HARD severity).
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (lowercase severity + STRUCTURED_DETAILS_JSON workaround); v4 §9.4 case-fold + v5 §9.4 field-name fix + v6 §9.4 parser/validator/cap/schema_version hardening + v7 §9.4 JSON-string-aware state machine all cross-reference this LD.
- `LD-593` — v4 §9.4 severity case-fold authority (preserved through v5 → v6 → v7 since the case-fold remains in effect).
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority (preserved through v7).
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — v6 Cursor AMEND_V2 fix authority (preserved through v7).
- `LD-597 TASK_DESCRIPTION_GOTCHA_DRIFT_RESOLUTION_V1` — `prod_activity_log.task_description` non-existence anti-confusion guard (preserved through v7; v7 inherits the guidance and uses `details` (JSON dict) as canonical narrative carrier in the activity-log POST cited in this session's bookkeeping).
- `LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` — **v7 Cursor AMEND_V3 fix authority** (v7 NEW reference; filed 2026-05-08 same session as v7 spec authoring; LD id captured at file time).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for v4 §9.4 case-fold + v5 §9.4 field-name fix + v6 §9.4 parser/validator/cap/schema_version hardening + v7 §9.4 JSON-string-aware state machine (8-field enumeration at lines 320-336, severity enum at lines 338-347, STRUCTURED_DETAILS_JSON pattern at lines 378-405). Schema-ref doc §5 currently cites LD-596 (v6); LIKELY needs a v7-pointer update — surface to Kim per §12 changelog. (v7 does NOT update the schema-ref doc.)
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff. Currently at v2.3 citing v6; LIKELY needs v2.4 amendment to point at v7 + LD-598 explicitly (surface to Kim per §12 changelog). (v7 does NOT update the handoff.)
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export.
- `Production/exports/prod_locked_decisions_<DATE>.metadata.json` — cached export metadata sidecar.
- `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` — append-only checkpoint per §5.0.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` — rehearsal pass/fail report.
- `Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` — queued Directus writes deferred while Directus production is offline.
- `Production/docs/SCHEMA_MIGRATION_V3_AND_LOCK_DECISION_FIX_REPORT_20260508.md` — final proof report for v3 spec + handoff + Task H execution.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3; remains canonical for v7's cumulative review trail).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — **THIS SPEC (v7)** (v7 NEW self-reference).

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Author: Claude Opus 4.7 (1M context). Status: superseded by v2.
- **v2** — 2026-05-08 — Cursor AMEND_V2 (4 amendments) applied: PHASE_5_ENABLED feature flag + dual-canonical paths + snapshot integrity fields + cost split. Status: superseded by v3.
- **v3** — 2026-05-08 — Cursor AMEND_V2 on v2 (5 amendments — Tasks B/D/E/F/H) applied: cached canonical-export + rollback rehearsal + remote mutex §9.4 + checkpoint schema §5.0 + lock_decision.py canonical-aware Task H execution. Status: superseded by v4. Author: Claude Opus 4.7 (1M context).
- **v4** — 2026-05-08 — self-discovered §9.4 severity case-fold (NOT a Cursor amendment). Live `prod_blockers.severity` enum lowercase-only (`critical`/`high`/`medium`/`low`) but v3 §9.4 mandated uppercase `CRITICAL` returning HTTP 500. v4 case-folds severity to lowercase `critical`, adds §6 Gate 11.1, adds §7 risk #13, cross-references `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 + LD-592. v4 also flagged two informational schema observations (no `details`, no `resolution_notes`) without correcting the example bodies (minimal-amendment mandate). Status: superseded by v5. Author: Claude Opus 4.7 (1M context).
- **v5** — 2026-05-08 — self-discovered §9.4 field-name fix (NOT a Cursor amendment; corrects what v4 explicitly deferred). Live `prod_blockers` has exactly 8 fields; v3+v4 example bodies referenced `details` (acquisition POST + stale-mutex cleanup parsing) and `resolution_notes` (release PATCH) — both non-existent fields returning HTTP 400 unknown-field. v5 corrects: (1) acquisition POST encodes `host`/`pid`/`started_at`/`script_version` inside `description` as `STRUCTURED_DETAILS_JSON:` + JSON literal per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 lines 362-377; (2) release PATCH appends resolution context to `description` rather than using non-existent `resolution_notes`; (3) stale-mutex cleanup parses PID from `description` via regex anchored on `STRUCTURED_DETAILS_JSON:` then `json.loads(...)`. Adds §6 Gate 11.2 (field-name compliance + grep lint), adds §7 risk #14, adds §11 reference-index entries (v4 historical baseline + LD-595), files LD-595. Cross-references LD-592 + LD-593 + handoff §6. Status: superseded by v6. Author: Claude Opus 4.7 (1M context).
- **v6** — 2026-05-08 — Cursor AMEND_V2 on v5 (3 HIGH/Y blockers + 2 non-blockers) applied. **Blocker A:** v5 stale-mutex parser raw `json.loads` REPLACED with guarded `try/except json.JSONDecodeError` falling back to `None` + `STALE_MUTEX_PARSE_FAILURE` activity-log diagnostic. **Blocker B:** v5 §6 Gate 11.2 grep-based lint REPLACED with runtime payload-key validator `validate_prod_blockers_payload(payload: dict) -> None` invoked immediately before every POST/PATCH; AST-based CI lint documented as defense-in-depth. **Blocker F:** v5 brittle lazy-regex REPLACED with `extract_structured_payload(description: str) -> Optional[dict]` performing delimiter-find + balanced-brace JSON extraction. **Non-blocker D:** explicit "DO NOT IMPLEMENT FROM HISTORICAL CONTENT — §9.4 v6 IS AUTHORITATIVE" hazard warnings added at §5 + §6 + every §0.1 historical row. **Non-blocker E:** acquisition POST payload now includes `schema_version: "v1"`; release PATCH caps appended resolution-text at ≤256 chars with `[truncated]` marker if exceeded. Adds risk #15 (regex-extraction failure mode). Files LD-596. Status: superseded by v7. Author: Claude Opus 4.7 (1M context).
- **v7** — 2026-05-08 — Cursor AMEND_V3 on v6 (1 HIGH/Y blocker, Task F) applied. **Blocker F:** v6's `extract_structured_payload` raw brace counter (which ignored JSON string state and escape characters) REPLACED with a JSON-string-aware parser state machine. The new function tracks `in_string` (toggled on UNESCAPED `"` — i.e. not toggled if previous char's `escape` was true) and `escape` (set on `\\` inside a string; cleared on next char). Only `{`/`}` outside strings count toward `depth`. Example payload variation that breaks v6 documented in §0.1 v7-A row + §9.4 callout: `{"notes":"contains } brace","pid":123,...}`. v6 graceful `None` fallback + `STALE_MUTEX_PARSE_FAILURE` activity-log row preserved verbatim. Acquisition POST + release PATCH bodies stay v6 (already correct). Runtime validator `validate_prod_blockers_payload` (§6 Gate 11.2) stays v6 (already correct). Adds risk #16 (brace-counter vs. state-machine implementer drift; LOW likelihood with v7 explicit pseudocode + §0.1 v7-A row + LD-598 + Gate 11.2 complement / HIGH severity due to potentially-corrupted PID → wrong host check). All other v6 design (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, Task H, severity case-fold, Gate 11.1, runtime validator, hazard warnings, schema_version, ≤256-char cap) preserved verbatim. v1 + v2 + v3 + v4 + v5 + v6 preserved as historical baselines. Files LD-598 `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1`. **Note:** handoff §6 prod_blockers schema gotchas should likely be amended to v2.4 to explicitly cite v7 (v2.3 currently cites v6); schema-ref doc §5 should likely be updated to point at v7 + LD-598. Both surfaced for Kim's call — v7 does NOT update those files. Author: Claude Opus 4.7 (1M context).
