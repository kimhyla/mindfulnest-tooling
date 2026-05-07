#!/usr/bin/env python3
"""AF.3.1 — F-SVR-001 regression: sidecar TypeError on malformed display_order.

Spec: STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md §5 Phase 2.3
LD: SERVER_SILENT_FAILURE_FAIL_LOUD_V1 (NEW)

Before fix (production_server.py:3885):
    if "display_order" in intro_partition:
        projection["__meta__"] = {"display_order": list(intro_partition["display_order"])}

If `display_order` is an int instead of an iterable, `list(int)` raises
`TypeError: 'int' object is not iterable`. The except: handler at line 3899
silently swallowed it with `print(f"[sidecar] write failed: ...")`, leaving
no sidecar on disk + no observable failure for callers.

After fix (Phase 2.3 root-cause):
    - isinstance guard ensures malformed display_order does not raise
    - catch-all log uses stderr + traceback (loud, structured) so any future
      unforeseen exception class is observable in CI / production logs

Run directly:
    python3 Production/tools/tests/test_sidecar_display_order_int.py

Or via unittest:
    python3 -m unittest Production.tools.tests.test_sidecar_display_order_int -v
"""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Make production_server importable when run directly.
_THIS = Path(__file__).resolve()
_TOOLS = _THIS.parent.parent  # Production/tools/
sys.path.insert(0, str(_TOOLS))

import production_server as ps  # noqa: E402


def _make_app(tmp_dir: Path) -> SimpleNamespace:
    """Synthesize the minimum AppContext shape _write_sidecar_L_json reads."""
    storyboard_path = tmp_dir / "storyboard_v59_prod.html"
    storyboard_path.write_text("<html></html>", encoding="utf-8")
    return SimpleNamespace(
        event_dir=tmp_dir,
        storyboard_path=storyboard_path,
        _storyboard_write_lock=threading.RLock(),
    )


class TestSidecarDisplayOrderInt(unittest.TestCase):
    def test_malformed_display_order_int_does_not_raise(self) -> None:
        """display_order=int (regression case) must not raise; sidecar writes anyway."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            app = _make_app(tmp)
            state = {
                "videos": {
                    "intro": {
                        "beats": {
                            "beat_01": {"text": "hello", "phase_1": {}, "_version": 1},
                        },
                        # MALFORMED: int instead of list. Pre-fix this raises
                        # TypeError: 'int' object is not iterable on list().
                        "display_order": 5,
                    }
                }
            }
            # Should not raise; should not return None on this kind of input post-fix.
            result = ps._write_sidecar_L_json(app, state)
            self.assertIsNotNone(result, "sidecar write must complete despite malformed display_order")
            sidecar = tmp / "storyboard_v59_prod.L.json"
            self.assertTrue(sidecar.is_file(), "sidecar JSON must exist on disk")

    def test_well_formed_display_order_list_writes_meta(self) -> None:
        """display_order=[...] (well-formed) writes __meta__.display_order list."""
        import json as _json
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            app = _make_app(tmp)
            state = {
                "videos": {
                    "intro": {
                        "beats": {"beat_01": {"text": "x", "phase_1": {}, "_version": 1}},
                        "display_order": ["beat_01", "beat_02"],
                    }
                }
            }
            result = ps._write_sidecar_L_json(app, state)
            self.assertIsNotNone(result)
            sidecar = tmp / "storyboard_v59_prod.L.json"
            data = _json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertIn("__meta__", data)
            self.assertEqual(data["__meta__"]["display_order"], ["beat_01", "beat_02"])

    def test_no_display_order_does_not_emit_meta(self) -> None:
        """Absent display_order → no __meta__ key (existing behavior preserved)."""
        import json as _json
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            app = _make_app(tmp)
            state = {
                "videos": {
                    "intro": {
                        "beats": {"beat_01": {"text": "x", "phase_1": {}, "_version": 1}},
                    }
                }
            }
            result = ps._write_sidecar_L_json(app, state)
            self.assertIsNotNone(result)
            sidecar = tmp / "storyboard_v59_prod.L.json"
            data = _json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertNotIn("__meta__", data)


if __name__ == "__main__":
    unittest.main()
