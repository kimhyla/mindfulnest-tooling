#!/usr/bin/env python3
"""STITCH_CACHE_BUILD_LOCK_V1 + STITCH_PREVIEW_NORMALIZE_V1 — category durability tests."""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))

from credentials_lib.stitch_cache_build import (  # noqa: E402
    run_stitch_cache_build,
    stitch_cache_build_lock,
)


class StitchCacheBuildLockTests(unittest.TestCase):
    def test_run_stitch_cache_build_single_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            out = cache_dir / "artifact.bin"
            builds = {"n": 0}
            lock = threading.Lock()

            def ready() -> bool:
                return out.is_file()

            def build() -> None:
                with lock:
                    builds["n"] += 1
                out.write_bytes(b"ok")

            threads = [
                threading.Thread(
                    target=run_stitch_cache_build,
                    args=(cache_dir,),
                    kwargs={"ready": ready, "build": build},
                )
                for _ in range(6)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
                self.assertFalse(t.is_alive(), "thread hung in run_stitch_cache_build")

            self.assertTrue(out.is_file())
            self.assertEqual(builds["n"], 1, "exactly one builder despite concurrent waiters")

    def test_run_stitch_cache_build_waits_for_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            out = cache_dir / "peer.bin"
            peer_started = threading.Event()
            peer_release = threading.Event()

            def ready() -> bool:
                return out.is_file()

            def slow_build() -> None:
                peer_started.set()
                peer_release.wait(timeout=5)
                out.write_bytes(b"peer")

            def waiter_build() -> None:
                out.write_bytes(b"waiter-should-not-run")

            t_peer = threading.Thread(
                target=run_stitch_cache_build,
                args=(cache_dir,),
                kwargs={"ready": ready, "build": slow_build},
            )
            t_peer.start()
            self.assertTrue(peer_started.wait(timeout=5))

            # Hold lock so waiter cannot acquire until peer finishes.
            with stitch_cache_build_lock(cache_dir):
                pass  # release immediately — peer holds lock during slow_build body

            t_wait = threading.Thread(
                target=run_stitch_cache_build,
                args=(cache_dir,),
                kwargs={"ready": ready, "build": waiter_build},
                daemon=True,
            )
            t_wait.start()
            peer_release.set()
            t_peer.join(timeout=10)
            t_wait.join(timeout=10)
            self.assertEqual(out.read_bytes(), b"peer")

    def test_production_server_normalize_uses_cache_lock(self):
        src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
        block = src.split("def _stitch_normalize_slot", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("run_stitch_cache_build", block)
        self.assertIn("preview_only", block)
        self.assertIn("_pv", block)
        self.assertIn("normalize_for_stitch_preview", block)

    def test_production_server_mix_uses_cache_lock(self):
        src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
        block = src.split("def _stitch_mix_slot_audio", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("run_stitch_cache_build", block)
        self.assertIn("atomic_ffmpeg_output", block)

    def test_preview_normalize_function_and_pipeline_flag(self):
        ff = (TOOLS / "credentials_lib" / "ffmpeg_stitch.py").read_text(encoding="utf-8")
        self.assertIn("def normalize_for_stitch_preview", ff)
        self.assertIn("STITCH_PREVIEW_NORMALIZE_V1", ff)
        pipe = (TOOLS / "production_server.py").read_text(encoding="utf-8")
        build_block = pipe.split("def _stitch_build_pipeline", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("preview_only = bool(body.get(\"slot_preview\"))", build_block)
        self.assertIn("preview_only=preview_only", build_block)
        self.assertIn("run_stitch_cache_build", build_block)

    def test_stitch_editor_waveform_mix_waits_on_cache_lock(self):
        src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def _mix_stitch_waveform_audio", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("run_stitch_cache_build", block)

    def test_client_mux_rebuild_queue_markers(self):
        hydrate = (
            TOOLS / "storyboard-v2" / "src" / "utils" / "stitchJobMediaHydrate.ts"
        ).read_text(encoding="utf-8")
        tab = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
            encoding="utf-8",
        )
        self.assertIn("selectSlotsForMuxRebuild", hydrate)
        self.assertIn("STITCH_MUX_REBUILD_QUEUE_V1", hydrate)
        self.assertIn("selectSlotsForMuxRebuild", tab)
        self.assertIn("scheduledMuxSlotsRef", tab)
        self.assertIn("data-stitch-mux-rebuild-queue", tab)


class StitchCacheBuildLockUnitTests(unittest.TestCase):
    def test_in_process_threads_block_on_thread_lock(self):
        """Second thread waits on threading.Lock; no concurrent build in one process."""
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            order: list[str] = []
            release = threading.Event()

            def holder() -> None:
                with stitch_cache_build_lock(cache_dir):
                    order.append("hold")
                    release.wait(timeout=5)

            def waiter() -> None:
                with stitch_cache_build_lock(cache_dir):
                    order.append("waiter")

            t1 = threading.Thread(target=holder, daemon=True)
            t1.start()
            deadline = time.monotonic() + 5
            while "hold" not in order and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(order, ["hold"])
            t2 = threading.Thread(target=waiter, daemon=True)
            t2.start()
            time.sleep(0.15)
            self.assertEqual(order, ["hold"], "waiter must block until holder releases")
            release.set()
            t1.join(timeout=5)
            t2.join(timeout=5)
            self.assertEqual(order, ["hold", "waiter"])


if __name__ == "__main__":
    unittest.main()
