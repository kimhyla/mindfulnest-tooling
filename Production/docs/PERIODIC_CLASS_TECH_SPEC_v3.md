# PERIODIC Class — SHORTCUT LD Classification System Tech Spec v3

**Status:** GOVERNANCE-AUTHORING — surgical amendment over v2 to address Cursor round-2 cross-review (5 substantive defect closures: 2 HIGH + 3 MEDIUM, 2026-05-09) + v3-B documentation-structure closure (1 LOW: §14 placeholder); v3-C round-3 cleanup (count math + preserved-verbatim tightening + §14 trade-off doc + `_classification` stamping pin); v3-D round-4 cleanup (governance reframing + ld_id pseudocode pin + pyproject search broadened + closure-type reframing); v3-E round-5 cleanup (line citation refresh + portable find + LD-620 numeric id parity + WARN parity + grep -E portability + re-verify note). **Total: 5 substantive + 1 documentation-structure closure = 6 governance items addressed across v3-A + v3-B + v3-C + v3-D + v3-E sub-passes.**
**Author:** Claude (subagent, surgical-amendment pattern under `zero-error-qa` skill discipline DS-1 .. DS-30)
**Cross-reviewer:** Cursor (round-2 review on v2, 2026-05-09)
**Date:** 2026-05-09
**Classification:** ARCHITECTURAL (Directus schema migration + audit-logic branch)
**Self-classification (Rule 35 / DS-13):** **GOVERNANCE-AUTHORING. No production code mutations** (no `weekly_preflight_audit.py` edits; no hook installs; no `SKILL.md` edits). Spec-authoring artifacts (LD filing in `prod_locked_decisions`; activity_log POST in `prod_activity_log`) ARE the deliverables of governance-authoring sessions per the project-wide Rule 35 / DS-29 discipline — these are NOT production code mutations and ARE the canonical pattern, not an exception. v3-A filed LD-620; v3-B filed LD-625; v3-C filed LD-635; v3-D files a new LD per §0.1 v3-D row below.

**Predecessors / inputs:**
- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` — direct predecessor; 530 lines; sha256 `86343950847942ca0b20691cfe652bb4096732dd7c6b46845f95b382eac69175` [VERIFIED 2026-05-09 via `shasum -a 256`].
- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` — historical baseline; 867 lines; sha256 `387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f` [VERIFIED via v2 §11 carried citation; not re-shasummed in this session — v2 verified 2026-05-09].
- LD-615 (`PERIODIC_CLASS_TECH_SPEC_V2_CADENCE_PARSE_SEVERITY_CONTRACT_V1`) — v2 lock decision; v3 cross-references and supplements.
- Cursor 2026-05-09 round-2 6-finding review on v2 (2 HIGH + 3 MEDIUM + 1 LOW; LOW closed via §14 placeholder): classification source blur (HIGH-1), null-cadence silent skip (HIGH-2), severity-consumer assumption (MEDIUM-1), python-dateutil dependency claim (MEDIUM-2), `none` wording conflict (MEDIUM-3), §14 skeleton gap (LOW — closed via §14 placeholder section).
- `Production/scripts/weekly_preflight_audit.py` — 1887 lines. Read fresh in this session for MEDIUM-1 verification (NOT modified). Severity-field-consumption citations below.

**Note on prior v2 drafts:** A 909-line v2 draft (sha256 `92eec08c33df1d4a14ac119bd3ed8f4e5c8b91bacef2c7c72d7f7446d10fdc2`) addressed an unrelated 9-finding Cursor review and is preserved at `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md.bak.preexisting_20260509`. This v3 amends THE NEW v2 (the 4-defect-fix version, 530 lines), NOT the older 9-finding draft.

**Self-bounds (DS-29 source tagging):** v3 is the ONLY file written this session. v1/v2/v2.bak.preexisting/`weekly_preflight_audit.py`/Cursor review handoff/PERIODIC implementation handoff/settings.json/hook scripts NOT modified. NO commits. NO parallel agents. weekly_preflight_audit.py read-only for line-number citation.

---

## §0 Operating Mode Declaration

Per `zero-error-qa` skill §0:

- **Mode:** GOVERNANCE-AUTHORING tech spec (v3 surgical amendment over v2). Spec content + LD filing + activity_log POST are the canonical deliverables of governance-authoring sessions; these are NOT production code mutations.
- **Tier:** Tier C (architectural — same scope as v1 + v2; touching governance schema + audit logic).
- **Scope risk class:** Multi-stage + side-effect (v2's classes carry forward); v3's amendments are doc-only and lower the risk by closing a verification gap (MEDIUM-1 actually-read consumer code).
- **Six-Layer applicability (DS-13):** v2's mapping carries forward verbatim. v3 adds: Layer 3 backend processing now has a CONFIRMED consumer-code citation (grep anchors `is_critical = days_overdue >= 7`, `days_until_cap <= critical_threshold_days`, and `f.get("critical")` in `weekly_preflight_audit.py`) replacing v2's INFERRED claim.
- **Authoring discipline (DS-15):** Every state claim cites a source. v3 reads `weekly_preflight_audit.py` fresh and cites line numbers; v1/v2 line citations carried forward verbatim where unchanged.
- **Confidence tags (Rule 24):** `[VERIFIED]` = directly read from source in this session; `[INFERRED]` = derived from cited evidence; `[ASSUMED]` = working hypothesis pending confirmation.

This spec lands as a reviewable doc. **No production code edits. No schema migrations on production tables. No dependency installs from THIS session.** Spec-authoring artifacts (LD filings in `prod_locked_decisions`; activity_log POSTs in `prod_activity_log`) ARE produced by this session — those are the canonical deliverables of governance-authoring per Rule 35 / DS-29, NOT exceptions to a no-mutation rule. v3's behavior amendments are queued for the same Kim-authorized implementation patch session that will fold v2 amendments — a unified Phase B.

### §0.1 v3 Changelog (vs. v2)

Cursor's round-2 2026-05-09 review on v2 surfaced two HIGH defects (classification-source blur, null-cadence silent skip) and three MEDIUM defects (severity-consumer assumption, python-dateutil dependency claim, `none` wording conflict). v3 lands surgical fixes; all v2 sections not listed below are preserved verbatim by reference.

#### v3-F (2026-05-09 — citation refresh + dual-lib refactor) — supersedes v3-E citation style where conflicts exist

Periodic follow-up cleanup removes the remaining load-bearing `weekly_preflight_audit.py` line-number citations in §B1, §B3, §11, and the §A4-linked audit pseudocode, replacing them with grep-anchored references to stable symbols/snippets (`def check_shortcut_ld_closure_dates`, `SHORTCUT_LD_CLASSIFICATION.get(ld_id)`, `f.get("critical")`, and the outbound `"severity": "critical"` payload). The implementation cleanup also renames the smaller ambiguous `Production/tools/lib` package to `Production/tools/credentials_lib`, updates its importers, and keeps canonical `Production/lib` imports distinct.

#### v3-E (2026-05-09 — Cursor round-5 cleanup: line citation refresh + portable find + LD-620 numeric id parity + WARN parity + grep -E portability + re-verify note) — supersedes v3-A/v3-B/v3-C/v3-D wording where conflicts exist

Cursor 2026-05-09 round-5 cross-review on v3 (post-v3-D) surfaced 6 documentation-quality findings (1 HIGH + 3 MEDIUM + 2 LOW):

- **HIGH** §0.1 v3-D "sections touched" cites stale line numbers. Cursor cited line 47 (v3-D row 48 in current spec): "v3-D changelog claims '§9 risk row #14 at line 582 (ld_id pin)' but line 582 is actually inside Phase B0 prerequisite block under §8. Risk row #14 is at lines 596-599." v3-E HIGH refresh: re-audited ALL hard line citations in v3-D row 48 + v3-D HIGH-1 row 43 + v3-D MEDIUM-2 row 46. Findings: (a) v3-D row 48 had stale citations for §B1 stamping pseudocode (claimed 125-133, actual 141-142), helper-signature docstring (claimed 148, actual 153), call-site pseudocode (claimed 172, actual 186-187), §4.2 audit-branch comment (claimed 417, actual 431-435), §B4 pyproject search (claimed 319, actual 334), and risk row #14 (claimed 582, actual 598); (b) v3-D HIGH-1 row 43 cited "lines 621-623" for the §11 LD-bullet block, which had drifted to 637-639; (c) v3-D MEDIUM-2 row 46 cited "lines 3 / 43 / 714" for the §19 authorship trail, where 714 is blank (§19 starts at line 727 and the v2-reviewed row is line 732). Resolution: convert ALL of these citations to section-ref form ("§B1 stamping pseudocode", "§9 risk row #14", "§19 v2-reviewed-by-Cursor entry") which is resilient to future edits. This v3-E row deliberately uses ZERO hard line numbers in its own changelog text to avoid recreating the rot pattern.

- **MEDIUM-1** §B4 embeds machine-specific absolute path. Cursor cited lines 330-334: pyproject.toml absence-search uses `find "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" ...` — that absolute path embeds a machine-specific dependency. v3-E resolution: rewrite as portable repo-root form `find . -name pyproject.toml -not -path '*/node_modules/*' -not -path '*/.deploy_backups/*' -not -path '*/.git/*'` with explicit "run from project root" note. Rationale documented: any clone path on a different machine, CI runner, or worktree should produce the same audit result; the absolute-path form created an apparent dependency on Kim's local Dropbox path. v3-D's verification result (ZERO matches) is preserved.

- **MEDIUM-2** §11 v3-A "self-reference LD" bullet inconsistent with v3-B / v3-C / v3-D bullet format. Cursor cited a "§11 v3-A bullet says 'LD id assigned at filing time' without numeric id" claim — current v3-A bullet text DID NOT contain that string (Cursor quotation was inaccurate; recorded here as a disagreement). However, on inspection, the v3-A bullet WAS less detailed than v3-B/v3-C/v3-D format and v3-B was missing entirely from the §11 list despite being filed under LD-625. v3-E parity refresh: v3-A bullet rewritten to match v3-B/v3-C/v3-D format with explicit `filed 2026-05-09 via lock_decision.py lock; cache rebuilt at filing time; predecessors: none` fields; new v3-B bullet inserted with LD-625 + predecessors LD-620.

- **MEDIUM-3** §B3 Step 2 tag migration may rename WARN → WARNING. Cursor cited lines 301-306: v3-D Step 2 used `("critical" if f.get("critical") else "warning").upper()` which yields `"WARNING"`, while v2-old the print-tag anchor emitted `"WARN"`. v3-E parity decision (option (b) in the prompt): use lowercase `"warn"` (NOT `"warning"`) so `.upper()` round-trips to `"WARN"`, preserving back-compat with logs/screenshots/grep-anchors/tests. The `prod_blockers` REST payload column (grep anchor `"severity": "critical",`) continues to use canonical `"critical"` / `"warning"` enum strings — that is a separate schema layer and is NOT affected. v3-E also adds a parity-deviation note: if Phase B implementer DOES choose `"warning"` in the finding dict, that is a deliberate rename and MUST be documented in the Phase B closeout LD with explicit log-grep / screenshot-diff impact assessment.

- **LOW-1** grep one-liner BSD/GNU portability. Cursor cited lines 332-333: `grep -rn "from dateutil\|import dateutil\|python-dateutil\|relativedelta" ...` uses backslash-pipe alternation, which behaves differently on BSD `grep` (macOS default) vs GNU `grep` unless `-E` is specified. v3-E LOW-1 portability refresh: add `-E` flag (`grep -rEn "from dateutil|import dateutil|python-dateutil|relativedelta" ...`) so the unescaped `|` is the canonical alternation operator on both platforms. v3-E note: this works on both BSD and GNU grep with `-E`; portable across CI / local-dev / worktrees.

- **LOW-2** Pinned `weekly_preflight_audit.py` line numbers will rot under future edits. Cursor cited §B1 / §B3 / §11 use exact lines (167, 201–212, 215, 219, 230, 231, 281, 289, 305, 372, 395, 404, 434, etc.). Edits to the audit script invalidate these. v3-E LOW-2 resolution: add a "re-verify on edit" note in §11 Reference Index citing the canonical re-verification grep recipe; document that line numbers are point-in-time snapshots and not load-bearing for behavior — they are reading aids only. The existing line numbers stay as point-in-time audit data; future re-verification is mechanical.

Locked under LD `PERIODIC_CLASS_TECH_SPEC_V3_E_ROUND_5_FIXES_V1` — **LD-645** (filed 2026-05-09 via `lock_decision.py lock`; cache rebuilt to 606 active LDs). Predecessors: LD-620 v3-A, LD-625 v3-B, LD-635 v3-C, LD-640 v3-D. Sections touched (v3-E uses section-refs throughout — no hard line numbers): §0.1 v3-E row (new — this section), §0.1 v3-D HIGH-1 row (line citation refresh — converts "lines 621-623" to §11 LD-bullet block + adds v3-E note), §0.1 v3-D MEDIUM-2 row (line citation refresh — converts "lines 3 / 43 / 714" to section-refs + adds v3-E note), §0.1 v3-D row 48 "Sections touched" sentence (line citation refresh — converts all hard line numbers to section-refs + adds v3-E header note), §B3 Step 1 producer pseudocode (WARN parity — `"warning"` → `"warn"`), §B3 Step 2 consumer pseudocode + lead-in paragraph (WARN parity decision documented + parity-deviation Phase B closeout requirement), §B4 pyproject absence-search bullet (portability rewrite + grep -E refresh + v3-E note), §11 Reference Index `weekly_preflight_audit.py` row (re-verify note), §11 Reference Index §B4 confidence row (`grep -rEn` portability refresh), §11 LDs cited (v3-A bullet parity refresh + new v3-B bullet inserted), §17 §B4 confidence row (grep -rEn portability), §12 v3 changelog (v3-E row added — see below), §19 authorship trail (v3-E drafted + v3-D reviewed by Cursor row added). v1 + v2 + v2.bak + weekly_preflight_audit.py + hooks + settings.json + other tech-specs + Cursor v3 review handoff + implementation handoff NOT touched. v3 remains canonical spec; v3-E is a sub-version sweep, NOT a version bump.

**Disagreement with Cursor (v3-E MEDIUM-2):** Cursor's MEDIUM-2 quotation ("§11 v3-A bullet says 'LD id assigned at filing time' without numeric id") was not present in the on-disk spec at v3-E review time — current v3-A bullet DID have **LD-620** numeric id. v3-E counter-position: the underlying parity concern (v3-A bullet less detailed than v3-B/v3-C/v3-D format, and missing v3-B bullet entirely) IS valid even though Cursor's quoted string was inaccurate. v3-E applies the parity fix on the underlying concern; the inaccurate quotation is logged here for audit trail completeness and DS-19 deviation discipline.

#### v3-D (2026-05-09 — Cursor round-4 cleanup: GOVERNANCE-AUTHORING reframing + ld_id pseudocode pin (final) + pyproject search broadened + closure-type reframing) — supersedes v3-A/v3-B/v3-C wording where conflicts exist

Cursor 2026-05-09 round-4 cross-review on v3 (post-v3-C) surfaced 4 documentation-quality findings, including ONE real pseudocode bug (the ld_id pin v3-C claimed to fix but left applied to documentation only):
- **HIGH-1** Design-only declaration vs in-session LD writes (recurring governance wording). Cursor cited line 8 ("STANDARD — surgical doc-only amendment; no code/schema mutation in this session; spec content only") vs the §11 "NEW v3 self-reference LD" bullets (v3 LD filed in this session via lock_decision.py + cache rebuilt) (v3-E note 2026-05-09: v3-D originally cited "lines 621-623" — the §11 LD-bullet block has since drifted; v3-E HIGH refresh converts to section-ref form). v3-D resolution: replace STANDARD/no-mutation language with **GOVERNANCE-AUTHORING** declaration explicitly noting that LD filings + activity_log POSTs ARE the canonical deliverables of governance-authoring sessions per Rule 35 / DS-29, NOT exceptions. Applied at §0 self-classification banner, §0 operating-mode bullet, §0 mid-paragraph mutation-scope sentence. Aligns this spec with the project-wide governance-authoring reframing applied to other tech-specs.
- **HIGH-2** Pseudocode still uses `ld["key"]` after v3-C "ld_id pin" fix. v3-C documented the live convention in prose (lines 126-132 NOTE block) but left the pseudocode itself at lines 133, 148, 172, 417 — and the §9 risk #14 mitigation snippet — still using `ld["key"]` "for spec-level readability" — that mismatch IS the bug class v3-C claimed to fix. v3-D resolution: rewrite ALL pseudocode/docstring/risk-row references to use `ld_id = ld["id"]` (integer Directus row id) consistently. Documentation comments AT lines 46, 128, 136, 650 retain `ld["key"]` quotation in their role as descriptions of the bug pattern (not code patterns); pseudocode does not. Post-edit grep-verified.
- **MEDIUM-1** "find . -maxdepth 3" too shallow for repo-wide pyproject.toml absence claim. Cursor cited line 319 (v3-A's `find . -maxdepth 3 -name pyproject.toml` claim under §B4) — flagged that "the command scope is not strong enough to support a global dependency-authority assertion." v3-D resolution: re-ran broadened search `find "<project root>" -name pyproject.toml -not -path '*/node_modules/*' -not -path '*/.deploy_backups/*' -not -path '*/.git/*'` — returned ZERO results [VERIFIED 2026-05-09 in v3-D session]. Citation rewritten at line 319 to include the broadened command + verification timestamp + result.
- **MEDIUM-2** "6 findings closed" semantically conflates defect closure with documentation cleanup. Cursor cited lines 43-47 (v3-C's count-math standardization) — flagged that mechanical governance gates may want to distinguish substantive defect-fix from doc-structure cleanup. v3-D resolution: reframe wording in §0 status banner + §0.1 HIGH-1 closure paragraph + §19 authorship trail (v3-E note 2026-05-09: v3-D originally cited "lines 3 / 43 / 714" — the §19 line citation 714 was stale at v3-D filing time; v3-E HIGH refresh converts these to section-refs) to make the **5/1 split** explicit — 5 substantive defect closures (2 HIGH + 3 MEDIUM, authored in v3-A from Cursor round-2 verbatim) + 1 documentation-structure closure (LOW §14 placeholder, authored in v3-B). Bare "6 findings" count remains valid for backward-compatible reading; the 5/1 split is the v3-D-tightened canonical decomposition.

Locked under LD `PERIODIC_CLASS_TECH_SPEC_V3_D_ROUND_4_FIXES_V1` (predecessors: LD-620 v3-A, LD-625 v3-B, LD-635 v3-C). Sections touched (v3-E note 2026-05-09: hard line numbers below were point-in-time when v3-D was authored; v3-E round-5 HIGH refresh re-verifies them and converts to section-ref form for resilience to future edits — see v3-E row above): §0 status header (closure-type reframing + v3-D entry), §0 self-classification banner (governance reframing), §0 operating-mode bullet (governance reframing), §0 mid-paragraph (governance reframing), §0.1 v3-D row (new — this section), §0.1 HIGH-1 closure paragraph (closure-type reframing), §B1 stamping pseudocode (ld_id pin), §B1 helper-signature docstring (ld_id pin), §B1 call-site pseudocode (ld_id pin), §4.2 audit-branch comment (ld_id pin), §B4 pyproject search (broadened), §9 risk row #14 / §7 table (ld_id pin in mitigation text), §19 v2-reviewed-by-Cursor entry (closure-type reframing), §12 v3 changelog (v3-D row added). v1 + v2 + v2.bak + weekly_preflight_audit.py + hooks + settings.json + other tech-specs + Cursor v3 review handoff + implementation handoff NOT touched. v3 remains canonical spec; v3-D is a sub-version sweep, NOT a version bump.

#### v3-C (2026-05-09 — Cursor round-3 cleanup: count math + preserved-verbatim tightening + §14 trade-off doc + `_classification` stamping pin) — supersedes v3-B framing where conflicts exist

Cursor 2026-05-09 round-3 cross-review on v3 (post-v3-B) surfaced 5 documentation-quality findings:
- **HIGH-1** Internal contradiction about fixture/finding count: "5 findings (2 HIGH + 3 MEDIUM, 1 LOW closed via §14 placeholder)" — math conflict (2+3=5; +1 LOW would be 6). v3-C resolution: standardize on **6 findings closed (2 HIGH + 3 MEDIUM + 1 LOW)** in every count reference (§0 status header, §0.1 changelog, §12 changelog, §19 authorship trail, line-14 finding-list). The LOW IS closed (via §14 placeholder); it counts as a closed finding, not a deferred one. v3-C grep-verified zero remaining "5 findings" / "5-finding" math-conflicting strings. **v3-D round-4 MEDIUM-2 reframing:** to make the closure-type composition mechanically readable, this 6-count is decomposed as **5 substantive defect closures (2 HIGH + 3 MEDIUM) authored in v3-A from Cursor round-2 verbatim + 1 documentation-structure closure (LOW §14 placeholder) authored in v3-B**. Both flavors are valid governance closures; future automation can read either the bare 6-count OR the 5/1 split depending on whether it cares to distinguish defect-fix from doc-cleanup.
- **HIGH-2** "Preserved verbatim" framing was overstated for sections that v3 amends behavior on (§4.1, §4.2, §5.1, §A1, §A3, §A4, §7). v3-A's §0.1 listed these among "preserved unchanged" (technically true for v2-baseline wording) but didn't distinguish from sections v3 truly amends. v3-C resolution: section-status taxonomy split into 3 explicit buckets — **PRESERVED VERBATIM** (true zero v3 changes), **PRESERVED AS V2 BASELINE + AMENDED BELOW** (v2 wording is starting point but v3 §B amendments supersede behavior), and **NEW IN V3** (no v2 equivalent). Each behavior-changing section header tightened to point to its §B[N] amendment block (§7, §5.3, §A2 confirmation). Reader rule added: implementers MUST read both v2 + the §B[N] block for any "AMENDED BELOW" section.
- **MEDIUM-1** §14 placeholder fix introduces structural drift without rationale documentation. v3-C resolution: §14 v3-C trade-off documentation subsection added, explicitly weighing "full structural renumber" vs. "placeholder + cross-walk" and documenting WHY placeholder won (3 reasons: breaks v1+v2 cross-references; balloons diff for cosmetic gain; long-term maintenance friction). Future v4 hook noted.
- **MEDIUM-2** `_classification` stamping convention was unpinned to function/location. v3-C resolution: pinned to `weekly_preflight_audit.py` grep anchors `def check_shortcut_ld_closure_dates`, `client.get("prod_locked_decisions"`, `for ld in rows:`, and `SHORTCUT_LD_CLASSIFICATION.get(ld_id)`; stamping insertion point immediately after the `if classification is None` short-circuit (after UNCLASSIFIED short-circuit, before PERIODIC branch). Also caught and documented v3-A pseudocode bug: live code keys registry by `ld_id` (integer row id), NOT `ld["key"]` — Phase B implementation MUST mirror live convention.
- **LOW** Count-math tail issue — rolled into HIGH-1 resolution above.

Locked under LD `PERIODIC_CLASS_TECH_SPEC_V3_C_ROUND_3_FIXES_V1` (predecessors: LD-620 v3-A original, LD-625 v3-B cleanup). Sections touched: line 3 status header, line 14 review-finding list, §0.1 v3-C row (new — this section), §0.1 section-status taxonomy (HIGH-2 split), §B1 stamping pin (MEDIUM-2), §A2 confirmation note, §5.3 header tightening, §7 header tightening, §12 v3 changelog header (count math), §14 v3-C trade-off subsection (MEDIUM-1), §19 v3 + v3-C authorship rows (count math + new v3-C drafted row). v1 + v2 + v2.bak + weekly_preflight_audit.py + hooks + settings.json NOT touched.

#### v3-B (2026-05-09 — multi-section LOW consistency cleanup) — supersedes v3-A LOW-deferred narrative

Authoring sweep over v3 found internal contradiction: a prior edit added the §14 placeholder section closing the Cursor round-2 LOW finding, but other sections (§0 status header, §0.1 changelog row, §12 changelog row, §19 authorship trail, line-14 finding-list, §0.1 LOW-paragraph) still asserted "1 LOW deferred". v3-B sweeps every LOW reference and rewrites to a consistent narrative: **LOW closed via §14 placeholder section.** No new content; tone-only consistency repair. Locked under LD `PERIODIC_CLASS_TECH_SPEC_V3_B_LOW_CONSISTENCY_V1` (predecessor LD-620). Sections touched (consistency only): line 3 status header, line 14 review-finding list, §0.1 LOW paragraph (line 48), §12 v3 changelog bullet (line 582), §12 LOW sub-bullet (line 588), §19 v2-reviewed-by-Cursor entry (line 635). v1 + v2 + v2.bak + weekly_preflight_audit.py + hooks + settings.json NOT touched.

#### v3-A (2026-05-09 — Cursor round-2 surgical fixes)

| # | Cursor finding | Severity | v2 location | v3 resolution | v3 sections |
|---|---|---|---|---|---|
| HIGH-1 | Classification source blurred — helper uses `ld.get("classification")`, but v1 design keys class from a code constant `SHORTCUT_LD_CLASSIFICATION`, not a Directus field. Implementers may test on the wrong object (REST row vs. local dict). | HIGH | v2 §A4 line 227 (`if ld.get("classification") != "PERIODIC": return False`) and §4.2 line 274 (`if classification == "PERIODIC":`) | Pin canonical convention: classification is computed from the `SHORTCUT_LD_CLASSIFICATION` registry/constant at LD-load time and **stamped onto the dict as a `_classification` key** before any audit predicate runs. The `is_audit_eligible_periodic_row` helper now takes `(classification, ld_row)` parameters explicitly (option-b in the prompt) — but for ergonomics also stores `_classification` on the row when the loader prefers single-arg helpers. Documented in §B1. | §B1, §A4-amend, §4.2-amend |
| HIGH-2 | PERIODIC rows with `review_cadence = NULL` are silently skipped — collides with "LD 249 must have structured cadence" intent and hides mis-configuration. The (classification=PERIODIC, cadence=NULL) combination is an INVALID config, not an opt-out. | HIGH | v2 §A4 lines 222-235 (audit predicate `cadence is None ... return False`), §4.2 lines 277-280 (early `continue` on `cadence is None`) | Add explicit `PERIODIC_INVALID_CONFIGURATION` finding (severity=`critical`) when `classification == "PERIODIC" AND cadence is None`. Update §A4 table — the (PERIODIC, NULL) combination is explicitly INVALID. The opt-outs (`'none'`, `'event-driven'`) remain valid skip values; NULL is no longer a valid skip when classification is PERIODIC. | §B2, §A4-amend, §4.2-amend |
| MEDIUM-1 | "Boolean → string severity is compatible with existing blocker writer" was asserted without re-verifying the real consumer in `weekly_preflight_audit.py`. | MEDIUM | v2 §A3 line 200 ("the prod_blockers writer that fires on critical findings already keys off severity strings") | Re-read `weekly_preflight_audit.py` this session; cite actual consumption lines. **Finding:** the consumer keys off BOOLEAN `f.get("critical")` at the blocker-filter and print-tag anchors. The string `"severity": "critical"` at the outbound-payload anchor is the OUTBOUND `prod_blockers` POST payload schema field, not the finding-dict consumption. v2's "already keys off severity strings" claim is INACCURATE. v3 documents a 3-step migration: (1) implementer adds STRING `"severity"` field to finding dict alongside boolean `"critical"`; (2) print/filter sites updated to read `severity == "critical"` instead of `critical is True`; (3) boolean `"critical"` field deprecated then removed. | §B3, §A3-amend |
| MEDIUM-2 | "python-dateutil already transitive dependency" claim is environment-specific and unverified. | MEDIUM | v2 §A1 line 94 ("It is already a transitive dependency in this codebase (used by `requests`/`requests-toolbelt`/`directus-sdk` chains)") | Drop the "already transitive" claim. v3 documents explicit `pip install python-dateutil>=2.8` requirement. Verified `Production/tools/requirements.txt` (the canonical CI install manifest, 20 lines) does NOT list python-dateutil — only `PyYAML>=6.0` + `Pillow>=10.0`. Verified zero `from dateutil`/`import dateutil` matches anywhere under `Production/`. Implementer MUST add `python-dateutil>=2.8` to `Production/tools/requirements.txt` as Phase B prerequisite step B0. | §B4, §A1-amend, §8 Phase B prerequisite |
| MEDIUM-3 | §5.1 "Common case" wording for `'none'` reads as if `'none'` applies to RARE_NEVER and EVENT_DRIVEN LDs. Per §A4 it's a PERIODIC-only opt-out. RARE_NEVER + EVENT_DRIVEN must use NULL. | MEDIUM | v2 §5.1 line 372 (`'none'                            n/a — no review surfacing (per §A4)            All RARE_NEVER and most EVENT_DRIVEN LDs`) | Rewrite the §5.1 `'none'` row: it's a PERIODIC-only opt-out (rare; explicit "PERIODIC class but no calendar review"). RARE_NEVER and EVENT_DRIVEN LDs MUST set `review_cadence = NULL`, NOT `'none'`. Add §A4 cross-reference. | §B5, §5.1-amend |

**LOW closed via §14 placeholder:** v2 §13 Audit Checklist is followed by §15 Pre-Implementation Gates — §14 was dropped from the skeleton (numbering jumps §13 → §15). Cursor flagged this as cosmetic. v3 closes this LOW finding by adding a §14 placeholder section (see §14 below) that documents the historical gap and provides a v1→v3 cross-walk pointer. v3 deliberately does NOT renumber: renumbering would force every §15+ cross-reference in v1/v2/handoffs to update, against the surgical-amendment principle. The placeholder closes the citation surface without renumbering. A future v4 (if produced) may renumber as part of a structural pass.

**Section-status taxonomy (v3-C tightened — supersedes v3-A's broad "preserved unchanged" framing):**

v3-C distinguishes three states (v3-A conflated the first two; v3-C round-3 HIGH-2 cleanup splits them):

- **PRESERVED VERBATIM (no v3 changes; safe to copy directly from v2):** §1 scope, §2 background, §3 current system (note: v3 ADDS line citations 281/289/305/372/395/404/434 as VERIFIED — that addition is purely informational, no v2 wording changes), §4.3 cap-selection refactor, §4.4 roadmap update, §4.5 non-SHORTCUT scope, §5.2 next_review_date required-vs-optional, §5.4 last-reviewed consistency check, §5.5 severity reuse, §6 dual-Opus meta-debate, §13 audit checklist, §15 pre-implementation gates (v3 ADDS one new gate: Kim approves §B1–§B5 — additive only), §16 recommended sequence (v3 ADDS Phase B0 insertion — additive only; existing v2 sequence preserved), §17 confidence sweep (v3 ADDS new rows for §B1–§B5 — additive only), §18 TL;DR, §19 authorship trail (v3-extended).
- **PRESERVED AS V2 BASELINE + AMENDED BELOW (v2 wording is the starting point but v3 §B amendments supersede behavior; implementers MUST read both):**
  - §4.1 — schema/cadence semantics. **AMENDED BELOW: see §B2** (NULL on PERIODIC = INVALID, not opt-out).
  - §4.2 — audit-branch pseudocode. **AMENDED BELOW: see §B1 (classification source) + §B2 (NULL invalid-config) + §B3 Step 1 (string severity)**. v2's audit-branch pseudocode is REPLACED by §4.2 v3 block (lines 363-464); reading v2 alone for this section is INSUFFICIENT.
  - §5.1 — `review_cadence` enum table. **AMENDED BELOW: see §B5** (`'none'` is PERIODIC-only; NULL is non-PERIODIC default; (PERIODIC, NULL) is INVALID).
  - §7 — migration cohort. **AMENDED BELOW: see §B4 + §8** (Phase B0 prerequisite — `python-dateutil>=2.8` required before §A1's `relativedelta` import).
  - §8 — implementation phases. **AMENDED BELOW: see §B4 + §8 v3 block** (Phase B0 INSERTED before Phase B; Phase B audit-logic update lands in same PR as B0 or strictly after).
  - §A1 (calendar-aware cadence). **AMENDED BELOW: see §B4** ("already transitive" claim DROPPED; explicit Phase B0 dependency-add required).
  - §A3 (severity from resolution). **AMENDED BELOW: see §B3** (v2's "already keys off severity strings" claim REPLACED with verified consumer-code citation + 3-step migration; behavior change to finding-dict shape).
  - §A4 (3-state contract). **AMENDED BELOW: see §B1 (predicate signature) + §B2 (NULL on PERIODIC = INVALID; new state PERIODIC_INVALID_CONFIGURATION).** v2's §A4 contract table is REPLACED by §B2 v3 contract table.
- **NEW IN V3 (v2 contained no equivalent):** §B1–§B5 (the 5 surgical fix sections themselves), §10.7 (round-2 regression tests), §14 (placeholder closing the LOW finding), §9 risk rows #14–#18 (5 new round-2 risks), §11 v3 augmentations (audit-script + requirements.txt citations + new constants `_classification` / `is_audit_eligible_periodic_row` / `PERIODIC_INVALID_CONFIGURATION`), §12 v3-A + v3-B + v3-C changelog rows.

**Reader rule (v3-C):** For any "PRESERVED AS V2 BASELINE + AMENDED BELOW" section, the v2 wording is necessary but NOT sufficient — implementers MUST also read the cited §B[N] amendment block. v3-A's broad "preserved unchanged" framing was overstated for behavior-changing sections; v3-C corrects that surface.

---

## §B Surgical Amendments (the 5 v3 fixes)

This section consolidates the 5 surgical amendments that drive the v2→v3 diff. v2 sections referenced above are amended in place by reading v2 + applying these patches; the prose below is the canonical v3 statement of each fix.

### §B1 HIGH-1 fix — pin classification source convention

**Problem (Cursor round-2 2026-05-09):** v2 `is_audit_eligible_periodic_row(ld)` (v2 §A4 line 223 quoted: `if ld.get("classification") != "PERIODIC": return False`) reads `classification` from the row dict. But the v1 design keys classification from a code-side `SHORTCUT_LD_CLASSIFICATION` constant/registry — NOT from a Directus field on the row. Implementers copying §A4 / §4.2 literally may test classification on the wrong object: a REST row dict that has no `classification` key would always return `False` from `ld.get("classification")`, silently disabling the audit branch for every PERIODIC LD.

**Fix (v3 §B1 — supersedes v2 §A4 helper signature + v2 §4.2 audit branch top):**

Two-pronged convention. Pick the loader convention (option a) AND clarify the helper signature (option b):

**(a) Loader convention — classification stamped onto the row dict at load time:**

**v3-F citation refresh — grep-anchored function/snippet citation:**

The loader is grep-anchored by `def check_shortcut_ld_closure_dates(client, dry_run=False)` in `Production/scripts/weekly_preflight_audit.py` [VERIFIED 2026-05-09 via direct read]. Within that function, anchor the Directus query on `client.get("prod_locked_decisions", filters={"decision_key": {"_starts_with": "SHORTCUT_"}, "status": {"_eq": "active"}}, fields=[...])`, the per-row loop on `for ld in rows:`, and the classification lookup on `classification = SHORTCUT_LD_CLASSIFICATION.get(ld_id)`. These grep anchors replace hard line numbers; line positions are non-normative.

**Stamping MUST land after the `SHORTCUT_LD_CLASSIFICATION.get(ld_id)` registry lookup and before the PERIODIC branch.** Specifically, immediately after the existing `if classification is None: ... continue` UNCLASSIFIED short-circuit, insert the stamping:

```python
# Production/scripts/weekly_preflight_audit.py — Phase B implementation
# inserts this AFTER the UNCLASSIFIED short-circuit (`if classification is None`)
# and BEFORE the first date/cadence validation for classified rows.
# Stamping convention per spec §B1(a): underscore prefix marks code-derived,
# distinguishing from any future REST `classification` column.
ld["_classification"] = classification
```

Phase B implementation MUST land this stamping line BEFORE any audit predicate that consumes `_classification` (i.e., before the §B2 invalid-config check, before the §B3 finding-dict construction, and before any future helper invocation that takes `ld_row` as a single argument). At the time of writing (v3-C, 2026-05-09), no in-tree code yet reads `ld["_classification"]` — the stamping is forward-looking infrastructure for §B1's helper-signature contract.

**Stamping pseudocode in the abstract — for reader convenience (the canonical pinning is the citation above):**

```python
# After fetching rows from Directus and BEFORE any audit predicate runs,
# stamp the classification under the underscore-prefixed key `_classification`
# (underscore prefix marks "computed/derived, not from REST"):

# v3-D round-4 HIGH-2 fix: pseudocode now uses `ld_id` (integer row id)
# directly, mirroring the LIVE codebase convention at
# grep anchor `SHORTCUT_LD_CLASSIFICATION.get(ld_id)`. v3-C documented the convention but left
# the pseudocode using `ld["key"]` "for readability" — that mismatch was
# itself the bug class v3-C claimed to fix. v3-D removes the mismatch.
for ld in shortcut_ld_rows:
    ld_id = ld["id"]  # integer Directus row id (canonical registry key)
    classification = SHORTCUT_LD_CLASSIFICATION.get(ld_id, "UNCLASSIFIED")
    ld["_classification"] = classification
```

**Disagreement note (v3-C with v2 §A4 line 227):** v2 §A4 quoted `if ld.get("classification") != "PERIODIC": return False` — that quotation is a v2 design illustration, not a citation to live code. The live code uses the grep anchor `SHORTCUT_LD_CLASSIFICATION.get(ld_id)` against the registry, and there is no `classification` field on the Directus row at all. The §B1 fix is correct in direction; the v3-C tightening is just to make the registry-lookup key (`ld_id` integer, not `ld["key"]` string) match the live convention.

The underscore prefix is the documented convention for "this key is derived in code, not from the Directus REST payload." Any future REST-side `classification` column would NOT collide (different key names).

**(b) Helper signature — explicit two-arg form:**

```python
def is_audit_eligible_periodic_row(classification: str, ld_row: dict) -> bool:
    """Return True iff this row should be processed by the PERIODIC
    auto-cadence audit branch.

    Args:
        classification: SHORTCUT_LD_CLASSIFICATION[ld_row["id"]] resolved
            BEFORE this call (integer row id; grep anchor: `SHORTCUT_LD_CLASSIFICATION.get(ld_id)`). NEVER read from ld_row
            directly — the row does not carry classification as a Directus
            column.
        ld_row: the Directus REST payload (fields: id, key, date_locked,
            review_cadence, next_review_date, last_reviewed_date, ...).
    """
    if classification != "PERIODIC":
        return False  # caller already classified non-PERIODIC
    cadence = ld_row.get("review_cadence")
    # NULL is INVALID for PERIODIC — see §B2; caller MUST pre-check or
    # this helper returns False (and a separate finding fires).
    if cadence is None:
        return False
    if cadence in ("none", "event-driven"):
        return False  # documented opt-outs (still valid)
    return True  # cadence ∈ {monthly, quarterly, semi-annually, annually}
```

The two-arg form makes the source-of-classification explicit to callers — there is no `ld.get("classification")` line that could be misread.

**At call sites:** the audit loop computes classification ONCE from the registry, passes both args:

```python
# v3-D round-4 HIGH-2 fix: registry keyed by ld_id (integer), not ld["key"]
# (string). Live convention grep anchor: `SHORTCUT_LD_CLASSIFICATION.get(ld_id)`.
for ld in shortcut_ld_rows:
    ld_id = ld["id"]  # integer Directus row id
    classification = SHORTCUT_LD_CLASSIFICATION.get(ld_id, "UNCLASSIFIED")
    ld["_classification"] = classification  # stamping per (a) above
    # ... existing UNCLASSIFIED warning per v1 §3.2 ...
    if classification == "PERIODIC":
        # PERIODIC branch — all subsequent helpers receive classification
        # explicitly OR read ld["_classification"] (the stamped key).
        ...
```

**Why both conventions:** Some helpers prefer dict-only signatures (e.g., test fixtures that construct one ld dict and call several helpers). The stamped `_classification` key supports those without ambiguity. The two-arg signature supports callers that already have classification in scope and want zero ambiguity at the call site. Implementer picks per call site; both forms read the same data.

**Documentation rule (v3):** ANY future helper that branches on classification MUST either (i) take classification as an explicit argument, OR (ii) read `ld["_classification"]` (the stamped key, never `ld["classification"]`). Reading `ld.get("classification")` is forbidden — it would silently miss because Directus does NOT carry that column on `prod_locked_decisions`.

[CONFIDENCE: VERIFIED Cursor finding directly quoted; INFERRED stamping convention follows underscore-prefix pattern documented elsewhere in this codebase; VERIFIED two-arg helper signature is mechanically correct.]

### §B2 HIGH-2 fix — null cadence on PERIODIC is INVALID, not silent skip

**Problem (Cursor round-2 2026-05-09):** v2 §A4 lines 230-231 documents the audit predicate as `if cadence is None or cadence == "none" or cadence == "event-driven": return False` — i.e., NULL cadence on a PERIODIC row is treated as a documented opt-out. But v2 §A4 table also says `review_cadence = NULL` means "this row is not a PERIODIC LD." These two statements contradict for the (classification=PERIODIC, cadence=NULL) cell:

- Table-row interpretation: NULL means non-PERIODIC, and the classification check at the top of the predicate already filtered. So PERIODIC + NULL shouldn't occur.
- Predicate interpretation: NULL is a third opt-out value alongside `'none'` and `'event-driven'`.

The collision: if someone sets `classification = PERIODIC` (via the SHORTCUT_LD_CLASSIFICATION registry) but forgets to set `review_cadence`, the predicate skips silently — NO finding fires, the LD review never surfaces, the misconfiguration is invisible. v1 §5.2 explicitly mandates "LD 249 must have structured cadence" for every PERIODIC LD; silent-skip on NULL violates that intent.

**Fix (v3 §B2 — supersedes v2 §A4 audit predicate + table NULL row + v2 §4.2 cadence-None branch):**

Make (PERIODIC, NULL) INVALID and surface it. Updated audit predicate AND a separate up-front check that fires the invalid-config finding:

```python
# In the PERIODIC branch of weekly_preflight_audit.py
# (replacing v2 §4.2 lines 274-280):

if classification == "PERIODIC":
    cadence = ld.get("review_cadence")

    # §B2: NULL cadence on PERIODIC is INVALID — surface, do NOT skip silently.
    if cadence is None:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "issue": "PERIODIC_INVALID_CONFIGURATION",
            "classification": "PERIODIC",
            "severity": "critical",
            "message": (
                f"PERIODIC SHORTCUT LD id={ld_id} ({ld_key}) has "
                f"review_cadence=NULL — invalid for PERIODIC class. "
                f"Set review_cadence ∈ {{monthly, quarterly, semi-annually, "
                f"annually, none, event-driven}} per §A4 contract, then "
                f"re-run audit. NULL is reserved for non-PERIODIC LDs."
            ),
        })
        continue

    # Documented opt-outs — STILL valid skip values for PERIODIC.
    if cadence in ("none", "event-driven"):
        # (existing v2 behavior carries forward)
        continue

    # ... §A1 + §A2 + §A3 audit logic continues as in v2 ...
```

**Updated §A4 contract table (v3 supersedes v2):**

| classification | review_cadence | State name | Audit behavior |
|---|---|---|---|
| `RARE_NEVER` / `EVENT_DRIVEN` / any non-PERIODIC | `NULL` | NON_PERIODIC_DEFAULT | Audit ignores `review_cadence` entirely (classification check filters out). Valid + canonical. |
| `RARE_NEVER` / `EVENT_DRIVEN` / any non-PERIODIC | non-NULL (any value) | NON_PERIODIC_INCONSISTENT | Audit still skips (classification check filters out), but the value is never read. v3 NOTES: this state is harmless but inelegant; future linters may flag it. |
| `PERIODIC` | `NULL` | **PERIODIC_INVALID_CONFIGURATION** | **CRITICAL finding fires (per §B2). NEVER silent skip.** |
| `PERIODIC` | `'none'` | PERIODIC_OPT_OUT_NONE | Documented opt-out. Audit skips (no auto-cadence). Future v4 may add staleness check. |
| `PERIODIC` | `'event-driven'` | PERIODIC_OPT_OUT_EVENT_DRIVEN | Documented opt-out. Audit cannot auto-increment without external signal. |
| `PERIODIC` | `'monthly'` / `'quarterly'` / `'semi-annually'` / `'annually'` | PERIODIC_AUTO_CADENCE | Active audit path: §A1 calendar-aware increment + §A2 parse-failure handling + §A3 severity tiering. |

**Documentation rule (v3):** Any future code path consuming `review_cadence` MUST first establish classification. The (PERIODIC, NULL) cell is INVALID. Three documented opt-outs collapse to two: `'none'` and `'event-driven'`. NULL is NOT an opt-out for PERIODIC.

[CONFIDENCE: VERIFIED Cursor finding directly quoted; VERIFIED v1 §5.2 LD-249-must-have-cadence intent; INFERRED finding-payload format follows v2 §A2 pattern.]

### §B3 MEDIUM-1 fix — verified consumer-code citation + 3-step migration plan

**Problem (Cursor round-2 2026-05-09):** v2 §A3 line 200 asserted "the prod_blockers writer that fires on critical findings already keys off severity strings (per v1 §3.2 fact 5). The change from `'critical': True` (boolean) to `'severity': 'critical'` (string) aligns the PERIODIC branch with the existing severity-string convention used elsewhere in the audit; it is not a schema change." This claim was not verified against `weekly_preflight_audit.py` source — Cursor flagged that boolean → string severity migration "needs a fresh cite to actual code handling."

**Fix (v3 §B3 — supersedes v2 §A3 paragraph at line 200, replaces the assumption with verified citations from the actual consumer code):**

This v3 authoring session re-read `weekly_preflight_audit.py` (1887 lines, sha256 not pinned because file is not modified by this session). Severity field consumption sites in the SHORTCUT LD branch:

| Grep anchor | Code (verbatim) | Role |
|---|---|---|
| `is_critical = days_overdue >= 7` | `is_critical = days_overdue >= 7` | Boolean computation for PERIODIC overdue findings |
| `"critical": is_critical,` | `"critical": is_critical,` | **Boolean** field on PERIODIC overdue finding dict |
| `"critical": False,` | `"critical": False,` | **Boolean** field on PERIODIC approaching finding dict |
| `"critical": days_until_cap <= critical_threshold_days,` | `"critical": days_until_cap <= critical_threshold_days,` | **Boolean** field on RARE_NEVER/EVENT_DRIVEN cap-imminent finding dict |
| `f.get("critical") else "WARN"` | `tag = "CRITICAL" if f.get("critical") else "WARN"` | **READS boolean** for print tag |
| `if not f.get("critical")` | `if not f.get("critical"): continue` | **READS boolean** for prod_blockers blocker-creation filter |
| `"severity": "critical",` | `"severity": "critical",` | **String** — but on the OUTBOUND `prod_blockers` POST payload, NOT on the finding dict. This is the prod_blockers TABLE column field name, not the finding-dict consumption pattern. |

**Verified state (correcting v2):** v2's claim that "the existing blocker-creation logic ... already keys off severity strings" is **INACCURATE** for the finding-dict layer. The finding dict uses BOOLEAN `"critical": bool`. The grep anchor `"severity": "critical",` is the prod_blockers REST payload field (table column), separate from the finding-dict shape.

**3-step migration plan (v3 — supersedes v2's "not a schema change" claim):**

The boolean → string severity change DOES require code edits, NOT just a schema or terminology shift. v3 documents an explicit 3-step migration:

**Step 1 (additive — no consumer changes):** During Phase B, the PERIODIC branch produces finding dicts with BOTH fields populated:

```python
findings.append({
    "ld_id": ld_id, "key": ld_key,
    "classification": "PERIODIC",
    # ...
    "critical": is_critical,            # boolean — for back-compat with `f.get("critical")` consumers
    "severity": "critical" if is_critical else "warn",  # string — new canonical field; lowercase "warn" preserves v2 print-tag parity per v3-E MEDIUM-3
    "message": ...,
})
```

The existing `f.get("critical")` consumer anchors continue reading the boolean field — works unchanged. Step 1 alone is mechanically safe and all v2's audit-path improvements (calendar-aware cadence, parse-failure handling, severity tiering) ship.

**Step 2 (consumer migration — same Phase B PR or follow-up):** Update the two consumer sites to read the string field. **v3-E MEDIUM-3 parity decision (2026-05-09):** preserve the `WARN` print-tag string verbatim across the migration to keep logs/screenshots/grep-anchors/tests stable. the v2-old print-tag anchor emitted uppercase `WARN`; the v3 string-severity field uses lowercase `"warn"` (NOT `"warning"`) so that `.upper()` round-trips to `"WARN"`. This is intentional — using `"warning"` would silently rename the print tag from `WARN` to `WARNING` and break any downstream log-grep / screenshot-diff tooling. The Step 1 finding-dict producer at §B3 emits `"severity": "critical" if is_critical else "warn"` (lowercase) for the same parity reason; consumers in `prod_blockers` POST payload (`"severity": "critical",` anchor) continue to use the canonical `"critical"` / `"warning"` enum strings — those are a separate REST-payload schema and are NOT part of the in-memory finding-dict shape under migration here.

```python
# v2-old grep anchor: tag = "CRITICAL" if f.get("critical") else "WARN"
# v3-new (v3-E MEDIUM-3 parity refresh — uses lowercase "warn" so .upper() == "WARN" preserves the v2 tag verbatim):
tag = (f.get("severity") or ("critical" if f.get("critical") else "warn")).upper()

# v2-old grep anchor: if not f.get("critical"): continue
# v3-new:
if (f.get("severity") or ("critical" if f.get("critical") else "warn")) != "critical":
    continue
```

The `or` fallback preserves back-compat with any pre-Step-1 finding dict shape (e.g., the RARE_NEVER/EVENT_DRIVEN cap-imminent branch anchored by `days_until_cap <= critical_threshold_days` if it has not been migrated yet). **v3-E parity note:** if Phase B implementer DOES choose `"warning"` instead of `"warn"` for the string field, that is a deliberate rename and MUST be documented in the Phase B closeout LD with explicit log-grep/screenshot-diff impact assessment — it is NOT the default v3 path.

**Step 3 (cleanup — separate PR after Step 2 lands):** Once all finding-producing branches emit `severity` strings, drop boolean `"critical"` from finding dicts AND drop the fallback in `f.get("critical")` readers. Net result: one canonical severity field across all SHORTCUT LD finding shapes.

**Recommended Phase B execution:** Step 1 (additive) is mandatory — it is what v2's pseudocode actually requires to ship safely. Step 2 is recommended in the same PR (small, mechanical, eliminates the fallback ambiguity). Step 3 deferred to a follow-up PR (cleanup; lower priority).

**Documentation rule (v3):** The `prod_blockers` schema column `severity` (a string enum: `critical`/`warning`/`info` — confirmed by the `"severity": "critical",` outbound-payload anchor) is UNCHANGED. The change is to the finding-dict shape (Python dict in audit memory), not the Directus schema. Step 1 is purely an in-memory dict change.

[CONFIDENCE: VERIFIED `weekly_preflight_audit.py` consumer grep anchors directly read this session; VERIFIED v2's "already keys off severity strings" assertion is INACCURATE; INFERRED 3-step migration is mechanically safe; ASSUMED the prod_blockers `severity` column accepts the strings at the outbound-payload anchor — it is outbound, not re-read.]

### §B4 MEDIUM-2 fix — explicit python-dateutil dependency requirement

**Problem (Cursor round-2 2026-05-09):** v2 §A1 line 94 asserted `python-dateutil` "is already a transitive dependency in this codebase (used by `requests`/`requests-toolbelt`/`directus-sdk` chains)." Cursor flagged this as environment-specific and unverified.

**Fix (v3 §B4 — supersedes v2 §A1 paragraph at line 94):**

This v3 authoring session verified:

- `Production/tools/requirements.txt` — the canonical CI install manifest (per LD `PRODUCTION_TOOLING_REQUIREMENTS_TXT_V1` per the file's own header) — contains exactly `PyYAML>=6.0` and `Pillow>=10.0`. **No python-dateutil entry.**
- `grep -rEn "from dateutil|import dateutil|python-dateutil|relativedelta" --include="*.py" --include="*.txt" Production/` returns ZERO matches across the entire Production/ tree. (v3-E LOW-1 portability refresh 2026-05-09: `-E` flag added for explicit extended-regex semantics — works on both BSD `grep` (macOS default) and GNU `grep`. The pre-v3-E form used `\|` alternation which silently behaves differently across BSD vs GNU defaults. With `-E`, the unescaped `|` is the canonical alternation operator on both platforms.)
- **No `pyproject.toml` exists anywhere in the project tree** (v3-D round-4 MEDIUM-1 broadened search; v3-E round-5 MEDIUM-1 portability refresh — the v3-D command embedded a machine-specific absolute path that would not reproduce on other clones/CI/worktrees, so v3-E rewrites it as a portable repo-root-anchored form): from project root, run `find . -name pyproject.toml -not -path '*/node_modules/*' -not -path '*/.deploy_backups/*' -not -path '*/.git/*'` — returns ZERO results [VERIFIED 2026-05-09 in v3-D session under the absolute-path form; v3-E re-verified the equivalent `.`-anchored form returns the same ZERO result on this machine]. Rationale: any clone path on a different machine, CI runner, or worktree should produce the same audit result; the absolute-path form created an apparent dependency on Kim's local Dropbox path. The v3-A claim used `find . -maxdepth 3` which v3-D round-4 Cursor flagged as too shallow for a global dependency-authority assertion. Broadened (and now portable) search confirms no PEP 621 / PEP 517 build config exists; `Production/tools/requirements.txt` is the canonical and only Python dependency manifest.

**v3 statement (replaces v2 §A1 line 94 paragraph):**

`python-dateutil` is NOT a current dependency of the Production tooling. It must be added explicitly as a Phase B prerequisite step.

**New Phase B0 prerequisite (v3 — see §8 amendment):**

```
Phase B0 (NEW v3 prerequisite):
  Add `python-dateutil>=2.8` to Production/tools/requirements.txt.
  CI will install on next workflow run via existing
  `pip install -r Production/tools/requirements.txt` step.
  Verification: after PR merges, the next CI run logs
  `Successfully installed python-dateutil-2.X.Y` in the install step.
```

The implementer MUST land Phase B0 in the same PR as the Phase B audit-logic update — running the audit before `python-dateutil` is on PYTHONPATH would produce `ImportError` at the new `from dateutil.relativedelta import relativedelta` line.

**Why python-dateutil and not a stdlib alternative:** v2 §A1 already documented this — calendar-aware month arithmetic via stdlib requires ~15 lines of boilerplate easy to get wrong on year-boundary + Feb-29 edges; `dateutil.relativedelta` is the canonical idiom. v3 does not re-litigate the choice; only the dependency-presence claim is corrected.

**Schema impact:** None. This is a tooling dependency add only.

[CONFIDENCE: VERIFIED `Production/tools/requirements.txt` contents directly read this session; VERIFIED `grep` returns no dateutil matches; INFERRED the CI install pipeline reads from `Production/tools/requirements.txt`; ASSUMED `python-dateutil>=2.8` is the appropriate floor (matches v2 §A1's documented version anchor).]

### §B5 MEDIUM-3 fix — `'none'` is PERIODIC-only opt-out, not RARE_NEVER/EVENT_DRIVEN default

**Problem (Cursor round-2 2026-05-09):** v2 §5.1 line 372 documents the `'none'` cadence value as: `n/a — no review surfacing (per §A4) | All RARE_NEVER and most EVENT_DRIVEN LDs`. This conflicts with v2 §A4: per §A4, RARE_NEVER and EVENT_DRIVEN LDs have `review_cadence = NULL`, NOT `'none'`. Readers may wrongly set `'none'` on non-PERIODIC rows, creating the (RARE_NEVER, 'none') ambiguous state.

**Fix (v3 §B5 — supersedes v2 §5.1 enum table 'none' row + 'event-driven' row):**

**Updated v3 §5.1 enum table (replaces v2 §5.1 enum table in full):**

| Value | Calendar-aware increment (v2/v3) | Common case | Allowed classification |
|---|---|---|---|
| `monthly` | `next_review_date += relativedelta(months=1)` | Operational safety reviews | PERIODIC only |
| `quarterly` | `next_review_date += relativedelta(months=3)` | LD 249 — identity platform | PERIODIC only |
| `semi-annually` | `next_review_date += relativedelta(months=6)` | Vendor pricing reviews | PERIODIC only |
| `annually` | `next_review_date += relativedelta(years=1)` | Annual cost reviews | PERIODIC only |
| `event-driven` | n/a — manual updates only (per §A4) | future CodeQL major-release LDs | **PERIODIC only** (rare; explicit non-calendar trigger) |
| `none` | n/a — no review surfacing (per §A4) | **Rare**: PERIODIC LD whose review is "when somebody asks" — taxonomy-bucket-only | **PERIODIC only** (explicit opt-out from automatic surfacing despite PERIODIC class) |
| **(NULL — column unset)** | n/a — column does not apply | All RARE_NEVER, all EVENT_DRIVEN, all non-SHORTCUT LDs | **non-PERIODIC only** (NULL is INVALID for PERIODIC — see §B2) |

**Cross-reference (v3):** `'none'` and `'event-driven'` are PERIODIC-only opt-outs. NULL is the canonical non-PERIODIC default. RARE_NEVER and EVENT_DRIVEN LDs MUST set `review_cadence = NULL`, NEVER `'none'`. See §A4 (v3-amended) for the full state contract; the (PERIODIC, NULL) cell is INVALID per §B2.

**Common-case examples (v3 supersedes v2 §5.1 column):**

- LD 249 (PERIODIC, quarterly identity-platform review) → `review_cadence = 'quarterly'`.
- A hypothetical RARE_NEVER LD (one-shot policy lock) → `review_cadence = NULL`. Setting `'none'` would be inconsistent.
- A hypothetical PERIODIC LD whose closure mechanism is "review when someone asks" → `review_cadence = 'none'`. NOT NULL — NULL would trip the §B2 invalid-config finding.
- A hypothetical PERIODIC LD anchored to "next CodeQL major release" → `review_cadence = 'event-driven'`. NULL would trip §B2; calendar values would mismatch the trigger.

[CONFIDENCE: VERIFIED Cursor finding directly quoted; VERIFIED v2 §A4 documents `'none'` and `'event-driven'` as PERIODIC opt-outs (lines 217-218); INFERRED the (RARE_NEVER, 'none') state has never been authored — no live LD; v3 corrects the documentation surface to prevent future drift.]

---

## §A v2 surgical amendments — STATUS NOTES (preserved by reference; v3 amendments noted inline)

The 4 v2 surgical amendments (v2 §A1–§A4) are preserved by reference. v3's amendments to those sections are inline above (§B1–§B5). For convenience:

- **v2 §A1** (calendar-aware cadence arithmetic): preserved; v3 §B4 corrects the "already transitive" claim only — the calendar-aware-arithmetic decision STANDS.
- **v2 §A2** (bounded parse-failure handling): preserved verbatim; no v3 change. (v3-C confirms: A2 is the only §A section with NO v3 amendment.)
- **v2 §A3** (severity from resolution semantics): preserved as design intent; v3 §B3 replaces the "already keys off severity strings" assumption with a verified citation + 3-step migration plan.
- **v2 §A4** (review_cadence 3-state contract): v3 §B1 + §B2 amend — classification source pinned (§B1), NULL on PERIODIC is INVALID not opt-out (§B2), audit predicate signature updated (§B1).

---

## §1 Scope (preserved verbatim from v2 → v1)

(All v2 §1 / v1 §1 content preserved by reference; no in-scope/out-of-scope changes from v3 amendments.)

## §2 Background (preserved verbatim from v2 → v1)

## §3 Current System (preserved verbatim from v2 → v1)

(v3 adds: `weekly_preflight_audit.py` line citations 281, 289, 305, 372, 395, 404, 434 are now VERIFIED in this session — see §B3.)

## §4 Proposed Design (v3-amended)

### §4.1 Schema migration (v3-amended — see §B2 for NULL on PERIODIC = INVALID)

The 3 fields and types remain as v2 §4.1 specified. v3 sharpens the `review_cadence` semantic for the (PERIODIC, NULL) cell:

| Field | Type | Nullable | Semantic (v3) |
|---|---|---|---|
| `review_cadence` | string (enum: `monthly`, `quarterly`, `semi-annually`, `annually`, `event-driven`, `none`) | YES | NULL = non-PERIODIC default (state NON_PERIODIC_DEFAULT). NULL on a PERIODIC LD is **INVALID** (state PERIODIC_INVALID_CONFIGURATION — fires CRITICAL finding per §B2). `'none'` and `'event-driven'` are PERIODIC-only opt-outs. The 4 calendar values are PERIODIC auto-cadence. See §B2 contract table. |
| `next_review_date` | date | YES | Calendar date when the next review fires. Required for PERIODIC LDs whose `review_cadence ∉ {NULL, 'none'}`; audit-enforced (per v2 §A2 + §B2) rather than DB-enforced. |
| `last_reviewed_date` | date | YES | Last calendar date a review was conducted. Initially NULL; set on first review. Used by audit consistency-check (deferred to v4 per v1 §5.4). |

Migration mechanics unchanged from v1 §4.1 + v2 §4.1.

### §4.2 Audit logic — PERIODIC branch (v3-amended — supersedes v2 §4.2 lines 271-345 audit pseudocode block)

The v2 stitched pseudocode is updated to incorporate §B1 (classification source) + §B2 (NULL invalid-config) + §B3 Step 1 (string severity field added alongside boolean).

```python
# In check_shortcut_ld_closure_dates(), after existing classification lookup:
# Note (§B1, v3-D round-4 HIGH-2 pin): `classification` here is the value
# from SHORTCUT_LD_CLASSIFICATION[ld["id"]] (integer row id, per live
# convention anchored by `SHORTCUT_LD_CLASSIFICATION.get(ld_id)`), resolved by the caller,
# NOT ld.get("classification"). The row may also carry ld["_classification"]
# stamped at load time per §B1(a).

if classification == "PERIODIC":
    cadence = ld.get("review_cadence")

    # §B2: NULL cadence on PERIODIC is INVALID — surface, do NOT skip.
    if cadence is None:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "issue": "PERIODIC_INVALID_CONFIGURATION",
            "critical": True,                  # §B3 Step 1: keep boolean
            "severity": "critical",            # §B3 Step 1: add string
            "message": (
                f"PERIODIC SHORTCUT LD id={ld_id} ({ld_key}) has "
                f"review_cadence=NULL — invalid for PERIODIC class. "
                f"Set review_cadence ∈ {{monthly, quarterly, "
                f"semi-annually, annually, none, event-driven}} per "
                f"§A4 contract, then re-run audit."
            ),
        })
        continue

    # Documented opt-outs — STILL valid skip values for PERIODIC.
    if cadence in ("none", "event-driven"):
        continue

    # §A1 + §A2: required-field check + parse-failure bounded finding.
    next_review = ld.get("next_review_date")
    if not next_review:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "issue": "PERIODIC_MISSING_NEXT_REVIEW_DATE",
            "critical": True,                  # §B3 Step 1
            "severity": "critical",            # §B3 Step 1
            "message": (
                f"PERIODIC SHORTCUT LD id={ld_id} missing required "
                f"next_review_date. Set this field before next audit run."
            ),
        })
        continue

    try:
        next_review_date = parse_date(next_review)
    except (ValueError, TypeError) as e:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "issue": "PERIODIC_INVALID_NEXT_REVIEW_DATE",
            "critical": True,                  # §B3 Step 1
            "severity": "critical",            # §B3 Step 1
            "value": next_review,
            "error": str(e),
            "message": (
                f"PERIODIC SHORTCUT LD id={ld_id} has unparseable "
                f"next_review_date={next_review!r}: {e!s}. Audit cannot "
                f"compute days-until-review; fix the field then re-run."
            ),
        })
        continue

    days_until_review = (next_review_date - today).days

    # §A3: severity computed from days-overdue, matching §5.3 resolution.
    if days_until_review <= 0:
        days_overdue = abs(days_until_review)
        is_critical = days_overdue >= 7
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "next_review": next_review_date.isoformat(),
            "days_overdue": days_overdue,
            "critical": is_critical,           # §B3 Step 1: keep boolean
            "severity": "critical" if is_critical else "warn",  # §B3 Step 1 — v3-E MEDIUM-3 parity: lowercase "warn" preserves v2 print-tag
            "message": (
                f"PERIODIC LD {ld_key} review OVERDUE by {days_overdue} "
                f"days [{('CRITICAL' if is_critical else 'WARN')}]. "
                f"Next-review-date was {next_review_date.isoformat()}."
            ),
        })
    elif days_until_review <= 7:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "next_review": next_review_date.isoformat(),
            "days_until_review": days_until_review,
            "critical": False,                 # §B3 Step 1
            "severity": "warn",                # §B3 Step 1 — v3-E MEDIUM-3 parity: lowercase "warn"
            "message": (
                f"PERIODIC LD {ld_key} review due in {days_until_review} "
                f"days ({next_review_date.isoformat()})."
            ),
        })
    # else: silent — review is far enough out that no surfacing is needed.
    continue
```

The two consumer sites anchored by `f.get("critical")` (print tag + blocker filter) MAY remain on the boolean field for Step 1 ship; Step 2 migration to `f.get("severity") == "critical"` happens in the same PR (recommended) or a follow-up (per §B3).

### §4.3 Cap-selection refactor (preserved verbatim from v2 → v1)

### §4.4 Roadmap §1.6 update (preserved verbatim from v2 → v1)

### §4.5 No new LD class for non-SHORTCUT LDs (preserved verbatim from v2 → v1)

---

## §5 Open Decisions — Dual-Opus Debate (v3-amended on §5.1)

### §5.1 review_cadence enum (v3-amended — `'none'` corrected; classification column added)

Replaced wholesale by §B5 v3 enum table above. The Resolution from v1 §5.1 (ENUM with structured-cadence-as-string) stands. v3's amendments to the increment-rule + classification-allowed columns close the wording-conflict surface.

[CONFIDENCE: VERIFIED Advocate position carried from v1; VERIFIED Counter from v1's blocker-deduplication argument; VERIFIED `relativedelta` calendar-aware semantics; VERIFIED Cursor MEDIUM-3 finding directly quoted.]

### §5.2 next_review_date required-vs-optional (preserved verbatim from v2 → v1)

### §5.3 Past-due severity (preserved as v2 baseline + AMENDED BELOW: see §B3 — v3-C note: v2's "already keys off severity strings" claim was INACCURATE; v3 §B3 supersedes with verified consumer-code grep anchors (`is_critical = days_overdue >= 7`, `"critical": is_critical`, `"critical": False`, `days_until_cap <= critical_threshold_days`, `f.get("critical")`, and `"severity": "critical"`) + 3-step boolean→string migration plan. This section is behavior-affecting, not verbatim-preserved.)

### §5.4 Last-reviewed consistency check (preserved verbatim from v2 → v1 — deferred to v4)

### §5.5 Severity reuse (preserved verbatim from v2 → v1)

---

## §6 Dual-Opus Meta-Debate (preserved verbatim from v2 → v1)

---

## §7 Migration Cohort (preserved as v2 baseline + AMENDED BELOW: see §B4 + §8 — Phase B0 prerequisite (`python-dateutil>=2.8`) MUST land before §A1's `relativedelta` import; v3-C clarifies this is a behavior-affecting amendment, not a verbatim preservation)

LD 249 example calendar dates unchanged from v2. v3 notes only: the `relativedelta(months=3)` import requires the §B4 Phase B0 prerequisite (`python-dateutil>=2.8` added to `Production/tools/requirements.txt`) before Phase B audit-logic ships.

---

## §8 Implementation Phases (v3-amended — adds Phase B0 prerequisite)

v2 Phase A → Phase G preserved by reference. v3 INSERTS Phase B0 BEFORE Phase B:

```
Phase B0 (NEW v3 — dependency prerequisite):
  Touch only: Production/tools/requirements.txt
  Edit: append `python-dateutil>=2.8` after the Pillow line.
  Verification: PR diff is one-line addition; CI run logs
    `Successfully installed python-dateutil-2.X.Y` on next workflow.
  Rollback: revert the one-line addition.
  Estimated time: < 1 minute.
  Approver: Kim.
```

Phase B (audit-logic update) MUST land in the same PR as B0, or strictly after B0 has merged. Running the v3 audit pseudocode without `python-dateutil` produces `ImportError: No module named 'dateutil.relativedelta'`.

All other v2 Phase content preserved.

---

## §9 Risk Assessment (v3-amended — 5 new risk rows)

v2 risks 1-13 preserved verbatim. v3 appends 5 new risks for the round-2 defect classes:

| # | Risk (v3 additions) | Severity | Mitigation |
|---|---|---|---|
| 14 | **Classification-source mis-read** — implementer copies `is_audit_eligible_periodic_row` and writes `ld.get("classification")`, silently disabling audit for every PERIODIC LD because that key does not exist on the Directus row | HIGH | §B1 two-arg helper signature is the canonical form. PR review checks for any `ld.get("classification")` or `ld["classification"]` pattern under `Production/scripts/weekly_preflight_audit.py`; if found, fail review. Smoke test: insert a PERIODIC LD row WITHOUT `classification` REST field, assert audit still classifies it correctly via `SHORTCUT_LD_CLASSIFICATION[ld["id"]]` registry (integer row id; live convention anchored by `SHORTCUT_LD_CLASSIFICATION.get(ld_id)`; v3-F line-citation refresh). |
| 15 | **NULL-cadence silent skip regression** — implementer keeps the v2 `if cadence is None: continue` early-return and never adds the §B2 invalid-config finding | HIGH | §B2 pseudocode is the single source of truth. Smoke test: insert a row with `classification=PERIODIC AND review_cadence=NULL`, assert audit emits `PERIODIC_INVALID_CONFIGURATION` finding (severity=critical), not silent. |
| 16 | **Severity-field migration partial** — implementer ships Step 1 (additive) but skips Step 2 (consumer migration), leaving boolean+string both in flight for >1 release | MEDIUM | §B3 Step 2 marked "recommended in same PR as Step 1." If deferred, file a follow-up issue/blocker referencing this row. Step 3 (cleanup) explicitly deferred to a separate PR. |
| 17 | **python-dateutil dependency missed** — implementer ships v3 Phase B audit-logic without v3 Phase B0 prerequisite, audit ImportErrors at first run | MEDIUM | §B4 Phase B0 lands in same PR as Phase B (or strictly before). PR description checklist asks: "Phase B0 added python-dateutil>=2.8 to requirements.txt? [verified]" |
| 18 | **`'none'` mis-applied to non-PERIODIC LDs** — future LD authors set `review_cadence='none'` on a RARE_NEVER row (because v2 §5.1 listed it as their "common case") | LOW | §B5 v3 enum table corrects the wording surface. Future LD-author-onboarding doc should reference the §A4 contract table (state name column) when explaining the field. |

---

## §10 Testing Plan (v2 §10 + new §10.7 round-2 regression tests)

(All v2 §10.1–§10.6 preserved.)

### §10.7 [v3 NEW] Round-2 regression tests

To exercise the 5 v3 defect classes specifically:

- **HIGH-1 classification source:** insert a PERIODIC LD row with NO `classification` REST field (which is the actual Directus state — no such column exists). Assert audit correctly classifies via registry lookup AND processes the row through the PERIODIC branch. Negative test: any code path reading `ld.get("classification")` directly should fail PR review (lint or grep CI check).
- **HIGH-2 null cadence on PERIODIC:** inject `classification=PERIODIC AND review_cadence=NULL` row. Assert audit emits `PERIODIC_INVALID_CONFIGURATION` finding with `severity="critical"`, NOT silent skip. Verify the finding propagates to a `prod_blockers` POST per the line-404 filter (after Step 1 ships).
- **MEDIUM-1 severity field shape:** assert every PERIODIC finding dict carries BOTH `"critical": bool` AND `"severity": "critical"|"warn"` (Step 1 invariant; v3-E MEDIUM-3 parity — lowercase `"warn"` not `"warning"`). Assert lines 395 + 404 (consumer code) work unchanged when reading boolean — back-compat. Optional Step 2 test: with consumer-code migration, assert reader works against `severity` string only and `.upper()` yields `"WARN"` (preserves v2 print-tag verbatim).
- **MEDIUM-2 dependency check:** in CI, assert `python-dateutil` is importable BEFORE running the audit (`python -c "from dateutil.relativedelta import relativedelta"` returns 0 exit code).
- **MEDIUM-3 `'none'` placement:** assert no LD in `prod_locked_decisions` has the (classification ≠ PERIODIC, review_cadence='none') combination. Survey query (run once at v3 land time) — if any extant rows match, file a clean-up blocker.

---

## §11 Reference Index (v3-amended — adds v2 baseline + audit-script line citations + requirements.txt)

### Source documents read this session (v3 authoring 2026-05-09)

| Document | Purpose | Verification |
|---|---|---|
| `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` | Spec under amendment; direct predecessor | sha256 `86343950847942ca0b20691cfe652bb4096732dd7c6b46845f95b382eac69175` [VERIFIED 2026-05-09 via shasum -a 256, 530 lines] |
| `Production/scripts/weekly_preflight_audit.py` | MEDIUM-1 verified consumer code (READ ONLY) | 1887 lines [VERIFIED 2026-05-09]. v3-F replaces load-bearing line citations with grep anchors: `grep -nE 'def check_shortcut_ld_closure_dates|SHORTCUT_LD_CLASSIFICATION\.get\(ld_id\)|for ld in rows:|f\.get("critical")|f\.get("severity")|"critical": is_critical|"critical": False|days_until_cap <= critical_threshold_days|"severity": "critical"' Production/scripts/weekly_preflight_audit.py`. These anchors cover §B1 loader/stamping, §B3 severity consumers/producers, and §A4-linked audit pseudocode without relying on mutable line positions. |
| `Production/tools/requirements.txt` | MEDIUM-2 verified dependency manifest (READ ONLY) | 20 lines; contains PyYAML>=6.0 + Pillow>=10.0 only; NO python-dateutil [VERIFIED 2026-05-09] |
| Cursor 2026-05-09 round-2 6-finding review (2 HIGH + 3 MEDIUM + 1 LOW closed via §14 placeholder) | v3 driver | Verbatim quotations carried in §B1–§B5 + §14 |
| Cursor 2026-05-09 round-3 5-finding review (HIGH-1 count math + HIGH-2 preserved-verbatim tightening + MEDIUM-1 §14 trade-off + MEDIUM-2 stamping pin + LOW rolled into HIGH-1) | v3-C driver | Verbatim quotations carried in §0.1 v3-C row |

### LDs cited (v3)

- v2 §11 LDs cited carry forward verbatim (LD-615 + v1's 199, 200, 201, 249, 263, 561, 566, 568).
- **NEW v3-A self-reference LD:** `PERIODIC_CLASS_TECH_SPEC_V3_CLASSIFICATION_NULL_CADENCE_FIX_V1` — **LD-620** (v3-A round-2 surgical fixes; filed 2026-05-09 via `lock_decision.py lock`; cache rebuilt at filing time; same authority as §0 banner `v3-A filed LD-620`). Predecessors: none (this is v3-A, the original v3 LD). [v3-E MEDIUM-2 parity refresh — bullet rewritten to match v3-B/v3-C/v3-D format with explicit filed-date + cache-rebuild + predecessors fields.]
- **NEW v3-B self-reference LD:** `PERIODIC_CLASS_TECH_SPEC_V3_B_LOW_CONSISTENCY_V1` — **LD-625** (filed 2026-05-09 via `lock_decision.py lock`; cache rebuilt at filing time). Predecessors: LD-620 (v3-A original). [v3-E MEDIUM-2 parity refresh — v3-B bullet was missing from this list pre-v3-E despite v3-B being filed under LD-625; added for completeness.]
- **NEW v3-C self-reference LD:** `PERIODIC_CLASS_TECH_SPEC_V3_C_ROUND_3_FIXES_V1` — **LD-635** (filed 2026-05-09 via `lock_decision.py lock`; cache rebuilt to 596 active LDs). Predecessors: LD-620 (v3-A original), LD-625 (v3-B cleanup).
- **NEW v3-D self-reference LD:** `PERIODIC_CLASS_TECH_SPEC_V3_D_ROUND_4_FIXES_V1` — **LD-640** (filed 2026-05-09 via `lock_decision.py lock`; cache rebuilt to 601 active LDs). Predecessors: LD-620 (v3-A original), LD-625 (v3-B cleanup), LD-635 (v3-C cleanup).
- **NEW v3-E self-reference LD:** `PERIODIC_CLASS_TECH_SPEC_V3_E_ROUND_5_FIXES_V1` — **LD-645** (filed 2026-05-09 via `lock_decision.py lock`; cache rebuilt to 606 active LDs). Predecessors: LD-620 (v3-A original), LD-625 (v3-B cleanup), LD-635 (v3-C cleanup), LD-640 (v3-D cleanup).

### Specs cited as precedent (v3)

- `PERIODIC_CLASS_TECH_SPEC_v2.md` — direct predecessor; structure mirrored.
- `PERIODIC_CLASS_TECH_SPEC_v1.md` — historical baseline; structure carried.

### Constants and identifiers (v3 additions)

- `_classification` (new dict-stamped key, §B1 — convention: underscore prefix marks code-derived keys, distinct from any future REST `classification` column).
- `is_audit_eligible_periodic_row(classification, ld_row)` (canonical predicate signature, §B1).
- `PERIODIC_INVALID_CONFIGURATION` (new finding key, §B2).

---

## §12 Changelog

- **v1 (2026-05-07):** Original DESIGN-ONLY spec; 5 dual-Opus debates resolved; 1 LD migration cohort; awaiting Kim authorization.
- **v2-A (2026-05-09):** 4-defect surgical amendment (HIGH×2, MEDIUM×2): calendar-aware cadence (§A1), parse-failure handling (§A2), severity from resolution (§A3), `review_cadence` 3-state contract (§A4). LD-615.
- **v3 (2026-05-09):** 6-finding round-2 surgical amendment (2 HIGH + 3 MEDIUM + 1 LOW; LOW closed via §14 placeholder):
  - **HIGH-1** Classification source pinned — `_classification` stamping convention + two-arg helper signature (§B1).
  - **HIGH-2** NULL cadence on PERIODIC is INVALID — fires `PERIODIC_INVALID_CONFIGURATION` finding instead of silent skip (§B2).
  - **MEDIUM-1** Verified consumer-code grep anchors from `weekly_preflight_audit.py` (`is_critical = days_overdue >= 7`, `"critical": is_critical`, `"critical": False`, `days_until_cap <= critical_threshold_days`, `f.get("critical")`, `"severity": "critical"`) replace v2's INFERRED claim; 3-step boolean→string severity migration plan (§B3).
  - **MEDIUM-2** "Already transitive" claim dropped; explicit `python-dateutil>=2.8` requirement; new Phase B0 prerequisite (§B4).
  - **MEDIUM-3** `'none'` enum row clarified: PERIODIC-only opt-out, NOT default for RARE_NEVER/EVENT_DRIVEN; v3 §5.1 enum table corrected (§B5).
  - **LOW closed via §14 placeholder:** §14 skeleton gap (§13 → §15 jump) closed by adding a §14 placeholder section pointing to the actual Reference Index at §11; deliberately not renumbered to preserve v1/v2/handoff cross-references; future v4 may renumber as structural pass.
  - 5 new risk rows (#14–#18) for the 5 round-2 defect classes.
  - Sections preserved verbatim from v2 → v1: see §0.1 v3-C section-status taxonomy for the precise three-bucket split (PRESERVED VERBATIM / PRESERVED AS V2 BASELINE + AMENDED BELOW / NEW IN V3). v3-A's broad "preserved verbatim" framing was tightened by v3-C round-3 HIGH-2 fix.
- **v3-C (2026-05-09):** Cursor round-3 cleanup. 5 doc-quality findings closed: HIGH-1 count-math standardization to "6 findings closed (2 HIGH + 3 MEDIUM + 1 LOW)" everywhere; HIGH-2 section-status taxonomy split (PRESERVED VERBATIM vs. PRESERVED AS V2 BASELINE + AMENDED BELOW vs. NEW IN V3) plus per-section header tightening for behavior-changing sections (§7, §5.3, §A2); MEDIUM-1 §14 trade-off rationale documented (renumber rejected for 3 reasons); MEDIUM-2 `_classification` stamping pinned to `weekly_preflight_audit.py` grep anchors `def check_shortcut_ld_closure_dates`, `client.get("prod_locked_decisions"`, `for ld in rows:`, `SHORTCUT_LD_CLASSIFICATION.get(ld_id)`, and stamping insertion after the `if classification is None` short-circuit, and registry-key correction (ld_id integer, not ld["key"]); LOW rolled into HIGH-1. NO behavior changes, NO new content sections beyond doc tightening; v3 is still the canonical spec, v3-C is a sub-version sweep. LD `PERIODIC_CLASS_TECH_SPEC_V3_C_ROUND_3_FIXES_V1` (predecessors LD-620 v3-A, LD-625 v3-B).
- **v3-D (2026-05-09):** Cursor round-4 cleanup. 4 findings closed including ONE real pseudocode bug v3-C documented but did not actually fix: HIGH-1 GOVERNANCE-AUTHORING reframing (replaces "STANDARD/no-mutation" wording at lines 8/27/34 with explicit governance-authoring declaration noting LD filings + activity_log POSTs ARE the canonical deliverables per Rule 35 / DS-29); HIGH-2 ld_id pseudocode pin (rewrites pseudocode at lines 133/148/172/417 plus §9 risk row #14 mitigation text from `ld["key"]` to `ld_id = ld["id"]` integer pattern, mirroring live convention at `SHORTCUT_LD_CLASSIFICATION.get(ld_id)` — closes the gap v3-C left where prose said "use ld_id" but pseudocode still showed `ld["key"]`); MEDIUM-1 broadened pyproject.toml absence search (replaces shallow `find . -maxdepth 3` at line 319 with project-wide find excluding node_modules/.deploy_backups/.git, ZERO results VERIFIED); MEDIUM-2 closure-type reframing (lines 3/43/714 — distinguishes 5 substantive defect closures from v3-A vs. 1 documentation-structure closure from v3-B; bare "6 findings" backward-compatible). NO behavior changes; v3 still canonical; v3-D is a sub-version sweep. LD `PERIODIC_CLASS_TECH_SPEC_V3_D_ROUND_4_FIXES_V1` (predecessors LD-620 v3-A, LD-625 v3-B, LD-635 v3-C).
- **v3-E (2026-05-09):** Cursor round-5 cleanup. 6 findings closed (1 HIGH + 3 MEDIUM + 2 LOW): HIGH line citation refresh (v3-D's §0.1 hard line citations were stale across multiple cells — risk row #14 at "line 582" was actually 596-599; pseudocode line cites at 125-133/148/172/417 had drifted to 141-142/153/186-187/431-435; pyproject search at "line 319" had drifted to 334; §11 LD-bullet block cited as "lines 621-623" had drifted to 637-639; §19 authorship trail cited as "line 714" was blank with §19 starting at line 727 — all converted to section-ref form for resilience to future edits, and v3-E's own changelog uses ZERO hard line numbers); MEDIUM-1 portable find (rewrites §B4 absence-search command from machine-specific absolute path to portable repo-root form `find . -name pyproject.toml -not -path '*/node_modules/*' -not -path '*/.deploy_backups/*' -not -path '*/.git/*'` with explicit "run from project root" note); MEDIUM-2 §11 LD-bullet parity refresh (v3-A bullet rewritten to match v3-B/v3-C/v3-D detail format with `filed 2026-05-09 via lock_decision.py lock; cache rebuilt at filing time; predecessors: none`; new v3-B bullet inserted with LD-625 — was missing despite v3-B being filed); MEDIUM-3 WARN parity decision (Step 2 consumer migration uses lowercase `"warn"` not `"warning"` so `.upper()` preserves v2 print-tag verbatim — protects log-grep / screenshot-diff tooling; deliberate rename to `"warning"` MUST be documented in Phase B closeout LD if implementer chooses that path); LOW-1 grep portability (`grep -rn "from dateutil\\|..."` → `grep -rEn "from dateutil|..."` for BSD/GNU parity); LOW-2 re-verify note (§11 Reference Index gains explicit re-verify-on-edit recipe for `weekly_preflight_audit.py` line citations, marking them as point-in-time snapshots not load-bearing for behavior). One disagreement logged with Cursor MEDIUM-2 (Cursor quoted "LD id assigned at filing time" string that did not appear in on-disk spec; underlying parity concern was still valid and applied). NO behavior changes; v3 still canonical; v3-E is a sub-version sweep. LD `PERIODIC_CLASS_TECH_SPEC_V3_E_ROUND_5_FIXES_V1` — **LD-645** (predecessors LD-620 v3-A, LD-625 v3-B, LD-635 v3-C, LD-640 v3-D).

---

## §13 Audit Checklist (preserved verbatim from v2 → v1)

(v3 amendments are spec-only; no schema or code changes in this session.)

## §14 Reference Index pointer (placeholder — closes Cursor round-2 LOW finding)

In v1 this section number was occupied by "Reference Index (per zero-error-qa §16)". Starting in v2, the Reference Index moved to §11 to align with the broader spec template.

This §14 placeholder exists in v3 to (a) prevent broken cross-references in any v1-era checklist or handoff that cites "see §14" and (b) close the Cursor round-2 LOW finding flagging the §13 → §15 gap. **The actual Reference Index lives at v3 §11.** Citers updating v1-era references should rewrite "v1 §14" as "v3 §11" (or "v2 §11" if citing the v2 baseline).

For machine-readable cross-walk:

| Era | Section | Title |
|---|---|---|
| v1 | §14 | Reference Index (per zero-error-qa §16) |
| v2 | §11 | Reference Index (renumbered) |
| v3 | §11 | Reference Index (extended; v2 + audit-script lines + requirements.txt) |

### §14 v3-C trade-off documentation (round-3 MEDIUM-1 closure)

Cursor round-3 MEDIUM-1 (2026-05-09) flagged that the §14 placeholder fix introduces structural drift — i.e., the §13 → §14 placeholder → §15 sequence is a documentation patch, not a true structural renumbering. v3-C explicitly documents the trade-off rationale rather than letting the patch read as silently sub-optimal:

**Option considered: Full structural renumbering across v1 + v2 + v3.** This would close the §14 gap "properly" by shifting §15+ down to §14+ throughout the v3 spec.

**Option taken: §14 placeholder + cross-walk in §0.X.** Section numbers preserved; §14 documented as an intentional placeholder.

**Why the placeholder won (rationale, v3-C round-3):**
1. **Breaks historical v1 + v2 cross-references.** v1 §14 was "Reference Index"; v1 §15 was "Pre-Implementation Gates." Any external handoff, prior LD note, or downstream skill doc citing "v1 §15" would silently mis-resolve under a v3 renumbering. v1 + v2 are immutable artifacts (sha256-pinned); their cross-references are LOAD-BEARING.
2. **Balloons the v3 diff for cosmetic gain.** Renumbering §15 → §14, §16 → §15, §17 → §16, §18 → §17, §19 → §18 cascades through every §B/§A/§4–§13 cross-reference inside v3 itself ("see §15 below" → "see §14 below"). The diff becomes a renumbering pass, not a behavior-fix pass — which is precisely what `zero-error-qa` discipline DS-15 (authoring discipline) and DS-19 (deviation logging) flag as a maintenance hazard mid-amendment.
3. **Long-term maintenance friction outweighs reader friction.** A reader scanning §13 → §14 placeholder → §15 sees a one-paragraph explanation and proceeds. A future amendment author trying to reconcile v1 + v2 + v3 cross-references after a renumber faces a multi-document untangle.

**Acknowledged compromise:** Reader friction is non-zero. The §14 placeholder + cross-walk in this section IS the trade-off. It is not silently sub-optimal — it is explicitly chosen.

**Future v4 hook:** A future v4 (if produced) MAY renumber as part of a structural pass — but only if v4 is also a major-version cut (i.e., not a surgical amendment), and only if every external citer can be updated in the same release. v4 renumbering is NOT a goal in itself; the placeholder is stable indefinitely.

**Closure marker:** Cursor round-3 MEDIUM-1 closed by this paragraph; no further v3 amendment required for this finding.

## §15 Pre-Implementation Gates (preserved verbatim from v2 → v1; v3 adds: Kim approves the 5 v3 surgical fixes per §B1–§B5 before Phase B implementation)

## §16 Recommended Sequence (preserved verbatim from v2 → v1; v3 inserts Phase B0 before Phase B per §8 amendment)

## §17 Confidence Annotations Sweep (v3 additions)

| Section | Predominant tag | Notes |
|---|---|---|
| §B1 (classification source) | [VERIFIED] | Cursor finding directly quoted; v2 §A4 line 227 directly cited; SHORTCUT_LD_CLASSIFICATION registry pattern carried from v1 §3.2 |
| §B2 (NULL invalid for PERIODIC) | [VERIFIED] | Cursor finding directly quoted; v2 §A4 contradiction directly cited; v1 §5.2 LD-249-must-have-cadence intent referenced |
| §B3 (severity migration) | [VERIFIED] | `weekly_preflight_audit.py` grep anchors for `f.get("critical")`, `"critical": is_critical`, `"critical": False`, `days_until_cap <= critical_threshold_days`, and `"severity": "critical"` directly read this session — replaces v2's INFERRED claim |
| §B4 (python-dateutil dep) | [VERIFIED] | `Production/tools/requirements.txt` directly read; `grep -rEn` over Production/ returns zero matches (v3-E LOW-1 `-E` portability refresh); replaces v2's "already transitive" assumption |
| §B5 (`'none'` placement) | [VERIFIED] | Cursor finding directly quoted; v2 §A4 vs §5.1 contradiction directly cited |

All v2 §17 + v1 §17 confidence tags carry forward verbatim.

## §18 TL;DR Table (preserved verbatim from v2 → v1)

## §19 Authorship Trail (v3-extended)

- **v1 drafted:** 2026-05-07.
- **v1 reviewed by Cursor:** 2026-05-09 — 4 defects.
- **v2 drafted:** 2026-05-09 (4-defect surgical amendment).
- **v2 reviewed by Cursor:** 2026-05-09 round-2 — 6 findings addressed: 5 substantive defect closures (2 HIGH + 3 MEDIUM authored in v3-A) + 1 documentation-structure closure (LOW §14 placeholder authored in v3-B). v3-D MEDIUM-2 reframing makes the 5/1 split explicit.
- **v3 drafted:** 2026-05-09 (6-finding round-2 surgical amendment, this document).
- **v3 reviewed by Cursor:** 2026-05-09 round-3 — 5 findings (HIGH×2 internal contradictions, MEDIUM×2 documentation tightening, LOW rolled into HIGH-1).
- **v3-C drafted:** 2026-05-09 (round-3 surgical cleanup, this document).
- **v3-C reviewed by Cursor:** 2026-05-09 round-4 — 4 findings (HIGH×2 governance-reframing + ld_id pseudocode pin; MEDIUM×2 broadened pyproject search + closure-type reframing).
- **v3-D drafted:** 2026-05-09 (round-4 surgical cleanup, this document).
- **v3-D reviewed by Cursor:** 2026-05-09 round-5 — 6 findings (HIGH×1 stale line citations; MEDIUM×3 portable find + LD-620 numeric id parity + WARN parity; LOW×2 grep -E portability + re-verify note).
- **v3-E drafted:** 2026-05-09 (round-5 surgical cleanup, this document).
- **v3 reviewed by:** (pending Kim).
- **Approved for implementation:** (pending Kim).
- **Implementation session:** (TBD — folds v2 + v3 amendments into v1 Phase B; Phase B0 prerequisite lands in same PR).
- **Closeout:** (TBD).
- **6-month retro:** scheduled 2026-11-07 (carries from v1 + v2).

---

*End of PERIODIC_CLASS_TECH_SPEC_v3.md.*
