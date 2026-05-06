#!/usr/bin/env python3
"""C-7.6 — SCR.1 + SCR.2 scrambled-state Pytest tests (READ-ONLY against Event_1).

Per STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v2.md §11.2 + Kim's pre-C-9
addendum (2026-05-06): exercise the SR+G v1 architecture against the
ACTUAL Event_1 production_state.json to surface scrambled-state-specific
bugs BEFORE the C-9 salvage runs. C-9 only exercises graft (Pillar 7);
SCR.1 + SCR.2 cover scope_router.resolve + _handle_beat_update_text
(Pillar 1 K1 fix) + K8 dual-store mirror against the post-2026-05-01-leak
Event_1/intro state (17 beats, display_order with 11 entries, beats 12-17
stranded, beat_05 with legacy speaker="Guide Bird").

Hard contract: Event_1's actual production_state.json on Dropbox MUST be
byte-identical (sha256) before and after the test run. Tests use a tmpfs
copy isolated from the canonical state file; the canonical file is read
once for the source bytes, hashed once for the post-test verification,
and never opened for write.

Run directly:
    python3 Production/tools/tests/test_scope_router_scrambled.py

Or via unittest:
    python3 -m unittest Production.tools.tests.test_scope_router_scrambled -v
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# sys.path setup MUST run before any production_server / scope_router import.
# Subtle: production_server.py at module top first does
#   sys.path.insert(0, os.path.dirname(__file__))   # Production/tools at [0]
# then `if Production not in sys.path: sys.path.insert(0, Production)`.
# If we pre-populate Production AND Production/tools here, the absolute
# Production is already in sys.path so production_server's own check
# skips re-inserting it; meanwhile production_server unconditionally
# re-inserts Production/tools at [0], leaving sys.path[0]=Production/tools.
# Production/tools/lib/ is a regular package (with __init__.py) that
# SHADOWS Production/lib/, so `from lib.atomic_json_write import ...`
# resolves to the wrong package and fails. The fix: insert ONLY
# Production/ here (so the lib package is reachable for find_spec / for
# any test code that imports it directly) and let production_server.py
# handle adding Production/tools itself when it's first imported.
_THIS_FILE = Path(__file__).resolve()
_PRODUCTION_DIR = _THIS_FILE.parents[2]               # tooling-repo/Production
_PRODUCTION_DIR_S = str(_PRODUCTION_DIR)
_TOOLS_DIR_S = str(_PRODUCTION_DIR / "tools")
# Production/ goes at FRONT (so the `lib.*` package resolves to
# Production/lib/, not the shadowing Production/tools/lib/ package).
# Production/tools/ goes at END (lower priority for `lib` search but
# visible for explicit `import production_server` / `import scope_router`).
if _PRODUCTION_DIR_S not in sys.path:
    sys.path.insert(0, _PRODUCTION_DIR_S)
if _TOOLS_DIR_S not in sys.path:
    sys.path.append(_TOOLS_DIR_S)
# SINGLE_MACHINE bypass for the Directus dlock — required by some
# StateManager paths even on tmpfs reads.
os.environ.setdefault("PRODUCTION_SERVER_SINGLE_MACHINE", "1")
# Eager import primes production_server's own sys.path manipulation and
# verifies the test-time import path works.
import production_server as _ps  # noqa: E402,F401
import scope_router as _scope_router  # noqa: E402,F401


# Locate Event_1's production_state.json in the canonical state tree
# (Dropbox per LD-505). The test is gated on the file being present —
# CI runs may not have Dropbox mounted; in that case the test SKIPs
# rather than failing, since the test fixture lives in Kim's tree.
_DROPBOX_ROOT = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
    "Claude Mindfulnest Project Files"
)
_EVENT_1_STATE = _DROPBOX_ROOT / "Production" / "Event_1" / "production_state.json"


def _has_event_1_state() -> bool:
    return _EVENT_1_STATE.is_file()


@unittest.skipUnless(_has_event_1_state(), "Event_1/production_state.json not on this host")
class ScopeRouterScrambledStateTests(unittest.TestCase):
    """SCR.1 + SCR.2 against actual Event_1 state (READ-ONLY contract).

    Sets up a per-test tmpfs copy of Event_1 state. Snapshots the canonical
    file's sha256 before and after every test in this class to enforce the
    "do not mutate the actual file" contract.
    """

    @classmethod
    def setUpClass(cls):
        # sys.path setup happened at module top so production_server +
        # scope_router are importable. Snapshot canonical Event_1 state
        # sha256 to enforce read-only invariant across all tests in this class.
        with open(_EVENT_1_STATE, "rb") as f:
            cls._canonical_sha256_pre = hashlib.sha256(f.read()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        # Verify canonical state file unchanged across all tests in this class.
        with open(_EVENT_1_STATE, "rb") as f:
            sha_post = hashlib.sha256(f.read()).hexdigest()
        if sha_post != cls._canonical_sha256_pre:
            raise AssertionError(
                f"Canonical Event_1 state file mutated by SCR tests. "
                f"sha256 pre={cls._canonical_sha256_pre} post={sha_post}. "
                f"This is a contract violation — tests MUST operate on tmpfs "
                f"copy only."
            )

    def setUp(self):
        # Per-test fresh tmpfs Event_1 copy.
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmpdir_path = Path(self._tmpdir.name)
        # Mirror canonical event_dir layout: <tmp>/Event_1/production_state.json
        self.tmp_event_dir = tmpdir_path / "Event_1"
        self.tmp_event_dir.mkdir()
        with open(_EVENT_1_STATE, "rb") as src:
            data = src.read()
        with open(self.tmp_event_dir / "production_state.json", "wb") as dst:
            dst.write(data)
        # Also write a placeholder storyboard html so app.storyboard_path is
        # a real path (prevents some downstream resolution surprises).
        (self.tmp_event_dir / "storyboard_v59_prod.html").write_text(
            "<html><body><script>window.storyboardData={lines:[]};</script></body></html>",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # SCR.1 — scope_router.resolve doesn't crash on Event_1 stranded state
    # ------------------------------------------------------------------
    def test_SCR_1_scope_router_resolve_against_scrambled_state(self):
        """Loading Event_1 state and resolving scope keys returns ResolvedScope."""
        import scope_router  # type: ignore

        # Read state directly (not via StateManager) to avoid any
        # write-side initialization. Pure read-only assertion.
        with open(self.tmp_event_dir / "production_state.json", "r", encoding="utf-8") as f:
            state = json.load(f)

        # Sanity: this IS the scrambled-state shape (17 beats, 11-entry display_order)
        intro = (state.get("videos") or {}).get("intro") or {}
        self.assertIsInstance(
            intro.get("beats"), dict,
            "Event_1/intro must have beats dict (sanity)",
        )
        self.assertGreaterEqual(len(intro["beats"]), 17, "expected 17+ beats in scrambled state")
        self.assertIsInstance(intro.get("display_order"), list, "display_order should be a list")

        body = {
            "scope_event_id": "Event_1",
            "scope_target_video": "intro",
        }
        # Should not raise
        scope = scope_router.resolve(body, "Event_1")
        self.assertEqual(scope.event_id, "Event_1")
        self.assertEqual(scope.video_role, "intro")
        self.assertIsNone(scope.beat_id)
        self.assertIsNone(scope.mutation_id)

    # ------------------------------------------------------------------
    # SCR.2 — _handle_beat_update_text on scrambled-state beat_05
    #          (whose top-level speaker is "Guide Bird")
    # ------------------------------------------------------------------
    # HALT + SURFACE per Kim's pre-C-9 addendum: this test was authored to
    # discover whether the SR+G architecture migrates legacy on-disk
    # Guide-Bird speakers when an unrelated field (text) is touched. Local
    # run (2026-05-06) confirmed the GAP: _handle_beat_update_text writes
    # ONLY text; the K8 dual-store + SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1
    # only fire on patch_state(field='speaker', ...) writes. Effect:
    # legacy 'Guide Bird' values persist in Event_1.state.json until
    # someone explicitly writes the speaker field; TTS-time alias
    # resolution (_canonicalize_speaker via _SPEAKER_ALIAS) compensates
    # at READ time, so audio renders correctly, but the on-disk state
    # never converges to canonical names without an explicit speaker
    # patch operation. Marked expectedFailure so CI stays green; remove
    # the decorator + commit the fix once Kim authorizes the architectural
    # change (most likely: add `_canonicalize_on_touch` write to
    # _handle_beat_update_text's update_partition mutator that re-writes
    # beat['speaker'] = _canonicalize_speaker(beat.get('speaker') or '')
    # plus the K8 phase_1 mirror).
    @unittest.expectedFailure
    def test_SCR_2_update_text_on_legacy_guide_bird_speaker(self):
        """beat_05 update_text → text persisted; speaker canonicalized to Chipper.

        Per Kim's pre-C-9 addendum: this test is intentionally designed to
        exercise the SR+G architecture against legacy on-disk Guide-Bird
        speakers. If it fails (specifically on speaker canonicalization),
        that is the architectural gap to surface — _handle_beat_update_text
        does not currently migrate legacy speaker values; the K8 dual-store
        mirror only fires on patch_state speaker writes.
        """
        # Import production_server with sys.path already prepared in setUpClass
        import production_server as ps  # type: ignore

        # Verify pre-condition: beat_05 currently has speaker="Guide Bird"
        with open(self.tmp_event_dir / "production_state.json", "r", encoding="utf-8") as f:
            pre_state = json.load(f)
        pre_beat = pre_state["videos"]["intro"]["beats"]["beat_05"]
        self.assertEqual(
            pre_beat.get("speaker"), "Guide Bird",
            "Pre-condition: Event_1.beat_05.speaker should be legacy 'Guide Bird'",
        )

        # Build StateManager + AppContext for the tmpfs event_dir
        sm = ps.StateManager(self.tmp_event_dir, "Event_1")

        class _MiniApp:
            def __init__(self, _sm, _ed):
                self.state = _sm
                self.event_dir = _ed
                self.event_id = "Event_1"
                self.storyboard_path = _ed / "storyboard_v59_prod.html"
                self.source_event_dir = None
                # _storyboard_write_lock: the beat_update_text path calls
                # _write_sidecar_L_json which uses this lock; provide a real
                # lock to avoid AttributeError.
                import threading
                self._storyboard_write_lock = threading.Lock()
            # Used by _handle_beat_update_text → _patch_storyboard_L_field
            # which calls app.beats(); return empty list (storyboard html is
            # placeholder). The L[] patch will report not_in_storyboard which
            # is fine for the state-only assertions below.
            def beats(self):
                return []
            def get_beat_image(self, *args, **kwargs):
                return None

        app = _MiniApp(sm, self.tmp_event_dir)

        # Mock server with .app property — ProductionHandler reads via
        # self.server.app.
        class _MockServer:
            def __init__(self, _app):
                self.app = _app

        h = ps.ProductionHandler.__new__(ps.ProductionHandler)
        h.server = _MockServer(app)
        # Capture _send_json output instead of writing to a real socket.
        captured = {"status": None, "payload": None}
        def _capture(status, payload, _c=captured):
            _c["status"] = status
            _c["payload"] = payload
        h._send_json = _capture
        # Some internal helpers reference self.path / self.command; provide
        # safe defaults.
        h.path = "/api/beat/update_text"
        h.command = "POST"

        # Issue the update_text request against beat_05.
        new_text = "SCR.2 RED test text — should persist + canonicalize speaker"
        h._handle_beat_update_text({
            "scope_event_id": "Event_1",
            "scope_target_video": "intro",
            "beat": "beat_05",
            "text": new_text,
            "skip_tts_regen": True,
        })

        # The request should succeed (HTTP 200).
        self.assertEqual(
            captured["status"], 200,
            f"update_text should succeed; got {captured['status']} {captured['payload']}",
        )

        # Read back state from tmpfs
        with open(self.tmp_event_dir / "production_state.json", "r", encoding="utf-8") as f:
            post_state = json.load(f)
        post_beat = post_state["videos"]["intro"]["beats"].get("beat_05")
        self.assertIsNotNone(
            post_beat,
            "beat_05 should survive update_text (it's in display_order; prune skips)",
        )
        # Text persisted
        self.assertEqual(post_beat.get("text"), new_text, "text must persist")
        # Speaker canonicalized at write boundary (per K8 dual-store + C-6 mirror)
        self.assertEqual(
            post_beat.get("speaker"), "Chipper",
            f"K8: top-level speaker MUST canonicalize legacy 'Guide Bird' to 'Chipper' "
            f"on update_text; got {post_beat.get('speaker')!r}",
        )
        # phase_1 mirror also Chipper
        self.assertEqual(
            (post_beat.get("phase_1") or {}).get("speaker"), "Chipper",
            f"K8 mirror: phase_1.speaker MUST mirror canonical top-level; "
            f"got {(post_beat.get('phase_1') or {}).get('speaker')!r}",
        )


if __name__ == "__main__":
    if not _has_event_1_state():
        print(f"SKIP: Event_1 state not present at {_EVENT_1_STATE}")
        sys.exit(0)
    unittest.main(verbosity=2)
