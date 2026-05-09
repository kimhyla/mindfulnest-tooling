# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1

**Authored:** 2026-05-08
**Author:** Claude Opus 4.7 (1M context)
**Status:** DESIGN ONLY — execution gated on Kim approval per §6
**Self-classification:** ARCHITECTURAL (per zero-error-qa DS-26 / tech-spec skill v2 §0.1)
**Scope:** Generic schema-aware payload validator covering ALL `prod_*` Directus collections
**Generalizes:** v6 narrow validator pattern (`validate_prod_blockers_payload`) one architectural layer up
**Companion:** Cursor cross-review handoff (NOT yet authored — see §10)

---

## §0 — Operating Mode

This document is **DESIGN ONLY**. No code is written, no scripts are executed, no Directus rows are PATCHed, no LDs except the spec-LD itself are filed during the authoring of this spec. Per tech-spec skill v2 §0 + §14:

- **Authoring this session:** spec markdown + spec-LD POST + activity-log POST. No more. Self-bound list at end of handoff prompt is binding.
- **Implementation:** gated on Kim approving each of the 7 design decisions (§6 Gates 1-7) + the phased rollout sequence (§6 Gate 8) + the strict-promotion gate (§6 Gate 9) + the Cursor cross-review (§6 Gate 10).
- **Cursor cross-review handoff:** NOT authored in this session. Surface as §10 follow-up. Path reserved at `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`.

[CONFIRMED — self-bound list explicitly forbids implementation, Cursor handoff authorship, modification of any other spec/handoff/schema-ref/hook/migration script/LD record other than this spec's LD.]

## §0.1 — Self-classification

**ARCHITECTURAL.** This validator sits in the path of every Directus write across every script in the codebase (21 active write-call files inventoried in Wave A). Blast radius is broad — a Phase 4 strict-mode promotion that is wrong silently breaks production-tracking writes; a permissive-mode default that is wrong silently allows the next silent_write_failure to recur. The 7 design decisions debated in §3 each carry non-trivial tradeoffs (cache TTL, fail-open vs fail-closed, opt-in vs opt-out, retired-field grace period). DS-26 escalation criteria triggered: cross-cutting infrastructure helper called by ≥10 scripts; failure mode is Layer 6 (input/output variation enforcement); broad-by-default behavior change.

[CONFIRMED — Wave A inventory: 21 write-call files; per-collection write frequency: prod_activity_log=21 grep-hits, prod_locked_decisions=9, prod_modules=4, prod_preflight_reviews=2, prod_assets=2, prod_reference_docs=1, prod_blockers=1, prod_app_stages=1.]

---

## §1 — Goal

**Mechanically prevent silent_write_failure on ALL `prod_*` Directus writes by validating payload keys against the live collection schema before send.** Cover the failure mode that produced LD-595 / LD-596 / LD-597 generically rather than per-collection.

### Non-goals

1. **NOT a replacement for the v6 narrow validator** (`validate_prod_blockers_payload` in `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` §6 Gate 11.2). That stays as the prod_blockers-specific layer; this generic validator is one architectural layer up. Both layers can coexist — narrow validator runs first (cheap, O(1), no probe), generic validator runs second (cache hit O(1), cache miss one schema probe). [CONFIRMED — see §3 Decision 3 verdict]
2. **NOT a value-validator.** Only key-validator: reject unknown keys; do NOT validate VALUES (no enum-membership checks, no length checks, no type checks beyond what `_validate_json_columns` already does in `Production/lib/directus.py`). Value-validation is a separable concern.
3. **NOT a schema-migration tool.** This validator READS the live schema; it never PATCHes the schema. Migrations go through `Production/scripts/migrate_schema_vocab_v1.py` per `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md`.
4. **NOT a backward-compat-shim for retired fields.** A separate concern: see §3 Decision 7 for the retired-field handling debate. The validator does NOT auto-rename old field-names to new field-names. If a payload sends a retired field, the validator rejects it (or warns, per Decision 7 verdict).
5. **NOT a substitute for `post_item_verified` read-back.** The validator catches **field-name** drift before send; `post_item_verified` catches **value** drift after send. Both layers complement each other (defense-in-depth).

### Bounded by

- 30 `prod_*` collections (Wave A live probe, 2026-05-08): `prod_activity_log` (11), `prod_app_stages` (8), `prod_approvals` (8), `prod_arcs` (7), `prod_asset_aliases` (5), `prod_asset_versions` (7), `prod_assets` (24), `prod_audio_assets` (10), `prod_audio_locked_decisions` (8), `prod_blockers` (8), `prod_checklist_items` (6), `prod_checklists` (5), `prod_creatures` (6), `prod_dependencies` (5), `prod_infrastructure_scripts` (9), `prod_locked_decisions` (25), `prod_locks` (8), `prod_module_json` (6), `prod_modules` (44), `prod_numerical_claims` (14), `prod_phase_a_scenes` (5), `prod_phase_b_scripts` (8), `prod_preflight_reviews` (12), `prod_reference_docs` (15), `prod_scripts` (14), `prod_session_decisions` (7), `prod_stages` (6), `prod_techniques` (6), `prod_visual_assets` (32), `prod_voice_profiles` (9). [CONFIRMED — full live probe captured in §2.]

---

## §2 — Background

### 2.1 — Two silent_write_failure incidents on 2026-05-08

**Incident 1 — `task_description` to `prod_activity_log`.** A handoff template included `task_description` in the activity-log payload. Live `prod_activity_log` schema has 11 fields and `task_description` is NOT one of them — it lives on `prod_preflight_reviews` (12 fields, `task_description` IS one of them). Directus accepted the POST with HTTP 200/201, silently dropped the `task_description` key, persisted the row WITHOUT it. `post_item_verified`'s read-back deep-equality check raised `SilentWriteFailure` only AFTER the row was already in the DB, requiring a subsequent PATCH to clean up. Resolution: LD-597 (`TASK_DESCRIPTION_FIELD_ANTI_CONFUSION_GUARDS_V1`) — anti-confusion guards in CLAUDE.md Rule 35, schema-ref doc, memory file, with explicit 11-field enumeration for `prod_activity_log` and 12-field enumeration for `prod_preflight_reviews`. [CONFIRMED — Wave A live probe matches the field counts.]

**Incident 2 — `details` and `resolution_notes` to `prod_blockers`.** During schema-vocab migration v3→v4→v5 chain authoring, the `release_stale_mutex.py` helper and the migration script's mutex POST/PATCH paths used `details` and `resolution_notes` as field names. Live `prod_blockers` schema has 8 fields and neither key exists — structured payloads must encode INSIDE the `description` field as text-embedded JSON anchored on `STRUCTURED_DETAILS_JSON:`. Resolution chain: LD-595 (v5 spec field-name fix; replaces `details` with `description+STRUCTURED_DETAILS_JSON` and replaces `resolution_notes` with appended-to-`description`), LD-596 (v6 spec runtime payload-key validator `validate_prod_blockers_payload` — narrow, prod_blockers-only, replaces v5's grep-based lint that was bypassable via token concat / computed keys / helper wrappers), LD-598 (v7 spec JSON-string-aware extractor for the embedded `STRUCTURED_DETAILS_JSON:` payload). [CONFIRMED — see `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` §6 Gate 11.2 lines 142-180.]

### 2.2 — The v6 narrow validator pattern (verbatim, 3-line quote)

From `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` lines 173-179:

> "`extra = set(payload.keys()) - ALLOWED_PROD_BLOCKERS_KEYS`
> `if extra:`
> `    raise RuntimeError(f"prod_blockers payload contains non-existent fields: {extra}.")`"

This is the LOAD-BEARING in-process write-time enforcement. v6 §9.4 + §6 Gate 11.2 documented the necessity: grep-based pre-launch lint cannot catch token concatenation (`"deta"+"ils"`), computed keys (`{f"detail{'s'}": ...}`), helper wrappers that build the dict elsewhere, or carve-out tokens (`prod_activity_log` / `prod_locked_decisions`) sharing a line with a real `prod_blockers` write. **A runtime validator is the only mechanically-reliable enforcement.** This spec generalizes that pattern from one collection (`prod_blockers`, 8-key allowlist) to ALL 30 `prod_*` collections (live-schema-derived allowlists per collection).

### 2.3 — Why per-collection narrow validators don't scale

Authoring 30 narrow validators one-by-one (one per collection) duplicates code 30 times, drifts per-collection at schema migration time (we already have 7+ schema-migration spec versions: v1-v7), and leaves new collections unprotected by default. A single generic schema-aware validator amortizes the cost: one function, one cache, one fail-mode, every collection covered automatically. Schema migrations invalidate the cache and the validator stays correct. [HIGH CONFIDENCE — derived from the 30-collection count + the schema-vocab migration v1-v7 chain that has touched fields multiple times.]

### 2.4 — LD-597 anti-confusion guards (already shipped)

LD-597 is documentation hardening — CLAUDE.md Rule 35 + schema-ref doc + memory file all carry explicit field enumerations for the two confusable collections (`prod_activity_log` 11 fields vs `prod_preflight_reviews` 12 fields). This is preventive but human-facing — it relies on Claude / scripts reading the docs at write-time. The mechanical complement is the runtime validator proposed here.

[CONFIRMED — LD-597 referenced in memory `Memory Index` line for the 2026-05-08 V59 Storyboard Foundation Sprint session; CLAUDE.md Rule 35 cited in v6 spec line 282-285.]

---

## §3 — Dual-Opus debate (REQUIRED)

For each of the 7 design decisions, two GOOD-FAITH positions are authored: an **Advocate** and a **Counter**. Synthesis verdict follows. Per tech-spec skill: do NOT pre-conclude.

### Decision 1 — Strict reject vs permissive warn-only default behavior

**Advocate (strict reject):** The fail-loud principle is the foundational safety pattern across this codebase: `_validate_json_columns` raises `JsonColumnTypeError` BEFORE the POST, `post_item_verified` raises `SilentWriteFailure` on read-back drift, the v6 narrow validator raises `RuntimeError` on unknown keys. Every layer of the existing Directus stack is fail-loud. A permissive-warn-only default would be the ONE soft-failure path in an otherwise hard-failure stack — exactly the kind of inconsistency that produces the cognitive offload that allowed LD-595/596/597 to ship in the first place. Strict-reject also catches schema drift earlier: every silent dropped key is now a hard halt + activity-log row + operator escalation, instead of a warning the operator may or may not read. The two failure modes that produced today's LDs were both caused by a write succeeding (HTTP 200) when it should have failed; strict-reject is the mechanical answer.

Strict-reject is also the simpler-to-document mode: there is exactly one behavior at the call site (write succeeds → row is correct; write fails → caller knows immediately). Permissive-warn-only requires an audit trail to know whether a warning was raised, where the warning was logged, and whether anyone followed up. Strict mode self-documents via the exception traceback at call-time. The migration-cohort risk (§5 Phase 3 warn-mode sweep before promotion) is a known, bounded concern that can be discharged once.

**Counter (permissive warn-only):** Strict-reject is dangerous as a default because we do NOT know all the existing callers' payload shapes. The Wave A inventory found 21 active write-call files (`Production/scripts/lock_decision.py`, `Production/tools/upload_module.py`, `Production/tools/beat_generator.py`, etc.) and 59+ raw call-sites. Some of those callers may be passing extra fields that Directus has been silently dropping for months. Promoting the validator to strict mode without auditing every caller would break working scripts on day one — exactly the production-blocking surprise Kim's "no shortcuts" doctrine is designed to prevent. Permissive-warn-only by default lets us roll the validator out broadly with zero risk of breaking working code, surface every unknown-field hit to a single audit channel (`prod_activity_log` row `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_WARN`), and promote to strict only AFTER the warn-mode sweep returns clean.

Permissive-warn-only also handles the schema-migration race condition more gracefully. Per the schema-vocab v3→v7 migration chain, fields are added/renamed/retired as part of normal evolution. A strict-reject default produces production-blocking failures DURING migration windows (the validator's cache may briefly disagree with the live schema). A warn-mode validator stays informational during migrations — the operator chooses when to discharge the warnings, after the migration's checkpoint protocol has settled.

**Synthesis verdict — Advocate wins (HYBRID with phased promotion).** Strict-reject is the correct end state because it matches the rest of the stack's fail-loud doctrine and provides mechanical guarantees that warn-only cannot. The Counter's concern about unknown caller behavior is real but is best discharged by §5 Phase 3 (warn-mode sweep) BEFORE Phase 4 (strict promotion), not by permanently keeping the default at warn-only. The validator ships with `mode='warn'` for one full sweep cohort, surfaces every unknown-field hit to `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_WARN` activity-log rows, then flips to `mode='strict'` once the sweep returns zero warnings. This satisfies both fail-loud doctrine AND migration safety. Headline argument: **strict end-state, phased path to get there**.

### Decision 2 — Schema cache TTL (long ≥1h vs short ≤5min vs per-write)

**Advocate (long TTL — 1 hour or session-lifetime):** Performance matters. A per-write probe adds one HTTP round-trip (~100-300ms) to every Directus write, which compounds across the 21 active write-call files. The high-frequency callers (`prod_activity_log` writes from every spec, every closeout script, every Phase G/H rollback rehearsal) would each pay this cost. A 1-hour TTL with `functools.lru_cache(maxsize=64)` (32 collections × 2 cache slots for under-sustained-pressure) reduces the steady-state probe count from N writes to ~30 probes/hour. This matches the existing `lock_decision.py` cache TTL (1 hour per LD-227 / line 60 in script). Consistency across the helper layer is its own value.

A 1-hour TTL is also long enough to ride out the schema-migration window's transient inconsistencies (a Phase 1 PATCH chain that takes 10 minutes won't see the cache drift mid-run if the cache was warmed at start). Cross-process consistency: the per-process cache means each Python process probes once and reuses; the next process pays the cost on its first call. For most use cases that's fine because most scripts are short-lived (lock_decision, closeout scripts, single-pass migration phases).

**Counter (short TTL ≤5 min, or per-write):** A 1-hour TTL is dangerous DURING migration windows. The schema-vocab migration v3 inserts 7 new task_category enum values + remaps ~110 rows in Phase 4. If the validator's cache is 1-hour stale, Phase 1 (Rule 4 scope_domain remap) writes pass; Phase 4 writes fail because the cache predates the enum-value addition. This is exactly the failure mode Kim's zero-error-qa doctrine flags as Layer 6 (input variation → output variation) drift. A 5-minute TTL bounds the cache-drift window to under one Phase's commit window, eliminating the cross-phase staleness risk. A per-write probe (no caching at all) eliminates it entirely — at the cost of ~150ms per write, which is acceptable for audit-trail operations but not for tight loops.

A short TTL also fails-faster on schema corruption: if a collection's schema gets accidentally mutated (e.g., admin-UI field-rename), the validator surfaces the divergence within 5 minutes instead of within 1 hour. The 1-hour TTL trades correctness for performance during a window where correctness is precisely the value the validator exists to provide.

**Synthesis verdict — Hybrid (15-minute default, with explicit invalidate-on-migration hook).** Neither extreme is right. The 1-hour TTL is too coarse for migration windows; the per-write probe is too aggressive for high-volume callers. **15 minutes** strikes the balance: long enough to amortize probe cost across short-lived scripts (most scripts complete in <15 min), short enough to bound cross-phase drift inside a multi-phase migration. Add a public function `invalidate_schema_cache(collection: Optional[str] = None)` that migration scripts call at phase boundaries (e.g., after Phase 3 enum-add commits, before Phase 4 PATCHes begin). The migration scripts ALREADY know when they've changed the schema; explicit invalidation costs one line per phase boundary and eliminates the staleness risk for the ONE caller class where it matters. Headline argument: **15-minute TTL + explicit invalidation hook for migration scripts**.

### Decision 3 — Where the validator lives (`lib/directus.py` co-located vs separate `lib/payload_validator.py`)

**Advocate (co-located in `lib/directus.py`):** Co-location is the simplest design. The existing helpers (`post_item_verified`, `try_post_or_queue`, `_validate_json_columns`, `JSON_COLUMN_INVENTORY`) all live in one file at `Production/lib/directus.py`. Adding the new validator function adjacent to `_validate_json_columns` makes the call-site sequence obvious: `validate_payload_keys → _validate_json_columns → POST → read-back-verify`. One import path, one place to reason about Directus write semantics, one place to read when debugging a write failure. The maintenance load is also lower: every existing caller already imports from `lib.directus`, so no caller code needs to change.

Co-location matches the established pattern for write-time guards: `_validate_json_columns` is a private helper in `lib/directus.py` rather than a separate module, even though it's a discrete validation concern. The same shape applies to the payload-key validator. Splitting would create a two-file pattern where there's only ever been one.

**Counter (separate `lib/payload_validator.py`):** The validator has clean inputs/outputs (`(collection, payload, mode) → None | raise`), is testable in isolation (no need to mock the entire Directus stack), and has nothing in common with the rest of `lib/directus.py` except that it's called from `try_post_or_queue`. A separate module is better SOLID practice: single responsibility, easy to disable (drop one import), easy to swap (e.g., for a CI-only mode that runs the validator against a static schema export for offline lint). It also keeps `lib/directus.py` from growing into a god-module — the file already has multiple concerns (post + verify, queue + replay, JSON column type guard, equality helpers) and adding one more increases reading load on every contributor.

A separate module also makes the §6 Gate 5 (opt-in vs opt-out per collection) configuration cleaner: the per-collection override file (`~/.claude/state/payload_validator_overrides.json`) lives next to the module that consumes it, not buried inside `lib/directus.py`'s growing surface.

**Synthesis verdict — Counter wins (separate module).** The module-split argument is stronger because the validator IS a discrete responsibility and `lib/directus.py` is already at 600+ lines covering multiple concerns. A separate `Production/lib/payload_validator.py` lets us test in isolation, swap modes (runtime vs CI-only static-schema check), and keep `lib/directus.py` focused on the post+verify+queue pipeline. The integration is one import line in `lib/directus.py::try_post_or_queue`, plus the override-file logic is local to the new module. Headline argument: **separate `lib/payload_validator.py` module + one import in `try_post_or_queue`**.

### Decision 4 — Failure mode on probe failure (fail-closed: refuse write, vs fail-open: warn + proceed)

**Advocate (fail-closed: refuse write):** Safety. The validator exists to prevent silent_write_failure; if the validator can't probe the schema, it can't perform its job. Fail-open in this case is exactly the failure mode the validator was created to eliminate — write proceeds, payload is unverified, silent drop is possible. Consistency with `_validate_json_columns`: that helper raises `JsonColumnTypeError` on its violation; the equivalent here is to raise `SchemaProbeError` on probe failure. The caller can catch and handle (e.g., queue the write to `pending_directus_writes.json` per existing offline-tolerance pattern), but the default is "halt and surface" per CLAUDE.md Rule 35.

Fail-closed also has a clean offline-tolerance integration: if Directus is offline, the schema probe fails AND the POST would fail anyway. `try_post_or_queue` already queues writes on POST failure; we extend the queue to also fire on schema-probe failure. The queued write replays at next session; the schema probe replays with it. Net: identical user-visible behavior as offline-POST-failure, no degraded silent path.

**Counter (fail-open with warn):** `try_post_or_queue` was explicitly designed to be tolerant of Directus outages — that's the entire reason it exists as a wrapper around `post_item_verified`. The offline path (queue to `pending_directus_writes.json`, replay later) is the established precedent for graceful degradation. A fail-closed validator breaks this contract: a Directus outage on schema probe blocks even the writes that would otherwise queue cleanly. The downstream effect: the operator's local script halts with `SchemaProbeError` and the operator has to manually decide whether to retry, override, or skip — exactly the cognitive load the offline-queue pattern eliminates.

A fail-open warn-mode preserves the existing semantics: probe fails → log a warning → fall through to `try_post_or_queue`'s normal path → POST attempt → POST fails (because Directus is down) → queue offline. The validator is now strictly additive to the existing pipeline. The risk of a silent_write_failure during a probe-only outage (Directus is partially up, accepting POSTs but failing on `/fields/<collection>`) is real but bounded — Directus does not typically partially-fail on schema endpoints.

**Synthesis verdict — Advocate wins (fail-closed) BUT with offline-queue integration.** Fail-closed is correct because the validator's job IS to prevent silent_write_failure, and a fail-open mode reintroduces the failure class on the one path where the validator is supposed to provide guarantees. However, the integration with `try_post_or_queue` should be: probe failure → raise `SchemaProbeError` → `try_post_or_queue` catches → queues the write to `pending_directus_writes.json` with a `reason` tag of `schema_probe_failure` → returns the queued sentinel `{"queued": True, "path": str, "reason": "schema_probe_failure"}` to the caller. This satisfies fail-closed semantics (no unverified write hits the wire) AND offline tolerance (the operator's script gets a queued sentinel, not a hard halt). Headline argument: **fail-closed at the validator layer; queue-on-fail at the wrapper layer**.

### Decision 5 — Opt-in vs opt-out per collection

**Advocate (opt-out / always on):** Broadest protection by default. The whole point of generalizing the v6 narrow validator is to cover EVERY `prod_*` collection automatically; an opt-in mode means new collections start unprotected and someone has to remember to add them to the registry. That's the same maintenance burden as authoring 30 narrow validators by hand — exactly what generalization is supposed to eliminate. Opt-out (always-on with per-collection disable flag) gives the broadest baseline coverage and only forces explicit justification when a caller really needs to skip the validator (e.g., a debug script writing experimental fields to a sandbox collection).

Opt-out is also the conservative-by-default principle that matches Kim's "no shortcuts" doctrine. New code is protected; opt-out requires explicit thought + a row in the override file (`~/.claude/state/payload_validator_overrides.json`) + presumably an LD documenting why.

**Counter (opt-in per collection registered in config):** Gradual rollout reduces blast radius. Phase 4 strict-mode promotion across 30 collections at once is a HUGE blast radius — any one collection's caller mismatch breaks production. Opt-in mode lets us promote one collection at a time: `prod_blockers` first (already covered by the v6 narrow validator, low risk), then `prod_activity_log` (highest call volume, highest test surface), then the rest. The override file becomes the inverse — a registry of WHICH collections are validated, not which are excluded. This is the same pattern as the JSON-column inventory in `lib/directus.py` (lines 256-261): explicit per-collection registration, opt-in by design.

Opt-in also handles the migration-window risk gracefully. During a schema-vocab migration, a collection's schema is in flux — opt-in means the validator can be temporarily DEREGISTERED for that collection during the migration phase, then re-registered after Phase 6 final audit. Opt-out forces an override-file edit + cleanup + LD trail, which is more friction.

**Synthesis verdict — Advocate wins (opt-out / always-on with per-collection disable file).** The generalization argument is decisive: the whole point of this spec is to cover every collection by default. Opt-in inverts the failure mode — new collections start unprotected, and each collection requires explicit registration (which is just the v6 narrow validator pattern at scale, defeating the purpose of generalization). The Counter's gradual-rollout concern is real but is better addressed by §5 Phase 3 warn-mode sweep (which exercises every collection's existing callers in informational mode before strict promotion), not by permanently inverting the default. The override file (`~/.claude/state/payload_validator_overrides.json`) carries per-collection `mode='warn' | 'strict' | 'skip'` overrides for edge cases. Headline argument: **opt-out always-on, with override file for migration-window exceptions**.

### Decision 6 — Auto-generated / read-only field handling (silent strip vs warn vs reject)

**Advocate (silent strip before send):** Convenience. Directus rejects auto-fields anyway (`id`, `date_created`, `date_updated` are server-set; passing them in a POST returns 422 or silently overwrites). The validator can strip these from the payload before send and the caller doesn't have to remember which fields are auto-set per collection. This matches `_AUTO_FIELDS` in `lib/directus.py` lines 122-130 (`{id, date_created, date_updated, created_at, updated_at, user_created, user_updated, sort}`) — that set is already a per-write convention. The validator can re-use the same set and strip-on-validate.

Silent-strip is also low-friction. A caller that builds a payload from a row read-back (e.g., for PATCH) doesn't have to manually filter auto-fields; the validator does it. The behavior is documented; the strip is logged in debug mode; the net effect is fewer errors for callers.

**Counter (warn or reject — never silent-strip):** Silent-strip violates the validator's own design principle. The whole reason for the validator is to PREVENT silent payload manipulation. If the validator silently strips fields, it's exactly the silent_write_failure failure mode at a different layer — the caller thinks it sent a value, the row on disk doesn't reflect that value, the caller has no way to know. This is especially dangerous for `created_at` / `resolved_at` / `flipped_at` where a caller might WANT to backdate a row (e.g., during a data-restoration migration) and silent-strip discards the intent. Warn-or-reject forces the caller to explicitly handle auto-fields (pass `omit_auto_fields=True` arg, or remove them at construction time), preserving the principle that nothing about the payload is silently manipulated.

The `_AUTO_FIELDS` set in `lib/directus.py` is used for a DIFFERENT purpose: presence-only verification on read-back (don't fail equality if the server set its own value). That's NOT the same as stripping the field from the payload before send. Confusing the two contracts is a footgun.

**Synthesis verdict — Counter wins (warn-mode strip, never silent).** The "silent" anything from a validator whose purpose is preventing silent failures is internally inconsistent. The validator should: detect auto-field presence in payload, log a warning to `prod_activity_log` (`PAYLOAD_VALIDATOR_AUTO_FIELD_STRIPPED`) with the field name + collection, AND strip the field from the wire payload, AND return the strip-set to the caller for inspection. The caller receives `{"row": <row>, "stripped_auto_fields": [...]}` and can log/halt as appropriate. This preserves auditability (every strip is recorded) without forcing callers to manually filter auto-fields. Backdate use cases: caller passes explicit `allow_auto_field_overrides=True` flag to suppress the strip; this requires deliberate override + LD justification. Headline argument: **strip with warning + audit trail; explicit override flag for backdating**.

### Decision 7 — Retired-field grace period (block immediately vs grace period with warn-then-error)

**Advocate (block immediately):** Consistency. Strict-reject (Decision 1 verdict) means unknown keys are rejected immediately. Retired fields are a special case of unknown keys — the live schema no longer has them. Treating retired fields specially (with a grace period) creates two failure modes (unknown vs retired) that callers have to distinguish, and produces stale documentation: the schema-ref doc would need to enumerate every retired field for every grace-period window. Just reject. Force callers to migrate immediately. This is the same posture as the v6 narrow validator (no grace period for `details` / `resolution_notes` on `prod_blockers`).

Block-immediately also has the cleanest surface area: the validator's allowlist is the live schema's field set, period. No retired-set, no grace-period date arithmetic, no "warn until 2026-06-01 then error" logic to maintain.

**Counter (grace period with `_warn_retired_fields=True` flag for N weeks then promote to error):** Migration safety. When a schema field is retired (e.g., during the schema-vocab v3 migration when `task_category=='task_description'` was renamed or deprecated), there's a transition window where some scripts still reference the old field name. Block-immediately means every script using the retired field breaks at promotion-time. Grace period (e.g., 2 weeks of warn-mode for retired fields) gives operators time to migrate without production-blocking surprises.

The grace period is NOT a permanent soft-failure mode; it's a bounded migration aid. The validator carries a `RETIRED_FIELDS_REGISTRY` map (`{collection: {field_name: retire_date}}`) populated at retirement time; payloads containing a retired field within N days of retirement get a warning + the field is stripped + activity-log row `PAYLOAD_VALIDATOR_RETIRED_FIELD_USED`; payloads after the grace window get the same treatment as unknown keys (strict reject).

**Synthesis verdict — Hybrid: short 2-week grace period for explicitly-registered retired fields; immediate-reject for everything else.** The Advocate's "no special treatment" position is too coarse; the Counter's "grace period for everything" is too lax. The right answer is: a `RETIRED_FIELDS_REGISTRY` (lives in `Production/lib/payload_validator.py`) enumerates fields that were INTENTIONALLY retired with their retire_date. Payloads using a registered-retired field within 14 days of retire_date: warn + strip + audit. Payloads using a registered-retired field after the 14-day window: strict-reject (same as unknown keys). Payloads using an UNREGISTERED unknown key (never was a field, or was retired without registration): strict-reject immediately. This puts the burden on the schema-migration author to register retired fields at retirement time (one-line edit to the registry) in exchange for a bounded grace window for callers. Headline argument: **registered-retired fields get 14-day grace; unregistered unknowns reject immediately**.

---

## §4 — Per-decision action table

| # | Decision | Verdict | One-sentence rationale | Depends-on | Risk class |
|---|----------|---------|------------------------|------------|------------|
| 1 | Strict vs permissive default | **Strict end-state via Phase-3 warn-mode sweep** | Matches fail-loud doctrine of `_validate_json_columns` + `post_item_verified` + v6 narrow validator | §5 Phase 3 sweep zero-warning return | HIGH (Phase 4 promotion is the load-bearing change) |
| 2 | Schema cache TTL | **15-min default + explicit `invalidate_schema_cache()` hook for migration scripts** | Long-enough to amortize, short-enough to bound cross-phase drift | Migration scripts call invalidator at phase boundaries | MEDIUM (cache drift inside one migration phase) |
| 3 | Validator location | **Separate `Production/lib/payload_validator.py` module** | Single responsibility; testable in isolation; keeps `lib/directus.py` from growing into a god-module | Wire-up: one import in `lib/directus.py::try_post_or_queue` | LOW (file-organization choice) |
| 4 | Probe-failure mode | **Fail-closed at validator + queue-on-fail at wrapper** | Validator's job is to prevent silent failures; offline-queue integration preserves operator UX | `try_post_or_queue` catches `SchemaProbeError` → queues with `reason='schema_probe_failure'` | MEDIUM (Directus partial-outage edge case) |
| 5 | Opt-in vs opt-out | **Opt-out always-on + override file** | Generalization point is broad-by-default coverage; per-collection override handles migration-window edge cases | `~/.claude/state/payload_validator_overrides.json` | MEDIUM (migration-window collection deregistration) |
| 6 | Auto-field handling | **Strip with warning + audit + explicit override flag** | Silent-strip violates validator's own anti-silent-failure principle; audit preserves traceability | `prod_activity_log` row `PAYLOAD_VALIDATOR_AUTO_FIELD_STRIPPED` per strip | LOW (well-understood pattern via existing `_AUTO_FIELDS`) |
| 7 | Retired-field grace | **14-day grace for registered-retired fields; immediate-reject for unregistered unknowns** | Bounds migration window without permanent soft-failure | Schema-migration author registers retired field at retirement time | MEDIUM (depends on author discipline) |

[CONFIRMED — verdicts derived from §3 dual-Opus debate; rationales summarize the headline argument from each synthesis paragraph.]

---

## §5 — Implementation sequence (phased rollout)

### §5.0 — Caching invariants

- **Cache structure:** `_SCHEMA_CACHE: dict[str, tuple[set[str], float]]` keyed by collection name; value is `(field_set, fetched_at_epoch)`. Lives at module scope in `Production/lib/payload_validator.py`. Per-process (no cross-process sharing); each Python process probes once per collection per 15-min window.
- **Invalidation triggers:**
  1. TTL expiry (15 min from `fetched_at`).
  2. Explicit call to `invalidate_schema_cache(collection: Optional[str] = None)`. `collection=None` flushes the entire cache.
  3. Process exit (cache is in-memory, not persistent).
- **Cross-process consistency:** NOT GUARANTEED. Each Python process has its own cache. This is acceptable because (a) each process's writes are serial within itself, and (b) the schema-migration discipline puts explicit `invalidate_schema_cache()` calls at phase boundaries inside the migration script, so cross-phase consistency within ONE migration run is enforced.
- **Cache miss behavior:** On miss, probe `GET /fields/<collection>` via `DirectusAdminClient._request('GET', f'/fields/{collection}')`, parse the response into `{ff['field'] for ff in data}`, store with `fetched_at = time.time()`, return the field set.
- **Probe failure behavior:** Per Decision 4 verdict — raise `SchemaProbeError(collection, cause)`. Caller layer (`try_post_or_queue`) catches and queues.

### §5.1 — Phase plan (6 phases)

**Phase 0 — Snapshot current Directus writes across the codebase.**
- `grep -rn -E "client.post_item\(|try_post_or_queue\(|post_item_verified\(|client.patch_item\(" Production/ > Production/exports/payload_validator_caller_inventory_$(date +%Y%m%d).txt`.
- Inventory all callers + collections + fields they write.
- Wave A already produced this inventory: 21 active write-call files; per-collection grep frequency captured in §0.1.
- Output: `Production/exports/payload_validator_caller_inventory_<DATE>.txt` — flat file, one line per call site, columns `<file>:<line>:<collection>`.
- Phase 0 is non-mutating reconnaissance.

**Phase 1 — Author the validator function** in `Production/lib/payload_validator.py` per Decision 3 verdict.
- Module exports: `validate_payload(collection, payload, mode='strict|warn|skip') -> dict` (returns `{stripped_auto_fields: [...], retired_fields_used: [...]}` for caller inspection); `invalidate_schema_cache(collection: Optional[str]=None) -> None`; `SchemaProbeError`, `UnknownPayloadKeyError`, `RetiredPayloadKeyError` exceptions.
- Schema cache via module-scope dict + 15-min TTL per Decision 2.
- Reads `~/.claude/state/payload_validator_overrides.json` at module-import time + on cache invalidation.
- Override file schema: `{"<collection>": {"mode": "strict|warn|skip", "extra_allowed_keys": [...]}}`.
- `RETIRED_FIELDS_REGISTRY: dict[str, dict[str, str]]` — `{collection: {field_name: ISO_retire_date}}` per Decision 7.
- Auto-field handling per Decision 6: re-uses `_AUTO_FIELDS` from `lib/directus.py` (cross-import or duplicate locally; recommend duplicate to keep `payload_validator` independent).
- Phase 1 deliverable: `Production/lib/payload_validator.py` (~250 LOC est.) + companion `Production/lib/tests/test_payload_validator.py`.

**Phase 2 — Wire into `try_post_or_queue`.**
- Single integration point in `Production/lib/directus.py::try_post_or_queue`: after the existing `_validate_json_columns(collection, payload)` call, add `validate_payload(collection, payload, mode=_resolve_mode(collection))`.
- `_resolve_mode(collection)`: reads override file, defaults to `'warn'` for Phase 2-3, will flip to `'strict'` in Phase 4.
- `try_post_or_queue` catches `SchemaProbeError` → returns queued sentinel `{"queued": True, "reason": "schema_probe_failure", ...}`.
- `try_post_or_queue` catches `UnknownPayloadKeyError` (in strict mode) → returns sentinel `{"unknown_payload_key": True, "collection": ..., "extra": [...]}`. NOT queued — author error.
- All other writes (verify-success path) continue unchanged.
- Phase 2 is one-file edit + tests.

**Phase 3 — Run inventory scripts in `mode='warn'` for a sweep.**
- Default mode in Phase 2 is `'warn'`. Every existing caller's writes flow through the validator, log warnings to `prod_activity_log` (`PAYLOAD_VALIDATOR_UNKNOWN_FIELD_WARN` row per offending write), but proceed with the write.
- Sweep duration: ≥1 week of normal Kim activity OR explicit run-each-script-once trigger via `Production/scripts/payload_validator_phase3_sweep.py` (NEW; iterates every active write-call file's known invocation pattern).
- Exit criterion: zero `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_WARN` rows in the last 7 days.
- Any non-zero count surfaces a list of (caller_file, collection, extra_keys) → operator fixes the caller → re-sweeps.
- Phase 3 deliverable: clean sweep report at `Production/exports/payload_validator_phase3_sweep_<DATE>.md`.

**Phase 4 — Promote to `mode='strict'` per Decision 1 verdict.**
- Edit `_resolve_mode` default from `'warn'` to `'strict'`.
- Activity-log row `PAYLOAD_VALIDATOR_PROMOTED_TO_STRICT_V1` posted with sweep-report sha256 + commit-sha + the override-file snapshot.
- Phase 4 is gated on Phase 3 zero-warning sweep (§6 Gate 9).
- Rollback per §8 Phase 4 row.

**Phase 5 — Document the validator in CLAUDE.md Rule 35 + schema-ref doc + memory file.**
- CLAUDE.md Rule 35 amendment: add a sub-section §35.X documenting the validator (when it runs, how to override, how to register retired fields, how to invalidate cache).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` cross-reference + a new top-of-doc note pointing to `Production/lib/payload_validator.py` as the runtime enforcement.
- Memory file: append a memory line under Memory Index for the validator.
- Phase 5 is doc-only; LD `DIRECTUS_PAYLOAD_VALIDATOR_DOCS_HARDENED_V1` filed alongside.

[CONFIRMED — phases ordered per DS-28 dependency-order: Phase 0 inventory feeds Phase 1 author + Phase 3 sweep target list; Phase 1 deliverable feeds Phase 2 wire-up; Phase 2 ships warn-mode and feeds Phase 3 sweep; Phase 3 zero-warning return gates Phase 4 promotion; Phase 4 strict-mode promotion gates Phase 5 docs hardening.]

---

## §6 — Pre-implementation gates Kim must approve

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

Each gate gets a Kim verdict before §5 phases proceed. Gate 9 is the hard pre-condition for Phase 4 (zero-warning sweep is verified before strict-mode flip).

---

## §7 — Risk assessment

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

**Top 3 risks by severity-x-likelihood:**
1. **Risk #1 — Existing script breakage on Phase 4 promotion** (MEDIUM × HIGH). Mitigated by Phase 3 sweep gate.
2. **Risk #5 — Migration race condition** (LOW × HIGH). Mitigated by explicit invalidation hook.
3. **Risk #8 — Dog-fooding recursion** (LOW × HIGH). Mitigated by `_VALIDATOR_INTERNAL_BYPASS` flag.

---

## §8 — Rollback per phase

| Phase | If broken, rollback | Recovery time est. |
|-------|---------------------|---------------------|
| Phase 0 | Non-mutating reconnaissance — no rollback needed. Just delete the inventory file. | Instant |
| Phase 1 | Delete `Production/lib/payload_validator.py` + companion test. No callers yet. | Instant |
| Phase 2 | Revert the one-line wire-up edit in `Production/lib/directus.py::try_post_or_queue`. Validator becomes dormant; existing pipeline restored. | <1 min |
| Phase 3 | Phase 3 is informational (warn-mode). Rollback = stop the sweep. No production impact. | Instant |
| Phase 4 | Edit `_resolve_mode` default from `'strict'` back to `'warn'`. New writes immediately revert to warn-mode. Existing in-flight strict-mode failures: caller's exception trace surfaces the field name; caller fixes payload + retries. | <5 min code; manual fix-up of any tripped writes |
| Phase 5 | Doc rollback — git revert the CLAUDE.md / schema-ref / memory edits. No production impact. | <1 min |

The most fragile rollback is Phase 4 (strict-mode flip): if a caller class is broken at promotion-time, every write from that class fails until either (a) the caller is fixed or (b) the override file adds a `'warn'` mode for that collection. Operator workflow under Phase 4 breakage: (a) check `_resolve_mode` default, flip to `'warn'`, ship to mainline as hotfix; (b) audit the breaking caller; (c) re-promote once caller fixed.

---

## §9 — Operational notes

### 9.1 — Debug toggle env var

`MN_PAYLOAD_VALIDATOR_DISABLE=1` — when set in environment, validator is a no-op. For one-off debug + emergency hotfix scenarios. NOT for production-tracked scripts. Documented in CLAUDE.md Rule 35 sub-section per Phase 5.

### 9.2 — Per-collection override file

Path: `~/.claude/state/payload_validator_overrides.json`. Schema:
```json
{
  "<collection_name>": {
    "mode": "strict | warn | skip",
    "extra_allowed_keys": ["additional_key_1", "additional_key_2"],
    "_note": "human-readable rationale; not parsed"
  }
}
```
Re-read at each call (cheap — file is tiny). Missing file = default mode for all collections. Per Decision 5 verdict, default = `'warn'` (Phase 2-3) or `'strict'` (Phase 4+).

### 9.3 — Logging strategy (dog-fooding the validator)

Every rejection/warn/strip is logged to `prod_activity_log` via `try_post_or_queue`. The validator's OWN log writes go through `try_post_or_queue` → would re-enter the validator → infinite recursion. Mitigation: thread-local `_VALIDATOR_INTERNAL_BYPASS = threading.local()`. The validator sets `_VALIDATOR_INTERNAL_BYPASS.active = True` before its log-write, calls `try_post_or_queue`, validator's entry-guard checks `getattr(_VALIDATOR_INTERNAL_BYPASS, 'active', False)` and bypasses validation. Sets back to False in a `finally`. The validator IS the audit channel for itself, but only with explicit bypass for its own writes.

### 9.4 — Telemetry expected post-Phase-4

- Activity-log row counts for `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_REJECT` per day (target: ≤1/week, anything more flags a caller bug).
- Activity-log row counts for `PAYLOAD_VALIDATOR_AUTO_FIELD_STRIPPED` per day (informational; expected non-zero for callers using `_AUTO_FIELDS` rebroadcast).
- `PAYLOAD_VALIDATOR_RETIRED_FIELD_USED` rows during the 14-day grace window per Decision 7; should drop to zero after the window.
- `SchemaProbeError` count during Directus outages (correlate with offline-queue depth in `pending_directus_writes.json`).

---

## §10 — Cursor cross-review companion handoff (FOLLOW-UP — NOT authored in this session)

**Path reserved:** `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`

**Scope of the Cursor review (when the handoff is authored):**
- Adversarial pass on each of the 7 design decisions in §3.
- Identify any Blocker (HIGH severity, would-block-implementation) — present per the SCHEMA_VOCAB_MIGRATION pattern (Cursor v6 found 3 Blockers in v5).
- Identify any non-Blocker findings (MED/LOW severity) for v2 amendment.
- Verify §5 phased rollout dependency-order is correct (Phase 0 → 1 → 2 → 3 → 4 → 5).
- Verify §6 Gate 10's claim that Cursor cross-review is REQUIRED for ARCHITECTURAL specs.
- Surface any caller-class in §0.1's 21-file inventory whose payload shape would NOT survive Phase 4 strict promotion.

**Why surface as follow-up:** Self-bound list in this session's handoff prompt explicitly forbids authoring this Cursor handoff. Kim spawns it separately.

[INFERRED — Cursor review is the established second-opinion pattern for ARCHITECTURAL specs in this codebase per the schema-vocab v3→v7 chain (each version had a Cursor cross-review handoff at `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v{N}.md`).]

---

## §11 — Reference index (verbatim cited files + LDs)

- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/directus.py` — where `try_post_or_queue`, `post_item_verified`, `_validate_json_columns`, `JSON_COLUMN_INVENTORY` live; Phase 2 wire-up edits this file (one-line addition in `try_post_or_queue`).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/directus_admin_client.py` — `DirectusAdminClient._request('GET', f'/fields/{collection}')` is the schema probe endpoint.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — current docs hardening (629 lines), enumerates per-collection field-names; Phase 5 cross-reference target.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` §6 Gate 11.2 (lines 142-180) — the v6 narrow validator pattern this generalizes; verbatim 3-line quote in §2.2.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — v7 spec (JSON-string-aware extractor); LD-598 reference.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff template that LD-597 anti-confusion guards updated with the 11-vs-12 field enumeration for `prod_activity_log` vs `prod_preflight_reviews`.
- `/Users/kimberlysmith/.claude/skills/zero-error-qa/SKILL.md` — DS-13 Layer 6 input/output variation; DS-19 absolute-path discipline; DS-26 ARCHITECTURAL escalation; DS-27 absolute-path; DS-28 dependency-order. This validator is itself a Layer 6 enforcement layer (it lives in the input→output flow at Directus write time).
- `/Users/kimberlysmith/.claude/skills/tech-spec/SKILL.md` v2 — §0 Operating Mode + §14 Pre-execution Checklist + §15 Audit + §16 Reference Index mandatory per memory `project_skills_updated_with_error_elimination_20260506.md`.
- **LD-595** (`SCHEMA_VOCAB_MIGRATION_V5_FIELD_NAME_FIX`) — v5 spec field-name fix; replaces `details` → `description+STRUCTURED_DETAILS_JSON`; replaces `resolution_notes` → appended-to-`description`. Filed 2026-05-08.
- **LD-596** (`SCHEMA_VOCAB_MIGRATION_V6_RUNTIME_VALIDATOR`) — v6 spec runtime payload-key validator `validate_prod_blockers_payload`; narrow (prod_blockers-only). Filed 2026-05-08.
- **LD-597** (`TASK_DESCRIPTION_FIELD_ANTI_CONFUSION_GUARDS_V1`) — anti-confusion guards in CLAUDE.md / schema-ref doc / memory file; 11-field `prod_activity_log` vs 12-field `prod_preflight_reviews` enumerations. Filed 2026-05-08.
- **LD-598** (`SCHEMA_VOCAB_MIGRATION_V7_JSON_STRING_AWARE_EXTRACTOR`) — v7 spec JSON-string-aware extractor for `STRUCTURED_DETAILS_JSON:` payload. Filed 2026-05-08.
- **LD-364** (`POST_ITEM_VERIFIED_V1`) — every Directus write uses `post_item_verified` for read-back-after-write. The validator proposed here runs BEFORE the POST; LD-364's verifier runs AFTER. Defense-in-depth.

---

## §12 — Changelog

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-05-08 | Initial spec authored. 7 design decisions debated (§3); per-decision action table (§4); 6-phase rollout (§5); 10 pre-implementation gates (§6); 10 risks (§7); per-phase rollback (§8); operational notes + override file + dog-fooding bypass (§9); Cursor cross-review companion flagged as follow-up (§10). Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` filed alongside. |

---

## §13 — Cross-references (related skills + rules)

- **CLAUDE.md Rule 35** — Directus schema verification before any prod_* write; this spec adds the runtime mechanical complement to Rule 35's documentation-based protection.
- **CLAUDE.md Rule 18** — Python urllib.request only (never curl); validator's schema probe uses `DirectusAdminClient` per Rule 18.
- **CLAUDE.md Rule 19** — No Shortcuts; validator is the no-shortcut answer to "we should validate field names mechanically not just by docs."
- **zero-error-qa SKILL.md DS-13 Layer 6** — input/output variation enforcement; this validator IS a Layer 6 layer.
- **zero-error-qa SKILL.md DS-19** — absolute-path discipline; every cited file in §11 is an absolute path under Dropbox-canonical root.
- **zero-error-qa SKILL.md DS-26** — ARCHITECTURAL classification + Cursor cross-review escalation.
- **zero-error-qa SKILL.md DS-27** — absolute paths; same as DS-19 above.
- **zero-error-qa SKILL.md DS-28** — dependency-order; §5 phases ordered per dependency.
- **tech-spec SKILL.md v2 §0 + §14 + §15 + §16** — Operating Mode + Pre-execution Checklist + Audit + Reference Index mandatory.
- **`Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` §6 Gate 11.2** — v6 narrow validator pattern this generalizes.

---

## §14 — Pre-execution checklist (per tech-spec skill v2)

Before Phase 1 implementation begins, Kim verifies each of these:

- [ ] §6 Gate 1 — Decision 1 verdict (strict end-state, phased path) approved.
- [ ] §6 Gate 2 — Decision 2 verdict (15-min TTL + invalidator hook) approved.
- [ ] §6 Gate 3 — Decision 3 verdict (separate `lib/payload_validator.py`) approved.
- [ ] §6 Gate 4 — Decision 4 verdict (fail-closed + queue-on-fail) approved.
- [ ] §6 Gate 5 — Decision 5 verdict (opt-out always-on + override file) approved.
- [ ] §6 Gate 6 — Decision 6 verdict (strip auto-fields with audit + override flag) approved.
- [ ] §6 Gate 7 — Decision 7 verdict (14-day grace for registered-retired fields) approved.
- [ ] §6 Gate 8 — §5 phased rollout (Phase 0 → 5) approved.
- [ ] §6 Gate 9 — Phase 4 strict-promotion gated on Phase 3 zero-warning sweep.
- [ ] §6 Gate 10 — Cursor cross-review handoff authored + Cursor verdict received.
- [ ] All 10 risks in §7 reviewed and mitigations approved (especially Risk #1, #5, #8 — top 3 by severity).
- [ ] §0 Operating Mode acknowledged (DESIGN ONLY this session; implementation gated).
- [ ] LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` confirmed filed (filing in this session per spec-LD POST below).
- [ ] Activity-log row `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1_AUTHORED_V1` confirmed filed.
- [ ] Wave A live-schema probe results referenced in §1 + §0.1 cross-checked against current Directus state.

---

## §15 — Audit (post-implementation telemetry)

Once Phase 4 is live, the validator's correctness is audited via:

1. **Daily count** of `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_REJECT` rows in `prod_activity_log`. Target: ≤1/week. Any spike triggers a caller-bug review.
2. **Cache hit rate** logged per `validate_payload` call (debug-mode only). Target: >95% hit rate in steady state.
3. **Schema-probe latency** distribution logged at p50 / p95 / p99. Target: p95 ≤ 300ms.
4. **Override-file consistency check** — weekly script `Production/scripts/payload_validator_override_audit.py` (NEW; Phase 5 deliverable) reads the override file and posts a summary row to `prod_activity_log`. Stale `'skip'` overrides (>30 days old) get flagged.
5. **Retired-field grace cleanup** — 14-day grace window expiry rows logged to `PAYLOAD_VALIDATOR_RETIRED_FIELD_GRACE_EXPIRED`; promote to immediate-reject mode at expiry.
6. **Dog-fooding recursion smoke test** — Phase 1 unit test verifies `_VALIDATOR_INTERNAL_BYPASS` correctly prevents recursion.

---

## §16 — Reference index (external docs + APIs)

- **Directus schema API** — `GET /fields/<collection>` returns `{data: [{field, type, schema, ...}, ...]}`. Used by validator's schema probe via `DirectusAdminClient._request('GET', f'/fields/{collection}')`.
- **Directus collections API** — `GET /collections` returns the list of all collections. Used in Wave A inventory; not used at runtime by the validator.
- **`functools.lru_cache`** — Python stdlib; alternative implementation backing for the schema cache (chose module-scope dict + manual TTL instead, for explicit invalidation control).
- **`threading.local()`** — Python stdlib; backing for `_VALIDATOR_INTERNAL_BYPASS` per §9.3 dog-fooding bypass.
- **`pathlib.Path`** — Python stdlib; backing for override-file read at `~/.claude/state/payload_validator_overrides.json`.

---

## Authoring metadata

- **Spec author:** Claude Opus 4.7 (1M context)
- **Authoring session date:** 2026-05-08
- **Authoring branch:** claude/gallant-bouman-804b4f (worktree)
- **Self-bound list compliance:** confirmed; no spec/handoff/schema-ref/hook/migration/LD modifications other than this spec + spec-LD + activity-log POST.
- **Wave A live-schema probe timestamp:** 2026-05-08 (this session)
- **Wave A inventory file:** [DEFERRED — Phase 0 deliverable will produce `Production/exports/payload_validator_caller_inventory_<DATE>.txt` in implementation session]

[CONFIRMED — every claim in this spec is anchored to a live-schema probe, an existing file/LD/spec, or an explicit synthesis paragraph in §3. Confidence tags applied throughout per zero-error-qa Rule 24.]
