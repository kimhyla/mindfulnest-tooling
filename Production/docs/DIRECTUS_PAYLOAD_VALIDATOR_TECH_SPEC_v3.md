# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v3

**Authored:** 2026-05-08
**Author:** Claude Opus 4.7 (1M context)
**Status:** DESIGN ONLY — execution gated on Kim approval per §6
**Self-classification:** ARCHITECTURAL (per zero-error-qa DS-26 / tech-spec skill v2 §0.1)
**Scope:** Generic schema-aware payload validator covering ALL `prod_*` Directus collections
**Generalizes:** v6 narrow validator pattern (`validate_prod_blockers_payload`) one architectural layer up
**Supersedes:** `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md` (sha256 `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b`) — preserved as historical baseline.
**Motivation for v3:** Cursor cross-review of v2 returned a HIGH classification-bug finding on §9.2. v2's reference implementation calls `if not path.exists(): return {}` BEFORE attempting `path.read_text()`. `Path.exists()` returns False for broken symlinks, so a broken symlink resolves down the Case A (file absent) branch instead of Case E (permission denied / I/O error) — silently no-op'ing instead of producing the §9.2 diagnostic that Case E mandates. This breaks v2's "single deterministic case per failure mode" guarantee. v3 restructures §9.2 with explicit symlink detection: a NEW Case A1 (broken symlink) is classified BEFORE Case A via `path.lstat()` + `path.is_symlink()` checks, with its own normative path (log + activity-log + return `{}`). v2's HIGH finding also surfaced a MEDIUM placeholder issue: `LD-NEW` was used as a placeholder for the v2 spec-LD across §11; concrete LD-604 is now substituted everywhere. v3 corrects ONLY: §0.1 (changelog row v3-A), §7 (NEW risk #12 — implementer copies v2's reference impl literally), §9.2 (5-case table → 6-case table + Case A1 NEW + reference implementation rewritten with `lstat` + `is_symlink` + `exists` ordering), §11 (`LD-NEW` → `LD-604` find-and-replace + v2 historical baseline + v3 self-reference + LD-NEW for v3's own LD), §12 (changelog row), §14 (checklist row for new gate not added — Case A1 is implementation correctness, not policy). All other v2 design (Decisions 1-8, Phases 0/1/2/3/4/5, Gates 1-11, Risks 1-11, §1/§2/§3/§4/§5/§6/§8/§9.1/§9.3/§9.4/§10/§13/§15/§16) is **preserved verbatim by reference** to v2; only sections that needed updating got rewritten.

---

## §0.1 — Authoring changelog (v3-A row above v2-A row above v1 row)

| Version | Date | Change |
|---------|------|--------|
| **v3-A** | **2026-05-08** | **Cursor cross-review of v2 returned a HIGH Case-E classification-bug finding + a MEDIUM `LD-NEW` placeholder finding. HIGH: v2's §9.2 reference implementation calls `if not path.exists(): return {}` BEFORE attempting to read the file; `Path.exists()` returns False for broken symlinks, so a broken symlink resolves as Case A (file absent) instead of Case E (permission denied / I/O error) — breaks the "single deterministic case per failure mode" guarantee. v3 fixes: §9.2 restructures the case taxonomy with explicit symlink detection — NEW Case A1 (broken symlink: `path.lstat()` succeeds + `path.is_symlink()` True + `path.exists()` False) is classified BEFORE Case A; reference implementation rewritten using `lstat` → `is_symlink` + `exists` → `read_text` ordering so each failure mode lands in exactly one case. §7 NEW risk #12 (implementer copies v2's reference impl literally; broken symlink misclassifies as Case A; LIKELIHOOD LOW with v3 explicit case table + Case A1; SEVERITY MEDIUM — silent miss-classification of operator override file state). §11 reference index `LD-NEW` placeholder replaced with concrete `LD-604` (~5 occurrences) + v2 historical baseline (sha256 `047b5efd...`) + v3 self-reference + new LD-NEW for v3's own spec-LD. §12 changelog row appended. §14 checklist updated for v3 (no new policy gate — Case A1 is reference-implementation correctness, not a new operator-facing decision). v2 sha256 `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b` recorded for drift detection. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V3_CASE_E_SYMLINK_FIX_V1`. Cursor v2 review findings addressed: `case_e_symlink` (HIGH) + `ld_new_placeholder` (MEDIUM). All other v2 design preserved verbatim by reference.** |
| v2-A | 2026-05-08 | Cursor cross-review of v1 returned `AMEND_V2` (single Task E blocker — malformed override file behavior undefined). v2 fixes: §9.2 full rewrite enumerating 5 cases (absent / valid / malformed-JSON / malformed-layout / permission-denied) with single normative path (fail-safe default + diagnostic + activity-log row); §3 NEW Decision 8 dual-Opus debate (fail-safe vs fail-loud) → synthesis: fail-safe default + opt-in fail-loud env var; §5 Phase 1 deliverable adds 4-fixture test (valid / invalid-JSON / invalid-layout-not-dict / invalid-layout-bad-key); §6 NEW Gate 11 (override-file fail-mode policy approval); §7 NEW risk #11 (override-file silent-fallback masking user intent); §11 reference index appends v1 historical baseline + LD-NEW + Cursor review outputs; §12 changelog appends v2 row. v1 sha256 `14ae4e22b653...` recorded for drift detection. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1` (LD-604 confirmed live in v3 authoring `(my probe)`). |
| v1 | 2026-05-08 | Initial spec authored. 7 design decisions debated (§3); per-decision action table (§4); 6-phase rollout (§5); 10 pre-implementation gates (§6); 10 risks (§7); per-phase rollback (§8); operational notes + override file + dog-fooding bypass (§9); Cursor cross-review companion flagged as follow-up (§10). Companion LD-599 `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` filed alongside. Preserved as historical baseline. |

---

## §0 — Operating Mode (preserved verbatim from v2)

This document is **DESIGN ONLY**. No code is written, no scripts are executed, no Directus rows are PATCHed, no LDs except the v3 spec-LD itself are filed during the authoring of this spec. v3 inherits v2's §0 binding scope unchanged. Self-bound list at end of v3 handoff prompt is binding for the v3 session.

[CONFIRMED — v3 self-bound list explicitly forbids modifying v1 spec, v2 spec, prior schema-migration specs (v1-v7), implementation handoff, schema-ref doc, weekly_preflight, settings.json, hook scripts, payload_validator.py (doesn't exist), Cursor review outputs, prior LD records.]

## §0.2 — Self-classification (preserved verbatim from v2)

**ARCHITECTURAL.** v3 inherits v2's §0.2 self-classification rationale unchanged: cross-cutting infrastructure helper called by ≥10 scripts; failure mode is Layer 6 (input/output variation enforcement); broad-by-default behavior change. The v3 amendments (Case A1 broken-symlink classification + reference implementation reordering + LD-604 substitution) DO NOT change the architectural blast radius — they tighten one operational edge case that Cursor flagged as a HIGH classification bug, plus correct a placeholder reference.

---

## §1 — Goal (preserved verbatim from v2)

See `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md` §1 (which itself preserves v1 §1 by reference). v3 inherits §1 (Goal + Non-goals 1-5 + Bounded by 30-collection inventory) unchanged.

---

## §2 — Background (preserved verbatim from v2)

See v2 §2 (which preserves v1 §2 by reference). v3 inherits §2.1, §2.2, §2.3, §2.4 unchanged.

---

## §3 — Dual-Opus debate (8 decisions; preserved verbatim from v2)

See v2 §3 — Decisions 1-8 preserved verbatim. v3 introduces NO new design decisions; the Case A1 broken-symlink classification fix is reference-implementation correctness, not a new operator-facing policy. Decision 8's fail-safe-vs-fail-loud synthesis remains binding for Case A1: when `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` is set, broken symlinks raise `OverrideFileMalformedError(path, "broken_symlink", None)`; otherwise return `{}` per fail-safe default.

---

## §4 — Per-decision action table (preserved verbatim from v2)

See v2 §4 — 8-row table preserved verbatim. v3 adds no new rows.

---

## §5 — Implementation sequence (preserved verbatim from v2)

See v2 §5 — Phases 0/1/2/3/4/5 preserved verbatim. v3 adds NO new Phase deliverables, but Phase 1 implementer MUST follow v3 §9.2 reference implementation (NOT v2's) to avoid the Case E classification bug. Phase 1 unit-test deliverable is augmented in v3 §9.2 below with one additional fixture: **broken-symlink fixture** asserting Case A1 resolution. The 4-fixture test from v2 becomes a 5-fixture test in v3 (valid / invalid-JSON / invalid-layout-not-dict / invalid-layout-bad-key / **broken-symlink**) per v3 §9.2 normative path. Fail-loud env-var test extends to assert broken-symlink raises `OverrideFileMalformedError(path, "broken_symlink", None)` when env var set.

---

## §6 — Pre-implementation gates Kim must approve (preserved verbatim from v2)

See v2 §6 — 11-row gate table preserved verbatim. v3 adds no new gates; the Case A1 fix is implementation correctness, not a new operator-facing policy decision. Gates 1-11 from v2 remain binding for Phase 1 implementation. The v3-amended Phase 1 deliverable (5-fixture test instead of 4) flows through Gate 11 (Decision 8 fail-mode policy) without modification — Case A1 is one more file-state branch covered by the same fail-safe-default-plus-opt-in-fail-loud policy.

---

## §7 — Risk assessment (v3 extends v2's 11-row table to 12 rows)

The table below preserves v2 rows 1-11 verbatim and appends row 12 (NEW for v3 — implementer copies v2's reference implementation literally, broken symlink misclassifies as Case A).

| # | Risk | Likelihood | Severity | Mitigation |
|---|------|------------|----------|------------|
| 1 | Existing script breakage on Phase 4 strict promotion (caller passes extra fields that have been silently dropping for months) | MEDIUM | HIGH | §5 Phase 3 warn-mode sweep with zero-warning exit criterion; Phase 4 only fires after Phase 3 returns clean. |
| 2 | Schema cache staleness producing false-positives during a migration window | MEDIUM | MEDIUM | §3 Decision 2 verdict: 15-min TTL + `invalidate_schema_cache()` hook called at every migration phase boundary. |
| 3 | Performance impact on high-volume callers (`prod_activity_log` writes) | LOW | LOW | 15-min cache reduces steady-state probe count to ≤30/hour across a 30-collection codebase; benchmark in Phase 1 gate. |
| 4 | Probe failure on Directus outage producing hard halt | MEDIUM | MEDIUM | §3 Decision 4 verdict: fail-closed at validator + queue-on-fail at `try_post_or_queue`; same offline tolerance as POST failure. |
| 5 | Race condition between schema migration (v3-v7 chain) and validator probe | LOW | HIGH | Validator probes AFTER each migration phase commits + explicit `invalidate_schema_cache()` call at phase boundaries; per-collection override mode `'skip'` for fields-in-flux during a Phase 4-style remap. |
| 6 | Auto-generated field stripping causing missing-data bug (caller WANTED to backdate) | LOW | HIGH | §3 Decision 6 verdict: explicit `allow_auto_field_overrides=True` flag + audit row on every strip; backdating use cases must opt-in deliberately. |
| 7 | Over-broad opt-out catching legitimate edge-case writes (debug script writing experimental fields to a sandbox collection) | LOW | LOW | Override file (`~/.claude/state/payload_validator_overrides.json`) supports per-collection `mode='skip'` + `extra_allowed_keys=[...]`. |
| 8 | Validator's own activity-log writes silently fail (dog-fooding circular dependency) | LOW | HIGH | Validator's writes go through `try_post_or_queue` which goes through the validator → infinite recursion risk. Mitigation: validator's OWN activity-log writes use a `_VALIDATOR_INTERNAL_BYPASS=True` thread-local flag that skips the validator on that one call. Documented in §9 Operational notes. |
| 9 | Retired-field grace registry drifts (author forgets to register a retired field at retirement time) | MEDIUM | MEDIUM | Schema-migration spec template gets a new mandatory checklist item: "If this migration retires any field, register it in `RETIRED_FIELDS_REGISTRY` in `Production/lib/payload_validator.py` with retire_date." |
| 10 | Per-process cache inconsistency (one Python process is on stale cache while another has fresh cache) | LOW | LOW | Acceptable per §5.0 invariants — each process is serial within itself; cross-process consistency only matters for parallel-write scenarios which are rare in this codebase (writes are mostly single-process). |
| 11 | Override file becomes malformed in production (concurrent edit by another script, partial-write crash, accidental hand-edit typo) and validator silently falls back to defaults; operator assumes their `'warn'` or `'skip'` override is active but it isn't. | LOW (override file is a config file, edited rarely — typically only at migration-window boundaries) | MEDIUM (incorrect mode = strict-when-`'warn'`-expected → false-rejects on legitimate writes during a migration; OR `'warn'`-when-`'strict'`-expected → silent_write_failure recurs on the very class the validator was designed to prevent) | (1) v2 §9.2 single normative path enumerating 5 cases + v3 §9.2 6-case extension with Case A1; (2) `prod_activity_log` row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` queued via `try_post_or_queue` on every fall-to-defaults event with `details` dict (NO `task_description`) per LD-597; (3) ERROR-level log line to `~/.claude/state/payload_validator.log`; (4) Phase 1 5-fixture test (per v3) covers every malformed branch including broken symlink; (5) opt-in fail-loud env var `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud`; (6) §6 Gate 11 surfaces the policy decision to Kim explicitly. |
| **12** | **NEW v3 — Implementer copies v2's reference implementation literally; broken symlink misclassifies as Case A (file absent) instead of Case E (I/O error) because v2's reference impl calls `if not path.exists(): return {}` before any read attempt, and `Path.exists()` returns False on broken symlinks. Result: silent miss-classification of operator override file state — broken symlink produces no log line, no activity-log row, no `OverrideFileMalformedError` even when `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` is set. Operator's intent is silently lost, breaks v2's "single deterministic case per failure mode" guarantee.** | **LOW (with v3 §9.2 explicit case table + Case A1 + reference impl using `lstat` + `is_symlink` ordering; the bug only resurfaces if a future implementer reverts to `path.exists()`-first ordering)** | **MEDIUM (silent miss-classification of operator override file state — same severity class as Risk #11; operator's `'warn'` or `'skip'` override silently lost when override file is a broken symlink, e.g., after a `~/.claude/state` directory rename or a manually-created symlink whose target was later deleted)** | **(1) v3 §9.2 6-case table makes Case A1 (broken symlink) explicit and ordered BEFORE Case A — single deterministic resolution; (2) v3 §9.2 reference implementation rewritten using `path.lstat()` + `path.is_symlink()` + `path.exists()` ordering so broken symlinks are caught at lstat-stat-vs-exists divergence, before any read attempt; (3) v3 §5 Phase 1 augmented test deliverable adds broken-symlink fixture (5th fixture) — `tmp_path / "broken_link"` symlinked to `tmp_path / "nonexistent"` then `Path.unlink(tmp_path / "nonexistent")` so the symlink dangles; assertion: `_load_override_file()` returns `{}` (fail-safe) + log line + activity-log row with `reason='broken_symlink'`; with env var `loud`, asserts `OverrideFileMalformedError(path, "broken_symlink", None)` raised; (4) v3 §9.2 normative table is the source of truth — reference implementation is non-normative per v2 §9.2 disclaimer preserved verbatim into v3.** |

**Top 3 risks by severity-x-likelihood (v3-updated):**
1. **Risk #1 — Existing script breakage on Phase 4 promotion** (MEDIUM × HIGH). Mitigated by Phase 3 sweep gate.
2. **Risk #5 — Migration race condition** (LOW × HIGH). Mitigated by explicit invalidation hook.
3. **Risk #8 — Dog-fooding recursion** (LOW × HIGH). Mitigated by `_VALIDATOR_INTERNAL_BYPASS` flag.

Risk #11 (NEW v2) and Risk #12 (NEW v3) do NOT enter the top-3 because severity is MEDIUM (not HIGH); both are bounded by the rarity-of-edit pattern + the diagnostic + the opt-in fail-loud env var. Risk #12 is additionally bounded by the v3 reference-implementation rewrite.

---

## §8 — Rollback per phase (preserved verbatim from v2)

See v2 §8 (which preserves v1 §8 by reference). v3 inherits the per-phase rollback table unchanged. The Phase 1 v3 amendments (5th fixture for broken-symlink + reference implementation reordering) are deliverables-only and rollback the same way as v1/v2 Phase 1: delete `Production/lib/payload_validator.py` + companion test.

---

## §9 — Operational notes

### §9.1 — Debug toggle env var (preserved verbatim from v2)

`MN_PAYLOAD_VALIDATOR_DISABLE=1` — when set in environment, validator is a no-op. For one-off debug + emergency hotfix scenarios. NOT for production-tracked scripts. Documented in CLAUDE.md Rule 35 sub-section per Phase 5.

### §9.2 — Per-collection override file (REWRITTEN for v3 to fix Case E broken-symlink classification bug surfaced by Cursor v2 review)

**Path:** `~/.claude/state/payload_validator_overrides.json` (absolute path resolved via `Path("~/.claude/state/payload_validator_overrides.json").expanduser()`).

**File schema (when present + valid):**
```json
{
  "<collection_name>": {
    "mode": "strict | warn | skip",
    "extra_allowed_keys": ["additional_key_1", "additional_key_2"],
    "max_payload_size_bytes": 65536,
    "_note": "human-readable rationale; not parsed"
  }
}
```

**Layout-validation rules** (preserved verbatim from v2 §9.2; enforced by `_validate_override_layout(parsed) -> bool`):
1. Top-level value MUST be a dict.
2. Each top-level key MUST be a string starting with `prod_` (validator-relevant collection names only).
3. Each top-level value MUST be a dict.
4. Each sub-dict MAY contain ONLY the keys `mode`, `extra_allowed_keys`, `max_payload_size_bytes`, `_note`. Any other sub-key triggers layout-invalid.
5. If `mode` is present, it MUST be one of `{"strict", "warn", "skip"}`.
6. If `extra_allowed_keys` is present, it MUST be a list of strings.
7. If `max_payload_size_bytes` is present, it MUST be a non-negative int.
8. `_note` (if present) is opaque (string or any value); always ignored by the parser.

**Single normative path for the 6 file-state cases** (v3 EXTENDS v2's 5-case table with NEW Case A1 — broken symlink — classified BEFORE Case A; fixes the HIGH bug Cursor surfaced on v2 where broken symlinks misclassified as Case A):

| # | File state | Detection method | Behavior |
|---|------------|------------------|----------|
| **A** | **File truly absent** (no entry at path; not a symlink, not a broken symlink) | `path.lstat()` raises `FileNotFoundError` | Return `{}`. Use defaults for all collections. No log line. No activity-log row. (v1/v2 baseline preserved.) |
| **A1** | **Broken symlink** (symlink exists but target does not — the symlink path-entry is present, but `path.exists()` is False because exists follows the symlink) | `path.lstat()` succeeds (symlink path-entry exists) AND `path.is_symlink()` returns True AND `path.exists()` returns False | **NEW v3.** Default fail-safe path: emit ERROR log line; queue activity-log row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` via `try_post_or_queue` (with `_VALIDATOR_INTERNAL_BYPASS=True` per §9.3); return `{}` (fail-safe). If `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` env var is set, raise `OverrideFileMalformedError(path, "broken_symlink", None)` instead of returning `{}`. |
| **B** | **File present + valid JSON + valid layout** | `path.exists()` True AND `read_text()` succeeds AND `json.loads(content)` succeeds AND `_validate_override_layout(parsed)` returns True | Return parsed dict. No log line. No activity-log row. (v1/v2 baseline preserved.) |
| **C** | **File present + JSON parse fails** | `read_text()` succeeds AND `json.loads(content)` raises `json.JSONDecodeError` | Default fail-safe path: emit ERROR log line; queue activity-log row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` via `try_post_or_queue` (with `_VALIDATOR_INTERNAL_BYPASS=True`); return `{}` (fail-safe). If `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud`, raise `OverrideFileMalformedError(path, "json_parse_error", e)` instead. (v2 baseline preserved.) |
| **D** | **File present + JSON parses but layout invalid** | `_validate_override_layout(parsed)` returns False (top-level not a dict, unknown sub-key, bad `mode` value, non-list `extra_allowed_keys`, etc.) | Default fail-safe path: emit ERROR log line with `layout_error=<describe_layout_failure(parsed)>`; queue activity-log row with `layout_error` in details; return `{}`. If env var `loud`, raise `OverrideFileMalformedError(path, "layout_invalid", reason)` instead. (v2 baseline preserved.) |
| **E** | **File present + permission denied / I/O error** (chmod 000, ACL block, transient I/O failure — NOT broken symlinks; those resolve to Case A1 above) | `path.lstat()` succeeds AND `path.exists()` True AND `path.read_text()` raises `OSError` (excluding `FileNotFoundError` which would have surfaced at lstat) | Default fail-safe path: emit ERROR log line with `reason=<OSError str>`; queue activity-log row with `os_error` in details; return `{}`. If env var `loud`, raise `OverrideFileMalformedError(path, "permission_denied", e)` instead. **v3 NOTE: broken symlinks no longer land here; v2 ambiguity resolved via NEW Case A1 above.** |

**Resolution-order invariant** (v3 NEW): the case dispatcher MUST follow the order `A → A1 → E (read-failure) → C (parse-failure) → D (layout-failure) → B (success)`. The `lstat`-then-`is_symlink`-then-`exists` ordering ensures Case A1 (broken symlink) is detected BEFORE Case A (truly absent) and Case E (I/O error). The reference implementation below encodes this order. Each case has exactly one deterministic resolution path — no failure mode can be classified into two different cases.

**Diagnostic format** (cases A1, C, D, E) — preserved from v2 §9.2 with one v3 addition:

- **Log line** (appended to `~/.claude/state/payload_validator.log`, ERROR level):
  ```
  [PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED] <iso8601-utc> path=<absolute-path> reason=<broken_symlink | json-parse-error | layout-error-description | os-error-string>
  ```
  v3 NOTE: `reason=broken_symlink` is the v3-NEW value; cases C/D/E reasons unchanged from v2.

- **Activity-log row** (POSTed to `prod_activity_log` via `try_post_or_queue` with `_VALIDATOR_INTERNAL_BYPASS=True` per §9.3):
  - `action`: `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED`
  - `details` (dict — NO `task_description` per LD-597; uses ONLY fields valid for `prod_activity_log`'s 11-field schema):
    - `path`: absolute path string of the override file
    - `content_sha256`: sha256 of the raw file content (or `null` if `OSError` or broken-symlink prevented reading)
    - `parse_error`: JSON decode error message string (case C only; absent for A1/D/E)
    - `layout_error`: layout-failure description string (case D only; absent for A1/C/E)
    - `os_error`: OSError string (case E only; absent for A1/C/D)
    - `symlink_target`: result of `os.readlink(str(path))` if Case A1 (v3 NEW); absent for C/D/E
    - `attempted_at`: ISO-8601 UTC timestamp of the load attempt
    - `recovery_action`: `"defaults_used"` (default fail-safe path) OR `"raised_OverrideFileMalformedError"` (fail-loud env var path)
    - `fail_mode`: `"safe"` (default) OR `"loud"` (env var set)
    - `case`: `"A1"` | `"C"` | `"D"` | `"E"` (v3 NEW — explicit case-id for telemetry traceability)
  - `module_id`: null (validator is a global helper, not module-specific)
  - `performed_by`: `"payload_validator"` (validator's identity for audit trail)

**Re-read frequency:** preserved from v2 — override file is read at module-import time AND on every call to `invalidate_schema_cache()`. Re-reads pay the malformed-handling cost again per the 6-case table above.

**Env-var opt-in to fail-loud:** preserved from v2:
- `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` — when set, cases A1/C/D/E raise `OverrideFileMalformedError(path, kind, cause)` instead of returning `{}`. v3 NEW: `kind="broken_symlink"` is the Case A1 value.
- `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE` unset OR set to anything other than `loud` (including `safe`, `default`, empty string) → default fail-safe path for ALL malformed cases (A1/C/D/E).

**Reference implementation** (v3 — REWRITTEN to fix Cursor's HIGH classification-bug finding on v2; lstat → is_symlink → exists → read_text → loads → validate ordering ensures Case A1 is caught before Case A; not normative — the §9.2 6-case table above is normative):

```python
def _load_override_file() -> dict:
    """Load per-collection override config. v3 normative path per §9.2 6-case table.

    Resolution order (v3): A → A1 → E (read) → C (parse) → D (layout) → B.
    Fix vs v2: `path.exists()` is NEVER called before `path.lstat()`, because
    `exists()` returns False for broken symlinks and would misclassify them as
    Case A (truly absent) instead of Case A1 (broken symlink — distinct case).
    """
    path = Path("~/.claude/state/payload_validator_overrides.json").expanduser()

    # Case A vs A1: lstat first — distinguishes "no entry at path" from "symlink with dead target"
    try:
        path.lstat()  # raises FileNotFoundError ONLY if path-entry truly absent
    except FileNotFoundError:
        return {}  # Case A: truly absent — no log, no activity-log row

    # Case A1: path-entry exists; if it's a symlink AND exists() (which follows the link) is False,
    # then the symlink target is missing → broken symlink. Detect BEFORE attempting read_text.
    if path.is_symlink() and not path.exists():
        _log_malformed_override(path, None, "broken_symlink", None)
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "broken_symlink", None)
        return {}  # Case A1 (fail-safe)

    # At this point: path-entry exists AND (not a symlink, OR symlink with valid target).
    # Defensive guard: if exists() is False here despite lstat success and not a broken symlink,
    # it's a TOCTOU race (file vanished between lstat and now). Treat as Case A.
    if not path.exists():
        return {}  # Case A: defensive (TOCTOU vanish)

    # Case E: read failure (permission denied, I/O error)
    try:
        content = path.read_text()
    except OSError as e:
        _log_malformed_override(path, None, "permission_denied", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "permission_denied", e)
        return {}  # Case E (fail-safe)

    # Case C: JSON parse failure
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        _log_malformed_override(path, content, "json_parse_error", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "json_parse_error", e)
        return {}  # Case C (fail-safe)

    # Case D: layout invalid
    if not _validate_override_layout(parsed):
        reason = _describe_layout_failure(parsed)
        _log_malformed_override(path, content, "layout_invalid", reason)
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "layout_invalid", reason)
        return {}  # Case D (fail-safe)

    return parsed  # Case B: success
```

**Decision flowchart** (v3 — companion to the 6-case table; expresses resolution-order invariant graphically):

```
                        _load_override_file()
                                 |
                                 v
                       path.lstat() succeeds?
                       /                    \
                     no                     yes
                      |                      |
              [Case A: return {}]            v
                                  path.is_symlink()
                                  AND not path.exists()?
                                  /                  \
                                yes                  no
                                 |                    |
                  [Case A1: log+actlog,               v
                   return {} | raise]        path.exists()?
                                                /        \
                                              no         yes
                                               |          |
                                  [Case A defensive:      v
                                   return {}]    read_text() OSError?
                                                       /        \
                                                     yes         no
                                                      |           |
                                          [Case E: log+actlog,    v
                                           return {} | raise]  json.loads JSONDecodeError?
                                                                  /         \
                                                                yes          no
                                                                 |            |
                                                  [Case C: log+actlog,        v
                                                   return {} | raise]  layout valid?
                                                                          /         \
                                                                        no          yes
                                                                         |           |
                                                              [Case D: log+actlog,   v
                                                               return {} | raise] [Case B: return parsed]
```

**Test coverage** (Phase 1 deliverable per §5 v3 augmentation): **5-fixture test** (valid + invalid-JSON + invalid-layout-not-dict + invalid-layout-bad-key + **broken-symlink** NEW v3) + 1 fail-loud env-var test extended to assert broken-symlink path raises `OverrideFileMalformedError(path, "broken_symlink", None)`. Broken-symlink fixture authored via `pathlib.Path.symlink_to` then `Path.unlink` of the target so the symlink dangles. Assertion: `_load_override_file()` returns `{}` with env var unset; raises with env var set; activity-log row contains `case="A1"` + `symlink_target` field per v3 details schema.

### §9.3 — Logging strategy (dog-fooding the validator) (preserved verbatim from v2)

See v2 §9.3 (which preserves v1 §9.3 by reference). v3 inherits the `_VALIDATOR_INTERNAL_BYPASS` thread-local pattern unchanged. The v3 Case A1 broken-symlink activity-log row queue uses this bypass identically to Cases C/D/E per v2 §9.3.

### §9.4 — Telemetry expected post-Phase-4 (preserved verbatim from v2)

See v2 §9.4 — five-row telemetry list preserved verbatim. v3 NOTE: row 5 (`PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` per-day count) now includes Case A1 broken-symlink events; operators reading telemetry should disambiguate via `details.case` field per v3 §9.2 details schema.

---

## §10 — Cursor cross-review companion handoff (UPDATED for v3)

The v2 §10 noted Cursor's v1 review verdict was `AMEND_V2`. v3 has been authored in response to Cursor's v2 cross-review which surfaced one HIGH classification bug + one MEDIUM placeholder issue:

- **Cursor v2 review HIGH finding:** §9.2 Case E classification bug — broken symlinks misclassify as Case A because v2's reference impl calls `path.exists()` before any read attempt; `Path.exists()` returns False for broken symlinks. v3 fixes via §9.2 NEW Case A1 + reference impl reorder.
- **Cursor v2 review MEDIUM finding:** v2 references `LD-NEW` placeholder in §11. v3 substitutes concrete LD-604 (verified live `(my probe)` 2026-05-08; status=active; decision_key matches) across §11 reference index.

**Cursor v3 review authorship:** RECOMMENDED before Phase 1 implementation begins per v2 §6 Gate 10 (preserved). The v3 Case A1 fix is an implementation-correctness amendment; future Cursor v3 review handoff path: `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_v3_20260508.md` (NOT authored in this v3 session per self-bound list).

---

## §11 — Reference index (v3 substitutes `LD-NEW` → `LD-604` everywhere + appends new entries)

**Preserved from v2 §11 with `LD-NEW` → `LD-604` substitution applied** (v2 used `LD-NEW` as a placeholder for the v2 spec-LD that was filed alongside v2 authoring; v3 substitutes the live, confirmed LD-604):

- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/directus.py` — where `try_post_or_queue`, `post_item_verified`, `_validate_json_columns`, `JSON_COLUMN_INVENTORY` live; Phase 2 wire-up edits this file.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/directus_admin_client.py` — `DirectusAdminClient._request('GET', f'/fields/{collection}')` is the schema probe endpoint.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Phase 5 cross-reference target.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` §6 Gate 11.2 — narrow validator pattern this generalizes.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — v7 spec; LD-598.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff template post-LD-597 anti-confusion guards.
- `/Users/kimberlysmith/.claude/skills/zero-error-qa/SKILL.md` — DS-13 Layer 6, DS-19, DS-26, DS-27, DS-28, DS-29.
- `/Users/kimberlysmith/.claude/skills/tech-spec/SKILL.md` v2 — §0 + §14 + §15 + §16 mandates.
- **LD-595** (`SCHEMA_VOCAB_MIGRATION_V5_FIELD_NAME_FIX`).
- **LD-596** (`SCHEMA_VOCAB_MIGRATION_V6_RUNTIME_VALIDATOR`).
- **LD-597** (`TASK_DESCRIPTION_FIELD_ANTI_CONFUSION_GUARDS_V1`) — binding on v3 activity-log details dict (NO `task_description`).
- **LD-598** (`SCHEMA_VOCAB_MIGRATION_V7_JSON_STRING_AWARE_EXTRACTOR`).
- **LD-364** (`POST_ITEM_VERIFIED_V1`).
- **LD-599** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1`) — v1 spec-LD; verified live 2026-05-08 `(my probe)` per v2 §11.
- **LD-604** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1`) — v2 spec-LD; verified live 2026-05-08 `(my probe)`: id=604, decision_key matches, status=`active`, severity=SOFT, task_category=governance, source_document=`Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md`. **v3 substitutes this concrete LD-604 for v2's `LD-NEW` placeholder** (~5-10 occurrences across v2 §10/§11/§12/§14/§0.1 — v3 carries forward the corrected reference everywhere v2 referenced its own spec-LD).

**NEW for v3** (appended below):

- **`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md`** — v3's historical baseline; sha256 `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b`; 407 lines; authored 2026-05-08. v3 inherits Decisions 1-8, Phases 0/1/2/3/4/5, Gates 1-11, Risks 1-11 verbatim.
- **`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v3.md`** — this document (self-reference); supersedes v2; addresses Cursor v2 review HIGH finding (Case E broken symlink) + MEDIUM finding (LD-NEW placeholder).
- **LD-NEW** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V3_CASE_E_SYMLINK_FIX_V1`) — this v3's spec-LD; filed in this v3 session per §0 Operating Mode; documents the Case A1 NEW + reference-impl reorder + `LD-NEW`→`LD-604` substitution scope.

---

## §12 — Changelog (v3 appends one row to v2)

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-05-08 | Initial spec authored. 7 design decisions debated (§3); per-decision action table (§4); 6-phase rollout (§5); 10 pre-implementation gates (§6); 10 risks (§7); per-phase rollback (§8); operational notes + override file + dog-fooding bypass (§9); Cursor cross-review companion flagged as follow-up (§10). Companion LD-599 `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` filed alongside. |
| v2 | 2026-05-08 | Address Cursor cross-review AMEND_V2 verdict on v1 (single Task E blocker — malformed override file behavior undefined). Changes: §9.2 full rewrite enumerating 5 file-state cases with single normative path (fail-safe default + diagnostic + activity-log row) + opt-in fail-loud env var `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud`. §3 NEW Decision 8 dual-Opus debate (fail-safe vs fail-loud). §5 Phase 1 deliverable adds 4-fixture override-file test + 1 fail-loud env-var test. §6 NEW Gate 11. §7 NEW risk #11. §11 + §12 + §14 augmented. Companion LD-604 (verified live in v3 session). |
| **v3** | **2026-05-08** | **Address Cursor cross-review of v2 (HIGH classification bug on §9.2 Case E + MEDIUM `LD-NEW` placeholder). Changes: §9.2 6-case table (NEW Case A1 broken symlink classified BEFORE Case A; reference impl rewritten using `lstat` + `is_symlink` + `exists` ordering so each failure mode lands in exactly one case; resolution-order invariant + decision flowchart added). §7 NEW risk #12 (implementer copies v2 reference impl literally → broken symlink misclassifies as Case A; LIKELIHOOD LOW with v3 explicit case table; SEVERITY MEDIUM). §11 reference index `LD-NEW` placeholder substituted with concrete LD-604 (verified live `(my probe)` 2026-05-08; status=active) — applies wherever v2 referenced its own spec-LD; v2 historical baseline appended (sha256 `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b`); v3 self-reference appended; new LD-NEW for v3 spec-LD. §12 this row. §5 Phase 1 deliverable augmented from 4-fixture to 5-fixture test (broken-symlink fixture added) — implementation correctness, not new policy. §14 checklist row for v3 spec-LD filing. All other v2 design preserved verbatim by reference. v2 baseline sha256 `047b5efd...` recorded for drift detection. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V3_CASE_E_SYMLINK_FIX_V1` filed alongside. Cursor v2 findings addressed: `case_e_symlink` (HIGH) + `ld_new_placeholder` (MEDIUM).** |

---

## §13 — Cross-references (preserved verbatim from v2)

See v2 §13 (which preserves v1 §13 by reference). v3 inherits cross-references unchanged.

---

## §14 — Pre-execution checklist (v3 extends v2's checklist with one row for v3 spec-LD)

The checklist below preserves v2 rows verbatim and appends one row for the v3 spec-LD.

- [ ] §6 Gate 1 — Decision 1 verdict (strict end-state, phased path) approved.
- [ ] §6 Gate 2 — Decision 2 verdict (15-min TTL + invalidator hook) approved.
- [ ] §6 Gate 3 — Decision 3 verdict (separate `lib/payload_validator.py`) approved.
- [ ] §6 Gate 4 — Decision 4 verdict (fail-closed + queue-on-fail) approved.
- [ ] §6 Gate 5 — Decision 5 verdict (opt-out always-on + override file) approved.
- [ ] §6 Gate 6 — Decision 6 verdict (strip auto-fields with audit + override flag) approved.
- [ ] §6 Gate 7 — Decision 7 verdict (14-day grace for registered-retired fields) approved.
- [ ] §6 Gate 8 — §5 phased rollout (Phase 0 → 5) approved.
- [ ] §6 Gate 9 — Phase 4 strict-promotion gated on Phase 3 zero-warning sweep.
- [ ] §6 Gate 10 — Cursor cross-review handoff authored + Cursor verdict received (v1: complete with `AMEND_V2`; v2: complete with HIGH+MEDIUM findings; v3: pending — see §10).
- [ ] §6 Gate 11 — Decision 8 verdict (override-file fail-mode policy: fail-safe default + opt-in fail-loud env var) approved. (v3: still binding; Case A1 inherits this policy.)
- [ ] All 12 risks in §7 reviewed and mitigations approved (especially Risk #1, #5, #8 — top 3 by severity; Risk #11 reviewed for adequacy; **Risk #12 NEW v3 reviewed for adequacy of v3 reference-impl reorder**).
- [ ] §0 Operating Mode acknowledged (DESIGN ONLY this session; implementation gated).
- [ ] LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1` (LD-604) confirmed filed (verified live in v3 session `(my probe)`).
- [ ] **LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V3_CASE_E_SYMLINK_FIX_V1` confirmed filed (filing in this v3 session per spec-LD POST below).**
- [ ] Activity-log row `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V3_AUTHORED_V1` confirmed filed.
- [ ] v2 baseline sha256 `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b` recorded; drift detection confirms v2 untouched during v3 authoring (`(my probe)` per v3 final report).
- [ ] v1 baseline sha256 `14ae4e22b653...` re-confirmed unchanged at v3 authoring (`(my probe)` per v3 final report).

---

## §15 — Audit (preserved verbatim from v2; v3 appends one new line)

Preserves v2 §15 seven-row audit list verbatim. v3 appends:

8. **NEW v3** — Override-file Case A1 broken-symlink smoke test: Phase 1 unit test verifies all 6 cases (A/A1/B/C/D/E) per v3 §9.2 normative path + verifies fail-loud env var raises `OverrideFileMalformedError(path, "broken_symlink", None)` correctly. Test asserts `_load_override_file()` returns `{}` (fail-safe) for case A1 when env var unset, and raises when env var set to `loud`. Activity-log row contains `case="A1"` + `symlink_target` field. Reference implementation in v3 §9.2 verified to follow `lstat → is_symlink → exists → read_text` ordering so broken symlinks are caught before `path.exists()` is consulted on the resolved-target path.

---

## §16 — Reference index — external docs + APIs (preserved verbatim from v2)

See v2 §16 (which preserves v1 §16 by reference). v3 inherits Directus schema API, Directus collections API, `functools.lru_cache`, `threading.local()`, `pathlib.Path` references unchanged.

---

## Authoring metadata

- **Spec author:** Claude Opus 4.7 (1M context)
- **Authoring session date:** 2026-05-08 (v3; same calendar day as v1, v2, Cursor v1 review, Cursor v2 review)
- **Authoring branch:** claude/gallant-bouman-804b4f (worktree)
- **v2 baseline sha256:** `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b` — confirmed unchanged at v3 authoring start `(my probe)`.
- **v2 baseline size:** 407 lines — confirmed `(my probe)`.
- **v1 baseline sha256:** `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75` — confirmed unchanged through v2/v3 authoring `(per v2 metadata + v3 self-bound list)`.
- **LD-604 live verification:** confirmed live 2026-05-08 `(my probe)`: id=604, decision_key=`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1`, status=`active`, severity=`SOFT`, task_category=`governance`, source_document=`Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md`.
- **Self-bound list compliance:** confirmed; v3 modifies ONLY the new v3 file + v3 spec-LD POST + v3 activity-log POST. NO modifications to v1 spec, v2 spec, prior schema-migration specs (v1-v7), implementation handoff, schema-ref doc, weekly_preflight, settings.json, hook scripts, payload_validator.py (doesn't exist), Cursor review outputs, prior LD records (LD-599, LD-604).
- **Cursor v2 review findings addressed:** HIGH `case_e_symlink` (broken-symlink misclassification) + MEDIUM `ld_new_placeholder` (concrete LD-604 substituted).
- **Wave A live-schema probe timestamp:** 2026-05-08 (this v3 session — LD-604 verified live `(my probe)`).
- **Wave A inventory file:** [DEFERRED — Phase 0 deliverable per v1 §5.1 Phase 0 unchanged through v2/v3.]

[CONFIRMED — every claim in v3 is anchored to a live-schema probe (LD-604), an existing file (v2 spec sha256, v1 spec sha256), or an explicit synthesis paragraph. DS-29 source tagging applied throughout (`(my probe)` for live verification, `(agent claim)` not used in v3 — v3 has no agent-derived claims). Confidence tags applied per zero-error-qa Rule 24 + DS-29.]
