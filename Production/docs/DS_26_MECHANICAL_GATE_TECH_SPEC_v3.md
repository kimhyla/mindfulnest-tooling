# DS-26 Mechanical Gate — Tech Spec v3

**Status:** GOVERNANCE-AUTHORING. No production code (no hook installs, no SKILL.md changes, no settings.json mutations). Spec-authoring artifacts (LD filing in `prod_locked_decisions`; activity_log POST in `prod_activity_log`) ARE the deliverables of governance-authoring sessions per the project-wide Rule 35 / DS-29 discipline — these are NOT production code mutations. Implementation (hook installation + SKILL.md updates) is deferred to a future Terminal CLI session under a separate authorization.
**Authors:** v3 amendment authored 2026-05-09, gallant-bouman-804b4f worktree, in response to Cursor round-2 cross-review of v2 (4 findings: 2 HIGH + 2 MEDIUM; 1 LOW closed via §0.3 Section ID Legend in v3-B sub-pass — see §0.1 v3-B row).
**Source authority:** zero-error-qa SKILL.md DS-26 (discipline-only); LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (id=578); LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V2_TOOL_NAME_REGEX_FAKERY_FIX_V1` (id=614 — v2's authority); LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V3_VERIFY_FAIL_MODE_RECONCILE_REF_REGEX_V1` (this v3's own authority); HANDOFF_TEMPLATE_v1.md.
**Originating incident:** unchanged from v1 — Terminal A on `HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`, 2026-05-08.
**Tracking blocker:** `prod_blockers` row `DS_26_MECHANICAL_GATE_PENDING` (this spec is the design artifact resolving it; v3 supersedes v2 in the four amendment areas below; v2 supersedes v1; both v1 and v2 are preserved verbatim by reference).
**v2 sha256 (verified at v3 author time):** `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (374 lines).

**v3 supersedes v2 in the following sections only.** All other v2 content is preserved by reference (see §0.2 v3 scope below). When v2 and v3 disagree, v3 prevails. When v1 and v3 disagree, v3 prevails.

---

## §0 Operating Mode

Unchanged from v2 (GOVERNANCE-AUTHORING per §0 status banner; multipass discipline; Rule 24 confidence tags; DS-19 standing escape hatches; DS-26 itself is active on this session). v3-D reframing note: prior v3 drafts said "DESIGN ONLY" which conflicted with the v3-A/v3-B/v3-C sub-sessions filing LDs in `prod_locked_decisions` and POSTing to `prod_activity_log`. Per the project-wide Rule 35 / DS-29 discipline, governance-authoring sessions DO file LDs + activity-log rows — those are spec-authoring artifacts, not production code mutations. Production code (hooks, SKILL.md, settings.json) remains untouched until a separate Terminal CLI implementation session is authorized.

---

## §0.1 v3-A Changelog (top-of-file, supersedes v2 entries below)

| Row | Date | Change | Source authority |
|---|---|---|---|
| **v3-F** | **2026-05-09** | **Round-6 prose-alignment sub-pass (no version bump; spec remains v3). **MEDIUM (§3.4.1-A.3 internal drift vs v3-E):** the normative docstring under `PRECISE REGEX MODE` and the canonical fenced code in §3.4.1-A.3 + §6.0-A still described v3-D’s single-line MODE-2 “junk rule” (column-0 / `m.end() != len(stripped)` branching) even though v3-E already tightened implementation semantics: **MODE 2 (`.search()`) runs only when `'\n' in evidence_source`** (multi-line context); **single-line evidence is bound to MODE 1 (`.fullmatch` on stripped)** and `fullmatch` failure → **UNVERIFIED** (no `.search` on single-line). v3-F replaces all stale v3-D MODE-2 prose with this v3-E canonical wording, updates both fenced code blocks to match, and reconciles **F-FRAG-1** / **F-FRAG-2** fixture rows plus the F-FRAG explanatory note: F-FRAG-2 is multi-line per **T20** (`Per LD-578: see decision` + newline + continuation). **§3.4.1-A.6:** canonical-snippet line/byte count and SHA256 anchor recomputed after the fenced-body edit (prior v3-D / v3-E anchors preserved for lineage in the same subsection). v1 + v2 specs NOT modified.** | **DS-26 Mechanical Gate follow-up (Phase B / Cursor); v3-E authority `DS_26_MECHANICAL_GATE_TECH_SPEC_V3_E_ROUND_5_FIXES_V1` (LD-646); normative contract aligned to `Production/scripts/hooks/ds26_gate_check.py` v3-E matcher** |
| **v3-D** | **2026-05-09** | **Round-4 cleanup sub-pass (no version bump; spec remains v3). Triggered by Cursor round-4 review surfacing 2 REAL CORRECTNESS BUGS in the anti-fakery code (not wording) plus 1 recurring MEDIUM governance reframing. **HIGH-1 (verify_gate_evidence row classification bug):** the `return row is not None` expression in §3.4.1-A.3 + §6.0-A code blocks contradicted the docstring HTTP/API outcome mapping table — empty dict `{}` and empty list `[]` are NOT None, so a malformed Directus response (404 mapped to `{}` by some client wrappers; list-endpoint empty `[]`) would have falsely classified as VERIFIED EVIDENCE. v3-D rewrote the row-classification path to enforce 4 explicit branches (None / empty dict / empty list / truthy non-empty) matching the contract. **HIGH-2 (precise regex "fully parse" vs `.search` substring match):** the contract claimed "If broad sentinel matches BUT precise regex fails to fully parse → UNVERIFIED" but the code used `DIRECTUS_REF_RE.search()` which accepts partial substring matches anywhere (e.g., `LD-578xyz` would have parsed as `LD-578` and queried row 578 against malformed evidence). v3-D pins a two-mode policy: MODE 1 `.fullmatch()` on stripped evidence first (single-line citation must match whole token); MODE 2 `.search()` fallback only when MODE 1 None (for embedded refs in multi-line/prose context). New fixtures F-FRAG-1 (single-line compound malformed `LD-578xyz` → UNVERIFIED) + F-FRAG-2 (embedded `Per LD-578: see decision text` → PASS) pin the contract. **MEDIUM (DESIGN-ONLY vs in-session LD writes recurring):** §0 status banner reframed from "DESIGN ONLY" to "GOVERNANCE-AUTHORING" — same project-wide reframing applied to other tech-specs that file LDs + activity-log rows in their own sub-sessions; spec-authoring artifacts ARE the deliverables of governance-authoring sessions, not production code mutations. Production code (hooks, SKILL.md, settings.json) remains untouched. **Code-block audit:** verified §3.4.1-A.3 + §6.0-A function bodies remain normatively identical (both updated; both pass post-fix audit). **Canonical snippet SHA256 anchor recomputed:** old `ce8c4819dde66d82de024d7dfedee4f915249490100589760eeb6b596ec74cf1` → new `424300ba22a1440256e9ab4104566edd9de738bd85584773bd48e7264c3c895b` (183 lines, 10252 bytes UTF-8); old anchor preserved in §3.4.1-A.6 for audit lineage. v1 + v2 specs NOT modified. v2 sha256 still `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (drift verified post-edit).** | **LD-DS_26_MECHANICAL_GATE_TECH_SPEC_V3_D_ROUND_4_FIXES_V1 (this v3-D sub-pass's own LD; id=641); Cursor round-4 review notes embedded in this session's handoff prompt; LD-619 (v3-A predecessor); LD-630 (v3-B predecessor); LD-632 (v3-C predecessor)** |
| **v3-C** | **2026-05-09** | **VERIFY-AND-REMEDIATE sub-pass (no version bump; spec remains v3). Triggered by Cursor round-3 review re-surfacing 5 findings v3-B claimed to close. v3-C performed a mandatory verification phase BEFORE applying any edits — for each Cursor round-3 finding, read the cited line range and compared to v3-B's claim. **Verification verdict (documented in disagreement protocol):** all 5 fixes v3-B claimed for the substantive findings (HIGH-1 LOW-deferred sweep at §0.1 + line 556; HIGH-2 §0.3 §6 row repair at line 69; MEDIUM-1 cannot-simulate-offline tightening at line 344; MEDIUM-2 LD-invariant docstring + R-V3-LD-INVARIANT row at lines 183-198 + 539; LOW F4 prose pipe escaping standardization at line 99) ARE actually present in the spec at v3-C author time. Cursor's round-3 line citations (lines 24-29, 61-74, 294-297, 183-187, 99) appear to reference an OLDER snapshot than current spec — citations are stale, fixes are landed. v3-C therefore did NOT redundantly re-apply landed fixes; instead documented the verification record + disagreement note here. **However, v3-C DID find 4 stale "byte-identical" / "byte-canonical" references that v3-B's "Two LOWs closed" claim missed:** line 37 (§0.2 v3 in scope HIGH-1 bullet — "Pin byte-identical helper code"), line 49 (§0.2 v3 out of scope bullet — "byte-identical to v3 §3.4.1-A's helper"), line 123 (§3.4.1-A intro — "byte-canonical source"), line 535 (§7 R-V3-H1 mitigation cell — "body byte-identical in §3.4.1-A.3 AND §6.0-A"). v3-C surgically replaced all 4 with "normatively identical" / "normatively canonical source" + cross-reference to §3.4.1-A.6 SHA256 anchor — bringing the entire spec into consistency with the §3.4.1-A.3 + §6.0-A + §0.3 normative-vs-byte-identical framing. Net change: 4 prose edits + 1 changelog row (this one) + 1 §12 changelog row + 1 §14 authorship entry. v1 + v2 specs NOT modified. v2 sha256 still `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (drift verified post-edit).** | **LD-632 `DS_26_MECHANICAL_GATE_TECH_SPEC_V3_C_VERIFY_AND_REMEDIATE_V1` (this v3-C sub-pass's own LD); Cursor round-3 review notes embedded in this session's handoff prompt; LD-619 (v3-A predecessor); LD-630 (v3-B predecessor)** |
| **v3-B** | **2026-05-09** | **Comprehensive cleanup sub-pass (no version bump; spec remains v3). Closes 5 follow-on items: (1) multi-section LOW-deferred consistency sweep — every "1 LOW deferred" / "intentionally deferred" reference re-narrated to "1 LOW closed via §0.3 Section ID Legend"; (2) §0.3 legend §6 row repaired (replaced all-`n/a` row with meaningful "v1: n/a (no §6 in v1) | v2: §6.0-A introduced (Updated detection algorithm) | v3: §6.0-A preserved + verify_gate_evidence body normatively identical to §3.4.1-A.3" content); (3) Cursor round-3 MEDIUM "cannot simulate offline" overclaim tightened in §3.4.1-A.5 to "silent text-presence fallback is closed; verification gaps surface visibly via UNVERIFIED_DIRECTUS_REF rather than silently passing — residual risks (client/hook bugs, broad-vs-precise misclassification, spoofed checklist plumbing) NOT eliminated, only made visible"; (4) Cursor round-3 MEDIUM `get_item` 404-vs-exception normative rule pinned in §3.4.1-A.3 + §6.0-A docstrings via explicit HTTP/API outcome mapping table (`None`/empty/404 ⇒ FAIL_EVIDENCE_MISSING; raised exception ⇒ PROBE_FAILED → UNVERIFIED_DIRECTUS_REF); (5) Cursor round-3 MEDIUM LD-shorthand mapping invariant documented at §3.4.1-A.2 (`LD N → prod_locked_decisions.id = N` is an explicit assumption holding for entire project history; if a future migration breaks the invariant, `_resolve_collection_and_row` MUST switch to `decision_key` lookup) and tracked as new §7 row R-V3-LD-INVARIANT. Two Cursor round-3 LOWs also closed: (6a) F4 prose pipe escaping standardized (table cell uses `\|` markdown escape; code blocks use plain `|`; pin one form per render context); (6b) "byte-identical" claim replaced with "normatively identical" + SHA256-of-canonical-snippet anchor for audit drift checks. v1 + v2 specs NOT modified. v2 sha256 still `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (drift verified post-edit).** | **LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V3_B_CONSISTENCY_AND_ROUND_3_FIXES_V1` (this v3-B sub-pass's own LD); Cursor round-3 review notes embedded in this session's handoff prompt; LD-619 (v3-A predecessor)** |
| **v3-A** | **2026-05-09** | **Four surgical amendments authored in response to Cursor round-2 cross-review of v2 (2 HIGH + 2 MEDIUM; LOW closed via §0.3 — see v3-B row above). HIGH-1 = `verify_gate_evidence` single normative fail mode (reconcile §3.4.1-A vs §6.0-A "except branches" conflict — choose: offline / Directus failure ⇒ surface UNVERIFIED_DIRECTUS_REF checklist entry; never silent text-presence fallback for Directus refs; pin in BOTH §3.4.1-A AND §6.0-A; normatively identical helper). HIGH-2 = anti-fakery narrative aligned with online-only qualifier (rewrite §3.4.1-A.1 to explicitly state online-only guarantee + offline UNVERIFIED surfacing). MEDIUM-1 = §3.4-A.1 fixture F4 reconciled — adopt the permissive alternation regex `gate(?:s\|\(s\))?` as the canonical implementation form, F4 now expects YES match, removing the contradiction between fixture and adjacent note. MEDIUM-2 = `DIRECTUS_REF_RE` broadened to cover `LD\s*-?\s*\d+`, `prod_\w+\s+(?:id\s*=\s*\|row\s*\|/)\d+`, `items/prod_\w+/\d+`; new fixture rows F11-F14 added; Directus-ish references that match a broad detector but fail full parse surface UNVERIFIED_DIRECTUS_REF (no silent text-presence fallback). LOW closed via §0.3 Section ID Legend (added in v3-A authoring pass; cross-section consistency completed in v3-B).** | **LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V3_VERIFY_FAIL_MODE_RECONCILE_REF_REGEX_V1` (id=619); Cursor round-2 review notes embedded in this session's handoff prompt** |
| v2-A | 2026-05-08 | Four surgical amendments responding to Cursor v3 cross-review of v1: HIGH-1 (cross-tool name normalization), HIGH-2 (declaration regex escaping bug fix), MEDIUM-1 (legacy fallback noise reduction), MEDIUM-2 (anti-fakery hardening via Directus row verification). 4 new §7 risk rows (R-V2-A1, R-V2-B2, R-V2-C1, R-V2-D2). | LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V2_TOOL_NAME_REGEX_FAKERY_FIX_V1` (id=614) |
| v1 | 2026-05-08 | Initial design — dual-Opus debate, §3 Step 2.5c surface, §4 debate verbatim, §5 resolution, §6 algorithm, §7 pre-execution variant, §10 pre-implementation gates, §11 risk assessment, §13 testing plan, §14 reference index. | LD 578 + zero-error-qa DS-26 |

**LOW closed in v3 (was deferred at first authoring pass; reopened per Kim's "no LOW deferrals" directive):** Cursor round-2 flagged a numbering discrepancy between v2 §7 (Risk Assessment) and v1 §11 (also Risk Assessment) — v2 added rows under §7 while preserving v1 §11 by reference, creating onboarding risk of editing the wrong "§11" mentally. v3 closes this NOT via cross-document renumbering (which would break v1/v2 historical anchors) but by adding a **Section ID Legend (§0.3 below)** that disambiguates which "§N" is meant in any cross-doc citation. Section headers in v3 §7 and v3 §11 also self-document the lineage in their titles ("v3 — extended; v1 §X + v2 §Y rows preserved").

---

## §0.2 v3 Scope (supersedes v2 §0.2 only in the listed sections; rest of v2 §0.2 preserved)

**v3 in scope (SURGICAL amendments only — v2 architecture preserved):**

- **HIGH-1 (verify_gate_evidence single normative fail mode):** v3 §3.4.1-A + §6.0-A — eliminate the divergence between v2 §3.4.1-A (`except Exception ⇒ return False`) and v2 §6.0-A (`except Exception ⇒ return text_presence_check(...)`). Pick ONE: on Directus offline / get_item failure ⇒ surface `UNVERIFIED_DIRECTUS_REF` checklist entry (visible degradation), NOT silent text-presence fallback. Pin **normatively identical** helper code in BOTH sections (audit anchor: SHA256 in §3.4.1-A.6; v3-C correction — earlier draft said "byte-identical" which was relaxed to "normatively identical" in v3-B).
- **HIGH-2 (anti-fakery narrative aligned with online-only qualifier):** v3 §3.4.1-A.1 — rewrite the v2 narrative claim "v2 closes this for Directus references — the row must actually exist when queried" to be precise about the online-only guarantee: "v3 closes this for Directus references **WHEN ONLINE**; when offline or the Directus probe fails, the gate surfaces `UNVERIFIED_DIRECTUS_REF` rather than silently falling back to text-presence." Document trade-off explicitly: anti-fakery is online-only and intentionally fails-visibly when offline.
- **MEDIUM-1 (fixture F4 vs canonical regex reconciliation):** v3 §3.4-A.1 — pick the permissive alternation form `gate(?:s|\(s\))?` as the canonical regex (already recommended by v2 §3.4-A.2). Update fixture F4 to expect YES match (input `HALT gate scan: 0 gate(s) detected`). Phase B unit tests align with the permissive form. The simpler `gate(s)?` form is documented as a non-canonical alternative.
- **MEDIUM-2 (DIRECTUS_REF_RE broadened to handle real handoff phrasing):** v3 §3.4.1-A — broaden `DIRECTUS_REF_RE` to cover at minimum: `LD\s*-?\s*\d+` (LD shorthand with optional hyphen), `prod_\w+\s+(?:id\s*=\s*|row\s*|/)\d+` (canonical with `id=`, `row`, or `/` separator), `items/prod_\w+/\d+` (REST-path style). Add fixture rows F11-F14. When a "Directus-ish" reference is detected by a broad sentinel (`BROAD_DIRECTUS_HINT_RE`) but the precise regex fails to fully parse, the gate surfaces `UNVERIFIED_DIRECTUS_REF` — never silent text-presence fallback.

**v3 out of scope (preserved verbatim from v2 / v1):**

- v2 §0 (Operating Mode) — preserved.
- v2 §3.4-A (Declaration Parser Regex HIGH-2 from v2) — preserved EXCEPT §3.4-A.1 fixture F4 row + canonical-regex selection (this v3 makes the permissive form canonical; fixture F4 reconciled).
- v2 §3.6-A (Legacy Fallback Noise Reduction MEDIUM-1 from v2) — preserved verbatim.
- v2 §3.7-A (Cross-Tool Name Normalization HIGH-1 from v2) — preserved verbatim.
- v2 §3.4.1-A (Anti-Fakery Hardening MEDIUM-2 from v2) — preserved EXCEPT v3-A HIGH-1 / HIGH-2 / MEDIUM-2 surfaces (verify_gate_evidence body, narrative, regex broadening).
- v2 §6.0-A (Updated §6 Detection Algorithm) — preserved EXCEPT verify_gate_evidence body now **normatively identical** to v3 §3.4.1-A's helper (HIGH-1 fix; v3-C correction — see §3.4.1-A.6 SHA256 anchor for audit drift checks).
- v2 §7 (Risk Assessment — 8 v1 rows + 4 v2 rows) — preserved; v3 ADDS 5 rows (R-V3-H1, R-V3-H2, R-V3-M1, R-V3-M2 from v3-A; R-V3-LD-INVARIANT from v3-B).
- v2 §11 (Reference Index) — preserved; v3 extends.
- v2 §12 (Changelog) — v3 entry appended.
- v2 §13 (Testing Plan — T1-T14) — preserved; v3 ADDS T15-T18.
- v2 §14 (Authorship Trail) — v3 entry appended.

---

## §0.3 Section ID Legend (NEW in v3 — closes LOW finding from Cursor round-2)

When citing a section ID across docs/handoffs/PRs/Cursor reviews, **always disambiguate version**:

| Section ID | v1 meaning | v2 meaning | v3 meaning |
|---|---|---|---|
| §3 | Step 2.5c surface (verbatim) | preserved | preserved |
| §3.4-A | n/a | Declaration parser regex (HIGH-2 fix) | preserved + F4 reconciled |
| §3.4.1-A | n/a | Anti-fakery hardening (MEDIUM-2 fix) | rewritten for HIGH-1+HIGH-2+MEDIUM-2 |
| §3.6-A | n/a | Legacy fallback noise reduction | preserved |
| §3.7-A | n/a | Cross-tool name normalization (HIGH-1 fix) | preserved |
| §6.0-A | n/a (no §6 in v1) | §6.0-A introduced (Updated detection algorithm) | §6.0-A preserved + verify_gate_evidence body normatively identical to §3.4.1-A.3 (single normative source of truth; SHA256-anchored — see §3.4.1-A.6 for canonical-snippet anchor) |
| §7 | Pre-execution variant | Risk Assessment (renumbered from v1 §11) | Risk Assessment extended |
| §11 | **Risk Assessment** | Reference Index (renumbered from v1 §14) | Reference Index extended |
| §13 | n/a | Testing Plan T1-T14 | extended T15-T18 |
| §14 | Reference Index | Authorship Trail (renumbered from v1 §10) | extended |

**Rule for citers:** when referring to a v3 section, write `v3 §N`. When referring to a v1 or v2 section that v3 preserved by reference, write `v1 §N` or `v2 §N` explicitly — never bare `§N`. v3 section headers also self-document lineage in their titles.

---

## §3.4-A.1 v3 Amendment — Canonical Regex Selection + Fixture F4 Reconciliation (MEDIUM-1 fix)

**v2 defect (Cursor round-2 finding MEDIUM-1):** v2 §3.4-A.1 row F4 expects the input `HALT gate scan: 0 gate(s) detected` to YES-match the canonical regex `gate(s)?`, but the adjacent F4-nuance note correctly states that `gate(s)?` cannot consume literal parentheses in the input. The fixture row contradicts the adjacent note within the same table.

**v3 resolution:** adopt the **permissive alternation form** `gate(?:s|\(s\))?` as the **canonical** regex used in implementation. v2 already noted this form in §3.4-A.2 as recommended; v3 promotes it from "recommended alternative" to "canonical". Fixture F4 now correctly resolves to YES under the permissive canonical form.

```python
# v3 canonical declaration regex (promoted from v2's "permissive alternation form")
DECLARATION_RE = re.compile(
    r"(?i)HALT\s+gate\s+scan\s*:\s*(\d+)\s+gate(?:s|\(s\))?\s+detected",
)
```

### §3.4-A.1 (v3-revised) Unit-test fixture list — F4 reconciled

| # | Input | Expected match (canonical v3 regex) | Captured count |
|---|---|---|---|
| F1 | `HALT gate scan: 5 gates detected` | YES | `5` |
| F2 | `HALT gate scan: 1 gate detected` | YES | `1` |
| F3 | `HALT gate scan: 0 gates detected` | YES | `0` |
| F4 | `HALT gate scan: 0 gate(s) detected` | **YES (v3 — canonical regex is now the permissive alternation form `gate(?:s\|\(s\))?` which DOES match the literal-parens form). v3-B note: the `\|` inside this prose cell is a markdown table-pipe escape required by the renderer; the equivalent regex inside a fenced code block (lines 86-90 above) uses a plain `|` because code-block content is not interpreted as table syntax. Pin one form per render context — DO NOT mix.** | `0` |
| F5 | `halt gate scan: 3 gates detected` (lowercase) | YES (case-insensitive flag) | `3` |
| F6 | `HALT gate scan : 2 gates detected` (extra spaces) | YES | `2` |
| F7 | `HALT gate scan: 12 gates detected` (multi-digit) | YES | `12` |
| F8 | `No HALT gates declared` | NO | n/a |
| F9 | `HALT gate scan: gate detected` (missing number) | NO | n/a |
| F10 | `HALT gate scan completed: 3 gates detected` (extra word) | NO (strict match — colon must directly follow `scan`) | n/a |

**v3 reconciliation note (replaces v2 F4 nuance):** the v3 canonical regex `gate(?:s|\(s\))?` parses as: literal `gate` + optional non-capturing alternation of (`s` OR literal `(s)`). It matches both:

- `gates` (canonical plural)
- `gate(s)` (legacy literal-parens form)
- `gate` (singular — the entire alternation group is optional)

The simpler form `gate(s)?` (matches `gate` or `gates` only — not the literal-parens form) is documented as a non-canonical alternative; if Phase B implementation chooses it, fixture F4 expected-match must be updated to NO. **v3 selects the permissive alternation form as canonical**; F4 expects YES; Phase B unit tests run against the permissive form.

### §3.4-A.1 (v3-revised) Narrative — why this matters

[CONFIRMED.] v2's table-internal contradiction (fixture F4 said YES while the adjacent F4-nuance note explained why YES was actually NO under the simpler regex) would have caused Phase B implementation to choose one form, then fail the other interpretation's fixtures. v3 picks the canonical form explicitly so Phase B implementation has unambiguous source of truth.

---

## §3.4.1-A (v3-revised) Amendment — verify_gate_evidence Single Fail Mode + Anti-Fakery Online-Only + Broadened Reference Regex (HIGH-1 + HIGH-2 + MEDIUM-2)

This section consolidates v3 amendments to v2's §3.4.1-A. It is the **normatively canonical source** of `verify_gate_evidence` for v3; §6.0-A's helper body is updated to match (v3-C correction — earlier draft said "byte-canonical source" which was a synonym for the deprecated "byte-identical" framing; the SHA256 anchor in §3.4.1-A.6 is the actual drift-detection mechanism).

### §3.4.1-A.0 v2 defects (Cursor round-2 findings)

- **HIGH-1 (verify_gate_evidence behaves differently in v2 §3.4.1-A vs v2 §6.0-A):**
  - v2 §3.4.1-A `except Exception` ⇒ `return False` (fail closed).
  - v2 §6.0-A `except Exception` ⇒ `return text_presence_check(...)` (silent fallback).
  - Two normative behaviors for the same function. The §6.0-A fallback restores the gameable echo path that v2 was supposed to close.
- **HIGH-2 (anti-fakery narrative misaligned with offline behavior):** v2 §3.4.1-A.1 says "v2 closes this for Directus references — the row must actually exist when queried." With the §6.0-A fallback, an offline SAVE silently re-admits forged text. The narrative claim is the OPPOSITE of the documented offline path.
- **MEDIUM-2 (`DIRECTUS_REF_RE` brittle vs real handoff phrasing):** v2 regex anchors on `prod_<token>\s+(?:id=|row\s+)\d+`. Real-world handoff phrasing includes: `LD 578`, `LD-578`, `prod_locked_decisions/578`, `items/prod_locked_decisions/578`. These either (a) don't parse and silently drop to text-presence (per v2 §6.0-A fallback), or (b) require the v2 regex to be broadened. Either way, v2's narrative under-promises detection and over-promises hardening.

### §3.4.1-A.1 v3 resolution — single normative fail mode (HIGH-1)

**v3 chooses Cursor's recommended option:** offline / Directus probe failure ⇒ surface `UNVERIFIED_DIRECTUS_REF` checklist entry (visible degradation), **never** silent text-presence fallback for Directus-ish references. Reasoning:

- The whole point of v2's anti-fakery upgrade was to close the gameable echo path for Directus references.
- Silently re-admitting that path on offline failure makes the upgrade illusory — an attacker (or a model in autonomous mode) can simulate offline by failing the probe, then the gate accepts text-presence.
- Visible degradation (`UNVERIFIED_DIRECTUS_REF` in the surfaced checklist) preserves Kim's authority to decide whether to proceed despite the verification gap. Silent fallback removes that authority.

For **non-Directus evidence** (file paths, chat-quote keywords), the v1/v2 text-presence path remains as a best-effort check (no change in v3 — non-Directus refs were never claimed to be unfakeable).

### §3.4.1-A.2 v3 resolution — broadened reference detection (MEDIUM-2)

**v3 introduces a broad sentinel `BROAD_DIRECTUS_HINT_RE`** that fires on any phrasing that LOOKS like a Directus reference, then attempts full parse with the broadened `DIRECTUS_REF_RE`. If the broad sentinel matches but full parse fails ⇒ surface `UNVERIFIED_DIRECTUS_REF` (NOT silent text-presence fallback). This is the same fail-visibly contract as the offline path.

```python
# v3 broadened Directus-ish reference detection

import re

# Broad sentinel — fires on any phrasing that LOOKS like a Directus / LD reference.
# If this matches but the precise regex below does NOT fully parse,
# we surface UNVERIFIED_DIRECTUS_REF rather than silently falling through
# to text-presence. This is the v3-A MEDIUM-2 fail-visibly contract.
BROAD_DIRECTUS_HINT_RE = re.compile(
    r"(?i)\b(?:LD[\s\-]?\d+|prod_\w+|items/prod_\w+)",
)

# Precise regex — fully parses the reference into (collection, row_id).
# Covers (in alternation order):
#   1. LD shorthand:                LD 578     LD-578     LD578
#   2. Canonical with separators:   prod_locked_decisions id=578
#                                   prod_locked_decisions row 578
#                                   prod_locked_decisions/578
#   3. REST-path style:             items/prod_locked_decisions/578
DIRECTUS_REF_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"  LD[\s\-]?(?P<ld_id>\d+)"                                            # form 1: LD shorthand
    r"  |"
    r"  prod_(?P<coll1>\w+)\s*(?:id\s*=\s*|row\s+|/)(?P<row1>\d+)"           # form 2: canonical
    r"  |"
    r"  items/prod_(?P<coll2>\w+)/(?P<row2>\d+)"                              # form 3: REST-path
    r")",
)


def _resolve_collection_and_row(match: re.Match) -> tuple[str, int] | None:
    """Convert a successful DIRECTUS_REF_RE match to (collection, row_id).

    ASSUMPTION (v3-B explicit invariant — Cursor round-3 MEDIUM):
        LD ids cited in handoffs equal `prod_locked_decisions.id` primary key.
        i.e. the mapping `LD N -> ("locked_decisions", N)` then querying
        `prod_locked_decisions/N` is correct ONLY IF row.id == N.

        This invariant has held for the entire MindfulNest project history
        (LDs are minted as monotonically-increasing primary keys via
        lock_decision.py). If a future migration breaks this invariant
        (e.g., id renumbering, archival re-id, multi-tenant collection
        splitting), `_resolve_collection_and_row` MUST be updated to use
        a lookup field (e.g., `decision_key`) instead of the raw id.

        Tracked as risk row R-V3-LD-INVARIANT in v3 §7 (added v3-B).
        If the invariant breaks silently, evidence verification becomes
        WRONG (querying the wrong row), not merely UNVERIFIED — so the
        invariant is load-bearing for the anti-fakery guarantee.
    """
    if match.group("ld_id"):
        return ("locked_decisions", int(match.group("ld_id")))
    if match.group("coll1") and match.group("row1"):
        return (match.group("coll1"), int(match.group("row1")))
    if match.group("coll2") and match.group("row2"):
        return (match.group("coll2"), int(match.group("row2")))
    return None
```

### §3.4.1-A.3 v3 canonical `verify_gate_evidence` — normatively identical helper (HIGH-1 fix; pinned in BOTH §3.4.1-A AND §6.0-A; SHA256-anchored — see §3.4.1-A.6)

```python
def verify_gate_evidence(
    parsed_gate: dict,
    session_state,
    session_window_writes,
    client,
    surface_checklist: list,
) -> bool:
    """v3 anti-fakery cross-check — single normative fail mode.

    Behavior contract (v3-A HIGH-1 + HIGH-2 + MEDIUM-2; v3-D corrections):
      * If evidence_source contains a Directus-ish hint (BROAD_DIRECTUS_HINT_RE)
        AND DIRECTUS_REF_RE fully parses it (see "PRECISE REGEX MODE" below):
          - Query Directus. Apply 4-branch row classification (see
            "GET_ITEM ROW CLASSIFICATION" below):
              * Truthy non-empty row → True (evidence verified).
              * row is None → False (FAIL_EVIDENCE_MISSING).
              * row is empty dict {} → False (FAIL_EVIDENCE_MISSING).
              * row is empty list [] → False (FAIL_EVIDENCE_MISSING).
          - If get_item raises (offline / network failure / auth failure):
              append UNVERIFIED_DIRECTUS_REF entry to surface_checklist
              return False  (visible degradation; NEVER silent fallback)
      * If broad sentinel matches BUT precise regex fails to fully parse:
          append UNVERIFIED_DIRECTUS_REF entry to surface_checklist
          return False  (visible degradation; NEVER silent fallback)
      * If broad sentinel does NOT match (non-Directus evidence —
        file paths, chat-quote keywords):
          fall back to v1 text-presence + activity-log + halt-row checks.

    Anti-fakery guarantee: ONLINE-ONLY for Directus-ish references.
    When offline OR the Directus probe fails OR the precise regex cannot parse,
    the gate fails visibly via UNVERIFIED_DIRECTUS_REF rather than silently
    accepting text-presence echo.

    PRECISE REGEX MODE (v3-E HIGH-2 fix — ".search vs .fullmatch" pinned; v3-F prose alignment):
        The phrase "fully parse" in this contract means: the regex finds
        a COMPLETE, WELL-FORMED reference token, NOT a partial sub-fragment
        of a malformed compound string. Earlier v3 drafts used .search()
        unconditionally, which would have accepted partial substring matches
        anywhere in the input (e.g., "LD-578xyz" would have parsed as
        "LD-578" via search and queried row 578 against malformed evidence).
        v3-E pins the following two-mode policy (v3-F aligns all prose and
        canonical code fences to this policy — no v3-D single-line MODE-2 branch):

          * MODE 1 (single-line and multi-line): .fullmatch() on the **stripped**
            evidence string. A pure citation must match the WHOLE token after
            stripping leading/trailing whitespace (e.g., "LD-578",
            "prod_locked_decisions/578", "items/prod_locked_decisions/578").

          * MODE 2 (multi-line **only**): .search() on the **original**
            (unstripped) evidence string runs **only when** `'\n' in evidence_source`.
            This is the sole path for embedded references that share a line with
            surrounding prose **and** continue in a multi-line context (see T20 /
            F-FRAG-2). **Single-line evidence never enters MODE 2** — if MODE 1
            `fullmatch` fails on a single-line string, precise parsing fails →
            UNVERIFIED_DIRECTUS_REF (`reason=broad_hint_matched_but_precise_regex_did_not_parse`).

        The implementation tries MODE 1 first; if MODE 1 returns None and the
        evidence is multi-line, it applies MODE 2 `.search()`; if MODE 1 returns
        None and the evidence is single-line, precise_match stays None.

        Phase B implementation MUST use this two-mode contract verbatim.
        Fixtures (see §3.4.1-A.4):
          * F-FRAG-1: input "LD-578xyz" (single-line) → MODE 1 fails; MODE 2 **not**
            attempted → UNVERIFIED_DIRECTUS_REF.
          * F-FRAG-2: input `Per LD-578: see decision\nNext line of context`
            (multi-line, embedded ref) → MODE 1 fails; MODE 2 `.search()` resolves
            `LD-578` → PASS when row exists (T20).

    GET_ITEM ROW CLASSIFICATION (v3-D HIGH-1 fix; supersedes the buggy
    `return row is not None` from v3-A through v3-C):
        Different Directus client libraries handle row-not-found differently
        (some return None for HTTP 404; some return empty dict {}; some
        return empty list [] for list endpoints; some raise an exception).
        v3-D enforces 4 explicit branches in code (was 1 buggy expression):

            +-------------------------------------------+--------------------------------+
            | get_item(collection, id) returns ...      | classification                 |
            +-------------------------------------------+--------------------------------+
            | truthy non-empty row dict (no "data" key) | True (evidence verified)       |
            | wrapper {"data": <truthy non-empty>}      | True (evidence verified)       |
            | None                                      | False (FAIL_EVIDENCE_MISSING)  |
            | empty dict {} (non-None, len==0)          | False (FAIL_EVIDENCE_MISSING)  |
            | empty list [] (non-None, len==0)          | False (FAIL_EVIDENCE_MISSING)  |
            | wrapper {"data": null}  (v3-E MEDIUM-1)   | False (FAIL_EVIDENCE_MISSING)  |
            | wrapper {"data": []}    (v3-E MEDIUM-1)   | False (FAIL_EVIDENCE_MISSING)  |
            | wrapper {"data": {}}    (v3-E MEDIUM-1)   | False (FAIL_EVIDENCE_MISSING)  |
            | HTTP 404 (mapped to None by wrapper)      | False (FAIL_EVIDENCE_MISSING)  |
            | raises any Exception subclass             | PROBE_FAILED -> UNVERIFIED     |
            +-------------------------------------------+--------------------------------+

        Earlier `return row is not None` (v3-A through v3-C) was a contract
        bug — empty dict {} and empty list [] are NOT None, so they would
        have falsely classified as VERIFIED. v3-D adds explicit isinstance
        + len() checks for {} and [] before the truthy-non-empty fallthrough.

        v3-E MEDIUM-1 extension — wrapper-shape envelope responses: some
        Directus client libraries return responses wrapped in a {"data": ...}
        envelope. A wrapper with empty inner payload (e.g., {"data": null} or
        {"data": []}) has len() > 0 at the outer level (because "data" is a
        key) but represents the same "no row data" outcome. v3-E adds an
        explicit branch that inspects the inner payload of {"data": ...}
        wrappers and applies the same None / empty-collection contract before
        falling through to truthy. New fixtures F-WRAP-1, F-WRAP-2, F-WRAP-3
        in §3.4.1-A.4 pin the contract.

        Rationale: 404 means "the row truly does not exist" (anti-fakery
        gold-standard outcome — user cited a non-existent row). Empty dict,
        empty list, and empty-payload wrappers all mean "the API responded
        but with no row data" (same outcome — no row data == no evidence).
        Network / auth / timeout / 5xx errors mean "we could not verify
        either way" (anti-fakery offline outcome — surface visibly, do not
        silently pass or silently fail-with-wrong-reason).

        If the underlying Directus SDK does NOT distinguish 404 from
        connection error (e.g., raises the same exception class for both),
        the wrapper MUST inspect the exception (e.g., status_code == 404)
        and translate to None for 404 / re-raise for everything else.

    Args:
        parsed_gate: dict with 'evidence_source' and 'gate_index' keys.
        session_state: session metadata (assistant turns).
        session_window_writes: prod_activity_log + HALT-row writes this session.
        client: Directus client supporting client.get_item(collection, id)
                with the normalized 404-vs-exception contract above.
        surface_checklist: list[str] — appended to when degradation occurs.

    Returns:
        True iff evidence is verified per the contract above.
    """
    evidence_source = parsed_gate.get("evidence_source", "")
    gate_index = parsed_gate.get("gate_index", "?")

    if not BROAD_DIRECTUS_HINT_RE.search(evidence_source):
        # Non-Directus evidence (file paths, chat quote keywords, free-form):
        # text-presence + activity-log + halt-row best-effort fallback (same as v1).
        return (
            text_presence_check(evidence_source, session_state.assistant_turns)
            or activity_log_cites_gate(parsed_gate, session_window_writes)
            or halt_row_cites_gate(parsed_gate, session_window_writes)
        )

    # Directus-ish reference. Try to fully parse.
    # v3-E HIGH-1 fix (MODE 2 gated to multi-line only — F-FRAG-1 vs F-FRAG-2 / T20):
    # MODE 1 .fullmatch() on stripped evidence. MODE 2 .search() on the original
    # string ONLY when '\n' in evidence_source. Single-line: fullmatch failure →
    # precise_match None (no substring .search on one line).
    stripped = evidence_source.strip()
    precise_match = DIRECTUS_REF_RE.fullmatch(stripped)
    if precise_match is None:
        if "\n" not in evidence_source:
            precise_match = None
        else:
            precise_match = DIRECTUS_REF_RE.search(evidence_source)
    resolved = _resolve_collection_and_row(precise_match) if precise_match else None
    if resolved is None:
        # Broad sentinel matched but precise regex did NOT fully parse
        # (neither fullmatch on the stripped evidence nor search across the
        # multi-line context found a complete, well-formed reference token).
        # Visible degradation — DO NOT fall back to text-presence.
        surface_checklist.append(
            f"UNVERIFIED_DIRECTUS_REF gate={gate_index} "
            f"evidence_source={evidence_source!r} "
            f"reason=broad_hint_matched_but_precise_regex_did_not_parse"
        )
        return False

    collection, row_id = resolved
    try:
        row = client.get_item(f"prod_{collection}", row_id)
    except Exception as exc:
        # Offline / network failure / auth failure / row-fetch error.
        # Visible degradation — DO NOT fall back to text-presence.
        surface_checklist.append(
            f"UNVERIFIED_DIRECTUS_REF gate={gate_index} "
            f"evidence_source={evidence_source!r} "
            f"reason=directus_probe_failed exc={type(exc).__name__}"
        )
        return False

    # v3-D HIGH-1 fix: enforce the §3.4.1-A.3 HTTP/API outcome mapping table
    # explicitly. None / empty dict / empty list ALL map to FAIL_EVIDENCE_MISSING.
    # Earlier `return row is not None` was buggy: empty dict {} and empty list []
    # are NOT None, so a malformed Directus response (404 mapped to {} by some
    # client wrappers, or a list endpoint returning []) would have falsely
    # classified as VERIFIED EVIDENCE. The 4-branch contract below is normative.
    if row is None:
        return False
    if isinstance(row, dict) and len(row) == 0:
        return False
    if isinstance(row, list) and len(row) == 0:
        return False
    # v3-E MEDIUM-1 fix: handle wrapper-shaped responses (e.g., {"data": null}
    # or {"data": []}) that some Directus client libraries return. Without this
    # branch, a wrapper envelope with empty inner payload would have falsely
    # classified as VERIFIED (because the outer dict has len() > 0 due to the
    # "data" key being present). Match the inner payload against the same
    # None / empty-collection contract before falling through to truthy.
    if isinstance(row, dict) and "data" in row:
        inner = row["data"]
        if inner is None:
            return False
        if isinstance(inner, (dict, list)) and len(inner) == 0:
            return False
    # Truthy non-empty row (or non-wrapper dict with payload) → evidence verified.
    return True
```

This block is the **normatively canonical** source for v3. §6.0-A below contains a normatively identical copy (HIGH-1 fix: pin in BOTH sections). v3-B note: "normatively identical" replaces the earlier "byte-identical" claim per Cursor round-3 LOW — minor drift in surrounding context (comments, shebangs, import order) does not constitute spec drift, only changes to the function body / signature / docstring contract do. The audit anchor is the SHA256 of the canonical snippet documented in §3.4.1-A.6.

### §3.4.1-A.4 v3 fixture rows F11-F14 — broadened reference detection

| # | Input (`evidence_source` substring) | Broad sentinel matches? | Precise regex parses? | Verify path | Validates |
|---|---|---|---|---|---|
| F11 | `LD 578` | YES | YES (`(locked_decisions, 578)`) | Directus get_item; row 578 exists ⇒ True | v3-A MEDIUM-2 (LD shorthand without hyphen) |
| F12 | `LD-578` | YES | YES (`(locked_decisions, 578)`) | Directus get_item; row 578 exists ⇒ True | v3-A MEDIUM-2 (LD shorthand with hyphen) |
| F13 | `prod_locked_decisions/578` | YES | YES (`(locked_decisions, 578)`) | Directus get_item; row 578 exists ⇒ True | v3-A MEDIUM-2 (slash separator) |
| F14 | `items/prod_locked_decisions/578` | YES | YES (`(locked_decisions, 578)`) | Directus get_item; row 578 exists ⇒ True | v3-A MEDIUM-2 (REST-path style) |
| F15 | `prod_locked_decisions rows 578 and 614` | YES | NO (`rows` plural not in canonical separators) | UNVERIFIED_DIRECTUS_REF | v3-A MEDIUM-2 (broad-matched-precise-failed surfaces visibly) |
| F16 | `see Directus dashboard for the row` (no number) | NO (`Directus dashboard` is prose, no `prod_*` / `LD\d` / `items/prod_*` token) | n/a | text-presence fallback (non-Directus path) | v3-A MEDIUM-2 negative case (no broad-sentinel match) |
| **F-FRAG-1** (v3-D origin; v3-E + v3-F canonical) | `LD-578xyz` (single-line compound malformed string) | YES (`LD\s\-?\d+` matches `LD-578` substring) | MODE 1 fullmatch: NO. MODE 2 **not** run (no `\n` in evidence) → **UNVERIFIED**. | UNVERIFIED_DIRECTUS_REF | v3-E HIGH-1 (single-line bound to MODE 1; no `.search` on one line) |
| **F-FRAG-2** (v3-E + v3-F; aligns T20) | `Per LD-578: see decision\nNext line of context` (multi-line embedded ref) | YES | MODE 1 fullmatch: NO. MODE 2 `.search()` (multi-line gate satisfied) → **accept**. Resolves to `(locked_decisions, 578)`. | Directus get_item; row 578 exists ⇒ True | T20 / v3-E embedded ref in multi-line context |
| **F-WRAP-1** (NEW v3-E) | `LD-578` (single-line citation) — Directus client returns `{"data": null}` (wrapper-shape envelope with null inner) | YES | YES (resolves to `(locked_decisions, 578)`) | Directus get_item returns `{"data": null}` — outer dict is non-empty (has "data" key) but inner payload is None → FAIL_EVIDENCE_MISSING | UNVERIFIED-class FAIL_EVIDENCE_MISSING (returns False) | v3-E MEDIUM-1 (wrapper-shape envelope with null inner) |
| **F-WRAP-2** (NEW v3-E) | `LD-578` (single-line citation) — Directus client returns `{"data": []}` (wrapper-shape envelope with empty list inner) | YES | YES (resolves to `(locked_decisions, 578)`) | Directus get_item returns `{"data": []}` — outer dict non-empty, inner payload empty list → FAIL_EVIDENCE_MISSING | UNVERIFIED-class FAIL_EVIDENCE_MISSING (returns False) | v3-E MEDIUM-1 (wrapper-shape envelope with empty list inner) |
| **F-WRAP-3** (NEW v3-E) | `LD-578` (single-line citation) — Directus client returns `{"data": {"id": 578}}` (wrapper-shape envelope with truthy non-empty inner) | YES | YES (resolves to `(locked_decisions, 578)`) | Directus get_item returns `{"data": {"id": 578}}` — wrapper, inner payload is non-empty dict → True | True (evidence verified) | v3-E MEDIUM-1 (wrapper-shape envelope with truthy inner — positive case) |

**Note on F16:** v3's broad sentinel intentionally requires at least one of `LD\d+`, `prod_\w+`, or `items/prod_\w+` to fire. Pure prose like "see Directus dashboard" is treated as non-Directus evidence and routed to text-presence fallback. This is by design — the broad sentinel is meant to catch "this LOOKS like a Directus reference", not "this MENTIONS the word Directus."

**Note on F-FRAG-1 vs F-FRAG-2 (v3-E HIGH-1; v3-F table + note reconciliation):** FAIL vs PASS hinges on MODE 1 `fullmatch` on stripped evidence, then — **only if** `'\n' in evidence_source` — MODE 2 `.search()` on the original string. **Single-line** compound malformed evidence (`LD-578xyz`): MODE 1 fails; MODE 2 is **not** attempted → UNVERIFIED (F-FRAG-1). **Multi-line** embedded prose (F-FRAG-2 / T20): MODE 1 fails; MODE 2 may resolve the token → PASS when the row exists.

The fixture pair pins the contract: whole-string pure citations via MODE 1 `fullmatch`; embedded refs in **multi-line** evidence via MODE 2 `.search()`; single-line junk never partially resolves via substring search. Phase B MUST match §3.4.1-A.3 and §6.0-A.

### §3.4.1-A.5 v3 narrative — anti-fakery is online-only (HIGH-2 fix; replaces v2 §3.4.1-A.1 narrative)

**v3 narrative (replaces v2 line 158 verbatim; refined v3-B per Cursor round-3):**

> v3 closes the **silent text-presence fallback path** for Directus references **WHEN ONLINE** — the row must actually exist when queried. **WHEN OFFLINE or when the Directus probe fails** (network failure, auth failure, broad sentinel matched but precise regex did not parse — note: 404 / row-not-found is mapped to FAIL_EVIDENCE_MISSING, NOT to UNVERIFIED, per the §3.4.1-A.3 HTTP/API mapping table), the gate surfaces `UNVERIFIED_DIRECTUS_REF` in the visible checklist and fails the evidence cross-check, **rather than silently falling back to text-presence echo**. This makes anti-fakery **online-only and intentionally fails-visibly when offline** — Kim retains authority to decide whether to proceed despite the verification gap. v3 does NOT claim unfakeability — it claims **visibility of verification gaps** (see Benefit clause below for residual-risk enumeration).

**Trade-off documented explicitly:**

- **Cost of the v3 contract:** offline SAVE / Directus outage produces a checklist entry that Kim must consciously dismiss before proceeding. Operationally noisier than v2 (which silently accepted text-presence on offline).
- **Benefit (v3-B-tightened, Cursor round-3 MEDIUM):** the **silent text-presence fallback path** is closed for Directus-ish references — verification gaps surface **visibly** via `UNVERIFIED_DIRECTUS_REF` in the surfaced checklist rather than silently passing the gate. **Residual risks NOT eliminated, only made visible:** (a) client/hook bugs (e.g., the Directus client wrapper itself failing to honor the 404-vs-exception contract pinned in §3.4.1-A.3 docstring); (b) misclassification at the broad-vs-precise regex boundary (a handoff phrasing that the broad sentinel misses entirely will route to text-presence — see F16 negative case; a phrasing that broad-matches but the precise regex parses incorrectly into the wrong (collection, row_id) would query a real row and pass against false evidence — relies on the LD-shorthand invariant in §3.4.1-A.2); (c) spoofed checklist plumbing (a model that controls the `surface_checklist` list reference could in principle suppress the appended entry — Phase B implementation MUST treat the checklist as authoritative and surface it via Kim's dashboard, not via session output the model could overwrite). Earlier framing ("a model cannot simulate offline failure to bypass") was an overclaim — the model literally does not control network state, but it can influence other surfaces; what v3 provides is **visibility of verification gaps**, not unfakeability.

**Residual risk acknowledged (carries forward to v3 §7 risk row R-V3-H2):** non-Directus evidence (file paths, chat-quote keywords) still uses text-presence fallback and remains gameable in the same residual surface as v2's R-V2-D2.

### §3.4.1-A.6 v3 alignment with v3 §6.0-A — canonical-snippet SHA256 anchor (v3-B)

The `verify_gate_evidence` body in §3.4.1-A.3 above is **normatively identical** to the body in v3 §6.0-A below. This is the HIGH-1 fix: a single normative source of truth for the function, with no divergence between sections.

**v3-B Cursor round-3 LOW resolution — SHA256 audit anchor:**

The "byte-identical" claim from earlier v3 drafts was overstated — minor cosmetic drift (comments around the function, surrounding imports, blank lines, copy-paste artifacts) would break literal byte equality without breaking the normative contract. v3-B replaces "byte-identical" with "normatively identical" and provides a SHA256 anchor for audit drift checks.

**Canonical snippet definition (v3-F current; supersedes v3-D line-count / SHA256 for this function):**
- **Source-of-truth section:** §3.4.1-A.3 (this section's parent ancestor)
- **Snippet boundaries:** from `def verify_gate_evidence(` through the function's last `return True` (the function-body end inside the §3.4.1-A.3 fenced code block, NOT including the closing triple-backtick fence)
- **Line / byte count (post v3-F):** 206 lines, 11827 bytes UTF-8 (LF line endings, includes one trailing newline at end of snippet)
- **SHA256 (canonical snippet @ v3-F authoring):** `43555c85f4216c47c348c513218014e6ad7432275388e31953512f47bc53b49c`
- **SHA256 (canonical snippet @ v3-D authoring; SUPERSEDED by v3-F prose+code alignment):** `424300ba22a1440256e9ab4104566edd9de738bd85584773bd48e7264c3c895b` — preserved for audit lineage; v3-F amended the PRECISE REGEX MODE docstring and MODE-2 implementation lines so the fence matches v3-E Phase-B semantics (MODE 2 only when `'\n' in evidence_source`).
- **SHA256 (canonical snippet @ v3-B authoring; SUPERSEDED):** `ce8c4819dde66d82de024d7dfedee4f915249490100589760eeb6b596ec74cf1` — preserved for audit lineage.

**Audit procedure:**

1. Extract lines from `def verify_gate_evidence(` through (and including) the final `return True` of the function body in §3.4.1-A.3 (i.e., everything inside the fenced code block from the def line up to the line before the closing triple-backtick fence).
2. Compute SHA256 of the extracted bytes (UTF-8, LF line endings, snippet text terminated with one trailing newline; no other trailing whitespace changes vs spec).
3. Compare to the v3-F recorded anchor `43555c85...b49c`. If they match, the canonical snippet has not drifted since v3-F. If they do not match, EITHER the canonical snippet was intentionally amended (in which case a new spec version / sub-pass should be cut and the anchor updated in a new changelog row) OR the spec has drifted accidentally (in which case the drift must be reverted).

The §6.0-A copy of `verify_gate_evidence` may have docstring abbreviations (referring back to §3.4.1-A.3 for the full HTTP/API mapping table) and surrounding context (preceding comment header, position inside the algorithm sketch). The contract (signature, behavior, return values, surface_checklist appends) is preserved — that is what "normatively identical" means.

If a future spec version (v4) needs to amend the function, it MUST: (a) cut a new version, (b) update the SHA256 anchor in the new version's §3.4.1-A.6 (or successor), (c) add a changelog row.

---

## §6.0-A v3 Amendment — Updated §6 Detection Algorithm (consolidating v3 amendments; verify_gate_evidence body normatively identical to §3.4.1-A.3 — see SHA256 anchor in §3.4.1-A.6)

The v2 §6.0-A Python sketch is updated. Diff against v2:

```python
# mn-context SKILL.md Step 2.5c — DS-26 Mechanical Gate (v3)
# Runs after Step 2.5b. Inputs: assistant output turns, session metadata.

import re

# v2-A HIGH-1 (preserved): canonical tool-name set + helper
SUBAGENT_SPAWN_TOOL_NAMES = {"Agent", "Task", "subagent"}

def is_subagent_spawn_call(tool_call: dict) -> bool:
    return tool_call.get("name") in SUBAGENT_SPAWN_TOOL_NAMES

# v3-A MEDIUM-1 (canonical regex now the permissive alternation form)
DECLARATION_RE = re.compile(
    r"(?i)HALT\s+gate\s+scan\s*:\s*(\d+)\s+gate(?:s|\(s\))?\s+detected",
)

# v2-A MEDIUM-1 (preserved): tightened legacy fallback regex
LEGACY_HALT_RE = re.compile(
    r"(?im)^\|\s*\d+\s*\|.*?(HALT|do\s+NOT\s+proceed|surface\s+to\s+Kim|halt\s+and)",
)

# v3-A MEDIUM-2: broad sentinel for Directus-ish references
BROAD_DIRECTUS_HINT_RE = re.compile(
    r"(?i)\b(?:LD[\s\-]?\d+|prod_\w+|items/prod_\w+)",
)

# v3-A MEDIUM-2: precise regex covering 3 reference forms
DIRECTUS_REF_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"  LD[\s\-]?(?P<ld_id>\d+)"
    r"  |"
    r"  prod_(?P<coll1>\w+)\s*(?:id\s*=\s*|row\s+|/)(?P<row1>\d+)"
    r"  |"
    r"  items/prod_(?P<coll2>\w+)/(?P<row2>\d+)"
    r")",
)


def _resolve_collection_and_row(match):
    if match.group("ld_id"):
        return ("locked_decisions", int(match.group("ld_id")))
    if match.group("coll1") and match.group("row1"):
        return (match.group("coll1"), int(match.group("row1")))
    if match.group("coll2") and match.group("row2"):
        return (match.group("coll2"), int(match.group("row2")))
    return None


# v3-A HIGH-1 + v3-B: NORMATIVELY IDENTICAL TO §3.4.1-A.3 — single normative fail mode.
# DO NOT fall back to text-presence for Directus-ish refs on probe failure
# or precise-regex-parse failure. Surface UNVERIFIED_DIRECTUS_REF instead.
# Function body + signature + docstring contract MUST match §3.4.1-A.3.
# SHA256 anchor for canonical snippet is documented in §3.4.1-A.6.
def verify_gate_evidence(
    parsed_gate: dict,
    session_state,
    session_window_writes,
    client,
    surface_checklist: list,
) -> bool:
    """v3 anti-fakery cross-check — single normative fail mode.

    Behavior contract (v3-A HIGH-1 + HIGH-2 + MEDIUM-2; v3-D corrections).
    See §3.4.1-A.3 docstring for the full multi-mode contract; this
    docstring abbreviates by reference. Summary:
      * Non-Directus evidence (broad sentinel does NOT match) → v1
        text-presence / activity-log / halt-row best-effort fallback.
      * Directus-ish evidence (broad sentinel matches):
          - PRECISE REGEX (v3-E HIGH-2; v3-F prose alignment): MODE 1 .fullmatch()
            on stripped evidence; on failure, MODE 2 .search() **only when**
            `'\n' in evidence_source` (see §3.4.1-A.3 docstring).
          - GET_ITEM ROW CLASSIFICATION (v3-D HIGH-1): explicit 4-branch
            check — None / empty {} / empty [] all map to
            FAIL_EVIDENCE_MISSING; truthy non-empty row → True.
          - Probe exception → UNVERIFIED_DIRECTUS_REF.
          - Broad sentinel matched but precise regex (both modes) failed
            → UNVERIFIED_DIRECTUS_REF.

    Anti-fakery guarantee: ONLINE-ONLY for Directus-ish references.
    Phase B implementation MUST use a client wrapper that normalizes
    404 -> None and re-raises only network/auth/5xx exceptions.
    Function body + signature + behavior contract MUST match §3.4.1-A.3.
    """
    evidence_source = parsed_gate.get("evidence_source", "")
    gate_index = parsed_gate.get("gate_index", "?")

    if not BROAD_DIRECTUS_HINT_RE.search(evidence_source):
        return (
            text_presence_check(evidence_source, session_state.assistant_turns)
            or activity_log_cites_gate(parsed_gate, session_window_writes)
            or halt_row_cites_gate(parsed_gate, session_window_writes)
        )

    # v3-E HIGH-1 fix — MODE 2 .search only when multi-line (same as §3.4.1-A.3)
    stripped = evidence_source.strip()
    precise_match = DIRECTUS_REF_RE.fullmatch(stripped)
    if precise_match is None:
        if "\n" not in evidence_source:
            precise_match = None
        else:
            precise_match = DIRECTUS_REF_RE.search(evidence_source)
    resolved = _resolve_collection_and_row(precise_match) if precise_match else None
    if resolved is None:
        surface_checklist.append(
            f"UNVERIFIED_DIRECTUS_REF gate={gate_index} "
            f"evidence_source={evidence_source!r} "
            f"reason=broad_hint_matched_but_precise_regex_did_not_parse"
        )
        return False

    collection, row_id = resolved
    try:
        row = client.get_item(f"prod_{collection}", row_id)
    except Exception as exc:
        surface_checklist.append(
            f"UNVERIFIED_DIRECTUS_REF gate={gate_index} "
            f"evidence_source={evidence_source!r} "
            f"reason=directus_probe_failed exc={type(exc).__name__}"
        )
        return False

    # v3-D HIGH-1 fix: explicit 4-branch row classification (was buggy
    # `return row is not None`). Empty {} and [] are NOT None and would
    # have falsely classified as VERIFIED.
    if row is None:
        return False
    if isinstance(row, dict) and len(row) == 0:
        return False
    if isinstance(row, list) and len(row) == 0:
        return False
    # v3-E MEDIUM-1 fix: wrapper-shaped responses (e.g., {"data": null} or
    # {"data": []}) — match the inner payload against the same contract.
    if isinstance(row, dict) and "data" in row:
        inner = row["data"]
        if inner is None:
            return False
        if isinstance(inner, (dict, list)) and len(inner) == 0:
            return False
    return True


def step_2_5c_ds26_gate(session_state, session_window_writes, client):
    surface_checklist = []  # v3-A HIGH-1: feed this through to verify_gate_evidence

    # §3.7 false-positive guard — v2-A HIGH-1: use is_subagent_spawn_call
    candidate_handoffs = collect_candidate_handoffs(session_state)
    agent_calls = [c for c in session_state.tool_calls if is_subagent_spawn_call(c)]
    complete_writes = session_window_writes.filter_status_complete()
    if not candidate_handoffs and not agent_calls and not complete_writes:
        log("Step 2.5c: no handoff context detected, skipping.")
        return PASS

    # ... §3.3 parsing unchanged ...
    # ... §3.4 declaration verification — uses DECLARATION_RE (v3-A MEDIUM-1 canonical permissive form) ...
    # ... §3.4.1 evidence cross-check — calls verify_gate_evidence(..., surface_checklist) ...
    # ... §3.5 MET vs NOT MET unchanged ...
    # ... §3.6 legacy fallback — uses LEGACY_HALT_RE (v2-A MEDIUM-1 preserved) ...

    # rest of v1 §6 algorithm preserved verbatim, with surface_checklist
    # surfaced to Kim alongside any FAIL verdict.
    ...
```

[CONFIRMED — `verify_gate_evidence` body in this §6.0-A is normatively identical to §3.4.1-A.3 above (function body + signature + behavior contract match; the §6.0-A docstring abbreviates the HTTP/API mapping table by reference to §3.4.1-A.3 to keep the algorithmic-overview readable, but the contract is identical). Single normative source of truth. SHA256 anchor for canonical snippet in §3.4.1-A.6.]

---

## §7 Risk Assessment (v3 — extended; v1 §11 + v2 §7 rows preserved)

v1 §11 contained 8 risk rows (preserved verbatim by reference). v2 §7 added 4 rows (R-V2-A1, R-V2-B2, R-V2-C1, R-V2-D2; preserved verbatim). v3 ADDS 5 rows total: 4 from v3-A (R-V3-H1, R-V3-H2, R-V3-M1, R-V3-M2 for the 4 Cursor round-2 findings) plus 1 from v3-B (R-V3-LD-INVARIANT for the LD-shorthand-to-row-id mapping invariant flagged in Cursor round-3):

| Row | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-V3-H1** | **`verify_gate_evidence` divergent fail modes (v2 §3.4.1-A vs §6.0-A)** — two normative behaviors for the same function; the §6.0-A silent text-presence fallback restores the gameable echo path that v2 was supposed to close | **Was 100% (v2 had this divergence)** | **High** (anti-fakery upgrade rendered illusory; offline SAVE silently re-admits forged text) | v3-A HIGH-1: single normative fail mode; offline / Directus probe failure ⇒ surface `UNVERIFIED_DIRECTUS_REF` (visible degradation), NEVER silent text-presence fallback for Directus-ish refs; `verify_gate_evidence` body **normatively identical** in §3.4.1-A.3 AND §6.0-A (v3-C correction; SHA256 anchor in §3.4.1-A.6 is the audit drift-detection mechanism); Phase G unit tests assert behavioral parity across both surfaces |
| **R-V3-H2** | **Anti-fakery narrative under-specifies online-only guarantee** — v2 narrative claims "row must actually exist" without qualifying offline behavior; gives false sense of unfakeability | **High** (any reader of v2 spec inherits the over-promised guarantee)  | **Medium** (operational misunderstanding; Kim or future implementer trusts the gate more than warranted) | v3-A HIGH-2: rewrite §3.4.1-A.5 narrative to explicitly state online-only guarantee + offline UNVERIFIED surfacing; document trade-off (offline noise) and benefit (closed echo path in all observable conditions) |
| **R-V3-M1** | **Fixture F4 vs canonical regex contradiction** — v2 §3.4-A.1 row F4 expects YES-match under canonical `gate(s)?` regex, but adjacent F4-nuance note correctly explains literal-parens cannot match; Phase B implementation choosing one form would fail the other interpretation's fixtures | **Was 100% (v2 had this contradiction)** | **Low-Medium** (Phase B test failures; spec re-author cycle; no production impact while still in GOVERNANCE-AUTHORING — see §0 status banner; production code installation is deferred to the future Terminal CLI implementation session) | v3-A MEDIUM-1: promote permissive alternation form `gate(?:s\|\(s\))?` to canonical; update F4 expected-match to YES; document simpler `gate(s)?` form as non-canonical alternative; Phase B unit tests align with permissive canonical form |
| **R-V3-M2** | **`DIRECTUS_REF_RE` brittle vs real handoff phrasing** — v2 regex misses `LD 578`, `LD-578`, `prod_*/N`, `items/prod_*/N`; missed references silently drop to weak text-presence fallback (per v2 §6.0-A `except`) without surfacing the gap | **High** (LD shorthand and REST-path forms are common in real handoffs) | **Medium** (silent loss of anti-fakery coverage on the most common reference forms; combined with R-V3-H1's silent fallback, compounds to "gate looks closed but isn't") | v3-A MEDIUM-2: broaden `DIRECTUS_REF_RE` to cover 3 forms (LD shorthand, canonical with `id=`/`row`/`/` separators, REST-path); add fixture rows F11-F16; introduce `BROAD_DIRECTUS_HINT_RE` sentinel — when broad matches but precise fails, surface `UNVERIFIED_DIRECTUS_REF` (no silent text-presence fallback); same fail-visibly contract as R-V3-H1 |
| **R-V3-LD-INVARIANT** (NEW v3-B) | **LD-shorthand-to-row-id mapping invariant** — `_resolve_collection_and_row` maps `LD N → ("locked_decisions", N)` then queries `prod_locked_decisions/N`. This is correct ONLY IF `prod_locked_decisions.id == N` for the LD numbered N. If a future migration breaks this invariant (id renumbering, archival re-id, multi-tenant collection split), evidence verification becomes WRONG (querying the wrong row), not merely UNVERIFIED — i.e., the gate would PASS against false evidence. | **Low** (invariant has held for the entire MindfulNest project history; LDs are minted as monotonically-increasing primary keys via lock_decision.py — no historical migration has broken this) | **High** (silent verification on the wrong row would defeat the anti-fakery upgrade entirely; the gate would say "verified" when it had not actually verified the cited LD) | v3-B Cursor round-3 MEDIUM closure: invariant explicitly documented in `_resolve_collection_and_row` docstring (§3.4.1-A.2) so future implementers cannot miss it. If the invariant is ever known to break (or migration is planned), `_resolve_collection_and_row` MUST be updated to use a lookup field (e.g., `decision_key`) instead of the raw id, and a new spec version (v4) cut to track the change |

**Cross-reference to v2 §7 rows + v1 §11 rows:** the v3 rows above are ADDITIVE — they don't supersede v2's 4 rows or v1's 8 rows. R-V3-H1 strengthens v1 §11 row "Faked declaration with faked evidence citations" + v2 R-V2-D2 by closing the offline gameable surface for Directus-ish references. R-V3-M2 strengthens v2 R-V2-D2 by widening the detected reference surface. **R-V3-LD-INVARIANT** (added v3-B) closes a load-bearing assumption made invisible in v2-v3-A — the `LD N → row.id = N` mapping was implicit and would have caused silent verification on the wrong row if ever broken.

---

## §11 Reference Index (v3 — extended; v1 §14 + v2 §11 entries preserved)

In addition to all v1 §14 + v2 §11 entries (preserved verbatim by reference), v3 adds:

- **v3-specific authority:**
  - LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V3_VERIFY_FAIL_MODE_RECONCILE_REF_REGEX_V1` — this v3's own LD; covers the four amendments (HIGH-1 + HIGH-2 + MEDIUM-1 + MEDIUM-2).
  - LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V2_TOOL_NAME_REGEX_FAKERY_FIX_V1` (id=614) — v2's LD; preserved by reference.
  - LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (id=578) — origin LD; preserved by reference.
  - `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md` — historical baseline.
  - `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v2.md` — sha256 `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (374 lines); supersedes v1 in 4 surfaces; preserved verbatim.
  - `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v3.md` — this document; supersedes v2 in 4 surfaces.
- **Cursor round-2 review:** the 4 findings (HIGH-1 verify_gate_evidence divergent fail modes; HIGH-2 anti-fakery narrative misalignment; MEDIUM-1 fixture F4 contradiction; MEDIUM-2 DIRECTUS_REF_RE brittleness) are addressed in v3 §3.4-A.1, §3.4.1-A, §6.0-A, §7. The 1 LOW finding (§7 vs v1 §11 numbering discrepancy) is **closed** via §0.3 Section ID Legend (added in v3-A authoring pass; consistency sweep across all sections completed in v3-B sub-pass).
- **Cursor round-3 review (v3-B):** 3 MEDIUMs + 2 LOWs all closed in v3-B sub-pass — see §0.1 v3-B changelog row for full enumeration. New §7 row R-V3-LD-INVARIANT added.
- **Cursor round-4 review (v3-D):** 2 REAL CORRECTNESS BUGS + 1 recurring MEDIUM all closed in v3-D sub-pass — see §0.1 v3-D changelog row for full enumeration. LD-641 `DS_26_MECHANICAL_GATE_TECH_SPEC_V3_D_ROUND_4_FIXES_V1` filed as v3-D's authority. Canonical snippet SHA256 anchor in §3.4.1-A.6 updated to `424300ba22a1440256e9ab4104566edd9de738bd85584773bd48e7264c3c895b`.
- **Self-reference:** v3 is a supersede-by-amendment document; it does NOT replace v1 or v2 in storage. v1, v2, and v3 are all preserved in `Production/docs/` for audit traceability.
- **Implementation reference:** Phase B of the future Terminal CLI implementation session MUST source the regex set + helper functions from v3 §3.4-A.1 (canonical declaration regex), v3 §3.4.1-A.2 (broadened reference regex), v3 §3.4.1-A.3 (verify_gate_evidence single fail mode), v3 §6.0-A (consolidated algorithm) — NOT v2's now-superseded equivalents.

---

## §12 Changelog (v3 entry appended; v2 + v1 entries preserved)

| Version | Date | Author | Change |
|---|---|---|---|
| **v3 (sub-pass v3-D)** | **2026-05-09** | **gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context)** | **Round-4 cleanup sub-pass — no version bump. Cursor round-4 surfaced 2 REAL CORRECTNESS BUGS in the anti-fakery code: HIGH-1 (`return row is not None` contradicted the docstring outcome-mapping table by passing empty `{}` / `[]` as VERIFIED) and HIGH-2 (`DIRECTUS_REF_RE.search()` contradicted the "fully parse" contract by accepting partial substring matches). v3-D rewrote both code paths in §3.4.1-A.3 + §6.0-A: explicit 4-branch row classification (None / empty dict / empty list / truthy non-empty) and two-mode regex policy (`.fullmatch()` first on stripped evidence, then `.search()` fallback for embedded refs). New fixtures F-FRAG-1 + F-FRAG-2 pin the regex contract. MEDIUM: §0 status banner reframed from "DESIGN ONLY" to "GOVERNANCE-AUTHORING" matching project-wide DS-29 / Rule 35 framing. Code-block audit verified §3.4.1-A.3 + §6.0-A bodies remain normatively identical post-fix. Canonical snippet SHA256 anchor recomputed: `424300ba22a1440256e9ab4104566edd9de738bd85584773bd48e7264c3c895b` (was `ce8c4819...74cf1` at v3-B authoring). v1 + v2 specs NOT modified.** |
| **v3 (sub-pass v3-C)** | **2026-05-09** | **gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context)** | **VERIFY-AND-REMEDIATE sub-pass — no version bump. Mandatory verification phase performed for each Cursor round-3 finding before any edit. Verdict (per disagreement protocol): all 5 substantive v3-B fixes ARE present in spec — Cursor's round-3 line citations reference a stale snapshot; v3-C did not redundantly re-apply landed fixes. v3-C DID find 4 stale "byte-identical" / "byte-canonical" references that v3-B's LOW-closure claim missed (§0.2 lines 37 + 49, §3.4.1-A intro line 123, §7 R-V3-H1 mitigation cell line 535) and replaced with "normatively identical" / "normatively canonical source" + §3.4.1-A.6 SHA256 anchor cross-reference. Brings the entire spec into terminological consistency with the v3-B normative-vs-byte-identical framing. v1 + v2 specs NOT modified.** |
| **v3 (sub-pass v3-B)** | **2026-05-09** | **gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context)** | **Comprehensive cleanup sub-pass — no version bump. Closes 5 follow-on items from Cursor round-3 review + internal consistency: (1) multi-section LOW-deferred narrative consistency sweep — every "1 LOW deferred" / "intentionally deferred" reference re-narrated as "1 LOW closed via §0.3 Section ID Legend"; (2) §0.3 §6 row repaired (replaced all-`n/a` row with meaningful v1/v2/v3 lineage cells); (3) §3.4.1-A.5 "cannot simulate offline" overclaim tightened to "silent text-presence fallback closed; verification gaps surface visibly via UNVERIFIED_DIRECTUS_REF — residual risks NOT eliminated, only made visible"; (4) §3.4.1-A.3 + §6.0-A `get_item` HTTP/API normative outcome mapping table added (404/None ⇒ FAIL_EVIDENCE_MISSING; raised exception ⇒ PROBE_FAILED → UNVERIFIED); (5) §3.4.1-A.2 LD-shorthand invariant assumption documented (`LD N → prod_locked_decisions.id = N`) + new §7 row R-V3-LD-INVARIANT. Two Cursor round-3 LOWs also closed: F4 prose pipe escaping standardized; "byte-identical" replaced with "normatively identical" + SHA256 anchor in §3.4.1-A.6 (`ce8c4819dde66d82de024d7dfedee4f915249490100589760eeb6b596ec74cf1`). v1 + v2 specs NOT modified.** |
| **v3 (sub-pass v3-A)** | **2026-05-09** | **gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context)** | **Four surgical amendments responding to Cursor round-2 review of v2: HIGH-1 (verify_gate_evidence single normative fail mode — eliminate v2 §3.4.1-A vs §6.0-A divergent except branches; pin normatively identical helper in both sections), HIGH-2 (anti-fakery narrative aligned with online-only qualifier — rewrite §3.4.1-A.1 narrative; document offline UNVERIFIED surfacing trade-off), MEDIUM-1 (fixture F4 reconciliation — promote permissive alternation regex `gate(?:s\|\(s\))?` to canonical), MEDIUM-2 (DIRECTUS_REF_RE broadened to cover LD shorthand, canonical with `id=`/`row`/`/` separators, REST-path style; new fixtures F11-F16; broad sentinel for fail-visibly contract on broad-match-precise-fail). 4 new §7 risk rows (R-V3-H1, R-V3-H2, R-V3-M1, R-V3-M2). 4 new test cases T15-T18. 1 LOW closed via §0.3 Section ID Legend (cross-section consistency sweep completed in v3-B sub-pass). v1 + v2 specs NOT modified. Implementation handoff NOT modified. Cursor v3 review handoff NOT modified.** |
| v2 | 2026-05-08 | gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context) | Four surgical amendments responding to Cursor v3 cross-review of v1: HIGH-1 (cross-tool name normalization), HIGH-2 (declaration regex escaping bug fix), MEDIUM-1 (legacy fallback noise reduction), MEDIUM-2 (anti-fakery hardening via Directus row verification). 4 new §7 risk rows (R-V2-A1, R-V2-B2, R-V2-C1, R-V2-D2). |
| v1 | 2026-05-08 | gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context) | Initial design via dual-Opus debate. §3 SAVE-time surface (Step 2.5c). §6 algorithm. §7 pre-execution variant deferred. §10 ten pre-implementation gates. §11 risk assessment (8 rows). §13 testing plan (T1-T10). |

---

## §13 Testing Plan (v3 — additive cases T15-T18; v1 T1-T10 + v2 T11-T14 preserved)

In addition to v1 §13 T1-T10 + v2 §13 T11-T14 (preserved verbatim by reference), v3 adds:

| Test # | Handoff content | Session state | Expected verdict | Validates |
|---|---|---|---|---|
| **T15** | v1-template, 1 gate, evidence_source = `prod_locked_decisions row 578` | Directus client raises `ConnectionError` on get_item | FAIL with `UNVERIFIED_DIRECTUS_REF gate=1 ... reason=directus_probe_failed exc=ConnectionError` appended to surface_checklist; NO silent text-presence fallback | v3-A HIGH-1 (single normative fail mode; offline degradation surfaces visibly, never falls back) |
| **T16** | v1-template, 1 gate, evidence_source = `prod_locked_decisions rows 578 and 614` (plural rows — broad-match-precise-fail) | Directus online | FAIL with `UNVERIFIED_DIRECTUS_REF gate=1 ... reason=broad_hint_matched_but_precise_regex_did_not_parse` appended to surface_checklist; NO silent text-presence fallback | v3-A MEDIUM-2 + HIGH-1 (broad sentinel matched, precise regex did not parse, fail-visibly contract holds) |
| **T17** | v1-template, 4 gates with evidence_source = `LD 578`, `LD-578`, `prod_locked_decisions/578`, `items/prod_locked_decisions/578` | Directus online; row 578 exists in `prod_locked_decisions` | All 4 gates PASS evidence cross-check (all 4 reference forms parse to `(locked_decisions, 578)`) | v3-A MEDIUM-2 (4 broadened reference forms all parse correctly) |
| **T18** | v1-template, 1 gate, evidence_source = `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md` (file path — non-Directus) | Session output echoes the path string | PASS via text-presence fallback (non-Directus path; broad sentinel does NOT match `prod_*` / `LD\d` / `items/prod_*`) | v3-A MEDIUM-2 negative case (non-Directus evidence routes to v1 text-presence path; broad sentinel correctly does not fire) |

Phase G of the implementation session runs T15-T18 in addition to v1 T1-T10 + v2 T11-T14 and confirms expected verdicts.

---

## §14 Authorship Trail (v3 entry appended)

- **2026-05-09 (v3-D sub-pass)** — v3-D round-4 cleanup sub-pass, gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context). No version bump. Cursor round-4 surfaced 2 REAL CORRECTNESS BUGS in the anti-fakery code (not wording): HIGH-1 row-classification (`return row is not None` would falsely VERIFY empty `{}` / `[]`) and HIGH-2 fully-parse vs `.search` substring (`DIRECTUS_REF_RE.search()` accepted partial substring matches contradicting the "fully parse" contract). Plus 1 recurring MEDIUM: DESIGN-ONLY vs in-session LD writes reframed to GOVERNANCE-AUTHORING. v3-D applied 3 fixes: (1) §3.4.1-A.3 + §6.0-A code blocks rewritten with explicit 4-branch row classification; (2) `.fullmatch()`-first / `.search()`-fallback two-mode regex policy + new fixtures F-FRAG-1 + F-FRAG-2; (3) §0 + §0 Operating Mode reframed GOVERNANCE-AUTHORING. Code-block audit verified §3.4.1-A.3 + §6.0-A bodies remain normatively identical post-fix. Canonical snippet SHA256 anchor recomputed: `424300ba22a1440256e9ab4104566edd9de738bd85584773bd48e7264c3c895b` (183 lines, 10252 bytes UTF-8); old anchor `ce8c4819dde66d82de024d7dfedee4f915249490100589760eeb6b596ec74cf1` preserved in §3.4.1-A.6 for audit lineage. v1 + v2 specs NOT modified at v3-D authoring time; v2 sha256 still `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (drift verified post-edit).
- **2026-05-09 (v3-C sub-pass)** — v3-C VERIFY-AND-REMEDIATE sub-pass, gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context). No version bump. Mandatory verification of v3-B claimed fixes performed FIRST: all 5 substantive fixes verified present in spec at v3-C author time (Cursor round-3 line citations are stale; fixes ARE landed). v3-C surgically closed 4 stale "byte-identical" / "byte-canonical" references that v3-B's LOW-closure claim missed (lines 37, 49, 123, 535) — replaced with "normatively identical" / "normatively canonical source" + §3.4.1-A.6 SHA256 anchor cross-reference. Net: 4 prose edits + 3 changelog entries (this §14 row + §0.1 v3-C row + §12 v3-C row). v1 + v2 specs NOT modified at v3-C authoring time; v2 sha256 still `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (drift verified post-edit). Canonical-snippet SHA256 anchor unchanged (§3.4.1-A.6: `ce8c4819dde66d82de024d7dfedee4f915249490100589760eeb6b596ec74cf1`).
- **2026-05-09 (v3-B sub-pass)** — v3-B comprehensive cleanup sub-pass, gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context). No version bump. 5 follow-on fixes (multi-section LOW-deferred consistency sweep + §0.3 §6 row repair + 3 substantive Cursor round-3 fixes: §3.4.1-A.5 overclaim tightening, §3.4.1-A.3/§6.0-A `get_item` HTTP/API normative mapping, §3.4.1-A.2 LD-shorthand invariant) + 2 Cursor round-3 LOW closures (F4 prose pipe escaping standardization, "byte-identical" → "normatively identical" + SHA256 anchor). v1 + v2 specs NOT modified at v3-B authoring time; v2 sha256 still `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (drift verified post-edit). Canonical-snippet SHA256 anchor recorded in §3.4.1-A.6: `ce8c4819dde66d82de024d7dfedee4f915249490100589760eeb6b596ec74cf1`.
- **2026-05-09 (v3-A authoring pass)** — v3 authored, gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context). Four surgical amendments responding to Cursor round-2 review of v2 (2 HIGH + 2 MEDIUM addressed; 1 LOW closed via §0.3 — see §0.1 v3-A row). Did NOT modify v1 spec, v2 spec, v1 implementation handoff, or Cursor v3 review handoff (per self-bound rule). v2 sha256 verified at author time: `8f1430bca0cfa89550591c453e07b5f8e543840067ea378862926f11a49418d0` (374 lines).
- v2 authorship preserved per v2 §14.
- v1 authorship preserved per v1 §15.

---

**End of v3 amendments. All other v2 sections (§0, §3.4-A through §3.4-A.2 except F4 fixture row + canonical-regex selection, §3.6-A, §3.7-A, §6.0-A baseline structure, v2 §7 8+4 risk rows, §11 reference index, §12 changelog, §13 T1-T14, §14 authorship) preserved verbatim by reference at `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v2.md`. All other v1 sections (§1, §2, §3.1-3.3, §3.5, §3.7-3.8, §4, §5, §6 baseline, §7 pre-execution variant, §8, §9, §10, §11 baseline 8 rows, §12 rollback, §13 baseline T1-T10, §14, §15) preserved verbatim by reference at `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md`.**
