#!/usr/bin/env python3
"""Tier 1B (April 18 2026) — timeout->failed edge + late-success recovery tests.

Covers the LDs:
  - PHASE_1_TIMEOUT_TO_FAILED_PER_VENDOR_THRESHOLDS
  - STALE_TIMEOUT_RECOVERY_VIA_ARTIFACT_CHECK
  - LATE_SUCCESS_IDEMPOTENCY_GUARD_NEVER_CLOBBER_FAILED

Philosophy: tests talk to the real PollingThread / StateManager. They don't
start a TCP server (would flake); instead they construct a PollingThread
directly and call its internal methods — this is closer than import-and-call
to what the running server actually does because it still exercises the
real atomic mutate_state + lock + file IO path.

signal.alarm(30) is used to prevent hangs.
"""
from __future__ import annotations
import json
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
# Directus lock is module-level; don't hit the network in tests.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"
# Keep T1 enabled for these tests (explicit — don't rely on default).
os.environ.pop("MINDFULNEST_WRITE_PATH", None)
os.environ["MINDFULNEST_T1_ENABLED"] = "1"

import production_server as PS  # noqa: E402


def _alarm(sec: int = 30):
    """Arm a SIGALRM to prevent hangs on test."""
    try:
        signal.alarm(sec)
    except (AttributeError, ValueError):
        pass  # Windows — no SIGALRM


def _disarm_alarm():
    try:
        signal.alarm(0)
    except (AttributeError, ValueError):
        pass


class _FakeWaveSpeedClient:
    """Minimal stand-in so PollingThread can be constructed without secrets.
    None of the Tier 1B tests actually exercise poll/download — they stop
    short of the network-ish layer by invoking _pending_tasks and
    _download_and_mark_completed with pre-set state."""
    api_key = "FAKE"

    def poll(self, task_id):
        return {"status": "processing"}

    def download(self, url, dest):
        # Never called in these tests — they seed artifacts directly
        raise AssertionError("FakeWaveSpeedClient.download should not be called")


def _build_state_manager(tmp_path: Path) -> PS.StateManager:
    event_dir = tmp_path / "Event_TEST"
    event_dir.mkdir(parents=True, exist_ok=True)
    return PS.StateManager(event_dir, "M1E1_T1B_TEST")


def _seed_beat_with_polling_option(
    sm: PS.StateManager,
    beat_id: str,
    *,
    source: str,
    submitted_at_epoch: float,
    task_id: str = "FAKE-TASK-123",
):
    # P5 migration (2026-05-19): poller _pending_tasks walks v3 partitions
    # via _iter_v3_beats — legacy top-level state["beats"] returns 0 tasks.
    # Seed into videos.intro.beats AND ensure display_order includes beat_id
    # so DISPLAY_ORDER_STRICT_V2 prune (mutate_state line 1338-1347) doesn't
    # delete the beat we just seeded.
    def seed(state):
        partition = state.setdefault("videos", {}).setdefault("intro", {})
        beats = partition.setdefault("beats", {})
        beats[beat_id] = {
            "phase_1": {
                "status": "polling",
                "options": [
                    {
                        "task_id": task_id,
                        "status": "polling",
                        "file": None,
                        "submitted_at": "2026-04-18T00:00:00+00:00",
                        "submitted_at_epoch": submitted_at_epoch,
                        "source": source,
                        "retries": 0,
                        "last_error": None,
                    }
                ],
                "selected_option": None,
            },
        }
        do = partition.setdefault("display_order", [])
        if beat_id not in do:
            do.append(beat_id)
        return True
    sm.mutate_state(seed)


class TestTier1BStaleTimeout(unittest.TestCase):

    def setUp(self):
        _alarm(30)
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="tier1b_t_"))
        self.sm = _build_state_manager(self.tmp_dir)
        import threading
        self.stop_event = threading.Event()
        self.poller = PS.PollingThread(
            self.sm, _FakeWaveSpeedClient(), self.stop_event,
        )

    def tearDown(self):
        _disarm_alarm()
        self.stop_event.set()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # --- Test 1: stale Kling option, no artifact → failed -------------------
    def test_stale_kling_no_artifact_flips_to_failed(self):
        beat_id = "beat_01"
        # 20 min ago — exceeds Kling 15-min threshold
        stale_epoch = time.time() - 20 * 60
        _seed_beat_with_polling_option(
            self.sm, beat_id, source="kling", submitted_at_epoch=stale_epoch,
        )
        # _pending_tasks should detect the stale option, invoke the recovery
        # helper, which (no artifact) flips to failed. Returned list excludes
        # the stale option (it's no longer ready to poll).
        pending = self.poller._pending_tasks()
        self.assertEqual(
            [bid for (bid, _i, _o) in pending], [],
            "stale option must NOT be returned for polling"
        )
        st = self.sm.read_state()
        opt = st["videos"]["intro"]["beats"][beat_id]["phase_1"]["options"][0]
        self.assertEqual(opt["status"], "failed",
                         f"expected status=failed, got {opt.get('status')}")
        self.assertEqual(opt["last_error"], "stale_timeout")
        self.assertTrue(opt.get("stale_timeout_failed"))
        self.assertEqual(opt.get("stale_timeout_threshold_sec"), 900)
        self.assertEqual(opt.get("stale_timeout_source"), "kling")
        # phase_1 rollup should become "partial" (single failed, no polling)
        self.assertEqual(st["videos"]["intro"]["beats"][beat_id]["phase_1"]["status"], "partial")

    # --- Test 2: stale Kling option WITH on-disk artifact → succeeded_late ---
    def test_stale_with_artifact_recovers_as_succeeded_late(self):
        beat_id = "beat_02"
        stale_epoch = time.time() - 20 * 60  # 20 min ago
        _seed_beat_with_polling_option(
            self.sm, beat_id, source="kling", submitted_at_epoch=stale_epoch,
        )
        # Create a fake artifact file with mtime > submitted_at_epoch
        artifact = self.sm.clips_dir / f"{beat_id}_option_1.mp4"
        artifact.write_bytes(b"FAKE_MP4_CONTENT" * 100)
        # mtime is "now" which is > stale_epoch
        self.assertGreater(artifact.stat().st_mtime, stale_epoch)

        pending = self.poller._pending_tasks()
        self.assertEqual(pending, [], "stale recovered option must not re-poll")
        st = self.sm.read_state()
        opt = st["videos"]["intro"]["beats"][beat_id]["phase_1"]["options"][0]
        self.assertEqual(opt["status"], "succeeded_late",
                         f"expected status=succeeded_late, got {opt.get('status')}")
        self.assertTrue(opt.get("resurrected"))
        self.assertTrue(opt.get("stale_timeout_recovered"))
        self.assertEqual(opt.get("file"), f"{beat_id}_option_1.mp4")
        self.assertGreater(opt.get("size_bytes", 0), 0)
        # phase_1 rollup should be "completed" (only option, now terminal-success)
        self.assertEqual(st["videos"]["intro"]["beats"][beat_id]["phase_1"]["status"], "completed")

    # --- Test 3: late success on previously-failed option → resurrected -----
    def test_late_callback_on_failed_slot_transitions_to_completed(self):
        beat_id = "beat_03"
        # P5 migration: seed into v3 partition shape + display_order
        def seed(state):
            partition = state.setdefault("videos", {}).setdefault("intro", {})
            partition.setdefault("beats", {})[beat_id] = {
                "phase_1": {
                    "status": "partial",
                    "options": [
                        {
                            "task_id": "TASK-LATE-ABC",
                            "status": "failed",
                            "last_error": "stale_timeout",
                            "stale_timeout_failed": True,
                            "file": None,
                            "submitted_at": "2026-04-18T00:00:00+00:00",
                            "submitted_at_epoch": time.time() - 20 * 60,
                            "source": "kling",
                            "retries": 0,
                        }
                    ],
                    "selected_option": None,
                },
            }
            do = partition.setdefault("display_order", [])
            if beat_id not in do:
                do.append(beat_id)
            return True
        self.sm.mutate_state(seed)

        # Simulate the late vendor callback arriving — put the artifact on
        # disk BEFORE invoking _download_and_mark_completed (matches the
        # dest.exists() branch where we skip re-download).
        artifact = self.sm.clips_dir / f"{beat_id}_option_1.mp4"
        artifact.write_bytes(b"LATE_MP4" * 100)

        ok = self.poller._download_and_mark_completed(
            beat_id, 0, "TASK-LATE-ABC", "https://fake.example/out.mp4",
            source="late_callback_test",
        )
        self.assertTrue(ok, "_download_and_mark_completed should return True")

        st = self.sm.read_state()
        opt = st["videos"]["intro"]["beats"][beat_id]["phase_1"]["options"][0]
        self.assertEqual(opt["status"], "completed",
                         f"expected status=completed, got {opt.get('status')}")
        self.assertEqual(opt.get("resurrected_from"), "failed")
        self.assertNotIn("last_error", opt, "last_error should be cleared on resurrection")
        self.assertEqual(opt.get("file"), f"{beat_id}_option_1.mp4")

    # --- Test 4: non-stale option still returned for polling ----------------
    def test_fresh_option_is_still_polled(self):
        beat_id = "beat_04"
        # Submitted 30s ago — well under 15min threshold
        fresh_epoch = time.time() - 30
        _seed_beat_with_polling_option(
            self.sm, beat_id, source="kling", submitted_at_epoch=fresh_epoch,
        )
        pending = self.poller._pending_tasks()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0][0], beat_id)
        # Status unchanged
        st = self.sm.read_state()
        self.assertEqual(st["videos"]["intro"]["beats"][beat_id]["phase_1"]["options"][0]["status"],
                         "polling")

    # --- Test 5: feature-flag disables T1 entirely --------------------------
    def test_feature_flag_disabled_skips_timeout_check(self):
        beat_id = "beat_05"
        stale_epoch = time.time() - 20 * 60
        _seed_beat_with_polling_option(
            self.sm, beat_id, source="kling", submitted_at_epoch=stale_epoch,
        )
        os.environ["MINDFULNEST_T1_ENABLED"] = "0"
        try:
            pending = self.poller._pending_tasks()
            # With T1 off, the stale option is still returned for polling.
            self.assertEqual(len(pending), 1)
            # Status should still be 'polling' — no T1 mutation happened.
            st = self.sm.read_state()
            self.assertEqual(
                st["videos"]["intro"]["beats"][beat_id]["phase_1"]["options"][0]["status"],
                "polling",
            )
        finally:
            os.environ["MINDFULNEST_T1_ENABLED"] = "1"

    # --- Test 6: per-vendor threshold — bytedance_lipsync uses 5min ---------
    def test_bytedance_lipsync_threshold_is_300s(self):
        beat_id = "beat_06"
        # 6 min ago — exceeds bytedance 5min threshold but NOT Kling 15min.
        # Ensures we look up the right per-vendor row.
        past_epoch = time.time() - 6 * 60
        _seed_beat_with_polling_option(
            self.sm, beat_id, source="bytedance_lipsync",
            submitted_at_epoch=past_epoch,
        )
        pending = self.poller._pending_tasks()
        self.assertEqual(pending, [])
        st = self.sm.read_state()
        opt = st["videos"]["intro"]["beats"][beat_id]["phase_1"]["options"][0]
        self.assertEqual(opt["status"], "failed")
        self.assertEqual(opt.get("stale_timeout_threshold_sec"), 300)
        self.assertEqual(opt.get("stale_timeout_source"), "bytedance_lipsync")

    # --- Test 7: artifact with mtime BEFORE submission is NOT claimed -------
    def test_old_artifact_does_not_claim_as_late_success(self):
        beat_id = "beat_07"
        submitted_epoch = time.time() - 20 * 60
        _seed_beat_with_polling_option(
            self.sm, beat_id, source="kling",
            submitted_at_epoch=submitted_epoch,
        )
        artifact = self.sm.clips_dir / f"{beat_id}_option_1.mp4"
        artifact.write_bytes(b"OLD_PRIOR_RUN" * 100)
        # Backdate the artifact mtime to BEFORE submission (30 min ago)
        old_mtime = time.time() - 30 * 60
        os.utime(artifact, (old_mtime, old_mtime))

        pending = self.poller._pending_tasks()
        self.assertEqual(pending, [])
        st = self.sm.read_state()
        opt = st["videos"]["intro"]["beats"][beat_id]["phase_1"]["options"][0]
        # Must NOT have been claimed as late success — artifact predates submit
        self.assertEqual(opt["status"], "failed",
                         "artifact older than submission should not resurrect")


if __name__ == "__main__":
    unittest.main(verbosity=2)
