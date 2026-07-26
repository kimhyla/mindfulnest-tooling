"""EVENT_LOAD_IDEMPOTENT_REPIN_V1 — a no-op re-pin must not re-run the swap.

Regression cover for the 2026-07-26 deploy hang: after a fleet restart, every
POST /api/event/load for the event the port already served re-ran the full
scope swap — including a sidecar reconcile that walks kling_o3_clips on Dropbox
— serialized under event_load_lock. Retries (deploy g.5 pin, UI reload) queued
faster than the walks drained, so event/load hung indefinitely while
/api/event/current answered normally.

These tests drive the real handle_event_load with a handler double whose lock
and reconcile paths explode if touched, proving the short-circuit answers
without the lock, without a reconcile, and without a generation bump.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS.parent))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "event_video_idempotent_test",
        TOOLS / "server_handlers" / "event_video.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["event_video_idempotent_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class _PoisonLock:
    """A lock stand-in that fails the test if the handler tries to take it."""

    def __enter__(self):
        raise AssertionError(
            "idempotent re-pin must not acquire event_load_lock — that queues "
            "behind the reconcile pileup it exists to avoid"
        )

    def __exit__(self, *exc):
        return False


def _make_handler(event_dir: Path, storyboard: Path) -> MagicMock:
    handler = MagicMock()
    handler.app = MagicMock(
        event_dir=event_dir,
        event_id=event_dir.name,
        storyboard_path=storyboard,
        cli_pinned_event_id=event_dir.name,
        server_port=5110 + int(event_dir.name.rsplit("_", 1)[1]),
        event_generation=7,
        scope_type="event",
        active_milestone_id=None,
        event_load_lock=_PoisonLock(),
    )
    return handler


def _fixture_event(tmp: Path, event_id: str) -> tuple[Path, Path]:
    event_dir = tmp / "Production" / event_id
    event_dir.mkdir(parents=True)
    storyboard = event_dir / "storyboard_v59_prod.html"
    storyboard.write_text("<html></html>", encoding="utf-8")
    return event_dir, storyboard


class EventLoadIdempotentRepinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module()

    def test_same_event_repin_short_circuits(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            event_dir, storyboard = _fixture_event(Path(tmp), "Event_4")
            handler = _make_handler(event_dir, storyboard)

            self.mod.handle_event_load(handler, {"event_id": "Event_4"})

            handler._send_error_v59.assert_not_called()
            handler._send_json.assert_called_once()
            status, payload = handler._send_json.call_args[0]
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["already_loaded"])
            self.assertEqual(payload["event_id"], "Event_4")
            self.assertEqual(
                payload["event_generation"], 7,
                "no-op re-pin must not bump event_generation — async jobs "
                "pinned to it must stay valid (LD-460)",
            )

    def test_repin_answers_while_lock_is_held_by_a_stuck_swap(self) -> None:
        """The deploy-killing shape: lock held by a wedged reconcile."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            event_dir, storyboard = _fixture_event(Path(tmp), "Event_4")
            handler = _make_handler(event_dir, storyboard)
            real_lock = threading.Lock()
            real_lock.acquire()  # simulate a swap wedged mid-reconcile
            handler.app.event_load_lock = real_lock

            done = threading.Event()

            def _call():
                self.mod.handle_event_load(handler, {"event_id": "Event_4"})
                done.set()

            t = threading.Thread(target=_call, daemon=True)
            t.start()
            self.assertTrue(
                done.wait(timeout=10),
                "re-pin blocked on event_load_lock held by a stuck swap",
            )
            handler._send_json.assert_called_once()

    def test_milestone_scope_still_takes_full_swap_path(self) -> None:
        """Exiting milestone scope must reconcile — never short-circuit it."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            event_dir, storyboard = _fixture_event(Path(tmp), "Event_4")
            handler = _make_handler(event_dir, storyboard)
            handler.app.scope_type = "milestone"
            handler.app.active_milestone_id = "m1"

            with self.assertRaises(AssertionError) as ctx:
                self.mod.handle_event_load(handler, {"event_id": "Event_4"})
            self.assertIn("event_load_lock", str(ctx.exception))

    def test_different_storyboard_still_takes_full_swap_path(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            event_dir, storyboard = _fixture_event(Path(tmp), "Event_4")
            other = event_dir / "storyboard_v60_prod.html"
            other.write_text("<html></html>", encoding="utf-8")
            handler = _make_handler(event_dir, storyboard)

            with self.assertRaises(AssertionError) as ctx:
                self.mod.handle_event_load(
                    handler, {"event_id": "Event_4", "storyboard": other.name}
                )
            self.assertIn("event_load_lock", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
