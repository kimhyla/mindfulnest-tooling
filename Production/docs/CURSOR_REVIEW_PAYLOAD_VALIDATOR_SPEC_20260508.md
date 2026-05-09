# Cursor Cross-Review — DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1 (2026-05-08)

**Confidence tags (Rule 24):** Each paragraph tagged **CONFIRMED** (quoted from repo files / shell output), **INFERRED** (reasonable extension from cited design), or **GUESSED** (no strong evidence).

---

## Preflight evidence

### 1. Spec integrity **(CONFIRMED — my probe)**

- `ls -la`: `-rw-r--r--  60533 May  8 17:36 …/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md`
- `shasum -a 256`: `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75` — **matches** handoff expectation.

### 2. First 20 lines verbatim **(CONFIRMED — my probe)**

Lines 1–20 of `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md`:

```
     1|# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1
     2|
     3|**Authored:** 2026-05-08
     4|**Author:** Claude Opus 4.7 (1M context)
     5|**Status:** DESIGN ONLY — execution gated on Kim approval per §6
     6|**Self-classification:** ARCHITECTURAL (per zero-error-qa DS-26 / tech-spec skill v2 §0.1)
     7|**Scope:** Generic schema-aware payload validator covering ALL `prod_*` Directus collections
     8|**Generalizes:** v6 narrow validator pattern (`validate_prod_blockers_payload`) one architectural layer up
     9|**Companion:** Cursor cross-review handoff (NOT yet authored — see §10)
    10|
    11|---
    12|
    13|## §0 — Operating Mode
    14|
    15|This document is **DESIGN ONLY**. No code is written, no scripts are executed, no Directus rows are PATCHed, no LDs except the spec-LD itself are filed during the authoring of this spec. Per tech-spec skill v2 §0 + §14:
    16|
    17|- **Authoring this session:** spec markdown + spec-LD POST + activity-log POST. No more. Self-bound list at end of handoff prompt is binding.
    18|- **Implementation:** gated on Kim approving each of the 7 design decisions (§6 Gates 1-7) + the phased rollout sequence (§6 Gate 8) + the strict-promotion gate (§6 Gate 9) + the Cursor cross-review (§6 Gate 10).
    19|- **Cursor cross-review handoff:** NOT authored in this session. Surface as §10 follow-up. Path reserved at `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`.
    20|
```

First non-blank line: `# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1` — **PASS**.

### 3. Companion anchors **(CONFIRMED — my probe)**

**(a)** `Production/lib/directus.py` — `try_post_or_queue` at approximately lines 447–467 (ranges may drift):

- Signature / docstring opener and first body lines confirm the Phase 2 wire-up target matches the handoff (**CONFIRMED**): `def try_post_or_queue(collection: str, payload: dict, client: Optional[DirectusAdminClient] = None) -> dict:` then docstring bullets and `try: return post_item_verified(collection, payload, client=client)`.

**(b)** `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`:
- Heading `## 3. \`prod_preflight_reviews\`` under **§3 prod_preflight_reviews** lists live fields including `task_description` (CONFIRMED).
- Heading `## 4. \`prod_activity_log\`` under **§4 prod_activity_log** lists fields `id`, `module_id`, `action`, `details`, `performed_by`, `created_at`, `voice_settings`, `script_version`, `kim_verdict`, `kim_feedback`, `asset_id` (CONFIRMED; matches anti-confusion narrative).

**(c)** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md`:
- **`validate_prod_blockers_payload`** and **`ALLOWED_PROD_BLOCKERS_KEYS`** anchored at Gate 11.2 verification artifact (**CONFIRMED**): function uses `extra = set(payload.keys()) - ALLOWED_PROD_BLOCKERS_KEYS` and raises `RuntimeError` on extra keys — the narrow pattern this spec generalizes.

**(d)** `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` first line: `# Handoff v6 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v6` (**CONFIRMED**).

**(e)** `Production/docs/HANDOFF_TEMPLATE_v2.md` first line: `# Handoff Template v2` (**CONFIRMED**).

**(f–g)** v7 review handoff + v7 migration spec paths: `ls -la` returned present under canonical root #1 (**CONFIRMED — my probe**).

### 4. Spec anchor captures — summary **(CONFIRMED — excerpts on file)**

- **§0 Operating Mode:** full paragraph cites **DESIGN ONLY** binding scope (quoted in preflight lines 13–18 above).

- **§3 Decisions 1–7 synthesis verdict headlines (sentence-level):**
  1. **HYBRID:** strict-reject correct end-state; ship `mode='warn'` for sweep then flip strict after zero warnings (**CONFIRMED** — spec §3 Decision 1).
  2. **HYBRID:** 15-min TTL + **`invalidate_schema_cache()`** hook (**CONFIRMED** — §3 Decision 2).
  3. **Counter wins:** separate `Production/lib/payload_validator.py` + thin import/call from `try_post_or_queue` (**CONFIRMED** — §3 Decision 3).
  4. **Advocate wins with queue wrapper:** fail-closed at validator; **`SchemaProbeError`** caught → queue with **`schema_probe_failure`** (**CONFIRMED** — §3 Decision 4).
  5. **Advocate wins:** opt-out always-on + override file (**CONFIRMED** — §3 Decision 5).
  6. **Counter wins:** strip auto-fields **with** **`PAYLOAD_VALIDATOR_AUTO_FIELD_STRIPPED`** warning + audit; explicit override for intentional backdating (**CONFIRMED** — §3 Decision 6).
  7. **HYBRID:** **`RETIRED_FIELDS_REGISTRY`** + **14-day** grace for **registered** retired fields; unregistered unknowns rejected immediately (**CONFIRMED** — §3 Decision 7).

- **§4 Per-decision action table:** verbatim 7-row Markdown table Present under `## §4 — Per-decision action table` (**CONFIRMED**).

- **§5 Six phase headings:** **Phase 0** snapshot grep inventory → **Phase 1** author `payload_validator.py` + tests → **Phase 2** wire `try_post_or_queue` → **Phase 3** warn sweep ≥1 week / sweep script → **Phase 4** promote strict gated on Phase 3 clean → **Phase 5** docs (**CONFIRMED**). Dependency CONFIRMED note at end of §5.1 block (**CONFIRMED**).

- **§6 10-gate table:** Markdown table Gates 1–10 including Cursor Gate 10 (**CONFIRMED**).

- **§7 10-risk table + Top 3 risks** summary numbering risks #1, #5, #8 (**CONFIRMED**).

- **§9.3 `_VALIDATOR_INTERNAL_BYPASS`:** **`threading.local()`**, set **`.active = True`** before validator’s **`try_post_or_queue`** log-write, entry-guard short-circuit, reset in **`finally`** (**CONFIRMED**).

---

## ANALYSIS TABLES (tasks A–G)

**Citation rule:** Anchored headers + snippets (no brittle line-number-only proof).

---

### TASK A — Decision verdicts (7 decisions)

| # | Concern | Severity | Evidence (anchored citation) | Suggested mitigation | Blocker |
|---|---------|----------|-------------------------------|---------------------|---------|
| A1 | Low-volume collection coverage in Phase 3 | MED | §5 Phase 3: “≥1 week **OR** explicit run-each-script-once”; §0.1 shows uneven call frequency (**CONFIRMED**). Sweep script mitigates but operator discipline required. | Make Phase 3 exit checklist include “every collection touched at least once by sweep script OR rationale recorded.” | N |
| A2 | TTL + forgotten `invalidate_schema_cache()` mid-migration | MED | §3 Decision 2 + risk #2 row tie mitigations to phase-boundary hooks (**CONFIRMED**). | v2 checklist: migrations fail CI if phases touch schema without invalidation call template. | N |
| A3 | Circular imports validator ↔ directus | LOW | Decision 3: validator is separate module; **`try_post_or_queue`** imports **`validate_payload`** only (**CONFIRMED** design). **`INFERRED`**: avoid `payload_validator` importing `try_post_or_queue`; pass client or neutral logger. | Explicit “no upward import” rule + lint. | N |
| A4 | Partial Directus outage (POST up, `/fields` down) | MED | Advocate argument in Decision 4 notes partial failure as “real but bounded”; synthesis chooses queue (**CONFIRMED**). **`INFERRED`**: asymmetric outage plausible. | Document correlation: queue depth spike + **`schema_probe_failure`** reason. Optional health preflight doc. | N |
| A5 | Override semantics (wildcards etc.) | LOW | §5.1 Phase 1 + §9.2 JSON schema lists per-collection map only (**CONFIRMED**). No wildcard — by design unless extended. | v2 clarify “no inheritance/wildcards v1”; or add explicit **`extra_allowed_keys`** only. | N |
| A6 | `_AUTO_FIELDS` vs per-collection realities | MED | Decision 6 reuses **`_AUTO_FIELDS`** from **`lib/directus.py`** (**CONFIRMED**). Risk #6 captures backdating (**CONFIRMED**). **`INFERRED`**: uncommon collection-specific server fields edge case. | Unit tests against `/fields` snapshot hashes in CI; doc “unknown auto server field ⇒ treat as strip+warn audit.” | N |
| A7 | Registry drift (`RETIRED_FIELDS_REGISTRY`) | MED | Decision 7 + risk #9 mitigation = migration checklist item (**CONFIRMED**). **`INFERRED`**: human lapse still possible | Automate lint: schema diff ⇒ registry diff required. | N |

**Numeric threshold (Task A):** No verdict where synthesis is **demonstrably wrong** counter-example (**INFERRED**). **PASS — no AMEND trigger from Task A.**

---

### TASK B — Phase plan

| # | Concern | Severity | Evidence | Mitigation | Blocker |
|---|---------|----------|----------|------------|---------|
| B1 | Phase 3 depends on Phase 2 | LOW | §5.1 CONFIRMED dependency ordering: Phase 2 ships warn routing through wrapper before Phase 3 sweep (**CONFIRMED**). | None — aligned. | N |
| B2 | Phase 4 concurrency / rollback | MED | §8 Phase 4 rollback row documents `_resolve_mode` flip (**CONFIRMED**). **`INFERRED`**: concurrent long jobs during flip. | Hotfix playbook already implied; reinforce in Phase 5 docs. | N |
| B3 | “Phase 6” audit | LOW | Phase 5 is doc + LD; telemetry §9.4 post-Phase-4 (**CONFIRMED**). No separate Phase 6 — acceptable if Kim accepts Phase 5 as closure. | Call out in Kim gate 8 that post-implementation audit is Phase 5 + §15. | N |
| B4 | Phase 1 = module + tests | LOW | Combined in one Phase 1 (**CONFIRMED**). Optional split cosmetic only. | **GUESSED** — not forcing AMEND. | N |

**Numeric threshold (Task B):** **PASS** — no reorder/split rises to AMEND threshold.

---

### TASK C — Risk table

| # | Concern | Severity | Evidence | Mitigation | Blocker |
|---|---------|----------|----------|------------|---------|
| C1 | Schema type representation drift | MED | Risks skew to cache/probe/order; **`INFERRED`** Directus **`/fields`** type quirks exist but validator is **key-only** (**CONFIRMED** §1 non-goals value validation). Lower blast than value-type mismatches already handled elsewhere. | Note in Phase 5: keys derived from **`field`** name only. | N |
| C2 | Override-file read races | MED | **`INFERRED`** not specified (**CONFIRMED** absence). | v2 atomic read / last-write-wins + doc. | N |
| C3 | Bad probe response poisoning cache | MED | Bounded by TTL + **`INFERRED`** no sanity row in §5.0. | Minimum field sanity + **`id`** check in implementation spec v2 optional. Risk row could elevate. | N |
| C4 | Activity-log spam DoS | LOW | **`INFERRED`** no rate-limit in spec (**CONFIRMED** no mention). **`GUESSED`** ops concern not production API DoS severity per rubric MED not HIGH-alone. | Sampling / dedupe key suggestion for v2. | N |

**Numeric threshold (Task C):** **PASS** — no **missing HIGH-severity risk** cleanly above table coverage without debate (**INFERRED**).

---

### TASK D — Performance + scaling

Assumptions **(INFERRED / GUESSED):** Typical script &lt; 15 min **(CONFIRMED — spec stance)**; **`set`** diff O(keys) tiny.

| # | Concern | Severity | Evidence | Mitigation | Blocker |
|---|---------|----------|----------|------------|---------|
| D1 | Steady-state per-write **(cache hit)** | LOW | **`INFERRED`**: set-difference on tens of keys is sub-millisecond CPU on laptop-class hardware (**GUESSED** p99 far below **50 ms** threshold). Aligns with spec §7 risk #3 “LOW LOW” (**CONFIRMED**). | Phase 1 micro-benchmark stays as spec suggests. | N |
| D2 | Cache-miss amortization | LOW | Spec §5.0 + Decision 2: 15 min TTL; first write/collection/process pays probe (**CONFIRMED**). For Kim’s predominantly short-lived scripts, miss rate is much less than writes (**INFERRED**). | Optional v2: refresh TTL on successful access per handoff perf edge case. | N |
| D3 | Long daemons | MED | TTL implies bounded probe frequency (**CONFIRMED** design). **`INFERRED`**: acceptable for audit workload volumes described. | Count collections × probe cost if watchers exist. | N |
| D4 | Multi-process probes | MED | **`INFERRED`**: cold-start burst—not rate-limit concern at stated scale (**GUESSED**). | Retry/backoff belongs in **`DirectusAdminClient`** if telemetry shows spikes. | N |

**Computation (threshold D):** With **N** writes per process per collection where **N** is typically large and TTL **900 s**, unconditional miss probability per write is roughly **1/N**, hence **below 10%** in normal mix (**INFERRED**).

**PASS — Task D numeric threshold.**

---

### TASK E — Failure modes

| # | Concern | Severity | Evidence | Mitigation | Blocker |
|---|---------|----------|----------|------------|---------|
| E1 | Probe + POST both fail vs queue | MED | **`try_post_or_queue`** queues **`DirectusWriteError`**, **`DirectusReadError`**, and generic **`Exception`** (**CONFIRMED** in `Production/lib/directus.py`). Spec extends queue path for **`SchemaProbeError`** (**CONFIRMED** §5 Decision 4). **`INFERRED`**: disk-full double-fault inherits grim last-ditch path. | v2 §9 note: sentinel if offline queue fails. | N |
| E2 | Stale cache vs live schema shrink | MED | Accepted window bounded by TTL (**CONFIRMED** §5.0); risk #2 MEDIUM (**CONFIRMED**). **`post_item_verified`** read-back remains (**CONFIRMED** §1). | Optional v2 shorten TTL mid-migration. | N |
| E3 | Validator rejects good payload | MED | §8 rollback to **`warn`** (**CONFIRMED**). | None. | N |
| E4 | **Malformed override JSON on disk** | **HIGH** | §9.2 documents missing file ⇒ defaults (**CONFIRMED**); **no** documented behavior when file is present but JSON parse fails (**CONFIRMED** — absent from §9). | **v2 REQUIRED:** specify one behavior + activity-log diagnostic + Phase 1 test. | **Y** |

**Numeric threshold (Task E):** **FAIL — AMEND trigger** (**CONFIRMED** gap at **§9.2**).

---

### TASK F — Dog-fooding recursion

| # | Concern | Severity | Evidence | Mitigation | Blocker |
|---|---------|----------|----------|------------|---------|
| F1 | `threading.local()` vs async | LOW | No `async` in `Production/lib/directus.py` (**CONFIRMED** grep). | If async added later, use **`contextvars`**. | N |
| F2 | Bypass reset | LOW | §9.3 mandates **`finally`** (**CONFIRMED**). | Phase 1 unit test asserts reset after exception paths. | N |
| F3 | Test coverage depth | MED | Implement smoke per §15 audit plan (**CONFIRMED** §15 heading exists). | Assert both non-recursion and flag lifecycle. **INFERRED** practice. | N |

**PASS — Task F.**

---

### TASK G — Backward compatibility

| # | Concern | Severity | Evidence | Mitigation | Blocker |
|---|---------|----------|----------|------------|---------|
| G1 | Warn path | LOW | §5 Phase 3 logging + proceeding write (**CONFIRMED**). | Ensure log payload richness. **INFERRED**. | N |
| G2 | Exit criterion feasibility | MED | Sweep script cited (**CONFIRMED** §5). | Operator may rely on scripted sweep for cold callers. **INFERRED**. | N |
| G3 | Hidden branches | MED | Conditional error paths underspecified (**INFERRED**). | Coverage matrix in Phase 3 report. Optional v2. | N |

**PASS — Task G numeric threshold.** Unknown keys at **`dict`** write time are observable (**CONFIRMED** generalization from v6 three-line validator pattern quoted in §2.2).

---

## Verdict (pick exactly one)

### `AMEND_V2`

**Defect:** **`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1` §9.2** does not define behavior when **`payload_validator_overrides.json` exists but is not parseable JSON** (or wrong top-level type). This fails the Task **E** requirement for an explicit documented handler and creates implementer ambiguity that can become production friction.

**Required v2 amendment:** Add under **§9.2** (and reference from **§5.1** Phase 1 module contract) a single normative rule: e.g. **parse failure ⇒ fall back to default modes for all collections + emit `prod_activity_log` row `PAYLOAD_VALIDATOR_OVERRIDE_LOAD_FAILED`** (or alternative fail-closed+queue)—**exactly one** normative path plus a §7 risk row update if severity warrants.

Optional v2 backlog (non-blocking): override read races (**§9.2**), probe sanity checks (**§5.0**), Phase 3 path-coverage checklist.

---

## Limitations / cross-skill drift

| Topic | Tag |
|--------|-----|
| LD-599 `status=active` + `decision_key` exact match | **(unverified)** — no live **`DirectusAdminClient`** probe per handoff §0.2; treat as **author attestation**. |
| Cross-links to weekly audits / skills when shipped | **(INFERRED)** Phase 5 already lists CLAUDE.md / schema-ref / memory (**CONFIRMED** §5)—may add backlinks in automation scripts and templates. |

---

## Self-classification

**REVIEW** — independent design review; no code edits to the spec per handoff.

---

## Concise→full escalation (mandatory)

> If any required section cannot be evidenced, full mode is mandatory.

All filesystem anchors + hash evidenced **(CONFIRMED — my probe)** except live LD row **(unverified)** as stated.
