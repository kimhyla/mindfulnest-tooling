"""DEDICATED_PORT_SCOPE_TRUTH_V1 — CLI Event_N on 5110+N is immutable scope truth."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS.parent))

from lib.event_pin import resolve_startup_event, write_persisted_event_pin  # noqa: E402
from lib.server_port_guard import port_to_event_id  # noqa: E402


class PortToEventIdTests(unittest.TestCase):
    def test_5112_maps_event_2(self) -> None:
        self.assertEqual(port_to_event_id(5112), "Event_2")

    def test_below_range_returns_none(self) -> None:
        self.assertIsNone(port_to_event_id(5110))


class ResolveStartupDedicatedPortTests(unittest.TestCase):
    def test_dedicated_port_cli_wins_over_global_pin(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            prod.mkdir()
            ev1 = prod / "Event_1"
            ev2 = prod / "Event_2"
            ev1.mkdir()
            ev2.mkdir()
            (ev1 / "storyboard_v59_prod.html").write_text("<html></html>", encoding="utf-8")
            (ev2 / "storyboard_v59_prod.html").write_text("<html></html>", encoding="utf-8")

            import lib.event_pin as event_pin

            original = event_pin.EVENT_DIR
            event_pin.EVENT_DIR = lambda eid: prod / str(eid)
            try:
                write_persisted_event_pin(
                    prod,
                    event_id="Event_1",
                    storyboard="storyboard_v59_prod.html",
                )
                resolved_dir, sb, eid, source = resolve_startup_event(
                    ev2,
                    "storyboard_v59_prod.html",
                    "Event_2",
                    port=5112,
                )
            finally:
                event_pin.EVENT_DIR = original

            self.assertEqual(source, "cli_dedicated_port")
            self.assertEqual(eid, "Event_2")
            self.assertEqual(resolved_dir.name, "Event_2")
            self.assertEqual(sb, "storyboard_v59_prod.html")


class HandleEventLoadDedicatedPortGuard(unittest.TestCase):
    def test_rejects_event_swap_on_dedicated_port(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "event_video_dedicated_test",
            TOOLS / "server_handlers" / "event_video.py",
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["event_video_dedicated_test"] = mod
        spec.loader.exec_module(mod)

        handler = MagicMock()
        handler.app = MagicMock(
            event_dir=Path("/tmp/Production/Event_2"),
            event_id="Event_2",
            cli_pinned_event_id="Event_2",
            server_port=5112,
            event_generation=1,
        )
        mod.handle_event_load(handler, {"event_id": "Event_1"})
        handler._send_error_v59.assert_called_once()
        args, kwargs = handler._send_error_v59.call_args
        self.assertEqual(args[0], 409)
        self.assertEqual(
            kwargs.get("error_code") or args[1],
            "DEDICATED_PORT_PIN_IMMUTABLE",
        )


if __name__ == "__main__":
    unittest.main()
