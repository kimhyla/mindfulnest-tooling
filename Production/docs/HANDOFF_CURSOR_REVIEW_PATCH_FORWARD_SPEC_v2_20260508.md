# Handoff — Cursor Cross-Review of PATCH-FORWARD PERIODIC Class Tech Spec v2

**For:** Cursor (Composer or chat) — independent reviewer (second-round)
**From:** Claude Code session, 2026-05-08
**Spec under review:** `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md`
**Predecessor handoff (v1):** `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_20260508.md` (193 lines, full mode)
**Companion specs (read for context only):** `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` (731 lines, historical baseline preserved per spec §0.1), `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` (867 lines), `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` (~900 lines), `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` (336 lines)
**Companion code (read for context only):** `Production/scripts/weekly_preflight_audit.py` (999 lines; PERIODIC at lines 130-411)

---

## What changed from v1 of this handoff (per Cursor LOW #6)

Cursor's review of patch-forward spec v1 noted the prior handoff was over-constrained — full citation tables required even when no blockers exist. **v2 of this handoff authorizes "concise mode"** for no-blocker reviews, reducing reviewer overhead while preserving rigor when blockers ARE found.

**Concise mode (when applicable):** If, after preflight + analysis, you find ZERO blocker concerns, your response can be:
- Preflight evidence (mandatory — 5 lines max)
- 1 paragraph confirming the v2 spec resolves all 6 of v1's Cursor findings AND identifies no new blockers
- Verdict: `APPROVE_IMPLEMENTATION`
- (Optional) ≤3 LOW-severity nice-to-have suggestions in a brief bullet list

**Full mode (REQUIRED if any blocker found):** All requirements from handoff v1 apply — citation tables with severity + blocker tags, Q1–Q18 minimum coverage, dependency graph, strict gate format.

You decide concise vs full mode based on what you find. Default to full mode if uncertain.

---

## Why this handoff exists

A prior Terminal A session executed v1 of the PERIODIC class spec without halting at gates. v2 of the PERIODIC spec was authored to address Cursor findings. v1 of the PATCH-FORWARD spec was then authored to take v1-as-built code up to v2 quality. Cursor reviewed PATCH-FORWARD v1 and returned AMEND_BEFORE_IMPLEMENTATION with 6 findings.

**v2 of the PATCH-FORWARD spec amends v1 to address all 6 Cursor findings.** This handoff requests Cursor's second-round review to confirm the amendments resolve the findings without introducing new blockers.

The fundamental question for your review: **Does v2 actually resolve v1's six findings, or are any of the amendments superficial?**

---

## Step 0 — Preflight (do FIRST, before any analysis)

Before reading or critiquing the spec, run these checks and emit results inline:

1. **v2 spec exists:** `ls -la "Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md"` — capture size and mtime.
2. **v2 spec hash:** `shasum "Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md"` — capture digest.
3. **v1 spec still present** (preserved per spec §0.1): `ls -la "Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md"` — confirm v1 not deleted (size + shasum).
4. **Companion files** (size + shasum): `PERIODIC_CLASS_TECH_SPEC_v1.md`, `PERIODIC_CLASS_TECH_SPEC_v2.md`, `PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md`, `weekly_preflight_audit.py` (line count + shasum).
5. **Quote v2 spec §0.1 changelog table verbatim** — read the v2 spec and quote §0.1 (the Cursor-finding-resolution table) as proof-of-fresh-read.

If any preflight fails, **HALT and report**. Do not proceed.

---

## Step 1 — Open the project in Cursor

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md` in the editor. Open Cursor Composer or chat.

Recommended additional editor tabs (read-only context):
- `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` (for diff comparison)
- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md`
- `Production/scripts/weekly_preflight_audit.py`

---

## Step 2 — Paste this prompt into Cursor

```
I have a v2 tech spec at Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md. It is a surgical amendment of v1 (Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md, preserved as historical baseline) that addresses your 6 prior findings on v1: 2 HIGH (byte-equivalent claim, string-fragile grep), 2 MED (reader inventory opacity, repeat-incident governance), 2 LOW (confidence rigor, handoff over-constrained).

v2 §0.1 contains a changelog table mapping each of your findings to the specific v2 amendment and the §ref where it lands. Your task is to verify the amendments are real (not superficial) and that no new blockers were introduced.

Background context (informational only):
- v1 was authored via dual-Opus debate; v2 keeps the resolution but tightens the load-bearing claims.
- v1 is preserved unmodified per Kim's hard rule (historical baseline).
- v2 is the authority for implementation handoff if you APPROVE.

CONCISE MODE AUTHORIZED:
If you find zero blocker concerns, your response can be:
- Preflight evidence (5 lines max)
- 1 paragraph confirming v2 resolves all 6 findings + no new blockers
- Verdict: APPROVE_IMPLEMENTATION
- (Optional) ≤3 LOW-severity nice-to-haves in brief bullet list

FULL MODE REQUIRED IF ANY BLOCKER FOUND:
- Citation tables with severity (CRITICAL/HIGH/MED/LOW) + blocker tag (Y/N)
- Per-finding analysis: did v2 actually resolve v1 finding #N?
- Independent search for any v3-class issues v2 itself missed
- Strict gate verdict: AMEND_V3 or PAUSE_FOR_REDEBATE

Default to full mode if uncertain.

PREFLIGHT (do first, emit inline regardless of mode):
1. Confirm `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md` exists; capture size + mtime.
2. shasum the v2 spec; capture digest.
3. Confirm `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` STILL exists (preserved per spec §0.1); capture size + shasum.
4. Capture size + shasum for the 3 PERIODIC companion specs + line count + shasum for `weekly_preflight_audit.py`.
5. Quote v2 §0.1 changelog table verbatim.
If preflight fails, HALT and report.

PER-FINDING VERIFICATION (covers all 6 v1 findings):

Finding 1 (HIGH — "byte-equivalent" claim too loose):
- v2 claim: §6.1 replaces "byte-equivalent" with "behavior-equivalent" + adds 6 acceptance tests AT1-AT6 (calendar arithmetic).
- Verify: Read v2 §6.1. Are the 6 acceptance tests concrete and unambiguous? Could an implementation pass all 6 while still being semantically wrong elsewhere? Are AT1 (Jan 31 + quarterly → Apr 30) and AT4 (Apr 18 + quarterly → Jul 18 matching LD 249) sufficient to prove `relativedelta` (not `timedelta(days=90)`) is being used?

Finding 2 (HIGH — string-fragile grep):
- v2 claim: §6.6 (NEW) adds Rule 5 structural verification: SV1 (AST-parse for `relativedelta` Call + ImportFrom node), SV2 (synthetic-date probes feeding 6 fabricated rows + asserting tier output), SV3 (date-hygiene invariant probes), SV4 (schema-assertion probe). All MUST-PASS gates.
- Verify: Read v2 §6.6. Is SV1's AST check robust to common variations (e.g., `from dateutil import relativedelta as rdelta`)? Is SV2's input matrix exhaustive enough? Could a paraphrased v1 doctrine still survive structural verification?

Finding 3 (MED — reader inventory opacity):
- v2 claim: §9.1 amended to dual-canonical: LD 577 notes AND new doc `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md`, bidirectionally linked, divergence-check in Phase F2.
- Verify: Read v2 §9.1. Is the divergence-detection mechanism specified concretely? Could the two sources silently drift without triggering a `prod_blocker`?

Finding 4 (MED — repeat-incident governance):
- v2 claim: §5.4.1 (NEW) adds threshold 2/30 OR 3/90 → mandatory process-audit BEFORE next implementation authorization. Audit covers handoff clarity, agent prompts, gate enforcement, doctrine drift.
- Verify: Read v2 §5.4.1. Is the threshold calibration sound? Is the process-audit scope (4 areas) sufficient? Is there a mechanism to ensure the audit actually fires (i.e., who tracks the rolling window)?

Finding 5 (LOW — confidence rigor):
- v2 claim: §4.1 + §10 gate #13 mandate the implementation session's FIRST action is direct Directus GET on LD 577 + direct Read on `weekly_preflight_audit.py` lines 130-411. Both outputs captured to /tmp + reproduced in proof report.
- Verify: Read v2 §4.1 + §10 gate #13. Is the re-read mandate actionable? Are the divergence-detection criteria specific enough to HALT?

Finding 6 (LOW — handoff over-constrained):
- v2 claim: This handoff (HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md) authorizes concise mode for no-blocker reviews.
- Verify: Are you currently using concise mode appropriately? Is the bar between "concise" and "full" defensible?

NEW-BLOCKER SEARCH:
- Q-NEW-1: Did v2 introduce any NEW blocker (HIGH or CRITICAL) that v1 didn't have?
- Q-NEW-2: Are any of the v2 amendments superficial — i.e., they LOOK like they resolve a finding but actually don't change behavior?
- Q-NEW-3: Did v2 break anything from v1 that was previously sound?

REQUIRED OUTPUT (concise OR full mode):

Concise mode output:
1. Preflight evidence (5 lines max)
2. 1 paragraph: "v2 resolves all 6 findings as follows: [brief recap]. No new blockers identified."
3. Verdict: APPROVE_IMPLEMENTATION
4. (Optional) ≤3 LOW-severity nice-to-haves in bullets

Full mode output:
1. Preflight evidence
2. Per-finding table (mandatory citation format with severity + blocker tag): one row per v1 finding, verdict on whether v2 resolved it (RESOLVED / PARTIALLY / NOT_RESOLVED).
3. New-blocker analysis (Q-NEW-1, Q-NEW-2, Q-NEW-3)
4. Final gate verdict in STRICT form (pick exactly one):
   APPROVE_IMPLEMENTATION: v2 resolves all findings, no new blockers; advance to implementation handoff.
   AMEND_V3: v2 has remaining issues; list specific blockers.
   PAUSE_FOR_REDEBATE: fundamental design issues; recommend fresh dual-Opus.
5. If AMEND_V3: list specific blocker concerns with severity + citations.
```

---

## Step 3 — After Cursor responds

If verdict is **APPROVE_IMPLEMENTATION**:
- Author the implementation handoff at `Production/docs/HANDOFF_PATCH_FORWARD_PERIODIC_IMPLEMENTATION_<date>.md` mirroring the v1 implementation handoff structure but with §10 gates 1-15 from the v2 patch-forward spec
- Spawn a Terminal CLI session

If verdict is **AMEND_V3**:
- Bring the blocker list back to Claude Code
- Author `PATCH_FORWARD_PERIODIC_TECH_SPEC_v3.md` addressing each blocker
- Re-run this Cursor cross-review on v3

If verdict is **PAUSE_FOR_REDEBATE**:
- Bring findings back to Claude Code
- Spawn fresh dual-Opus debate
- Do NOT advance to implementation

---

## Specific questions Kim wants Cursor to answer regardless of verdict

1. **Per-finding verification (Findings 1-6):** Does v2 actually resolve each finding, or is any amendment superficial?
2. **AT1–AT6 acceptance tests (§6.1):** Are the 6 calendar-arithmetic tests sufficient to prove `relativedelta` use, or could naive `timedelta(days=90)` slip through?
3. **SV1–SV4 structural verification (§6.6):** Are the AST + synthetic-date + invariant + schema-assertion probes robust to paraphrased v1 doctrine?
4. **§5.4.1 repeat-incident governance:** Is the 2/30 OR 3/90 threshold sound? Who tracks the rolling window?
5. **§9.1 dual-canonical reader inventory:** Is divergence-detection actually wired to fire?

---

## What you DON'T need to do

- Don't have Cursor edit the spec
- Don't have Cursor implement anything
- Don't dual-review the v1 patch-forward spec (already reviewed; v2 incorporates findings)
- Don't re-review the PERIODIC v2 spec (separate concern; already reviewed in prior round)

---

## Why this handoff is structured this way (concise-mode addition)

This v2 handoff descends from `HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_20260508.md` (v1 of the handoff). v1 had:
- Mandatory citation format with severity + blocker tags
- Preflight block
- Strict gate-decision format
- Reader / dependency graph requirements
- Removed framing bias

Cursor's LOW #6 finding noted v1 was over-constrained: full citation tables required even when no blockers exist. v2 adds:

- **Concise mode authorization** for no-blocker reviews — reduces overhead, preserves clarity
- **Per-finding verification structure** — explicitly asks Cursor whether each of the 6 v1 findings is resolved (rather than re-running the full Q1-Q18 from v1 of the handoff)
- **New-blocker search (Q-NEW-1/2/3)** — guards against v2 introducing fresh issues while addressing prior ones

Full mode remains required when blockers ARE found. This preserves rigor where it matters; reduces friction where it doesn't.

---

*End of HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md.*
