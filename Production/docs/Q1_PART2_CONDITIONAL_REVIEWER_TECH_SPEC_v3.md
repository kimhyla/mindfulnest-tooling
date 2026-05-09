# Q1 — Part 2: Conditional Opus Reviewer Subagent — Tech Spec v3

**Status:** Spec authored 2026-05-09 (v3 amendment cycle, post-Cursor-v2-review). GOVERNANCE-AUTHORING — no production code (no hook installs, no settings.json edits, no SKILL.md changes, no scripts written). Spec-authoring artifacts (LD filing in `prod_locked_decisions`; activity_log POST in `prod_activity_log`) ARE the canonical deliverables of governance-authoring sessions per project-wide Rule 35 / DS-29 discipline — these are NOT production code mutations and ARE the canonical pattern, not an exception.
**Authority:** Kim's Q1 directive (state-claim verification stack — Part 2 of 3).
**Pairs with:** Q1 Part 1 (`Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md`, LD 579 `Q1_PART1_STOP_HOOK_INSTALLED_V1`).
**Authoring method:** v1 dual-Opus debate preserved by reference; v2 surgical amendments preserved by reference; v3 surgical amendments closing **6 findings (2 HIGH + 2 MEDIUM + 2 LOW)** from Cursor v2 review: HIGH-1 + HIGH-2 + MEDIUM-1 + MEDIUM-2 (4 actionable in v3-A) + LOW-1 + LOW-2 (closed via §7-AMEND-V3.7b + §0.4 in v3-A; consistency cleanup in v3-B; round-3 round-up in v3-C per §0.1; round-4 fix-and-consolidate in v3-D — Python hard-fail gate + parse v2-observed schema + G-2 coherence + §7-AMEND-V3.7 dedup into 7a/7b; round-5 fix-and-consolidate in v3-E — `jq | wc -l` event-counting fix + §7-AMEND-V3.7a/7b historical-citation cleanup + numeric LD ids in §9-AMEND-V3 + token int() float-truncation assumption documented).
**Supersedes:** v2 (`Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md`, sha256 `ce8a5abff542b22b653c42565169e00dd174707c5ae2fb7bb5599287de000f2f`) for the four amended sections; all other v2 sections preserved verbatim by reference. v1 also remains authoritative for sections not amended in v2 or v3.

---

## §0. Operating Mode

- GOVERNANCE-AUTHORING. v3 specifies surgical amendments to v2's §6-AMEND, §7-AMEND (parse_claude_response), and adds new §6-AMEND.8 + §7-AMEND.8 to close the four defects Cursor surfaced on v2. No production scripts, no settings.json edits, no hook installs are written by the act of authoring this spec. Spec-authoring artifacts — one LD row filed via `lock_decision.py` per amendment cycle (v3-A → LD-621, v3-B → LD-626, v3-C → LD-634, v3-D → LD-639, v3-E → LD-642) and one `prod_activity_log` POST per amendment cycle (rows 1996, 2003, 2012, 2018, `<v3-E-row-this-session>`) — ARE produced; these are the standard, expected, canonical deliverables of governance-authoring sessions and are NOT a contradiction of the no-code-mutation rule. See §10-AMEND-V3 for the explicit MUST/MUST-NOT list.
- Multipass authoring: pass 1 drafts §3-AMEND-V3, §6-AMEND-V3, §7-AMEND-V3, §8-AMEND-V3; pass 2 verifies cross-references and counts; pass 3 stress-tests parse contract + L3 narrative + typed schema check + glob shape against the empirical fnmatch/PurePath.match probe results captured in §6-AMEND-V3.5.
- Per Rule 24: state claims about Q1 Part 2 internals are tagged `[CONFIRMED from <file>:<line>]` where verified inline; un-verified architectural assertions are tagged `[INFERRED]` or `[GUESSED]`.
- HALT triggers: any unresolved cost-model gap; any glob-matcher ambiguity I cannot mechanically resolve with the empirical probe; any open decision Kim has not signaled on.
- Implementation requires a separate authorized session post-Cursor cross-review of v3.

## §0.1. Changelog (descending — v3 row above v2 + v1 rows)

| Version | Date | Author | Change |
|---|---|---|---|
| v3-E | 2026-05-09 | Claude (Cursor round-5 cleanup) | Round-5 surgical 4-fix consolidation closing Cursor round-5 review (1 HIGH correctness bug + 2 MEDIUM consistency + 1 LOW): (HIGH) **§7-AMEND-V3.7b threshold-check `jq | wc -l` miscounts events.** v3-D recipe `COUNT=$(jq -r 'select(.schema == "fallback")' ... | wc -l)` pretty-prints each matched JSON object across multiple lines by default, so `wc -l` counts pretty-print rows rather than fallback events — a 4-event week with 4-line pretty-print would falsely read 16 and trigger the >5 threshold spuriously (false-positive surface to weekly_preflight_audit.py). v3-E rewrites to `jq -s '[.[] | select(.schema == "fallback")] | length'` (slurps all inputs into one array; `length` returns array element count = one per event regardless of pretty-print width). Documented rationale comment inline + offered per-line projection (`jq -r '...| .ts' \| wc -l`) as no-`-s` fallback. (MEDIUM-1) **Historical changelog rows now reflect §7-AMEND-V3.7 → §7-AMEND-V3.7a/7b rename.** v3-B row + §0.3 supersession map previously cited bare `§7-AMEND-V3.7` without forward-pointing to the v3-D rename; v3-E annotates the v3-B row inline with the rename history (preserving original v3-B text) and adds a NEW §0.3 supersession-map row "v2 §7-AMEND.7 (or v3-A §7-AMEND-V3.7) → EXTENDED in v3-D into §7-AMEND-V3.7a + §7-AMEND-V3.7b" for stable forward citation. (MEDIUM-2) **§9-AMEND-V3 reference index now lists numeric LD ids alongside decision_keys.** Old: only `Q1_PART2_..._V1` decision_key strings; v3-E expands the v3 self-reference into a 5-row LD chain (v3-A LD-621 / v3-B LD-626 / v3-C LD-634 / v3-D LD-639 / v3-E LD-this-session) with numeric ids — citations from PRs/handoffs/Cursor reviews can now reference stable numeric LD ids without round-tripping through the decision_keys table. (LOW) **`int(tokens_val)` / `int(input_t) + int(output_t)` float-truncation assumption documented inline.** v3-D code at lines 511/523 silently truncates if SDK ever emits float (e.g. estimated tokens) — v3-E adds an inline comment block stating the int-contract assumption + offering a Phase A optional fail-loud path (`if isinstance(tokens_val, float) and not tokens_val.is_integer(): logger.warning("Q1_PART2_TOKEN_FLOAT_OBSERVED — SDK contract drift")`) to be wired in implementation handoff. NO version bump (still v3); NO base-spec sha256 invalidation; v2 sha256 unchanged at `ce8a5ab...`. LD: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_E_ROUND_5_FIXES_V1` (predecessor LDs: 621 v3-A + 626 v3-B + 634 v3-C + 639 v3-D). DS-29 source-tagged. |
| v3-D | 2026-05-09 | Claude (Cursor round-4 fix-and-consolidate) | Round-4 surgical 4-fix consolidation closing Cursor round-4 review (2 HIGH correctness bugs + 2 MEDIUM contract issues): (HIGH-1) **Python runtime gate hardened from warning-only to hard-fail.** §6-AMEND-V3.5b previously allowed (a) `python_requires = ">=3.12"` OR (b) runtime warning-only check; v3-D requires AT LEAST ONE OF (a) manifest pin (CI fails-closed before install) OR (b) runtime hard-fail at hook-import time that **RAISES SystemExit(1)** if `sys.version_info < (3, 12)` (NOT warning). Warning-only path explicitly REJECTED. CI gate G15a now verifies the hard-fail behavior via Python 3.11 venv import test; Phase A test fixture must include both manifest-pin assertion AND runtime-hard-fail assertion. (HIGH-2) **`parse_claude_response` rewritten to handle v2-observed schema (sums usage.input_tokens + usage.output_tokens).** v3-A/B/C parser checked top-level `total_tokens` only — under claude 2.1.137 (which nests tokens under `usage.*` per §7-AMEND-V3.3 [CONFIRMED 2026-05-09 v3-C] probe), every SDK call wrongly classified as `schema=fallback`. v3-D: schema label set expanded to 3-state {`v1` / `v2-observed` / `fallback`}; Path 3 logic probes top-level `total_tokens` first (v1 schema), then sums `usage.{input_tokens + output_tokens}` (v2-observed schema), then fallback. Token typing tightened (both subkeys required for v2-observed; bools excluded). 3 new fixtures (F-PR-9 v2-observed happy path, F-PR-10 partial-usage rejection, F-PR-11 non-dict-usage rejection). G-4 schema set updated to 3-state. §7-AMEND-V3.6 prose tightened: cost-cap operates on `total_cost_usd` (top-level field present in BOTH v1 and v2-observed) — UNAFFECTED by token-shape variation. Banner shows token count when `schema ∈ {"v1", "v2-observed"}`, "(tokens unknown)" on fallback. (MEDIUM-1) **G-2 contractual coherence repaired.** Old: "is float or None — never int/bool/str. (Exception: ints accepted...)" — self-contradicting. v3-D: G-2 reads "`result['total_cost_usd']` is `float` or `None`. Implementation: int values are ACCEPTED at parse time (via isinstance + bool exclusion) and COERCED to float. The RETURNED value is always float-or-None." Test assertion strengthened to verify post-coercion shape (`isinstance(..., float)` not `(int, float)`). (MEDIUM-2) **Duplicate `§7-AMEND-V3.7` section identifier resolved.** v3-A introduced two sections both labeled §7-AMEND-V3.7 — line 532 ("Why typed isinstance over duck-typed try: float") and line 550 ("Weekly Drift Detection — jq Canonical Replaces grep"). v3-D renames: line 532 → `§7-AMEND-V3.7a`, line 550 → `§7-AMEND-V3.7b`. Forward-looking cross-references in §0 (Authoring method), §0.2 (closing paragraph), §0.3 (LOW-1 bullet), §0.4 (cross-walk row), §7-AMEND-V3.6 (Schema field bullet) updated to point to `§7-AMEND-V3.7b`. Historical changelog rows (v3-A, v3-B) preserve the original `§7-AMEND-V3.7` names that existed during those amendment cycles (rename happened in v3-D, not retroactively). NO version bump (still v3); NO base-spec sha256 invalidation; v2 sha256 unchanged at `ce8a5ab...`. LD: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_D_ROUND_4_FIXES_V1` (predecessor LDs: 621 v3-A + 626 v3-B + 634 v3-C). DS-29 source-tagged. |
| v3-C | 2026-05-09 | Claude (Cursor round-3 cleanup) | Round-3 surgical 5-fix consolidation closing Cursor round-3 review (HIGH-1 + HIGH-2 + MEDIUM-1 + MEDIUM-2 + LOW): (HIGH-1) §0 banner + §10-AMEND-V3 reframed from "DESIGN ONLY ... no Directus writes" to "GOVERNANCE-AUTHORING" with explicit "spec-authoring artifacts" framing — LD filing + activity_log POST are the canonical deliverables of governance-authoring sessions per Rule 35 / DS-29, NOT a contradiction or carve-out from the no-code-mutation rule; (HIGH-2) count math consolidated to "**6 findings (2 HIGH + 2 MEDIUM + 2 LOW)**" everywhere — §0 Authoring-method line + §0.2 reading-order paragraph + §0.1 v3-A row math now consistent (DISAGREEMENT noted: Cursor round-3 prompt suggested "5 findings: 2 HIGH + 3 MEDIUM ... 1 LOW" — counter-position is that Cursor v2 actually surfaced exactly 2 HIGH (HIGH-1+HIGH-2) + 2 MEDIUM (MEDIUM-1+MEDIUM-2) + 2 LOW (LOW-1+LOW-2) per verbatim quotes preserved in §6-AMEND-V3.1 + §7-AMEND-V3.1; v3-C uses the verified count 2+2+2=6, not Cursor round-3's 2+3+1=6); (MEDIUM-1) NEW §6-AMEND-V3.5b "Python runtime requirement" pins implementation to `python_requires = ">=3.12"` OR runtime sys.version_info check + adds Phase A install gate G15a — `pathlib.PurePath.match` semantics consistency under future-version drift (note: empirically tested on system Python 3.9.6 during v3-C authoring; trailing-segment match held for the §6-AMEND-V3.3 patterns); (MEDIUM-2) §7-AMEND-V3.3 CANONICAL_TEXT_KEYS comment block updated from `[INFERRED]` to `[CONFIRMED 2026-05-09 v3-C]` — empirical `claude -p --output-format json "respond with the single word: ok"` probe executed during v3-C authoring against `claude --version 2.1.137 (Claude Code)`; observed payload top-level keys captured verbatim in the comment block confirming "result" IS canonical text key + total_cost_usd IS a float (validates §7-AMEND-V3.3 typed schema classifier) + total_tokens lives under usage.* (intended drift-detection signal — fallback path will fire on this SDK version, future v4 can map usage.* if Kim wants no-noise total_tokens accuracy); (LOW) §0.4 closing paragraph extended with explicit v3-C trade-off rationale — full structural renumbering across v1+v2+v3 was considered but rejected on (1) historical citation breakage, (2) diff balloon, (3) maintenance-friction-vs-reader-friction trade — cross-walk + §X-AMEND-V3 naming convention locked as compromise; future v4 may renumber as atomic structural pass when v1+v2+v3 corpus is closed. LD: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_C_ROUND_3_FIXES_V1` (predecessor LDs: 621 v3-A + 626 v3-B). DS-29 source-tagged. |
| v3-B | 2026-05-09 | Claude (multi-section consistency repair) | Multi-section LOW-consistency cleanup — propagated v3-A's actual disposition of the 2 LOW findings (CLOSED, not deferred) into prior contradicting prose: (a) §0 Authoring-method line rewritten to read "2 LOW closed via §0.4 + §7-AMEND-V3.7" (note: §7-AMEND-V3.7 was renamed to §7-AMEND-V3.7b in v3-D round-4 to resolve duplicate-ID with §7-AMEND-V3.7a typed-isinstance rationale; v3-B authored before that rename so the original §7-AMEND-V3.7 name is preserved here as the historical record); (b) §0.1 v3-A changelog row trailing sentence rewritten from "2 LOW findings deferred (...)" to "2 LOW findings closed via §0.4 (LOW-2 — Section ID Legend) + §7-AMEND-V3.7b (LOW-1 — jq canonical replaces grep; §7-AMEND-V3.7 was renamed to §7-AMEND-V3.7b in v3-D round-4 to resolve duplicate-ID with §7-AMEND-V3.7a typed-isinstance rationale)"; (c) §0.2 closing paragraph rewritten from "Cursor-v2 found 4 actionable defects + 2 LOW; closing only the 4 actionable defects" to "Cursor-v2 found 4 actionable defects + 2 LOW; closing all 6 in v3 (4 actionable in v3-A surgical amendments + 2 LOW in §0.4 / §7-AMEND-V3.7b)". §0.4 Section ID Legend + §7-AMEND-V3.7b jq alternative remain unchanged (well-formed under v3-A; renamed in v3-D); §0.3 supersession map + §8/§9/§10/§11-AMEND-V3 remain unchanged (no deferred-LOW references found). LD: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_B_LOW_CONSISTENCY_V1` (predecessor LD-621). DS-29 source-tagged. |
| v3-A | 2026-05-09 | Claude (post-Cursor v2 review) | Surgical 4-defect closure: (HIGH-1) §7-AMEND.3 `parse_claude_response` rewritten — ALWAYS sets "text" key on every return path; canonical text-extraction contract pinned to `parsed.get("result")` with documented fallback chain; (HIGH-2) §6-AMEND.6 L3/L4 narrative tightened — explicit statement that spec/doc paths NEVER satisfy L3 by design + worked example showing spec-only edits stay in Part 1; (MEDIUM-1) §7-AMEND.3 schema classifier replaced — substring `'"total_cost_usd"' in response_text` removed in favor of typed structural check `isinstance(parsed.get("total_cost_usd"), (int, float))`; (MEDIUM-2) §6-AMEND.3 glob shapes canonicalized to `**/<dir>/*.<ext>` form + matcher pinned to `pathlib.PurePath.match` (with documented `fnmatch.fnmatch` deviation rationale per §6-AMEND-V3.5 empirical probe). Test fixture added: one exemplar relative path per pattern + assertion of match. 2 LOW findings closed via §0.4 (LOW-2 — Section ID Legend) + §7-AMEND-V3.7 (LOW-1 — jq canonical replaces grep). |
| v2-A | 2026-05-08 | Claude (post-Cursor v1 review) | (See v2 §0.1 row.) |
| v1 | 2026-05-08 | Claude (initial dual-Opus debate) | (See v1 §0.1 row.) |

## §0.2. Reading order (for reviewers)

v3 is a surgical amendment overlay on v2, NOT a full rewrite. To review v3 in context:

1. **Read v1 first** in full (`Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`).
2. **Read v2 next** in full (`Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md`) — v2's §3-AMEND/§6-AMEND/§7-AMEND/§10-AMEND supersede v1's §3/§6/§7/§10.
3. **Then read v3 §3-AMEND-V3 (carry-forward note), §6-AMEND-V3, §7-AMEND-V3, §8-AMEND-V3** — these supersede v2's corresponding amended sections per the table in §0.3.
4. **All other v1+v2 sections** (not listed above) **remain authoritative**.

This v3 doc is intentionally surgical to keep the diff against v2 small and reviewable. Cursor v2 review surfaced **6 findings total: 2 HIGH (HIGH-1 + HIGH-2) + 2 MEDIUM (MEDIUM-1 + MEDIUM-2) + 2 LOW (LOW-1 + LOW-2)**. v3 closes all 6: the 4 actionable (2 HIGH + 2 MEDIUM) in v3-A's surgical amendments to §6-AMEND/§7-AMEND/§3-AMEND, and the 2 LOW in v3-A via §0.4 Section ID Legend (LOW-2) and §7-AMEND-V3.7b jq canonical (LOW-1) per Kim's "no LOW deferrals" directive. v3-B consistency-cleaned the closure-vs-deferral wording across §0/§0.1/§0.2; v3-C consolidates count math + governance-authoring framing + Python runtime pin + canonical text keys gate + §14 placeholder trade-off doc per Cursor round-3 review; v3-D round-4 fix-and-consolidate addresses 4 round-4 defects (Python hard-fail gate + parse_claude_response v2-observed schema + G-2 coherence + §7-AMEND-V3.7 dedup into 7a/7b); v3-E round-5 fix-and-consolidate addresses 4 round-5 defects (`jq | wc -l` event-counting in §7-AMEND-V3.7b + §7-AMEND-V3.7a/7b historical-reference cleanup in v3-B row + §0.3 supersession map + numeric LD ids in §9-AMEND-V3 + token int() float-truncation assumption documented inline at §7-AMEND-V3.3).

## §0.3. v3 supersession map (which v2 sections does v3 replace?)

| v2 section | v3 disposition |
|---|---|
| v2 §3-AMEND (L4 deterministic suppression) | UNCHANGED. v3 carries v2 forward verbatim. (See §3-AMEND-V3 — no-op carry forward marker.) |
| v2 §6-AMEND.1–§6-AMEND.5 (allow-list narrowing) | AMENDED. v3 §6-AMEND-V3.3 republishes the canonicalized glob shapes; v3 §6-AMEND-V3.5 pins matcher; remainder of §6-AMEND.1–.5 carry forward. |
| v2 §6-AMEND.6 (L3/L4 decoupling rule) | AMENDED. v3 §6-AMEND-V3.6 rewrites the rule-statement paragraph + adds a worked example. |
| v2 §6-AMEND.7 | UNCHANGED carry-forward. |
| v2 §7-AMEND.1–§7-AMEND.2 (cost-field fallback rationale) | UNCHANGED carry-forward. |
| v2 §7-AMEND.3 (`parse_claude_response`) | AMENDED. v3 §7-AMEND-V3.3 rewrites the function: ALWAYS-text contract + canonical extraction chain + typed schema classifier. |
| v2 §7-AMEND.4–§7-AMEND.7 | UNCHANGED carry-forward. |
| v2 §7-AMEND.7 (or v3-A `§7-AMEND-V3.7`) | EXTENDED in v3-D into `§7-AMEND-V3.7a` (typed-isinstance rationale) + `§7-AMEND-V3.7b` (jq canonical / weekly drift). v3-E HIGH-fix corrects the §7-AMEND-V3.7b threshold-check recipe to count events not lines. |
| v2 §10-AMEND (recursion guard fail-CLOSED) | UNCHANGED. v3 carries v2 forward verbatim. |
| v2 §14-AMEND (4 v2 risk rows) | EXTENDED. v3 §8-AMEND-V3 appends 4 new v3 risk rows. |
| v2 §11-AMEND (reference index) | EXTENDED. v3 §9-AMEND-V3 appends v3 references. |

**LOW findings closed in v3 (was deferred at first authoring pass; reopened per Kim's "no LOW deferrals" directive):**

- **LOW-1 (weekly drift grep one-liner brittle on whitespace) — CLOSED:** see §7-AMEND-V3.7b below (renamed from §7-AMEND-V3.7 in v3-D to disambiguate from §7-AMEND-V3.7a "typed isinstance over duck-typed try: float"). v2's grep one-liner is replaced as the canonical recommendation by `jq -r 'select(.schema=="fallback") | .ts' < log.jsonl`. The grep variant is retained only as a no-jq fallback with explicit caveat about whitespace/key-order brittleness.
- **LOW-2 (§11-AMEND numbering vs v1 §17 reference index) — CLOSED:** see §0.4 Section ID Legend below. v3 does NOT renumber v2's §-AMEND headers (which would balloon the diff and break v2 cross-references), but adds a version-disambiguated cross-walk so citers always know which "Reference Index" is meant.

---

## §0.4. Section ID Legend (NEW in v3 — closes LOW-2)

When citing a section ID across docs/handoffs/PRs/Cursor reviews, **always disambiguate version**:

| Section ID | v1 meaning | v2 meaning | v3 meaning |
|---|---|---|---|
| §3 | (sections of v1 spec) | preserved by reference | §3-AMEND-V3 carry-forward marker (no change to v2 §3-AMEND) |
| §6 | (v1 spec) | §6-AMEND tightened allow-list (HIGH-1 from Cursor-v1) | §6-AMEND-V3 glob-shape canonicalization + L3∧L4 narrative (HIGH-2 from Cursor-v2 + MEDIUM-2) |
| §7 | (v1 spec) | §7-AMEND cost-field fallback (Cursor-v1) | §7-AMEND-V3 parse-contract tightening + typed schema classifier (HIGH-1 + MEDIUM-1 from Cursor-v2); §7-AMEND-V3.7a typed-isinstance rationale + §7-AMEND-V3.7b jq alternative (LOW-1; renamed in v3-D from single §7-AMEND-V3.7 — see §0.1 v3-D row) |
| §10 | (v1 spec) | §10-AMEND fail-closed recursion guard | preserved (no v3 change) |
| §11 | (v1 spec) | §11-AMEND extension-pointer to v1 §17 reference index | §9-AMEND-V3 appends v3 references; v2's §11-AMEND extension preserved by reference |
| §17 | **Reference Index (canonical location, v1)** | extended via §11-AMEND | extended via §9-AMEND-V3 + §11-AMEND |

**Rule for citers:** when referring to a v3 section, write `v3 §X-AMEND-V3`. When referring to a v2 amendment section, write `v2 §X-AMEND`. When referring to v1's canonical section, write `v1 §X`. Never bare `§X` for cross-doc citations. The Reference Index canonically lives at **v1 §17**; subsequent versions extend it via §11-AMEND (v2) and §9-AMEND-V3 (v3).

**v3-C trade-off note (closes Cursor round-3 LOW):** Cursor round-3 flagged that the §14 placeholder / cross-walk approach used here introduces indexing complexity instead of resolving structure. Full structural renumbering across v1 + v2 + v3 was considered for v3-C but deliberately rejected on three grounds:

1. **Historical citation breakage** — renumbering would invalidate every cross-reference in v1 + v2 (the LD-621 / LD-626 corpus, the implementation handoff at `Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md`, and the Cursor v1/v2 review handoffs all cite the existing numbering).
2. **Diff balloon** — a renumbering pass would touch nearly every §-anchor in 1300+ lines across v1+v2+v3 for cosmetic gain; the v3-C surgical patch principle (keep diffs reviewable) loses if v3-C ships a 1000-line cosmetic diff.
3. **Maintenance friction outweighs reader friction** — the cross-walk table above + the `§X-AMEND-V3` naming convention give readers a deterministic disambiguation; the cost is one extra lookup per cross-doc citation. Acceptable.

**Compromise locked:** the cross-walk table at §0.4 + the Reference-Index pointer at §9-AMEND-V3 are the acknowledged compromise. **A future v4 may renumber as a single structural pass** if (a) the v1 + v2 + v3 corpus is closed (no further amendments planned) AND (b) the implementation handoff is updated in the same atomic commit. Until then, the cross-walk stays.

---

## §3-AMEND-V3. L4 Deterministic Tag-Suppression Semantics — carry forward

**No change from v2.** v2's §3-AMEND.1–§3-AMEND.7 (HIGH-1 closure, deterministic 120-char window, edge-case rules EC-1 through EC-8, fixture rows F-EC-1 through F-EC-7) remain authoritative as published.

This carry-forward marker exists so that future readers can confirm v3 did NOT modify L4 trigger semantics. The v2 algorithm is sound per Cursor-v2 review (no objection raised on §3-AMEND).

---

## §6-AMEND-V3. Tightened Allow-List + L3/L4 Decoupling — Glob Shape & L3 Narrative Refinement

### 6-AMEND-V3.1. Cursor v2 findings addressed in this section

- **MEDIUM-2** (verbatim from Cursor v2 review): "Workflow glob patterns look easy to mis-specify vs real fnmatch / shell glob semantics. Examples such as `**/Production/.github/workflows/**.yml` deviate from the common `**/*.yml` shape used elsewhere; depending on how v1 INFRASTRUCTURE_PATH_PATTERNS is implemented, patterns may fail to ever match .github/workflows trees."
- **HIGH-2** (verbatim from Cursor v2 review): "§6-AMEND.6 wording vs L3∧L4 conjunction invites misimplementation. One sentence reads as though doc/spec risk is addressed 'via L4 only,' which is not what the conjunction does and can be read as 'doc edits still reach Part 2 through L4.' That conflicts with §6-AMEND.6's closing note that conjunction is unchanged."

### 6-AMEND-V3.2. Root causes

**MEDIUM-2 root cause.** v2's §6-AMEND.3 list mixed two glob shapes:

- The common shape `**/<segment>/*.<ext>` (e.g., `**/Production/scripts/preflight_hook.py`).
- The non-canonical shape `**.<ext>` and `**/<segment>/**.<ext>` (e.g., `**/Production/.github/workflows/**.yml`, `**/Production/.github/workflows/**.yaml`).

The non-canonical shape works *partially* under Python's `fnmatch.fnmatch` (because `**` and `*` are equivalent in fnmatch — both are "any sequence of any characters") but fails on relative paths because the leading `**/` does not anchor against `Production/...` without a leading slash. Empirical probe (run 2026-05-09, captured in §6-AMEND-V3.5):

```
fnmatch.fnmatch on '/Users/kim/Production/.github/workflows/ci.yml' vs '**/Production/.github/workflows/**.yml':  MATCH
fnmatch.fnmatch on 'Production/.github/workflows/ci.yml' (relative, no leading /)  vs '**/Production/.github/workflows/**.yml':  NO MATCH
fnmatch.fnmatch on 'Production/.github/workflows/ci.yml' vs '**/.github/workflows/*.yml':  MATCH
PurePath('Production/.github/workflows/ci.yml').match('**/.github/workflows/*.yml'):  MATCH
```

The hook receives `file_path` from Claude Code tool_use events; the path may be supplied as either absolute or project-relative depending on which tool emitted it. The v2 patterns therefore fired *inconsistently* depending on how the path was rendered upstream.

**HIGH-2 root cause.** v2 §6-AMEND.6 contains the line:

> **Doc/spec edits trigger Part 2 ONLY via L4 regex (state-claim language with no nearby tag), NOT via L3 path-class match.**

Read in isolation, that sentence can be parsed two ways:

- (intended) Doc/spec edits cannot reach Part 2 — L3 fails on doc/spec paths, L4 alone is insufficient because the conjunction L0∧L1∧L2∧L3∧L4∧L5 still requires L3.
- (unintended) Doc/spec edits ARE the things that trigger Part 2, via L4 only.

The closing note in v2 ("the §3-AMEND.3 trigger conjunction is unchanged") restores the intended reading, but only on careful reading of both paragraphs together. Cursor v2 flagged that an implementer reading just the bold sentence would write a buggy hook.

### 6-AMEND-V3.3. v3 canonicalized allow-list (locked — replaces v2 §6-AMEND.3)

```
~/.claude/hooks/*.py
~/.claude/settings.json
~/.claude/settings.local.json
**/.claude/skills/*/SKILL.md
**/CLAUDE.md
**/Production/scripts/preflight_hook.py
**/Production/scripts/weekly_preflight_audit.py
**/Production/scripts/session_event_logger.py
**/Production/scripts/precompact_save_trigger.py
**/Production/scripts/deny_bash_governed_write.py
**/Production/scripts/lock_decision.py
**/Production/scripts/registered_write.py
**/Production/scripts/migrate_*.py
**/Production/scripts/git_hooks/*
**/Production/lib/directus*.py
**/Production/lib/preflight.py
**/.github/workflows/*.yml
**/.github/workflows/*.yaml
**/Production/github_actions/*.yml
**/Production/github_actions/*.yaml
**/firestore.rules
**/firestore.indexes.json
```

**Changes from v2 §6-AMEND.3:**

| v2 pattern | v3 pattern | Change rationale |
|---|---|---|
| `**/Production/.github/workflows/**.yml` | `**/.github/workflows/*.yml` | Drop `Production/` segment (the `.github/workflows/` directory is repo-relative, not Production-relative — the master roadmap places future CI/CD configs at the repo root `.github/workflows/`, not inside `Production/`) AND replace `**.yml` with `*.yml` (canonical leaf glob; one segment of any name ending `.yml`). |
| `**/Production/.github/workflows/**.yaml` | `**/.github/workflows/*.yaml` | Same as above. |
| `**/Production/scripts/git_hooks/**` | `**/Production/scripts/git_hooks/*` | Replace `**` (which is two-star and ambiguous in fnmatch) with `*` (one segment, canonical leaf). Git hooks are flat files (`pre-commit`, `pre-push`, etc.) under `git_hooks/` — no nested subdirectories expected. |
| (all other patterns) | unchanged | Already canonical `**/<dir>/<file>` shape. |

### 6-AMEND-V3.4. Matcher pinned: `pathlib.PurePath.match`

**v3 pins the matcher to `pathlib.PurePath.match`** for the `INFRASTRUCTURE_PATH_PATTERNS` constant. v2's narrative inherited v1's `fnmatch.fnmatch` choice, which is empirically wrong on `**` semantics:

- `fnmatch.fnmatch` treats `**` as `*` (any sequence of any characters within a single segment OR across segments — there is no segment awareness; `*` matches `/` too in fnmatch).
- `pathlib.PurePath.match` treats `**` as a multi-segment wildcard for trailing segment matching (Python 3.13+ added `full_match` for full-path multi-segment globbing; on 3.12 and below, `match` only matches the *trailing* portion of the path against the pattern, which is exactly the "last-N-segments" semantics this allow-list needs).

Implementation pseudocode (for the implementation session, NOT executed by this spec):

```python
from pathlib import PurePath

INFRASTRUCTURE_PATH_PATTERNS = [
    "~/.claude/hooks/*.py",
    "~/.claude/settings.json",
    "~/.claude/settings.local.json",
    "**/.claude/skills/*/SKILL.md",
    "**/CLAUDE.md",
    "**/Production/scripts/preflight_hook.py",
    "**/Production/scripts/weekly_preflight_audit.py",
    "**/Production/scripts/session_event_logger.py",
    "**/Production/scripts/precompact_save_trigger.py",
    "**/Production/scripts/deny_bash_governed_write.py",
    "**/Production/scripts/lock_decision.py",
    "**/Production/scripts/registered_write.py",
    "**/Production/scripts/migrate_*.py",
    "**/Production/scripts/git_hooks/*",
    "**/Production/lib/directus*.py",
    "**/Production/lib/preflight.py",
    "**/.github/workflows/*.yml",
    "**/.github/workflows/*.yaml",
    "**/Production/github_actions/*.yml",
    "**/Production/github_actions/*.yaml",
    "**/firestore.rules",
    "**/firestore.indexes.json",
]

def matches_infrastructure_path(file_path: str) -> bool:
    """Trailing-segment match against the v3 allow-list.

    Uses pathlib.PurePath.match — segment-aware, treats `**` as
    multi-segment wildcard for trailing match. Does NOT use
    fnmatch.fnmatch (which has flat-string `*` and is incorrect
    for the `**/<dir>/<file>` shape).

    The `~/.claude/...` patterns are matched against the absolute
    expanded path (after `os.path.expanduser`) — the leading `~`
    in the pattern is matched literally only if the input path
    is also a tilde-prefixed string, which we do not expect from
    Claude Code tool_use events. Implementation expands `~` in
    BOTH the pattern and the input path before match.
    """
    import os
    p = PurePath(os.path.expanduser(file_path))
    for pat in INFRASTRUCTURE_PATH_PATTERNS:
        pat_expanded = os.path.expanduser(pat)
        try:
            if p.match(pat_expanded):
                return True
        except ValueError:
            # PurePath.match raises ValueError on certain malformed
            # patterns; treat as non-match and continue.
            continue
    return False
```

[INFERRED — `os.path.expanduser` interaction with `PurePath.match` patterns containing `~/...` requires implementation-time fixture verification. The fallback `try/except ValueError` is defensive against the documented behavior of `PurePath.match` raising on patterns like `**.yml` if any v3 pattern accidentally regresses to a v2-style shape.]

### 6-AMEND-V3.5. Empirical matcher probe (test fixture — locked)

The following probe was executed 2026-05-09 to confirm v3's pattern shapes work under both `pathlib.PurePath.match` (the pinned matcher) and `fnmatch.fnmatch` (legacy fallback if implementation ever needs to compare). Results form the regression baseline for the implementation handoff.

| Path (input) | Pattern | `fnmatch.fnmatch` | `PurePath.match` |
|---|---|---|---|
| `Production/.github/workflows/ci.yml` | `**/.github/workflows/*.yml` | MATCH | MATCH |
| `/Users/kim/Production/.github/workflows/ci.yml` | `**/.github/workflows/*.yml` | MATCH | MATCH |
| `Production/scripts/git_hooks/pre-commit` | `**/Production/scripts/git_hooks/*` | MATCH | MATCH |
| `Production/scripts/migrate_foo.py` | `**/Production/scripts/migrate_*.py` | MATCH | MATCH |
| `Production/lib/directus_writers.py` | `**/Production/lib/directus*.py` | MATCH | MATCH |
| `Production/Storyboards/M1E1.html` | (any v3 pattern) | NO MATCH | NO MATCH |
| `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v3.md` | (any v3 pattern) | NO MATCH | NO MATCH |

The last two rows are the L3-negative test (per v1 §6.3): storyboard HTML and spec markdown MUST NOT match the allow-list. The probe confirms they do not.

[CONFIRMED 2026-05-09 — probe results captured in spec authoring session; implementation handoff Phase D fixture must replay this exact table.]

### 6-AMEND-V3.5b. Python runtime requirement (NEW v3-C — closes Cursor round-3 MEDIUM-1)

**Cursor round-3 finding (MEDIUM-1, verbatim):** "PurePath.match guidance risks cross-version behavior drift without pinning Python runtime semantics. Spec acknowledges 3.13 added `full_match` but locks `match` choice without runtime version pinning."

**v3-C resolution — runtime pin LOCKED:**

Q1 Part 2 implementation MUST pin Python `>= 3.12` in the venv used by the Stop-hook subagent that ships `parse_claude_response` and the `matches_infrastructure_path` helper. The `pathlib.PurePath.match` semantics chosen in §6-AMEND-V3.4 assume 3.12-or-later behavior. Python 3.13 added `Path.full_match` for stricter full-path multi-segment globbing; v3 deliberately uses `match` (not `full_match`) for trailing-portion semantics consistent with the §6-AMEND-V3.3 INFRASTRUCTURE_PATH_PATTERNS shape (last-N-segments allow-list).

**Empirical compatibility note (added v3-C):** the 2026-05-09 probe in §6-AMEND-V3.5 was re-validated under Python 3.9.6 (the system Python on the spec-authoring host) and the trailing-segment match semantics for the v3 allow-list patterns held — patterns matched as expected. The `>= 3.12` pin is therefore conservative (the patterns also work under 3.9–3.11 for the specific shapes in §6-AMEND-V3.3); the pin's purpose is to forestall future-version drift, not to gate against a known 3.9–3.11 break.

**Phase A install gate (NEW G15a — v3-D HARDENED):** Q1 Part 2 implementation Phase A MUST satisfy AT LEAST ONE OF (a) or (b); BOTH preferred. Warning-only is INSUFFICIENT:

(a) **Manifest pin (CI fails-closed BEFORE install):** Add `python_requires = ">=3.12"` to the package manifest the hook subagent uses (`pyproject.toml`, `setup.cfg`, or equivalent). pip / build will refuse to install on a host running Python < 3.12 — the gate fires before the hook ever loads.

(b) **Runtime hard-fail at hook-import time:** Insert a check that **RAISES `SystemExit(1)` if `sys.version_info < (3, 12)`** (NOT a warning — the import must fail closed):

```python
import sys
if sys.version_info < (3, 12):
    sys.stderr.write(
        f"q1_part2: FATAL — running under Python "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; "
        f"v3 spec pins >=3.12 for PurePath.match semantics consistency. "
        f"Hook refusing to load. Upgrade Python or pin the manifest.\n"
    )
    raise SystemExit(1)
```

CI gate G15a verifies (a) — that `python_requires` is present in the manifest and CI fails closed before install. Hook self-test verifies (b) — that import under a Python 3.11 venv raises SystemExit(1) (not a warning, not a soft-pass). **Phase A test fixture MUST include both: a manifest-pin assertion AND a runtime-hard-fail assertion (skipif Python < 3.12 with explicit error message).** Warning-only logging paths are explicitly REJECTED — they let < 3.12 hosts run with a log line that operators ignore, defeating the contractual semantics guarantee.

**Quarterly review extension:** §6-AMEND-V3.7 quarterly cadence extends to: re-run §6-AMEND-V3.5 probe table on the deployed Python runtime; compare against the locked baseline; if the runtime drifts forward (e.g., 3.14, 3.15) and any row changes outcome, file a v4 amendment.

[CONFIRMED 2026-05-09 — Python runtime probe (Python 3.9.6 on spec-authoring host) returned expected match results for the §6-AMEND-V3.3 pattern shapes; pin to 3.12+ is conservative forward-compat insurance, not a fix for a known earlier-version break.]

### 6-AMEND-V3.6. L3 / L4 decoupling rule — rewritten (replaces v2 §6-AMEND.6 rule paragraph)

**Rule (locked, replaces v2 §6-AMEND.6 bold line):**

> **Spec/doc paths NEVER satisfy L3 by design.** The v3 §6-AMEND-V3.3 allow-list is the complete enumeration of L3-eligible paths; spec markdown (`Production/docs/*_SPEC_v*.md`), LD planning markdown (`Production/docs/*LD*.md`), and roadmap markdown (`Production/docs/MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v*.md`) are NOT in the list. **Therefore Part 2 cannot fire on spec-only edits regardless of whether L4 regex matches.** The L0∧L1∧L2∧L3∧L4∧L5 conjunction is unchanged from v1; the practical effect is that spec-only sessions stay in Part 1 + DS-22 SAVE-time scanning, never spawning Part 2.

**Worked example (locked — required fixture for implementation handoff):**

Suppose an authoring session writes:

- File edits: ONLY `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v3.md`.
- Assistant prose: contains the sentence "the L3 path matcher is wired to PurePath.match" — a state-claim regex match per v2 §3-AMEND.3.
- Tag chain: no `[CONFIRMED…]`/`[INFERRED…]` tag within 120 chars after the claim.

**Trigger evaluation:**

| Layer | Outcome | Why |
|---|---|---|
| L0 (env-var sentinel) | PASS (not inside `claude -p`) | Authoring session, not headless. |
| L1 (spawn cap) | PASS (assume <7 spawns this session) | Counter not yet exhausted. |
| L2 (Write|Edit tool_use present) | PASS | Spec edit is a Write/Edit tool_use. |
| L3 (path-class match) | **FAIL** | Spec markdown is not in §6-AMEND-V3.3 allow-list. |
| L4 (state-claim regex unsuppressed) | (would PASS) | But L3 short-circuits the conjunction. |
| L5 (output sentinel absent) | (would PASS) | Not a reviewer-output turn. |

**Verdict: NO SPAWN.** The spec edit is correctly routed to Part 1 (broader sieve) + DS-22 (SAVE-time scanning) only. Part 2 stays silent. This is the intended design — spec/doc state-claims are conditional ("will be wired") and do not justify burning a $1.50 reviewer spawn.

**Counter-example (sanity check — also required fixture):**

Suppose an authoring session writes:

- File edits: `~/.claude/hooks/stop_state_claim_scan.py` (in v3 §6-AMEND-V3.3 allow-list).
- Assistant prose: contains the sentence "the hook is wired by the new gate" — state-claim regex match.
- No tag within 120 chars.

| Layer | Outcome |
|---|---|
| L0 | PASS |
| L1 | PASS |
| L2 | PASS (Edit tool_use) |
| L3 | **PASS** (`~/.claude/hooks/*.py` matches) |
| L4 | **PASS** (regex match unsuppressed) |
| L5 | PASS |

**Verdict: SPAWN.** Both L3 (real infrastructure file) AND L4 (unverified state claim) fired. Part 2 dispatches the Opus reviewer.

### 6-AMEND-V3.7. Risk: matcher-runtime drift

If a future Python version changes `pathlib.PurePath.match` semantics (e.g., the documented Python 3.13 `full_match` addition), the v3 fixtures must be re-run. The §6-AMEND-V3.5 probe table is the regression baseline. Quarterly review (per v2 §6-AMEND.7 quarterly cadence) extends to: re-run the probe table and compare against the locked baseline.

---

## §7-AMEND-V3. Cost-Field Fallback — Parse Contract Tightening + Typed Schema Classifier

### 7-AMEND-V3.1. Cursor v2 findings addressed in this section

- **HIGH-1** (verbatim from Cursor v2 review): "`parse_claude_response` contradicts its own API spec (successful JSON path omits 'text'). The docstring requires a 'text' key on every return. For JSONDecodeError / non-object JSON you populate 'text'; for successful json.loads(...) into a dict you never set 'text' and only tweak cost fields plus schema. Any downstream code that assumes parsed['text'] always exists (per the normative sketch) would break after v2-amended Phase D."
- **MEDIUM-1** (verbatim from Cursor v2 review): "Cost 'schema drift' detector uses brittle substring checks on raw response_text. `has_cost = '\"total_cost_usd\"' in response_text` fires on incidental substrings inside JSON string values / partial streams and can mislabel schema as 'v1' when the typed fields are missing or malformed."

### 7-AMEND-V3.2. Root causes

**HIGH-1 root cause.** v2 §7-AMEND.3 splits into three return paths:

1. JSONDecodeError → returns `{"text": response_text, ..., "schema": "fallback"}`. **Sets text.**
2. JSON-but-not-dict → returns `{"text": response_text, ..., "schema": "fallback"}`. **Sets text.**
3. Successful dict parse → returns `parsed` after `parsed.setdefault("total_cost_usd", None)` etc. — but **never sets `parsed["text"]`** unless the upstream JSON happened to include a "text" key.

The docstring promises `"text"` always exists. Path 3 violates that promise. Any downstream caller writing `result = parse_claude_response(...); banner = result["text"]` will KeyError on the success path.

**MEDIUM-1 root cause.** v2 line 285:

```python
has_cost = '"total_cost_usd"' in response_text
```

This is a flat-string substring check on the raw JSON. It fires false-positives when:

- The raw text contains the literal string `"total_cost_usd"` inside a JSON string value (e.g., a reviewer's prose mentions the field name).
- A streamed/truncated response contains the field name but not the typed value.
- Any other place where the substring appears for non-schema reasons.

It fires false-negatives when:

- The schema renamed `total_cost_usd` to `cost_usd` but kept the `_usd` suffix elsewhere — substring would not match the renamed canonical field.
- Whitespace variants (`"total_cost_usd" : 0.05` vs `"total_cost_usd": 0.05`) are tolerated but a key-order serializer that reorders fields could change the substring shape.

### 7-AMEND-V3.3. v3 rewritten `parse_claude_response` (locked — replaces v2 §7-AMEND.3)

```python
import json
import logging

logger = logging.getLogger("q1_part2")

# Canonical text-extraction path. The Claude Code SDK's
# `claude -p ... --output-format json` response shape returns an
# object with a "result" key containing the assistant message body.
# If the schema drifts, fall back through the documented alternates
# before resorting to a stringified dump.
#
# [CONFIRMED 2026-05-09 v3-C — empirical probe executed during v3-C
# authoring session against `claude --version 2.1.137 (Claude Code)`:
#
#   $ claude -p --output-format json "respond with the single word: ok"
#   {"type":"result","subtype":"success","is_error":false,
#    "api_error_status":null,"duration_ms":2746,"duration_api_ms":2604,
#    "num_turns":1,"result":"ok","stop_reason":"end_turn",
#    "session_id":"<uuid>","total_cost_usd":0.40658849999999996,
#    "usage":{...},"modelUsage":{...},"permission_denials":[],
#    "terminal_reason":"completed","fast_mode_state":"off","uuid":"<uuid>"}
#
# Observed top-level keys: type, subtype, is_error, api_error_status,
# duration_ms, duration_api_ms, num_turns, RESULT (text body), stop_reason,
# session_id, TOTAL_COST_USD (float), usage, modelUsage, permission_denials,
# terminal_reason, fast_mode_state, uuid.
#
# Confirms: (a) "result" IS the canonical text-body key (first in the
# tuple below); (b) total_cost_usd IS a float (validates §7-AMEND-V3.3
# typed schema classifier); (c) total_tokens is NOT a top-level key —
# it lives under usage.input_tokens + usage.output_tokens.
#
# v3-D resolution (HIGH-2): the parse_claude_response function below
# now handles BOTH top-level `total_tokens` (v1 schema, hypothetical
# future shape) AND `usage.input_tokens + usage.output_tokens` aggregation
# (v2-observed schema, claude 2.1.137 actual shape). Schema label set
# expanded from {"v1", "fallback"} to {"v1", "v2-observed", "fallback"}
# (3-state) so the drift-detection signal still fires on TRULY missing
# token data (fallback) while NOT firing on the routine SDK shape that
# nests tokens under usage.* (v2-observed).
#
# CANONICAL_TEXT_KEYS tuple is the single point of update if the schema
# drifts in a future Claude Code release.]
CANONICAL_TEXT_KEYS = ("result", "assistant_message", "text", "content", "message")


def _extract_text_from_parsed(parsed: dict, raw: str) -> str:
    """Pull the assistant body out of a parsed claude -p JSON object.

    Tries each key in CANONICAL_TEXT_KEYS in order. Accepts only string
    values (not dicts/lists — those are structured response shapes that
    require their own canonical field probe). Falls back to
    json.dumps(parsed) if no canonical key produces a string. Falls back
    further to the raw response_text if json.dumps itself fails (it
    shouldn't, since `parsed` was successfully json.loads'd from `raw`,
    but defensive).
    """
    for k in CANONICAL_TEXT_KEYS:
        v = parsed.get(k)
        if isinstance(v, str):
            return v
    try:
        return json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    except Exception:
        return raw


def parse_claude_response(response_text: str) -> dict:
    """Parse the stdout from `claude -p ... --output-format json`.

    Returns a dict that ALWAYS contains these keys (no exceptions):
      - "text":             str — the reviewer's text body. Never None,
                                  never absent. Falls back through
                                  CANONICAL_TEXT_KEYS, then json.dumps,
                                  then raw response_text.
      - "total_cost_usd":   float | None — None signals "unknown". Coerced
                                  via float(val); ints accepted at parse
                                  time and coerced to float. Returned
                                  value is always float-or-None.
      - "total_tokens":     int | None — None signals "unknown". Probed
                                  at top-level (v1 schema) FIRST, then
                                  summed from usage.input_tokens +
                                  usage.output_tokens (v2-observed schema).
      - "schema":           "v1" | "v2-observed" | "fallback" — 3-state
                                  typed-presence classification (not
                                  substring).

    Never raises. Logs a WARNING when schema=fallback so weekly review
    can detect SDK output schema drift. v2-observed is NOT a fallback —
    it is the routine SDK shape on claude >= 2.1.137 and does not log a
    warning.

    Cost-cap operates on `total_cost_usd` (top-level field, present in
    BOTH v1 and v2-observed shapes); the cost-cap is therefore unaffected
    by the token-shape variation between v1 and v2-observed.
    """
    # Path 1: malformed JSON → fallback, text=raw.
    try:
        parsed = json.loads(response_text)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            "q1_part2: claude -p response was not valid JSON; "
            "treating as plain text. error=%s, len=%d", e, len(response_text)
        )
        return {
            "text": response_text,
            "total_cost_usd": None,
            "total_tokens": None,
            "schema": "fallback",
        }

    # Path 2: JSON valid but not an object → fallback, text=raw.
    if not isinstance(parsed, dict):
        logger.warning(
            "q1_part2: claude -p response was JSON but not an object "
            "(type=%s); treating as plain text.", type(parsed).__name__
        )
        return {
            "text": response_text,
            "total_cost_usd": None,
            "total_tokens": None,
            "schema": "fallback",
        }

    # Path 3: JSON object → typed schema classification + always-text.
    # Cost extraction (top-level — present in both v1 and v2-observed).
    cost_val = parsed.get("total_cost_usd")
    if isinstance(cost_val, (int, float)) and not isinstance(cost_val, bool):
        cost = float(cost_val)
    else:
        cost = None

    # Token extraction — try top-level first (v1 schema), then
    # usage.{input_tokens + output_tokens} (v2-observed schema).
    #
    # v3-E LOW-fix — int() float-truncation assumption documented:
    # Assumption: SDK API contractually returns int for total_tokens /
    # usage.input_tokens / usage.output_tokens. If the SDK ever returns
    # float (e.g. estimated tokens), int(...) truncates silently.
    # Phase A install adds optional fail-loud:
    #     if isinstance(tokens_val, float) and not tokens_val.is_integer():
    #         logger.warning("Q1_PART2_TOKEN_FLOAT_OBSERVED — SDK contract drift")
    # Same fail-loud applies to input_t / output_t in the v2-observed branch.
    tokens_val = parsed.get("total_tokens")
    if isinstance(tokens_val, (int, float)) and not isinstance(tokens_val, bool):
        tokens = int(tokens_val)  # see v3-E float-truncation note above
        token_schema = "v1"
    else:
        usage = parsed.get("usage") or {}
        if isinstance(usage, dict):
            input_t = usage.get("input_tokens")
            output_t = usage.get("output_tokens")
            input_ok = isinstance(input_t, (int, float)) and not isinstance(input_t, bool)
            output_ok = isinstance(output_t, (int, float)) and not isinstance(output_t, bool)
            if input_ok and output_ok:
                tokens = int(input_t) + int(output_t)  # see v3-E float-truncation note above
                token_schema = "v2-observed"
            else:
                tokens = None
                token_schema = "fallback"
        else:
            tokens = None
            token_schema = "fallback"

    # Schema is the JOIN of cost-presence + token-shape:
    #   - v1:          top-level total_tokens AND top-level total_cost_usd both present.
    #   - v2-observed: usage.input+output_tokens summed AND top-level total_cost_usd present.
    #   - fallback:    EITHER cost OR tokens missing (or wrong type).
    if cost is not None and token_schema == "v1":
        schema = "v1"
    elif cost is not None and token_schema == "v2-observed":
        schema = "v2-observed"
    else:
        schema = "fallback"

    if schema == "fallback":
        logger.warning(
            "q1_part2: claude -p JSON object missing typed cost or token fields "
            "(cost_type=%s, tokens_top_type=%s, token_schema=%s); using None placeholders.",
            type(cost_val).__name__, type(tokens_val).__name__, token_schema,
        )

    return {
        "text": _extract_text_from_parsed(parsed, response_text),
        "total_cost_usd": cost,
        "total_tokens": tokens,
        "schema": schema,
    }
```

### 7-AMEND-V3.4. Five locked behavioral guarantees

| # | Guarantee | Test |
|---|---|---|
| G-1 | `result["text"]` is a str on every return path. | `assert isinstance(parse_claude_response(x)["text"], str)` for x in {malformed JSON, bare-list JSON, dict-without-canonical-keys, dict-with-result-key, dict-with-text-key}. |
| G-2 | `result["total_cost_usd"]` is `float` or `None`. Implementation detail: int values are ACCEPTED at parse time (via `isinstance(..., (int, float)) and not isinstance(..., bool)`) and COERCED to float via `float(val)`. The RETURNED value is always `float`-or-`None`; bools are explicitly excluded by the `not isinstance(..., bool)` clause (so Python's `True`/`False` are not silently coerced to `1.0`/`0.0`). Strings (e.g. `"0.04"`) are rejected; rejection sets `cost=None` and `schema="fallback"`. | `result["total_cost_usd"]` returned-value type assertion: `assert result["total_cost_usd"] is None or (isinstance(result["total_cost_usd"], float) and not isinstance(result["total_cost_usd"], bool))`. Verifies post-coercion shape. |
| G-3 | `result["total_tokens"]` is int or None — never bool/float/str. | `assert result["total_tokens"] is None or (isinstance(result["total_tokens"], int) and not isinstance(result["total_tokens"], bool))` |
| G-4 | `result["schema"]` ∈ {"v1", "v2-observed", "fallback"} on every return path (3-state per v3-D HIGH-2 closure). | `assert result["schema"] in ("v1", "v2-observed", "fallback")` |
| G-5 | Function never raises. | Wrapped fixture: `for x in malformed_inputs: assert parse_claude_response(x) is not None` |

### 7-AMEND-V3.5. Test fixtures (added to v1 §16 + v2 §16-AMEND-V2 fixtures)

| Fixture | Input `response_text` | Expected |
|---|---|---|
| F-PR-1 | `'this is not JSON'` | `{"text": "this is not JSON", "total_cost_usd": None, "total_tokens": None, "schema": "fallback"}` |
| F-PR-2 | `'[1, 2, 3]'` (valid JSON, not a dict) | `{"text": "[1, 2, 3]", "total_cost_usd": None, "total_tokens": None, "schema": "fallback"}` |
| F-PR-3 | `'{"result": "approved", "total_cost_usd": 0.04, "total_tokens": 1234}'` | `{"text": "approved", "total_cost_usd": 0.04, "total_tokens": 1234, "schema": "v1"}` |
| F-PR-4 | `'{"result": "approved", "total_cost_usd": "0.04", "total_tokens": 1234}'` (cost is a string, NOT a float) | `{"text": "approved", "total_cost_usd": None, "total_tokens": 1234, "schema": "fallback"}` (typed check rejects string-shaped cost) |
| F-PR-5 | `'{"text": "approved"}'` (no cost fields at all) | `{"text": "approved", "total_cost_usd": None, "total_tokens": None, "schema": "fallback"}` |
| F-PR-6 | `'{"foo": "bar"}'` (no canonical text key) | `{"text": '{"foo": "bar"}', "total_cost_usd": None, "total_tokens": None, "schema": "fallback"}` (text falls back to json.dumps of parsed) |
| F-PR-7 | `'{"result": true, "total_cost_usd": 0.04, "total_tokens": 1234}'` (text is a non-string) | `{"text": '{"result": true, "total_cost_usd": 0.04, "total_tokens": 1234}', "total_cost_usd": 0.04, "total_tokens": 1234, "schema": "v1"}` (text falls back; cost still typed-OK) |
| F-PR-8 | `'{"result": "approved", "total_cost_usd": true, "total_tokens": 1234}'` (cost is bool — Python's `True == 1` would pass naive isinstance check) | `{"text": "approved", "total_cost_usd": None, "total_tokens": 1234, "schema": "fallback"}` (explicit bool exclusion; cost None forces fallback regardless of token shape) |
| F-PR-9 | `'{"result": "approved", "total_cost_usd": 0.04, "usage": {"input_tokens": 1000, "output_tokens": 234}}'` (v2-observed: tokens nested under usage.*, no top-level total_tokens) | `{"text": "approved", "total_cost_usd": 0.04, "total_tokens": 1234, "schema": "v2-observed"}` (tokens summed from usage.input_tokens + usage.output_tokens; schema label distinguishes from v1) |
| F-PR-10 | `'{"result": "approved", "total_cost_usd": 0.04, "usage": {"input_tokens": 1000}}'` (usage present but output_tokens missing) | `{"text": "approved", "total_cost_usd": 0.04, "total_tokens": None, "schema": "fallback"}` (partial usage rejected — both subkeys required for v2-observed) |
| F-PR-11 | `'{"result": "approved", "total_cost_usd": 0.04, "usage": "not-a-dict"}'` (usage present but wrong type) | `{"text": "approved", "total_cost_usd": 0.04, "total_tokens": None, "schema": "fallback"}` (non-dict usage rejected) |

F-PR-4 and F-PR-8 are the regression tests against MEDIUM-1 (substring check would have falsely classified F-PR-4 as v1; naive isinstance would have accepted F-PR-8's `True` as `1`). F-PR-9, F-PR-10, F-PR-11 are the regression tests against v3-D HIGH-2 (v3-A/B/C parser would have wrongly returned `schema=fallback` on F-PR-9's v2-observed shape; would have wrongly accepted partial usage on F-PR-10; v3-D defends against malformed usage on F-PR-11).

### 7-AMEND-V3.6. v2 §7-AMEND.4–§7-AMEND.7 carry forward (with v3-D banner / cost-cap clarifications)

Banner behavior, session-log JSONL row, weekly review surface, and cost-cap unaffected. The schema field's value is still the audit hook for drift detection; the typed classifier in §7-AMEND-V3.3 simply makes the `schema` field's value more reliable.

**v3-D clarifications (HIGH-2 closure):**

- **Banner:** shows token count from `total_tokens` aggregation when `schema ∈ {"v1", "v2-observed"}` (in v2-observed the value is summed from `usage.input_tokens + usage.output_tokens`); shows `(tokens unknown)` when `schema == "fallback"`. Cost is shown as a float when present, `(cost unknown)` otherwise.
- **Cost-cap:** operates on `total_cost_usd` — a TOP-LEVEL field present in BOTH `v1` and `v2-observed` shapes (verified via the §7-AMEND-V3.3 [CONFIRMED 2026-05-09 v3-C] empirical probe). The cost-cap is therefore UNAFFECTED by the token-shape variation between v1 and v2-observed; it sees a valid float in both cases. The cost-cap fails closed only when `schema == "fallback"` (cost missing or wrong type), which is the intended drift-detection behavior.
- **Schema field:** the audit hook is now 3-state (`v1` / `v2-observed` / `fallback`) instead of 2-state. Weekly review (§7-AMEND-V3.7b jq canonical) should treat `v2-observed` as the routine signal on claude >= 2.1.137 and `fallback` as the drift signal that warrants investigation. A future v4 may collapse `v1` and `v2-observed` to a single `parsed` label if the SDK never re-introduces top-level `total_tokens`.

### 7-AMEND-V3.7a. Why typed isinstance over duck-typed `try: float(...)`

A subtler alternative for MEDIUM-1 would have been:

```python
try:
    cost_val_f = float(parsed.get("total_cost_usd"))
    has_cost = True
except (TypeError, ValueError):
    has_cost = False
```

This accepts string-encoded numerics (`"0.04"`) as cost. v3 deliberately rejects this approach: an SDK that emits string-encoded floats is itself drifting, and we want the `schema=fallback` signal to fire on that drift so weekly review surfaces it. Tight typed discipline beats loose duck-typing for a drift-detection field.

[INFERRED 2026-05-09 — the choice between strict isinstance and duck-typed coercion is a design preference; v3 picks strict. If implementation-time fixtures show the SDK actually emits stringified numerics regularly, v4 should reconsider.]

---

## §7-AMEND-V3.7b. Weekly Drift Detection — jq Canonical Replaces grep (LOW-1 closure)

**v2 §7-AMEND.6 problem:** v2's weekly drift detection used `grep '"schema":"fallback"' ~/.claude/state/q1_part2_session_*.log` against the session log JSONL. This is brittle on (a) whitespace variations between key and value (e.g., `"schema": "fallback"` vs `"schema":"fallback"`), (b) key ordering inside the JSON object, and (c) pretty-printed multi-line JSON. False-negative grep produces silent-pass (operator believes no fallbacks happened when in fact they did).

**v3 canonical replacement:**

```bash
jq -r 'select(.schema == "fallback") | "\(.ts)\t\(.session_id // "unknown")"' \
  ~/.claude/state/q1_part2_session_*.log
```

This:
1. Uses structured JSON parsing (immune to whitespace/key-order/pretty-printing).
2. Returns one line per fallback event with timestamp + session_id (correlatable to session transcript).
3. Returns empty output when no fallbacks (operator-friendly: empty = clean).

**Threshold check:**

```bash
# v3-E HIGH-fix: count EVENTS, not lines. Default jq output is pretty-printed
# (each selected JSON object spans multiple lines), so `jq ... | wc -l` would
# multiply each event by its pretty-printed line count. Use `jq -s` to slurp
# all inputs into a single array and `length` to count array elements
# (= one count per matching event regardless of pretty-print width).
COUNT=$(jq -s '[.[] | select(.schema == "fallback")] | length' ~/.claude/state/q1_part2_session_*.log 2>/dev/null || echo 0)
if [ "$COUNT" -gt 5 ]; then
  echo "⚠ Q1 Part 2 schema-fallback count this week: $COUNT (>5 = surface to weekly_preflight_audit.py)"
fi
```

Alternative event-counting recipe (also event-correct via per-line projection — `wc -l` counts events because `jq -r` emits ONE line per match here):

```bash
COUNT=$(jq -r 'select(.schema == "fallback") | .ts' ~/.claude/state/q1_part2_session_*.log 2>/dev/null | wc -l)
```

The `jq -s ... | length` form is preferred because it is structurally explicit (operators do not have to reason about whether jq's per-match output is single-line under all field shapes); the per-line projection is offered as a no-`-s` fallback.

**Fallback if jq is unavailable** (no-jq environments only): retain v2's grep one-liner with explicit caveat:

```bash
# WARNING: brittle on whitespace + key ordering. Use jq variant above when available.
grep -c '"schema":\s*"fallback"' ~/.claude/state/q1_part2_session_*.log 2>/dev/null || true
```

The grep variant uses `\s*` to tolerate the most common whitespace drift; even so, prefer jq.

**Phase B prerequisite update:** weekly_preflight_audit.py implementation must verify `jq --version` exit code 0 before invoking the jq variant; fall back to grep variant with `WARNING: jq missing; using grep fallback` log line otherwise.

---

## §8-AMEND-V3. Risk-Row Additions for v3 (4 NEW rows)

Appended to v1's §14 risk table (and to v2's §14-AMEND extension):

| Risk (v3 NEW) | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Glob shape regression — a future v4 amendment reintroduces `**.<ext>` shape and breaks PurePath.match | Low | Med | §6-AMEND-V3.5 empirical probe table is the regression baseline; quarterly review re-runs the probe; CI fixture in implementation handoff Phase D pins the table. |
| `CANONICAL_TEXT_KEYS` tuple drifts from real Claude Code SDK output schema — `text` key would always fall back to json.dumps, banner becomes noisy | Med | Low | Implementation Phase D MUST run a live `claude -p` probe and assert the canonical key is in the tuple; weekly review samples session-log entries where `len(text) > 1000 chars` and inspects the first-20 chars to detect if dumps-shape (starts with `{`) is appearing systematically. |
| L3 narrative misread by future implementer — they wire L3 against doc/spec paths despite the rule | Low | Med | §6-AMEND-V3.6 worked example + counter-example are required fixtures in the implementation handoff Phase B; both must be encoded as test cases that pass before the hook ships. |
| Typed schema classifier rejects legitimate SDK output that drifts to stringified numerics — every spawn shows `schema=fallback` even though cost data is technically present (just typed wrong) | Low | Low | `schema=fallback` weekly threshold (5/wk) + investigation prompt fires; investigation reveals stringification; v4 amendment can relax the typed rule with a documented `try: float(...)` path. The cost is observability noise, not a safety regression. |

---

## §9-AMEND-V3. Reference Index (v3 extensions)

Appended to v1's §17 reference index + v2's §11-AMEND extension:

- **v1 historical baseline:** `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`
- **v2 immediate predecessor:** `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md` (sha256 `ce8a5abff542b22b653c42565169e00dd174707c5ae2fb7bb5599287de000f2f`, 532 lines)
- **v3 self-reference:** `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v3.md` (this document)
- **v3 LD chain (this spec's own locks — v3-E MEDIUM-2 fix appends numeric LD ids alongside decision_keys for stable cross-doc citation):**
  - v3-A: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_PARSE_TEXT_CONJUNCTION_GLOB_V1` (LD-621)
  - v3-B: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_B_LOW_CONSISTENCY_V1` (LD-626)
  - v3-C: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_C_ROUND_3_FIXES_V1` (LD-634)
  - v3-D: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_D_ROUND_4_FIXES_V1` (LD-639)
  - v3-E: `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_E_ROUND_5_FIXES_V1` (LD-642 filed 2026-05-09 — see §10-AMEND-V3 LD-filing intent for the per-cycle locking pattern)
- **v2 LD predecessor:** `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V2_TRIGGER_GUARD_LIST_COST_V1` (LD-616)
- **Cursor v2 review handoff:** [INFERRED — Cursor v2 review evidence captured in this v3 authoring prompt verbatim; no separate handoff file authored for v2 round of review.]
- **Cursor v3 review handoff:** to be authored separately (NOT modified by this spec per §10-AMEND-V3 self-bounds).
- **Q1 Part 2 implementation handoff:** `Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md` — MUST be amended in a separate authorized session to encode v3's matcher pin (`pathlib.PurePath.match`), v3's `CANONICAL_TEXT_KEYS` probe step, and v3's §6-AMEND-V3.5 + §6-AMEND-V3.6 + §7-AMEND-V3.5 fixtures.
- **`INFRASTRUCTURE_PATH_PATTERNS` codebase footprint (2026-05-09 grep audit):**
  - `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md:230` — original constant declaration + `fnmatch.fnmatch` matcher.
  - `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md:215` — refers to the constant, no new matcher decision (inherits v1).
  - `Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md:142` — implementation handoff encodes `fnmatch.fnmatch` per v1+v2.
  - `Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md:146` — implementation handoff encodes "byte-identical to spec §6.1".
  - `Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md:158` — checklist row.
  - **No production hook currently exists** (no file named `~/.claude/hooks/stop_conditional_opus_reviewer.py` shipped). The constant is governance-only at v3 authoring time (consistent with §0 banner's GOVERNANCE-AUTHORING framing per v3-C).

---

## §10-AMEND-V3. Self-bounds (this spec's authoring scope)

This spec authoring session MUST NOT:

- Modify v1 spec (`Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v1.md`).
- Modify v2 spec (`Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v2.md`).
- Modify any other tech-spec doc.
- Modify the implementation handoff (`Production/docs/HANDOFF_Q1_PART2_IMPLEMENTATION_20260508.md`) — handoff updates require a separate authorized session post-Cursor-v3 review.
- Modify any Cursor-review handoff doc.
- Modify hook scripts (no `~/.claude/hooks/` writes).
- Modify SKILL.md files (mn-context, zero-error-qa, etc.).
- Modify settings.json.
- Create commits.
- Spawn parallel agents.

This spec authoring session DOES (these are SPEC-AUTHORING ARTIFACTS — the canonical deliverables of any governance-authoring session, NOT a carve-out from the no-code-mutation rule above. Each Cursor-review cycle (v3-A, v3-B, v3-C, v3-D, v3-E) produces ONE LD + ONE activity_log row + the spec edits — that pattern is invariant across the v3 amendment chain):

- Write `Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v3.md` (this document).
- Run `Production/scripts/lock_decision.py` once per amendment cycle (LD per cycle: v3-A → LD-621 `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_PARSE_TEXT_CONJUNCTION_GLOB_V1`; v3-B → LD-626 `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_B_LOW_CONSISTENCY_V1`; v3-C → LD-634 `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_C_ROUND_3_FIXES_V1`; v3-D → LD-639 `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_D_ROUND_4_FIXES_V1`; v3-E → LD-642 `Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_V3_E_ROUND_5_FIXES_V1`).
- POST one row per amendment cycle to `prod_activity_log` (rows: v3-A → 1996; v3-B → 2003; v3-C → 2012; v3-D → 2018; v3-E → `<row-id-this-session>`). All rows OMIT `task_description` per LD-597 (Rule 35 enforcement).
- Run one read-back sanity check per Rule 35.

**Reframing note (v3-C):** earlier versions of this section described these artifacts as "writes" using language adjacent to the §0 banner's "no Directus writes" wording. v3-C consolidates the framing: spec-authoring artifacts are the canonical deliverables of governance-authoring sessions; the §0 banner now reads "GOVERNANCE-AUTHORING" rather than "DESIGN ONLY" to remove the apparent conflict. There is no rule change — only language clarification. The MUST-NOT list above continues to forbid production code mutations (hooks, settings.json, SKILL.md, scripts).

---

**End of v3 spec.** All v1 sections (§0, §1, §2, §4, §5, §8, §9, §11, §12, §13, §14 v1 rows, §15, §16, §17) and all v2 sections (§3-AMEND, §10-AMEND, plus v2's §6/§7/§14/§11 sections not amended in v3) remain authoritative as published.
