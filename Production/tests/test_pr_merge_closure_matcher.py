"""
PR-merge auto-close matcher tightening — LD-576-amend-1 regression suite.

Pins the LD-565 / PR-#8 false-close scenario from 2026-05-09 so the matcher
cannot regress to scraping arbitrary UPPER_SNAKE tokens from decision_text.

Also pins the LD-545 / V59_CICD_GAP_FIX correct-close path: under the new
matcher, an LD that declares a structured `gates on X PR merge` closure event
must still match a PR whose body cites that same identifier.

Run from Production/:
  PYTHONPATH=. python3 -m unittest tests.test_pr_merge_closure_matcher -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PROD = Path(__file__).resolve().parents[1]
_TOOLS = str(_PROD / "tools")
for p in (str(_PROD), _TOOLS, str(_PROD / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import weekly_preflight_audit as wpa  # noqa: E402


# ---------------------------------------------------------------------------
# Realistic LD fixtures (decision_text/notes shaped like the real Directus rows
# that drove the 2026-05-09 incident — see LD-576-amend-1 audit trail).
# ---------------------------------------------------------------------------

# LD-565: closure criteria are NOT PR-merge-based (private flip OR Enterprise
# tier OR 4-month hard cap). decision_text mentions API_KEYS_MASTER as related
# context (the LD references the master key inventory file). Under the OLD
# matcher, API_KEYS_MASTER was scraped as a candidate token; PR-#8's body
# cited API_KEYS_MASTER.md and the matcher fired a false-close.
LD_565_FIXTURE = {
    "id": 565,
    "decision_key": "SHORTCUT_TOOLING_REPO_PUBLIC_FOR_CODESCAN_V1",
    "decision_text": (
        "Tooling repo (kimhyla/mindfulnest-tooling) flipped to public so GitHub "
        "free-tier CodeQL can scan it. Closure event is whichever fires first: "
        "(a) tooling repo flips back to private, (b) we upgrade to Enterprise "
        "with private-repo CodeQL, (c) hard cap 2026-09-07. References file "
        "API_KEYS_MASTER.md for the rotation inventory; no PR-merge gate."
    ),
    "notes": "",
    "status": "active",
}

# LD-545: closure criteria ARE PR-merge-based. decision_text uses the
# structured `gates on V59_CICD_GAP_FIX PR merge` grammar that the new matcher
# is designed to recognize. PR body for the gap-fix PR cites
# V59_CICD_GAP_FIX_SPEC_v1, which is a substring containing the structured
# token V59_CICD_GAP_FIX.
LD_545_FIXTURE = {
    "id": 545,
    "decision_key": "SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1",
    "decision_text": (
        "Storyboard build script gets a focused fix BEFORE V59 CI/CD gap-fix "
        "lands. This LD gates on V59_CICD_GAP_FIX PR merge to main."
    ),
    "notes": "Tracking: tooling repo. See V59_CICD_GAP_FIX_SPEC_v1.md.",
    "status": "active",
}

# Synthetic LD that cites a literal owner/repo#NN — the strongest closure signal.
LD_EXPLICIT_PR_FIXTURE = {
    "id": 9999,
    "decision_key": "SHORTCUT_SYNTHETIC_EXPLICIT_PR_REF_V1",
    "decision_text": (
        "Closes when kimhyla/mindfulnest-tooling#42 merges to main."
    ),
    "notes": "",
    "status": "active",
}


# ---------------------------------------------------------------------------
# PR fixtures (shaped like `gh pr list --json` rows).
# ---------------------------------------------------------------------------

# Real PR-#8: API key rotation work in tooling repo. Body cites API_KEYS_MASTER.md.
# Under the OLD matcher this triggered the LD-565 false-close.
PR_8_TOOLING_FIXTURE = {
    "number": 8,
    "title": "Rotate prod API keys; refresh credentials inventory",
    "body": (
        "## Summary\n\nRotates production API keys per quarterly policy. "
        "Updates API_KEYS_MASTER.md inventory. Refs lessons-learned doc.\n"
    ),
    "headRefName": "rotate-api-keys-2026-05",
    "mergedAt": "2026-05-09T00:00:00Z",
    "mergeCommit": {"oid": "deadbeef00000000000000000000000000000000"},
}

# Synthetic gap-fix PR whose body cites V59_CICD_GAP_FIX_SPEC_v1 (the structured
# closure-event token from LD-545's grammar).
PR_GAP_FIX_FIXTURE = {
    "number": 12,
    "title": "V59 CI/CD gap fix — Phase A through H",
    "body": (
        "Implements V59_CICD_GAP_FIX_SPEC_v1.md Phases A-H: workflows, "
        "browser-smoke hooks, CodeQL/Dependabot security scanning."
    ),
    "headRefName": "v59-cicd-gap-fix",
    "mergedAt": "2026-05-08T00:00:00Z",
    "mergeCommit": {"oid": "abc1230000000000000000000000000000000000"},
}

# Synthetic PR matching an explicit owner/repo#NN reference.
PR_EXPLICIT_REF_FIXTURE = {
    "number": 42,
    "title": "Unrelated title that does not cite any LD identifier",
    "body": "Body text completely unrelated to any LD prose.",
    "headRefName": "feature/something",
    "mergedAt": "2026-05-08T00:00:00Z",
    "mergeCommit": {"oid": "f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0"},
}


class FalseCloseRegressionTests(unittest.TestCase):
    """LD-565 / PR-#8 — must NOT match under tightened matcher."""

    def test_ld_565_signals_excludes_api_keys_master(self) -> None:
        signals = wpa._ld_closure_signals(LD_565_FIXTURE)
        # decision_keys: present (always extracted).
        self.assertEqual(
            signals["decision_keys"],
            [
                "SHORTCUT_TOOLING_REPO_PUBLIC_FOR_CODESCAN_V1",
                "SHORTCUT_TOOLING_REPO_PUBLIC_FOR_CODESCAN",
            ],
        )
        # No `repo#NN` in LD-565's prose.
        self.assertEqual(signals["explicit_pr_refs"], [])
        # No structured `gates on X PR merge` grammar in LD-565's prose.
        self.assertEqual(signals["structured_event_tokens"], [])
        # API_KEYS_MASTER must NOT appear anywhere in signals.
        flat = (
            signals["decision_keys"]
            + [t for t in signals["structured_event_tokens"]]
            + [r for ref in signals["explicit_pr_refs"] for r in ref[:1]]
        )
        self.assertNotIn("API_KEYS_MASTER", flat)

    def test_ld_565_does_not_match_pr_8(self) -> None:
        """The exact 2026-05-09 false-close scenario."""
        signals = wpa._ld_closure_signals(LD_565_FIXTURE)
        result = wpa._match_pr_to_ld(
            PR_8_TOOLING_FIXTURE,
            "kimhyla/mindfulnest-tooling",
            signals,
        )
        self.assertIsNone(
            result,
            "REGRESSION: LD-565 false-close on PR-#8 returned (LD-576-amend-1)",
        )

    def test_old_substring_token_no_longer_used(self) -> None:
        """Even if API_KEYS_MASTER were forced into prose, the matcher must
        not fall through to scraping arbitrary UPPER_SNAKE tokens."""
        ld = {
            "id": 99001,
            "decision_key": "SHORTCUT_INERT_PROSE_TOKEN_V1",
            "decision_text": (
                "References API_KEYS_MASTER.md, ROTATION_POLICY_V2, and "
                "OPERATOR_CHECKLIST. None of these are closure events."
            ),
            "notes": "PR #99 mentioned in passing for context.",
        }
        pr = {
            "number": 99,
            "title": "Update API_KEYS_MASTER inventory and ROTATION_POLICY_V2",
            "body": "Touches OPERATOR_CHECKLIST.md.",
            "headRefName": "ops/key-rotation",
            "mergedAt": "2026-05-08T00:00:00Z",
        }
        signals = wpa._ld_closure_signals(ld)
        # Only the decision_key + de-suffixed form should appear.
        self.assertEqual(
            signals["decision_keys"],
            ["SHORTCUT_INERT_PROSE_TOKEN_V1", "SHORTCUT_INERT_PROSE_TOKEN"],
        )
        self.assertEqual(signals["structured_event_tokens"], [])
        self.assertIsNone(
            wpa._match_pr_to_ld(pr, "kimhyla/mindfulnest-tooling", signals)
        )


class StructuredEventTokenTests(unittest.TestCase):
    """LD-545 / V59_CICD_GAP_FIX — must STILL match under tightened matcher."""

    def test_ld_545_extracts_structured_token(self) -> None:
        signals = wpa._ld_closure_signals(LD_545_FIXTURE)
        self.assertIn("V59_CICD_GAP_FIX", signals["structured_event_tokens"])

    def test_ld_545_matches_gap_fix_pr_body(self) -> None:
        """Regression check: the LD-545 close on 2026-05-08 was correct.
        Under the new matcher, structured-event-token match must still fire."""
        signals = wpa._ld_closure_signals(LD_545_FIXTURE)
        result = wpa._match_pr_to_ld(
            PR_GAP_FIX_FIXTURE,
            "kimhyla/mindfulnest-tooling",
            signals,
        )
        self.assertIsNotNone(result, "LD-545 must still match the gap-fix PR")
        self.assertTrue(
            result.startswith("body:") or result.startswith("title:"),
            f"unexpected match field: {result!r}",
        )
        self.assertIn("V59_CICD_GAP_FIX", result)

    def test_structured_token_requires_pr_merge_grammar(self) -> None:
        """A bare `V59_CICD_GAP_FIX` mention without `PR merge` grammar is
        NOT promoted to a structured token."""
        ld = {
            "id": 99002,
            "decision_key": "SHORTCUT_NO_GRAMMAR_V1",
            "decision_text": "References V59_CICD_GAP_FIX in passing.",
            "notes": "",
        }
        signals = wpa._ld_closure_signals(ld)
        self.assertEqual(signals["structured_event_tokens"], [])


class ExplicitPRRefTests(unittest.TestCase):
    """LD cites `kimhyla/mindfulnest-tooling#NN` literally — strongest tier."""

    def test_explicit_pr_ref_extracted(self) -> None:
        signals = wpa._ld_closure_signals(LD_EXPLICIT_PR_FIXTURE)
        self.assertIn(
            ("kimhyla/mindfulnest-tooling", 42),
            signals["explicit_pr_refs"],
        )

    def test_explicit_pr_ref_matches_by_number(self) -> None:
        signals = wpa._ld_closure_signals(LD_EXPLICIT_PR_FIXTURE)
        result = wpa._match_pr_to_ld(
            PR_EXPLICIT_REF_FIXTURE,
            "kimhyla/mindfulnest-tooling",
            signals,
        )
        self.assertEqual(result, "explicit_pr_ref:kimhyla/mindfulnest-tooling#42")

    def test_explicit_pr_ref_does_not_match_wrong_repo(self) -> None:
        signals = wpa._ld_closure_signals(LD_EXPLICIT_PR_FIXTURE)
        # Same PR number, but different repo → must not match.
        self.assertIsNone(
            wpa._match_pr_to_ld(
                PR_EXPLICIT_REF_FIXTURE,
                "kimhyla/mindfulnest-ios",
                signals,
            )
        )

    def test_path_prefix_not_treated_as_pr_ref(self) -> None:
        """`Production/docs#5` looks like owner/repo#NN but isn't a real GitHub
        ref. Same path-prefix guard as _resolve_repo_for_ld."""
        ld = {
            "id": 99003,
            "decision_key": "SHORTCUT_PATH_PREFIX_GUARD_V1",
            "decision_text": "See Production/docs#5 for context.",
            "notes": "",
        }
        signals = wpa._ld_closure_signals(ld)
        self.assertEqual(signals["explicit_pr_refs"], [])


class DecisionKeyMatchTests(unittest.TestCase):
    """Decision-key literal in PR title/body/branch is the primary tier."""

    def test_decision_key_match_in_title(self) -> None:
        ld = {
            "id": 99004,
            "decision_key": "SHORTCUT_FOO_BAR_V1",
            "decision_text": "",
            "notes": "",
        }
        pr = {
            "number": 1,
            "title": "Implements SHORTCUT_FOO_BAR_V1 closure",
            "body": "",
            "headRefName": "feat/foo-bar",
        }
        signals = wpa._ld_closure_signals(ld)
        result = wpa._match_pr_to_ld(pr, "owner/repo", signals)
        self.assertEqual(result, "title:SHORTCUT_FOO_BAR_V1")

    def test_decision_key_match_case_insensitive(self) -> None:
        """Decision-key check is case-insensitive; explicit token check is not."""
        ld = {
            "id": 99005,
            "decision_key": "SHORTCUT_FOO_BAR_V1",
            "decision_text": "",
            "notes": "",
        }
        pr = {
            "number": 1,
            "title": "implements shortcut_foo_bar_v1 closure",
            "body": "",
            "headRefName": "feat/foo-bar",
        }
        signals = wpa._ld_closure_signals(ld)
        result = wpa._match_pr_to_ld(pr, "owner/repo", signals)
        self.assertEqual(result, "title:SHORTCUT_FOO_BAR_V1")

    def test_destripped_decision_key_matches(self) -> None:
        """`SHORTCUT_FOO_BAR_V1` → `SHORTCUT_FOO_BAR` (de-suffixed)."""
        ld = {
            "id": 99006,
            "decision_key": "SHORTCUT_FOO_BAR_V1",
            "decision_text": "",
            "notes": "",
        }
        pr = {
            "number": 1,
            "title": "Implements SHORTCUT_FOO_BAR closure",
            "body": "",
            "headRefName": "feat/foo-bar",
        }
        signals = wpa._ld_closure_signals(ld)
        result = wpa._match_pr_to_ld(pr, "owner/repo", signals)
        self.assertEqual(result, "title:SHORTCUT_FOO_BAR")


if __name__ == "__main__":
    unittest.main()
