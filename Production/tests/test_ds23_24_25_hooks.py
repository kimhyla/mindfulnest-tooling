"""
DS-23 / DS-24 / DS-25 hook + workflow tests.

Coverage maps directly to spec §6.5 fixtures (AT14-AT21 + AF8-AF11) and §13
testing plan. Run from Production/:

  PYTHONPATH=. python3 -m unittest tests.test_ds23_24_25_hooks -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

# Repo path setup
_PROD = Path(__file__).resolve().parents[1]
if str(_PROD) not in sys.path:
    sys.path.insert(0, str(_PROD))

from scripts.hooks import ds23_prepare_commit_msg as ds23  # noqa: E402
from scripts.hooks import ds24_pre_commit as ds24  # noqa: E402


# ---------------------------------------------------------------------------
# Mock Directus client
# ---------------------------------------------------------------------------


class MockDirectusClient:
    """Minimal in-memory client supporting get_items / post_item / get_item."""

    def __init__(
        self,
        rows: Optional[list[dict]] = None,
        *,
        post_returns: Optional[dict] = None,
        raise_on_get: Optional[BaseException] = None,
        raise_on_post: Optional[BaseException] = None,
    ) -> None:
        self.rows = rows or []
        self.posted: list[tuple[str, dict]] = []
        self.read_back: list[tuple[str, Any]] = []
        # Use `is None` instead of `or` so empty-dict overrides survive.
        self.post_returns = {"id": 999} if post_returns is None else post_returns
        self.raise_on_get = raise_on_get
        self.raise_on_post = raise_on_post

    def get_items(self, collection, filters=None, fields=None, sort=None, limit=-1):
        if self.raise_on_get:
            raise self.raise_on_get
        # In a real Directus client, filters narrow the result set. The mock
        # simply returns the provided rows — tests scope rows to what each
        # call should see.
        return list(self.rows)

    def post_item(self, collection, data, retry_post=False):
        if self.raise_on_post:
            raise self.raise_on_post
        self.posted.append((collection, data))
        return dict(self.post_returns)

    def get_item(self, collection, item_id, fields=None):
        self.read_back.append((collection, item_id))
        return {"id": item_id}


# ---------------------------------------------------------------------------
# DS-23 — canonical regex behavior (AT16, RR12, OD10 closure)
# ---------------------------------------------------------------------------


class CanonicalRegexTests(unittest.TestCase):
    def test_matches_secret_token_password(self):
        for word in ("secret", "credential", "token", "password"):
            self.assertTrue(
                ds23.grep_pattern_in_files.__defaults__ is None,  # smoke
            )
        # Direct regex check (we use the embedded canonical default):
        import re
        pat = re.compile(ds23.CANONICAL_PATTERN_DEFAULT, re.IGNORECASE)
        for word in (
            "secret", "credential", "token", "password", "api_key",
            "apikey", "session_id", "session-token", "JWT", "OAUTH",
            "authn", "authz", "authentication", "authorization",
        ):
            self.assertIsNotNone(pat.search(word), f"should match {word!r}")

    def test_does_not_match_unrelated_words(self):
        import re
        pat = re.compile(ds23.CANONICAL_PATTERN_DEFAULT, re.IGNORECASE)
        for word in ("author", "authority", "tokensuffix", "secretkey", "authentic"):
            self.assertIsNone(pat.search(word), f"should NOT match {word!r}")


# ---------------------------------------------------------------------------
# DS-23 — bash-style glob matching (AT21, AF11, G16)
# ---------------------------------------------------------------------------


class GlobMatchTests(unittest.TestCase):
    """Verify SECURITY_GLOBS coverage for both top-level + nested files."""

    def test_at21_top_level_index_ts_matches(self):
        # AT21 v3-D — top-level functions/src/index.ts MUST match.
        self.assertTrue(
            ds23.matches_glob("functions/src/index.ts", "functions/src/*.ts")
        )

    def test_af11_nested_only_misses_top_level(self):
        # AF11 v3-D — bash `**/*.ts` does NOT match top-level files.
        self.assertFalse(
            ds23.matches_glob("functions/src/index.ts", "functions/src/**/*.ts"),
            "Bash `**/*.ts` should NOT match top-level files (this is the bug "
            "v3-D HIGH-2 fixes; top-level companion glob is required)."
        )

    def test_nested_pattern_matches_deep_file(self):
        self.assertTrue(
            ds23.matches_glob("functions/src/sub/foo.ts", "functions/src/**/*.ts")
        )
        self.assertTrue(
            ds23.matches_glob("functions/src/a/b/c.ts", "functions/src/**/*.ts")
        )

    def test_top_level_pattern_misses_nested(self):
        self.assertFalse(
            ds23.matches_glob("functions/src/sub/foo.ts", "functions/src/*.ts")
        )

    def test_production_lib_glob(self):
        self.assertTrue(
            ds23.matches_glob("Production/lib/foo.py", "Production/lib/*.py")
        )
        # Nested under Production/lib/ NOT covered by *.py — by design.
        self.assertFalse(
            ds23.matches_glob("Production/lib/sub/foo.py", "Production/lib/*.py")
        )

    def test_production_server_literal(self):
        self.assertTrue(ds23.matches_glob("production_server.py", "production_server.py"))
        self.assertFalse(ds23.matches_glob("Production/production_server.py", "production_server.py"))

    def test_firestore_rules_glob(self):
        self.assertTrue(ds23.matches_glob("firestore/rules/main.rules", "firestore/rules/*"))


# ---------------------------------------------------------------------------
# DS-23 — pattern config loader (G14)
# ---------------------------------------------------------------------------


class PatternConfigLoaderTests(unittest.TestCase):
    def test_missing_file_returns_default(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "absent.txt"
            self.assertEqual(ds23.load_pattern_config(cfg), ds23.CANONICAL_PATTERN_DEFAULT)

    def test_strips_comments_and_blanks(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "p.txt"
            cfg.write_text("# header\n\n# more\nfoo|bar\n# trailing\n", encoding="utf-8")
            self.assertEqual(ds23.load_pattern_config(cfg), "foo|bar")

    def test_only_comments_raises(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "p.txt"
            cfg.write_text("# nothing else\n# really\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                ds23.load_pattern_config(cfg)


# ---------------------------------------------------------------------------
# DS-23 — gate behavior (AT14, AT15, AT16, AT19, AT21, AF11)
# ---------------------------------------------------------------------------


class GateBehaviorTests(unittest.TestCase):
    """Pure-functional tests of run_gate via injected grep_fn."""

    def _grep_factory(self, hits: dict[str, int]):
        """Return grep_fn returning files+count from a deterministic dict."""
        def fn(files, _pat):
            matched = [f for f in files if hits.get(f, 0) > 0]
            return matched, sum(hits.get(f, 0) for f in matched)
        return fn

    def test_at15_short_form_appended_on_hit(self):
        # AT15 v3: hook auto-appends short-form `Swept: <files>` + `Verified: <count>`.
        result = ds23.run_gate(
            commit_msg_text="initial subject\n",
            staged_files=["production_server.py"],
            pattern=ds23.CANONICAL_PATTERN_DEFAULT,
            halted_files=set(),
            grep_fn=self._grep_factory({"production_server.py": 3}),
            bypass_env=False,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Swept: production_server.py", result.appended_lines)
        self.assertIn("Verified: 3", result.appended_lines)
        self.assertEqual(result.swept_files, ["production_server.py"])
        self.assertEqual(result.verified_count, 3)

    def test_at14_legacy_form_passes_through(self):
        # AT14 v3: hand-authored legacy commit msg passes the union regex (no
        # appended block), exit 0. Run with NO security file modified +
        # legacy commit msg containing the legacy block — even simpler: the
        # gate doesn't fire when no security path. So the meaningful test is:
        # security path + no pattern hit + pre-existing legacy block in msg.
        msg = (
            "subject line\n\n"
            "Swept production_server.py for `(secret|credential|token)`:\n"
            "  - L42 (fixed)\n"
        )
        result = ds23.run_gate(
            commit_msg_text=msg,
            staged_files=["production_server.py"],
            pattern=ds23.CANONICAL_PATTERN_DEFAULT,
            halted_files=set(),
            grep_fn=self._grep_factory({}),  # no hit → require pre-existing block
            bypass_env=False,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.appended_lines, [])

    def test_no_security_file_passes_silently(self):
        result = ds23.run_gate(
            commit_msg_text="subj\n",
            staged_files=["docs/notes.md", "Production/scripts/other.py"],
            pattern=ds23.CANONICAL_PATTERN_DEFAULT,
            halted_files=set(),
            grep_fn=self._grep_factory({}),
            bypass_env=False,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.swept_files, [])

    def test_security_file_no_hit_no_block_fails(self):
        # AF7-equivalent (preserved from v2): security file modified, no pattern
        # hit, no pre-existing sweep block → exit 1.
        result = ds23.run_gate(
            commit_msg_text="subj only\n",
            staged_files=["production_server.py"],
            pattern=ds23.CANONICAL_PATTERN_DEFAULT,
            halted_files=set(),
            grep_fn=self._grep_factory({}),
            bypass_env=False,
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("FATAL DS-23", result.fail_reason or "")

    def test_bypass_env_appends_waiver(self):
        result = ds23.run_gate(
            commit_msg_text="subj\n",
            staged_files=["production_server.py"],
            pattern=ds23.CANONICAL_PATTERN_DEFAULT,
            halted_files=set(),
            grep_fn=self._grep_factory({}),
            bypass_env=True,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(any("DS-23 sweep waived" in line for line in result.appended_lines))

    def test_at19_halted_file_emits_notice_but_runs_ds23(self):
        # AT19 v3: active DS_24_FP_LOOP_SUSPECTED_<file> blocker → DS-24 sweep
        # is skipped (notice emitted) but DS-23 sweep STILL runs.
        result = ds23.run_gate(
            commit_msg_text="subj\n",
            staged_files=["production_server.py"],
            pattern=ds23.CANONICAL_PATTERN_DEFAULT,
            halted_files={"production_server.py"},
            grep_fn=self._grep_factory({"production_server.py": 1}),
            bypass_env=False,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.halted_files, ["production_server.py"])
        self.assertTrue(
            any("DS_24_HALTED_BY_BLOCKER" in line for line in result.stderr_lines),
            "Halt notice MUST be emitted on stderr per §7.1.1 v3-E HIGH-1 fix",
        )
        # DS-23 still ran:
        self.assertIn("Swept: production_server.py", result.appended_lines)

    def test_at21_top_level_functions_src_index_ts_caught(self):
        # AT21 v3-D: top-level functions/src/index.ts containing a security
        # pattern is detected by the SECURITY_GLOBS top-level pattern.
        result = ds23.run_gate(
            commit_msg_text="subj\n",
            staged_files=["functions/src/index.ts"],
            pattern=ds23.CANONICAL_PATTERN_DEFAULT,
            halted_files=set(),
            grep_fn=self._grep_factory({"functions/src/index.ts": 1}),
            bypass_env=False,
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Swept: functions/src/index.ts", result.appended_lines)


# ---------------------------------------------------------------------------
# DS-23 — halt-list fetch (graceful degradation + happy path)
# ---------------------------------------------------------------------------


class HaltListFetchTests(unittest.TestCase):
    def test_no_client_returns_empty(self):
        self.assertEqual(ds23.fetch_halted_files(None), set())

    def test_strips_prefix_correctly(self):
        client = MockDirectusClient(
            rows=[
                {"blocker_type": "DS_24_FP_LOOP_SUSPECTED_production_server.py"},
                {"blocker_type": "DS_24_FP_LOOP_SUSPECTED_functions/src/index.ts"},
                # Non-matching entry — Directus should filter, but defense-in-depth:
                {"blocker_type": "OTHER_BLOCKER_TYPE"},
            ]
        )
        halted = ds23.fetch_halted_files(client)
        self.assertEqual(
            halted,
            {"production_server.py", "functions/src/index.ts"},
        )

    def test_get_items_failure_returns_empty(self):
        client = MockDirectusClient(raise_on_get=RuntimeError("offline"))
        self.assertEqual(ds23.fetch_halted_files(client), set())


# ---------------------------------------------------------------------------
# DS-23 — file-grep helper
# ---------------------------------------------------------------------------


class GrepHelperTests(unittest.TestCase):
    def test_finds_matches_in_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_text("API_KEY=abc\nsession_token = x\n")
            (root / "b.py").write_text("nothing here\n")
            (root / "c.py").write_text("Bearer token foo\n")
            matched, total = ds23.grep_pattern_in_files(
                ["a.py", "b.py", "c.py"],
                ds23.CANONICAL_PATTERN_DEFAULT,
                root,
            )
            self.assertIn("a.py", matched)
            self.assertNotIn("b.py", matched)
            self.assertIn("c.py", matched)
            self.assertGreaterEqual(total, 3)

    def test_missing_file_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            matched, total = ds23.grep_pattern_in_files(
                ["nonexistent.py"], ds23.CANONICAL_PATTERN_DEFAULT, root
            )
            self.assertEqual(matched, [])
            self.assertEqual(total, 0)


# ---------------------------------------------------------------------------
# DS-23 — CLI integration (writes to commit-msg file)
# ---------------------------------------------------------------------------


class CliWriteTests(unittest.TestCase):
    def test_main_appends_to_commit_msg_file(self):
        # Bypass env keeps this hermetic: no Directus, no git needed beyond
        # process exit, and no real grep — bypass returns immediately.
        with tempfile.TemporaryDirectory() as td:
            msg_path = Path(td) / "COMMIT_EDITMSG"
            msg_path.write_text("subj\n", encoding="utf-8")
            os.environ["MN_SKIP_DS23_GATE"] = "1"
            try:
                rc = ds23.main(["ds23_prepare_commit_msg.py", str(msg_path)])
            finally:
                del os.environ["MN_SKIP_DS23_GATE"]
            self.assertEqual(rc, 0)
            content = msg_path.read_text(encoding="utf-8")
            self.assertIn("DS-23 sweep waived", content)

    def test_main_missing_arg_fails(self):
        rc = ds23.main(["ds23_prepare_commit_msg.py"])
        self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# DS-24 — fetch_active_halt_blockers + post_halt_event + post_event_observation
# ---------------------------------------------------------------------------


class Ds24HaltBlockersTests(unittest.TestCase):
    def test_no_client_returns_empty(self):
        self.assertEqual(ds24.fetch_active_halt_blockers(None), {})

    def test_returns_file_keyed_dict_with_id(self):
        client = MockDirectusClient(
            rows=[
                {"id": 7, "blocker_type": "DS_24_FP_LOOP_SUSPECTED_production_server.py"},
                {"id": 9, "blocker_type": "DS_24_FP_LOOP_SUSPECTED_functions/src/index.ts"},
            ]
        )
        out = ds24.fetch_active_halt_blockers(client)
        self.assertEqual(set(out.keys()), {"production_server.py", "functions/src/index.ts"})
        self.assertEqual(out["production_server.py"]["id"], 7)

    def test_get_items_failure_returns_empty(self):
        client = MockDirectusClient(raise_on_get=RuntimeError("offline"))
        self.assertEqual(ds24.fetch_active_halt_blockers(client), {})


class Ds24WriteTests(unittest.TestCase):
    """Verify activity-log POST contract per LD-597 + Rule 35 read-back."""

    def test_post_halt_event_payload_shape(self):
        client = MockDirectusClient(post_returns={"id": 42})
        ok = ds24.post_halt_event(
            client, file_path="production_server.py",
            blocker_id=7, commit_sha="abc123",
        )
        self.assertTrue(ok)
        self.assertEqual(len(client.posted), 1)
        coll, payload = client.posted[0]
        self.assertEqual(coll, "prod_activity_log")
        # LD-597: only allowed top-level keys
        self.assertEqual(
            set(payload.keys()), {"action", "details", "performed_by", "module_id"}
        )
        # No forbidden fields
        for forbidden in ("task_description", "metadata", "task_id", "status",
                          "timestamp", "task_name"):
            self.assertNotIn(forbidden, payload)
        self.assertEqual(payload["action"], "DS_24_HALTED_BY_BLOCKER")
        self.assertEqual(payload["details"]["file_path"], "production_server.py")
        self.assertEqual(payload["details"]["blocker_id"], 7)
        self.assertEqual(payload["details"]["commit_sha"], "abc123")
        # Rule 35 read-back
        self.assertEqual(client.read_back, [("prod_activity_log", 42)])

    def test_post_event_observation_payload_shape(self):
        client = MockDirectusClient(post_returns={"id": 55})
        ok = ds24.post_event_observation(
            client, file_path="Production/lib/foo.py", commit_sha="def456",
        )
        self.assertTrue(ok)
        coll, payload = client.posted[0]
        self.assertEqual(coll, "prod_activity_log")
        self.assertEqual(payload["action"], "DS_24_FP_EVENT")
        self.assertEqual(
            set(payload.keys()), {"action", "details", "performed_by", "module_id"}
        )
        # Rule 35
        self.assertEqual(client.read_back, [("prod_activity_log", 55)])

    def test_post_failure_returns_false(self):
        client = MockDirectusClient(raise_on_post=RuntimeError("network down"))
        ok = ds24.post_halt_event(
            client, file_path="x.py", blocker_id=1, commit_sha=None
        )
        self.assertFalse(ok)

    def test_post_no_id_in_response_returns_false(self):
        client = MockDirectusClient(post_returns={})
        ok = ds24.post_event_observation(
            client, file_path="x.py", commit_sha=None
        )
        self.assertFalse(ok)


class Ds24RunHookTests(unittest.TestCase):
    """End-to-end pure-functional run_hook coverage."""

    def test_halted_file_emits_halt_writer_not_observation(self):
        halt_writes: list[tuple] = []
        obs_writes: list[tuple] = []

        def halt_writer(fp, bid, sha):
            halt_writes.append((fp, bid, sha))
            return True

        def obs_writer(fp, sha):
            obs_writes.append((fp, sha))
            return True

        outcome = ds24.run_hook(
            staged_files=["production_server.py"],
            halt_blockers={"production_server.py": {"id": 7}},
            commit_sha="abc",
            halt_writer=halt_writer,
            observation_writer=obs_writer,
        )
        self.assertEqual(outcome.exit_code, 0)
        self.assertEqual(outcome.halted_files, ["production_server.py"])
        self.assertEqual(outcome.observed_files, [])
        self.assertEqual(halt_writes, [("production_server.py", 7, "abc")])
        self.assertEqual(obs_writes, [])
        self.assertTrue(
            any("DS_24_HALTED_BY_BLOCKER" in line for line in outcome.stderr_lines)
        )

    def test_non_halted_file_emits_observation(self):
        halt_writes: list[tuple] = []
        obs_writes: list[tuple] = []
        outcome = ds24.run_hook(
            staged_files=["Production/lib/foo.py"],
            halt_blockers={},
            commit_sha="def",
            halt_writer=lambda fp, bid, sha: halt_writes.append((fp, bid, sha)) or True,
            observation_writer=lambda fp, sha: obs_writes.append((fp, sha)) or True,
        )
        self.assertEqual(outcome.observed_files, ["Production/lib/foo.py"])
        self.assertEqual(outcome.halted_files, [])
        self.assertEqual(obs_writes, [("Production/lib/foo.py", "def")])
        self.assertEqual(halt_writes, [])

    def test_mixed_staged_set(self):
        halt_writes: list[tuple] = []
        obs_writes: list[tuple] = []
        outcome = ds24.run_hook(
            staged_files=["a.py", "b.py", "c.py"],
            halt_blockers={"b.py": {"id": 12}},
            commit_sha="xyz",
            halt_writer=lambda fp, bid, sha: halt_writes.append((fp, bid, sha)) or True,
            observation_writer=lambda fp, sha: obs_writes.append((fp, sha)) or True,
        )
        self.assertEqual(outcome.halted_files, ["b.py"])
        self.assertEqual(outcome.observed_files, ["a.py", "c.py"])
        self.assertEqual(outcome.halt_event_writes, 1)
        self.assertEqual(outcome.observation_writes, 2)

    def test_exit_code_always_zero_per_tier_1(self):
        # §11.7-v3-C Tier 1: hook NEVER blocks commit. Even with halt + write
        # failures, exit code stays 0.
        outcome = ds24.run_hook(
            staged_files=["production_server.py"],
            halt_blockers={"production_server.py": {"id": 7}},
            commit_sha=None,
            halt_writer=lambda *_args: False,  # all writes fail
            observation_writer=lambda *_args: False,
        )
        self.assertEqual(outcome.exit_code, 0)


# ---------------------------------------------------------------------------
# DS-25 workflow YAML — structural assertions (AT17, AT20, AF8, AF10)
# ---------------------------------------------------------------------------


class WorkflowYamlStructureTests(unittest.TestCase):
    """Validate the CI workflow YAML satisfies §6.5 + §7.3.1 contracts."""

    @classmethod
    def setUpClass(cls):
        cls.path = _PROD / "github_actions" / "ds23_ds25_check.yml"
        cls.text = cls.path.read_text(encoding="utf-8")

    def test_yaml_parses(self):
        # Don't require PyYAML if not installed; do basic structure check.
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(self.text)
            self.assertIn("jobs", data)
            self.assertIn("ds_23_check", data["jobs"])
            self.assertIn("ds_25_check", data["jobs"])
        except ImportError:  # pragma: no cover
            # Fallback: structural string assertion.
            self.assertIn("jobs:", self.text)
            self.assertIn("ds_23_check:", self.text)
            self.assertIn("ds_25_check:", self.text)

    def test_at17_workflow_run_if_clause_broadened(self):
        # AT17: if-clause accepts pull_request | push | schedule | workflow_dispatch.
        for evt in ("pull_request", "push", "schedule", "workflow_dispatch"):
            self.assertIn(
                f"github.event.workflow_run.event == '{evt}'",
                self.text,
                f"missing broadened if-clause branch for {evt}",
            )

    def test_at20_multi_pr_detect_uses_open_state_filter(self):
        # AT20-(c) v3-D: multi-PR-detect uses select(.state == "open").
        self.assertIn(
            'map(select(.state == "open")) | map(.number)',
            self.text,
            "PR enumeration must filter open PRs only (v3-B closure)",
        )

    def test_at20_three_branch_pr_count_handling(self):
        # AT20-(a/b/c): 0/1/>1 branches.
        self.assertIn('PR_COUNT" -eq 0', self.text)
        self.assertIn('PR_COUNT" -gt 1', self.text)
        self.assertIn("DS_25_NO_OPEN_PR", self.text)
        self.assertIn("DS_25_AMBIGUOUS_PR_CONTEXT", self.text)

    def test_af10_ambiguous_pr_writes_blocker_row(self):
        # AF10 v3-D: G15 verification — multi-PR ambiguity MUST write a
        # prod_blockers row (not just an audit-log).
        self.assertIn(
            "prod_blockers",
            self.text,
            "DS_25_AMBIGUOUS_PR_CONTEXT must write a prod_blockers row, not just activity-log",
        )
        # Specifically: blocker_type DS_25_AMBIGUOUS_PR_CONTEXT_<sha>.
        self.assertIn(
            'DS_25_AMBIGUOUS_PR_CONTEXT_$HEAD_SHA',
            self.text,
        )

    def test_tier_3_pr_merge_step_present(self):
        # §7.3.1 v3-E HIGH-2: ds24_halt_check step must be present.
        self.assertIn("ds24_halt_check", self.text)
        self.assertIn("DS_24_PR_MERGE_BLOCKED_", self.text)
        self.assertIn("DS_24_PR_MERGE_BLOCKED_GATE_FIRED", self.text)

    def test_tier_3_step_before_sweep_block_step(self):
        # §7.3.1 v3-E HIGH-2: ds24_halt_check MUST run BEFORE the sweep-block-required step.
        # Match against the `- name:` step header lines (NOT comments that
        # mention the step name) so we measure step-position, not prose-position.
        import re
        steps = [
            (m.start(), m.group(1).strip())
            for m in re.finditer(r"^\s*-\s+name:\s*(.+)$", self.text, flags=re.MULTILINE)
        ]
        names = [n for _, n in steps]
        self.assertIn("Check DS-24 PR-merge halt blockers", names,
                      "ds24_halt_check step missing")
        self.assertIn("Require sweep block in PR body", names,
                      "sweep-block step missing")
        idx_halt = names.index("Check DS-24 PR-merge halt blockers")
        idx_sweep = names.index("Require sweep block in PR body")
        self.assertLess(
            idx_halt, idx_sweep,
            "ds24_halt_check MUST be ordered BEFORE Require sweep block in PR body",
        )

    def test_at18_nested_key_jsonb_filter_on_bypass_lookup(self):
        # AT18 v3 + AF8: bypass-row lookup uses filter[details][commit_sha][_eq]=
        # (NOT the legacy filter[details][_contains]= that v2 used).
        self.assertIn(
            "filter[details][commit_sha][_eq]=",
            self.text,
            "DS-23 + DS-25 bypass lookups must use nested-key jsonb filter (M-3 fix)",
        )
        self.assertNotIn(
            "filter[details][_contains]=",
            self.text,
            "Legacy _contains filter must be eliminated (M-3)",
        )

    def test_ds23_union_regex_present(self):
        # §3.2-v3 / §7.1.2 v3 union regex.
        self.assertIn(
            r"^Swept(:| .+ for `)",
            self.text,
            "DS-23 CI must accept BOTH legacy and short-form Swept blocks",
        )

    def test_ds23_security_globs_grep_pattern(self):
        # Ensures the path-grep covers production_server.py + Production/lib +
        # firestore/rules + functions/src (top-level + nested via .* metachar).
        # The CI uses extended regex grep, which doesn't have bash glob semantics
        # — `functions/src/.*\.(ts|js)$` matches BOTH top-level and nested.
        self.assertIn(r"functions/src/.*\.(ts|js)$", self.text)
        self.assertIn(r"production_server\.py", self.text)

    def test_no_urllib_or_requests_in_yaml(self):
        # YAML uses curl from within `run:` scripts (CI doesn't have Python
        # client). No urllib/requests Python imports in the YAML.
        self.assertNotIn("import urllib", self.text)
        self.assertNotIn("import requests", self.text)

    def test_workflow_triggers_match_codeql_actuals(self):
        # §7.3.1 v3-C [VERIFIED-IN-V3-C]: workflows: [CodeQL].
        self.assertIn("workflows: [CodeQL]", self.text)
        self.assertIn("workflow_run:", self.text)
        self.assertIn("pull_request:", self.text)


# ---------------------------------------------------------------------------
# Hook source files — no urllib/requests direct calls
# ---------------------------------------------------------------------------


class NoDirectHttpInHooksTests(unittest.TestCase):
    """Spec contract: no urllib/requests direct calls anywhere in hook files."""

    HOOKS = [
        _PROD / "scripts" / "hooks" / "ds23_prepare_commit_msg.py",
        _PROD / "scripts" / "hooks" / "ds24_pre_commit.py",
    ]

    def test_no_urllib_imports(self):
        for path in self.HOOKS:
            text = path.read_text(encoding="utf-8")
            for needle in ("import urllib", "from urllib", "import requests", "from requests"):
                self.assertNotIn(
                    needle, text,
                    f"{path.name} must not import urllib/requests directly "
                    "(use DirectusAdminClient per DS-30)",
                )


if __name__ == "__main__":
    unittest.main()
