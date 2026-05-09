# Handoff — Cursor Cross-Review of Directus Payload Validator Tech Spec v2

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md` — Dropbox-rooted (canonical root #1; **spec under review**); 47,098 bytes; 407 lines; sha256 `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b`.

**Driver:** Cursor returned **`AMEND_V2`** on v1 (Task E blocker — malformed override file behavior undefined). v2 addresses Task E with single-normative-path + diagnostic + Phase 1 test. **v2 review handoff verifies the surgical fix; do NOT re-review v1's other 6 tasks (A/B/C/D/F/G all PASSED at AUTHORIZE thresholds).**

**Authority:** LD-604 `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1` (filed 2026-05-08; status=active; severity=SOFT; task_category=governance; enforcement_type=awareness_only; scope_domain=infra) — confirmed live via `DirectusAdminClient` probe at handoff authoring time `(my probe)`. v1 baseline authority: LD-599 `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` (also confirmed live `(my probe)`).

---

## §0.1 — Why this review exists (surgical 1-task verification, NOT full re-review)

v2 is a SURGICAL 1-task fix-set addressing Task E from Cursor's `AMEND_V2` verdict on v1. v1's other 6 tasks (A / B / C / D / F / G) ALL PASSED at AUTHORIZE thresholds — they DO NOT need to be re-reviewed. v2 preserves Decisions 1-7, Phases 0/2/3/4/5, Gates 1-10, Risks 1-10 verbatim by reference to v1 (per spec §0 "Motivation for v2"). Re-reviewing those tasks would burn Cursor's review budget on already-cleared design surface.

The Task E blocker, per Cursor's v1 verbatim review (`Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`): *"FAIL → AMEND. Override file malformed JSON: CONFIRMED absence of normative §9 behavior."* v1 §9.2 documented missing-file behavior (defaults) but did NOT define behavior when the override file is present and JSON-parse / layout is invalid.

v2's Task E fix surface (per spec §0.1 v2-A row + §3 + §5 + §6 + §7 + §9.2 + §11 + §12):
- §3 NEW Decision 8: dual-Opus debate (fail-safe vs fail-loud) → synthesis = fail-safe default + opt-in fail-loud via `MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud` env var.
- §5 Phase 1 NEW: 4-fixture override-file test (valid + invalid-JSON + invalid-layout-not-dict + invalid-layout-bad-key) + 1 fail-loud env-var test.
- §6 NEW Gate 11: override-file fail-mode policy approval.
- §7 NEW risk #11: override-file silent-fallback masking operator intent.
- §9.2 FULL REWRITE: 5-case file-state table (absent / valid / JSON-parse-fail / layout-invalid / permission-denied) with single normative path each.
- §11 reference index appends v1 baseline + LD-604 + Cursor v1 review outputs.
- §12 changelog appends v2 row.

Cursor offered (verbatim from v1 review) "*I can immediately run the same strict gate on the next revision*" — this v2 review handoff is meant for that.

**Iteration lineage (note for Cursor):** v1 was Cursor's first review of this spec; verdict was AMEND_V2. The v2 spec (under review here) is Claude Opus's response to that AMEND_V2. If THIS v2 review identifies a new Task E defect, the verdict would be **AMEND_V3** — i.e., iteration 3 of the AMEND lineage for this spec. (Not to be confused with HANDOFF_TEMPLATE_v2 which is the template version.)

The structural template for THIS v2 review handoff is `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md` (the v1 review handoff that produced the AMEND_V2 outcome). v2 mirrors v1's preflight + companion-files + HALT-gates + Step 0/1/2/3 architecture but tightens the analysis surface to Task E only. v2 of the handoff template (`Production/docs/HANDOFF_TEMPLATE_v2.md`) governs structural compliance: anchored citations, concise→full escalation rule, numeric AMEND_V3 thresholds, dual-canonical absolute paths, companion-files with canonical-root tags, HALT gates section, autonomous-mode reminder.

---

## §0.2 — What you DON'T need to do

- Do NOT have Cursor re-review v1's other 6 tasks (A/B/C/D/F/G). They ALL PASSED in the v1 review at AUTHORIZE thresholds; v2 preserves the corresponding spec sections verbatim by reference. Re-reviewing them is out of scope for v2.
- Do NOT have Cursor edit the spec. Verdict-only review.
- Do NOT have Cursor implement the validator. Implementation is gated on Kim approving each of spec §6's 11 gates AFTER this Cursor review returns.
- Do NOT have Cursor probe live Directus state — Cursor's environment may not have credentials. LD-604 + LD-599 live-confirms were performed at v2 spec authoring time + at this handoff authoring time `(my probe)`.
- Do NOT re-debate whether a runtime payload validator is the right pattern (locked at v6 narrow scope; v1 generalization premise already AUTHORIZED by Cursor's v1 review at Task A).
- Do NOT touch any other spec, handoff, schema-ref doc, hook script, migration script, or LD record — this is review-only on `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md`.

---

## Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical)

- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md` — Dropbox-rooted (canonical root #1; **spec under review**); sha256 `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b`; 47,098 bytes; 407 lines.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1; **historical baseline preserved**); sha256 `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`; 60,533 bytes; 449 lines. Inherited Decisions 1-7, Phases 0/2/3/4/5, Gates 1-10, Risks 1-10 are referenced from this file by v2.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md` — Dropbox-rooted (canonical root #1; **structural template + prior review handoff**); produced Cursor's v1 AMEND_V2 verdict on Task E.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md` — Dropbox-rooted (canonical root #1; **Cursor's v1 verbatim review output**); 17,477 bytes; sha256 `e45e266e94c2eeea3cc9dc31d2c89ba8b66e66bcdc15894924f6f1ad22918291`. Source of the Task E defect statement v2 corrects.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_REPORT_20260508.md` — Dropbox-rooted (canonical root #1; **Cursor's v1 review companion summary**); 4,038 bytes; sha256 `08f78529dc54e269a9739a41f3e4a169828fb650ef27025ab510e784bde7738a`.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Dropbox-rooted (canonical root #1; **live schema authority**); contains the 11-field `prod_activity_log` enumeration — verifies v2 §9.2 activity-log row `details` keys are valid (LD-597 anti-confusion guards).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1; **template-compliance reference**); this handoff conforms to v2 — anchored citations, concise→full escalation, numeric AMEND_V3 thresholds, dual-canonical absolute paths, companion path discipline, HALT gates section.
- `/Users/kimberlysmith/.claude/skills/zero-error-qa/SKILL.md` — Global Claude config (recognized exception per HANDOFF_TEMPLATE_v2 §"Absolute-path filesystem discipline"); DS-13 / DS-19 / DS-26 / DS-27 / DS-28 / DS-29 references for hard-rules section.

**Cross-references — LDs:**
- **LD-597** (`TASK_DESCRIPTION_FIELD_ANTI_CONFUSION_GUARDS_V1`) — anti-confusion guards (v2 §9.2 activity-log row payload MUST NOT contain `task_description` per LD-597).
- **LD-599** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1`) — v1 spec authority; status=active `(my probe)`.
- **LD-604** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1`) — **spec authority for THIS review**; status=active, severity=SOFT, task_category=governance, enforcement_type=awareness_only, scope_domain=infra `(my probe)`.

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Step 2 prompt is paste-able to Cursor)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|-----------------|----------------|-------------|
| 1 | Has v2 spec sha256 been confirmed match `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b`? | `shasum -a 256` of v2 spec absolute path | Hash matches verbatim | HALT — author drift; surface to Kim |
| 2 | Has the first non-blank line of v2 spec been confirmed to read `# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v2`? | First-20-lines verbatim quote during Step 0 preflight | First non-blank line MUST match | HALT — stale-cache or wrong file; surface to Kim |
| 3 | Have ALL 7 companion-file anchors been verified? | Per-companion `ls -la <absolute-path>` returns existing file | All 7 paths resolve under canonical root #1 | HALT and report which anchor failed |
| 4 | Does v2 spec §0 Operating Mode read "DESIGN ONLY"? | Anchor: locate `## §0 — Operating Mode` heading; capture verbatim text | Substring "DESIGN ONLY" present in §0 body | HALT — spec scope misclassification; surface to Kim |
| 5 | Has LD-604 been confirmed `decision_key=DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1` AND `status=active`? | Live Directus probe via `DirectusAdminClient` (handoff author performed at authoring time `(my probe)`) | Both fields match exactly | HALT — LD authority drift; surface to Kim |

---

## Step 0 — Preflight (do FIRST, before any analysis) — anchored discipline

Mandatory actions, emit inline:

1. **`ls -la` v2 spec absolute path:**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md"
   ```
   Expected: file exists, size 47,098 bytes, mtime 2026-05-08.

2. **`shasum -a 256` v2 spec:**
   ```sh
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md"
   ```
   Expected output: `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b  <path>`. **HALT if hash differs — author drift detected; surface to Kim before proceeding.**

3. **Quote first 20 lines of v2 spec verbatim** (stale-cache detector). The first non-blank line MUST be `# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v2`. Capture lines 1-20 with line numbers.

4. **Companion-file integrity (anchored — header/snippet ONLY, NOT line-number):**
   - (a) v1 spec — anchor: locate `# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1` (first line); confirm v1 baseline preserved + sha256 match `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`.
   - (b) v1 review handoff — anchor: locate `# Handoff — Cursor Cross-Review of Directus Payload Validator Tech Spec v1` (first line); confirm structural template lineage.
   - (c) Cursor v1 verbatim review — anchor: locate "Task E" heading or "FAIL — AMEND trigger" snippet; capture line range + the v1 Task E defect statement verbatim.
   - (d) Cursor v1 review report — anchor: locate "AMEND_V2" + "§9.2" snippet; capture line range + the one-line verdict.
   - (e) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor: locate the heading containing `prod_activity_log`; capture the 11-field enumeration list (verifies v2 §9.2 activity-log row `details` keys do NOT include `task_description` per LD-597).
   - (f) `Production/docs/HANDOFF_TEMPLATE_v2.md` — anchor: `# Handoff Template v2` (first line); confirm template version compliance.
   - (g) `~/.claude/skills/zero-error-qa/SKILL.md` — anchor: locate `DS-29` heading or `verification-source discipline` snippet; capture the source-tagging rule for Cursor's per-task evidence claims.

5. **v2-spec-specific anchor capture (REQUIRED for review):**
   - (i) Locate `## §0 — Operating Mode (preserved verbatim from v1)` heading; capture the verbatim DESIGN-ONLY paragraph.
   - (ii) Locate `## §0.1 — Authoring changelog (v2-A row above v1 row)` heading; capture the v2-A row verbatim (the surgical fix scope summary).
   - (iii) Locate `### Decision 8 — Malformed override file: fail-safe ... vs fail-loud ... — NEW v2` heading; capture the 3 paragraphs (Advocate / Counter / Synthesis) verbatim.
   - (iv) Locate `## §4 — Per-decision action table (v2 extends v1's 7-row table to 8 rows)` heading; capture row 8 verbatim.
   - (v) Locate `**Phase 1 — Author the validator function**` paragraph; capture the v2 Phase 1 deliverable amendment (4-fixture test + 1 fail-loud env-var test) verbatim.
   - (vi) Locate `## §6 — Pre-implementation gates Kim must approve` heading; capture row 11 (NEW Gate 11) verbatim.
   - (vii) Locate `## §7 — Risk assessment` heading; capture row 11 (NEW risk #11) verbatim.
   - (viii) Locate `### §9.2 — Per-collection override file (FULL REWRITE for v2 per Cursor AMEND_V2 Task E blocker)` heading; capture the full 5-case file-state table (cases A / B / C / D / E) verbatim + the diagnostic format block + the env-var opt-in block + the reference implementation sketch.
   - (ix) Locate `## §11 — Reference index (v2 preserves v1 entries + appends new entries)` heading; capture the NEW v2 entries (v1 baseline sha256, Cursor review outputs, LD-599, LD-604).
   - (x) Locate `## §12 — Changelog (v2 appends one row to v1)` heading; capture the v2 row verbatim.

If preflight 1-3 fails, HALT and report. If 4 or 5 fails for any anchor, document inline; if all anchors fail, HALT.

---

## Step 1 — Open the project in Cursor

Project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Open `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md`.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md. v2 is a SURGICAL 1-task fix-set addressing Task E from your AMEND_V2 verdict on v1. v1's other 6 tasks (A / B / C / D / F / G) ALL PASSED at AUTHORIZE thresholds in your v1 review — DO NOT re-review them. v2 preserves Decisions 1-7, Phases 0/2/3/4/5, Gates 1-10, Risks 1-10 verbatim by reference to v1 (per spec §0 "Motivation for v2"). Re-reviewing those tasks is out of scope and will burn review budget on already-cleared design surface.

Background context (informational only — do NOT re-debate):
- Your v1 verdict was AMEND_V2 with one Task E blocker: "Override file malformed JSON: CONFIRMED absence of normative §9 behavior." v1 §9.2 documented missing-file behavior (defaults) but did NOT define behavior when the override file is present and JSON-parse / layout is invalid.
- v2 corrects ONLY Task E surface: §9.2 full rewrite (5-case file-state table) + §3 NEW Decision 8 (dual-Opus debate fail-safe vs fail-loud → synthesis fail-safe default + opt-in fail-loud env var) + §5 Phase 1 NEW (4-fixture override test + 1 fail-loud env-var test) + §6 NEW Gate 11 (override fail-mode policy) + §7 NEW risk #11 (silent-fallback masking operator intent) + §11/§12 (reference index + changelog updates).
- v1 baseline preserved at `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md`; sha256 `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`; size 60,533 bytes; 449 lines.
- Authority: LD-604 DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1 (filed 2026-05-08; status=active; severity=SOFT; scope_domain=infra). v1 baseline authority: LD-599 (status=active).
- Iteration lineage note: v1 was your first review (AMEND_V2 verdict). v2 (under review here) is Claude Opus's response. If THIS v2 review identifies a new Task E defect, the verdict would be AMEND_V3 — iteration 3 of the AMEND lineage for this spec. Distinct from HANDOFF_TEMPLATE_v2 (template version).

PREFLIGHT (do first, emit inline) — anchored discipline:
1. Confirm v2 spec file exists; capture size + mtime + shasum.
   Expected sha256: 047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b
   HALT if mismatch — author drift.
2. Quote the first 20 lines of v2 spec verbatim with capture-line-range.
   First non-blank line MUST be: "# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v2"
3. Companion-file integrity (anchored header/snippet only):
   (a) v1 spec — anchor first line `# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1`; confirm v1 baseline preserved + sha256 match `14ae4e22b653...`.
   (b) v1 review handoff (`Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`) — anchor first line.
   (c) Your v1 verbatim review (`Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`) — anchor "Task E" heading or "FAIL — AMEND trigger" snippet; capture the v1 Task E defect statement verbatim.
   (d) v1 review report (`Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_REPORT_20260508.md`) — anchor "AMEND_V2" + "§9.2" snippet.
   (e) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor heading containing `prod_activity_log`; capture 11-field enumeration list (verifies v2 §9.2 activity-log row `details` keys exclude `task_description` per LD-597).
4. v2-spec-specific anchor capture:
   (i) `## §0 — Operating Mode` — quote DESIGN-ONLY paragraph.
   (ii) `## §0.1 — Authoring changelog (v2-A row above v1 row)` — quote v2-A row verbatim.
   (iii) `### Decision 8 — Malformed override file ... — NEW v2` — quote 3 paragraphs (Advocate / Counter / Synthesis) verbatim.
   (iv) `## §4 — Per-decision action table` row 8 — quote verbatim.
   (v) `**Phase 1 — Author the validator function**` — quote v2 Phase 1 deliverable amendment (4-fixture test + 1 fail-loud env-var test) verbatim.
   (vi) `## §6` row 11 (NEW Gate 11) — quote verbatim.
   (vii) `## §7` row 11 (NEW risk #11) — quote verbatim.
   (viii) `### §9.2 ... (FULL REWRITE for v2 per Cursor AMEND_V2 Task E blocker)` — quote full 5-case file-state table (cases A / B / C / D / E) + diagnostic format block + env-var opt-in block + reference implementation sketch verbatim.
   (ix) `## §11` NEW v2 entries — quote.
   (x) `## §12` v2 row — quote verbatim.
If preflight 1-3 fails, HALT and report.

CONCISE→FULL ESCALATION RULE (mandatory verbatim per HANDOFF_TEMPLATE_v2):
> If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced": could not read the spec; could not reproduce a §3 / §4 / §5 Phase 1 / §6 / §7 / §9.2 anchor (header/snippet match in actual file content); the spec section the question targets is missing or ambiguous; the reviewer's evidence is "I think" or "probably" rather than a quoted citation; the reviewer skipped a question to save tokens. Document WHICH area was under-evidenced in full-mode output.

ANALYSIS REQUIREMENTS (citation table format):
| # | Concern | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (anchored citation: section header + snippet match, NOT line numbers alone) | Suggested mitigation | Blocker (Y/N) |

REQUIRED ANALYSIS — single task (TIGHT scope: v2 Task E fix verification only)

E. **Task E fix verification.** Confirm v2's Task E fix is sound. Sub-questions:
   (a) §9.2 — Does the 5-case file-state table (absent / valid / JSON-parse-fail / layout-invalid / permission-denied) define a SINGLE NORMATIVE PATH for each case? Confirm: every case has explicit return value (`{}` or parsed dict), explicit log behavior (none for A/B; ERROR-level line for C/D/E), explicit activity-log behavior (none for A/B; queued row with specific `details` dict shape for C/D/E), explicit env-var opt-in branch (raise vs return for C/D/E). No case is ambiguous, no case has "fall through to next" behavior.
   (b) §3 Decision 8 — Is the fail-safe-default + opt-in fail-loud-env-var resolution well-supported by the synthesis paragraph? Are tradeoffs honestly represented in BOTH Advocate and Counter paragraphs (no straw-man positions)? Is the env var name (`MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud`) consistent with the existing `MN_PAYLOAD_VALIDATOR_DISABLE=1` pattern in §9.1?
   (c) §5 Phase 1 — Does the 4-fixture test cover all 4 malformed/invalid cases (valid + invalid-JSON + invalid-layout-not-dict + invalid-layout-bad-key)? Plus the 1 fail-loud env-var test for the env-var branch? Are fixture assertions specific enough (log line format, activity-log row `action`, `details` dict shape)?
   (d) §7 risk #11 — Are likelihood (LOW) and severity (MEDIUM) calibrations defensible? Does the mitigation list link back to specific §3 / §5 / §6 / §9.2 elements? Does the risk justify the existing §9.2 fail-safe-default decision (rather than upgrading severity or proposing a different default)?
   (e) §6 Gate 11 — Does the gate explicitly offer YES / DEFER / NO options? Is "NO (different policy)" defined enough that Kim can act on it (vs vague catch-all)?

   EDGE CASES TO PROBE (independent scrutiny — these are the failure modes Cursor should test v2 §9.2's 5-case enumeration against):
   - **File exists but is empty (0 bytes)** — does this fall under case C (JSON-parse-fail, since `json.loads('')` raises `JSONDecodeError`) or case D (layout-invalid, since empty content has no top-level dict)? v2 §9.2 should say case C (the parse fails first); confirm or flag.
   - **File is a symlink to a missing target** — does `Path.exists()` return True or False for a broken symlink? On Python 3.x, `Path.exists()` follows symlinks → returns False if target missing → falls to case A (file absent). But `path.read_text()` would raise `FileNotFoundError` (subclass of `OSError`). Is this case C/D/E or case A? v2 §9.2 needs to handle the asymmetry between `path.exists()` and `path.read_text()` consistently.
   - **File is a symlink to a different file with valid content** — should the validator follow the symlink or reject (security: symlink attack)? v2 §9.2 doesn't explicitly address symlinks; may need an explicit policy line ("symlinks followed; file content evaluated as if direct").
   - **Concurrent edit (file changes between probe and load)** — v2 §9.2 reference implementation does `path.exists()` then `path.read_text()` then `json.loads(content)` — three separate operations. Between any two, the file could change (admin-UI flow per Risk #11 narrative). Is an atomic-read pattern (e.g., open + flock + read) documented? If not, is the cost of one bad-read-then-self-heal-on-next-cache-invalidation acceptable per the fail-safe doctrine?
   - **File is a directory (not a regular file)** — does `Path.exists()` return True for a directory? Yes. Then `path.read_text()` raises `IsADirectoryError` (subclass of `OSError`) → falls to case E (permission-denied bucket). Is "directory not a file" semantically the same as "permission denied"? v2 §9.2 case E enumeration says "permission denied (e.g., chmod 000, ACL block, broken symlink)" — does "broken symlink" cover this asymmetry? Or should case E be widened to "OSError on read" with sub-categories?
   - **Disk-full when WRITING the override file** — out of scope for v2 §9.2 (which covers READ paths only). But flag if v2 addresses it (separate concern from reading; the validator only reads the override file, never writes it; admin-UI flow handles writes — v2 should NOT be expected to cover this).

   NUMERIC AMEND_V3 THRESHOLD (note: this is iteration 3 of the AMEND lineage for this spec; v1 was AMEND_V2; v2 amend would be AMEND_V3):
   - If you identify ≥1 plausible failure mode for the override file that v2 §9.2 does NOT enumerate or handle gracefully (i.e., one of the 5 cases doesn't cover it, or the cases are ambiguous about which one applies), verdict MUST be AMEND_V3. Show the specific failure mode + which case (if any) currently claims to cover it + why coverage is inadequate.
   - "Handle gracefully" = the failure mode resolves to one specific case in the 5-case table with deterministic behavior (return `{}` OR raise on env-var path); ambiguity about which case covers a failure mode = NOT graceful handling.

VERDICT FORMAT (strict, pick exactly ONE):
- AUTHORIZE_IMPLEMENTATION — v2 is sound; Phase 0 (snapshot) may proceed; subsequent phases gated on §6 Kim approvals (including Gate 11). Inherits v1's AUTHORIZE on tasks A-D + F-G.
- AUTHORIZE_PHASE_0_ONLY — v2 is sound BUT Cursor cannot verify live Directus state; mirror prior schema-migration v3 verdict scope (Phase 0 dry-run only, with risk acceptance for Phases 1+ post-Phase 0 artifact review). NOTE: Phase 0 is non-mutating (just inventory), so equivalent to AUTHORIZE_IMPLEMENTATION for Phase 0.
- AMEND_V3 — v2 has a defect on Task E specifically; specify the defect + required v3 fix in concrete numeric terms (which §9.2 case is ambiguous, OR which failure mode is uncovered, OR which fixture is missing from §5 Phase 1, OR which Decision 8 tradeoff was missed in synthesis). NOTE: this is the SECOND Cursor review of this spec lineage; AMEND_V3 means "v2 is the current; emit v3."
- PAUSE_FOR_REDEBATE — fundamental issue; recommend dual-Opus or expanded review (e.g., new debate on the override-file mechanism itself, OR a missing decision that requires independent debate).

Required output:
1. Preflight evidence (sha256 + first 20 lines verbatim + 5 anchored companion-file quotes + 10 v2-spec-anchor captures).
2. Analysis table (Task E + sub-questions a-e + edge-case probe results) with severity, evidence (anchored citation), mitigation, blocker Y/N.
3. Verdict (one of the four above).
4. Limitations + cross-skill drift if any.
```

---

## Step 3 — After Cursor responds

Save Cursor's verbatim response to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_v2_20260508.md`.

Verdict-driven next steps:

- **`AUTHORIZE_IMPLEMENTATION`** → author the implementation handoff for Phase 0 dispatch (Kim authorizes when ready). Phase 0 is non-mutating reconnaissance; subsequent phases gated on spec §6 Kim approvals (Gates 1-11, including the NEW v2 Gate 11 override-file fail-mode policy). v2 explicitly inherits v1's AUTHORIZE on tasks A-D + F-G — combined with v2 Task E pass = full AUTHORIZE for the entire spec surface.
- **`AUTHORIZE_PHASE_0_ONLY`** → equivalent to AUTHORIZE_IMPLEMENTATION since Phase 0 is non-mutating; author Phase 0 implementation handoff.
- **`AMEND_V3`** → author `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v3.md` addressing the defect; preserve v1 + v2 as historical baselines; re-run THIS handoff against v3 (rename + bump version refs + re-anchor sha256). v3 scope should be tightest possible — only the new defect, not a re-open of cleared surface.
- **`PAUSE_FOR_REDEBATE`** → halt; bring findings back to Claude Code; spawn fresh dual-Opus debate on the flagged decision (likely Decision 8 if synthesis is unsound, or a missing decision if coverage gap is structural); do NOT proceed to implementation.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST (applies to handoff author logging this handoff to `prod_activity_log`; applies to Cursor reviewer if they touch Directus during analysis — they should not).
- **Multipass:** re-Read v2 spec after this handoff is authored (handoff author discipline; Cursor reviewer also re-reads if a HALT gate fires).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-13 Layer 6:** input variation (read v2 spec + v1 spec + v1 review handoff + Cursor v1 review outputs) → output variation (this handoff differs structurally from v1 review handoff to TIGHTEN scope from v1's full 7-task review to v2's surgical 1-task verification).
- **DS-19 + DS-26:** always active; fire on any trigger condition. Autonomous mode does not bypass HALT gates.
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."
- **DS-27 (absolute paths, dual-canonical):** all filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits. All paths in this handoff are anchored to canonical root #1 (Dropbox-rooted), with one recognized-exception path under `~/.claude/skills/` for global Claude config.
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in this handoff is listed with absolute path + canonical-root tag. All 7 companion files were probed via `ls -la` at authoring time and confirmed present under canonical root #1 (or recognized `~/.claude/` exception).
- **DS-28 dependency-order:** Wave A research (read v2 spec + v1 spec + v1 review handoff + Cursor v1 outputs + HANDOFF_TEMPLATE_v2) before Wave B execution (author handoff); preflight steps 1-5 verified before Step 1; Step 1 before Step 2; Step 2 before Step 3.
- **DS-29 verification-source discipline:** every claim in the final report tagged explicitly `(my probe)` / `(agent claim)` / `(unverified)`.
- **JSON-column gotcha:** the activity-log POST below uses `details` as a dict (live `prod_activity_log.details` IS a JSON column).
- **LD-597 anti-confusion:** the activity-log POST below MUST NOT include `task_description` (`prod_activity_log` has 11 fields; `task_description` lives on `prod_preflight_reviews`, not `prod_activity_log`).
- **Anchored citation:** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation (mandatory):** "If any required section cannot be evidenced, full mode is mandatory." (Verbatim in Step 2 prompt.)
- **Numeric AMEND_V3 thresholds (mandatory):** Task E (sole task in this surgical scope) has explicit numeric trigger tied to AMEND_V3 verdict (≥1 plausible uncovered failure mode → AMEND_V3).
- **Multipass-Read after authoring:** handoff author re-reads this handoff post-authoring to confirm structural integrity.
- **Halt-and-surface if v2 spec sha256 has changed since session-record:** preflight Gate 1 catches this.

---

## Final report — required structure

Path: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_v2_REPORT_20260508.md`

Required sections:

1. **HALT gate scan results** — 5 gates (sha256 match `047b5efd...`, first-line verbatim `# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v2`, companion-anchor verification, §0 Operating Mode "DESIGN ONLY" confirmed, LD-604 active confirmed).
2. **Cursor verdict verbatim** — exact pasted Cursor response.
3. **Per-task summary** — Task E with sub-questions (a)/(b)/(c)/(d)/(e) + edge-case probe results; verdict + anchored evidence + numeric-threshold result.
4. **Inheritance carry-over** — explicit confirmation that v1's AUTHORIZE on tasks A/B/C/D/F/G carries forward (not re-reviewed in v2).
5. **Confidence tags per Rule 24.**
6. **Self-classification** — REVIEW (Cursor's classification of its own analysis).
7. **Limitations** — what wasn't covered (live Directus state if unreachable from Cursor's environment; v1 tasks A/B/C/D/F/G out of scope per design).
8. **Cross-skill drift** — does v2's §9.2 5-case enumeration require parallel updates to weekly_preflight_audit.py, zero-error-qa SKILL.md, tech-spec SKILL.md, or HANDOFF_TEMPLATE_v2.md?
9. **Next-step recommendation.**

---

## Cross-references

- `LD-597` (`TASK_DESCRIPTION_FIELD_ANTI_CONFUSION_GUARDS_V1`) — anti-confusion guards (governs activity-log row `details` dict shape in v2 §9.2).
- `LD-599` (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1`) — v1 spec authority; status=active `(my probe)`.
- `LD-604` (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V2_MALFORMED_OVERRIDE_FIX_V1`) — **spec authority for THIS review**; status=active `(my probe)`.
- `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md` — v1 historical baseline; sha256 `14ae4e22b653...`; the spec v2 inherits Decisions 1-7, Phases 0/2/3/4/5, Gates 1-10, Risks 1-10 from.
- `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md` — v1 review handoff; structural template for THIS handoff.
- `Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md` — Cursor's v1 verbatim review (AMEND_V2 verdict on Task E).
- `Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_REPORT_20260508.md` — Cursor's v1 review companion summary.
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — live schema authority (LD-597 11-field `prod_activity_log` enumeration).
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate (this handoff conforms to v2 + §0.3).

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Surgical 1-task review (Cursor v1 AMEND_V2 fix verification): Task E only — verifies v2 §9.2 5-case file-state table + §3 Decision 8 dual-Opus synthesis + §5 Phase 1 4-fixture test + §6 Gate 11 + §7 risk #11. Numeric AMEND_V3 threshold tied to ≥1 plausible uncovered failure mode. Edge-case probe list covers symlinks, empty file, concurrent edit, directory-as-file, atomic-read. v1 tasks A/B/C/D/F/G explicitly OUT OF SCOPE (carry forward AUTHORIZE from v1 review). Structural template: `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`.
