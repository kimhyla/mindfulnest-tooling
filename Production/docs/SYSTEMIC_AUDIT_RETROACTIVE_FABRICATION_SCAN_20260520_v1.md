# Systemic Retroactive Fabrication + Error-Class Audit

**Marker:** `SYSTEMIC_AUDIT_MARKER_20260520_4D03F85A2BBF`
**Date:** 2026-05-20
**Authority:** Kim 2026-05-20 directive — "scan for this and EVERY OTHER CATEGORY OR TYPE of error that may still exist"
**Cost ceiling:** $0 vendor (cursor agents only; no Opus/Sonnet)
**Branch:** `fix/runtime-regression-bugs-20260519` (per DEVIATION-6058, all overnight work absorbs into PR #73)
**Parent commit:** `af163e0`

---

## §1 — Scope

Retroactive audit of EVERY active LD + reference doc + memory file + endpoint catalog + test catalog for the following error classes:

1. **LD-class fabrication** — locked decision claims a code/file/symbol that doesn't exist
2. **Ref-doc fabrication** — `prod_reference_docs.file_path` points at a missing file
3. **Endpoint catalog drift** — MUTATION_ENDPOINTS / READ_ENDPOINTS declared but no server handler (or vice versa)
4. **Test-file claims** — tests claimed in LDs that don't exist or pass vacuously (`create=True` mocks)
5. **CSS / data-testid marker drift** — UI features claimed shipped but markers absent from built dist
6. **Supersession-chain breaks** — LD A claims supersedes B but B's status not updated
7. **Activity log "_COMPLETE" rows** — claiming completion of work that has no on-disk artifact
8. **CLAUDE.md rule enforcement** — rules cite enforcement mechanisms (scripts/hooks/CI) that don't exist
9. **Blocker descriptions** — open blockers describing fixes that already shipped (false-positive open)
10. **Pre-push lint guard claims** — `Production/scripts/lint_*.py` cited in commits/LDs that don't exist on disk

## §2 — Method

**Phase 1**: build LD inventory. Query `prod_locked_decisions` status=active, all LDs (~600+ rows). Extract `related_files` + `enforcement_artifact_ref` + decision_text references.

**Phase 2**: categorize claims. For each LD, classify the verifiable claim type (file-exists / function-exists / endpoint / test / CSS-marker / etc).

**Phase 3**: mechanical audit. Write `Production/scripts/ld_fabrication_audit.py` that probes each claim against current HEAD + Dropbox runtime tree.

**Phase 4**: triage by remediation cost:
- **TRIVIAL** (<10 LOC fix or status PATCH): apply inline
- **MODERATE** (10-100 LOC, 1-2 files): apply inline OR dispatch cursor-agent
- **TECH_SPEC_NEEDED**: halt for Kim with explicit question

**Phase 5**: fix in dependency order (smaller, more-isolated fixes first).

**Phase 6**: per-fix multi-pass verification:
- pre-pass: re-grep the claim to confirm it's still broken
- apply fix
- post-pass 1: re-grep to confirm marker landed
- post-pass 2: py_compile / tsc / npm build / pytest as applicable
- post-pass 3: Directus state confirms LD PATCH landed (Rule 35 read-back)

**Phase 7**: final cursor-agent independent review.

**Phase 8**: commit + push + deploy + coordinator POST row.

## §3 — Coordinator + recovery

- **PRE row:** `COORDINATOR_RESUMPTION_PRE_SYSTEMIC_AUDIT_20260520` (about to be written)
- **POST row:** `COORDINATOR_RESUMPTION_POST_SYSTEMIC_AUDIT_20260520` (at end)
- **Deviation rows:** `DEVIATION_SYSTEMIC_AUDIT_<id>_V1` per scope-drift

A fresh session reading the latest `CROSS_SESSION_STATE_SUMMARY_*` row + this spec + git log + Directus query of `prod_activity_log` filtered to `_systemic_audit` actions can resume mid-build.

## §4 — Honest scope limits

- Vendor cost cap: $0 (no Opus, no Sonnet agents).
- Cursor agents allowed — but only for non-trivial multi-file refactor/investigation.
- This audit does NOT cover: app-side (RN) code, Firestore rules, Cloud Functions, ElevenLabs/Kling/OpenAI live-vendor probes.
- This audit DOES cover: every `Production/`-rooted artifact + every `prod_*` Directus collection.

## §5 — Exit criteria

Audit considered complete when:
1. Every active LD with a verifiable claim has been probed
2. Every fabrication found has been EITHER fixed OR superseded-with-correction-LD OR DEVIATION-logged-with-halt
3. Final cursor-agent review reports zero remaining blockers
4. PR #73 mergeStateStatus=CLEAN with all 7 CI checks green

## §6 — Companion docs

- LD-773: Forensic audit of LDs 734-772 (8 fabrications found 2026-05-17)
- LD-783: CLAIM_TO_COMMIT_ENFORCEMENT_GATE_V1 (fabrication-prevention infrastructure)
- LD-812: corrective for LD-787 fabricated re-ship claim
- Today's commit `af163e0`: 5 fabrication fixes (LD-733/722/766/741/787-via-812)
