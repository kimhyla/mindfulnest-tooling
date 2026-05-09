"""
DS-26 gate-check wrapper — LD-597 payload shape + Rule 35 read-back.

Run from Production/:
  PYTHONPATH=. python3 -m unittest tests.test_ds26_gate_check_wrapper -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Optional

_PROD = Path(__file__).resolve().parents[1]
if str(_PROD) not in sys.path:
    sys.path.insert(0, str(_PROD))

from scripts.hooks.ds26_gate_check_wrapper import (  # noqa: E402
    Rule35ReadBackFailure,
    run_ds26_gate_check_with_activity_log,
)

_LD597_FORBIDDEN = frozenset(
    {
        "task_description",
        "metadata",
        "task_id",
        "status",
        "timestamp",
        "task_name",
    }
)


class MockActivityDirectusClient:
    """Minimal client: post_item + get_item for prod_activity_log tests."""

    def __init__(self, *, mismatch_readback: bool = False) -> None:
        self.post_calls: list[tuple[str, dict[str, Any]]] = []
        self._rows: dict[int, dict[str, Any]] = {}
        self._next_id = 100
        self._mismatch_readback = mismatch_readback
        self.rows_for_gate: dict[tuple[str, int], Any] = {
            ("prod_locked_decisions", 578): {"id": 578},
        }

    def get_item(self, collection: str, item_id: Any, fields: Optional[list[str]] = None) -> Any:
        if collection != "prod_activity_log":
            return self.rows_for_gate.get((collection, int(item_id)))
        iid = int(item_id)
        if self._mismatch_readback and iid in self._rows:
            row = dict(self._rows[iid])
            row["action"] = "TAMPERED"
            return row
        return self._rows.get(iid)

    def post_item(self, collection: str, data: dict[str, Any], retry_post: bool = False) -> Any:
        self.post_calls.append((collection, data))
        iid = self._next_id
        self._next_id += 1
        row = dict(data)
        row["id"] = iid
        self._rows[iid] = row
        return row


class WrapperLd597Tests(unittest.TestCase):
    def test_ld597_no_forbidden_top_level_keys(self) -> None:
        client = MockActivityDirectusClient()
        out = "HALT gate scan: 1 gate(s) detected\nGate 1 — Evidence: LD-578\n"
        run_ds26_gate_check_with_activity_log(
            out,
            client=client,  # type: ignore[arg-type]
            session_id="sess-unit-1",
        )
        self.assertEqual(len(client.post_calls), 1)
        coll, payload = client.post_calls[0]
        self.assertEqual(coll, "prod_activity_log")
        for k in _LD597_FORBIDDEN:
            self.assertNotIn(k, payload)
        self.assertEqual(set(payload.keys()), {"action", "details", "performed_by", "module_id"})

    def test_rule35_readback_mismatch_raises(self) -> None:
        client = MockActivityDirectusClient(mismatch_readback=True)
        out = "HALT gate scan: 1 gate(s) detected\nGate 1 — Evidence: LD-578\n"
        with self.assertRaises(Rule35ReadBackFailure):
            run_ds26_gate_check_with_activity_log(
                out,
                client=client,  # type: ignore[arg-type]
                session_id="sess-unit-2",
            )

    def test_happy_path_pass_and_round_trip(self) -> None:
        client = MockActivityDirectusClient()
        out = "HALT gate scan: 1 gate(s) detected\nGate 1 — Evidence: LD-578\n"
        res = run_ds26_gate_check_with_activity_log(
            out,
            client=client,  # type: ignore[arg-type]
            session_id="sess-unit-3",
        )
        self.assertEqual(res["gate_result"].verdict, "PASS")
        self.assertIn("activity_log_id", res)
        self.assertEqual(res["posted_row"]["action"], "DS_26_GATE_CHECK_RESULT")
        d = res["posted_row"]["details"]
        self.assertEqual(d["verdict"], "PASS")
        self.assertEqual(d["gates_declared"], 1)
        self.assertEqual(d["gates_verified"], 1)
        self.assertEqual(d["gates_unverified"], 0)
        self.assertEqual(d["session_id"], "sess-unit-3")


if __name__ == "__main__":
    unittest.main()
