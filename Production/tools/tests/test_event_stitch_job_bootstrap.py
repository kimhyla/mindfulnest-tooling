"""EVENT_STITCH_JOB_BOOTSTRAP_V1 — canonical Event_N_stitch always registered."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from server_handlers import stitch_editor as se
from server_handlers.stitch_editor import (
    EVENT_STITCH_JOB_BOOTSTRAP_V1,
    ensure_event_stitch_job_registered,
    is_numbered_event_id,
    stitch_bootstrap_shim_for_app,
)


class NumberedEventIdTests(unittest.TestCase):
    def test_numbered_event_pattern(self) -> None:
        self.assertTrue(is_numbered_event_id("Event_1"))
        self.assertTrue(is_numbered_event_id("Event_89"))
        self.assertFalse(is_numbered_event_id("Event_Oliver"))
        self.assertFalse(is_numbered_event_id("Milestone_1"))


class EnsureEventStitchJobRegisteredTests(unittest.TestCase):
    def test_creates_empty_canonical_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            event_dir = root / "Production" / "Event_7"
            event_dir.mkdir(parents=True)
            stitch_path = root / "Production" / "tools" / "stitch_editor_state.json"
            stitch_path.parent.mkdir(parents=True)
            stitch_path.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")

            from production_server import StitchEditorState  # noqa: PLC0415

            store = StitchEditorState(stitch_path)
            app = MagicMock()
            app.event_dir = event_dir
            app.stitch_state = store
            app._event_stitch_state = store
            h = stitch_bootstrap_shim_for_app(app)

            boot = ensure_event_stitch_job_registered(
                h,
                "Event_7",
                hydrate_from_disk=False,
            )
            self.assertTrue(boot.get("ok"))
            self.assertEqual(boot.get("code"), EVENT_STITCH_JOB_BOOTSTRAP_V1)
            self.assertTrue(boot.get("created"))
            self.assertTrue(boot.get("changed"))

            saved = json.loads(stitch_path.read_text(encoding="utf-8"))
            job = saved["jobs"]["Event_7_stitch"]
            self.assertIn("intro", job["slots"])
            self.assertIn("resolution", job["slots"])

    def test_idempotent_second_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            event_dir = root / "Production" / "Event_7"
            event_dir.mkdir(parents=True)
            stitch_path = root / "Production" / "tools" / "stitch_editor_state.json"
            stitch_path.parent.mkdir(parents=True)
            stitch_path.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")

            from production_server import StitchEditorState  # noqa: PLC0415

            store = StitchEditorState(stitch_path)
            app = MagicMock()
            app.event_dir = event_dir
            app.stitch_state = store
            app._event_stitch_state = store
            h = stitch_bootstrap_shim_for_app(app)

            ensure_event_stitch_job_registered(h, "Event_7", hydrate_from_disk=False)
            boot2 = ensure_event_stitch_job_registered(
                h,
                "Event_7",
                hydrate_from_disk=False,
            )
            self.assertFalse(boot2.get("created"))
            self.assertFalse(boot2.get("changed"))

    def test_skips_non_numbered_event(self) -> None:
        h = MagicMock()
        boot = ensure_event_stitch_job_registered(h, "Event_Oliver", hydrate_from_disk=False)
        self.assertTrue(boot.get("skipped"))


class LoadJobBootstrapSourceGuards(unittest.TestCase):
    def test_load_job_bootstraps_event_job_without_disk_hydrate(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def handle_stitch_load_job", 1)[1].split(
            "\ndef handle_stitch_serve_module_final", 1,
        )[0]
        self.assertIn("ensure_event_stitch_job_registered", block)
        self.assertIn("hydrate_from_disk=False", block)
        self.assertNotIn(
            "hydrate_stitch_canonical_slots_from_disk(h, state, event_id)",
            block,
        )


class EventCreateBootstrapSourceGuards(unittest.TestCase):
    def test_event_create_registers_stitch_job(self) -> None:
        from server_handlers import event_video as ev

        src = Path(ev.__file__).read_text(encoding="utf-8")
        self.assertIn(EVENT_STITCH_JOB_BOOTSTRAP_V1, src)
        self.assertIn("ensure_event_stitch_job_registered", src)


if __name__ == "__main__":
    unittest.main()
