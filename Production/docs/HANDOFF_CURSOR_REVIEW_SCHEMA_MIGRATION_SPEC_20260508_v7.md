# Handoff v7 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v7

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` (59,307 bytes; 498 lines; sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`).

**Supersedes:** `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` (preserved as historical baseline; do NOT edit in place). v6 handoff covered v6 spec; that review returned `AMEND_V3` earlier today (1 HIGH/Y blocker — Task F balanced-brace state-tracking). v7 is a SURGICAL 1-element fix-set over v6 addressing exactly that finding. Tasks A + B + D + E remain authorized at LOW per Cursor's AMEND_V3 review of v6; v3-v6 design surface remains authorized; this handoff narrows Cursor's scope to v7's ONE fix.

**v6 → v7 driver (Cursor AMEND_V3 verdict — 1 HIGH/Y blocker):**

- **Blocker F (HIGH, Y):** v6 §9.4 `extract_structured_payload` used a raw brace counter that ignored JSON string state and escape characters. Example payload variation that breaks v6: `{"notes":"contains } brace","pid":123,...}` — the `}` inside the JSON string value is treated as a structural close, causing a wrong slice / parse failure / incorrect extraction path. Other variations along the same axis: nested-object payload where a `}` appears inside a string before the structural close (`{"k":"a } b","pid":1,"nested":{"x":"y"}}`); escaped-quote payload where the in-string `}` follows an escaped quote (`{"notes":"a \"quoted\" } brace","pid":1}`). v7 §9.4 REPLACES the brace counter with a JSON-string-aware parser state machine tracking `in_string` (toggled when an UNESCAPED `"` is encountered; not toggled if previous char's `escape` was true) and `escape` (set when `\\` is encountered inside a string; cleared on the next char). Only `{`/`}` outside strings count toward `depth`. v6 graceful `None` fallback + `STALE_MUTEX_PARSE_FAILURE` activity-log diagnostic preserved verbatim from v6. The acquisition POST + release PATCH bodies stay v6 (already correct). The runtime validator `validate_prod_blockers_payload` (§6 Gate 11.2) stays v6 (already correct).

Tasks A (guarded parse), B (runtime validator), D (hazard warnings), E (`schema_version` + ≤256-char cap) all PASS at LOW per Cursor's AMEND_V3 review of v6 — v7 preserves them verbatim. v3-v5 design surface, v4 case-fold, v5 field-name fix, and v6 parser/validator/cap/schema_version hardening are all authorized via prior verdicts and remain in effect.

**Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical):**

- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — Dropbox-rooted (canonical root #1; **spec under review**); sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`; size 59,307 bytes; 498 lines.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — Dropbox-rooted (canonical root #1; v6 historical baseline — v7's direct predecessor); sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — Dropbox-rooted (canonical root #1; v5 historical baseline); sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — Dropbox-rooted (canonical root #1; v4 historical baseline); sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — Dropbox-rooted (canonical root #1; v3 historical baseline — design surface authorized via prior `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE`); sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — Dropbox-rooted (canonical root #1; **prior review handoff** — structural template for THIS handoff; v6 review returned AMEND_V3).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Dropbox-rooted (canonical root #1; §5 = ground truth for v7 fix verification; 8-field enumeration + STRUCTURED_DETAILS_JSON pattern + lowercase severity enum). NOTE: schema-ref doc §5 currently cites LD-596 (v6); v7-pointer update is being authored by parallel agent — surface inline if not yet present, do NOT HALT.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — Dropbox-rooted (canonical root #1; implementation handoff currently at v2.3 citing v6; v2.4 amendment to point at v7 + LD-598 is being authored by parallel agent — surface inline if not yet present, do NOT HALT).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1; this handoff conforms to v2 template — anchored citations, concise→full escalation, numeric AMEND_V4 thresholds, dual-canonical absolute paths, companion path discipline).

---

## §0.1 — Why this v7 review exists

v6 spec received `AMEND_V3` from Cursor earlier today — 1 HIGH/Y blocker (Task F: v6 raw brace counter ignored JSON string state and escape characters). v7 was authored as Kim's authorized response: a SURGICAL 1-element fix-set over v6 replacing the brace counter with a JSON-string-aware state machine. v7 is NOT a re-review of design surface — that was authorized via prior verdicts and remains in effect. This v7 review tightens scope to verification of the ONE fix only.

v7 needs a TIGHT cross-review specifically on:

1. **§9.4 `extract_structured_payload`** — Blocker F: replaces v6's brace counter with JSON-string-aware state machine tracking `in_string` + `escape`. Only `{`/`}` outside strings count toward depth. Graceful `None` + `STALE_MUTEX_PARSE_FAILURE` diagnostic preserved verbatim from v6.

The v3-v6 design surface (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, mutex pattern, Task H lock_decision.py, severity case-fold from v4, field-name fix from v5, parser/validator/cap/schema_version hardening from v6, hazard warnings, runtime validator, ≤256-char cap) is OUT OF SCOPE for this v7 review — it remains authorized.

---

## §0.2 — What you DON'T need to do

- Do NOT re-review v3-v6 design surface (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, mutex pattern, Task H, severity case-fold, field-name fix, runtime validator, hazard warnings, schema_version, ≤256-char cap). Already authorized via prior verdicts.
- Do NOT re-review v6's runtime validator `validate_prod_blockers_payload` (§6 Gate 11.2) — preserved verbatim from v6 and stays correct (it operates on dict keys, NOT parser correctness).
- Do NOT re-review the acquisition POST + release PATCH + stale-mutex caller pattern — preserved verbatim from v6 (only the called extractor is replaced; the caller wiring is unchanged).
- Do NOT re-review hazard warnings, schema_version, or RESOLUTION_APPEND_MAX_CHARS — all preserved verbatim from v6.
- Do NOT have Cursor edit v7. Verdict-only.
- Do NOT have Cursor implement the migration. Implementation handoff is at `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md`; this handoff is review-only.
- Do NOT have Cursor sample CRITICAL rows from `prod_locked_decisions` — out-of-scope for v7 surgical fix-set.
- Do NOT have Cursor probe live Directus state — out-of-scope; v7 changes only one Python function in §9.4.

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|-----------------|----------------|-------------|
| 1 | Has spec v7 sha256 been confirmed match `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`? | `shasum -a 256` of v7 spec absolute path | Hash matches verbatim | HALT — author drift; surface to Kim |
| 2 | Has v7 §9.4 v7-callout block + state-machine function definition been read into context? | Quote anchor: locate `### §9.4 — Concurrency, lockfile, and remote mutex (v7 JSON-STRING-AWARE STATE MACHINE over v6 — Cursor AMEND_V3 fix-set: Blocker F)` header in v7 spec; capture the v7-authoritative paragraph (`> **JSON-string-aware extraction (v7 NEW correction).**`) + the `extract_structured_payload` Python function body verbatim + the state-machine invariants block (`**State-machine invariants (v7 explanatory):**`) + the stale-mutex cleanup caller block | Reviewer emits the v7 §9.4 callout text + `extract_structured_payload` function body + invariants block + caller block | HALT and report which anchor failed |
| 3 | Has v7 §0.1 v7-A row been read into context? | Quote anchor: locate `## §0.1 — v7 Changelog (single-row amendment over v6)` header; capture the v7-A row including the example variation `{"notes":"contains } brace","pid":123,...}` and the resolution paragraph | Reviewer emits the v7-A row verbatim including the three example variations and the resolution paragraph | HALT and report which anchor failed |
| 4 | Has v7 §7 risk #16 (NEW) been read into context? | Quote anchor: locate `**(v7 NEW — #16)**` row in §7; ALSO confirm risk #15 (preserved from v6) was NOT structurally changed (likelihood narrowed only) | Reviewer emits risk #16 verbatim including likelihood/severity/mitigation chain; confirms #15 unchanged | HALT and report which anchor failed |
| 5 | Has v7 §11 reference index + §12 changelog v7 entries been read into context? | Quote anchors: locate `LD-NEW SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` reference in §11 (twice — once near top, once at line ~476); locate `**v7** — 2026-05-08 — Cursor AMEND_V3 on v6` row in §12 changelog | Reviewer emits both §11 entries + §12 v7 row verbatim | HALT and report which anchor failed |

---

## Step 0 — Preflight (do FIRST, before any analysis) — anchored discipline

Mandatory actions, emit inline:

1. **`ls -la` v7 spec absolute path:**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md"
   ```
   Expected: file exists, size 59,307 bytes, mtime 2026-05-08.

2. **`shasum -a 256` v7 spec:**
   ```sh
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md"
   ```
   Expected output: `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3  <path>`. **HALT if hash differs — author drift detected; surface to Kim before proceeding.**

3. **Quote first 20 lines of v7 spec verbatim** (stale-cache detector). The first non-blank line MUST be `# Schema Vocab Migration — Tech Spec v7`. Capture lines 1-20 with line numbers.

4. **Companion-file integrity (anchored — header/snippet ONLY):**
   - (a) `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — anchor `# Schema Vocab Migration — Tech Spec v6` (first line); confirm v6 spec exists as predecessor; capture v6 §9.4 brace-counter snippet to confirm v7 is replacing the right thing.
   - (b) `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — anchor `# Handoff v6 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v6` (first line); confirm prior AMEND_V3 verdict context exists.
   - (c) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor `## 5. \`prod_blockers\``; capture the 8-field list section. (NOTE: v7-pointer update may not yet be present in the schema-ref doc — surface "may not yet be present" if absent; do NOT HALT, since the parallel agent may be mid-flight on that update.)
   - (d) `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — anchor `### prod_blockers schema gotchas` heading in §6. (NOTE: if the v2.4 amendment citing v7 + LD-598 is missing, the implementation handoff has not yet landed v2.4 — surface "v2.4 amendment may not yet be present" inline; do NOT HALT, since the parallel agent may be mid-flight.)

If preflight 1-3 fails, HALT and report. If 4 fails for any companion file, document inline; if all 4 fail, HALT.

---

## Step 1 — Open the project in Cursor

Project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Open `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md`.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md (v7 — supersedes v6 which superseded v5 which superseded v4 which superseded v3). v7 is a SURGICAL 1-element fix-set over v6 addressing your own AMEND_V3 verdict on v6 (1 HIGH/Y blocker — Task F balanced-brace JSON-string-state tracking). v3-v6 design surface is preserved + already authorized; do NOT re-review it. Re-review specifically:
  - §9.4 `extract_structured_payload(description)` — JSON-string-aware state machine REPLACES v6 raw brace counter (Blocker F).

Background context (informational only):
- v6 returned AMEND_V3 with: Blocker F (raw brace counter in extract_structured_payload ignored JSON string state and escape characters; payloads with `}` or `{` inside JSON string values mis-slice). Tasks A (guarded parse), B (runtime validator), D (hazard warnings), E (schema_version + ≤256-char cap) all PASSED at LOW.
- v7 §9.4 REPLACES v6's brace counter with a JSON-string-aware parser state machine. Two booleans: `in_string` (toggled when an UNESCAPED `"` is encountered; not toggled if the previous char's `escape` was true) and `escape` (set when `\\` is encountered inside a string; cleared on the next char). Only `{`/`}` outside strings count toward `depth`. Existing graceful `None` fallback + `STALE_MUTEX_PARSE_FAILURE` activity-log diagnostic preserved verbatim from v6.
- v7 §0.1 v7-A row cites three example variations that break v6's brace counter: `{"notes":"contains } brace","pid":123,...}`, `{"k":"a } b","pid":1,"nested":{"x":"y"}}`, `{"notes":"a \"quoted\" } brace","pid":1}`.
- v7 §7 ADDS risk #16 documenting brace-counter vs. state-machine implementer drift (LOW likelihood with v7 explicit pseudocode + §0.1 v7-A row + LD-598 + Gate 11.2 complement; HIGH severity due to potentially-corrupted PID → wrong host check).
- v6 acquisition POST + release PATCH + stale-mutex caller pattern + runtime validator + hazard warnings + schema_version + ≤256-char cap all preserved verbatim. v7 changes EXACTLY ONE function body (the parser depth counter now tracks JSON string state).

Authority: LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1 (filed 2026-05-08 same session as v7 spec).

Apply your full independent scrutiny on the v7-scope change only. The v3-v6 design is locked.

PREFLIGHT (do first, emit inline) — anchored discipline:
1. Confirm spec v7 file exists; capture size + mtime + shasum.
   Expected sha256: dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3
   HALT if mismatch — author drift.
2. Quote the first 20 non-blank lines of spec v7 verbatim with capture-line-range.
   First line MUST be: "# Schema Vocab Migration — Tech Spec v7"
3. Companion-file integrity (anchored header/snippet only):
   (a) `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — anchor `# Schema Vocab Migration — Tech Spec v6`; confirm predecessor exists; capture v6 §9.4 brace-counter snippet (the function v7 is replacing).
   (b) `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — anchor `# Handoff v6 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v6`; confirm prior AMEND_V3 verdict context exists.
   (c) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor "## 5. `prod_blockers`"; quote the 8-field enumeration. (If v7-pointer update is missing in the schema-ref doc, surface "v7 pointer may not yet be present" inline; do NOT HALT — parallel agent may be mid-flight.)
   (d) `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — anchor `### prod_blockers schema gotchas`. (If v2.4 amendment citing v7 + LD-598 is missing, surface "v2.4 amendment may not yet be present" inline; do NOT HALT.)
4. v7-specific anchor capture:
   (i) Locate `### §9.4 — Concurrency, lockfile, and remote mutex (v7 JSON-STRING-AWARE STATE MACHINE over v6 — Cursor AMEND_V3 fix-set: Blocker F)` header; quote the v7-authoritative paragraph (`> **JSON-string-aware extraction (v7 NEW correction).**`) + the `extract_structured_payload` Python function body verbatim + the `**State-machine invariants (v7 explanatory):**` block + the stale-mutex cleanup caller block.
   (ii) Locate v7 §0.1 v7-A row in `## §0.1 — v7 Changelog (single-row amendment over v6)` table; quote verbatim including the three example variations.
   (iii) Locate v7 §7 risk #16 (NEW) row (`**(v7 NEW — #16)**`); quote verbatim. Confirm risk #15 (preserved from v6) was likelihood-narrowed only, not structurally changed.
   (iv) Locate v7 §11 LD-598 reference + §12 v7 changelog row; quote both verbatim.
If preflight 1-3 fails, HALT and report.

CONCISE→FULL ESCALATION RULE (mandatory verbatim per HANDOFF_TEMPLATE_v2):
> If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced": could not read v7 spec; could not reproduce a v7-scope anchor (header/snippet match in actual file content); the v7 §9.4 state-machine surface is missing or ambiguous; reviewer's evidence is "I think" or "probably" rather than a quoted citation; reviewer skipped a question to save tokens. Document WHICH area was under-evidenced in full-mode output.

ANALYSIS REQUIREMENTS (citation table format):
| # | Concern | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (anchored citation: section header + snippet match, NOT line numbers alone) | Suggested mitigation | Blocker (Y/N) |

REQUIRED ANALYSIS TASK (v7-scope only — 1 fix):

F. BLOCKER F FIX VERIFICATION — JSON-string-aware state machine in `extract_structured_payload`
   Confirm:
   (a) The state machine: marker find → first `{` find → walk character-by-character with `in_string` + `escape` state → only count `{`/`}` outside strings → return slice when depth returns to 0; wrap `json.loads` in `try/except json.JSONDecodeError` returning None.
   (b) `in_string` toggles ONLY when `"` is seen AND previous char did not set `escape`. The function's actual order — `if escape: escape = False; continue` BEFORE the `if ch == '"'` branch — implements this correctly because an escaped `"` is consumed by the `escape` guard before the quote-toggling branch runs.
   (c) `escape` is set on `\\` ONLY when `in_string` is true (defensive harmless-when-false branch documented in §9.4 invariants).
   (d) `escape` is consumed on the very next character regardless of value, so `\n` / `\"` / `\\` all behave correctly.
   (e) On `None` return (marker absent / opening brace absent / unbalanced braces / JSONDecodeError), the §9.4 stale-mutex cleanup caller posts `STALE_MUTEX_PARSE_FAILURE` activity-log row including blocker_row_id, blocker_title, description_preview (truncated 1024 chars), spec_reference (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md §9.4`), and remediation pointer. Preserved verbatim from v6.

   Edge cases to probe (independent scrutiny — these are the dominant failure surfaces for a state-machine extractor):

   - **Cursor's v6-breaking example payload:** `{"notes":"contains } brace","pid":123,...}` — verify v7's state machine extracts the WHOLE payload correctly (not slicing at the in-string `}`). Walk through: at the in-string `}`, `in_string=True`, so the `not in_string` guard skips depth decrement; depth stays at 1; closing `}` at end correctly drops depth to 0. PASS expected.

   - **Escaped-quote inside string:** `{"notes":"says \"hi\"","pid":123}` — verify state machine handles correctly. Walk through: encounter `\\`; `in_string=True` so `escape=True`; next char `"` is consumed by `if escape: escape=False; continue` BEFORE the quote-toggle branch runs; `in_string` STAYS TRUE; the `hi` substring is correctly treated as in-string; closing `\"` repeats the pattern; `","pid"` closes the string normally; outer `}` drops depth to 0. PASS expected. **VERIFY THIS ORDER:** the `escape` guard MUST run before the `"` branch in the function body — confirm by inspecting the actual loop order in §9.4.

   - **Nested objects:** `{"meta":{"pid":123,"started_at":"..."}}` — verify depth tracking still works. Walk through: outer `{` → depth=1; key `"meta"`; inner `{` outside string → depth=2; inner `}` outside string → depth=1; outer `}` → depth=0. PASS expected.

   - **Unicode escape inside string:** `{"notes":"} in unicode","pid":123}` — `}` is an escaped representation of `}`. Walk through: encounter `\\`; `escape=True`; next char `u` consumed by escape guard; subsequent `007d` are plain chars inside string; the LITERAL `}` character does NOT appear in the input bytes (only the escape sequence). State machine never sees a structural-looking `}` that's actually in-string. PASS expected. **EDGE CASE:** what if the JSON literal contains an actual unescaped Unicode `}` (U+007D rendered as a real `}` byte) inside a string? That's the same as the first example — handled. What if the JSON contains `\}` (backslash + brace)? `\\` in JSON strings outside the recognized escape set — JSON spec says invalid; `json.loads` will reject; caught by try/except → graceful None.

   - **Truncated payload (missing closing brace):** `{"a":1` with no `}` — depth never returns to 0; loop exits with `end is None`; function returns None gracefully. PASS expected.

   - **Empty payload after marker:** `STRUCTURED_DETAILS_JSON: ` (no `{` after marker) — `description.find("{", idx)` returns -1; function returns None. PASS expected.

   - **Marker absent:** description does not contain `STRUCTURED_DETAILS_JSON:` — `description.find(marker)` returns -1; function returns None. PASS expected.

   - **Adversarial: backslash followed by `"` outside a string** — the §9.4 invariants document this as a defensive harmless-when-false branch (`escape` is only meaningful inside strings). Walk through: outside string, `\\` → `escape=True` (per the function body's `if ch == "\\": if in_string: escape=True; continue` — wait, the function body says `if in_string: escape = True` so `escape` is NOT set outside strings). Re-read the function: `if ch == "\\": if in_string: escape = True; continue` — so `escape` is ONLY set inside strings. Outside strings, `\\` is silently consumed by the `continue`. The §9.4 invariants block claims `escape` outside string is "harmless"; verify the function body matches the invariant prose.

   - **Stress: extremely deeply nested JSON or very large payload (~10KB)** — O(n) loop, acceptable.

   NUMERIC THRESHOLD: if Cursor identifies ≥1 plausible payload variation that v7's state machine STILL mis-handles (despite the v7 fix) — including but not limited to: (i) order-of-operations bug where the `escape` guard does NOT run before the `"` branch, (ii) `escape` set incorrectly outside strings causing a structural `{`/`}` to be skipped, (iii) Unicode-escape edge case where `}` causes incorrect depth tracking, (iv) any payload variation Cursor can construct where v7's state machine returns the wrong dict OR returns None where v6's brace counter would have returned the correct dict — verdict MUST be AMEND_V4. Show the variation explicitly with a character-by-character walkthrough.

VERDICT FORMAT (mandatory, pick exactly ONE):
- AUTHORIZE_IMPLEMENTATION — v7 is sound; Phases 0+1+2+4+6 may proceed; Phase 5 stays self-gated per spec §3.1 PHASE_5_ENABLED feature flag; v7's 1 fix is verified.
- AUTHORIZE_PHASE_0_ONLY — v7 is sound BUT live Directus state cannot be verified by Cursor from its environment; mirror prior v3 verdict scope (Phase 0 dry-run only, with risk acceptance for Phases 1+2+4+5+6 review post-Phase 0 artifacts).
- AMEND_V4 — v7 has a defect in its 1 surgical fix; specify the defect AND the required v8 fix in concrete numeric terms (which §9.4 line, which character-class transition the state machine mis-handles, which payload variation breaks it).
- PAUSE_FOR_REDEBATE — v7 has a fundamental issue requiring dual-Opus or expanded review.

Required output:
1. Preflight evidence (sha256 + first 20 lines verbatim + 4 anchored companion-file quotes + 4 v7-anchor captures).
2. Analysis table (per task F) with severity, evidence (anchored citation), mitigation, blocker Y/N.
3. Verdict (one of the four above).
4. Limitations + cross-skill drift if any.
```

---

## Step 3 — After Cursor responds

Save Cursor's verbatim response to `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v7.md`.

Verdict-driven next steps:

- **`AUTHORIZE_IMPLEMENTATION`** → dispatch implementation via terminal CLI per `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` (post-v2.4 amendment landed by parallel agent). Phase 5 stays self-gated per spec §3.1 PHASE_5_ENABLED feature flag; Phases 0+1+2+4+6 may proceed.
- **`AUTHORIZE_PHASE_0_ONLY`** → dispatch Phase 0 dry-run only with risk acceptance; Phases 1+2+4+6 follow after Phase 0 artifact review (mirrors prior v3 verdict scope).
- **`AMEND_V4`** → author `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` addressing the blocker; preserve v7 as historical baseline; re-run THIS handoff against v8 (rename + bump version refs + re-anchor).
- **`PAUSE_FOR_REDEBATE`** → halt; bring findings back to Claude Code; spawn fresh dual-Opus debate; do NOT proceed to implementation.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST (applies to handoff author logging this handoff to `prod_activity_log`; applies to Cursor reviewer if they touch Directus during analysis — they should not).
- **Multipass:** re-Read v7 spec after this handoff is authored (handoff author discipline; Cursor reviewer also re-reads if a HALT gate fires).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19 + DS-26:** always active; fire on any trigger condition. Autonomous mode does not bypass HALT gates.
- **DS-13 Layer 6:** input variation (read v6 review handoff as template + v7 spec) → output variation (this handoff differs structurally to focus only on v7's surgical 1-element fix-set, not the full v6 task surface).
- **DS-27 (absolute paths, dual-canonical):** all filesystem-touching commands MUST use absolute paths anchored to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (canonical root #1) OR `/Users/kimberlysmith/Projects/` (canonical root #2). Do NOT operate inside `.claude/worktrees/` subdirectories. All paths in this handoff are anchored to canonical root #1 (Dropbox-rooted).
- **DS-28 dependency-order:** preflight steps 1-4 verified before Step 1; Step 1 before Step 2; Step 2 before Step 3.
- **JSON-column gotcha:** the activity-log POST below uses `details` as a dict (live `prod_activity_log.details` IS a JSON column — distinct from `prod_blockers` which has NO `details` field; this is the cross-collection schema divergence v6's runtime validator catches and v7 preserves verbatim).
- **LD-597 anti-confusion guard:** do NOT include `task_description` in any `prod_activity_log` POST — that field does not exist on `prod_activity_log`; `details` (JSON dict) is the canonical narrative carrier.
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in this handoff is listed with absolute path + canonical-root tag.
- **Anchored citation:** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation (mandatory):** "If any required section cannot be evidenced, full mode is mandatory." (Verbatim in Step 2 prompt.)
- **Numeric AMEND_V4 thresholds (mandatory):** Task F has explicit numeric trigger (≥1 plausible payload variation that v7 mis-handles → AMEND_V4).

---

## Final report — required structure

Path: `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_REPORT_20260508_v7.md`

Required sections:

1. HALT gate scan results — 5 gates (sha256 match, §9.4 v7-callout + state-machine function anchor, §0.1 v7-A row anchor, §7 risk #16 anchor, §11 LD-598 + §12 v7 changelog anchor).
2. Cursor verdict verbatim.
3. Per-task summary — Task F, with verdict + anchored evidence + numeric-threshold result (whether any v7-breaking payload variation was identified).
4. Confidence tags per Rule 24.
5. Self-classification — REVIEW (v7-scope tight; Cursor's classification of its own analysis).
6. Limitations — what wasn't covered (v3-v6 design surface intentionally excluded; live Directus state if unreachable).
7. Cross-skill drift — does v7's state-machine pattern require parallel update to weekly_preflight_audit.py or zero-error-qa SKILL.md? Has the schema-ref doc + implementation handoff v2.4 been updated to point at v7 + LD-598?
8. Next-step recommendation.

---

## Cross-references

- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority.
- `LD-593` — v4 §9.4 severity case-fold authority.
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority.
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — v6 Cursor AMEND_V2 fix-set authority (preserved through v7).
- `LD-597 TASK_DESCRIPTION_GOTCHA_DRIFT_RESOLUTION_V1` — anti-confusion guard for `prod_activity_log.task_description` non-existence (v7 inherits verbatim).
- `LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` — **v7 Cursor AMEND_V3 fix-set authority** (filed 2026-05-08 same session as v7 spec; verified registered in `prod_locked_decisions` at handoff authoring time).
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — prior review handoff (structural template for THIS handoff; v6 review returned AMEND_V3).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — v6 historical baseline (v7's direct predecessor).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline.
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth (v7-pointer update being authored by parallel agent).
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff (v2.4 amendment to point at v7 + LD-598 being authored by parallel agent).
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate (this handoff conforms).

---

## §12 — Change log

- **v7** — 2026-05-08 — initial draft for v7 spec cross-review. Surgically narrowed scope: v3-v6 design out-of-scope (already authorized); v6 Tasks A + B + D + E out-of-scope (already locked under LD-596 with Cursor AMEND_V3 PASS at LOW); review focuses on v7's 1 surgical fix (Task F: JSON-string-aware state machine in `extract_structured_payload`). One analysis task (F) with explicit numeric AMEND_V4 threshold. AMEND lineage continues from v6's AMEND_V3 → v7's AMEND_V4 if v7 has a defect. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`.
