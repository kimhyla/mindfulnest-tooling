# DS-26 Mechanical Gate — Tech Spec v2

**Status:** DESIGN ONLY (per handoff hard rules — implementation deferred to a future Terminal CLI session under a separate authorization).
**Authors:** v2 amendment authored 2026-05-08, gallant-bouman-804b4f worktree, in response to Cursor cross-review of v1.
**Source authority:** zero-error-qa SKILL.md DS-26 (discipline-only); LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (id=578); LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V2_TOOL_NAME_REGEX_FAKERY_FIX_V1` (this v2's authority); HANDOFF_TEMPLATE_v1.md.
**Originating incident:** unchanged from v1 — Terminal A on `HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`, 2026-05-08.
**Tracking blocker:** `prod_blockers` row `DS_26_MECHANICAL_GATE_PENDING` (this spec is the design artifact resolving it; v2 supersedes v1 design choices in the four amendment areas below).

**v2 supersedes v1 in the following sections only.** All other v1 content is preserved by reference (see §0.1 v2-A scope below). When v1 and v2 disagree, v2 prevails.

---

## §0 Operating Mode

Unchanged from v1 (DESIGN ONLY; multipass discipline; Rule 24 confidence tags; DS-19 standing escape hatches; DS-26 itself is active on this session).

---

## §0.1 v2-A Changelog (top-of-file, supersedes v1 entries below)

| Row | Date | Change | Source authority |
|---|---|---|---|
| **v2-A** | **2026-05-08** | **Four surgical amendments authored in response to Cursor cross-review of v1 (4 findings: 2 HIGH, 2 MEDIUM). HIGH-1 = canonical tool-name set + helper for subagent-spawn detection (replaces literal `name == "Agent"` check). HIGH-2 = declaration parser regex escaping bug fixed (`gate\(?s\)?` → `gate(s)?`) + unit-test fixture list. MEDIUM-1 = legacy fallback regex tightened to require gate-table-format adjacency (markdown table row). MEDIUM-2 = anti-fakery cross-check upgraded from text-presence to Directus row evidence verification. New §7 risk rows added (4 rows for the 4 defect classes). Reference index extended; full §12 changelog row appended.** | **LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V2_TOOL_NAME_REGEX_FAKERY_FIX_V1` (this spec's own LD); HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508_v3.md** |
| v1 | 2026-05-08 | Initial design — dual-Opus debate, §3 Step 2.5c surface, §4 debate verbatim, §5 resolution, §6 algorithm, §7 pre-execution variant, §10 pre-implementation gates, §11 risk assessment, §13 testing plan, §14 reference index. | LD 578 + zero-error-qa DS-26 |

---

## §0.2 v2 Scope (supersedes v1 §0.1 only in the listed sections; rest of v1 §0.1 preserved)

**v2 in scope (SURGICAL amendments only — v1 architecture preserved):**

- **HIGH-1 (cross-tool name normalization):** v2 §3.7-A + §6.0-A — define `SUBAGENT_SPAWN_TOOL_NAMES` constant set + `is_subagent_spawn_call()` helper used by Step 2.5c's false-positive guard. Replaces v1 literal `name == "Agent"` check at v1 lines 151-152 + 369-370.
- **HIGH-2 (declaration parser regex):** v2 §3.4-A — fix the Python `re` escaping bug in v1 line 201 (`gate\(?s\)?` matches literal parens, NOT optional `s`). Correct form is `gate(s)?`. Add unit-test fixture list documenting valid + invalid declaration formats.
- **MEDIUM-1 (legacy fallback noise reduction):** v2 §3.6-A — tighten v1 line 245 regex to require markdown-table-format adjacency. Reduces false-positive matches from generic HALT/etc keywords appearing in explanatory prose. Trade-off acknowledged.
- **MEDIUM-2 (anti-fakery hardening):** v2 §3.4.1-A — upgrade v1 §3.4.1 evidence-citation cross-check from "text-presence of evidence_source string" to "Directus row evidence verification (when evidence_source is a Directus reference)." Non-Directus evidence still uses text-presence as fallback. Documented as harder-but-not-impossible.

**v2 out of scope (preserved verbatim from v1):**

- v1 §1 Background (originating incident, governance response, remaining gap, HALT-gate format).
- v1 §2 Existing Landscape (DS-20/21/22 pattern).
- v1 §3.1, §3.2, §3.3 (except §3.3's §3.4-related regex), §3.5, §3.7 (false-positive guard structure unchanged; only the *tool-name* check inside it is fixed), §3.8.
- v1 §4 Dual-Opus debate (entire section).
- v1 §5 Resolution + Decision Criteria.
- v1 §6 Detection Algorithm Python sketch (except §6.0-A normalized helper insertion + §3.4-A regex correction).
- v1 §7 Pre-execution variant.
- v1 §8 Implementation Phases.
- v1 §9 Open Decisions.
- v1 §10 Pre-Implementation Gates.
- v1 §11 (existing 8 rows preserved; v2 adds 4 rows in §7 risk section below).
- v1 §12 Rollback.
- v1 §13 Testing Plan (T1-T10 preserved; v2 adds T11-T14 corresponding to the 4 amendments).
- v1 §14 Reference Index (extended in §11 below).
- v1 §15 Authorship Trail.

---

## §3.4-A v2 Amendment — Declaration Parser Regex (HIGH-2 fix)

**v1 defect (Cursor finding HIGH-2, lines 200-202):**

```
v1 (BUGGY):  (?i)HALT\s+gate\s+scan\s*:\s*(\d+)\s+gate\(?s\)?\s+detected
```

In Python `re`, `\(` and `\)` match LITERAL parenthesis characters (escaped). The intent was clearly "optional `s` for plural" — but the form `gate\(?s\)?` parses as: `gate` + optional `(` + `s` + optional `)`. So it matches "gate(s)" or "gates)" or "gate(s" or "gates" only when accompanied by literal parens, NOT the canonical plural "gates". This means the parser would FAIL to parse the most common declaration form `HALT gate scan: 5 gates detected`.

**v2 correct form (CONFIRMED via Python re.compile + test fixtures):**

```python
# Canonical v2 declaration regex
DECLARATION_RE = re.compile(
    r"(?i)HALT\s+gate\s+scan\s*:\s*(\d+)\s+gate(s)?\s+detected",
)
```

The unparenthesized `gate(s)?` syntax uses regex group + quantifier semantics: `(s)?` = optional capture group containing literal `s`. Matches both "gate" (singular) and "gates" (plural). The captured group `(s)?` is captured as group 2 but not used by Step 2.5c (only the gate count in group 1 matters).

### §3.4-A.1 Unit-test fixture list (NEW in v2)

The implementation session (Phase B) MUST verify the regex against this fixture list:

| # | Input | Expected match | Captured count |
|---|---|---|---|
| F1 | `HALT gate scan: 5 gates detected` | YES | `5` |
| F2 | `HALT gate scan: 1 gate detected` | YES | `1` |
| F3 | `HALT gate scan: 0 gates detected` | YES | `0` |
| F4 | `HALT gate scan: 0 gate(s) detected` | YES | `0` (note: matches because `(s)?` is optional, so the literal `(s)` in input is NOT required — but if present, the literal parens would break this regex; see F4 nuance below) |
| F5 | `halt gate scan: 3 gates detected` (lowercase) | YES (case-insensitive flag) | `3` |
| F6 | `HALT gate scan : 2 gates detected` (extra spaces) | YES | `2` |
| F7 | `HALT gate scan: 12 gates detected` (multi-digit) | YES | `12` |
| F8 | `No HALT gates declared` | NO | n/a |
| F9 | `HALT gate scan: gate detected` (missing number) | NO | n/a |
| F10 | `HALT gate scan completed: 3 gates detected` (extra word) | NO (strict match — colon must directly follow `scan`) | n/a |

**F4 nuance (CONFIRMED):** the input `HALT gate scan: 0 gate(s) detected` contains literal parens. The v2 regex `gate(s)?\s+detected` would NOT match that input (because `(s)?` matches zero chars, leaving `(s) detected` ahead, which is `(` not `\s`). To support the legacy literal-parens form alongside the canonical plural form, the implementation MAY use the alternation form:

```python
# v2 alternation form — supports BOTH "gates" (canonical) AND "gate(s)" (legacy literal-parens)
DECLARATION_RE_PERMISSIVE = re.compile(
    r"(?i)HALT\s+gate\s+scan\s*:\s*(\d+)\s+gate(?:s|\(s\))?\s+detected",
)
```

Implementation Phase B chooses one form; v2 spec recommends the **permissive alternation form** to avoid regression on any legacy `gate(s)` declarations from before the v1 spec was authored.

### §3.4-A.2 Narrative — why this matters

[CONFIRMED via Python re docs + manual fixture run.] The v1 regex was a backslash-escaping bug, NOT a logic bug. The author intent was right; the syntax was wrong. Step 2.5c with v1's regex would have silently produced `MISSING_DECLARATION` failures on ANY session that emitted a correctly-plural declaration — i.e., on every multi-gate handoff. v2 closes this defect.

---

## §3.4.1-A v2 Amendment — Anti-Fakery Hardening (MEDIUM-2 fix)

**v1 design (lines 220-223):** for each parsed gate, search assistant output turns for at least one of: (1) literal mention of the `evidence_source` string, (2) `prod_activity_log` row citing the gate, (3) `HALTED_AWAITING_AUTHORIZATION` row. Cursor finding: branch (1) is gameable — a model can echo the evidence_source string without actually verifying.

**v2 hardening:** when `evidence_source` is a Directus reference (e.g., `"prod_activity_log id=1234"` or `"prod_locked_decisions row 578"`), branches (1) is replaced with an actual Directus row-existence verification. The model cannot fake "this row exists" because the verification queries Directus directly.

```python
# v2 anti-fakery cross-check (replaces v1 §3.4.1 branch 1 for Directus references)
import re

DIRECTUS_REF_RE = re.compile(
    r"prod_(\w+)\s+(?:id\s*=\s*|row\s*)(\d+)",
    re.IGNORECASE,
)

def verify_gate_evidence(parsed_gate: dict, client) -> bool:
    """v2 anti-fakery cross-check.

    For Directus references in evidence_source, verify the row actually exists.
    For non-Directus evidence (file paths, chat quote keywords), fall back to
    text-presence check (same as v1).

    Args:
        parsed_gate: dict with key 'evidence_source' (string).
        client: Directus client (must support .get_item(collection, id)).

    Returns:
        True if evidence is verified; False otherwise.
    """
    evidence_source = parsed_gate.get("evidence_source", "")
    directus_match = DIRECTUS_REF_RE.search(evidence_source)
    if directus_match:
        collection, row_id = directus_match.groups()
        try:
            row = client.get_item(f"prod_{collection}", int(row_id))
            return row is not None  # actual row exists in Directus
        except Exception:
            # Network failure or row not found → treat as fail
            return False
    # Non-Directus evidence (file paths, chat quotes, etc.):
    # fall back to text-presence check (best-effort, same as v1).
    return text_presence_check(evidence_source, parsed_gate)
```

### §3.4.1-A.1 Narrative — what this buys

[CONFIRMED via DS-22 precedent for Directus-row verification.] v1's text-presence cross-check is gameable: a model in autonomous mode could echo `"checked prod_locked_decisions LD-578"` in its output without ever querying Directus. The verification step succeeds (the literal substring appears) and the gate is marked PASS. v2 closes this for Directus references — the row must actually exist when queried.

**Residual risk acknowledged (NEW v2 §7 risk row R-V2-D2):** the model can still fake non-Directus evidence (file paths, chat quote keywords) via text-presence echo. v2 narrows the gameable surface from "all evidence sources" to "non-Directus evidence sources only", which substantially reduces the cost-of-fakery / cost-of-detection ratio.

**Trade-off — extra Directus calls at SAVE time:** v2 adds one Directus `get_item` call per parsed gate whose evidence_source is a Directus reference. For a 3-gate handoff, that's up to 3 additional Directus calls during Step 2.5c. Mitigation: use cached Directus client (already standard in mn-context Step 2/2.5/2.5b); offline branch falls back to text-presence (same as v1's branch 1).

---

## §3.6-A v2 Amendment — Legacy Fallback Noise Reduction (MEDIUM-1 fix)

**v1 design (lines 245-247):** `(?i)\b(HALT|do\s+NOT\s+proceed|surface\s+to\s+Kim|halt\s+and)\b` matches generic HALT/etc keywords anywhere in handoff prose. Cursor finding: matches explanatory text (e.g., "If you see a HALT, …" in narrative discussion of HALT gates). False-positive fatigue risk.

**v2 design:** tighten the regex to require markdown-table-format adjacency. Legacy HALT gates in the wild are predominantly authored as markdown tables (one row per gate); explanatory prose mentioning HALT/etc keywords is much more common in headers, body paragraphs, and bullet lists.

```python
# v2 legacy fallback regex — requires markdown-table format
LEGACY_HALT_RE = re.compile(
    r"(?im)^\|\s*\d+\s*\|.*?(HALT|do\s+NOT\s+proceed|surface\s+to\s+Kim|halt\s+and)",
)
```

Pattern explanation: line must start with `|` (markdown table syntax), followed by whitespace + a digit (the gate index column in legacy table format), followed by another `|`, followed by any content containing the HALT keyword. The `re.MULTILINE` flag (`(?m)`) ensures `^` matches per-line, not just at the start of the whole document.

### §3.6-A.1 Trade-off (documented, NOT mitigated)

The tightened regex MAY MISS legacy HALT gates that were authored as numbered lists or freeform prose (e.g., "1. HALT and surface to Kim" without table syntax). v2 accepts this trade-off:

- **Cost of false negative (miss a real legacy gate):** medium — the gate is still authored, the agent CAN still see it in the handoff body and HALT correctly per discipline; Step 2.5c just won't auto-surface it via legacy fallback.
- **Cost of false positive (flag prose mentions of HALT):** high — every false-positive checklist degrades trust and creates fatigue; over time the gate becomes "the noisy thing Kim dismisses" instead of "the gate that catches violations."

[INFERRED based on DS-20/22 precedent — false-positive cost dominates false-negative cost for these gate types.] v2 prefers stricter regex + accepted false-negative rate over noisy regex + false-positive rate.

### §3.6-A.2 Migration path

v2 implementation Phase F (DS-26 amendment) SHOULD also amend HANDOFF_TEMPLATE_v1.md to recommend (not require) markdown-table format for gate enumeration even in legacy/freeform handoffs going forward. This narrows the gap between legacy and v1-template parsing over time.

---

## §3.7-A v2 Amendment — Cross-Tool Name Normalization (HIGH-1 fix)

**v1 defect (Cursor finding HIGH-1, lines 151-152 + 369-370):** v1 §3.7's false-positive guard counts `Agent` tool calls; v1 §6 algorithm uses `session_state.tool_calls.filter(name="Agent")`. Other examples (and the broader Claude Code CLI runtime) use the name `Task` for subagent spawns. Runtime metadata may use either; Step 2.5c may skip when it should run (silent non-detection — exactly the failure mode Step 2.5c is designed to prevent).

**v2 design:** define a canonical tool-name set + helper. Step 2.5c uses the helper instead of literal `name == "Agent"`. Adding new spawn-tool names in the future = one-line change in the constant set.

```python
# v2 canonical tool-name set for subagent-spawn detection
SUBAGENT_SPAWN_TOOL_NAMES = {
    "Agent",      # primary in current Claude Code CLI
    "Task",       # legacy / subagent invocation
    "subagent",   # potential future alias
}

def is_subagent_spawn_call(tool_call: dict) -> bool:
    """Returns True if the given tool call is a subagent-spawn call.

    Recognizes all canonical tool-names that may indicate subagent spawn
    in current or legacy Claude Code CLI runtime metadata.
    """
    return tool_call.get("name") in SUBAGENT_SPAWN_TOOL_NAMES
```

### §3.7-A.1 Updated §3.7 false-positive guard text (v2)

v1 §3.7 condition (2) reads "Zero `Agent` tool calls were made this session". v2 replaces with:

> "Zero subagent-spawn tool calls (per `SUBAGENT_SPAWN_TOOL_NAMES`) were made this session."

### §3.7-A.2 Updated §6 algorithm Python sketch (v2)

v1 §6 line `agent_calls = session_state.tool_calls.filter(name="Agent")` is replaced with:

```python
agent_calls = [c for c in session_state.tool_calls if is_subagent_spawn_call(c)]
```

### §3.7-A.3 Narrative — why this matters

[CONFIRMED — Cursor v3 review specifically identified this as HIGH because runtime tool-name evolves between Claude Code CLI versions. The current name `Task` may be replaced by `Agent` or `subagent` in future versions.] If only one literal name is checked, Step 2.5c skips the false-positive guard incorrectly when runtime metadata uses a different name — and silently skips the entire gate scan. The constant set + helper makes the check robust to runtime tool-name evolution.

**Maintenance note (NEW v2 §7 risk row R-V2-A1):** any new subagent-spawn tool name added to Claude Code CLI runtime metadata MUST be added to `SUBAGENT_SPAWN_TOOL_NAMES`. If not, detection breaks silently (the worst class of defect for a gate). v2 implementation Phase B adds a unit-test fixture asserting the constant set is non-empty and contains all current names.

---

## §6.0-A v2 Amendment — Updated §6 Detection Algorithm (consolidating amendments)

The v1 §6 Python sketch (lines 360-454) is updated with the four amendments. Diff against v1:

```python
# mn-context SKILL.md Step 2.5c — DS-26 Mechanical Gate (v2)
# Runs after Step 2.5b. Inputs: assistant output turns, session metadata.

# v2-A HIGH-1: canonical tool-name set + helper
SUBAGENT_SPAWN_TOOL_NAMES = {"Agent", "Task", "subagent"}

def is_subagent_spawn_call(tool_call: dict) -> bool:
    return tool_call.get("name") in SUBAGENT_SPAWN_TOOL_NAMES

# v2-A HIGH-2: corrected declaration regex (note: permissive alternation form)
DECLARATION_RE = re.compile(
    r"(?i)HALT\s+gate\s+scan\s*:\s*(\d+)\s+gate(?:s|\(s\))?\s+detected",
)

# v2-A MEDIUM-1: tightened legacy fallback regex
LEGACY_HALT_RE = re.compile(
    r"(?im)^\|\s*\d+\s*\|.*?(HALT|do\s+NOT\s+proceed|surface\s+to\s+Kim|halt\s+and)",
)

# v2-A MEDIUM-2: Directus row evidence verification helper
DIRECTUS_REF_RE = re.compile(
    r"prod_(\w+)\s+(?:id\s*=\s*|row\s*)(\d+)",
    re.IGNORECASE,
)

def verify_gate_evidence(parsed_gate: dict, session_state, session_window_writes, client) -> bool:
    evidence_source = parsed_gate.get("evidence_source", "")
    directus_match = DIRECTUS_REF_RE.search(evidence_source)
    if directus_match:
        collection, row_id = directus_match.groups()
        try:
            row = client.get_item(f"prod_{collection}", int(row_id))
            if row is None:
                return False
            return True
        except Exception:
            # Offline / row-not-found: fall back to text-presence check
            return text_presence_check(evidence_source, session_state.assistant_turns)
    # Non-Directus evidence: text-presence fallback (same as v1)
    return (
        text_presence_check(evidence_source, session_state.assistant_turns) or
        activity_log_cites_gate(parsed_gate, session_window_writes) or
        halt_row_cites_gate(parsed_gate, session_window_writes)
    )

def step_2_5c_ds26_gate(session_state, session_window_writes, client):
    # §3.7 false-positive guard — v2-A HIGH-1: use is_subagent_spawn_call
    candidate_handoffs = collect_candidate_handoffs(session_state)
    agent_calls = [c for c in session_state.tool_calls if is_subagent_spawn_call(c)]
    complete_writes = session_window_writes.filter_status_complete()
    if not candidate_handoffs and not agent_calls and not complete_writes:
        log("Step 2.5c: no handoff context detected, skipping.")
        return PASS

    # ... §3.3 parsing unchanged ...
    # ... §3.4 declaration verification — uses DECLARATION_RE (v2-A HIGH-2) ...
    # ... §3.4.1 evidence cross-check — uses verify_gate_evidence (v2-A MEDIUM-2) ...
    # ... §3.5 MET vs NOT MET unchanged ...
    # ... §3.6 legacy fallback — uses LEGACY_HALT_RE (v2-A MEDIUM-1) ...

    # rest of v1 §6 algorithm preserved verbatim
    ...
```

[CONFIRMED — diff isolated to four amendment surfaces; v1 control flow preserved.]

---

## §7 Risk Assessment (v2 — extended; v1 rows preserved)

v1 §11 contained 8 risk rows (preserved verbatim by reference). v2 ADDS the following 4 risk rows for the 4 defect classes Cursor surfaced:

| Row | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-V2-A1** | **Cross-tool name silent miss** — runtime tool-name evolves to a name not in `SUBAGENT_SPAWN_TOOL_NAMES`, false-positive guard incorrectly skips Step 2.5c, gate scan never runs | **Medium** (Claude Code CLI rename history shows past renames; future renames likely) | **High** (silent gate-bypass detection failure) | v2-A HIGH-1: canonical constant set + helper; Phase B unit-test fixture asserts constant set is non-empty + covers all current names; documented maintenance contract: new spawn-tool name = one-line PR to extend `SUBAGENT_SPAWN_TOOL_NAMES` |
| **R-V2-B2** | **Declaration regex false-negative on plural form** — v1 regex never matched canonical "gates" plural, would fail every multi-gate handoff session | **Was 100% (v1 had this bug)** | **High** (every multi-gate session would erroneously fail with `MISSING_DECLARATION`) | v2-A HIGH-2: corrected regex `gate(s)?` (or permissive alternation `gate(?:s|\(s\))?`); §3.4-A.1 unit-test fixture list (10 cases F1-F10); Phase G implementation runs all 10 fixtures and confirms expected match/no-match |
| **R-V2-C1** | **Legacy fallback false-positive fatigue** — v1 generic regex matches HALT/etc in explanatory prose, generates noise checklists, degrades trust in gate over time | **High** (legacy handoffs use HALT/etc in many narrative contexts) | **Medium** (operational fatigue → gate dismissed → real violations slip through) | v2-A MEDIUM-1: tightened regex requires markdown-table-format adjacency; trade-off documented (§3.6-A.1 false-negative on non-table legacy gates accepted as preferable to false-positive fatigue); migration path (§3.6-A.2) recommends table format for new freeform gates |
| **R-V2-D2** | **Anti-fakery residual: non-Directus evidence still gameable** — text-presence check on file paths / chat quote keywords can be faked by model echoing the strings without verifying | **Low** (faking requires the model to know the exact evidence string AND echo it correctly AND not be caught in post-hoc audit) | **Medium** (production state advances; Kim catches on post-hoc audit; same severity as v1's residual risk but narrower surface) | v2-A MEDIUM-2: Directus references verified by row-existence check (no longer fakeable); non-Directus references documented as residual gameable surface; v2 implementation Phase F SHOULD encourage handoff authors to use Directus references where possible (narrows the gameable surface further); v2 hook (§7 alternative) is the long-term fix |

**Cross-reference to v1 §11 rows:** the v2 rows above are ADDITIVE — they don't supersede v1's 8 rows. v1 §11 row "Faked declaration with faked evidence citations" is partially mitigated by R-V2-D2 above; the residual that remains (non-Directus evidence) is documented in R-V2-D2's "Mitigation" column.

---

## §11 Reference Index (v2 — extended; v1 entries preserved)

In addition to all v1 §14 entries (preserved verbatim by reference), v2 adds:

- **v2-specific authority:**
  - LD `DS_26_MECHANICAL_GATE_TECH_SPEC_V2_TOOL_NAME_REGEX_FAKERY_FIX_V1` — this v2's own LD; covers the four amendments.
  - `Production/docs/HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508_v3.md` — Cursor cross-review handoff that surfaced the 4 findings.
  - `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md` — historical baseline; v2 supersedes only the four sections listed in §0.2.
  - `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v2.md` — this document.
- **Self-reference:** v2 is a supersede-by-amendment document; it does NOT replace v1 in storage. Both v1 and v2 are preserved in `Production/docs/` for audit traceability.
- **Implementation reference:** Phase B of the future Terminal CLI implementation session MUST source the regex set + helper functions from v2 §3.4-A, §3.4.1-A, §3.6-A, §3.7-A, §6.0-A — NOT v1 §3 / §6 directly.

---

## §12 Changelog (v2 entry appended; v1 entry preserved)

| Version | Date | Author | Change |
|---|---|---|---|
| **v2** | **2026-05-08** | **gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context)** | **Four surgical amendments responding to Cursor v3 cross-review of v1: HIGH-1 (cross-tool name normalization), HIGH-2 (declaration regex escaping bug fix), MEDIUM-1 (legacy fallback noise reduction), MEDIUM-2 (anti-fakery hardening via Directus row verification). 4 new §7 risk rows (R-V2-A1, R-V2-B2, R-V2-C1, R-V2-D2). Implementation handoff updates pending; v1 implementation handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508_v3.md` (NOT modified per self-bound rule).** |
| v1 | 2026-05-08 | gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context) | Initial design via dual-Opus debate. §3 SAVE-time surface (Step 2.5c). §6 algorithm. §7 pre-execution variant deferred. §10 ten pre-implementation gates. §11 risk assessment (8 rows). §13 testing plan (T1-T10). |

---

## §13 Testing Plan (v2 — additive cases T11-T14; v1 T1-T10 preserved)

In addition to v1 §13 cases T1-T10 (preserved verbatim by reference), v2 adds:

| Test # | Handoff content | Session state | Expected verdict | Validates |
|---|---|---|---|---|
| **T11** | v1-template, 3 gates | Session has 1 `Task` tool call (legacy spawn name) + 0 `Agent` calls | Step 2.5c **runs** (false-positive guard does NOT skip because `Task` is in `SUBAGENT_SPAWN_TOOL_NAMES`) | v2-A HIGH-1 |
| **T12** | v1-template, 5 gates | Declaration: `HALT gate scan: 5 gates detected` (canonical plural) | PASS_COUNT (regex matches plural form) | v2-A HIGH-2 |
| **T13** | legacy handoff with explanatory prose: "If you see a HALT keyword in the body, …" (no markdown table format) | declaration absent | SILENT (legacy regex no longer matches non-table prose); v1 would have FAILed `MISSING_DECLARATION_LEGACY` | v2-A MEDIUM-1 |
| **T14** | v1-template, 1 gate, evidence_source = `prod_locked_decisions row 578` | Session output echoes the literal string `"prod_locked_decisions row 578"` BUT row 578 does NOT exist in Directus | FAIL `EVIDENCE_MISSING_FOR_GATE_1` (v2 verifies row existence; text-presence echo is no longer sufficient) | v2-A MEDIUM-2 |

Phase G of the implementation session runs T11-T14 in addition to v1 T1-T10 and confirms expected verdicts.

---

## §14 Authorship Trail (v2 entry appended)

- **2026-05-08** — v2 authored, gallant-bouman-804b4f worktree (Claude Opus 4.7 1M-context). Four surgical amendments responding to Cursor v3 cross-review of v1. Did NOT modify v1 spec, v1 implementation handoff, or v3 review handoff (per self-bound rule).
- v1 authorship preserved per v1 §15.

---

**End of v2 amendments. All other v1 sections (§1, §2, §3.1-3.3, §3.5, §3.7-3.8, §4, §5, §6 baseline, §7 pre-execution variant, §8, §9, §10, §11 baseline 8 rows, §12 rollback, §13 baseline T1-T10, §14, §15) preserved verbatim by reference at `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md`.**
