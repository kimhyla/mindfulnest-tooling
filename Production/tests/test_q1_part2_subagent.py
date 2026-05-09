"""
Q1 Part 2 — stop_conditional_opus_reviewer (v3-E contract tests).

Requires Python >= 3.12 (hook hard-fails on import otherwise).
Loads hook from ~/.claude/hooks/stop_conditional_opus_reviewer.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_HOOK = Path.home() / ".claude" / "hooks" / "stop_conditional_opus_reviewer.py"


def _load_hook():
    if sys.version_info < (3, 12):
        raise unittest.SkipTest("Q1 Part 2 hook requires Python >= 3.12")
    if not _HOOK.is_file():
        raise unittest.SkipTest(f"hook missing: {_HOOK}")
    spec = importlib.util.spec_from_file_location("q1_part2_hook", _HOOK)
    if spec is None or spec.loader is None:
        raise unittest.SkipTest("could not load hook spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setUpModule():
    global q1
    try:
        q1 = _load_hook()
    except unittest.SkipTest:
        q1 = None  # type: ignore[assignment]


q1 = None  # populated in setUpModule


@unittest.skipUnless(sys.version_info >= (3, 12), "hook pins Python >= 3.12")
class ParseClaudeResponseTests(unittest.TestCase):
    """§7-AMEND-V3.3 fixtures F-PR-1 .. F-PR-11."""

    def setUp(self):
        self.assertIsNotNone(q1)

    def test_f_pr_1_non_json(self) -> None:
        r = q1.parse_claude_response("this is not JSON")
        self.assertEqual(
            r,
            {
                "text": "this is not JSON",
                "total_cost_usd": None,
                "total_tokens": None,
                "schema": "fallback",
            },
        )

    def test_f_pr_2_json_not_object(self) -> None:
        r = q1.parse_claude_response("[1, 2, 3]")
        self.assertEqual(r["text"], "[1, 2, 3]")
        self.assertIsNone(r["total_cost_usd"])
        self.assertIsNone(r["total_tokens"])
        self.assertEqual(r["schema"], "fallback")

    def test_f_pr_3_v1_happy(self) -> None:
        raw = '{"result": "approved", "total_cost_usd": 0.04, "total_tokens": 1234}'
        r = q1.parse_claude_response(raw)
        self.assertEqual(r["text"], "approved")
        self.assertEqual(r["total_cost_usd"], 0.04)
        self.assertIsInstance(r["total_cost_usd"], float)
        self.assertEqual(r["total_tokens"], 1234)
        self.assertEqual(r["schema"], "v1")

    def test_f_pr_4_string_cost_rejected(self) -> None:
        raw = '{"result": "approved", "total_cost_usd": "0.04", "total_tokens": 1234}'
        r = q1.parse_claude_response(raw)
        self.assertEqual(r["text"], "approved")
        self.assertIsNone(r["total_cost_usd"])
        self.assertEqual(r["total_tokens"], 1234)
        self.assertEqual(r["schema"], "fallback")

    def test_f_pr_5_no_cost(self) -> None:
        r = q1.parse_claude_response('{"text": "approved"}')
        self.assertEqual(r["text"], "approved")
        self.assertIsNone(r["total_cost_usd"])
        self.assertIsNone(r["total_tokens"])
        self.assertEqual(r["schema"], "fallback")

    def test_f_pr_6_no_canonical_text_key(self) -> None:
        r = q1.parse_claude_response('{"foo": "bar"}')
        self.assertEqual(r["text"], '{"foo": "bar"}')
        self.assertIsNone(r["total_cost_usd"])
        self.assertEqual(r["schema"], "fallback")

    def test_f_pr_7_result_non_string(self) -> None:
        raw = '{"result": true, "total_cost_usd": 0.04, "total_tokens": 1234}'
        r = q1.parse_claude_response(raw)
        self.assertTrue(r["text"].startswith("{"))
        self.assertEqual(r["total_cost_usd"], 0.04)
        self.assertEqual(r["total_tokens"], 1234)
        self.assertEqual(r["schema"], "v1")

    def test_f_pr_8_bool_cost_rejected(self) -> None:
        raw = '{"result": "approved", "total_cost_usd": true, "total_tokens": 1234}'
        r = q1.parse_claude_response(raw)
        self.assertEqual(r["text"], "approved")
        self.assertIsNone(r["total_cost_usd"])
        self.assertEqual(r["total_tokens"], 1234)
        self.assertEqual(r["schema"], "fallback")

    def test_f_pr_9_v2_observed(self) -> None:
        raw = (
            '{"result": "approved", "total_cost_usd": 0.04, '
            '"usage": {"input_tokens": 1000, "output_tokens": 234}}'
        )
        r = q1.parse_claude_response(raw)
        self.assertEqual(r["text"], "approved")
        self.assertEqual(r["total_tokens"], 1234)
        self.assertEqual(r["schema"], "v2-observed")

    def test_f_pr_10_partial_usage(self) -> None:
        raw = (
            '{"result": "approved", "total_cost_usd": 0.04, '
            '"usage": {"input_tokens": 1000}}'
        )
        r = q1.parse_claude_response(raw)
        self.assertEqual(r["text"], "approved")
        self.assertIsNone(r["total_tokens"])
        self.assertEqual(r["schema"], "fallback")

    def test_f_pr_11_usage_not_dict(self) -> None:
        raw = '{"result": "approved", "total_cost_usd": 0.04, "usage": "not-a-dict"}'
        r = q1.parse_claude_response(raw)
        self.assertEqual(r["text"], "approved")
        self.assertIsNone(r["total_tokens"])
        self.assertEqual(r["schema"], "fallback")

    def test_never_raises(self) -> None:
        for x in [None, "", "{", "\xff bad unicode surrogate"]:
            r = q1.parse_claude_response(x)  # type: ignore[arg-type]
            self.assertIsInstance(r["text"], str)
            self.assertIn(r["schema"], ("v1", "v2-observed", "fallback"))


@unittest.skipUnless(sys.version_info >= (3, 12), "hook pins Python >= 3.12")
class L4TagSuppressionTests(unittest.TestCase):
    """v2 §3-AMEND F-EC-* (deterministic 120-char lookahead)."""

    def setUp(self):
        self.assertIsNotNone(q1)

    def test_f_ec_1_period_before_tag(self) -> None:
        s = "the hook fires when X. [CONFIRMED from foo.py:42]"
        self.assertFalse(q1.has_unverified_state_claim(s))

    def test_f_ec_2_newline_before_tag(self) -> None:
        s = "the hook fires when X.\n[CONFIRMED from foo.py:42]"
        self.assertFalse(q1.has_unverified_state_claim(s))

    def test_f_ec_4_two_claims_one_tag(self) -> None:
        s = "X is wired and Y fires when Z [CONFIRMED from foo.py:42]"
        self.assertFalse(q1.has_unverified_state_claim(s))

    def test_f_ec_5_prefix_tag_does_not_suppress(self) -> None:
        s = "[CONFIRMED] X is wired by the new gate"
        self.assertTrue(q1.has_unverified_state_claim(s))

    def test_f_ec_7_end_of_text_no_tag(self) -> None:
        # Spec string "reads from" does not match Step 2.5b second group; use a
        # clear pattern match at EOF (EC-7: clipped window, no suppression).
        s = "the hook fires when saving"
        self.assertTrue(q1.has_unverified_state_claim(s))


@unittest.skipUnless(sys.version_info >= (3, 12), "hook pins Python >= 3.12")
class InfrastructureGlobTests(unittest.TestCase):
    """§6-AMEND-V3.5 empirical probe replay."""

    def setUp(self):
        self.assertIsNotNone(q1)

    def test_github_workflows_relative(self) -> None:
        self.assertTrue(
            q1.matches_infrastructure_path("Production/.github/workflows/ci.yml")
        )

    def test_git_hooks_leaf(self) -> None:
        self.assertTrue(
            q1.matches_infrastructure_path(
                "Production/scripts/git_hooks/pre-commit"
            )
        )

    def test_migrate_glob(self) -> None:
        self.assertTrue(
            q1.matches_infrastructure_path("Production/scripts/migrate_foo.py")
        )

    def test_directus_star(self) -> None:
        self.assertTrue(
            q1.matches_infrastructure_path("Production/lib/directus_writers.py")
        )

    def test_storyboard_negative(self) -> None:
        self.assertFalse(
            q1.matches_infrastructure_path("Production/Storyboards/M1E1.html")
        )

    def test_spec_md_negative(self) -> None:
        self.assertFalse(
            q1.matches_infrastructure_path(
                "Production/docs/Q1_PART2_CONDITIONAL_REVIEWER_TECH_SPEC_v3.md"
            )
        )


@unittest.skipUnless(sys.version_info >= (3, 12), "hook pins Python >= 3.12")
class RecursionGuardTests(unittest.TestCase):
    """§10-AMEND F-FC-1 .. F-FC-4."""

    def setUp(self):
        self.assertIsNotNone(q1)

    def test_f_fc_1_subprocess_missing_fail_closed(self) -> None:
        with patch.object(
            q1.subprocess,
            "check_output",
            side_effect=FileNotFoundError("no ps"),
        ):
            self.assertTrue(q1.has_recursion_ancestor())

    def test_f_fc_2_depth_exhausted_fail_closed(self) -> None:
        # Never reach ppid<=1 within max_depth — ambiguous chain => fail-closed True.
        def fake_check_output(cmd, **kwargs):  # noqa: ARG001
            s = " ".join(cmd)
            if "ppid=" in s:
                return b"42\n"
            return b"/bin/sh\n"

        with patch.object(q1.subprocess, "check_output", side_effect=fake_check_output):
            self.assertTrue(q1.has_recursion_ancestor(max_depth=5))

    def test_f_fc_3_mid_walk_fail_closed(self) -> None:
        from subprocess import CalledProcessError

        def boom(cmd, **kwargs):  # noqa: ARG001
            raise CalledProcessError(1, cmd)

        with patch.object(q1.subprocess, "check_output", side_effect=boom):
            self.assertTrue(q1.has_recursion_ancestor())

    def test_f_fc_4_clean_chain(self) -> None:
        hook_pid = str(os.getpid())

        def fake_check_output(cmd, **kwargs):  # noqa: ARG001
            if len(cmd) >= 4 and cmd[-1] == "ppid=":
                target = cmd[2]
                if target == hook_pid:
                    return b"501\n"
                if target == "501":
                    return b"1\n"
            if len(cmd) >= 4 and cmd[-1] == "command=":
                return b"/bin/bash\n"
            return b"\n"

        with patch.object(q1.subprocess, "check_output", side_effect=fake_check_output):
            self.assertFalse(q1.has_recursion_ancestor(max_depth=5))


@unittest.skipUnless(sys.version_info >= (3, 12), "hook pins Python >= 3.12")
class TriggerConjunctionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(q1)

    def _write_transcript(self, lines: list[dict]) -> str:
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            for row in lines:
                f.write(json.dumps(row) + "\n")
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_all_layers_storyboard_no_spawn(self) -> None:
        """L3 fails — path not on allow-list."""
        # Note: real Claude Code transcripts are chronological — most recent
        # entry (last in file) is the assistant turn. _read_last_turn_bundle
        # iterates reversed and breaks on user, so transcript order must be
        # [..., user, assistant] for the assistant entry to be processed.
        path = self._write_transcript(
            [
                {"type": "user", "message": {}},
                {
                    "type": "assistant",
                    "timestamp": "t1",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Write",
                                "input": {"file_path": "Production/Storyboards/M1E1.html"},
                            },
                            {
                                "type": "text",
                                "text": "the hook is wired by the new gate",
                            },
                        ]
                    },
                },
            ]
        )
        payload = {
            "session_id": "test-sess",
            "transcript_path": path,
            "stop_hook_active": False,
        }
        layers = q1.trigger_layer_pass(payload)
        self.assertTrue(layers["L0"])
        self.assertTrue(layers["L1"])
        self.assertTrue(layers["L2"])
        self.assertFalse(layers["L3"])

    def test_autonomous_blocks_l1(self) -> None:
        path = self._write_transcript([])
        payload = {
            "session_id": "s2",
            "transcript_path": path,
            "is_autonomous": True,
        }
        self.assertFalse(q1.trigger_layer_pass(payload)["L1"])

    def test_infra_plus_claim_all_layers_true_when_guards_clear(self) -> None:
        # Real Claude Code transcript order: [..., user, assistant_just_completed]
        path = self._write_transcript(
            [
                {"type": "user", "message": {}},
                {
                    "type": "assistant",
                    "timestamp": "t1",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Write",
                                "input": {
                                    "file_path": "Production/.github/workflows/ci.yml"
                                },
                            },
                            {
                                "type": "text",
                                "text": "the hook is wired by the new gate",
                            },
                        ]
                    },
                },
            ]
        )
        payload = {
            "session_id": "s3",
            "transcript_path": path,
            "stop_hook_active": False,
        }
        with patch.object(q1, "has_recursion_ancestor", return_value=False):
            with patch.object(q1, "has_reviewer_env_active", return_value=False):
                with patch.object(q1, "has_output_sentinel_fail_closed", return_value=False):
                    layers = q1.trigger_layer_pass(payload)
        for i in range(6):
            self.assertTrue(layers[f"L{i}"], msg=f"L{i} should pass: {layers}")


class PythonRuntimeGateTests(unittest.TestCase):
    """§6-AMEND-V3.5b — import must raise SystemExit(1) on Python < 3.12."""

    def test_import_hard_fail_below_312(self) -> None:
        if not _HOOK.is_file():
            self.skipTest(f"hook missing: {_HOOK}")
        if sys.version_info >= (3, 12):
            self.skipTest("need an interpreter <3.12 to assert import-time SystemExit(1)")
        p_lit = json.dumps(str(_HOOK))
        code = (
            "import importlib.util\n"
            f"p = {p_lit}\n"
            "spec = importlib.util.spec_from_file_location('h', p)\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 1, msg=f"stderr={r.stderr!r}")
        self.assertIn("FATAL", r.stderr)


if __name__ == "__main__":
    unittest.main()
