"""Tests for ProductionHandler._send_error_v59 — V59 Phase 7."""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))

from Production.tools.production_server import ProductionHandler  # noqa: E402


class _FakeHandler:
    def __init__(self):
        self.calls = []

    def _send_json(self, status, payload):
        self.calls.append((status, payload))


def test_send_error_v59_canonical_shape():
    h = _FakeHandler()
    ProductionHandler._send_error_v59(
        h,
        400,
        error_code="X",
        error_message="y",
    )
    assert len(h.calls) == 1
    status, payload = h.calls[0]
    assert status == 400
    # P5.5 (2026-05-19): _send_error_v59 includes `error` (back-compat
    # mirror of error_message) per V59_ERROR_SHAPE_v2 — test pre-dated
    # that addition.
    assert payload == {
        "ok": False,
        "error": "y",
        "error_code": "X",
        "error_message": "y",
        "retry_safe": True,
        "hint": None,
    }


def test_send_error_v59_with_hint_and_extra():
    h = _FakeHandler()
    ProductionHandler._send_error_v59(
        h,
        422,
        error_code="VALIDATION",
        error_message="bad input",
        retry_safe=False,
        hint="fix the body",
        extra={"field": "beat_id"},
    )
    status, payload = h.calls[0]
    assert status == 422
    assert payload["hint"] == "fix the body"
    assert payload["field"] == "beat_id"
    assert payload["retry_safe"] is False


def test_existing_send_json_unchanged():
    h = _FakeHandler()
    h._send_json(400, {"error": "x"})
    assert h.calls == [(400, {"error": "x"})]
