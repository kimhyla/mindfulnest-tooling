"""
PERIODIC class + §B3 severity — weekly_preflight_audit (PERIODIC_CLASS_TECH_SPEC_v3).

Run from Production/:
  PYTHONPATH=. python3 -m unittest tests.test_weekly_preflight_periodic -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

_PROD = Path(__file__).resolve().parents[1]
_TOOLS = str(_PROD / "tools")
for p in (str(_PROD), _TOOLS, str(_PROD / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)
# tools-only credentials helpers now live under `credentials_lib`, so they no
# longer collide with the canonical Production/lib package during discovery.

import weekly_preflight_audit as wpa  # noqa: E402


class FakeShortcutClient:
    """Minimal client for check_shortcut_ld_closure_dates — no network."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.post_calls: list[dict] = []

    def get(self, collection: str, filters=None, fields=None, limit=None):  # noqa: ARG002
        if collection == "prod_locked_decisions":
            return list(self._rows)
        if collection == "prod_blockers":
            return []
        return []

    def _request(self, method: str, path: str, data=None):  # noqa: ARG002
        self.post_calls.append({"method": method, "path": path, "data": data})
        return {"data": {"id": 1}}


class PeriodicInvalidConfigTests(unittest.TestCase):
    """§B2 — PERIODIC + NULL cadence."""

    def test_periodic_null_cadence_emits_critical_finding(self) -> None:
        rows = [
            {
                "id": 999001,
                "decision_key": "SHORTCUT_TEST_PERIODIC_NULL_V1",
                "date_locked": "2026-05-10",
                "decision_text": "",
                "notes": "",
                "review_cadence": None,
                "next_review_date": None,
            }
        ]
        with patch.dict(
            wpa.SHORTCUT_LD_CLASSIFICATION,
            {999001: "PERIODIC"},
            clear=False,
        ):
            findings = wpa.check_shortcut_ld_closure_dates(
                FakeShortcutClient(rows), dry_run=True
            )
        bad = [f for f in findings if f.get("finding_type") == "PERIODIC_INVALID_CONFIGURATION"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].get("severity"), "critical")
        self.assertTrue(bad[0].get("critical"))


class SeverityMigrationTests(unittest.TestCase):
    """§B3 — severity string + WARN parity (.upper() == WARN)."""

    def test_finding_severity_str_prefers_string(self) -> None:
        self.assertEqual(
            wpa._finding_severity_str({"severity": "critical", "critical": False}),
            "critical",
        )
        self.assertEqual(
            wpa._finding_severity_str({"severity": "warn", "critical": True}),
            "warn",
        )

    def test_fallback_boolean_critical(self) -> None:
        self.assertEqual(
            wpa._finding_severity_str({"critical": True}),
            "critical",
        )
        self.assertEqual(
            wpa._finding_severity_str({"critical": False}),
            "warn",
        )

    def test_tag_upper_warn_matches_v2_print(self) -> None:
        f = {"message": "x", "critical": False, "severity": "warn"}
        self.assertEqual(wpa._finding_severity_str(f).upper(), "WARN")


class RelativedeltaCadenceTests(unittest.TestCase):
    """§B4 — calendar-aware increments (not +30 days)."""

    def test_monthly_cross_month(self) -> None:
        base = date(2026, 1, 31)
        nxt = wpa.add_review_cadence_to_date(base, "monthly")
        self.assertEqual(nxt, date(2026, 2, 28))

    def test_quarterly(self) -> None:
        base = date(2026, 1, 15)
        self.assertEqual(
            wpa.add_review_cadence_to_date(base, "quarterly"),
            date(2026, 4, 15),
        )

    def test_semi_annually_normalized(self) -> None:
        base = date(2026, 3, 1)
        self.assertEqual(
            wpa.add_review_cadence_to_date(base, "semi_annually"),
            date(2026, 9, 1),
        )

    def test_annually(self) -> None:
        base = date(2025, 2, 28)
        self.assertEqual(
            wpa.add_review_cadence_to_date(base, "annually"),
            date(2026, 2, 28),
        )


class ClassificationStampTests(unittest.TestCase):
    """§B1 — _classification stamped after UNCLASSIFIED gate."""

    def test_stamped_on_classified_row(self) -> None:
        rows = [
            {
                "id": 999002,
                "decision_key": "SHORTCUT_TEST_STAMP_V1",
                "date_locked": "2026-05-10",
                "review_cadence": "none",
                "next_review_date": None,
            }
        ]
        with patch.dict(
            wpa.SHORTCUT_LD_CLASSIFICATION,
            {999002: "PERIODIC"},
            clear=False,
        ):
            wpa.check_shortcut_ld_closure_dates(FakeShortcutClient(rows), dry_run=True)
        self.assertEqual(rows[0].get("_classification"), "PERIODIC")


class IsAuditEligibleTests(unittest.TestCase):
    """§B5 — none / event-driven opt-out; calendar cadences eligible."""

    def test_none_not_eligible(self) -> None:
        self.assertFalse(
            wpa.is_audit_eligible_periodic_row(
                "PERIODIC",
                {"review_cadence": "none"},
            )
        )

    def test_null_not_eligible(self) -> None:
        self.assertFalse(
            wpa.is_audit_eligible_periodic_row(
                "PERIODIC",
                {"review_cadence": None},
            )
        )

    def test_quarterly_eligible(self) -> None:
        self.assertTrue(
            wpa.is_audit_eligible_periodic_row(
                "PERIODIC",
                {"review_cadence": "quarterly"},
            )
        )


class PeriodicDueSurfacingTests(unittest.TestCase):
    def test_overdue_critical_severity(self) -> None:
        today = datetime.now(timezone.utc).date()
        overdue = (today - timedelta(days=10)).isoformat()
        rows = [
            {
                "id": 999003,
                "decision_key": "SHORTCUT_TEST_OVERDUE_V1",
                "date_locked": "2026-05-01",
                "review_cadence": "monthly",
                "next_review_date": overdue,
            }
        ]
        with patch.dict(
            wpa.SHORTCUT_LD_CLASSIFICATION,
            {999003: "PERIODIC"},
            clear=False,
        ):
            findings = wpa.check_shortcut_ld_closure_dates(
                FakeShortcutClient(rows), dry_run=True
            )
        hit = [f for f in findings if f.get("classification") == "PERIODIC" and "OVERDUE" in f.get("message", "")]
        self.assertTrue(hit)
        self.assertEqual(hit[0].get("severity"), "critical")

    def test_due_soon_warn_severity(self) -> None:
        today = datetime.now(timezone.utc).date()
        soon = (today + timedelta(days=3)).isoformat()
        rows = [
            {
                "id": 999004,
                "decision_key": "SHORTCUT_TEST_SOON_V1",
                "date_locked": "2026-05-01",
                "review_cadence": "monthly",
                "next_review_date": soon,
            }
        ]
        with patch.dict(
            wpa.SHORTCUT_LD_CLASSIFICATION,
            {999004: "PERIODIC"},
            clear=False,
        ):
            findings = wpa.check_shortcut_ld_closure_dates(
                FakeShortcutClient(rows), dry_run=True
            )
        hit = [f for f in findings if "due in" in f.get("message", "")]
        self.assertTrue(hit)
        self.assertEqual(hit[0].get("severity"), "warn")
        self.assertFalse(hit[0].get("critical"))


if __name__ == "__main__":
    unittest.main()
