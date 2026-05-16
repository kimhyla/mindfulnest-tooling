#!/usr/bin/env python3
"""F-LIB-DELETE-SOURCES-001 — _handle_cr_library_delete tier-path support.

Origin incident (2026-05-16 ~12:50 PM PT, Kim browser toast):

    Delete failed: key 'crop_bg_arc1_event2_pre_beat_10_1777255953'
    not found in sources/

The library at /api/cr/library returns FOUR tiers (per
_handle_cr_library):
    - source     (BG_STILLS_DIR + BG_STILLS_DIR/sources/)
    - cropped    (BG_STILLS_DIR/crops/)
    - character_master (Character_Assets/)

The delete handler `_handle_cr_library_delete` previously globbed in
``sources/`` ONLY (line 6754) — crop-tier items emitted from the library
had no delete path, so the user got a confusing 404 referencing the
wrong directory.

Fix (matches client-side body shape — LibraryPanel onDelete already
sends `abs_path`, and the body-key contract baseline already records
``CLIENT_EXTRA|cr_library_delete|/api/cr/library/delete|abs_path``):

  1. If `abs_path` is supplied + realpath-containment confirms it lives
     in one of the legitimate library tier dirs (sources/, crops/),
     use it as the canonical target.
  2. Otherwise, fall back to multi-tier glob: sources/ first, then
     crops/. Character_Assets/ is reference-only and NEVER deleted by
     this handler (returns 403 with explicit reason).
  3. If filesystem file is missing at unlink time (race / stale Dropbox
     sync after a prior delete attempt), log a warning + audit row but
     return 200 — the user-intent ("remove this library entry") is
     satisfied because the Directus row (if any) was already removed.
     Rule 19 compliance: no silent error path. The warning is loud,
     visible in prod_activity_log, with `details.warning` populated.

Tests (5) — all run offline, hermetic:

  1. test_F_LIB_DELETE_SOURCES_001_crop_tier_delete_succeeds
     - RED pre-fix / GREEN post-fix.
     - Key matches a file in crops/; handler must succeed (200) and
       physically remove the crop file.

  2. test_source_tier_delete_still_works
     - Back-compat: pre-fix path for source-tier keys must still pass.

  3. test_abs_path_canonical_target_used_when_supplied
     - When client supplies abs_path, server uses it (skips glob).
     - abs_path must pass realpath-containment to the tier dirs.

  4. test_abs_path_outside_tier_dirs_rejected
     - abs_path = /etc/passwd → 403 (path outside library tiers).

  5. test_missing_file_soft_success_with_audit
     - File gone at unlink time → 200 + `details.warning` in response
       (already-deleted idempotent; Rule 19 audit-visible).

Run directly:
    python3 Production/tools/tests/test_handle_cr_library_delete_sources_path.py

Or via pytest:
    python3 -m pytest \
        Production/tools/tests/test_handle_cr_library_delete_sources_path.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

# sys.path setup must run BEFORE importing production_server. Same pattern as
# test_handle_beat_regenerate_audio_body_key.py and test_scope_router_scrambled.py.
_THIS_FILE = Path(__file__).resolve()
_PRODUCTION_DIR = _THIS_FILE.parents[2]
_PRODUCTION_DIR_S = str(_PRODUCTION_DIR)
_TOOLS_DIR_S = str(_PRODUCTION_DIR / "tools")
if _PRODUCTION_DIR_S not in sys.path:
    sys.path.insert(0, _PRODUCTION_DIR_S)
if _TOOLS_DIR_S not in sys.path:
    sys.path.append(_TOOLS_DIR_S)
os.environ.setdefault("PRODUCTION_SERVER_SINGLE_MACHINE", "1")

import production_server as _ps  # noqa: E402


_PRISTINE_STATE = (
    _PRODUCTION_DIR / "Event_e2e_fixture" / ".pristine" / "production_state.json"
)


class _FakeBGModule:
    """Stand-in for `beat_generator` exposing BG_STILLS_DIR pointing at a
    tmpfs project root that has a parallel sources/, crops/, and
    Character_Assets/ layout."""

    def __init__(self, stills_dir: str):
        self.BG_STILLS_DIR = stills_dir


class LibraryDeleteTierPathTests(unittest.TestCase):
    """F-LIB-DELETE-SOURCES-001 — multi-tier delete + abs_path canonical."""

    @classmethod
    def setUpClass(cls):
        if not _PRISTINE_STATE.is_file():
            raise unittest.SkipTest(
                f"Event_e2e_fixture pristine state not found at {_PRISTINE_STATE}"
            )

    def setUp(self):
        # tmpfs project root that contains beat_generator_stills/{sources,crops}
        # AND Character_Assets/. Server's realpath-containment check against
        # DROPBOX_ROOT (project root) is monkey-patched to point here.
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)

        # Project tree mirror
        self.project_root = tmp / "project"
        self.project_root.mkdir()
        self.stills_dir = self.project_root / "Production" / "beat_generator_stills"
        (self.stills_dir / "sources").mkdir(parents=True)
        (self.stills_dir / "crops").mkdir(parents=True)
        (self.project_root / "Production" / "Character_Assets").mkdir(parents=True)

        # Seed fixture files
        self.source_path = self.stills_dir / "sources" / "source_test_image.png"
        self.source_path.write_bytes(b"\x89PNG\r\n\x1a\nfakedata")
        self.crop_path = self.stills_dir / "crops" / (
            "crop_bg_arc1_event2_pre_beat_10_1777255953.webp"
        )
        self.crop_path.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 fakedata")

        # Monkey-patch DROPBOX_ROOT to project_root for realpath-containment
        self._orig_dropbox_root = _ps.DROPBOX_ROOT
        _ps.DROPBOX_ROOT = self.project_root

        # Monkey-patch _BG_MODULE so _bg_module() returns the fake
        self._orig_bg_module = _ps._BG_MODULE
        _ps._BG_MODULE = _FakeBGModule(str(self.stills_dir))

        # Per-test tmpfs event_dir built from pristine state (same as
        # test_handle_beat_regenerate_audio_body_key.py pattern).
        self.tmp_event_dir = tmp / "Event_e2e_fixture_target"
        self.tmp_event_dir.mkdir()
        with open(_PRISTINE_STATE, "r", encoding="utf-8") as f:
            state = json.load(f)
        state["event_id"] = "Event_e2e_fixture_target"
        (self.tmp_event_dir / "production_state.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8",
        )
        (self.tmp_event_dir / "storyboard_v59_prod.html").write_text(
            "<html></html>", encoding="utf-8",
        )

        # Shadow DirectusAdminClient so handler skips network calls.
        # The handler imports `from lib.directus_admin_client import
        # DirectusAdminClient` lazily inside the function body.
        fake_lib_mod = types.ModuleType("lib.directus_admin_client")

        class _FakeClient:
            def get_items(self, *_a, **_k):
                return []  # not referenced — handler skips force-delete branch

            def delete_item(self, *_a, **_k):
                return None

        fake_lib_mod.DirectusAdminClient = _FakeClient
        self._orig_lib_mod = sys.modules.get("lib.directus_admin_client")
        sys.modules["lib.directus_admin_client"] = fake_lib_mod

        # Shadow `try_post_or_queue` so the activity_log write is a no-op
        fake_directus_mod = types.ModuleType("lib.directus")
        fake_directus_mod.try_post_or_queue = lambda *_a, **_k: {"ok": True}
        self._orig_directus_mod = sys.modules.get("lib.directus")
        sys.modules["lib.directus"] = fake_directus_mod

    def tearDown(self):
        _ps.DROPBOX_ROOT = self._orig_dropbox_root
        _ps._BG_MODULE = self._orig_bg_module
        if self._orig_lib_mod is None:
            sys.modules.pop("lib.directus_admin_client", None)
        else:
            sys.modules["lib.directus_admin_client"] = self._orig_lib_mod
        if self._orig_directus_mod is None:
            sys.modules.pop("lib.directus", None)
        else:
            sys.modules["lib.directus"] = self._orig_directus_mod

    def _build_handler(self):
        """Build a ProductionHandler stub bound to the tmpfs event_dir.
        Mirrors test_handle_beat_regenerate_audio_body_key.py."""
        sm = _ps.StateManager(self.tmp_event_dir, "Event_e2e_fixture_target")

        class _App:
            def __init__(_self):
                _self.state = sm
                _self.event_dir = self.tmp_event_dir
                _self.event_id = "Event_e2e_fixture_target"
                _self.storyboard_path = (
                    self.tmp_event_dir / "storyboard_v59_prod.html"
                )
                _self.source_event_dir = None
                _self.event_generation = 0

        class _Server:
            def __init__(_self, _app):
                _self.app = _app

        h = _ps.ProductionHandler.__new__(_ps.ProductionHandler)
        h.server = _Server(_App())
        captured = {"status": None, "payload": None}

        def _capture(status, payload, _c=captured):
            _c["status"] = status
            _c["payload"] = payload

        h._send_json = _capture
        h.path = "/api/cr/library/delete"
        h.command = "POST"
        return h, captured

    # ------------------------------------------------------------------
    # F-LIB-DELETE-SOURCES-001 — RED pre-fix / GREEN post-fix
    # ------------------------------------------------------------------
    def test_F_LIB_DELETE_SOURCES_001_crop_tier_delete_succeeds(self):
        """Crop-tier key from the library MUST delete successfully.

        Pre-fix: handler globs sources/ only → 404 with payload
        ``{"error": "key '<key>' not found in sources/"}``. This is
        Kim's 2026-05-16 reproduction.

        Post-fix: handler also globs crops/ (and respects abs_path) →
        200 + crop file physically removed.
        """
        h, captured = self._build_handler()
        body = {
            "scope_event_id": "Event_e2e_fixture_target",
            "scope_video_role": "intro",
            "key": "crop_bg_arc1_event2_pre_beat_10_1777255953",
        }
        h._handle_cr_library_delete(body)

        # Pre-fix: status=404, payload mentions "not found in sources/"
        is_kim_404 = (
            captured["status"] == 404
            and isinstance(captured["payload"], dict)
            and "not found in sources" in str(captured["payload"].get("error", ""))
        )
        self.assertFalse(
            is_kim_404,
            (
                f"F-LIB-DELETE-SOURCES-001: crop-tier delete must NOT 404 "
                f"with sources/-only error. Got status={captured['status']} "
                f"payload={captured['payload']!r}"
            ),
        )
        self.assertEqual(
            captured["status"], 200,
            (
                f"Post-fix expectation: crop-tier delete returns 200. "
                f"Got status={captured['status']} payload={captured['payload']!r}"
            ),
        )
        self.assertEqual(captured["payload"].get("ok"), True)
        self.assertFalse(
            self.crop_path.exists(),
            f"Crop file should have been physically removed: {self.crop_path}",
        )

    # ------------------------------------------------------------------
    # Back-compat: source-tier still works
    # ------------------------------------------------------------------
    def test_source_tier_delete_still_works(self):
        """Back-compat: source-tier keys must continue to delete."""
        h, captured = self._build_handler()
        body = {
            "scope_event_id": "Event_e2e_fixture_target",
            "scope_video_role": "intro",
            "key": "source_test_image",
        }
        h._handle_cr_library_delete(body)
        self.assertEqual(
            captured["status"], 200,
            (
                f"Back-compat: source-tier delete must still succeed. "
                f"Got status={captured['status']} payload={captured['payload']!r}"
            ),
        )
        self.assertFalse(
            self.source_path.exists(),
            f"Source file should have been physically removed: {self.source_path}",
        )

    # ------------------------------------------------------------------
    # abs_path canonical target
    # ------------------------------------------------------------------
    def test_abs_path_canonical_target_used_when_supplied(self):
        """When client supplies abs_path that passes tier-dir containment,
        server uses it as the canonical target. Skips glob ambiguity."""
        h, captured = self._build_handler()
        body = {
            "scope_event_id": "Event_e2e_fixture_target",
            "scope_video_role": "intro",
            "key": "crop_bg_arc1_event2_pre_beat_10_1777255953",
            "abs_path": str(self.crop_path),
        }
        h._handle_cr_library_delete(body)
        self.assertEqual(
            captured["status"], 200,
            (
                f"abs_path canonical target must succeed. "
                f"Got status={captured['status']} payload={captured['payload']!r}"
            ),
        )
        self.assertFalse(
            self.crop_path.exists(),
            "Crop file should have been physically removed via abs_path.",
        )

    # ------------------------------------------------------------------
    # abs_path outside tier dirs rejected
    # ------------------------------------------------------------------
    def test_abs_path_outside_tier_dirs_rejected(self):
        """abs_path = /etc/passwd → 403. Library delete must never touch
        files outside the registered tier dirs (sources/, crops/)."""
        h, captured = self._build_handler()
        body = {
            "scope_event_id": "Event_e2e_fixture_target",
            "scope_video_role": "intro",
            "key": "etc_passwd_attempt",
            "abs_path": "/etc/passwd",
        }
        h._handle_cr_library_delete(body)
        self.assertEqual(
            captured["status"], 403,
            (
                f"abs_path outside tier dirs must be 403. "
                f"Got status={captured['status']} payload={captured['payload']!r}"
            ),
        )

    # ------------------------------------------------------------------
    # Missing file → soft success with audit (graceful no-op)
    # ------------------------------------------------------------------
    def test_missing_file_soft_success_with_audit(self):
        """If the crop file is already gone at unlink time (race / stale
        Dropbox sync after prior delete attempt), handler returns 200 with
        a `warning` field in payload — user-intent satisfied, audit visible.

        Setup: supply a valid abs_path that points to a file we delete
        OUT-OF-BAND before the handler runs.
        """
        h, captured = self._build_handler()
        # Delete the crop file out-of-band to simulate race / stale sync
        self.crop_path.unlink()
        self.assertFalse(self.crop_path.exists())

        body = {
            "scope_event_id": "Event_e2e_fixture_target",
            "scope_video_role": "intro",
            "key": "crop_bg_arc1_event2_pre_beat_10_1777255953",
            "abs_path": str(self.crop_path),
        }
        h._handle_cr_library_delete(body)
        self.assertEqual(
            captured["status"], 200,
            (
                f"Missing-file soft success: status should be 200. "
                f"Got status={captured['status']} payload={captured['payload']!r}"
            ),
        )
        self.assertEqual(captured["payload"].get("ok"), True)
        self.assertIn(
            "warning", captured["payload"],
            (
                f"Missing-file soft success must include `warning` for audit. "
                f"Got payload={captured['payload']!r}"
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
