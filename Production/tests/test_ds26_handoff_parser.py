"""
DS-26 handoff parser + gate-check integration (T6, T10, T12, T13).

Run from Production/:
  PYTHONPATH=. python3 -m unittest tests.test_ds26_handoff_parser -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PROD = Path(__file__).resolve().parents[1]
if str(_PROD) not in sys.path:
    sys.path.insert(0, str(_PROD))

from scripts.hooks.ds26_gate_check import check_ds26_mechanical_gate  # noqa: E402
from scripts.hooks.ds26_handoff_parser import (  # noqa: E402
    LegacyHandoffNotSupported,
    compare_handoff_to_template,
    compare_handoffs,
    parse_handoff,
)

FIXTURES = _PROD / "tests" / "fixtures" / "handoffs"


class MockDirectusClient:
    def __init__(self, rows: dict | None = None, exc: BaseException | None = None) -> None:
        self.rows = rows or {}
        self.exc = exc

    def get_item(self, collection: str, item_id: object) -> object:
        if self.exc is not None:
            raise self.exc
        return self.rows.get((collection, int(item_id)))


class ParseHandoffTests(unittest.TestCase):
    def test_t6_legacy_raises_legacy_handoff_not_supported(self) -> None:
        path = FIXTURES / "HANDOFF_LEGACY_V1_STYLE.md"
        with self.assertRaises(LegacyHandoffNotSupported):
            parse_handoff(str(path))

    def test_v2_two_gates_parsed(self) -> None:
        r = parse_handoff(str(FIXTURES / "HANDOFF_V2_TWO_GATES.md"))
        self.assertEqual(r.handoff_format_version, "v2")
        self.assertEqual(r.declared_gate_count, 2)
        self.assertEqual(len(r.evidence_checklist), 2)


class CompareHandoffsTests(unittest.TestCase):
    def test_t10_dual_handoff_gate_count_drift(self) -> None:
        cur = parse_handoff(str(FIXTURES / "HANDOFF_V2_THREE_GATES.md"))
        prior = parse_handoff(str(FIXTURES / "HANDOFF_V2_TWO_GATES.md"))
        d = compare_handoffs(cur, prior)
        self.assertTrue(d.gate_count_drift)
        self.assertEqual(d.prior_gate_count, 2)
        self.assertEqual(d.current_gate_count, 3)


class CompareTemplateTests(unittest.TestCase):
    def test_t12_template_example_two_gates_handoff_three_mismatch(self) -> None:
        hp = parse_handoff(str(FIXTURES / "HANDOFF_V2_THREE_GATES.md"))
        c = compare_handoff_to_template(hp, str(FIXTURES / "TEMPLATE_TWO_GATE_EXAMPLE.md"))
        self.assertFalse(c.matches_template)
        self.assertEqual(c.template_gate_count, 2)
        self.assertEqual(c.handoff_gate_count, 3)


class GateCheckHandoffIntegrationTests(unittest.TestCase):
    def test_t10_gate_check_handoff_drift(self) -> None:
        row = {"id": 578}
        c = MockDirectusClient({("prod_locked_decisions", 578): row})
        out = """HALT gate scan: 3 gates detected
Gate 1 — Evidence: LD-578
Gate 2 — Evidence: LD-578
Gate 3 — Evidence: LD-578
"""
        r = check_ds26_mechanical_gate(
            out,
            candidate_handoffs=1,
            client=c,  # type: ignore[arg-type]
            handoff_path=str(FIXTURES / "HANDOFF_V2_THREE_GATES.md"),
            prior_handoff_path=str(FIXTURES / "HANDOFF_V2_TWO_GATES.md"),
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertIn("HANDOFF_GATE_COUNT_DRIFT", r.failures)

    def test_t12_gate_check_template_mismatch(self) -> None:
        row = {"id": 578}
        c = MockDirectusClient({("prod_locked_decisions", 578): row})
        out = """HALT gate scan: 3 gates detected
Gate 1 — Evidence: LD-578
Gate 2 — Evidence: LD-578
Gate 3 — Evidence: LD-578
"""
        r = check_ds26_mechanical_gate(
            out,
            candidate_handoffs=1,
            client=c,  # type: ignore[arg-type]
            handoff_path=str(FIXTURES / "HANDOFF_V2_THREE_GATES.md"),
            handoff_template_path=str(FIXTURES / "TEMPLATE_TWO_GATE_EXAMPLE.md"),
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertIn("HANDOFF_TEMPLATE_GATE_COUNT_MISMATCH", r.failures)

    def test_t13_handoff_reference_missing_arg_warning(self) -> None:
        row = {"id": 578}
        c = MockDirectusClient({("prod_locked_decisions", 578): row})
        out = """HALT gate scan: 1 gate(s) detected
See HANDOFF_IMPLEMENTATION_20260509.md for scope.
Gate 1 — Evidence: LD-578
"""
        r = check_ds26_mechanical_gate(
            out,
            candidate_handoffs=1,
            client=c,  # type: ignore[arg-type]
            handoff_path=None,
        )
        self.assertEqual(r.verdict, "PASS")
        self.assertIn("HANDOFF_REFERENCE_MISSING_ARG", r.warnings)

    def test_t6_legacy_handoff_in_gate_check(self) -> None:
        c = MockDirectusClient({("prod_locked_decisions", 578): {"id": 578}})
        out = "HALT gate scan: 1 gate(s) detected\nGate 1 — Evidence: LD-578\n"
        r = check_ds26_mechanical_gate(
            out,
            candidate_handoffs=1,
            client=c,  # type: ignore[arg-type]
            handoff_path=str(FIXTURES / "HANDOFF_LEGACY_V1_STYLE.md"),
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertIn("legacy_handoff_unsupported", r.failures)
        self.assertTrue(any("legacy_handoff_unsupported" in x for x in r.surface_checklist))

    def test_count_mismatch_uses_parsed_handoff_count(self) -> None:
        c = MockDirectusClient({("prod_locked_decisions", 578): {"id": 578}})
        out = """HALT gate scan: 3 gates detected
Gate 1 — Evidence: LD-578
Gate 2 — Evidence: LD-578
Gate 3 — Evidence: LD-578
"""
        r = check_ds26_mechanical_gate(
            out,
            candidate_handoffs=1,
            client=c,  # type: ignore[arg-type]
            handoff_path=str(FIXTURES / "HANDOFF_V2_TWO_GATES.md"),
        )
        self.assertEqual(r.verdict, "FAIL")
        self.assertIn("COUNT_MISMATCH", r.failures)


if __name__ == "__main__":
    unittest.main()
