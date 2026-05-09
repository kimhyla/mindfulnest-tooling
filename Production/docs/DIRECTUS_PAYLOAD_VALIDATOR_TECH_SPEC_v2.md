# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v2

**Authored:** 2026-05-08
**Author:** Claude Opus 4.7 (1M context)
**Status:** DESIGN ONLY — execution gated on Kim approval per §6
**Self-classification:** ARCHITECTURAL (per zero-error-qa DS-26 / tech-spec skill v2 §0.1)
**Scope:** Generic schema-aware payload validator covering ALL `prod_*` Directus collections
**Generalizes:** v6 narrow validator pattern (`validate_prod_blockers_payload`) one architectural layer up
**Supersedes:** `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md` (sha256 `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`) — preserved as historical baseline.
**Motivation for v2:** Cursor cross-review of v1 returned `AMEND_V2` with one Task E blocker — `§9.2` documented missing-override-file behavior (defaults) but did **NOT** define behavior when the override file is present and JSON parse / layout is invalid. v2 corrects ONLY `§9.2` (full rewrite), `§3` (NEW Decision 8 dual-Opus debated), `§5 Phase 1` (4-fixture test added), `§6` (NEW Gate 11), `§7` (NEW risk #11), `§11/§12` (reference index + changelog updated). All other v1 design (Decisions 1-7, Phases 0/2/3/4/5, Gates 1-10, Risks 1-10, §1/§2/§4/§8/§9.1/§9.3/§9.4/§10/§13/§14/§15/§16) is **preserved verbatim by reference** to v1; only sections that needed updating got rewritten.

---

## §0.1 — Authoring changelog (v2-A row above v1 row)

| Version | Date | Change |
|---------|------|--------|
| **v2-A** | **2026-05-08** | **Cursor cross-review of v1 returned `AMEND_V2` (single Task E blocker — malformed override file behavior undefined). v2 fixes: §9.2 full rewrite enumerating 5 cases (absent / valid / malformed-JSON / malformed-layout / permission-denied) with single normative path (fail-safe default + diagnostic + activity-log row); §3 NEW Decision 8 dual-Opus debate (fail-safe vs fail-loud) → synthesis: fail-safe default + opt-in fail-loud env var; §5 Phase 1 deliverable adds 4-fixture test (valid / invalid-JSON / invalid-layout-not-dict / invalid-layout-bad-key); §6 NEW Gate 11 (override-file fail-mode policy approval); §7 NEW risk #11 (override-file silent-fallback masking user intent); §11 reference index appends v1 historical baseline + LD-NEW + Cursor review outputs; §12 changelog appends v2 row. v1 sha256 `14ae4e22b653...` recorded for drift detection. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1`. Cursor review outputs at `Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md` + `Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_REPORT_20260508.md`.** |
| v1 | 2026-05-08 | Initial spec authored. 7 design decisions debated (§3); per-decision action table (§4); 6-phase rollout (§5); 10 pre-implementation gates (§6); 10 risks (§7); per-phase rollback (§8); operational notes + override file + dog-fooding bypass (§9); Cursor cross-review companion flagged as follow-up (§10). Companion LD-599 `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` filed alongside. Preserved as historical baseline. |

---

## §0 — Operating Mode (preserved verbatim from v1)

This document is **DESIGN ONLY**. No code is written, no scripts are executed, no Directus rows are PATCHed, no LDs except the spec-LD itself are filed during the authoring of this spec. v2 inherits v1's §0 binding scope unchanged. Self-bound list at end of v2 handoff prompt is binding for the v2 session.

[CONFIRMED — v2 self-bound list explicitly forbids modifying v1 spec, prior schema-migration specs (v1-v7), implementation handoff, schema-ref doc, weekly_preflight, settings.json, hook scripts, payload_validator.py (doesn't exist), Cursor review outputs.]

## §0.2 — Self-classification (preserved verbatim from v1)

**ARCHITECTURAL.** v2 inherits v1's §0.1 self-classification rationale unchanged: cross-cutting infrastructure helper called by ≥10 scripts; failure mode is Layer 6 (input/output variation enforcement); broad-by-default behavior change. The v2 amendments (override-file fail-mode + diagnostic) DO NOT change the architectural blast radius — they tighten one operational edge case that Cursor flagged as ambiguous.

---

## §1 — Goal (preserved verbatim from v1)

See `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md` §1 (lines 31-46). v2 inherits §1 (Goal + Non-goals 1-5 + Bounded by 30-collection inventory) unchanged.

---

## §2 — Background (preserved verbatim from v1)

See v1 §2 (lines 49-75). v2 inherits §2.1 (two silent_write_failure incidents on 2026-05-08), §2.2 (v6 narrow validator verbatim 3-line quote), §2.3 (why per-collection narrow validators don't scale), §2.4 (LD-597 anti-confusion guards already shipped) unchanged.

---

## §3 — Dual-Opus debate (8 decisions in v2; Decisions 1-7 preserved verbatim from v1)

### Decisions 1-7 (preserved verbatim from v1)

See v1 §3 (lines 79-165). v2 inherits Decisions 1-7 verbatim:
- **Decision 1** — Strict reject vs permissive warn-only default → HYBRID with phased promotion (`mode='warn'` for Phase 2-3, flip to `'strict'` in Phase 4 after zero-warning sweep).
- **Decision 2** — Schema cache TTL → 15-minute default + explicit `invalidate_schema_cache()` hook for migration scripts.
- **Decision 3** — Validator location → separate `Production/lib/payload_validator.py` module + one import in `lib/directus.py::try_post_or_queue`.
- **Decision 4** — Probe-failure mode → fail-closed at validator + queue-on-fail at `try_post_or_queue` wrapper.
- **Decision 5** — Opt-in vs opt-out per collection → opt-out always-on + per-collection override file at `~/.claude/state/payload_validator_overrides.json`.
- **Decision 6** — Auto-generated / read-only field handling → strip with warning + audit row + explicit `allow_auto_field_overrides=True` flag for backdating.
- **Decision 7** — Retired-field grace period → 14-day grace for registered-retired fields; immediate-reject for unregistered unknowns; `RETIRED_FIELDS_REGISTRY` lives in `Production/lib/payload_validator.py`.

### Decision 8 — Malformed override file: fail-safe (defaults + log + activity-log) vs fail-loud (raise + halt validator init) — NEW v2

**Advocate (fail-safe by default — return `{}` + log + activity-log + continue with defaults):** The override file is a config file edited rarely (intended for migration-window exceptions per Decision 5 verdict). If it gets corrupted (concurrent edit by another script, partial-write crash, accidental hand-edit typo), the validator's normal job — preventing silent_write_failure on every Directus write across the codebase — should NOT be blocked by an unrelated config-file integrity issue. Fail-safe means: log an ERROR-level entry to `~/.claude/state/payload_validator.log`, queue an activity-log row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` to `prod_activity_log` via `try_post_or_queue` (visible in next `weekly_preflight_audit` sweep), return `{}` (treat as if file absent), and continue executing per default modes. The user surfaces the malformed file via the diagnostic (log + activity-log row), fixes it, and the validator self-heals on next module-import or cache-invalidation.

The fail-safe posture also matches the established offline-tolerance pattern in `try_post_or_queue` (per LD-364 + Decision 4 synthesis): when an upstream dependency (Directus, override file, schema probe) is in a failure state, the system continues the primary path (Directus writes) and queues / logs the secondary concern. Fail-safe on override-file load preserves Kim's normal workflow during the rare moment when the override file is in a transient bad state.

**Counter (fail-loud — raise `OverrideFileMalformedError` + halt validator init):** Silent fall-back to defaults could mask a real intent. Suppose Kim explicitly added a `mode='warn'` override for `prod_phase_b_scripts` during a schema-migration window (Decision 5 use case). If the override file gets corrupted between the time Kim authored the override and the time the next Directus write fires, the validator silently falls back to `'strict'` defaults — which means Kim's intended `'warn'` override IS NOT IN EFFECT. The Phase 2-3 sweep depends on operator-controlled `'warn'` mode for migration-window exceptions; silent fallback to `'strict'` defaults breaks the operator's mental model and reintroduces the production-blocking surprise that Decision 5's override-file mechanism was supposed to prevent.

Fail-loud forces the operator to fix the malformed file before any Directus write proceeds. The cost (one halted script during the rare malformed-file window) is bounded; the benefit (operator's intent is mechanically preserved, never silently overridden) matches the validator's fail-loud doctrine elsewhere (Decision 1 strict-reject; Decision 4 fail-closed at validator). Internally consistent: every other validator failure mode raises; override-file load should match.

**Synthesis verdict — Hybrid: fail-safe is the v2 default; opt-in fail-loud via env var.** The Advocate's fail-safe argument wins as the **default** because (a) the override file is a config file edited rarely, so the malformed-state window is short; (b) the diagnostic (log + activity-log row + `recovery_action="defaults_used"`) gives the operator a high-signal recovery path; (c) blocking ongoing Directus writes during a config-file corruption is a worse user experience than transparently using defaults + surfacing the issue. The Counter's "operator's intent silently lost" concern is real and is addressed via opt-in: operators who want fail-loud (e.g., during a high-stakes schema-migration window where intended overrides MUST be respected) can set `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` in their environment. When the env var is set to `loud`, the validator raises `OverrideFileMalformedError` on parse failure / layout failure / permission-denied; otherwise it falls back to defaults per the fail-safe path. The env var is documented in `§9.2` v2 and surfaced in CLAUDE.md Rule 35 sub-section per Phase 5. Headline argument: **fail-safe default + diagnostic; fail-loud opt-in via env var for migration-window operators**.

---

## §4 — Per-decision action table (v2 extends v1's 7-row table to 8 rows)

The table below preserves v1 rows 1-7 verbatim and appends row 8 (NEW Decision 8 verdict).

| # | Decision | Verdict | One-sentence rationale | Depends-on | Risk class |
|---|----------|---------|------------------------|------------|------------|
| 1 | Strict vs permissive default | **Strict end-state via Phase-3 warn-mode sweep** | Matches fail-loud doctrine of `_validate_json_columns` + `post_item_verified` + v6 narrow validator | §5 Phase 3 sweep zero-warning return | HIGH (Phase 4 promotion is the load-bearing change) |
| 2 | Schema cache TTL | **15-min default + explicit `invalidate_schema_cache()` hook for migration scripts** | Long-enough to amortize, short-enough to bound cross-phase drift | Migration scripts call invalidator at phase boundaries | MEDIUM (cache drift inside one migration phase) |
| 3 | Validator location | **Separate `Production/lib/payload_validator.py` module** | Single responsibility; testable in isolation; keeps `lib/directus.py` from growing into a god-module | Wire-up: one import in `lib/directus.py::try_post_or_queue` | LOW (file-organization choice) |
| 4 | Probe-failure mode | **Fail-closed at validator + queue-on-fail at wrapper** | Validator's job is to prevent silent failures; offline-queue integration preserves operator UX | `try_post_or_queue` catches `SchemaProbeError` → queues with `reason='schema_probe_failure'` | MEDIUM (Directus partial-outage edge case) |
| 5 | Opt-in vs opt-out | **Opt-out always-on + override file** | Generalization point is broad-by-default coverage; per-collection override handles migration-window edge cases | `~/.claude/state/payload_validator_overrides.json` | MEDIUM (migration-window collection deregistration) |
| 6 | Auto-field handling | **Strip with warning + audit + explicit override flag** | Silent-strip violates validator's own anti-silent-failure principle; audit preserves traceability | `prod_activity_log` row `PAYLOAD_VALIDATOR_AUTO_FIELD_STRIPPED` per strip | LOW (well-understood pattern via existing `_AUTO_FIELDS`) |
| 7 | Retired-field grace | **14-day grace for registered-retired fields; immediate-reject for unregistered unknowns** | Bounds migration window without permanent soft-failure | Schema-migration author registers retired field at retirement time | MEDIUM (depends on author discipline) |
| **8** | **Malformed override file: fail-safe default vs fail-loud** | **Fail-safe default (return `{}` + log + activity-log + continue) + opt-in fail-loud via `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud`** | **Fail-safe matches offline-tolerance pattern; opt-in fail-loud preserves operator intent during high-stakes migration windows** | **§9.2 v2 normative path; env var honored at module-import + cache-invalidation; §6 Gate 11** | **MEDIUM (operator's `'warn'` override silently lost during malformed-file window if env var unset)** |

[CONFIRMED — v2 row 8 verdict derived from §3 Decision 8 dual-Opus debate; rationale summarizes the headline argument from the synthesis paragraph.]

---

## §5 — Implementation sequence (v2 amends Phase 1 only; other phases preserved verbatim from v1)

### §5.0 — Caching invariants (preserved verbatim from v1)

See v1 §5.0 (lines 187-196). v2 inherits cache structure, invalidation triggers, cross-process consistency note, cache-miss behavior, probe-failure behavior unchanged.

### §5.1 — Phase plan (6 phases; Phase 1 amended in v2; Phases 0/2/3/4/5 preserved verbatim from v1)

**Phase 0 — Snapshot current Directus writes across the codebase.** (preserved verbatim from v1 — see v1 §5.1 lines 200-205.)

**Phase 1 — Author the validator function** in `Production/lib/payload_validator.py` per Decision 3 verdict. (v2 amendment below preserves all v1 Phase 1 deliverables and adds the 4-fixture test for malformed override file per Decision 8 verdict.)

- Module exports: `validate_payload(collection, payload, mode='strict|warn|skip') -> dict` (returns `{stripped_auto_fields: [...], retired_fields_used: [...]}` for caller inspection); `invalidate_schema_cache(collection: Optional[str]=None) -> None`; `_load_override_file() -> dict` (private helper invoked at module-import + cache invalidation; v2 implements per §9.2 normative path); `SchemaProbeError`, `UnknownPayloadKeyError`, `RetiredPayloadKeyError`, `OverrideFileMalformedError` (NEW v2 — raised only when `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud`) exceptions.
- Schema cache via module-scope dict + 15-min TTL per Decision 2.
- Reads `~/.claude/state/payload_validator_overrides.json` at module-import time + on cache invalidation, via `_load_override_file()` per §9.2 v2 normative path.
- Override file schema (validated by `_validate_override_layout`): top-level dict; each key is a `prod_*` collection name; each value is a dict with optional keys `mode` ∈ `{strict, warn, skip}`, `extra_allowed_keys` (list of strings), `max_payload_size_bytes` (int), `_note` (string, ignored by parser).
- `RETIRED_FIELDS_REGISTRY: dict[str, dict[str, str]]` per Decision 7.
- Auto-field handling per Decision 6: re-uses `_AUTO_FIELDS` from `lib/directus.py` (recommend duplicate locally to keep `payload_validator` independent).
- **NEW v2 — Phase 1 unit test deliverable: 4-fixture override-file test** in `Production/lib/tests/test_payload_validator.py::test_load_override_file_malformed_handling`. Fixtures (created via `tmp_path` / `pytest` monkey-patch of `Path.expanduser`):
  1. **Valid fixture** — `{"prod_blockers": {"mode": "warn", "extra_allowed_keys": ["debug_field"]}}` → assert `_load_override_file()` returns the parsed dict; no log line; no activity-log row queued.
  2. **Invalid-JSON fixture** — file contents `{prod_blockers: not valid json` → assert `_load_override_file()` returns `{}`; assert log line matches `[PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED] <iso8601> path=<absolute-path> reason=<json-decode-error-message>`; assert one activity-log row queued with `action='PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED'` + `details` dict (NO `task_description`) containing `path`, `content_sha256`, `parse_error`, `attempted_at`, `recovery_action='defaults_used'`.
  3. **Invalid-layout (not-dict) fixture** — file contents `["just", "a", "list"]` → assert `_load_override_file()` returns `{}`; assert log line + activity-log row as above with `layout_error='top-level not a dict'`.
  4. **Invalid-layout (bad-key) fixture** — file contents `{"prod_blockers": {"mode": "INVALID", "unknown_subkey": 1}}` → assert `_load_override_file()` returns `{}`; assert log line + activity-log row with `layout_error` describing both bad-mode + unknown-subkey.
- **NEW v2 — Phase 1 fail-loud env-var test** in same test module: `test_load_override_file_fail_loud_env_var`. Set `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` via monkey-patch; with the invalid-JSON fixture, assert `_load_override_file()` raises `OverrideFileMalformedError` (does NOT return `{}`). Unset env var; with same fixture, assert returns `{}` per default fail-safe path.
- Phase 1 deliverable (v2): `Production/lib/payload_validator.py` (~280 LOC est., +30 LOC over v1 estimate for `_load_override_file` + `_validate_override_layout` + `_describe_layout_failure` helpers + `OverrideFileMalformedError` exception) + companion `Production/lib/tests/test_payload_validator.py` (added 5 test fixtures: 4-fixture malformed test + fail-loud env-var test).

**Phase 2 — Wire into `try_post_or_queue`.** (preserved verbatim from v1 — see v1 §5.1 lines 216-222.)

**Phase 3 — Run inventory scripts in `mode='warn'` for a sweep.** (preserved verbatim from v1 — see v1 §5.1 lines 224-229.)

**Phase 4 — Promote to `mode='strict'` per Decision 1 verdict.** (preserved verbatim from v1 — see v1 §5.1 lines 231-235.)

**Phase 5 — Document the validator in CLAUDE.md Rule 35 + schema-ref doc + memory file.** (preserved verbatim from v1 — see v1 §5.1 lines 237-241; v2 augments the Phase 5 deliverable with one additional CLAUDE.md sub-section line documenting the `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` env var per §9.2 v2.)

[CONFIRMED — v2 phase additions are localized to Phase 1 (test fixtures + new private helpers) + Phase 5 (one extra doc line). Other phases unchanged. Dependency order preserved per DS-28: Phase 0 → 1 → 2 → 3 → 4 → 5.]

---

## §6 — Pre-implementation gates Kim must approve (v2 extends v1's 10-gate table to 11 rows)

The table below preserves v1 rows 1-10 verbatim and appends row 11 (NEW for v2 — override-file fail-mode policy).

| # | Gate | Kim's decision required |
|---|------|------------------------|
| 1 | **Decision 1 verdict — strict end-state via phased path.** Default mode `'warn'` for Phase 2-3, promote to `'strict'` in Phase 4 after zero-warning sweep. | YES (proceed per verdict) / DEFER (stay warn-only forever) / NO (different policy) |
| 2 | **Decision 2 verdict — 15-min TTL + `invalidate_schema_cache()` hook.** | YES / DEFER (use 1-hour TTL like `lock_decision.py`) / NO (per-write probe) |
| 3 | **Decision 3 verdict — separate `Production/lib/payload_validator.py` module.** | YES / DEFER (co-locate in `lib/directus.py`) / NO (other location) |
| 4 | **Decision 4 verdict — fail-closed at validator + queue-on-fail at `try_post_or_queue` wrapper.** | YES / DEFER (fail-open warn-mode) / NO |
| 5 | **Decision 5 verdict — opt-out always-on + per-collection override file at `~/.claude/state/payload_validator_overrides.json`.** | YES / DEFER (opt-in registry) / NO |
| 6 | **Decision 6 verdict — strip auto-fields with warning + audit row + explicit `allow_auto_field_overrides=True` flag for backdating.** | YES / DEFER (reject auto-fields without strip) / NO (silent strip per Advocate) |
| 7 | **Decision 7 verdict — 14-day grace for registered-retired fields; immediate-reject for unregistered unknowns; `RETIRED_FIELDS_REGISTRY` lives in `Production/lib/payload_validator.py`.** | YES / DEFER (no grace period — block immediately) / NO (longer grace period) |
| 8 | **§5 phased rollout sequence approved (Phase 0 → 1 → 2 → 3 → 4 → 5).** | YES / NO (alternative phasing) |
| 9 | **§5 Phase 4 strict-promotion gated on Phase 3 zero-warning sweep return.** | YES (REQUIRED — Phase 4 cannot fire without Phase 3 clean) / NO (different gating) |
| 10 | **Cursor cross-review of this spec before Phase 1 implementation begins.** Reserved path: `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`. | YES (REQUIRED — blast radius is broad; second-opinion review reduces design-risk) / DEFER (skip Cursor review; proceed directly to Phase 0) / NO |
| **11** | **NEW v2 — Decision 8 verdict — Override file fail-mode policy approved.** Default = fail-safe (return `{}` + log + activity-log row + continue with defaults). Operators may opt into fail-loud via `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` env var (raises `OverrideFileMalformedError` instead of returning `{}`). | **YES (proceed per Decision 8 synthesis — fail-safe default + opt-in fail-loud) / DEFER (fail-loud as default, no env var opt-in for fail-safe) / NO (different policy)** |

Each gate gets a Kim verdict before §5 phases proceed. Gate 9 is the hard pre-condition for Phase 4 (zero-warning sweep is verified before strict-mode flip). Gate 11 (NEW v2) is a hard pre-condition for Phase 1 implementation: the implementer must know the malformed-override-file behavior (default fail-safe vs operator-opt-in fail-loud) before authoring `_load_override_file()`.

---

## §7 — Risk assessment (v2 extends v1's 10-row table to 11 rows)

The table below preserves v1 rows 1-10 verbatim and appends row 11 (NEW for v2 — malformed override file silent-fallback masking user intent).

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
| **11** | **NEW v2 — Override file becomes malformed in production (concurrent edit by another script, partial-write crash, accidental hand-edit typo) and validator silently falls back to defaults; operator assumes their `'warn'` or `'skip'` override is active but it isn't.** | **LOW** (override file is a config file, edited rarely — typically only at migration-window boundaries) | **MEDIUM** (incorrect mode = strict-when-`'warn'`-expected → false-rejects on legitimate writes during a migration; OR `'warn'`-when-`'strict'`-expected → silent_write_failure recurs on the very class the validator was designed to prevent) | **(1) v2 §9.2 single normative path enumerating 5 cases (absent / valid / malformed-JSON / malformed-layout / permission-denied) with deterministic fail-safe behavior; (2) `prod_activity_log` row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` queued via `try_post_or_queue` on every fall-to-defaults event with `details` dict (NO `task_description`) containing `path`, `content_sha256`, `parse_error` or `layout_error`, `attempted_at`, `recovery_action='defaults_used'`; (3) ERROR-level log line to `~/.claude/state/payload_validator.log`; (4) Phase 1 4-fixture test (valid + invalid-JSON + invalid-layout-not-dict + invalid-layout-bad-key) covers every malformed branch; (5) opt-in fail-loud env var `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` for migration-window operators who require their intent be respected at hard-halt cost; (6) §6 Gate 11 surfaces the policy decision to Kim explicitly.** |

**Top 3 risks by severity-x-likelihood (v2-updated):**
1. **Risk #1 — Existing script breakage on Phase 4 promotion** (MEDIUM × HIGH). Mitigated by Phase 3 sweep gate.
2. **Risk #5 — Migration race condition** (LOW × HIGH). Mitigated by explicit invalidation hook.
3. **Risk #8 — Dog-fooding recursion** (LOW × HIGH). Mitigated by `_VALIDATOR_INTERNAL_BYPASS` flag.

Risk #11 (NEW v2) does NOT enter the top-3 because severity is MEDIUM (not HIGH); it is bounded by the rarity-of-edit pattern + the diagnostic + the opt-in fail-loud env var.

---

## §8 — Rollback per phase (preserved verbatim from v1)

See v1 §8 (lines 290-299). v2 inherits the per-phase rollback table unchanged. The Phase 1 v2 amendments (4-fixture test + `_load_override_file` helper) are deliverables-only and rollback the same way as v1 Phase 1: delete `Production/lib/payload_validator.py` + companion test.

---

## §9 — Operational notes

### §9.1 — Debug toggle env var (preserved verbatim from v1)

`MN_PAYLOAD_VALIDATOR_DISABLE=1` — when set in environment, validator is a no-op. For one-off debug + emergency hotfix scenarios. NOT for production-tracked scripts. Documented in CLAUDE.md Rule 35 sub-section per Phase 5.

### §9.2 — Per-collection override file (FULL REWRITE for v2 per Cursor AMEND_V2 Task E blocker)

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

**Layout-validation rules** (enforced by `_validate_override_layout(parsed) -> bool`):
1. Top-level value MUST be a dict.
2. Each top-level key MUST be a string starting with `prod_` (validator-relevant collection names only).
3. Each top-level value MUST be a dict.
4. Each sub-dict MAY contain ONLY the keys `mode`, `extra_allowed_keys`, `max_payload_size_bytes`, `_note`. Any other sub-key triggers layout-invalid.
5. If `mode` is present, it MUST be one of `{"strict", "warn", "skip"}`.
6. If `extra_allowed_keys` is present, it MUST be a list of strings.
7. If `max_payload_size_bytes` is present, it MUST be a non-negative int.
8. `_note` (if present) is opaque (string or any value); always ignored by the parser.

**Single normative path for the 5 file-state cases** (NEW v2 — defines behavior Cursor flagged as undefined in v1):

| # | File state | Behavior |
|---|------------|----------|
| **A** | **File absent** (`Path.exists()` returns False) | Return `{}`. Use defaults for all collections. No log line. No activity-log row. (v1 baseline preserved.) |
| **B** | **File present + valid JSON + valid layout** | Return parsed dict. No log line. No activity-log row. (v1 baseline preserved.) |
| **C** | **File present + JSON parse fails** (`json.JSONDecodeError` on `json.loads(content)`) | Default fail-safe path: emit ERROR log line; queue activity-log row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` via `try_post_or_queue` (with `_VALIDATOR_INTERNAL_BYPASS=True` per §9.3 to prevent dog-fooding recursion); return `{}` (treat as if file absent — fail-safe to defaults rather than fail-loud during validator init). If `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` env var is set, raise `OverrideFileMalformedError(path, "json_parse_error", e)` instead of returning `{}`. |
| **D** | **File present + JSON parses but layout invalid** (`_validate_override_layout(parsed)` returns False — e.g., top-level not a dict, unknown sub-key, bad `mode` value, non-list `extra_allowed_keys`) | Default fail-safe path: same as case C — emit ERROR log line with `layout_error=<describe_layout_failure(parsed)>`; queue activity-log row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` with `layout_error` in details; return `{}`. If `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` env var is set, raise `OverrideFileMalformedError(path, "layout_invalid", reason)` instead. |
| **E** | **File present + permission denied** (`OSError` on `path.read_text()` — e.g., chmod 000, ACL block, broken symlink) | Default fail-safe path: same as case C/D — emit ERROR log line with `reason=<OSError str>`; queue activity-log row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` with `os_error` in details; return `{}`. If `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` env var is set, raise `OverrideFileMalformedError(path, "permission_denied", e)` instead. |

**Diagnostic format** (cases C/D/E):

- **Log line** (appended to `~/.claude/state/payload_validator.log`, ERROR level):
  ```
  [PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED] <iso8601-utc> path=<absolute-path> reason=<json-parse-error | layout-error-description | os-error-string>
  ```

- **Activity-log row** (POSTed to `prod_activity_log` via `try_post_or_queue` with `_VALIDATOR_INTERNAL_BYPASS=True` per §9.3):
  - `action`: `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED`
  - `details` (dict — NO `task_description` per LD-597; uses ONLY fields valid for `prod_activity_log`'s 11-field schema):
    - `path`: absolute path string of the override file
    - `content_sha256`: sha256 of the raw file content (or `null` if `OSError` prevented reading)
    - `parse_error`: JSON decode error message string (case C only; absent for D/E)
    - `layout_error`: layout-failure description string (case D only; absent for C/E)
    - `os_error`: OSError string (case E only; absent for C/D)
    - `attempted_at`: ISO-8601 UTC timestamp of the load attempt
    - `recovery_action`: `"defaults_used"` (default fail-safe path) OR `"raised_OverrideFileMalformedError"` (fail-loud env var path)
    - `fail_mode`: `"safe"` (default) OR `"loud"` (env var set)
  - `module_id`: null (validator is a global helper, not module-specific)
  - `performed_by`: `"payload_validator"` (validator's identity for audit trail)

**Re-read frequency:** the override file is read at module-import time AND on every call to `invalidate_schema_cache()` (which migration scripts call at phase boundaries per Decision 2). Re-reads pay the malformed-handling cost again per the 5-case table above.

**Env-var opt-in to fail-loud:**
- `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` — when set in environment, cases C/D/E raise `OverrideFileMalformedError(path, kind, cause)` instead of returning `{}`. Documented in CLAUDE.md Rule 35 sub-section per Phase 5. Use case: high-stakes schema-migration windows where the operator's `'warn'` override MUST be respected and silent fallback to `'strict'` defaults would cause production breakage.
- `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE` unset OR set to anything other than `loud` (including `safe`, `default`, empty string) → default fail-safe path.

**Reference implementation sketch** (for Phase 1 implementer; not normative — the §9.2 table above is normative):
```python
def _load_override_file() -> dict:
    """Load per-collection override config. v2 normative path per §9.2."""
    path = Path("~/.claude/state/payload_validator_overrides.json").expanduser()
    if not path.exists():
        return {}  # Case A
    try:
        content = path.read_text()
    except OSError as e:
        _log_malformed_override(path, None, "permission_denied", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "permission_denied", e)
        return {}  # Case E (fail-safe)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        _log_malformed_override(path, content, "json_parse_error", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "json_parse_error", e)
        return {}  # Case C (fail-safe)
    if not _validate_override_layout(parsed):
        reason = _describe_layout_failure(parsed)
        _log_malformed_override(path, content, "layout_invalid", reason)
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "layout_invalid", reason)
        return {}  # Case D (fail-safe)
    return parsed  # Case B
```

**Test coverage** (Phase 1 deliverable per §5.1 v2 amendment): 4-fixture test (valid + invalid-JSON + invalid-layout-not-dict + invalid-layout-bad-key) + 1 fail-loud env-var test. See §5.1 Phase 1 v2 amendment for full test specification.

### §9.3 — Logging strategy (dog-fooding the validator) (preserved verbatim from v1)

See v1 §9.3 (lines 323-325). v2 inherits the `_VALIDATOR_INTERNAL_BYPASS` thread-local pattern unchanged. The malformed-override activity-log row queue per §9.2 v2 USES this bypass: the validator sets `_VALIDATOR_INTERNAL_BYPASS.active = True` before queueing the `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` row to prevent re-entering itself.

### §9.4 — Telemetry expected post-Phase-4 (preserved verbatim from v1; v2 appends one new row)

Preserves v1 §9.4 four-row telemetry list verbatim. v2 appends:

5. **NEW v2** — Activity-log row counts for `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` per day (target: zero in steady state; non-zero count flags an override-file integrity issue the operator should investigate via the log line).

---

## §10 — Cursor cross-review companion handoff (UPDATED for v2)

The v1 §10 noted the Cursor cross-review handoff was deferred. v1's Cursor review HAS been authored + executed in this session window:
- **Handoff:** `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`.
- **Cursor verbatim review:** `Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md` (sha256 captured below in §11).
- **Cursor review report:** `Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_REPORT_20260508.md`.

**Cursor v1 verdict:** `AMEND_V2`. Tasks A/B/C/D/F/G PASS at AUTHORIZE thresholds. Task E FAIL → AMEND. Defect: `§9.2` did not define behavior when `payload_validator_overrides.json` exists but is malformed (parse failure or wrong layout). v2 corrects this defect via §9.2 v2 full rewrite + §3 Decision 8 + §5 Phase 1 4-fixture test + §6 Gate 11 + §7 risk #11.

**Process note (Cursor):** Cursor was unable to verify LD-599 live per handoff §0.2 (instructed not to probe Directus); tagged `(agent claim)`/`(unverified)` per DS-29. v2 confirms live LD-599 per author's `(my probe)` (see v2 final report). This is a Cursor process-note, not a v1 design defect; v2 does not rewrite handoff guidance, but future review handoffs may consider explicitly authorizing LD-row probes per DS-29 source-tagging convention.

**v2 Cursor review authorship:** REQUIRED before Phase 1 implementation begins per §6 Gate 10. Reserved path for v2 review handoff: `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_v2_20260508.md` (NOT authored in this v2 session per self-bound list).

---

## §11 — Reference index (v2 preserves v1 entries + appends new entries)

**Preserved verbatim from v1 §11** (see v1 lines 354-368):

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
- **LD-597** (`TASK_DESCRIPTION_FIELD_ANTI_CONFUSION_GUARDS_V1`).
- **LD-598** (`SCHEMA_VOCAB_MIGRATION_V7_JSON_STRING_AWARE_EXTRACTOR`).
- **LD-364** (`POST_ITEM_VERIFIED_V1`).

**NEW for v2** (appended below):

- **`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md`** — historical baseline preserved; sha256 `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`; 449 lines / 60533 bytes; authored 2026-05-08. v2 inherits Decisions 1-7, Phases 0/2/3/4/5, Gates 1-10, Risks 1-10 verbatim.
- **`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`** — Cursor's verbatim adversarial review of v1; verdict `AMEND_V2` on Task E (malformed override file); 17477 bytes (per `(my probe)` `ls -la`).
- **`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_REPORT_20260508.md`** — companion summary report; 4038 bytes; one-line verdict `AMEND_V2`.
- **`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md`** — this document (self-reference); supersedes v1; addresses Cursor AMEND_V2 Task E.
- **LD-599** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1`) — v1 spec-LD; verified live 2026-05-08 `(my probe)`: id=599, decision_key matches, status=`active`, severity=SOFT, task_category=governance, enforcement_type=awareness_only, scope_domain=infra.
- **LD-NEW** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1`) — this v2's spec-LD; filed in this v2 session per §0 Operating Mode; documents the Cursor AMEND_V2 fix scope (§9.2 + §3 Decision 8 + §5 Phase 1 + §6 Gate 11 + §7 risk #11).

---

## §12 — Changelog (v2 appends one row to v1)

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-05-08 | Initial spec authored. 7 design decisions debated (§3); per-decision action table (§4); 6-phase rollout (§5); 10 pre-implementation gates (§6); 10 risks (§7); per-phase rollback (§8); operational notes + override file + dog-fooding bypass (§9); Cursor cross-review companion flagged as follow-up (§10). Companion LD-599 `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` filed alongside. |
| **v2** | **2026-05-08** | **Address Cursor cross-review AMEND_V2 verdict on v1 (single Task E blocker — malformed override file behavior undefined). Changes: §9.2 full rewrite enumerating 5 file-state cases with single normative path (fail-safe default + diagnostic + activity-log row) + opt-in fail-loud env var `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud`. §3 NEW Decision 8 dual-Opus debate (fail-safe vs fail-loud) → synthesis fail-safe default + opt-in fail-loud. §5 Phase 1 deliverable adds 4-fixture override-file test + 1 fail-loud env-var test. §6 NEW Gate 11 (override-file fail-mode policy approval). §7 NEW risk #11 (override silent-fallback masking operator intent). §11 reference index appends v1 historical baseline + Cursor review outputs + LD-NEW. §12 this row. All other v1 design preserved verbatim by reference. v1 baseline sha256 `14ae4e22b653...` recorded for drift detection. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1` filed alongside.** |

---

## §13 — Cross-references (preserved verbatim from v1)

See v1 §13 (lines 380-391). v2 inherits cross-references unchanged.

---

## §14 — Pre-execution checklist (v2 extends v1's checklist with one row)

The checklist below preserves v1 §14 rows verbatim and appends one row for §6 Gate 11 (NEW v2).

- [ ] §6 Gate 1 — Decision 1 verdict (strict end-state, phased path) approved.
- [ ] §6 Gate 2 — Decision 2 verdict (15-min TTL + invalidator hook) approved.
- [ ] §6 Gate 3 — Decision 3 verdict (separate `lib/payload_validator.py`) approved.
- [ ] §6 Gate 4 — Decision 4 verdict (fail-closed + queue-on-fail) approved.
- [ ] §6 Gate 5 — Decision 5 verdict (opt-out always-on + override file) approved.
- [ ] §6 Gate 6 — Decision 6 verdict (strip auto-fields with audit + override flag) approved.
- [ ] §6 Gate 7 — Decision 7 verdict (14-day grace for registered-retired fields) approved.
- [ ] §6 Gate 8 — §5 phased rollout (Phase 0 → 5) approved.
- [ ] §6 Gate 9 — Phase 4 strict-promotion gated on Phase 3 zero-warning sweep.
- [ ] §6 Gate 10 — Cursor cross-review handoff authored + Cursor verdict received (v1: complete with `AMEND_V2`; v2: pending — see §10).
- [ ] **§6 Gate 11 (NEW v2) — Decision 8 verdict (override-file fail-mode policy: fail-safe default + opt-in fail-loud env var) approved.**
- [ ] All 11 risks in §7 reviewed and mitigations approved (especially Risk #1, #5, #8 — top 3 by severity; Risk #11 NEW v2 reviewed for adequacy).
- [ ] §0 Operating Mode acknowledged (DESIGN ONLY this session; implementation gated).
- [ ] LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1` confirmed filed (filing in this v2 session per spec-LD POST below).
- [ ] Activity-log row `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_AUTHORED_V1` confirmed filed.
- [ ] v1 baseline sha256 `14ae4e22b653...` recorded; drift detection confirms v1 untouched during v2 authoring (`(my probe)` per v2 final report).

---

## §15 — Audit (preserved verbatim from v1; v2 appends one new line)

Preserves v1 §15 six-row audit list verbatim. v2 appends:

7. **NEW v2** — Override-file malformed-handling smoke test: Phase 1 unit test verifies all 5 cases (A/B/C/D/E) per §9.2 v2 normative path + verifies fail-loud env var raises correctly. Test asserts `_load_override_file()` returns `{}` (fail-safe) for cases C/D/E when env var unset, and raises `OverrideFileMalformedError` when env var set to `loud`. Activity-log row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` queued correctly with `details` dict containing required keys (`path`, `content_sha256`, `parse_error`/`layout_error`/`os_error`, `attempted_at`, `recovery_action`, `fail_mode`).

---

## §16 — Reference index — external docs + APIs (preserved verbatim from v1)

See v1 §16 (lines 432-436). v2 inherits Directus schema API, Directus collections API, `functools.lru_cache`, `threading.local()`, `pathlib.Path` references unchanged.

---

## Authoring metadata

- **Spec author:** Claude Opus 4.7 (1M context)
- **Authoring session date:** 2026-05-08 (v2; same calendar day as v1 + Cursor review)
- **Authoring branch:** claude/gallant-bouman-804b4f (worktree)
- **v1 baseline sha256:** `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75` — confirmed unchanged at v2 authoring start `(my probe)`.
- **v1 baseline size:** 449 lines / 60533 bytes — confirmed `(my probe)`.
- **Self-bound list compliance:** confirmed; v2 modifies ONLY the new v2 file + spec-LD POST + activity-log POST. NO modifications to v1 spec, prior schema-migration specs (v1-v7), implementation handoff, schema-ref doc, weekly_preflight, settings.json, hook scripts, payload_validator.py (doesn't exist), Cursor review outputs.
- **Cursor review verdict addressed:** `AMEND_V2` Task E (malformed override file behavior).
- **Wave A live-schema probe timestamp:** 2026-05-08 (this session — LD-599 verified live `(my probe)`).
- **Wave A inventory file:** [DEFERRED — Phase 0 deliverable per v1 §5.1 Phase 0 unchanged.]

[CONFIRMED — every claim in v2 is anchored to a live-schema probe (LD-599), an existing file (v1 spec sha256, Cursor review outputs), or an explicit synthesis paragraph in §3 Decision 8. Confidence tags applied throughout per zero-error-qa Rule 24 + DS-29 source tagging.]
