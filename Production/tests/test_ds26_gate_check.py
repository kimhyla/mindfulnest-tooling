"""
§13 plan T1–T22 behavioral coverage for DS-26 mechanical gate (v3-E).

Run from Production/:
  PYTHONPATH=. python3 -m unittest tests.test_ds26_gate_check -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
_PROD = Path(__file__).resolve().parents[1]
if str(_PROD) not in sys.path:
    sys.path.insert(0, str(_PROD))

from scripts.hooks.ds26_gate_check import (  # noqa: E402
    BROAD_DIRECTUS_HINT_RE,
    DECLARATION_RE,
    check_ds26_mechanical_gate,
    directus_row_evidence_verified,
    extract_gate_evidence_map,
    is_subagent_spawn_call,
    match_directus_reference,
    resolve_collection_and_row,
    should_skip_false_positive_guard,
    verify_gate_evidence,
)


class MockDirectusClient:
    """In-memory get_item — no network."""

    def __init__(
        self,
        rows: Optional[Dict[Tuple[str, int], Any]] = None,
        exc: Optional[BaseException] = None,
    ) -> None:
        self.rows = rows or {}
        self.exc = exc

    def get_item(self, collection: str, item_id: Any) -> Any:
        if self.exc is not None:
            raise self.exc
        return self.rows.get((collection, int(item_id)))


class DeclarationRegexTests(unittest.TestCase):
    def test_f4_gate_s_parens(self) -> None:
        text = "HALT gate scan: 0 gate(s) detected"
        m = DECLARATION_RE.search(text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "0")


class MatchDirectusReferenceV3E(unittest.TestCase):
    """v3-E: MODE 2 only when multiline — F-FRAG-1 / F-FRAG-2 / T19–T20."""

    def test_t19_ffrag1_single_line_junk_unverified(self) -> None:
        ev = "LD-578xyz"
        self.assertIsNone(match_directus_reference(ev))
        self.assertTrue(BROAD_DIRECTUS_HINT_RE.search(ev))

    def test_t20_ffrag2_multiline_embedded(self) -> None:
        ev = "Per LD-578: see decision text\nNext line"
        m = match_directus_reference(ev)
        self.assertIsNotNone(m)
        t = resolve_collection_and_row(m)
        self.assertEqual(t, ("locked_decisions", 578))

    def test_f11_ld_space(self) -> None:
        m = match_directus_reference("LD 578")
        self.assertIsNotNone(m)
        self.assertEqual(resolve_collection_and_row(m), ("locked_decisions", 578))


class RowClassificationTests(unittest.TestCase):
    def test_none_empty_fail(self) -> None:
        self.assertFalse(directus_row_evidence_verified(None))
        self.assertFalse(directus_row_evidence_verified({}))
        self.assertFalse(directus_row_evidence_verified([]))

    def test_wrap_null_empty_list_empty_dict(self) -> None:
        self.assertFalse(directus_row_evidence_verified({"data": None}))
        self.assertFalse(directus_row_evidence_verified({"data": []}))
        self.assertFalse(directus_row_evidence_verified({"data": {}}))

    def test_wrap_truthy_inner(self) -> None:
        self.assertTrue(directus_row_evidence_verified({"data": {"id": 578}}))
        self.assertTrue(directus_row_evidence_verified({"id": 578}))
        self.assertTrue(directus_row_evidence_verified([{"id": 1}]))


class VerifyGateEvidenceTests(unittest.TestCase):
    def test_t15_probe_raises_unverified(self) -> None:
        sc: list[str] = []
        client = MockDirectusClient(exc=ConnectionError("offline"))
        ev = "prod_locked_decisions row 578"
        self.assertTrue(BROAD_DIRECTUS_HINT_RE.search(ev))
        ok = verify_gate_evidence(
            {"evidence_source": ev, "gate_index": 1},
            client,  # type: ignore[arg-type]
            sc,
            assistant_turns=(),
        )
        self.assertFalse(ok)
        self.assertTrue(any("UNVERIFIED_DIRECTUS_REF" in x for x in sc))
        self.assertIn("ConnectionError", sc[0])

    def test_t16_broad_but_no_precise_parse(self) -> None:
        sc: list[str] = []
        ev = "prod_locked_decisions rows 578 and 614"
        self.assertTrue(BROAD_DIRECTUS_HINT_RE.search(ev))
        self.assertIsNone(match_directus_reference(ev))
        ok = verify_gate_evidence(
            {"evidence_source": ev, "gate_index": 1},
            MockDirectusClient(),
            sc,
        )
        self.assertFalse(ok)
        self.assertTrue(any("precise_regex_did_not_parse" in x for x in sc))

    def test_t21_wrap_data_null(self) -> None:
        sc: list[str] = []
        c = MockDirectusClient({("prod_locked_decisions", 578): {"data": None}})
        ok = verify_gate_evidence(
            {"evidence_source": "LD-578", "gate_index": 1},
            c,  # type: ignore[arg-type]
            sc,
        )
        self.assertFalse(ok)
        self.assertEqual(sc, [])

    def test_t22_wrap_data_empty_list(self) -> None:
        c = MockDirectusClient({("prod_locked_decisions", 578): {"data": []}})
        sc: list[str] = []
        ok = verify_gate_evidence(
            {"evidence_source": "LD-578", "gate_index": 1},
            c,  # type: ignore[arg-type]
            sc,
        )
        self.assertFalse(ok)

    def test_wrap3_truthy_inner(self) -> None:
        c = MockDirectusClient({("prod_locked_decisions", 578): {"data": {"id": 578}}})
        sc: list[str] = []
        ok = verify_gate_evidence(
            {"evidence_source": "LD-578", "gate_index": 1},
            c,  # type: ignore[arg-type]
            sc,
        )
        self.assertTrue(ok)


class CheckOrchestrationTests(unittest.TestCase):
    def test_t1_zero_gates(self) -> None:
        out = "HALT gate scan: 0 gate(s) detected"
        r = check_ds26_mechanical_gate(
            out, candidate_handoffs=1, client=MockDirectusClient()
        )
        self.assertEqual(r.verdict, "PASS")
        self.assertEqual(r.declaration_count, 0)

    def test_t17_four_reference_forms(self) -> None:
        row = {"id": 578}
        c = MockDirectusClient({("prod_locked_decisions", 578): row})
        out = """HALT gate scan: 4 gates detected
Gate 1 — Evidence: LD 578
Gate 2 — Evidence: LD-578
Gate 3 — Evidence: prod_locked_decisions/578
Gate 4 — Evidence: items/prod_locked_decisions/578
"""
        r = check_ds26_mechanical_gate(out, candidate_handoffs=1, client=c)  # type: ignore[arg-type]
        self.assertEqual(r.verdict, "PASS")

    def test_t2_three_gates_verified(self) -> None:
        row = {"id": 578}
        c = MockDirectusClient({("prod_locked_decisions", 578): row})
        out = """HALT gate scan: 3 gates detected, 3 met, 0 not met.
Gate 1 — Evidence: LD 578
Gate 2 — Evidence: LD-578
Gate 3 — Evidence: items/prod_locked_decisions/578
"""
        r = check_ds26_mechanical_gate(out, candidate_handoffs=1, client=c)  # type: ignore[arg-type]
        self.assertEqual(r.verdict, "PASS")
        self.assertEqual(r.declaration_count, 3)

    def test_t3_missing_declaration(self) -> None:
        r = check_ds26_mechanical_gate(
            "No scan line here", candidate_handoffs=1, client=MockDirectusClient()
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertIn("MISSING_DECLARATION", r.failures)

    def test_t4_count_mismatch(self) -> None:
        out = "HALT gate scan: 0 gate(s) detected"
        r = check_ds26_mechanical_gate(
            out,
            candidate_handoffs=1,
            handoff_gate_count=3,
            client=MockDirectusClient(),
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertIn("COUNT_MISMATCH", r.failures)

    def test_t5_missing_evidence_lines(self) -> None:
        out = "HALT gate scan: 3 gates detected"
        r = check_ds26_mechanical_gate(
            out, candidate_handoffs=1, client=MockDirectusClient()
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertTrue(any("EVIDENCE_MISSING_FOR_GATE_" in f for f in r.failures))

    def test_t9_silent_skip(self) -> None:
        r = check_ds26_mechanical_gate(
            "anything",
            candidate_handoffs=0,
            tool_calls=[],
            session_complete_writes=0,
            client=MockDirectusClient(),
        )
        self.assertEqual(r.verdict, "SILENT_SKIP")

    def test_t11_task_tool_prevents_skip(self) -> None:
        self.assertFalse(
            should_skip_false_positive_guard(
                candidate_handoffs=0,
                tool_calls=[{"name": "Task"}],
                session_complete_writes=0,
            )
        )
        self.assertTrue(is_subagent_spawn_call({"name": "Task"}))

    def test_t18_file_path_text_presence_pass(self) -> None:
        path = "Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md"
        out = f"""HALT gate scan: 1 gate(s) detected, 1 met, 0 not met.
Gate 1 — Evidence: {path}
"""
        self.assertIsNone(BROAD_DIRECTUS_HINT_RE.search(path))
        r = check_ds26_mechanical_gate(
            out,
            candidate_handoffs=1,
            client=None,
            assistant_turns=[out],
        )
        self.assertEqual(r.verdict, "PASS")

    def test_t19_embedded_t19_unverified_checklist(self) -> None:
        out = """HALT gate scan: 1 gate(s) detected
Gate 1 — Evidence: LD-578xyz
"""
        r = check_ds26_mechanical_gate(
            out, candidate_handoffs=1, client=MockDirectusClient()
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertTrue(any("UNVERIFIED_DIRECTUS_REF" in m for m in r.surface_checklist))

    def test_t20_multiline_embedded_pass(self) -> None:
        row = {"id": 578}
        c = MockDirectusClient({("prod_locked_decisions", 578): row})
        out = """HALT gate scan: 1 gate(s) detected
Gate 1 — Evidence: Per LD-578: see decision text
Next line
"""
        r = check_ds26_mechanical_gate(out, candidate_handoffs=1, client=c)  # type: ignore[arg-type]
        self.assertEqual(r.verdict, "PASS")
        self.assertEqual(
            r.evidence_entries_parsed.get(1, "").count("\n"),
            1,
        )

    def test_t8_halt_but_proceeded(self) -> None:
        out = """HALT gate scan: 1 gate(s) detected, 0 met, 1 not met. HALTED.
Gate 1 — Evidence: LD-578
"""
        c = MockDirectusClient({("prod_locked_decisions", 578): {"id": 578}})
        r = check_ds26_mechanical_gate(
            out,
            candidate_handoffs=1,
            client=c,  # type: ignore[arg-type]
            session_complete_writes=2,
            forbid_complete_writes_when_halted=True,
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertIn("HALT_DECLARED_BUT_PROCEEDED", r.failures)

    def test_t14_routes_missing_row_not_unverified(self) -> None:
        """v2 T14 — row absent => FAIL_EVIDENCE_MISSING, not probe failure."""
        out = """HALT gate scan: 1 gate(s) detected
Gate 1 — Evidence: prod_locked_decisions row 578
"""
        c = MockDirectusClient({})  # no row
        r = check_ds26_mechanical_gate(out, candidate_handoffs=1, client=c)  # type: ignore[arg-type]
        self.assertEqual(r.verdict, "FAIL")
        self.assertEqual(r.surface_checklist, [])
        self.assertTrue(any("FAIL_EVIDENCE_MISSING" in f for f in r.failures))


class RegexFixtureTableTests(unittest.TestCase):
    """§3.4-A.1 F1–F10 style spots."""

    def test_plurals_and_case(self) -> None:
        self.assertIsNotNone(DECLARATION_RE.search("HALT gate scan: 12 gates detected"))
        self.assertIsNotNone(DECLARATION_RE.search("halt gate scan: 3 gates detected"))

    def test_f8_f10_no_match(self) -> None:
        self.assertIsNone(DECLARATION_RE.search("No HALT gates declared"))
        self.assertIsNone(
            DECLARATION_RE.search("HALT gate scan completed: 3 gates detected")
        )


class ExtractGateMapTests(unittest.TestCase):
    def test_table_row(self) -> None:
        text = """
| 1 | G | LD-578 | P | F |
|---|---|---|---|---|
"""
        m = extract_gate_evidence_map(text)
        self.assertIn(1, m)


if __name__ == "__main__":
    unittest.main()
