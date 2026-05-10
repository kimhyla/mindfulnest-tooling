"""Tests for the four-class classifier added to claude_review.py.

Tests cover the four root-cause overreach classes from PR #23's 8-round
admin-override incident:

  1. NON_BLOCKING_PEDANTRY     — Rule 19 deferral with SHORTCUT_*_V<N> LD
  2. NON_BLOCKING_FALSE_ALARM  — Rule 35 with alternative governance protocol
  3. NON_BLOCKING_CONTRADICTION — bullet self-demotes inline
  4. NON_BLOCKING_HALLUCINATION — claim about file outside diff window

Plus negative tests asserting genuinely blocking findings still block, and
that PR #24's section-level dismissal continues to work.

LD: CLAUDE_REVIEW_HARDENING_FOUR_CLASS_CLASSIFIER_V1
Spec: Production/docs/V59_CLAUDE_REVIEW_HARDENING_SPEC_v2.md
"""

from __future__ import annotations

import textwrap

import pytest

from claude_review import (
    _classify_finding,
    _has_shortcut_ld_in_context,
    has_blocking,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap(bullet: str, *, extra_body: str = "") -> str:
    """Wrap a single bullet line into a full ### Blocking section so the
    gate-level has_blocking() can be exercised end-to-end."""
    return textwrap.dedent(
        f"""\
        ## AI Review Findings

        ### Blocking
        {bullet}
        {extra_body}

        ### Non-blocking
        - (none)

        ### Notes
        - smoke
        """
    )


# ---------------------------------------------------------------------------
# §3.2.1 — Pedantry
# ---------------------------------------------------------------------------


class TestPedantry:
    def test_rule_19_deferral_with_shortcut_ld_demoted(self):
        bullet = (
            "- `install_windows.ps1:14` — Rule 19 deferral pattern: "
            "`UNTESTED on Windows as of 2026-05-10` — but this is "
            "covered by `SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1`."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_PEDANTRY"
        assert has_blocking(_wrap(bullet)) is False

    def test_untested_phrase_with_shortcut_ld_in_section_context(self):
        # PR #23 round 6 verbatim pattern: bot lists 3 deferrals but cites
        # the LD only in the section's leading prose, not on each bullet.
        body = textwrap.dedent(
            """\
            ## AI Review Findings

            ### Blocking
            - `install_windows.ps1:13` — Rule 19 deferral: "UNTESTED on Windows"
            - `README.md:56` — Rule 19 deferral: "(Untested on Windows as of 2026-05-10)"
            - `README.md:112` — Rule 19 deferral: "Windows install ships but has not yet been run"

            ### Non-blocking
            - These three deferrals all trace to the same SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1 path.

            ### Notes
            - foo
            """
        )
        # Even though the LD is cited in Non-blocking section, body-wide scan picks it up.
        # has_blocking() runs the classifier scoped to the Blocking section body,
        # so the LD-in-Non-blocking case is intentionally NOT covered by this signal.
        # However if the bot writes the same LD inside the Blocking section's leading
        # paragraph (common pattern), that IS caught. Test that case:
        body_with_ld_in_section = textwrap.dedent(
            """\
            ## AI Review Findings

            ### Blocking

            All three of the following relate to SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1:

            - `install_windows.ps1:13` — Rule 19 deferral: "UNTESTED on Windows"
            - `README.md:56` — Rule 19 deferral: "Untested on Windows"

            ### Non-blocking
            - (none)

            ### Notes
            - foo
            """
        )
        assert has_blocking(body_with_ld_in_section) is False

    def test_rule_19_deferral_without_shortcut_ld_still_blocks(self):
        bullet = (
            "- `prod_code.py:42` — Rule 19 deferral pattern: "
            "`# TODO: implement later`. No SHORTCUT_ LD reference."
        )
        assert _classify_finding(bullet, bullet) == "BLOCKING"
        assert has_blocking(_wrap(bullet)) is True

    def test_pedantry_trigger_word_alone_without_ld_does_not_demote(self):
        # "untested" word present but no LD anywhere — must remain blocking.
        bullet = "- `prod.py:1` — Rule 19: untested code path with no governance reference."
        assert _classify_finding(bullet, bullet) == "BLOCKING"

    def test_fake_shortcut_without_v_suffix_does_not_demote(self):
        # SHORTCUT_FAKE — no _V<N> suffix; pedantry check correctly rejects.
        bullet = "- `prod.py:1` — Rule 19 deferral. SHORTCUT_FAKE applies."
        assert _classify_finding(bullet, bullet) == "BLOCKING"

    def test_mvp_pedantry_word_with_ld_demoted(self):
        bullet = (
            "- `README.md:1` — Rule 19: 'Phase 1 MVP' deferral pattern; "
            "SHORTCUT_MCP_PHASE1_MVP_SCOPE_V1 covers this."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_PEDANTRY"


# ---------------------------------------------------------------------------
# §3.2.2 — False alarm (alternative governance protocol)
# ---------------------------------------------------------------------------


class TestFalseAlarm:
    def test_rule_35_with_registered_write_demoted(self):
        bullet = (
            "- `tools/assets.py:29` — Rule 35 violation: `register_asset` delegates to "
            "`Production.tools.registered_write._reg` which is a separate wrapper, "
            "not `try_post_or_queue` from `Production/lib/directus.py`."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_FALSE_ALARM"
        assert has_blocking(_wrap(bullet)) is False

    def test_rule_35_with_ld_421_token_demoted(self):
        bullet = (
            "- `tools/assets.py:30` — Rule 35: `register_asset` does not call "
            "`try_post_or_queue` directly. Routes through LD-421 governance."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_FALSE_ALARM"

    def test_rule_35_with_real_urlopen_post_blocks(self):
        # Real Rule 35 violation — direct urllib POST without any alternative
        # governance protocol cited. Must remain blocking.
        bullet = (
            "- `prod_writer.py:42` — Rule 35 violation: "
            "`urllib.request.urlopen(req, ...)` POSTs directly to "
            "`/items/prod_locked_decisions` bypassing try_post_or_queue."
        )
        assert _classify_finding(bullet, bullet) == "BLOCKING"
        assert has_blocking(_wrap(bullet)) is True

    def test_try_post_or_queue_mention_alone_doesnt_demote(self):
        # If finding mentions try_post_or_queue but NOT an alternative protocol,
        # don't demote — could be a real concern.
        bullet = (
            "- `prod.py:1` — `try_post_or_queue` is missing the `client=` kwarg."
        )
        # No alternative governance token — bullet still blocking from this
        # check's perspective. (May be demoted by hallucination check if it
        # mentions diff window; here it doesn't.)
        assert _classify_finding(bullet, bullet) == "BLOCKING"


# ---------------------------------------------------------------------------
# §3.2.3 — Contradiction (bullet-level self-demotion)
# ---------------------------------------------------------------------------


class TestContradiction:
    def test_downgraded_inline_demotion(self):
        # PR #23 round 7 chunk 2 verbatim.
        bullet = (
            "- `tools/decisions.py:1` — Rule 35 violation: `try_post_or_queue` "
            "call does NOT pass `client=` kwarg. *(Downgraded — see Notes.)*"
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_CONTRADICTION"
        assert has_blocking(_wrap(bullet)) is False

    def test_reassessing_inline_demotion(self):
        bullet = (
            "- `prod.py:1` — Rule 19 deferral. *(Reassessing — no clear violation.)*"
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_CONTRADICTION"

    def test_reclassifying_inline_demotion(self):
        bullet = (
            "- `prod.py:1` — Rule 35 issue. (reclassifying — see non-blocking)"
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_CONTRADICTION"

    def test_bullet_without_self_demotion_still_blocks(self):
        bullet = "- `prod.py:1` — Rule 35 violation: direct urllib POST."
        assert _classify_finding(bullet, bullet) == "BLOCKING"


# ---------------------------------------------------------------------------
# §3.2.4 — Hallucination (diff-window blindness)
# ---------------------------------------------------------------------------


class TestHallucination:
    def test_not_present_in_diff_demoted(self):
        # PR #23 round 7 chunk 2 verbatim pattern.
        bullet = (
            "- `tools/decisions.py:1` — Rule 35: if `try_post_or_queue` does not "
            "accept `client=` kwarg this is a latent TypeError. lib/directus.py "
            "is NOT present in this diff."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_HALLUCINATION"
        assert has_blocking(_wrap(bullet)) is False

    def test_cannot_verify_from_diff_demoted(self):
        bullet = (
            "- `prod.py:1` — Rule 35 concern about helper signature. "
            "cannot verify from this diff."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_HALLUCINATION"

    def test_outside_diff_window_demoted(self):
        bullet = (
            "- `prod.py:1` — Helper function may not exist. "
            "outside the diff window."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_HALLUCINATION"

    def test_real_blocking_finding_with_full_diff_evidence(self):
        # Bot has full diff evidence and flags a real issue. Must block.
        bullet = (
            "- `prod.py:42` — Rule 35: `urlopen(req).read()` posts to "
            "/items/prod_locked_decisions directly. Confirmed against lib/directus.py "
            "diff at line 100 — try_post_or_queue is bypassed."
        )
        assert _classify_finding(bullet, bullet) == "BLOCKING"


# ---------------------------------------------------------------------------
# §3.2 — Order-of-checks: contradiction takes precedence
# ---------------------------------------------------------------------------


class TestOutOfSpecRule:
    """§3.2.5 — bullet cites a rule not in the prompt's blocking-eligible set
    (Rules 19, 32, 35 + credential/destructive/LD-deletion). Demote."""

    def test_rule_33_alone_demoted(self):
        bullet = (
            "- `README.md:57` — Rule 33 violation: PR description has "
            "'ready to test' but does NOT include the required 4-line "
            "verification block."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_OUT_OF_SPEC_RULE"

    def test_rule_24_alone_demoted(self):
        bullet = "- `prod.py:1` — Rule 24: untagged claim about cache TTL."
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_OUT_OF_SPEC_RULE"

    def test_rule_26_alone_demoted(self):
        bullet = "- `prod.py:1` — Rule 26: should have escalated to Opus."
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_OUT_OF_SPEC_RULE"

    def test_rule_19_alone_remains_blocking(self):
        bullet = "- `prod.py:1` — Rule 19 deferral: TODO without LD."
        assert _classify_finding(bullet, bullet) == "BLOCKING"

    def test_rule_35_alone_remains_blocking(self):
        bullet = "- `prod.py:1` — Rule 35: direct urlopen POST to /items/..."
        assert _classify_finding(bullet, bullet) == "BLOCKING"

    def test_combined_rule_19_and_24_remains_blocking(self):
        # Rule 19 is blocking-eligible; presence of Rule 24 alongside
        # doesn't demote — the Rule 19 concern stands.
        bullet = (
            "- `prod.py:1` — Rule 19 deferral pattern; also Rule 24 "
            "untagged claim. No SHORTCUT_."
        )
        assert _classify_finding(bullet, bullet) == "BLOCKING"

    def test_rule_24_with_credential_marker_remains_blocking(self):
        # Rule 24 cited but also contains "hardcoded credential" marker —
        # blocking via non-rule signal.
        bullet = (
            "- `prod.py:1` — Rule 24 untagged claim about a hardcoded credential "
            "`sk-proj-XXX` in source."
        )
        assert _classify_finding(bullet, bullet) == "BLOCKING"

    def test_no_rule_citation_no_demotion(self):
        # Bullet without any "Rule N" citation — falls through to BLOCKING
        # (out-of-spec check requires cited_rule_numbers to be non-empty).
        bullet = "- `prod.py:1` — generic concern about code quality."
        assert _classify_finding(bullet, bullet) == "BLOCKING"


class TestClassifierOrder:
    def test_contradiction_wins_over_pedantry(self):
        # Bullet matches both contradiction and pedantry signals; contradiction
        # check runs first → returns CONTRADICTION (not PEDANTRY).
        bullet = (
            "- `prod.py:1` — Rule 19 deferral with SHORTCUT_FOO_V1. "
            "*(Downgraded — see Notes.)*"
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_CONTRADICTION"

    def test_hallucination_wins_over_pedantry(self):
        bullet = (
            "- `prod.py:1` — Rule 19 untested. lib/directus.py "
            "is NOT present in this diff."
        )
        assert _classify_finding(bullet, bullet) == "NON_BLOCKING_HALLUCINATION"


# ---------------------------------------------------------------------------
# Integration with existing has_blocking() machinery
# ---------------------------------------------------------------------------


class TestHasBlockingIntegration:
    def test_pr24_section_dismissal_still_works(self):
        body = textwrap.dedent(
            """\
            ## AI Review Findings

            ### Blocking

            Reconsidering: no clear Rule 19/35 violations are present.

            - `prod.py:1` — initial concern about deferral pattern.

            ### Non-blocking
            - (none)
            """
        )
        assert has_blocking(body) is False

    def test_empty_bullet_marker_still_works(self):
        body = textwrap.dedent(
            """\
            ## AI Review Findings

            ### Blocking
            - (none)

            ### Non-blocking
            - (none)
            """
        )
        assert has_blocking(body) is False

    def test_non_blocking_skip_phrase_still_works(self):
        bullet = "- `prod.py:1` — concern flagged. Non-blocking finding only."
        assert has_blocking(_wrap(bullet)) is False

    def test_mixed_section_one_real_one_demoted(self):
        # Two bullets — one demoted (hallucination), one genuinely blocking.
        # has_blocking() must still return True because of the second bullet.
        body = textwrap.dedent(
            """\
            ## AI Review Findings

            ### Blocking
            - `prod.py:1` — Rule 35: helper call missing kwarg. lib/directus.py is NOT present in this diff.
            - `prod.py:99` — hardcoded credential `sk-XXXXX` in source.

            ### Non-blocking
            - (none)
            """
        )
        assert has_blocking(body) is True

    def test_all_demoted_section_passes(self):
        body = textwrap.dedent(
            """\
            ## AI Review Findings

            ### Blocking
            - `install_windows.ps1:14` — Rule 19 untested. SHORTCUT_DIRECTUS_MCP_WINDOWS_VALIDATION_PENDING_V1 covers this.
            - `tools/assets.py:29` — Rule 35: register_asset uses Production.tools.registered_write instead of try_post_or_queue.
            - `tools/decisions.py:1` — Rule 35: kwarg concern. lib/directus.py is NOT present in this diff.
            - `tools/decisions.py:5` — Rule 35 issue. *(Downgraded — see Notes.)*

            ### Non-blocking
            - (none)
            """
        )
        assert has_blocking(body) is False


# ---------------------------------------------------------------------------
# _has_shortcut_ld_in_context unit tests
# ---------------------------------------------------------------------------


class TestShortcutLdRegex:
    def test_matches_real_ld_format(self):
        assert (
            _has_shortcut_ld_in_context(
                "see SHORTCUT_FOO_BAR_V1 for details", ""
            )
            is True
        )

    def test_matches_high_version_number(self):
        assert (
            _has_shortcut_ld_in_context("SHORTCUT_DEEP_NESTED_V42", "") is True
        )

    def test_rejects_no_version_suffix(self):
        assert _has_shortcut_ld_in_context("SHORTCUT_FAKE", "") is False

    def test_rejects_non_uppercase(self):
        assert _has_shortcut_ld_in_context("shortcut_foo_v1", "") is False

    def test_finds_in_body_when_absent_from_bullet(self):
        body = "context paragraph mentions SHORTCUT_FOO_V1 here"
        assert _has_shortcut_ld_in_context("just a bullet", body) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
