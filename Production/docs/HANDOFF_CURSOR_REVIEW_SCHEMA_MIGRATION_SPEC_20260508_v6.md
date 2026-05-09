# Handoff v6 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v6

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` (50,827 bytes; sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`).

**Supersedes:** `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v5.md` (preserved as historical baseline; do NOT edit in place). v5 handoff covered v5 spec; that review returned `AMEND_V2` earlier today (3 HIGH/Y blockers + 2 non-blocker recommendations). v6 is a SURGICAL 5-element fix-set over v5 addressing exactly those 5 findings. v3-v5 design surface remains authorized; this handoff narrows Cursor's scope to v6's 5 fixes ONLY.

**v5 → v6 driver (Cursor AMEND_V2 verdict — 3 HIGH/Y blockers + 2 non-blockers):**
- **Blocker A (HIGH, Y):** v5 §9.4 stale-mutex parser used raw `json.loads(match.group(1))` with no try/except. v6 introduces `extract_structured_payload(description) -> Optional[dict]` wrapping `json.loads` in `try/except json.JSONDecodeError`; on failure, posts `STALE_MUTEX_PARSE_FAILURE` activity-log row + falls back to manual-review path.
- **Blocker B (HIGH, Y):** v5 §6 Gate 11.2 was a grep-based + line-based lint with bypass vulnerabilities (token concat / computed keys / helper wrappers / dict-spread / carve-out collisions). v6 REPLACES with runtime payload-key validator `validate_prod_blockers_payload(payload)` invoked immediately before every `prod_blockers` POST/PATCH; `ALLOWED_PROD_BLOCKERS_KEYS` is the exact 8 live fields; raises `RuntimeError` if extra keys present. Pre-launch CI AST-based lint documented as defense-in-depth (NOT load-bearing).
- **Blocker F (HIGH, Y):** v5 §9.4 regex `r"STRUCTURED_DETAILS_JSON:\s*(\{.*?\})\s*$"` was brittle for nested JSON + trailing same-line text. v6 REPLACES with delimiter-find + balanced-brace JSON extraction inside `extract_structured_payload`.
- **Non-blocker D (MED, N):** v3+v4+v5 historical example bodies created copy-paste hazard. v6 adds HAZARD WARNING blocks at §5 + §6 + above each historical §0.1 row (`DO NOT IMPLEMENT FROM HISTORICAL CONTENT — §9.4 v6 IS AUTHORITATIVE`).
- **Non-blocker E (LOW, N):** v5 description-append release lifecycle had unbounded growth + lacked structured-payload schema versioning. v6 caps appended resolution text at `RESOLUTION_APPEND_MAX_CHARS = 256` with `[truncated]` marker; acquisition POST adds `schema_version: "v1"` to STRUCTURED_DETAILS_JSON payload.

**Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical):**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — Dropbox-rooted (canonical root #1; **spec under review**); sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — Dropbox-rooted (canonical root #1; v5 historical baseline — v6's direct predecessor); sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — Dropbox-rooted (canonical root #1; v4 historical baseline).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — Dropbox-rooted (canonical root #1; v3 historical baseline — design surface authorized via prior `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE`).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v5.md` — Dropbox-rooted (canonical root #1; **prior review handoff** — structural template for THIS handoff; v5 review returned AMEND_V2).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Dropbox-rooted (canonical root #1; §5 = ground truth for v6 fix verification; v6 hazard warning at lines 304-318 already mirrors spec; 8-field enumeration at lines 327-336; severity enum at 340-347; STRUCTURED_DETAILS_JSON pattern at 378-388 includes `schema_version: "v1"` per LD-596).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — Dropbox-rooted (canonical root #1; implementation handoff; §6 prod_blockers schema gotchas at v2.3 explicitly cites v6 + helpers `extract_structured_payload` + `validate_prod_blockers_payload` per LD-596 — confirmed landed by parallel agent earlier this session at lines 520-521).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1; this handoff conforms to v2 template — anchored citations, concise→full escalation, numeric AMEND_V3 thresholds, dual-canonical absolute paths, companion path discipline).

---

## §0.1 — Why this v6 review exists

v5 spec received `AMEND_V2` from Cursor earlier today (3 HIGH/Y blockers + 2 non-blocker recommendations). v6 was authored as Kim's authorized response: a SURGICAL 5-element fix-set over v5 addressing exactly Blockers A + B + F + non-blockers D + E. v6 is NOT a re-review of design surface — that was authorized via the prior v3 verdict and remains in effect. This v6 review tightens scope to verification of the 5 fixes ONLY.

v6 needs a TIGHT cross-review specifically on:
1. **§9.4 `extract_structured_payload`** — Blocker A (try/except guard + STALE_MUTEX_PARSE_FAILURE diagnostic) + Blocker F (balanced-brace extraction) merged into one function.
2. **§6 Gate 11.2 v6 REPLACEMENT** — Blocker B (runtime validator `validate_prod_blockers_payload` + `ALLOWED_PROD_BLOCKERS_KEYS` constant) replacing v5's grep-based lint.
3. **§5 + §6 + §0.1 historical-row hazard warnings** — non-blocker D (5 hazard warning blocks above historical content references).
4. **§9.4 acquisition POST + release PATCH** — non-blocker E (`schema_version: "v1"` in payload + `RESOLUTION_APPEND_MAX_CHARS = 256` cap with `[truncated]` marker).
5. **§7 risk #14 clarification + risk #15 (NEW)** — likelihood-condition update on #14 + risk #15 documenting the regex-extraction failure mode (LOW/MED).

The v3-v5 design surface (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, mutex pattern, Task H lock_decision.py, severity case-fold from v4, field-name fix from v5, the v5 STRUCTURED_DETAILS_JSON-anchored encoding pattern itself) is OUT OF SCOPE for this v6 review — it remains authorized.

---

## §0.2 — What you DON'T need to do

- Do NOT re-review v3-v5 design surface (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, mutex pattern, Task H, severity case-fold from v4, field-name fix from v5). Already authorized via prior verdicts.
- Do NOT re-review the v5 STRUCTURED_DETAILS_JSON-anchored encoding pattern itself — v6 preserves it verbatim and only hardens the parse / validate / cap / version surface around it.
- Do NOT have Cursor edit v6. Verdict-only.
- Do NOT have Cursor implement the migration. Implementation handoff is at `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` (post-v2.3 amendment landed); this handoff is review-only.
- Do NOT have Cursor sample CRITICAL rows from `prod_locked_decisions` — out-of-scope for v6 surgical fix-set.

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|-----------------|----------------|-------------|
| 1 | Has spec v6 sha256 been confirmed match `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`? | `shasum -a 256` of v6 spec absolute path | Hash matches verbatim | HALT — author drift; surface to Kim |
| 2 | Has v6 §9.4 v6-callout block been read into context? | Quote anchor: locate `### §9.4 — Concurrency, lockfile, and remote mutex (v6 PARSER + VALIDATOR + CAP + SCHEMA_VERSION HARDENING over v5 — Cursor AMEND_V2 fix-set: Blockers A + B + F + non-blockers D + E)` header in v6 spec; capture the v6-authoritative paragraph + the `extract_structured_payload` function definition + the acquisition POST + release PATCH + stale-mutex cleanup blocks | Reviewer emits the v6 §9.4 callout text + `extract_structured_payload` function body + 3 v6-hardened code blocks (acquisition / release / stale-mutex cleanup) | HALT and report which anchor failed |
| 3 | Has v6 §6 Gate 11.2 v6 REPLACEMENT block been read into context? | Quote anchor: locate the row beginning `| 11.2 | **(v6 — Cursor AMEND_V2 Blocker B; REPLACES v5 grep-based gate)**` in v6 §6; capture the gate row + Gate 11.2 verification artifact code block (the `ALLOWED_PROD_BLOCKERS_KEYS` constant + `validate_prod_blockers_payload` function + call-site rule) | Reviewer emits the Gate 11.2 row text + the validator function body + call-site convention | HALT and report which anchor failed |
| 4 | Has v6 §7 risk #14 clarified + risk #15 NEW been read into context? | Quote anchor: locate the row beginning `**(v5 — #14; v6 likelihood condition clarified)**` in v6 §7; ALSO locate the row beginning `**(v6 NEW — #15)**` | Reviewer emits both risk rows verbatim including likelihood/severity/mitigation chain | HALT and report which anchor failed |
| 5 | Has v6 §5 + §6 + §0.1 hazard-warning blocks been read into context? | Quote anchor: locate `> **§5-LEVEL HAZARD WARNING (v6 NEW; Cursor non-blocker D):**` in §5; ALSO locate `> **§6-LEVEL HAZARD WARNING (v6 NEW; Cursor non-blocker D):**` in §6; ALSO locate the 3 `> **HAZARD WARNING — do not implement from this preserved historical row.**` blocks in §0.1 (above v5 / v4 / v3 historical rows) | Reviewer emits all 5 hazard-warning blocks verbatim | HALT and report which anchor failed |

---

## Step 0 — Preflight (do FIRST, before any analysis) — anchored discipline

Mandatory actions, emit inline:

1. **`ls -la` v6 spec absolute path:**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md"
   ```
   Expected: file exists, size 50,827 bytes, mtime 2026-05-08.

2. **`shasum -a 256` v6 spec:**
   ```sh
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md"
   ```
   Expected output: `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae  <path>`. **HALT if hash differs — author drift detected; surface to Kim before proceeding.**

3. **Quote first 20 lines of v6 spec verbatim** (stale-cache detector). The first non-blank line MUST be `# Schema Vocab Migration — Tech Spec v6`. Capture lines 1-20 with line numbers.

4. **Companion-file integrity (anchored — header/snippet ONLY):**
   - (a) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor `## 5. \`prod_blockers\`` heading; capture the 8-field list section AND the `HAZARD WARNING (2026-05-08; mirrors v6 spec §5 + §6 hazard blocks)` block (currently at lines ~302-318) to confirm schema-ref doc cross-pointer to v6 already lives in the canonical reference.
   - (b) `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — anchor `# Schema Vocab Migration — Tech Spec v5` (first line); capture v5 §0.1 v5-A row to confirm v5 deferred-fix lineage that v6 closes.
   - (c) `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v5.md` — anchor `# Handoff v5 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v5` (first line); confirm prior AMEND_V2 verdict context exists.
   - (d) `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — anchor `### prod_blockers schema gotchas` heading in §6; capture the v2.3 amendment block (currently at lines ~520-521) which cites v6 helpers `extract_structured_payload` + `validate_prod_blockers_payload` + LD-596. (NOTE: if this anchor is missing, the implementation handoff has not yet landed v2.3 amendment — surface that in the preflight report; do NOT HALT, since the parallel agent may be mid-flight.)

If preflight 1-3 fails, HALT and report. If 4 fails for any companion file, document inline; if all 4 fail, HALT.

---

## Step 1 — Open the project in Cursor

Project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Open `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md`.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md (v6 — supersedes v5 which superseded v4 which superseded v3). v6 is a SURGICAL 5-element fix-set over v5 addressing your own AMEND_V2 verdict on v5 (3 HIGH/Y blockers — A, B, F — + 2 non-blockers — D, E). v3-v5 design surface is preserved + already authorized; do NOT re-review it. Re-review specifically:
  - §9.4 `extract_structured_payload(description)` (Blockers A + F)
  - §6 Gate 11.2 v6 REPLACEMENT — runtime validator `validate_prod_blockers_payload` + `ALLOWED_PROD_BLOCKERS_KEYS` (Blocker B)
  - §5 + §6 + §0.1 historical-row hazard warnings (non-blocker D)
  - §9.4 acquisition POST `schema_version: "v1"` + release PATCH `RESOLUTION_APPEND_MAX_CHARS = 256` cap (non-blocker E)
  - §7 risk #14 likelihood-clarification + risk #15 NEW (regex-extraction failure mode)

Background context (informational only):
- v5 returned AMEND_V2 with: Blocker A (raw json.loads in stale-mutex parser, no try/except), Blocker B (grep-based + line-based Gate 11.2 lint with bypass vulnerabilities), Blocker F (brittle lazy-regex + `$` anchor for nested JSON / trailing same-line text), non-blocker D (historical example body copy-paste hazard), non-blocker E (description-append unbounded growth + missing schema_version).
- v6 §9.4 introduces `extract_structured_payload(description: str) -> Optional[dict]`: marker `STRUCTURED_DETAILS_JSON:` find → `{` find → balanced-brace counter increment/decrement → `try/except json.JSONDecodeError`; returns None on (a) marker absent, (b) opening brace absent, (c) unbalanced braces, (d) JSONDecodeError.
- v6 §6 Gate 11.2 introduces `ALLOWED_PROD_BLOCKERS_KEYS = {id, module_id, severity, title, description, is_resolved, created_at, resolved_at}` (8 fields; matches live `prod_blockers` schema per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 lines 327-336) + `validate_prod_blockers_payload(payload: dict) -> None` raising `RuntimeError` if `set(payload.keys()) - ALLOWED_PROD_BLOCKERS_KEYS` is non-empty. Validator MUST be invoked immediately before every `client.post_item("prod_blockers", ...)` and `client.patch_item("prod_blockers", id, ...)`. AST-based pre-launch CI lint documented as defense-in-depth, NOT load-bearing.
- v6 §9.4 acquisition POST adds `schema_version: "v1"` to STRUCTURED_DETAILS_JSON payload. v6 §9.4 release PATCH caps appended resolution-text at `RESOLUTION_APPEND_MAX_CHARS = 256` with `[truncated]` marker if exceeded.
- v6 §5 + §6 + §0.1 add 5 HAZARD WARNING blocks: §5-level + §6-level + 3 above v5/v4/v3 historical §0.1 rows. Each block reads "DO NOT IMPLEMENT FROM HISTORICAL CONTENT — §9.4 v6 IS AUTHORITATIVE."
- v6 §7 keeps risk #14 at LOW likelihood (with v6 hardened lint; if lint dropped/reverted, raise to MED) + adds risk #15 (regex-extraction failure mode; LOW/MED with graceful fallback to manual-review path via STALE_MUTEX_PARSE_FAILURE activity-log row).

Authority: LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1 (v6 NEW; filed 2026-05-08 same session as v6 spec).

Apply your full independent scrutiny on the v6-scope changes only. The v3-v5 design is locked.

PREFLIGHT (do first, emit inline) — anchored discipline:
1. Confirm spec v6 file exists; capture size + mtime + shasum.
   Expected sha256: e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae
   HALT if mismatch — author drift.
2. Quote the first 20 non-blank lines of spec v6 verbatim with capture-line-range.
   First line MUST be: "# Schema Vocab Migration — Tech Spec v6"
3. Companion-file integrity (anchored header/snippet only):
   (a) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor "## 5. `prod_blockers`"; quote the 8-field enumeration AND the `HAZARD WARNING (2026-05-08; mirrors v6 spec §5 + §6 hazard blocks)` block.
   (b) `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — anchor `# Schema Vocab Migration — Tech Spec v5`; quote v5 §0.1 v5-A row trailing paragraph (the field-name fix that v6 builds on).
   (c) `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v5.md` — anchor `# Handoff v5 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v5`; confirm prior AMEND_V2 verdict context exists.
   (d) `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — anchor `### prod_blockers schema gotchas` heading in §6; quote the v2.3 amendment block citing v6 helpers + LD-596. (If anchor is missing, surface "v2.3 amendment may not yet be present" inline; do NOT HALT.)
4. v6-specific anchor capture:
   (i) Locate `### §9.4 — Concurrency, lockfile, and remote mutex (v6 PARSER + VALIDATOR + CAP + SCHEMA_VERSION HARDENING over v5 — Cursor AMEND_V2 fix-set: Blockers A + B + F + non-blockers D + E)` header; quote the v6-authoritative paragraph + `extract_structured_payload` function body + the 3 v6-hardened code blocks (acquisition / release / stale-mutex cleanup) verbatim with line-range.
   (ii) Locate v6 §6 Gate 11.2 row + Gate 11.2 verification-artifact code block (`ALLOWED_PROD_BLOCKERS_KEYS` + `validate_prod_blockers_payload` + call-site rule); quote both verbatim.
   (iii) Locate v6 §7 risk #14 (clarified) row + risk #15 (NEW) row; quote both verbatim.
   (iv) Locate v6 §5 + §6 + §0.1 hazard-warning blocks (5 total: §5-level, §6-level, §0.1-above-v5, §0.1-above-v4, §0.1-above-v3); quote each verbatim.
If preflight 1-3 fails, HALT and report.

CONCISE→FULL ESCALATION RULE (mandatory verbatim per HANDOFF_TEMPLATE_v2):
> If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced": could not read v6 spec; could not reproduce a v6-scope anchor (header/snippet match in actual file content); the v6 §9.4 / §6 Gate 11.2 / §5 + §6 + §0.1 hazard-warning / §7 risk #14+#15 surface is missing or ambiguous; reviewer's evidence is "I think" or "probably" rather than a quoted citation; reviewer skipped a question to save tokens. Document WHICH area was under-evidenced in full-mode output.

ANALYSIS REQUIREMENTS (citation table format):
| # | Concern | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (anchored citation: section header + snippet match, NOT line numbers alone) | Suggested mitigation | Blocker (Y/N) |

REQUIRED ANALYSIS TASKS (v6-scope only — 5 fixes):

A. BLOCKER A FIX VERIFICATION — `extract_structured_payload` try/except guard + STALE_MUTEX_PARSE_FAILURE diagnostic
   Confirm:
   (a) `extract_structured_payload(description: str) -> Optional[dict]` is defined inside §9.4 with explicit `try: return json.loads(description[start:end]); except json.JSONDecodeError: return None`.
   (b) The function returns `None` on FOUR distinct failure modes: marker absent, opening brace absent, unbalanced braces (truncated payload), JSONDecodeError (corrupt payload).
   (c) On `None` return, the §9.4 stale-mutex cleanup helper posts a `STALE_MUTEX_PARSE_FAILURE` activity-log row including blocker_row_id, blocker_title, description_preview (truncated to 1024 chars), spec_reference, and remediation pointer.

   Edge cases to flag (independent scrutiny):
   - What if the `description` field on the prod_blockers row is None (live schema marks `description` as nullable)? Does `extract_structured_payload(None)` crash on `description.find(marker)` (AttributeError on NoneType)? The §9.4 stale-mutex cleanup snippet does `description = blocker_row.get("description", "") or ""` before calling — confirm the function itself does NOT need to defend against None.
   - What if marker `STRUCTURED_DETAILS_JSON:` appears MULTIPLE times in description (e.g., spec_version "v2" appended an updated payload)? The function uses `description.find(marker)` which returns the FIRST occurrence; later payloads silently ignored. Is this acceptable, or should the function find the LAST occurrence (rfind)?
   - What if extraction returns None on the SAME row repeatedly across multiple cleanup invocations? Does the activity-log row pattern create unbounded duplicates? Should there be deduplication logic?

   NUMERIC THRESHOLD: if Cursor identifies a NEW failure path in `extract_structured_payload` that v6 does NOT handle (e.g., None-input crash; a fifth distinct failure mode beyond the four documented; an edge case in balanced-brace counting that mis-extracts), verdict MUST be AMEND_V3 on Task A.

B. BLOCKER B FIX VERIFICATION — runtime validator `validate_prod_blockers_payload` + `ALLOWED_PROD_BLOCKERS_KEYS`
   Confirm:
   (a) `ALLOWED_PROD_BLOCKERS_KEYS` is exactly the 8 live fields per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (lines 327-336): `{id, module_id, severity, title, description, is_resolved, created_at, resolved_at}`. No more, no less.
   (b) `validate_prod_blockers_payload(payload: dict) -> None` computes `extra = set(payload.keys()) - ALLOWED_PROD_BLOCKERS_KEYS` and raises `RuntimeError` if `extra` is non-empty.
   (c) §9.4 acquisition POST + release PATCH each include a `validate_prod_blockers_payload(...)` line IMMEDIATELY BEFORE the `client.post_item(...)` / `client.patch_item(...)` call.

   Edge cases to flag (independent scrutiny):
   - **Dict-spread with computed keys at runtime** — `payload = {**base_dict, "deta" + "ils": value}` produces a dict with `"details"` key at runtime. The validator catches this because `payload.keys()` returns `{"details", ...}` regardless of how it got built. Confirm.
   - **Wrapper functions that build payload via kwargs** — `def post_blocker(**kwargs): client.post_item("prod_blockers", kwargs)` — does the migration script have wrappers that build payloads outside the §9.4 acquisition/release blocks? If so, do those wrappers ALSO call `validate_prod_blockers_payload`? Audit: does §6 Gate 11.2 call-site rule explicitly cover helpers like `release_stale_mutex.py`? (The spec says yes — "every helper that writes to prod_blockers, including release_stale_mutex.py" — confirm this is enforceable / discoverable at code-review time.)
   - **Untyped Mapping inputs** — what if `payload` is not a dict but a `Mapping` subclass (e.g., a `MultiDict` or `frozendict`)? `set(payload.keys())` should still work, but the type signature says `payload: dict`. Strict type-checked codebases would flag passing a non-dict.
   - **Empty payload dict `{}`** — does the validator raise or pass? Per the algorithm, `set({}.keys()) - ALLOWED = set()` is empty → passes. But `client.post_item("prod_blockers", {})` would fail at the HTTP level for missing required fields (`title`, `description`). Acceptable: the validator's job is to catch unknown-field violations, not missing-required-field violations.
   - **Read-back per Rule 35** — after PATCH, the script reads back the row to confirm persistence. Does the read-back path also need validation? (No — read-back is GET-only, no payload.)

   NUMERIC THRESHOLD: if Cursor identifies a runtime-validator bypass with ≤3 lines of evasion code (e.g., monkey-patching the validator function; raw HTTP request bypassing `client.post_item`; calling a helper that wraps `client.post_item` without validator invocation), verdict MUST be AMEND_V3 on Task B with a recommended hardening (e.g., wrap `client.post_item` itself with a decorator that auto-invokes the validator for prod_blockers; or add the validator call inside `client.post_item` for the `prod_blockers` collection name).

F. BLOCKER F FIX VERIFICATION — balanced-brace JSON extraction in `extract_structured_payload`
   Confirm:
   (a) The balanced-brace algorithm: find marker → find first `{` after marker → walk character-by-character incrementing depth on `{` and decrementing on `}` → return slice when depth returns to 0.
   (b) Handles nested JSON correctly — e.g., `{"a": {"b": 1}}` extracts the OUTER object, not the inner.
   (c) Trailing same-line text after JSON does NOT break extraction — e.g., `STRUCTURED_DETAILS_JSON: {"a":1} | RESOLVED: ...` correctly extracts `{"a":1}` and stops at the matching closing brace.
   (d) Unbalanced JSON (truncated payload, e.g., `{"a":1` with no closing brace) returns `None` gracefully, NOT raises.

   Edge cases to flag (independent scrutiny):
   - **Nested arrays** — JSON like `{"items": [1, 2, {"nested": true}]}` — arrays use `[ ]` brackets, not `{ }`, so the balanced-brace counter ignores them. The inner `{"nested": true}` increments and decrements depth correctly. Confirm: does the extractor correctly handle the case where the OUTER closing `}` comes AFTER the inner closing `}` plus closing `]`?
   - **Escaped braces in string values** — JSON strings can contain `{` or `}` characters when escaped or as literal text inside quotes (e.g., `{"text": "this has {curly} braces"}`). The current algorithm does NOT track string state — it just counts `{` and `}` characters. A `{` inside a JSON string would falsely increment depth, then a matching `}` inside a JSON string would falsely decrement. Edge case: would this cause the extractor to slice the wrong substring?
   - **Very large JSON payloads** — what if the payload is ~10KB or larger? The character-by-character loop is O(n); acceptable for typical mutex payloads (~200 bytes) but concerning if `schema_version` evolves to include large nested structures (e.g., closure_criteria lists per the schema-ref doc lines 378-388 example).
   - **Multiple JSON objects on the same line** — e.g., `STRUCTURED_DETAILS_JSON: {"a":1} {"b":2}` — extractor correctly extracts the FIRST one. Acceptable.
   - **Whitespace inside the JSON** — e.g., `{ "a" : 1 }` — balanced-brace counter still works (whitespace is not `{` or `}`). Confirm.

   NUMERIC THRESHOLD: if Cursor identifies a payload variation that breaks balanced-brace extraction (e.g., escaped-brace-inside-string causing wrong-depth count; a nested-array edge case where extraction returns the wrong substring; a corrupted-but-still-balanced payload that returns a syntactically-valid but semantically-wrong dict), verdict MUST be AMEND_V3 on Task F.

D. NON-BLOCKER D FIX VERIFICATION — hazard-warning placement
   Confirm:
   (a) §5-level HAZARD WARNING block exists at the top of §5 (anchor: `> **§5-LEVEL HAZARD WARNING (v6 NEW; Cursor non-blocker D):**`).
   (b) §6-level HAZARD WARNING block exists at the top of §6 (anchor: `> **§6-LEVEL HAZARD WARNING (v6 NEW; Cursor non-blocker D):**`).
   (c) THREE per-row HAZARD WARNING blocks exist at the top of each historical §0.1 row (above v5 row, above v4 row, above v3 row); each reads the literal text "DO NOT IMPLEMENT FROM HISTORICAL CONTENT" + a §9.4 v6 IS AUTHORITATIVE pointer.

   Edge cases to flag (independent scrutiny):
   - **Visibility prominence** — are the warnings prominent enough that a careless implementer skimming for "the example POST body" can't miss them? Should they be in BOLD ALL CAPS or use a more prominent visual marker (`> ⚠️` or HTML-rendered admonition block)?
   - **Warning placement vs reference order** — if a reader follows a `(Preserved verbatim from v5 §5)` pointer back to v5, they land in v5's content WITHOUT v6's hazard warning. Should the §5 warning explicitly enumerate WHICH historical-block pointers ALSO point to defective code (e.g., v3 §5 Phase 1 entry-guard literally contains the unguarded json.loads + brittle regex)?
   - **Schema-ref doc parallel** — `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 (lines 304-318) already mirrors the v6 hazard block with explicit cross-reference to LD-596. Is this redundancy adequate, or could a third hazard block in the implementation handoff §6 prod_blockers gotchas (already at v2.3) further harden the chain?

   NUMERIC THRESHOLD: descriptive evaluation. If Cursor identifies a load-bearing historical-block reference that LACKS a hazard warning AND points an implementer at defective code (e.g., a v3 §9.4 example body referenced from somewhere in v6's structure without the warning above it), verdict MUST be AMEND_V3 on Task D.

E. NON-BLOCKER E FIX VERIFICATION — schema_version + RESOLUTION_APPEND_MAX_CHARS cap
   Confirm:
   (a) §9.4 acquisition POST `structured_payload` dict literal includes `"schema_version": PAYLOAD_SCHEMA_VERSION` as the FIRST key, where `PAYLOAD_SCHEMA_VERSION = "v1"`.
   (b) §9.4 release PATCH defines `RESOLUTION_APPEND_MAX_CHARS = 256` and applies it via `if len(resolution_suffix) > RESOLUTION_APPEND_MAX_CHARS: resolution_suffix = resolution_suffix[: RESOLUTION_APPEND_MAX_CHARS - len("[truncated]")] + "[truncated]"`.
   (c) §9.4 stale-mutex cleanup parses `schema_version_recorded = payload.get("schema_version")` (handles legacy None payloads from pre-v6 rows that may still have the v5-format STRUCTURED_DETAILS_JSON without schema_version).

   Edge cases to flag (independent scrutiny):
   - **Future schema_version "v2"** — what is the policy if a future v7 spec needs to introduce schema_version "v2" with breaking payload structure? Is there a stated versioning policy in v6 (forward-compatible parser, branch-on-version, fail-on-unknown-version)? The §9.4 cleanup currently reads `schema_version_recorded` as informational only — the PID/host/started_at extraction is shape-stable across versions. Confirm: is this implicit forward-compat acceptable, or does v6 need an explicit versioning policy?
   - **Legacy v5 payloads** — pre-v6 rows in production may have STRUCTURED_DETAILS_JSON without `schema_version` field. The §9.4 stale-mutex cleanup uses `payload.get("schema_version")` returning None for legacy. PID extraction still works because `pid`/`host`/`started_at` keys are the same. Confirm legacy-tolerance.
   - **Cap truncation correctness** — `resolution_suffix[: 256 - len("[truncated]")] + "[truncated]"` truncates to 245 chars + 11-char marker = 256 chars total. Edge case: what if `resolution_suffix` is e.g., 257 chars (exceeds by 1)? The truncation triggers, slicing to 245 chars + `[truncated]` = 256 chars. Confirm boundary correctness.
   - **Cap excludes vs includes the leading ` | RESOLVED: ` prefix** — `resolution_suffix` is constructed as `f" | RESOLVED: {resolution_text} (see Phase 6 final-audit report at {phase_6_report_path})"`. The cap applies to the WHOLE suffix including the prefix. Is 256 chars enough for the prefix + meaningful resolution text + report path? (Phase 6 report path could be ~80 chars; ` | RESOLVED: ` is ~14 chars; leaves ~162 chars for resolution text.) Acceptable for the typical case; could truncate aggressively for verbose resolution text. Surface as observation.
   - **Multiple release-then-reopen-then-release cycles** — if the mutex row is released, then reopened (PATCH `is_resolved=false`), then released again, each cycle appends ANOTHER capped suffix. Over time the description could accumulate many `[truncated]` suffixes. Is this acceptable, or should there be a max-append-cycles cap? (Likely acceptable: mutex rows are typically one-shot per migration cycle.)

   NUMERIC THRESHOLD: descriptive evaluation. If Cursor identifies that the future-version policy is missing AND the absence creates a concrete risk (e.g., future v7 with breaking payload would crash v6 cleanup), verdict MUST be AMEND_V3 on Task E.

VERDICT FORMAT (mandatory, pick exactly ONE):
- AUTHORIZE_IMPLEMENTATION — v6 is sound; Phases 0+1+2+4+6 may proceed; Phase 5 stays self-gated per spec §3.1 PHASE_5_ENABLED feature flag; v6's 5 fixes are verified.
- AUTHORIZE_PHASE_0_ONLY — v6 is sound BUT live Directus state cannot be verified by Cursor from its environment; mirror prior v3 verdict scope (Phase 0 dry-run only, with risk acceptance for Phases 1+2+4+5+6 review post-Phase 0 artifacts).
- AMEND_V3 — v6 has a defect in one of its 5 surgical fixes; specify the defect AND the required v7 fix in concrete numeric terms (which §9.4 line, which §6 Gate 11.2 carve-out, which hazard-warning block, which schema_version policy, which cap-truncation boundary).
- PAUSE_FOR_REDEBATE — v6 has a fundamental issue requiring dual-Opus or expanded review.

Required output:
1. Preflight evidence (sha256 + first 20 lines verbatim + 4 anchored companion-file quotes + 4 v6-anchor captures including 5 hazard-warning blocks).
2. Analysis table (per task A, B, F, D, E) with severity, evidence (anchored citation), mitigation, blocker Y/N.
3. Verdict (one of the four above).
4. Limitations + cross-skill drift if any.
```

---

## Step 3 — After Cursor responds

Save Cursor's verbatim response to `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md`.

Verdict-driven next steps:

- **`AUTHORIZE_IMPLEMENTATION`** → dispatch implementation via terminal CLI per `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` (post-v2.3 amendment landed). Phase 5 stays self-gated per spec §3.1 PHASE_5_ENABLED feature flag; Phases 0+1+2+4+6 may proceed.
- **`AUTHORIZE_PHASE_0_ONLY`** → dispatch Phase 0 dry-run only with risk acceptance; Phases 1+2+4+6 follow after Phase 0 artifact review (mirrors prior v3 verdict scope).
- **`AMEND_V3`** → author `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` addressing the blocker(s); preserve v6 as historical baseline; re-run THIS handoff against v7 (rename + bump version refs + re-anchor).
- **`PAUSE_FOR_REDEBATE`** → halt; bring findings back to Claude Code; spawn fresh dual-Opus debate; do NOT proceed to implementation.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST (applies to handoff author logging this handoff to `prod_activity_log`; applies to Cursor reviewer if they touch Directus during analysis — they should not).
- **Multipass:** re-Read v6 spec after this handoff is authored (handoff author discipline; Cursor reviewer also re-reads if a HALT gate fires).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19 + DS-26:** always active; fire on any trigger condition. Autonomous mode does not bypass HALT gates.
- **DS-13 Layer 6:** input variation (read v5 review handoff as template + v6 spec) → output variation (this handoff differs structurally to focus only on v6's surgical 5-element fix-set, not the full v5 task surface).
- **DS-27 (absolute paths, dual-canonical):** all filesystem-touching commands MUST use absolute paths anchored to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (canonical root #1) OR `/Users/kimberlysmith/Projects/` (canonical root #2). Do NOT operate inside `.claude/worktrees/` subdirectories. All paths in this handoff are anchored to canonical root #1 (Dropbox-rooted).
- **DS-28 dependency-order:** preflight steps 1-4 verified before Step 1; Step 1 before Step 2; Step 2 before Step 3.
- **JSON-column gotcha:** the activity-log POST below uses `details` as a dict (live `prod_activity_log.details` IS a JSON column — distinct from `prod_blockers` which has NO `details` field; this is the cross-collection schema divergence v6 corrects via runtime validator).
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in this handoff is listed with absolute path + canonical-root tag.
- **Anchored citation:** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation (mandatory):** "If any required section cannot be evidenced, full mode is mandatory." (Verbatim in Step 2 prompt.)
- **Numeric AMEND_V3 thresholds (mandatory):** Tasks A, B, F have explicit numeric triggers; Tasks D, E are descriptive evaluations escalating per the standard rule.

---

## Final report — required structure

Path: `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_REPORT_20260508_v6.md`

Required sections:

1. HALT gate scan results — 5 gates (sha256 match, §9.4 v6-callout anchor, §6 Gate 11.2 v6 REPLACEMENT anchor, §7 risk #14+#15 anchors, §5+§6+§0.1 hazard-warning anchors).
2. Cursor verdict verbatim.
3. Per-task summary — A, B, F, D, E, each with verdict + anchored evidence + numeric-threshold result where applicable.
4. Confidence tags per Rule 24.
5. Self-classification — REVIEW (v6-scope tight; Cursor's classification of its own analysis).
6. Limitations — what wasn't covered (v3-v5 design surface intentionally excluded; live Directus state if unreachable).
7. Cross-skill drift — does v6's runtime-validator pattern require parallel update to weekly_preflight_audit.py or zero-error-qa SKILL.md?
8. Next-step recommendation.

---

## Cross-references

- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority.
- `LD-593` — v4 §9.4 severity case-fold authority.
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority.
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — **v6 Cursor AMEND_V2 fix-set authority** (filed 2026-05-08 same session as v6 spec).
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v5.md` — prior review handoff (structural template for THIS handoff; v5 review returned AMEND_V2).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline (v6's direct predecessor).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline.
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference + v6 hazard-warning mirror at lines 304-318.
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff (§6 prod_blockers schema gotchas at v2.3 cites v6 helpers + LD-596 — confirmed landed by parallel agent earlier this session).
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate (this handoff conforms).

---

## §12 — Change log

- **v6** — 2026-05-08 — initial draft for v6 spec cross-review. Surgically narrowed scope: v3-v5 design out-of-scope (already authorized); v4 case-fold + v5 field-name-fix out-of-scope (already locked under LD-593 + LD-595); review focuses on v6's 5 surgical fixes (Blockers A + B + F + non-blockers D + E). Five analysis tasks (A, B, F, D, E) with numeric AMEND_V3 thresholds on tasks A, B, F. AMEND lineage continues from v5's AMEND_V2 → v6's AMEND_V3 if v6 has a defect. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`.
