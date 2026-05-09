# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v4

**Authored:** 2026-05-09
**Author:** Claude Opus 4.7 (1M context)
**Status:** GOVERNANCE-AUTHORING (Rule 35 / DS-29 — LD + activity_log are canonical spec-session deliverables; see §0). **Implementation** remains gated on Kim approval per §6 — no Phase B code/schema rollout from this document alone.
**Self-classification:** STANDARD (per zero-error-qa DS-26 / tech-spec skill v2 §0.1) — surgical amendment overlay on v3; closes 3 Cursor round-2 findings (1 HIGH + 2 MEDIUM); no new design decisions; no new gates; reference-implementation correctness + vocabulary normalization only.
**Scope:** Generic schema-aware payload validator covering ALL `prod_*` Directus collections (preserved from v3 verbatim by reference).
**Generalizes:** v6 narrow validator pattern (preserved from v3 verbatim by reference).
**Supersedes:** `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v3.md` (sha256 `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b`, 403 lines) — preserved as historical baseline. v3 supersedes v2 (sha256 `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b`); v2 supersedes v1 (sha256 `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`). v4 inherits all v3 inheritance chains unchanged.
**Motivation for v4:** Cursor cross-review of v3 returned 3 round-2 findings (1 HIGH + 2 MEDIUM). HIGH: v3's §9.2 reference implementation only catches `FileNotFoundError` from `lstat()`; other OS errors from `lstat()` / `exists()` / `is_symlink()` (e.g., permission denied at the directory level, transient I/O failure on the metadata call itself, ENOTDIR on a parent component, ELOOP on excessive symlink chain) are unspecified in the normative case table and can crash the validator or escape the 6-case enumeration entirely — breaking the "exactly one case per failure mode" guarantee that v2/v3 introduced. MEDIUM-1: v3's "defensive TOCTOU" branch (`if not path.exists(): return {}` after a successful `lstat`) is a silent path with no log line and no activity-log row, contradicting v3's claim that every failure mode produces a diagnostic; this branch sits OUTSIDE the 6-case table. MEDIUM-2: operator-facing reason vocabulary is inconsistent across the v3 spec — log-line documentation uses `json-parse-error-style` (hyphen-delimited) tokens while the reference implementation passes `json_parse_error` / `permission_denied` (underscore-delimited) string literals, and `OverrideFileMalformedError` constructors use a third style (`"layout_invalid"` instead of `"layout-error-description"`); operator-facing telemetry consumers cannot reliably grep across log files + activity-log rows + raised exception kinds with a single token vocabulary. v4 fixes ONLY: §0.1 (changelog row v4-A); §3 (canonical `OVERRIDE_FILE_REASON_VOCAB` set pinned); §9.2 (case table extended to **9 file-state labels** (A/A1/A2/A3/B/C/D/E/E2) — 7 diagnostic + 2 non-diagnostic; Case A2 NEW for TOCTOU vanish promoted to logged path, Case A3 NEW for OSError-other-than-FileNotFoundError on lstat/exists/is_symlink; reference implementation rewritten with explicit `OSError` (excluding `FileNotFoundError`) catch around `lstat()` + a try/except wrapper around the symlink/exists guard; reason vocabulary normalized uniformly across log-line format, activity-log details, and `OverrideFileMalformedError` constructor strings); §7 (NEW risk #13 — operator telemetry inconsistency caused by mixed reason-token vocabulary; LIKELIHOOD LOW with v4 canonical vocab; SEVERITY LOW); §11 (v3 historical baseline appended + v4 self-reference + v4 spec-LD); §12 (changelog row appended). All other v3 design (Decisions 1-8, Phases 0/1/2/3/4/5, Gates 1-11, Risks 1-12, §1/§2/§3-decisions/§4/§5/§6/§8/§9.1/§9.3/§9.4/§10/§13/§15/§16) is **preserved verbatim by reference** to v3; only sections that needed updating got rewritten. Three LOW round-2 findings CLOSED in v4-B (multi-section consistency repair — see §0.1 v4-B changelog row + §3.10 NEW canonical exception API contract + §11 LD-622 substitution + §5/§9.2/§15 8-fixture canonical reconciliation).

---

## §0.1 — Authoring changelog (v4-D row above v4-C row above v4-B row above v4-A row above v3-A row above v2-A row above v1 row)

| Version | Date | Change |
|---------|------|--------|
| **v4-D** | **2026-05-09** | **Cursor round-5 cleanup — verification-phase finding: 5 of 6 prompt-recommended fixes were ALREADY landed by v4-C (HIGH line-5 banner GOVERNANCE-AUTHORING / MEDIUM-1 §12 v4 row 9-case / MEDIUM-2 §3.10 grep-anchored line refs / MEDIUM-3 [CONFIRMED] footer DS-29 alignment / LOW-1 §11 repo-relative paths). Cursor round-5 prompt was authored against an older v4 spec snapshot (referenced sha256 `320ad2aa75b33a1ce758837c2274f4964246151af0353a5c08ca2ea952ba548a`); v4-D session start observed actual sha256 `bf899c880489de700f1ae4dce5118e4213cdd8e8eb5d9a9cd84a6f0ff8f736ef` — drift between prompt-author time and v4-D session time, with 5 fixes already applied at v4-C. v4-D applies ONLY the 1 finding that survived: **LOW-2 `truly_absent` vocab vs Case A no-log mismatch** — added explicit operator FAQ note immediately after the Normative vocabulary rule bullet list at §3.9 stating that `truly_absent` is the only vocab token never written to log/actrow/exception kind (Case A produces no diagnostic), exists in the vocab solely for telemetry-consumer disambiguation between "no event expected" (Case A steady state) and "event missing — investigate" (any other case), and operators grepping for `truly_absent` will always get zero matches by design. Per-finding pre-edit verification (`(my probe)` greps): F1 line 5 already says GOVERNANCE-AUTHORING aligned with §0 body — no edit; F2 §12 v4 row line 359 already says "9 file-state case labels (7 diagnostic + 2 non-diagnostic per v4-C)" — no edit; F3 §3.10 line 108 already says "grep the fenced block — line numbers drift when the spec is edited" — no edit; F3b §10 line 329 has no hardcoded line numbers — no edit; F4 [CONFIRMED] footer line 418 + DS-29 paragraph line 413 already align with `(my probe)` / `(handoff claim)` / `(handoff claim — not re-probed in v4 authoring)` taxonomy — no edit; F5 §11 entries lines 343-348 already use repo-relative `Production/docs/...` form — no edit. v4-C spec sha256 pre-edit `bf899c880489de700f1ae4dce5118e4213cdd8e8eb5d9a9cd84a6f0ff8f736ef`. v3 sha256 unchanged `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b` (confirmed via shasum at v4-D session start AND end). Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_D_ROUND_5_FIXES_V1` filed alongside, severity SOFT, task_category governance, enforcement awareness_only, scope_domain infra. **DISAGREEMENT NOTE on Cursor round-5 prompt's claims of recurring HIGH bug:** Cursor stated "the file header line 5 keeps surviving multi-section sweeps" — `(my probe)` of the actual current line 5 contradicts: line 5 already says "GOVERNANCE-AUTHORING (Rule 35 / DS-29 — LD + activity_log are canonical spec-session deliverables; see §0). **Implementation** remains gated on Kim approval per §6 — no Phase B code/schema rollout from this document alone." which is functionally equivalent to the prompt's recommended replacement text. v4-D respectfully diverges from the prompt's "MUST update line 5 explicitly" mandate — the line is already correct; applying the prompt's literal text would introduce a near-duplicate without improving correctness. NO functional spec changes — pure 1-bullet operator FAQ addition to §3.9. Self-classification: STANDARD (consistency cleanup overlay; no new design decisions; no new gates; no functional changes).** |
| **v4-C** | **2026-05-09** | **Cursor round-3 cleanup — closes 4 findings (1 HIGH + 2 MEDIUM + 1 LOW) that v4-B partially landed or missed entirely. **VERIFICATION-PHASE FINDINGS** (v4-B claimed vs spec actual, line-by-line): (1) HIGH `operating-mode-vs-LD-actions` — v4-B claimed at §0.1 v4-B row "substituting `LD-NEW (this v4 session)` with `LD-622` in §11"; spec at line 338 confirms `LD-622` substitution landed for v4-A self-reference, BUT line 339 still showed `LD-NEW-v4-B` placeholder for v4-B's own LD (v4-B did not substitute its own placeholder at the time of authoring), AND §0 line 28 still said "DESIGN ONLY ... no LDs except the v4 spec-LD itself are filed during the authoring of this spec" — directly contradicting v4-A filing LD-622 + v4-B filing LD-628 + v4-C filing a new LD; v4-C fixes via §0 governance-authoring framing rewrite (replaces "DESIGN ONLY ... no LDs except" with explicit governance-authoring carve-out enumerating LD-622 + LD-628 + LD-636) AND substitutes LD-NEW-v4-B placeholder at §11 with `LD-628` per `(handoff claim)` (v4-B's filed LD id provided in v4-C session prompt) AND resolves §0 + §11 v4-C self-references to `LD-636` (v4-C session's filed LD). (2) MEDIUM-1 `fixture-count-still-inconsistent` — v4-B claimed at §0.1 v4-B row "reconciling the fixture count to **8-fixture test** ... consistently across §3.10 + §5 + §9.2 + §15"; spec at §5 line 115 confirms 8-fixture canonical, BUT §6 line 121 still said "the v4-amended Phase 1 deliverable (7-fixture test instead of 5)" — v4-B missed §6; v4-C fixes by updating §6 line 121 to "**8-fixture test** (was 5-fixture in v3; augmented to 7-fixture in v4-A; canonicalized to 8-fixture in v4-B per fixture-per-case parity rule, comprising 1 valid + 7 diagnostic fixtures one per case A1/A2/A3/C/D/E/E2)". (3) MEDIUM-2 `case-count-mathematically-contradictory` — v4-A/v4-B both said "8 file-state cases" (line 163) and "all 8 cases (A/A1/A2/A3/B/C/D/E/E2)" (line 380) — but A/A1/A2/A3/B/C/D/E/E2 is 9 labels, not 8; v4-C fixes by updating §9.2 header (line 163), §9.2 reference impl docstring (line 213), and §15 audit row 9 (line 380) to "9 cases (7 diagnostic + 2 non-diagnostic [Case A truly_absent + Case B success])" canonical count. **DISAGREEMENT NOTE on Cursor handoff prompt's recommendation**: handoff suggested wording "9 cases (8 diagnostic + 1 normal-path)" — v4-C respectfully diverges: by spec §9.2 line 179 "Case A is the only non-diagnostic absent-case" + Case B success path also produces "no log line. No activity-log row" (line 167 + 171), there are 7 diagnostic-emitting cases (A1/A2/A3/C/D/E/E2) + 2 non-diagnostic cases (A absent + B success); v4-C uses the spec-internally-consistent 7+2 split rather than the handoff-suggested 8+1 split. (4) LOW `unverified-metadata-overstated` — line 404 said "(unverified) not used in v4 — v4 has no unverified claims" but line 400 itself ("not re-probed in v4 authoring") IS technically an unverified claim; v4-C fixes by tightening line 404 to "v4 has no `(unverified)` tags except where explicitly cited as `(handoff claim — not re-probed in v4 authoring)` (the LD-604 verification carry-forward ... is the only such case)". NO functional spec changes — pure consistency / readability sweep + governance-authoring framing alignment. v4-B spec sha256 pre-edit `567d87b13a8fa05a38bfeabd8e62d7a897d09b51bb63a3aa0c1183ce67b67ce3`. v3 sha256 unchanged `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b` (confirmed via shasum at v4-C session start AND end). Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_C_ROUND_3_FIXES_V1` filed alongside, severity SOFT, task_category governance, enforcement awareness_only, scope_domain infra. Self-classification: STANDARD (consistency cleanup overlay; no new design decisions; no new gates; no functional changes).** |
| **v4-B** | **2026-05-09** | **Multi-section LOW consistency repair (closes the 3 LOW findings that v4-A had deferred). v4-A had partially closed inline (i) `OverrideFileMalformedError` constructor `path-vs-str(path)` via §3.10 NEW canonical exception API contract (lines 75-102), but the §0.1 v4-A row + §10 + §11 + §12 v4 row + §14 pre-execution checklist + Authoring metadata + Motivation paragraph all still said "3 LOW deferred" — internal contradiction. v4-B repairs by: (a) updating EVERY "3 LOW deferred" reference to "3 LOW closed (see §3.10 + §11 LD-622 substitution + §5/§9.2/§15 8-fixture reconciliation)"; (b) substituting `LD-NEW (this v4 session)` with `LD-622` in §11 reference index — the v4 spec-LD now has its real id post-filing in v4-A; (c) reconciling the fixture count to **8-fixture test (1 valid + 7 diagnostic, one fixture per diagnostic case A1/A2/A3/C/D/E/E2)** consistently across §3.10 + §5 + §9.2 + §15 (v4-A had a discrepancy: §5 enumerated 7 fixtures with only 6 diagnostic cases covered (layout-D split into 2 sub-fixtures + E/E2 missing), while §15 said "7 diagnostic-emitting fixtures" — irreconcilable; v4-B collapses layout to one fixture and adds E + E2 fixtures to give 1+7=8 total, with §15's "7 diagnostic-emitting fixtures" preserved as the diagnostic count). NO functional spec changes — this is a pure consistency/readability sweep. v4 sha256 pre-edit `354e48b61fe28bfb38d879ec8eef0ff571c8077c9681e989c0a2ed754a4bfc2f`. v3 sha256 unchanged `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b` (confirmed via shasum). Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_B_LOW_CONSISTENCY_V1` filed alongside, severity SOFT, task_category governance, enforcement awareness_only. Self-classification: STANDARD (consistency cleanup overlay; no new design decisions; no new gates; no functional changes).** |
| **v4-A** | **2026-05-09** | **Cursor cross-review of v3 returned 3 round-2 findings (1 HIGH + 2 MEDIUM + 3 LOW closed in v4-B). HIGH `os_error_surface_on_lstat`: v3's reference implementation catches only `FileNotFoundError` from `lstat()`; permission-denied / I/O / ENOTDIR / ELOOP errors at the metadata-call level are unspecified in v3's 6-case table. v4 fixes via NEW Case A3 (OSError-other-than-FileNotFoundError on `lstat/exists/is_symlink`) classified BEFORE Case A1 in the resolution order; reference implementation wraps the lstat call in `try/except (FileNotFoundError, OSError)` with branch dispatch on the exception class. MEDIUM-1 `toctou_silent_branch`: v3's `if not path.exists(): return {}` branch (post-lstat) is a silent path that produces no log line + no activity-log row, contradicting v3's "every failure mode produces a diagnostic" claim and sitting outside the 6-case table. v4 fixes by promoting the TOCTOU branch to its own NEW Case A2 (path-entry vanished between successful `lstat` and `exists` check) with logged + activity-row diagnostic identical in shape to Cases A1/C/D/E; rationale documented in §9.2 sub-note. MEDIUM-2 `reason_vocab_inconsistency`: v3 uses three different vocabulary styles (hyphen-tokens in log line documentation, underscore-tokens in reference impl, mixed in `OverrideFileMalformedError` kind strings). v4 pins canonical `OVERRIDE_FILE_REASON_VOCAB = {"truly_absent", "broken_symlink", "toctou_vanished", "metadata_os_error", "json_parse_error", "layout_error", "permission_denied", "io_error"}` (8-element set covering 1 normal-path Case A + 7 diagnostic cases A1/A2/A3/C/D/E/E2; Case E split into permission_denied / io_error variants) and applies uniformly across §9.2 log-line format documentation, reference implementation string literals, activity-log `reason` field, and `OverrideFileMalformedError(path, kind, cause)` constructor `kind` argument. §7 NEW risk #13 (operator telemetry parsing inconsistency; LIKELIHOOD LOW with v4 canonical vocab; SEVERITY LOW). §11 reference index appends v3 historical baseline + v4 self-reference + new LD-NEW for v4 spec-LD. §12 changelog row appended. v3 sha256 `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b` recorded for drift detection. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_OS_ERROR_TOCTOU_VOCAB_FIX_V1`. Cursor v3 review findings addressed: `os_error_surface_on_lstat` (HIGH) + `toctou_silent_branch` (MEDIUM) + `reason_vocab_inconsistency` (MEDIUM). **3 LOW findings CLOSED in v4-B (see §0.1 v4-B row above)**: (i) `OverrideFileMalformedError` constructor argument inconsistency `path-vs-str(path)` — closed via §3.10 NEW canonical exception API contract (str-typed `path` argument; v4 §9.2 reference impl already conforms); (ii) `§0 vs §11 LD-NEW labeling readability` — closed via §11 LD-622 substitution (v4 spec-LD has real id post-filing); historical `LD-NEW (this <vN> session)` tokens in prior-version baseline rows are explicitly disambiguated by the substitution rule documented in §10; (iii) `§5/§9.2 fixture count vs §15 case-count reconciliation` — closed via 8-fixture canonical target (1 valid + 7 diagnostic, one fixture per diagnostic case A1/A2/A3/C/D/E/E2) applied uniformly across §3.10 + §5 + §9.2 + §15. v4-A authoring-time rationale (now historical): each LOW was originally classified as a readability / non-functional consistency item; v4-A closed the 3 highest-impact findings (HIGH classification gap + 2 MEDIUM consistency gaps) within the surgical amendment scope; v4-B subsequently closed the 3 LOW findings as a multi-section consistency repair. All other v3 design preserved verbatim by reference.** |
| v3-A | 2026-05-08 | (Preserved from v3 §0.1.) Cursor cross-review of v2 returned a HIGH Case-E classification-bug finding + a MEDIUM `LD-NEW` placeholder finding. v3 fixed via §9.2 NEW Case A1 (broken symlink classified BEFORE Case A) + reference implementation reorder + LD-604 substitution everywhere. Companion LD-613 `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V3_CASE_E_SYMLINK_FIX_V1` (verified live `(my probe)` 2026-05-09 in v4 authoring: id=613, status=active, severity=SOFT, task_category=governance). |
| v2-A | 2026-05-08 | (Preserved from v3 §0.1.) Cursor cross-review of v1 returned `AMEND_V2` (single Task E blocker — malformed override file behavior undefined). v2 fixed via §9.2 5-case enumeration + Decision 8 dual-Opus debate + Phase 1 4-fixture test + Gate 11 + risk #11. Companion LD-604. |
| v1 | 2026-05-08 | (Preserved from v3 §0.1.) Initial spec authored. 7 design decisions debated; 6-phase rollout; 10 pre-implementation gates; 10 risks; per-phase rollback; operational notes + override file + dog-fooding bypass. Companion LD-599. |

---

## §0 — Operating Mode (v4-C governance-authoring framing; supersedes v3 verbatim inheritance)

This document is **GOVERNANCE-AUTHORING.** No production code is written, no scripts are executed, no Directus rows are PATCHed against production-tracking collections (e.g., `prod_modules`, `prod_blockers`). Spec-authoring artifacts — LD filing in `prod_locked_decisions` and activity_log POSTs to `prod_activity_log` — ARE the deliverables of governance-authoring sessions per the project-wide Rule 35 / DS-29 discipline; these are NOT production code mutations and ARE the canonical pattern for spec sessions, not an exception. The v4 authoring chain has therefore filed multiple LDs across the v4-A / v4-B / v4-C sub-sessions:

- **v4-A** filed `LD-622` (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_OS_ERROR_TOCTOU_VOCAB_FIX_V1`) — the v4 spec-LD covering Cases A2 + A3 + reason-vocab + Case E split.
- **v4-B** filed `LD-628` (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_B_LOW_CONSISTENCY_V1`) — the v4-B consistency-repair LD covering §3.10 + §11 LD-622 substitution + §5/§9.2/§15 8-fixture reconciliation.
- **v4-C** filed `LD-636` (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_C_ROUND_3_FIXES_V1`) — the v4-C round-3 cleanup LD covering: governance-authoring framing rewrite (this §0 paragraph), §6 fixture-count reconciliation, §15 case-count reconciliation (9-case canonical), and unverified-metadata precision tightening at §Authoring-metadata bullet.

v4 inherits v3's §0 binding scope on all OTHER aspects (no production code mutation; no Directus production-tracking PATCHes; no parallel agent spawning).

[CONFIRMED — v4 self-bound list explicitly forbids modifying v1 spec, v2 spec, v3 spec, prior schema-migration specs (v1-v7), implementation handoff, schema-ref doc, weekly_preflight, settings.json, hook scripts, payload_validator.py (doesn't exist), Cursor review outputs, prior LD records (LD-599, LD-604, LD-613, LD-622, LD-628), prod_blockers. `(my probe)` self-bound list reaffirmed in v4 final report.]

## §0.2 — Self-classification (v4 = STANDARD; v3 was ARCHITECTURAL)

**STANDARD.** v4 is a surgical amendment to v3. The architectural blast-radius assessment from v3 §0.2 (cross-cutting infrastructure helper called by ≥10 scripts; failure mode is Layer 6 input/output variation enforcement) DOES NOT change. v4 closes 3 Cursor round-2 findings WITHIN the same architectural envelope: NEW Case A2 + A3 are reference-implementation correctness (not new operator-facing decisions); reason-vocab normalization is consistency, not new policy. No new Phase deliverables, no new gates, no new design decisions. Per zero-error-qa DS-26 self-classification rubric, surgical amendments to a previously-classified ARCHITECTURAL spec that introduce zero new operator-facing decisions and zero new policy gates self-classify as STANDARD even if the parent was ARCHITECTURAL.

---

## §1 — Goal (preserved verbatim from v3)

See `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v3.md` §1 (which preserves v2 §1 by reference, which preserves v1 §1 by reference). v4 inherits §1 unchanged.

---

## §2 — Background (preserved verbatim from v3)

See v3 §2. v4 inherits §2.1, §2.2, §2.3, §2.4 unchanged.

---

## §3 — Dual-Opus debate (8 decisions; preserved verbatim from v3) + canonical reason vocabulary (NEW v4 sub-section)

See v3 §3 — Decisions 1-8 preserved verbatim. v4 introduces NO new design decisions. v4 ADDS one normative vocabulary set used by §9.2 reference implementation, log-line format, activity-log `reason` field, and `OverrideFileMalformedError(path, kind, cause)` constructor `kind` argument:

### §3.9 — Canonical override-file reason vocabulary (NEW v4)

```python
OVERRIDE_FILE_REASON_VOCAB = {
    "truly_absent",        # Case A — file path-entry does not exist (lstat raises FileNotFoundError)
    "broken_symlink",      # Case A1 — path-entry is a symlink whose target is missing
    "toctou_vanished",     # Case A2 — path-entry vanished between successful lstat() and exists() (NEW v4; previously silent in v3)
    "metadata_os_error",   # Case A3 — OSError other than FileNotFoundError on lstat/exists/is_symlink (NEW v4; previously unspecified in v3)
    "json_parse_error",    # Case C — file present + readable + JSON parse fails
    "layout_error",        # Case D — file present + readable + JSON parses + layout invalid
    "permission_denied",   # Case E — file present + read_text raises PermissionError (subclass of OSError)
    "io_error",            # Case E2 (NEW v4 split from v3's Case E) — file present + read_text raises non-PermissionError OSError (transient I/O, ENOSPC during stream read, etc.)
}
```

**Normative vocabulary rule** (binds §9.2 + reference impl + log line + activity-log `reason` + exception `kind` argument):
- The vocabulary set is the SOLE source of truth for reason tokens.
- Tokens are lowercase + underscore-delimited (no hyphens, no camelCase, no spaces).
- Case A (truly_absent) and Case B (success) are the two non-diagnostic cases — Case A is in the vocab so telemetry can disambiguate "no log expected" from "log expected"; Case B is NOT in the vocab because Case B produces no diagnostic.
- Adding a new case in v5+ requires extending this vocab set in §3.9 + the §9.2 case table + the reference implementation simultaneously, OR explicitly documenting why a new case maps to an existing vocab token (e.g., a future "directory-not-readable" case might map to `metadata_os_error`).
- Operators grepping telemetry use this exact 8-token list across `~/.claude/state/payload_validator.log` (case-id token in `reason=` field), `prod_activity_log.details.reason`, and `OverrideFileMalformedError.kind`.

**Operator note (v4-D — closes Cursor round-5 LOW-2):** `truly_absent` is the only vocab token NEVER written to log line / activity-log row / exception kind (Case A produces no diagnostic per the §9.2 case table behavior column + the Diagnostic format paragraph that explicitly excludes Case A). It exists in the vocab solely for telemetry-consumer disambiguation between "no event expected" (Case A — operator ran the validator, no override file present, this is the intended steady state) and "event missing — investigate" (any other case). Operators grepping logs / activity-log rows / exception traces for `truly_absent` will always get zero matches by design; if a future implementer accidentally emits `truly_absent` in a diagnostic, that is a bug in the case-dispatcher (Case A should have early-returned `{}` without diagnostic).

### §3.10 — Canonical exception API contract (NEW v4 — closes Cursor round-2 LOW (i))

**Normative `OverrideFileMalformedError` constructor signature:**

```python
class OverrideFileMalformedError(Exception):
    def __init__(self, path: str, kind: str, cause: Optional[BaseException]) -> None:
        """
        path:  STRING form of the override-file path. ALWAYS pass `str(path_obj)` at the call site.
               The exception's `.path` attribute is `str` for all 8 cases. NEVER pass a Path object.
               Rationale: callers doing `e.path == "/etc/foo.json"` or logging `e.path` to JSON
               must see a stable string type regardless of which case raised.
        kind:  Token from `OVERRIDE_FILE_REASON_VOCAB` (see §3.9). One of:
               truly_absent | broken_symlink | toctou_vanished | metadata_os_error |
               json_parse_error | layout_error | permission_denied | io_error.
        cause: Underlying exception object (e.g., the caught FileNotFoundError, PermissionError,
               JSONDecodeError) OR None (for cases like broken_symlink / toctou_vanished where
               there is no caught exception — only a metadata-call divergence).
        """
        super().__init__(f"override file malformed: {path}: {kind}")
        self.path = path
        self.kind = kind
        self.cause = cause
```

**Implementer rule:** at every `raise OverrideFileMalformedError(...)` call site in the v4 §9.2 `_load_override_file` reference implementation (grep the fenced block — line numbers drift when the spec is edited), the FIRST argument is `str(path)`, never `path` directly. v4 §9.2 already conforms; this contract elevates it to normative.

**Test parity:** the §15 v4 audit row 9 (vocab-grep parity test) is extended to assert `isinstance(e.path, str)` for all 7 diagnostic raise-side fixtures (A1/A2/A3/C/D/E/E2 per the canonical 8-fixture test from §5/§9.2 post-v4-B reconciliation).

---

## §4 — Per-decision action table (preserved verbatim from v3)

See v3 §4. v4 adds no new rows.

---

## §5 — Implementation sequence (preserved verbatim from v3 with one mechanical augmentation)

See v3 §5 — Phases 0/1/2/3/4/5 preserved verbatim. v4 mechanical augmentation (canonical post-v4-B): Phase 1 unit-test deliverable is augmented from v3's 5-fixture test to **8-fixture test** (1 valid + 7 diagnostic, one fixture per diagnostic case from §9.2: valid / invalid-JSON [Case C] / invalid-layout [Case D] / broken-symlink [Case A1] / **toctou-vanished** [Case A2 NEW v4] / **metadata-os-error** [Case A3 NEW v4] / permission-denied [Case E] / **io-error** [Case E2 NEW v4]) per v4 §9.2 normative path. Fail-loud env-var test extends to assert each of the 7 diagnostic cases raises `OverrideFileMalformedError(str(path), kind, cause)` with the canonical `kind` token from §3.9 and `isinstance(e.path, str)` per §3.10. The TOCTOU fixture is constructed by mocking `Path.exists` to return False after a successful `lstat()`; the metadata-os-error fixture is constructed by mocking `Path.lstat` to raise `PermissionError` (a non-FileNotFoundError OSError subclass) on the first call; the io-error fixture is constructed by mocking `Path.read_text` to raise `OSError(errno.EIO)`. v4-B reconciliation NOTE: prior v4-A wording said "7-fixture test" but enumerated only 6 diagnostic cases (layout-D split into 2 sub-fixtures while E + E2 missing) — irreconcilable with §15's "all 7 diagnostic-emitting fixtures" claim. v4-B canonicalizes to 1 valid + 7 diagnostic = 8 fixtures total, one per diagnostic case A1/A2/A3/C/D/E/E2; layout-D is one fixture; if implementers want 2-sub-fixture coverage on layout (not-dict vs bad-key) they MAY add a 9th fixture but the 8-fixture count is the normative minimum for case-parity.

---

## §6 — Pre-implementation gates Kim must approve (preserved verbatim from v3)

See v3 §6 — 11-row gate table preserved verbatim. v4 adds no new gates; the v4 amendments (Case A2 + A3 + reason-vocab normalization) are implementation correctness + consistency, not new operator-facing policy. Gates 1-11 from v3 remain binding for Phase 1 implementation. The v4-amended Phase 1 deliverable (**8-fixture test** — was 5-fixture in v3; augmented to 7-fixture in v4-A interim wording; canonicalized to 8-fixture in v4-B per fixture-per-case parity rule, comprising 1 valid + 7 diagnostic fixtures one per case A1/A2/A3/C/D/E/E2) flows through Gate 11 (Decision 8 fail-mode policy) without modification — Cases A2 + A3 are two more file-state branches covered by the same fail-safe-default-plus-opt-in-fail-loud policy.

---

## §7 — Risk assessment (v4 extends v3's 12-row table to 13 rows)

The table below preserves v3 rows 1-12 verbatim by reference and appends row 13 (NEW for v4 — operator telemetry parsing inconsistency caused by mixed vocabulary).

| # | Risk | Likelihood | Severity | Mitigation |
|---|------|------------|----------|------------|
| 1-12 | (Preserved verbatim from v3 §7 — see v3 spec for full text. Includes: existing-script breakage on Phase 4 promotion (#1), schema cache staleness (#2), perf impact (#3), Directus outage hard halt (#4), migration race (#5), auto-field stripping (#6), over-broad opt-out (#7), dog-fooding recursion (#8), retired-field grace drift (#9), per-process cache inconsistency (#10), override-file malformed silent fallback (#11 NEW v2), implementer copies v2-style impl literally → broken symlink misclassifies (#12 NEW v3).) | (per v3) | (per v3) | (per v3) |
| **13** | **NEW v4 — Operator telemetry parsing breaks because reason-token vocabulary is inconsistent across log line + activity-log row + exception `kind`. v3 reference implementation passes `"json_parse_error"` to log + `"json_parse_error"` to activity-log + `"json_parse_error"` to `OverrideFileMalformedError` (consistent for that case), but v3 also passes `"layout_invalid"` to `OverrideFileMalformedError` while v3 §9.2 log-line documentation says `reason=layout-error-description` (hyphen-delimited, mismatched). Operator running `grep "reason=layout_error" payload_validator.log` would get zero matches even though layout-invalid events occurred. Operator running `SELECT * FROM prod_activity_log WHERE details->>'reason' = 'layout_error'` would also miss. Existing v3 grep/filter recipes in operator runbooks (if any are written) would silently miss events.** | **LOW (with v4 canonical `OVERRIDE_FILE_REASON_VOCAB` from §3.9 + uniform application across log-line format, reference impl, activity-log details, exception kind; the bug only resurfaces if a future implementer re-introduces hyphen-delimited tokens in log lines or mixed vocabulary in exception construction)** | **LOW (silent operator telemetry miss — operator believes "no layout errors occurred this week" when in fact 12 occurred; bounded by the rarity of override-file edits + the existence of activity-log rows under the canonical vocab + the absence of operator-facing dashboards consuming this telemetry today)** | **(1) v4 §3.9 canonical vocabulary set pinned + applied uniformly across §9.2 log line documentation, reference implementation `_log_malformed_override` calls, activity-log details `reason` field, and `OverrideFileMalformedError(path, kind, cause)` constructor `kind` argument; (2) v4 §9.2 reference implementation rewritten to pass the EXACT vocab token from §3.9 in every diagnostic-emitting branch; (3) v4 §15 audit row 9 (NEW v4) verifies grep parity — given the 8-fixture Phase 1 test (1 valid + 7 diagnostic post-v4-B reconciliation), the test asserts that the log line, activity-log row, and exception kind for each diagnostic fixture all use the SAME vocab token; (4) telemetry-consumer compatibility: v4 operators reading the per-day count telemetry from §9.4 row 5 disambiguate cases via the canonical 8-token vocabulary instead of mixed strings; (5) future maintainers extending the case table MUST extend §3.9 vocab simultaneously per the normative rule.** |

**Top 3 risks by severity-x-likelihood (v4-updated):**
1. **Risk #1 — Existing script breakage on Phase 4 promotion** (MEDIUM × HIGH). (Preserved from v3.)
2. **Risk #5 — Migration race condition** (LOW × HIGH). (Preserved from v3.)
3. **Risk #8 — Dog-fooding recursion** (LOW × HIGH). (Preserved from v3.)

Risks #11, #12, #13 do NOT enter the top-3 — all three are MEDIUM or LOW severity bounded by the rarity-of-edit pattern + the diagnostic + the opt-in fail-loud env var + the v4 canonical vocab. v4 introduces one new MEDIUM-classification gap (Case A3 — OSError on metadata calls) which is mitigated within Risk #11/#12's family rather than as a new top-line risk: Case A3 + Case A2 are now first-class entries in the §9.2 case table, share the diagnostic + fail-mode policy with Cases A1/C/D/E/E2, and inherit the test fixture / log line / activity-log row behavior from Phase 1.

---

## §8 — Rollback per phase (preserved verbatim from v3)

See v3 §8 (which preserves v2 §8 by reference, which preserves v1 §8 by reference). v4 inherits the per-phase rollback table unchanged. The Phase 1 v4 augmentation (8-fixture test post-v4-B reconciliation; was 7-fixture in v4-A interim wording; v3 baseline 5-fixture) is deliverables-only and rolls back the same way as v1/v2/v3 Phase 1: delete `Production/lib/payload_validator.py` + companion test file.

---

## §9 — Operational notes

### §9.1 — Debug toggle env var (preserved verbatim from v3)

`MN_PAYLOAD_VALIDATOR_DISABLE=1` — when set in environment, validator is a no-op. (Per v3.)

### §9.2 — Per-collection override file (REWRITTEN for v4 — closes Cursor v3 round-2 HIGH `os_error_surface_on_lstat` + MEDIUM `toctou_silent_branch` + MEDIUM `reason_vocab_inconsistency`)

**Path:** `~/.claude/state/payload_validator_overrides.json` (preserved from v3).

**File schema (when present + valid):** preserved from v3 §9.2 verbatim. (See v3 spec.)

**Layout-validation rules:** preserved from v3 §9.2 verbatim. (See v3 spec.)

**Single normative path for the 9 file-state cases — 7 diagnostic + 2 non-diagnostic [Case A truly_absent + Case B success]** (v4 EXTENDS v3's 6-case table with NEW Case A2 — TOCTOU vanish promoted to logged path — and NEW Case A3 — OSError other than FileNotFoundError on metadata calls — and SPLITS v3's Case E into Case E (PermissionError) + Case E2 (other OSError); fixes the HIGH OSError-surface gap + MEDIUM TOCTOU silent path that Cursor surfaced on v3). Canonical case label set: A/A1/A2/A3/B/C/D/E/E2 — 9 labels total (v4-C correction; v3 had 6, v4-A had 8 enumerated but mis-counted "8 cases" while listing 9 labels A/A1/A2/A3/B/C/D/E/E2 — v4-C reconciles to 9):

| # | File state | Detection method | Vocab token (per §3.9) | Behavior |
|---|------------|------------------|------------------------|----------|
| **A** | **File truly absent** | `path.lstat()` raises `FileNotFoundError` | `truly_absent` | Return `{}`. Use defaults for all collections. No log line. No activity-log row. (v3 baseline preserved.) |
| **A1** | **Broken symlink** | `path.lstat()` succeeds AND `path.is_symlink()` returns True AND `path.exists()` returns False | `broken_symlink` | Default fail-safe path: emit ERROR log line; queue activity-log row; return `{}`. With env var `loud`, raise `OverrideFileMalformedError(str(path), "broken_symlink", None)`. (v3 baseline preserved.) |
| **A2** | **TOCTOU vanish** (path-entry existed at lstat() time but `exists()` returns False afterward, AND it's NOT a broken symlink — the entry was concurrently removed; possible during a directory rename or a parallel-process unlink between metadata calls) | `path.lstat()` succeeds AND `path.is_symlink()` returns False AND `path.exists()` returns False | `toctou_vanished` | **NEW v4 (closes Cursor MEDIUM-1).** Default fail-safe path: emit ERROR log line; queue activity-log row `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` (action) with `reason="toctou_vanished"` + `details.case="A2"` + `attempted_at` ISO-8601 UTC; return `{}` (fail-safe). With env var `loud`, raise `OverrideFileMalformedError(str(path), "toctou_vanished", None)`. **Rationale (Cursor MEDIUM-1 closure):** v3 had this branch present in the reference implementation but produced no diagnostic, contradicting the "every failure mode produces a diagnostic" claim and sitting outside v3's 6-case table. v4 promotes the branch to a first-class case so the silent-success path is closed and operator telemetry is complete. |
| **A3** | **Metadata-call OSError** (any OSError on `lstat()` / `exists()` / `is_symlink()` that is NOT `FileNotFoundError` — e.g., `PermissionError` on the parent directory, `NotADirectoryError` if a parent component is unexpectedly a file, `OSError` with errno `ELOOP` for excessive symlink chains, transient I/O errors at the metadata layer) | The first metadata call (`lstat()`) raises `OSError` AND the exception is NOT `FileNotFoundError` (which is Case A); OR a subsequent `is_symlink()` / `exists()` call raises `OSError` (caught by an inner try/except in the reference impl) | `metadata_os_error` | **NEW v4 (closes Cursor HIGH).** Default fail-safe path: emit ERROR log line with `reason="metadata_os_error"` + `os_error=<exception str>`; queue activity-log row with `details.case="A3"` + `details.os_error=<str(e)>` + `details.errno=<e.errno>` (when available) + `attempted_at` ISO-8601 UTC; return `{}` (fail-safe). With env var `loud`, raise `OverrideFileMalformedError(str(path), "metadata_os_error", e)`. **Rationale (Cursor HIGH closure):** v3's reference implementation only caught `FileNotFoundError` from `lstat()` — a `PermissionError` (chmod 000 on the parent dir) or `OSError` with errno ELOOP would have escaped the try/except entirely and crashed the validator at module-import time, defeating fail-safe semantics for the entire ecosystem of 30+ caller scripts. v4 catches all `OSError` subclasses at the metadata-call layer and routes them through Case A3, preserving fail-safe + diagnostic. |
| **B** | **File present + valid JSON + valid layout** | `path.exists()` True AND `read_text()` succeeds AND `json.loads(content)` succeeds AND `_validate_override_layout(parsed)` returns True | (none — no diagnostic on success) | Return parsed dict. No log line. No activity-log row. (v3 baseline preserved.) |
| **C** | **File present + JSON parse fails** | `read_text()` succeeds AND `json.loads(content)` raises `json.JSONDecodeError` | `json_parse_error` | Default fail-safe path: emit log + actrow; return `{}`. With env var `loud`, raise `OverrideFileMalformedError(str(path), "json_parse_error", e)`. (v3 baseline preserved with vocab token normalized.) |
| **D** | **File present + JSON parses but layout invalid** | `_validate_override_layout(parsed)` returns False | `layout_error` (v4 normalized; v3 used `"layout_invalid"` in exception kind + `"layout-error-description"` in log line — both replaced with `"layout_error"` per §3.9) | Default fail-safe path: emit log + actrow; return `{}`. With env var `loud`, raise `OverrideFileMalformedError(str(path), "layout_error", reason)`. (v3 logic preserved; vocab token normalized.) |
| **E** | **File present + permission denied on read** | `path.read_text()` raises `PermissionError` (subclass of `OSError`) | `permission_denied` | Default fail-safe path: emit log + actrow; return `{}`. With env var `loud`, raise `OverrideFileMalformedError(str(path), "permission_denied", e)`. (v3 baseline preserved with vocab token normalized.) |
| **E2** | **File present + non-permission OSError on read** (transient I/O error during stream read, ENOSPC, etc. — split from v3's Case E for vocab-token clarity) | `path.read_text()` raises `OSError` AND it is NOT a `PermissionError` | `io_error` | **NEW v4 (vocab-token clarity split from v3 Case E).** Default fail-safe path: emit log + actrow; return `{}`. With env var `loud`, raise `OverrideFileMalformedError(str(path), "io_error", e)`. **Rationale:** v3's Case E lumped permission-denied + transient I/O into one bucket. v4 splits them so operators can disambiguate "fix the file ACL" (Case E) from "filesystem is sick / disk full / transient I/O" (Case E2) without parsing the OSError string. |

**Resolution-order invariant** (v4 — extends v3's `A → A1 → E → C → D → B` to `A (FileNotFoundError on lstat) → A3 (other OSError on lstat) → A1 (broken symlink) → A2 (TOCTOU vanish) → E (PermissionError on read) → E2 (other OSError on read) → C (JSON parse) → D (layout) → B (success)`). The case dispatcher MUST follow this order. Each failure mode lands in exactly one case — no silent path, no escape from the table.

**Diagnostic format** (cases A1, A2, A3, C, D, E, E2 — Case A is the only non-diagnostic absent-case):

- **Log line** (appended to `~/.claude/state/payload_validator.log`, ERROR level; v4 normalizes to canonical vocab):
  ```
  [PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED] <iso8601-utc> path=<absolute-path> case=<A1|A2|A3|C|D|E|E2> reason=<canonical_vocab_token> [os_error=<str>] [parse_error=<str>] [layout_error=<str>]
  ```
  v4 NOTE: `reason=` value is ONE of the 8 canonical tokens from §3.9 (`truly_absent` is reserved for Case A which produces no log line; in practice log lines emit one of `broken_symlink | toctou_vanished | metadata_os_error | json_parse_error | layout_error | permission_denied | io_error`).

- **Activity-log row** (POSTed to `prod_activity_log` via `try_post_or_queue` with `_VALIDATOR_INTERNAL_BYPASS=True` per §9.3):
  - `action`: `PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED`
  - `details` (dict — NO `task_description` per LD-597; uses ONLY fields valid for `prod_activity_log`):
    - `path`: absolute path string of the override file
    - `case`: `"A1" | "A2" | "A3" | "C" | "D" | "E" | "E2"` (v4-extended from v3's `"A1" | "C" | "D" | "E"`)
    - `reason`: canonical vocab token from §3.9 — exactly one of `{"broken_symlink", "toctou_vanished", "metadata_os_error", "json_parse_error", "layout_error", "permission_denied", "io_error"}` (Case A produces no row so `truly_absent` is not emitted to activity-log)
    - `content_sha256`: sha256 of the raw file content (or `null` if read was not attempted — Cases A1/A2/A3)
    - `parse_error`: JSON decode error message string (Case C only; absent for others)
    - `layout_error`: layout-failure description string (Case D only; absent for others)
    - `os_error`: OSError string (Cases A3/E/E2 only; absent for others)
    - `errno`: integer errno value (Cases A3/E/E2 when `e.errno` is non-None; absent otherwise) (NEW v4 — operators can disambiguate ELOOP from EACCES from EIO via numeric errno without parsing the string)
    - `symlink_target`: result of `os.readlink(str(path))` if Case A1 (preserved from v3); absent for others
    - `attempted_at`: ISO-8601 UTC timestamp of the load attempt
    - `recovery_action`: `"defaults_used"` (default fail-safe) OR `"raised_OverrideFileMalformedError"` (fail-loud env var)
    - `fail_mode`: `"safe"` (default) OR `"loud"` (env var set)
  - `module_id`: null (validator is global)
  - `performed_by`: `"payload_validator"`

**Re-read frequency:** preserved from v3 — override file is read at module-import time AND on every `invalidate_schema_cache()` call.

**Env-var opt-in to fail-loud:** preserved from v3 (`MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE=loud`); v4 extension: cases A2 + A3 + E2 also raise `OverrideFileMalformedError(str(path), kind, cause)` with `kind` from §3.9 canonical vocab.

**Reference implementation** (v4 — REWRITTEN to close all 3 Cursor v3 round-2 findings; not normative — the §9.2 case table above is normative; this implementation is illustrative):

```python
def _load_override_file() -> dict:
    """Load per-collection override config. v4 normative path per §9.2 9-case table (7 diagnostic + 2 non-diagnostic).

    Resolution order (v4): A → A3 → A1 → A2 → E → E2 → C → D → B.
    Closes Cursor v3 round-2 findings:
      - HIGH (os_error_surface_on_lstat): metadata-call OSError other than
        FileNotFoundError now lands in NEW Case A3 instead of crashing the
        validator at import time.
      - MEDIUM-1 (toctou_silent_branch): TOCTOU vanish branch promoted from
        silent return to NEW Case A2 with logged + activity-row diagnostic.
      - MEDIUM-2 (reason_vocab_inconsistency): all reason tokens drawn from
        §3.9 OVERRIDE_FILE_REASON_VOCAB; uniform across log line, activity
        row reason field, and OverrideFileMalformedError kind argument.
    """
    path = Path("~/.claude/state/payload_validator_overrides.json").expanduser()

    # Case A vs Case A3: distinguish "no entry at path" from "metadata-call OSError".
    # v4 catches all OSError subclasses at the lstat layer; FileNotFoundError → A,
    # everything else (PermissionError, NotADirectoryError, ELOOP OSError, ...) → A3.
    try:
        path.lstat()
    except FileNotFoundError:
        return {}  # Case A: truly_absent; no log; no activity row
    except OSError as e:  # NEW v4 — closes Cursor HIGH
        _log_malformed_override(path, None, "metadata_os_error", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "metadata_os_error", e)
        return {}  # Case A3 (fail-safe)

    # Case A1 vs A2: lstat succeeded; if exists() (which follows symlinks) is False,
    # decide between broken-symlink (A1) and concurrent-removal-vanish (A2).
    # v4 wraps these calls in try/except OSError too — defensive against rare
    # filesystem states where is_symlink() / exists() raise post-lstat. If they
    # raise, route to A3.
    try:
        is_link = path.is_symlink()
        exists_after_lstat = path.exists()
    except OSError as e:  # NEW v4 — defensive belt-and-suspenders for HIGH closure
        _log_malformed_override(path, None, "metadata_os_error", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "metadata_os_error", e)
        return {}  # Case A3 (fail-safe; secondary metadata-OSError landing)

    if is_link and not exists_after_lstat:
        _log_malformed_override(path, None, "broken_symlink", None)
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "broken_symlink", None)
        return {}  # Case A1 (fail-safe)

    if not exists_after_lstat:
        # NEW v4 — promotes v3's silent TOCTOU-vanish branch to logged path.
        # Closes Cursor MEDIUM-1: every failure mode produces a diagnostic.
        _log_malformed_override(path, None, "toctou_vanished", None)
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "toctou_vanished", None)
        return {}  # Case A2 (fail-safe)

    # Case E vs E2: read_text() failure; PermissionError → E, other OSError → E2.
    try:
        content = path.read_text()
    except PermissionError as e:
        _log_malformed_override(path, None, "permission_denied", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "permission_denied", e)
        return {}  # Case E (fail-safe)
    except OSError as e:  # NEW v4 — split from v3's Case E for vocab clarity
        _log_malformed_override(path, None, "io_error", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "io_error", e)
        return {}  # Case E2 (fail-safe)

    # Case C: JSON parse failure
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        _log_malformed_override(path, content, "json_parse_error", str(e))
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "json_parse_error", e)
        return {}  # Case C (fail-safe)

    # Case D: layout invalid (vocab normalized — v3 used "layout_invalid"; v4 uses "layout_error")
    if not _validate_override_layout(parsed):
        reason_str = _describe_layout_failure(parsed)
        _log_malformed_override(path, content, "layout_error", reason_str)
        if os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud":
            raise OverrideFileMalformedError(str(path), "layout_error", reason_str)
        return {}  # Case D (fail-safe)

    return parsed  # Case B: success
```

**Test coverage** (Phase 1 deliverable per §5 v4 augmentation; canonical post-v4-B): **8-fixture test** (1 valid + 7 diagnostic, one fixture per diagnostic case A1/A2/A3/C/D/E/E2 per §9.2 normative path: valid + invalid-JSON [C] + invalid-layout [D] + broken-symlink [A1] + **toctou-vanished** [A2 NEW v4] + **metadata-os-error** [A3 NEW v4] + permission-denied [E] + **io-error** [E2 NEW v4]) + 1 fail-loud env-var test extended to assert each of the 7 diagnostic cases raises `OverrideFileMalformedError(str(path), kind, cause)` with the canonical vocab `kind` token from §3.9 and `isinstance(e.path, str)` per §3.10 contract. Vocab-grep parity test (NEW v4 per Risk #13 mitigation): assert that for each diagnostic fixture, the log line `reason=` value, the activity-log row `details.reason` field, and the raised exception `kind` argument are all the SAME canonical token from §3.9.

### §9.3 — Logging strategy (preserved verbatim from v3)

See v3 §9.3. v4 inherits the `_VALIDATOR_INTERNAL_BYPASS` thread-local pattern unchanged. v4 Cases A2 + A3 + E2 activity-log rows use this bypass identically to Cases A1/C/D/E.

### §9.4 — Telemetry expected post-Phase-4 (preserved verbatim from v3 with one v4 addition)

See v3 §9.4. v4 NOTE: row 5 (`PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED` per-day count) now includes Cases A2 + A3 + E2 events; operators reading telemetry should disambiguate via `details.case` field per v4 §9.2 case-id schema using the canonical 8-token vocabulary from §3.9.

---

## §10 — Cursor cross-review companion handoff (UPDATED for v4)

The v3 §10 noted Cursor's v2 review verdict surfaced HIGH Case-E + MEDIUM `LD-NEW`. v4 has been authored in response to Cursor's v3 round-2 cross-review which surfaced 3 additional findings (1 HIGH + 2 MEDIUM + 3 LOW closed in v4-B per §0.1 v4-B changelog row):

- **Cursor v3 round-2 HIGH `os_error_surface_on_lstat`:** v3 reference implementation only catches `FileNotFoundError` from `lstat()`; other OS errors (PermissionError on parent, ENOTDIR, ELOOP, transient I/O) are unspecified in v3's 6-case table. v4 fixes via §9.2 NEW Case A3 (metadata-call OSError) classified BEFORE Case A1 in resolution order; reference implementation wraps `lstat()` in `try/except (FileNotFoundError, OSError)` with branch dispatch + secondary defensive try/except around `is_symlink()` + `exists()`.
- **Cursor v3 round-2 MEDIUM-1 `toctou_silent_branch`:** v3 had a "defensive TOCTOU" branch (`if not path.exists(): return {}` post-lstat) that produced no log line + no activity row, contradicting v3's "every failure mode produces a diagnostic" claim and sitting outside the 6-case table. v4 fixes by promoting the branch to NEW Case A2 with logged + activity-row diagnostic identical in shape to A1/C/D/E.
- **Cursor v3 round-2 MEDIUM-2 `reason_vocab_inconsistency`:** v3 used three different vocabulary styles (hyphen-tokens in log line documentation, underscore-tokens in reference impl, mixed in exception construction). v4 fixes via §3.9 NEW canonical `OVERRIDE_FILE_REASON_VOCAB` set + uniform application across log line format, reference implementation, activity-log details, and `OverrideFileMalformedError(path, kind, cause)` constructor `kind` argument.
- **Cursor v3 round-2 LOW (i) `OverrideFileMalformedError_constructor_path_vs_str_path` — CLOSED:** see §3.10 NEW canonical exception API contract below. The `OverrideFileMalformedError(path, kind, cause)` constructor's `path` argument is normatively typed as `str` (always pass `str(path)` at the call site). The exception object's `.path` attribute is `str` for all diagnostic-raising cases. v4 reference implementation in §9.2 already conforms (every `raise OverrideFileMalformedError` in `_load_override_file` passes `str(path)`); §3.10 elevates this to a normative contract.
- **Cursor v3 round-2 LOW (ii) `LD_NEW_labeling_readability_§0_vs_§11` — CLOSED in v4-B:** §11 reference index now substitutes the v4 spec-LD's `LD-NEW (this v4 session)` placeholder with the real id `LD-622` filed in this v4 session. The remaining `LD-NEW` tokens in v4 §0.1 v3-row + v3 §0.1 baseline (preserved by reference) are HISTORICAL placeholders for v3's then-unfiled spec-LD (now LD-613) — no readability conflict because the substitution rule is: any `LD-NEW (this <vN> session)` resolves to the LD filed for that session (v3 → LD-613; v4 → LD-622).
- **Cursor v3 round-2 LOW (iii) `§5_§9.2_§15_fixture_count_reconciliation` — CLOSED in v4-B:** see §5 v4-amendment paragraph + §9.2 Test coverage paragraph + §15 v4 audit row + §3.10 Test parity paragraph. Canonical post-v4-B target: **8-fixture test (1 valid + 7 diagnostic, one fixture per diagnostic case A1/A2/A3/C/D/E/E2)** applied uniformly across all 4 sections. v3's "5-fixture" + "all 6 cases" stale text is superseded by v4-B's 8-fixture canonical target. v4-A's interim "7-fixture" wording (which enumerated only 6 diagnostic cases — layout-D split into 2 sub-fixtures while E + E2 missing — irreconcilable with §15's "all 7 diagnostic-emitting fixtures" claim) is reconciled in v4-B by collapsing layout to one fixture and adding E + E2 fixtures. §15 v4 audit row 9 verifies vocab-grep parity for all 7 diagnostic fixtures (the 1 valid fixture has no diagnostic to assert parity over).

**Cursor v4 review authorship:** RECOMMENDED before Phase 1 implementation begins per v3 §6 Gate 10 (preserved). Future Cursor v4 review handoff path: `Production/docs/HANDOFF_CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_v4_20260509.md` (NOT authored in this v4 session per self-bound list).

---

## §11 — Reference index (v4 appends v3 historical baseline + v4 self-reference + v4 spec-LD)

**Preserved from v3 §11 verbatim by reference** (v3 reference index includes all v1/v2 entries + LD-595/596/597/598/364/599/604 + LD-613 added during v3 authoring). v4 extends:

**NEW for v4** (appended below):

- **`Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v3.md`** — v4's historical baseline; sha256 `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b`; 403 lines; authored 2026-05-08. v4 inherits Decisions 1-8, Phases 0/1/2/3/4/5, Gates 1-11, Risks 1-12 verbatim by reference.
- **`Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v4.md`** — this document (self-reference); supersedes v3; addresses Cursor v3 round-2 HIGH `os_error_surface_on_lstat` + MEDIUM-1 `toctou_silent_branch` + MEDIUM-2 `reason_vocab_inconsistency`. 3 LOW findings closed in v4-B (see §0.1 v4-B changelog row).
- **LD-622** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_OS_ERROR_TOCTOU_VOCAB_FIX_V1`) — this v4's spec-LD (v4-A); filed in this v4 session per §0 Operating Mode; documents NEW Case A2 + A3 + canonical `OVERRIDE_FILE_REASON_VOCAB` + Case E split into E + E2. **(Read-back per Rule 35 confirmed in v4 final report.)** Substitution NOTE (v4-B closure of LOW (ii)): the `LD-NEW (this v4 session)` placeholder in v4-A authoring is now resolved to the real id `LD-622`; historical `LD-NEW` tokens in prior-version baseline rows of §0.1 + §12 retain their `(this <vN> session)` qualifiers and resolve via the substitution rule documented in §10.
- **LD-628** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_B_LOW_CONSISTENCY_V1`) — v4-B follow-up consistency-repair LD; filed in v4-B sub-session per `(handoff claim)` (activity log row 2006 references this LD id); documents the multi-section LOW closure sweep (§3.10 NEW canonical exception API contract + §11 LD-622 substitution + §5/§9.2/§15 8-fixture canonical reconciliation + §10 + §0.1 v4-B row + Authoring metadata + §14 pre-execution checklist updates). Severity SOFT, task_category governance, enforcement awareness_only, scope_domain infra. **(Read-back per Rule 35 confirmed in v4-B final report.)** v4-C substitution NOTE: LD-NEW-v4-B placeholder previously at this position is now resolved to `LD-628` per Cursor round-3 finding HIGH closure.
- **LD-636** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_C_ROUND_3_FIXES_V1`) — v4-C round-3 cleanup LD; filed in v4-C sub-session; documents 4-finding closure (1 HIGH governance-framing + §11 LD-628 substitution; 1 MEDIUM-1 §6 8-fixture canonical extension; 1 MEDIUM-2 9-case canonical reconciliation across §9.2 line 163, §9.2 line 213 docstring, and §15 audit row 9; 1 LOW unverified-metadata precision tightening at §Authoring-metadata bullet) + verification-phase findings table comparing v4-B claimed vs spec actual. Severity SOFT, task_category governance, enforcement awareness_only, scope_domain infra. **(Read-back per Rule 35 confirmed in v4-C final report — id=636, decision_key matches, status=active, severity=SOFT, task_category=governance, enforcement_type=awareness_only, scope_domain=infra, source_document=Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v4.md, decision_text length 3479 chars.)**
- **LD-644** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_D_ROUND_5_FIXES_V1`) — v4-D round-5 cleanup LD; filed in v4-D sub-session; documents VERIFICATION-PHASE FINDING that 5 of 6 Cursor round-5 prompt-recommended fixes were already landed by v4-C predecessor (HIGH line-5 GOVERNANCE-AUTHORING / MEDIUM-1 §12 v4 row 9-case / MEDIUM-2 §3.10 grep-anchored / MEDIUM-3 [CONFIRMED] footer DS-29 / LOW-1 §11 repo-relative); applies ONLY 1 surviving finding (LOW-2 `truly_absent` operator FAQ added at §3.9). Cross-refs: predecessor LDs LD-622 + LD-628 + LD-636. Severity SOFT, task_category governance, enforcement awareness_only, scope_domain infra. **(Read-back per Rule 35 confirmed in v4-D final report — id=644, decision_key matches, status=active, severity=SOFT, task_category=governance, enforcement_type=awareness_only, scope_domain=infra, source_document=Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v4.md, decision_text length 3929 chars.)**
- **LD-613** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V3_CASE_E_SYMLINK_FIX_V1`) — v3 spec-LD; verified live 2026-05-09 `(my probe)`: id=613, decision_key matches, status=`active`, severity=SOFT, task_category=governance.

---

## §12 — Changelog (v4 appends one row to v3)

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-05-08 | (Preserved.) Initial spec authored. |
| v2 | 2026-05-08 | (Preserved.) Address Cursor cross-review of v1 (`AMEND_V2`); §9.2 5-case enumeration + Decision 8 + Gate 11 + risk #11; LD-604. |
| v3 | 2026-05-08 | (Preserved.) Address Cursor cross-review of v2 (HIGH `case_e_symlink` + MEDIUM `ld_new_placeholder`); §9.2 NEW Case A1 broken symlink + reference impl reorder + LD-NEW→LD-604 substitution; risk #12; LD-613. |
| **v4** | **2026-05-09** | **Address Cursor cross-review of v3 round-2 (HIGH `os_error_surface_on_lstat` + MEDIUM-1 `toctou_silent_branch` + MEDIUM-2 `reason_vocab_inconsistency`; 3 LOW closed in v4-B per §0.1 v4-B row). Changes: §3.9 NEW canonical `OVERRIDE_FILE_REASON_VOCAB` set (8 tokens) pinned and applied uniformly across §9.2 log line, reference impl, activity-log details, and `OverrideFileMalformedError(path, kind, cause)` constructor `kind` arg. §9.2 **9 file-state case labels** (7 diagnostic + 2 non-diagnostic per v4-C) — NEW Case A2 (TOCTOU vanish promoted from silent to logged path; closes MEDIUM-1) + NEW Case A3 (metadata-call OSError other than FileNotFoundError; closes HIGH) + Case E split into E (PermissionError) + E2 (other OSError) for vocab-token clarity; reference implementation rewritten with `try/except (FileNotFoundError, OSError)` at lstat layer + secondary defensive `try/except OSError` around `is_symlink()`/`exists()` + split read-time exception catching; resolution-order invariant updated to `A → A3 → A1 → A2 → E → E2 → C → D → B`; activity-log details schema gains `errno` field. §7 NEW risk #13 (operator telemetry parsing inconsistency caused by mixed reason-token vocabulary; LIKELIHOOD LOW with v4 canonical vocab; SEVERITY LOW). §11 reference index appends v3 historical baseline (sha256 `e267a44...`) + v4 self-reference + v4 spec-LD + LD-613 cross-reference. §12 this row. §5 Phase 1 deliverable mechanically augmented from 5-fixture to 8-fixture test post-v4-B (1 valid + 7 diagnostic, one per diagnostic case A1/A2/A3/C/D/E/E2; v4-A interim wording said "7-fixture" with 6 diagnostic cases covered, reconciled in v4-B) + vocab-grep parity test (NEW v4 per Risk #13 mitigation). §15 augmentation row 9 NEW v4. v3 baseline sha256 `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b` recorded for drift detection. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_OS_ERROR_TOCTOU_VOCAB_FIX_V1` filed alongside. 3 LOW round-2 findings CLOSED in v4-B (multi-section consistency repair): (i) `OverrideFileMalformedError` constructor `path-vs-str(path)` argument-type consistency — closed via §3.10 NEW canonical exception API contract; (ii) `LD-NEW` labeling readability §0 vs §11 — closed via §11 LD-622 substitution; (iii) §5/§9.2/§15 fixture count reconciliation — closed via 8-fixture canonical target (1 valid + 7 diagnostic) applied uniformly across §3.10 + §5 + §9.2 + §15. Self-classification: STANDARD (surgical amendment overlay; no new operator decisions; no new gates; reference-impl correctness + vocab normalization + consistency cleanup only). All other v3 design preserved verbatim by reference. Cursor v3 round-2 findings addressed: `os_error_surface_on_lstat` (HIGH) + `toctou_silent_branch` (MEDIUM-1) + `reason_vocab_inconsistency` (MEDIUM-2).** |
| **v4-B** | **2026-05-09** | **Multi-section LOW consistency repair (closes the 3 LOW findings that v4-A had deferred). Sections updated: §0.1 (v4-B row added above v4-A); §3.10 (already complete from v4-A — NEW canonical exception API contract); §5 (fixture count canonicalized to 8-fixture: 1 valid + 7 diagnostic, one per case A1/A2/A3/C/D/E/E2); §9.2 Test coverage paragraph (8-fixture); §10 intro + LOW (ii)+(iii) bullets (CLOSED in v4-B); §11 reference index (LD-NEW → LD-622 substitution + v4-B follow-up LD added); §12 (this row); §14 pre-execution checklist (3 LOW closed); §15 audit row 9 (preserved at "7 diagnostic-emitting fixtures"); Authoring metadata (3 LOW closed). NO functional spec changes — pure consistency / readability sweep. v4-A spec sha256 pre-edit `354e48b61fe28bfb38d879ec8eef0ff571c8077c9681e989c0a2ed754a4bfc2f`. v3 sha256 unchanged `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b`. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_B_LOW_CONSISTENCY_V1` filed alongside. Self-classification: STANDARD (consistency cleanup overlay; no new design decisions; no new gates; no functional changes).** |
| **v4-C** | **2026-05-09** | **Cursor round-3 cleanup — closes 4 findings (1 HIGH + 2 MEDIUM + 1 LOW) that v4-B partially landed or missed. HIGH `operating-mode-vs-LD-actions`: §0 governance-authoring framing rewrite (replaces "DESIGN ONLY ... no LDs except" with explicit governance-authoring carve-out enumerating LD-622 + LD-628 + LD-636); §11 LD-NEW-v4-B placeholder substituted with `LD-628`; §11 + §0 v4-C self-reference resolved to `LD-636`. MEDIUM-1 `fixture-count-still-inconsistent`: §6 line 121 "7-fixture test instead of 5" updated to "8-fixture test (was 5 in v3; 7 in v4-A interim; canonicalized to 8 in v4-B)". MEDIUM-2 `case-count-mathematically-contradictory`: §9.2 header (line 163) + §9.2 reference impl docstring (line 213) + §15 audit row 9 (line 380) updated from "8 cases" to "9 cases (7 diagnostic + 2 non-diagnostic [A truly_absent + B success])"; v4-C respectfully diverges from handoff prompt's "8 diagnostic + 1 normal-path" recommendation (spec §9.2 line 179 designates Case A as non-diagnostic + Case B success as no-log per line 167+171, yielding 7+2 not 8+1). LOW `unverified-metadata-overstated`: line 404 "v4 has no unverified claims" tightened to "v4 has no `(unverified)` tags except where explicitly cited as `(handoff claim — not re-probed in v4 authoring)`". NO functional spec changes — pure consistency + governance-framing sweep. v4-B spec sha256 pre-edit `567d87b13a8fa05a38bfeabd8e62d7a897d09b51bb63a3aa0c1183ce67b67ce3`. v3 sha256 unchanged `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b`. Companion LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_C_ROUND_3_FIXES_V1` filed alongside. Self-classification: STANDARD (consistency cleanup overlay; no new design decisions; no new gates; no functional changes).** |
| **v4-D** | **2026-05-09** | **Cursor round-5 cleanup — VERIFICATION-PHASE FINDING: 5 of 6 prompt-recommended fixes already landed by v4-C (HIGH line-5 banner / MEDIUM-1 §12 v4 row 9-case / MEDIUM-2 §3.10 grep-anchored / MEDIUM-3 [CONFIRMED] footer DS-29 / LOW-1 §11 repo-relative). Cursor round-5 prompt referenced an older sha256 (`320ad2aa75b33a1ce758837c2274f4964246151af0353a5c08ca2ea952ba548a`); v4-D session start observed actual sha256 `bf899c880489de700f1ae4dce5118e4213cdd8e8eb5d9a9cd84a6f0ff8f736ef`. Only LOW-2 (`truly_absent` operator FAQ) survived as actionable: added explicit operator note at §3.9 immediately after the Normative vocabulary rule bullet list documenting that `truly_absent` is the only vocab token never written to log/actrow/exception (Case A produces no diagnostic), exists for telemetry-consumer disambiguation between "no event expected" and "event missing — investigate", and grep returns zero matches by design. Per-finding pre-edit `(my probe)` verification documented in §0.1 v4-D row. DISAGREEMENT NOTE on Cursor round-5 prompt's claim that line-5 banner "keeps surviving multi-section sweeps" — current line 5 already says GOVERNANCE-AUTHORING (functionally equivalent to prompt's recommended replacement); v4-D respectfully diverges from the literal-replacement mandate to avoid near-duplicate text. v4-C spec sha256 pre-edit `bf899c880489de700f1ae4dce5118e4213cdd8e8eb5d9a9cd84a6f0ff8f736ef`. v3 sha256 unchanged `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b`. Companion LD-644 (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_D_ROUND_5_FIXES_V1`) filed alongside. Self-classification: STANDARD (1-bullet FAQ addition + drift documentation; no functional spec changes; no new design decisions; no new gates).** |

---

## §13 — Cross-references (preserved verbatim from v3)

See v3 §13. v4 inherits unchanged.

---

## §14 — Pre-execution checklist (v4 extends v3's checklist with two rows)

The checklist below preserves v3 rows verbatim by reference and appends two rows for the v4 spec-LD + activity-log row + drift-detection on v3 baseline.

- [ ] (All v3 §14 rows preserved verbatim — see v3 spec.)
- [ ] **LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_OS_ERROR_TOCTOU_VOCAB_FIX_V1` (LD-622) confirmed filed in v4-A session (Rule 35 read-back confirms persisted fields).**
- [ ] **LD `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_B_LOW_CONSISTENCY_V1` confirmed filed in v4-B session (Rule 35 read-back confirms persisted fields; severity SOFT, task_category governance, enforcement awareness_only, scope_domain infra).**
- [ ] **Activity-log row `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_AUTHORED_V1` confirmed filed in v4-A session + `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V4_B_CLEANUP_V1` confirmed filed in v4-B session (Rule 35 read-back confirms `task_description` NOT present per LD-597).**
- [ ] **v3 baseline sha256 `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b` recorded; drift detection confirms v3 untouched during v4 + v4-B authoring (`(my probe)` per v4-B final report).**
- [ ] **All 13 risks in §7 reviewed and mitigations approved (especially Risk #13 NEW v4 — vocab inconsistency; mitigation = §3.9 canonical vocab + uniform application across log/actrow/exception).**
- [ ] **3 LOW round-2 findings closed in v4-B per §0.1 v4-B row + §10 LOW (i)/(ii)/(iii) bullets + §3.10 NEW canonical exception API contract + §11 LD-622 substitution + §5/§9.2/§15 8-fixture canonical reconciliation.**

---

## §15 — Audit (preserved verbatim from v3; v4 appends one new line)

Preserves v3 §15 eight-row audit list verbatim. v4 appends:

9. **NEW v4** — Override-file Cases A2 + A3 + E2 + vocab-grep parity smoke test: Phase 1 unit test verifies all 9 cases (A/A1/A2/A3/B/C/D/E/E2 — 7 diagnostic + 2 non-diagnostic [A truly_absent + B success]) per v4 §9.2 normative path. Asserts NEW Case A2 (TOCTOU-vanish, simulated by mocking `Path.exists` to return False after a successful `lstat()`) emits a log line with `reason=toctou_vanished` + activity-log row with `case="A2"` + `details.reason="toctou_vanished"`; with env var `loud`, asserts `OverrideFileMalformedError(str(path), "toctou_vanished", None)` raised. Asserts NEW Case A3 (metadata-OSError, simulated by mocking `Path.lstat` to raise `PermissionError`) emits log with `reason=metadata_os_error` + actrow with `case="A3"` + `details.os_error=<str>` + `details.errno=<int>`; with env var `loud`, asserts `OverrideFileMalformedError(str(path), "metadata_os_error", e)` raised. Asserts Case E2 (non-permission OSError on read, simulated by mocking `Path.read_text` to raise `OSError(errno=EIO)`) emits log with `reason=io_error` + actrow with `case="E2"`. Vocab-grep parity assertion (NEW v4 per Risk #13): for each of the 7 diagnostic-emitting fixtures, asserts the log line `reason=`, the activity-log row `details.reason`, and the raised `OverrideFileMalformedError.kind` argument all use the SAME canonical token from §3.9 `OVERRIDE_FILE_REASON_VOCAB` — guarantees single-token grep recipes work end-to-end across log + database + exception telemetry surfaces.

---

## §16 — Reference index — external docs + APIs (preserved verbatim from v3)

See v3 §16. v4 inherits unchanged. v4 NOTE: `pathlib.Path.lstat` + `Path.is_symlink` + `Path.exists` + `Path.read_text` raise behaviors are referenced per the Python 3 stdlib documentation for the `pathlib` and `os` modules; `OSError` subclass hierarchy (PermissionError, FileNotFoundError, NotADirectoryError, etc.) per the `errno` module + Python exception hierarchy.

---

## Authoring metadata

- **Spec author:** Claude Opus 4.7 (1M context)
- **Authoring session date:** 2026-05-09 (v4; one calendar day after v3, two days after v1/v2)
- **Authoring branch:** claude/gallant-bouman-804b4f (worktree)
- **v3 baseline sha256:** `e267a44577a097a8e3fc8b4248da24dfeb58067c0d324f347c70770ff838652b` — confirmed unchanged at v4 authoring start `(my probe)`. Re-confirmed at v4 final report.
- **v3 baseline size:** 403 lines — confirmed `(my probe)`.
- **v2 baseline sha256:** `047b5efd1c55a2eaf374e12e94665b4f4877d0732aca2b21fea1c22ff0d91b4b` — confirmed unchanged through v3 authoring `(per v3 metadata)`; v4 self-bound list forbids modification.
- **v1 baseline sha256:** `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75` — confirmed unchanged through v2/v3/v4 authoring `(per v3 metadata + v4 self-bound list)`.
- **LD-613 live verification:** confirmed live 2026-05-09 `(my probe)`: id=613, decision_key=`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V3_CASE_E_SYMLINK_FIX_V1`, status=`active`, severity=`SOFT`, task_category=`governance`.
- **LD-604 live verification:** preserved from v3 metadata `(handoff claim)` — not re-probed in v4 authoring (out of scope; v4 amends v3, not LD-604).
- **Self-bound list compliance:** confirmed `(my probe)`; v4 modifies ONLY the new v4 file + v4 spec-LD POST + v4 activity-log POST. NO modifications to v1 spec, v2 spec, v3 spec, prior schema-migration specs (v1-v7), implementation handoff, schema-ref doc, weekly_preflight, settings.json, hook scripts, payload_validator.py (doesn't exist), Cursor review outputs, prior LD records (LD-599, LD-604, LD-613), prod_blockers.
- **Cursor v3 round-2 findings addressed:** HIGH `os_error_surface_on_lstat` (Case A3 NEW) + MEDIUM-1 `toctou_silent_branch` (Case A2 NEW promoted from silent) + MEDIUM-2 `reason_vocab_inconsistency` (§3.9 canonical vocab pinned).
- **Cursor v3 round-2 findings CLOSED in v4-B (LOW):** (i) `OverrideFileMalformedError` `path-vs-str(path)` constructor argument-type consistency — closed via §3.10 NEW canonical exception API contract; (ii) `LD-NEW` labeling readability §0 vs §11 — closed via §11 LD-622 substitution; (iii) §5/§9.2/§15 fixture count reconciliation — closed via 8-fixture canonical target (1 valid + 7 diagnostic) applied uniformly across §3.10 + §5 + §9.2 + §15.
- **DS-29 source tagging:** every claim in v4 is tagged either `(my probe)` for live verification (LD-613 verification, sha256 probes), `(handoff claim)` for Cursor v3 round-2 / round-3 findings text quoted verbatim from the handoff prompt, or `(handoff claim — not re-probed in v4 authoring)` for live-verification-state claims that are carried forward from prior version metadata without fresh probing in v4. v4-C precision tightening: v4 has no `(unverified)` tags except where explicitly cited as `(handoff claim — not re-probed in v4 authoring)` — the LD-604 verification carry-forward at the §Authoring-metadata bullet two rows above is the only such case.
- **DS-30 canonical client:** all live-Directus probes performed via `Production/lib/directus_admin_client.py` `_request()` method; no urllib direct calls in v4 authoring.
- **Wave A live-schema probe timestamp:** 2026-05-09 (this v4 session — LD-613 verified live `(my probe)`).
- **Wave A inventory file:** [DEFERRED — Phase 0 deliverable per v1 §5.1 Phase 0 unchanged through v2/v3/v4.]

[CONFIRMED — claims are anchored per §Authoring-metadata DS-29 tagging: `(my probe)` where live verification was performed in this session (e.g. LD-613, sha256 read-backs), `(handoff claim)` / `(handoff claim — not re-probed in v4 authoring)` where cited; not every sentence was re-probed against Directus. Confidence tags applied per zero-error-qa Rule 24 + DS-29.]
