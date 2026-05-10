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
# (Dropbox per LD-505). Tests are gated on either:
#   (a) the live state file exists with ≥17 beats (scrambled state still
#       on disk — pre-C-9b / pre-recovery), OR
#   (b) a pre-image backup under Event_1/.backups/state/ has ≥17 beats
#       (scrambled state preserved as forensic record post-recovery)
# CI runs may not have Dropbox mounted; in that case both predicates
# return None and the test SKIPs since the fixture lives in Kim's tree.
from Production.lib.paths import DROPBOX_ROOT as _DROPBOX_ROOT
_EVENT_1_STATE = _DROPBOX_ROOT / "Production" / "Event_1" / "production_state.json"
_EVENT_1_BACKUPS = _DROPBOX_ROOT / "Production" / "Event_1" / ".backups" / "state"


def _scrambled_event_1_state_path() -> Path | None:
    """Return a path to Event_1 state with ≥17 beats in intro, or None.

    Order of preference:
      1. Live state at Event_1/production_state.json (pre-recovery state)
      2. Latest pre-image backup at .backups/state/ (post-recovery)
    Returns None if neither has the scrambled-state shape (CI / no Dropbox /
    Event_1 already restored to a different shape).
    """
    if _EVENT_1_STATE.is_file():
        try:
            s = json.loads(_EVENT_1_STATE.read_text(encoding="utf-8"))
            beats = (((s.get("videos") or {}).get("intro") or {}).get("beats") or {})
            if len(beats) >= 17:
                return _EVENT_1_STATE
        except (OSError, json.JSONDecodeError):
            pass
    if _EVENT_1_BACKUPS.is_dir():
        # Newest first; preimage_pre_C9b_skip_*.json (post-skip canonical
        # record), preimage_pre_K4_*.json (C-0 defensive snapshot), or
        # any other timestamped backup written by mutate_video_state.
        candidates = sorted(
            _EVENT_1_BACKUPS.glob("preimage_pre_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in candidates:
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
                beats = (((s.get("videos") or {}).get("intro") or {}).get("beats") or {})
                if len(beats) >= 17:
                    return p
            except (OSError, json.JSONDecodeError):
                continue
    return None


def _has_event_1_state() -> bool:
    return _scrambled_event_1_state_path() is not None


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
        # scope_router are importable. Resolve the scrambled-state source
        # (live or pre-image) and snapshot its sha256 to enforce read-only
        # invariant across all tests in this class.
        cls._scrambled_state_path = _scrambled_event_1_state_path()
        assert cls._scrambled_state_path is not None, (
            "scrambled Event_1 state not reachable; setUpClass should not "
            "have been called (skipUnless guard would have skipped)"
        )
        with open(cls._scrambled_state_path, "rb") as f:
            cls._canonical_sha256_pre = hashlib.sha256(f.read()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        # Verify scrambled-state source file unchanged across all tests
        # in this class. Whether it's the live Event_1/production_state.json
        # OR a .backups/state/preimage_*.json, READ-ONLY contract holds:
        # tests operate on a per-test tmpfs copy.
        with open(cls._scrambled_state_path, "rb") as f:
            sha_post = hashlib.sha256(f.read()).hexdigest()
        if sha_post != cls._canonical_sha256_pre:
            raise AssertionError(
                f"Scrambled-state source file mutated by SCR tests. "
                f"path={cls._scrambled_state_path} "
                f"sha256 pre={cls._canonical_sha256_pre} post={sha_post}. "
                f"This is a contract violation — tests MUST operate on tmpfs "
                f"copy only."
            )

    def setUp(self):
        # Per-test fresh tmpfs Event_1 copy from the resolved scrambled-state
        # source (live state file OR pre-image backup; class-level resolved).
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmpdir_path = Path(self._tmpdir.name)
        # Mirror canonical event_dir layout: <tmp>/Event_1/production_state.json
        self.tmp_event_dir = tmpdir_path / "Event_1"
        self.tmp_event_dir.mkdir()
        with open(self._scrambled_state_path, "rb") as src:
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
    # SCR.2 — _handle_beat_update_text on scrambled-state beat_05 (whose
    # top-level speaker is "Guide Bird" in Event_1 disk-truth).
    #
    # As of Path A (Kim's authorization 2026-05-06):
    # _handle_beat_update_text now does canonicalize-on-touch — every
    # beat-touch re-canonicalizes the existing speaker via
    # _canonicalize_speaker and writes both the top-level + phase_1
    # mirror. Test now asserts GREEN: the LD claims at
    # SPEAKER_DUAL_STORE_DEPRECATION_V1 + SPEAKER_WRITE_BOUNDARY_
    # CANONICALIZATION_V1 hold at every beat-touchpoint, not just
    # patch_state(field='speaker', ...).
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


# ---------------------------------------------------------------------------
# SCR.3 — cross-event graft (Event_e2e_fixture only; NO real Event_1/2 data)
# ---------------------------------------------------------------------------
# Per spec §11.2 + Kim's pre-C-10 addendum 2026-05-06: SCR.3 fills the
# architectural test gap that the EXECUTE-path C-9 salvage would have
# covered. C-9 folded to C-9b SKIP because of disk-truth divergence on
# RR-1 (Event_1 beats had rendered Kling .mp4 files; spec §7.2 had only
# quantified lipsync_task_id=0 absence). SCR.3 reproduces the cross-event
# move semantics — including the --source-event server flag, KEEP-IDS,
# pre-image backups for both source AND target events, audit JSONL +
# Directus mirror, content fingerprint replay-safety, and HTTP 409
# rejection without the flag — entirely inside Production/Event_e2e_fixture/
# tree. No production state touched.
#
# Layout per test:
#   tmpfs/Event_e2e_fixture_source/  ← copied from real fixture pristine
#   tmpfs/Event_e2e_fixture_target/  ← built fresh (empty intro partition)
#   AppContext.source_event_dir = source  ← simulates --source-event flag
#   AppContext.event_dir         = target  ← server write-pin


class BeatGraftCrossEventTests(unittest.TestCase):
    """SCR.3 — cross-event graft via /api/beat/graft handler stub.

    Independent of Event_1 disk-truth: uses Event_e2e_fixture pristine as
    the source-event content + a freshly-built target event_dir. Runs in
    every CI environment (Dropbox not required).
    """

    @classmethod
    def setUpClass(cls):
        # Pristine fixture state path — sourced from tooling repo.
        cls._pristine_state = (
            _PRODUCTION_DIR / "Event_e2e_fixture" / ".pristine" / "production_state.json"
        )
        if not cls._pristine_state.is_file():
            raise unittest.SkipTest(
                f"Event_e2e_fixture pristine state not found at {cls._pristine_state}"
            )

    def setUp(self):
        # Per-test: build source (copy of pristine fixture) + empty target.
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)
        self.source_event_dir = tmp / "Event_e2e_fixture_source"
        self.target_event_dir = tmp / "Event_e2e_fixture_target"
        self.source_event_dir.mkdir()
        self.target_event_dir.mkdir()

        # Source: copy pristine state.
        with open(self._pristine_state, "rb") as f:
            src_bytes = f.read()
        (self.source_event_dir / "production_state.json").write_bytes(src_bytes)
        # placeholder storyboard html for source (graft handler doesn't read it
        # but app.storyboard_path may be referenced by other helpers)
        (self.source_event_dir / "storyboard_v59_prod.html").write_text(
            "<html></html>", encoding="utf-8"
        )

        # Target: minimal v3 state with empty intro partition.
        target_state = {
            "_module_version": "test",
            "event_id": "Event_e2e_fixture_target",
            "version": 0,
            "videos": {
                "intro": {
                    "video_role": "intro",
                    "video_label": None,
                    "beats": {},
                    "image_overrides": {},
                    "display_order": [],
                    "completed_mp4_path": None,
                },
            },
        }
        (self.target_event_dir / "production_state.json").write_text(
            json.dumps(target_state, indent=2), encoding="utf-8",
        )
        (self.target_event_dir / "storyboard_v59_prod.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    def _build_handler(self, *, with_source_event: bool):
        """Build a ProductionHandler stub bound to the target event_dir.

        with_source_event=True simulates `--source-event Production/Event_<src>`
        CLI flag; False simulates a vanilla server start.
        """
        sm = _ps.StateManager(self.target_event_dir, "Event_e2e_fixture_target")

        class _App:
            def __init__(_self):
                _self.state = sm
                _self.event_dir = self.target_event_dir
                _self.event_id = "Event_e2e_fixture_target"
                _self.storyboard_path = self.target_event_dir / "storyboard_v59_prod.html"
                _self.source_event_dir = (
                    self.source_event_dir if with_source_event else None
                )

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
        h.path = "/api/beat/graft"
        h.command = "POST"
        return h, captured

    # ------------------------------------------------------------------
    # SCR.3a — cross-event graft WITHOUT --source-event → HTTP 409
    # ------------------------------------------------------------------
    def test_SCR_3a_cross_event_without_source_flag_returns_409(self):
        h, captured = self._build_handler(with_source_event=False)
        body = {
            "source": {
                "event_id": "Event_e2e_fixture_source",
                "video_role": "intro",
                "beat_id": "beat_01",
            },
            "target": {
                "event_id": "Event_e2e_fixture_target",
                "video_role": "intro",
                "position": 0,
            },
            "mutation_id": "scr3a-test",
            "move": True,
        }
        h._handle_beat_graft(body)
        self.assertEqual(captured["status"], 409, f"got {captured['status']} {captured['payload']}")
        self.assertEqual(
            captured["payload"].get("error"),
            "cross_event_requires_explicit_source",
        )

    # ------------------------------------------------------------------
    # SCR.3b — cross-event graft WITH --source-event:
    #   move=true → source delete + target seed + pre-images for BOTH
    # ------------------------------------------------------------------
    def test_SCR_3b_cross_event_move_with_source_flag(self):
        # Pre: source has fixture's beat_01 (Tessa), target intro is empty.
        src_state = json.loads(
            (self.source_event_dir / "production_state.json").read_text(encoding="utf-8")
        )
        src_intro = src_state["videos"]["intro"]
        self.assertIn("beat_01", src_intro["beats"], "source pre-condition")
        src_beat_01_text = src_intro["beats"]["beat_01"]["text"]
        src_beat_01_speaker = src_intro["beats"]["beat_01"]["speaker"]

        h, captured = self._build_handler(with_source_event=True)
        body = {
            "source": {
                "event_id": "Event_e2e_fixture_source",
                "video_role": "intro",
                "beat_id": "beat_01",
            },
            "target": {
                "event_id": "Event_e2e_fixture_target",
                "video_role": "intro",
                "position": 0,
            },
            "mutation_id": "scr3b-test",
            "move": True,
        }
        h._handle_beat_graft(body)
        self.assertEqual(
            captured["status"], 200,
            f"cross-event move must succeed; got {captured['status']} {captured['payload']}",
        )
        payload = captured["payload"]
        self.assertEqual(payload.get("status"), "moved")
        self.assertEqual(payload.get("beat_id"), "beat_01")

        # Pre-image paths: BOTH source + target captured (cross-event)
        pre_image_paths = payload.get("pre_image_paths") or []
        self.assertEqual(
            len(pre_image_paths), 2,
            f"cross-event move must pre-image BOTH events; got {pre_image_paths}",
        )
        for p in pre_image_paths:
            self.assertTrue(Path(p).is_file(), f"pre-image path missing: {p}")

        # Source post-state: beat_01 deleted from source/intro
        src_post = json.loads(
            (self.source_event_dir / "production_state.json").read_text(encoding="utf-8")
        )
        src_intro_post = src_post["videos"]["intro"]
        self.assertNotIn(
            "beat_01", src_intro_post.get("beats", {}),
            "source.beats[beat_01] must be deleted post-move",
        )

        # Target post-state: beat_01 inserted with K8-canonical speaker
        tgt_post = json.loads(
            (self.target_event_dir / "production_state.json").read_text(encoding="utf-8")
        )
        tgt_intro_post = tgt_post["videos"]["intro"]
        self.assertIn(
            "beat_01", tgt_intro_post.get("beats", {}),
            "target.beats[beat_01] must be present post-move",
        )
        tgt_beat = tgt_intro_post["beats"]["beat_01"]
        self.assertEqual(tgt_beat["text"], src_beat_01_text, "text preserved")
        # Canonicalized speaker (Tessa stays Tessa; if source had been Guide Bird → Chipper)
        canon_expected = _scope_router._VALID_VIDEO_ROLES  # noqa: F841 (just to keep import live)
        self.assertEqual(
            tgt_beat["speaker"],
            _ps._canonicalize_speaker(src_beat_01_speaker or "") or "",
            "speaker canonicalized at graft write boundary (K8 + Path A)",
        )
        self.assertEqual(
            (tgt_beat.get("phase_1") or {}).get("speaker"), tgt_beat["speaker"],
            "K8 mirror — phase_1.speaker matches top-level after graft insert",
        )

    # ------------------------------------------------------------------
    # SCR.3c — replay safety: same mutation_id → status="dedup", no further mutation
    # ------------------------------------------------------------------
    def test_SCR_3c_dedup_replay_returns_cached_no_mutation(self):
        h, captured = self._build_handler(with_source_event=True)
        body = {
            "source": {
                "event_id": "Event_e2e_fixture_source",
                "video_role": "intro",
                "beat_id": "beat_02",
            },
            "target": {
                "event_id": "Event_e2e_fixture_target",
                "video_role": "intro",
                "position": 0,
            },
            "mutation_id": "scr3c-test",
            "move": False,  # COPY for this one
        }
        h._handle_beat_graft(body)
        self.assertEqual(captured["status"], 200)
        first_status = captured["payload"]["status"]
        self.assertEqual(first_status, "copied")
        # State after first call
        tgt_after_1 = json.loads(
            (self.target_event_dir / "production_state.json").read_text(encoding="utf-8")
        )

        # Replay same mutation_id
        h._handle_beat_graft(body)
        self.assertEqual(captured["status"], 200)
        self.assertEqual(
            captured["payload"]["status"], "dedup",
            "replay with same mutation_id must return status=dedup",
        )
        # State unchanged
        tgt_after_2 = json.loads(
            (self.target_event_dir / "production_state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            tgt_after_1, tgt_after_2,
            "dedup replay must NOT mutate state again",
        )


if __name__ == "__main__":
    # Run against whichever classes are discoverable.
    if not _has_event_1_state():
        print(f"NOTE: Event_1 state not present; only SCR.3 (cross-event fixture-only) will run.")
    unittest.main(verbosity=2)
