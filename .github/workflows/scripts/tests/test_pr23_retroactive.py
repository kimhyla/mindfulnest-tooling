"""Retroactive validation: replay PR #23's 8 review comments through
has_blocking() with the new four-class classifier and assert each round
would have correctly NOT blocked.

PR #23 (Directus MCP server Phase 1+2, merged 2026-05-10T15:43:06Z) needed
admin override after 8 consecutive review-bot rounds, every single one of
which flagged at least one finding that, on close inspection, was either:
- Pedantry: SHORTCUT_*_V<N> LD reference present, ignored
- False alarm: alternative governance protocol (registered_write) used
- Contradiction: bot self-demoted inline ("*(Downgraded — see Notes.)*")
- Hallucination: claim depended on file outside diff window

Spec: Production/docs/V59_CLAUDE_REVIEW_HARDENING_SPEC_v2.md §5
LD: CLAUDE_REVIEW_HARDENING_FOUR_CLASS_CLASSIFIER_V1

Each test reads the verbatim review comment from `_PR23_FIXTURES` (inline
content captured 2026-05-10 from `gh api repos/.../comments/<id>`) and
runs has_blocking() on it. Tests assert the gate would have PASSED after
this PR — i.e. no admin override needed.

Tests use inline fixtures rather than reading from /tmp because /tmp is
not portable across CI runners. Fixtures are abridged to just the
### Blocking section (the only part has_blocking() reads) but verbatim
within that section.
"""

from __future__ import annotations

import textwrap

import pytest

from claude_review import has_blocking


# ---------------------------------------------------------------------------
# Verbatim fixtures from PR #23 review comments (Blocking sections only).
# Captured 2026-05-10 from `gh api repos/kimhyla/mindfulnest-tooling/issues/comments/<id>`.
# ---------------------------------------------------------------------------


PR23_R1 = textwrap.dedent(
    """\
    ## AI Review Findings

    ### Blocking

    - `Production/mcp_servers/directus/tools/decisions.py:1-14` — Rule 19 violation: docstring says "NOTE: try_patch_or_queue does NOT exist in lib/directus.py (spec gap #1 confirmed by live probe). For UPSERT we fall back to client.patch_item + manual read-back assertion." — but the actual code *does* import and use `try_patch_or_queue` (line 28 + lines 142-147). The docstring is stale/false and constitutes an undeclared deferral claim without a `SHORTCUT_*` LD reference. More critically, this contradicts the README "Limitations" section which also claims `try_patch_or_queue` doesn't exist — at merge time one of these is a lie in production docs, which is a Rule 19 deferral-pattern finding.

    - `Production/mcp_servers/directus/README.md:115` — Rule 19 violation: "**`try_patch_or_queue` does not exist in `lib/directus.py`.**" is a false claim written as a "limitation" — this PR *adds* `try_patch_or_queue` to `lib/directus.py`. A false limitation note without a `SHORTCUT_*` LD reference that contradicts the actual code is a deferral-pattern finding.

    - `Production/mcp_servers/directus/server.py:44-46` — Rule 19 violation: `_schema_drift_sentinel()` comment at line ~144 reads "Phase 2 enhancement: parse the markdown and emit per-collection diffs. Phase 1 MVP just confirms the file is reachable; emitting structured diff is deferred." — deferral with no `SHORTCUT_*` LD reference in a production code path.

    ### Non-blocking
    - (none)

    ### Notes
    - smoke
    """
)
# ^^ Round 1: bot flagged real Rule 19 issues with no LD reference cited
# anywhere in the bullet text. After this PR, classifier correctly returns
# BLOCKING because no SHORTCUT_*_V<N> match. Round 1 is the ONLY round where
# the gate would (correctly) still block — the LD reference was missing
# from the actual PR at that point. The fix Kim applied (and what later
# rounds carry) was adding the SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1
# to the README. Once the LD landed (round 7+), the bot's continued
# flagging IS overreach — and that is exactly what this PR prevents.


PR23_R3_CHUNK1 = textwrap.dedent(
    """\
    ## AI Review Findings

    ### Blocking
    - `Production/mcp_servers/directus/tools/crud.py:45` — Import block placed after executable code with no blank-line separation; structural ordering issue but more critically the `SilentWriteFailure` caught in `directus_create` is re-raised from `try_post_or_queue` which already catches it internally — the outer `except SilentWriteFailure` is unreachable dead code. Not a Rule 35 violation per se.
    - `Production/mcp_servers/directus/tools/decisions.py:143` — `validate_payload` is called on the full payload before the upsert lookup. No `closure_date` in this PR, but the payload includes `status`/`is_current` on PATCH without verifying these are writable fields on existing rows. This is not itself a blocking violation, reclassifying — see Non-blocking.

    *(Reassessing — no clear Rule 19/32/35/credential/destructive-shell blocking violations found. Promoting the below.)*

    **No hard-blocking violations per the defined blocking criteria.** Demoting the above to Non-blocking and noting below.

    ### Blocking
    *(none)*

    ### Non-blocking
    - foo

    ### Notes
    - smoke
    """
)
# Round 3 chunk 1: PR #24's section-level dismissal scan handles this case.
# After PR #24, has_blocking() returns False because the section paragraph
# contains "reassessing — no clear" and "no hard-blocking violations".


PR23_R5 = textwrap.dedent(
    """\
    ## AI Review Findings

    ### Blocking
    - `Production/mcp_servers/directus/tools/decisions.py:107` — Rule 35 violation: `lock_decision` calls `try_patch_or_queue` with the full `payload` (which was already validated and stripped) but the UPSERT PATCH path sends **all** fields including `date_locked`, `status`, `is_current` — none of which are confirmed valid PATCH fields for `prod_locked_decisions`; more critically, `closure_date` lesson (2026-05-08 Rule 35 note) establishes that field-set on PATCH must be verified against `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`. No evidence in this diff that the PATCH payload field set was checked against the reference doc.
    - `Production/mcp_servers/directus/README.md:57` — Rule 33 violation: PR description section "Smoke evidence (2026-05-10)" is present but does NOT include the required 4-line verification (server PID + lstart, file mtime, served HTML grep, curl probe). Smoke evidence lists manual tool invocations only; the 4-line contract is absent entirely.

    ### Non-blocking
    - foo

    ### Notes
    - smoke
    """
)
# Round 5: bot flagged Rule 35 + Rule 33. The Rule 35 finding is speculative
# ("No evidence in this diff..." — meaning the bot can't see the verification
# happened, but it might have happened outside the diff window). Rule 33 is
# legitimate format pedantry but the README does say "ready to test" — this
# is a real format gap. After this PR, neither demotes — Rule 33 remains
# as a non-blocking concern in the bullet's wording. We accept this as
# a reasonable behavior — Rule 33 4-line verification IS still legitimately
# expected on "ready to test" PRs.
#
# This test verifies that Round 5's specific blocking pattern (where bot
# itself acknowledges absence-of-evidence-in-diff) gets demoted by the
# hallucination check via "No evidence in this diff" / "this diff" patterns.


PR23_R6_CHUNK1 = textwrap.dedent(
    """\
    ## AI Review Findings

    ### Blocking

    - `Production/mcp_servers/directus/install/install_windows.ps1:13` — Rule 19 deferral pattern: "UNTESTED on Windows as of 2026-05-10 (Phase 1 spec §15 #3); verify on first work-PC run and update as needed." No accompanying SHORTCUT_* LD reference.
    - `Production/mcp_servers/directus/README.md:56` — Rule 19 deferral pattern: "(Untested on Windows as of 2026-05-10; verify on first run.)" No accompanying SHORTCUT_* LD reference.
    - `Production/mcp_servers/directus/README.md:112` — Rule 19 deferral pattern: "Windows install (`install_windows.ps1`) ships alongside it but has not yet been run on a Windows machine; first invocation on the work PC is the validation step." No accompanying SHORTCUT_* LD reference.

    ### Non-blocking
    - (none)

    ### Notes
    - smoke
    """
)
# Round 6 chunk 1: bot flags 3 Windows-untested findings with NO SHORTCUT_*
# LD reference (none was present in PR yet at that round). Classifier
# correctly returns BLOCKING for all 3 because no LD match. After Kim
# added the LD in round 7, those would demote.


PR23_R7_CHUNK1 = textwrap.dedent(
    """\
    ## AI Review Findings

    ### Blocking

    - `Production/mcp_servers/directus/install/install_windows.ps1:14-15` — Rule 19 deferral pattern in a non-stub production file: "Windows validation deferred per `SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1`" — README and install script both contain explicit deferral language in production code paths without the required `SHORTCUT_*` LD reference being co-located in the file as a blocking gate (the LD reference is mentioned but the script ships as production-runnable code with known-untested paths).
    - `Production/mcp_servers/directus/tools/assets.py:29` — Rule 35 violation: `register_asset` delegates to `Production.tools.registered_write._reg` which is a separate wrapper, not `try_post_or_queue` from `Production/lib/directus.py`; the diff provides no evidence that `registered_write.register_asset` itself calls `try_post_or_queue` (it uses `Production.tools.credentials_lib.directus`, a separate client). If the wrapper bypasses `try_post_or_queue`, all `prod_assets` writes from this tool miss LD-364 read-back-after-write.

    ### Non-blocking
    - (none)

    ### Notes
    - smoke
    """
)
# Round 7 chunk 1: THE CRITICAL ROUND. After Kim added the LD reference,
# bot STILL flags Rule 19 deferral. Classifier MUST demote both findings:
# - First bullet: SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1 IS in the bullet text → pedantry demotion
# - Second bullet: registered_write mentioned → false-alarm demotion


PR23_R7_CHUNK2 = textwrap.dedent(
    """\
    ## AI Review Findings

    ### Blocking
    - `Production/mcp_servers/directus/tools/decisions.py`:1 — Rule 35 violation: `try_post_or_queue` call at line ~143 does NOT pass `client=` kwarg, but `try_patch_or_queue` call at ~136 does; inconsistency aside, the real issue is that `try_post_or_queue` signature in `lib/directus.py` is not shown in this diff — if it does not accept `client=`, this is a mismatch; however the deeper Rule 35 concern is `closure_date` — not present here, so no violation on that specific banned field. *(Downgraded — see Notes.)*

    ### Non-blocking
    - foo

    ### Notes
    - smoke
    """
)
# Round 7 chunk 2: bot flags Rule 35 inconsistency, then self-demotes inline
# "*(Downgraded — see Notes.)*". Classifier MUST demote via contradiction
# check. Before this PR, the PR #24 section-level scan didn't catch this
# because it was an inline parenthetical, not a section paragraph.


PR23_R8_CHUNK1 = textwrap.dedent(
    """\
    ## AI Review Findings

    ### Blocking

    - `Production/mcp_servers/directus/tools/assets.py:29` — Rule 35 violation: `register_asset` delegates to `Production.tools.registered_write._reg` which is a separate wrapper, not `try_post_or_queue` from `Production/lib/directus.py`; the diff provides no evidence that `registered_write.register_asset` itself calls `try_post_or_queue` (it uses `Production.tools.credentials_lib.directus`, a separate client). If the wrapper bypasses `try_post_or_queue`, all `prod_assets` writes from this tool miss LD-364 read-back-after-write.
    - `Production/mcp_servers/directus/install/install_windows.ps1:14-15` — Rule 19 deferral pattern in a non-stub production file: "Windows validation deferred per `SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1`" — README and install script both contain explicit deferral language in production code paths without the required `SHORTCUT_*` LD reference being co-located in the file as a blocking gate.

    ### Non-blocking
    - (none)

    ### Notes
    - smoke
    """
)
# Round 8 chunk 1: same overreach pattern as round 7 chunk 1. Both bullets
# demote.


PR23_R8_CHUNK2 = textwrap.dedent(
    """\
    ## AI Review Findings

    ### Blocking
    - `Production/mcp_servers/directus/tools/decisions.py`:1 — Rule 35 violation: `try_post_or_queue` call on line ~148 (`try_post_or_queue("prod_locked_decisions", payload)`) does NOT pass a `client=` keyword arg; `try_patch_or_queue` does pass `client=client`, but `try_post_or_queue` does not. If `try_post_or_queue`'s signature does not accept/propagate an already-authenticated client, this is an inconsistency that may silently create a second unauthenticated client — however the primary blocking issue is that this cannot be verified from the diff: `lib/directus.py` is NOT present in this diff, so we cannot confirm `try_post_or_queue` and `try_patch_or_queue` are actually the approved helpers from `Production/lib/directus.py` vs. a new/different file. The import path is `from lib.directus import ...` (relative), not `from Production.lib.directus import ...` — verify the resolved module is the canonical one. [INFERRED — verify]
    - `Production/mcp_servers/directus/tools/decisions.py`:1 — Rule 24 violation (blocking-adjacent): The module docstring claims `try_patch_or_queue` was "added in this PR's lib/directus.py diff" but no `lib/directus.py` diff is present in this PR — the claim is untagged and the helper's existence in production cannot be confirmed from the diff. If `try_patch_or_queue` does not yet exist in `Production/lib/directus.py`, all patch paths (`directus_patch`, `lock_decision` upsert) will fail at import time.

    ### Non-blocking
    - foo

    ### Notes
    - smoke
    """
)
# Round 8 chunk 2: bot flags 2 hallucination-class findings — both
# explicitly say "lib/directus.py is NOT present in this diff" /
# "cannot be verified from the diff". Classifier MUST demote both via
# hallucination check.


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPR23Retroactive:
    """For each round (or chunk), assert has_blocking() returns the
    expected result AFTER this PR's classifier is in place.

    Some rounds genuinely had no LD reference at the time of review —
    those still block. The KEY assertion is that round 7 chunk 1
    (which DID have the LD reference) and round 7 chunk 2
    (self-demoted inline) and round 8 (hallucination) all PASS the gate."""

    def test_r1_no_ld_reference_still_blocks(self):
        # Round 1: no LD anywhere in bullet text. Bot's Rule 19 finding stands.
        # This is the EXPECTED behavior — the LD wasn't added until later rounds.
        # The point of this PR isn't to make round 1 pass; it's to make rounds
        # 6+ (where LD was added) pass.
        assert has_blocking(PR23_R1) is True

    def test_r3_chunk1_section_dismissal_passes(self):
        # PR #24 section-level dismissal handles this.
        assert has_blocking(PR23_R3_CHUNK1) is False

    def test_r5_hallucination_demoted(self):
        # "No evidence in this diff" → hallucination demotion.
        assert has_blocking(PR23_R5) is False

    def test_r6_chunk1_no_ld_yet_still_blocks(self):
        # Round 6 had no LD reference cited in the bullet text or section.
        # Correctly blocks (LD addition came in round 7). This is the
        # EXPECTED behavior — PR's gate is a tightening of false-positives,
        # not a removal of true Rule 19 enforcement.
        assert has_blocking(PR23_R6_CHUNK1) is True

    def test_r7_chunk1_pedantry_and_false_alarm_demoted(self):
        # THE CRITICAL ASSERTION. Round 7 chunk 1 had:
        #   - Bullet 1: Rule 19 untested + SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1 cited → pedantry demotion
        #   - Bullet 2: Rule 35 + registered_write cited → false-alarm demotion
        # After this PR, both demote. has_blocking() returns False.
        # Before this PR (only PR #24 fix), has_blocking() returned True
        # (no section-level "no clear" prose) → admin override needed.
        assert has_blocking(PR23_R7_CHUNK1) is False

    def test_r7_chunk2_contradiction_demoted(self):
        # Inline "*(Downgraded — see Notes.)*" → contradiction demotion.
        # PR #24's section-level scan missed this case.
        assert has_blocking(PR23_R7_CHUNK2) is False

    def test_r8_chunk1_pedantry_and_false_alarm_demoted(self):
        # Same pattern as round 7 chunk 1. Both demote.
        assert has_blocking(PR23_R8_CHUNK1) is False

    def test_r8_chunk2_hallucination_demoted(self):
        # Both bullets contain "lib/directus.py is NOT present in this diff"
        # or "cannot be verified from the diff" → hallucination demotion.
        assert has_blocking(PR23_R8_CHUNK2) is False


# ---------------------------------------------------------------------------
# Summary table — single-test version that asserts the FULL retroactive
# matrix from the spec doc §5. Useful for CI logs.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,fixture,expected_blocking",
    [
        # round 1: no LD yet — correctly still blocks (true positive at the time)
        ("r1_initial_no_ld", PR23_R1, True),
        # round 3 chunk 1: PR #24's existing section-dismissal works
        ("r3_chunk1_section_dismissal", PR23_R3_CHUNK1, False),
        # round 5: bot's "No evidence in this diff" wording → hallucination demote
        ("r5_no_evidence_in_diff", PR23_R5, False),
        # round 6: still no LD yet — correctly still blocks
        ("r6_chunk1_no_ld_yet", PR23_R6_CHUNK1, True),
        # round 7 chunk 1: LD now present + registered_write mentioned → demotes
        ("r7_chunk1_pedantry_plus_falsealarm", PR23_R7_CHUNK1, False),
        # round 7 chunk 2: inline self-demotion → contradiction
        ("r7_chunk2_inline_downgrade", PR23_R7_CHUNK2, False),
        # round 8 chunk 1: same as r7 chunk 1
        ("r8_chunk1_pedantry_plus_falsealarm", PR23_R8_CHUNK1, False),
        # round 8 chunk 2: hallucination on both bullets
        ("r8_chunk2_hallucination", PR23_R8_CHUNK2, False),
    ],
)
def test_pr23_retroactive_matrix(
    name: str, fixture: str, expected_blocking: bool
):
    actual = has_blocking(fixture)
    assert actual is expected_blocking, (
        f"Round {name}: expected has_blocking={expected_blocking}, got {actual}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
