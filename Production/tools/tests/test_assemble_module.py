"""
Tests for Production/tools/assemble_module.py — the canonical 10-step Phase C
pipeline + Step 1.5 (audio parity + bitrate gate) + Steps 11-13 (finalization).

Per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.3 (Phase C) + §3.2 (R2 10-step
pipeline) + §3.4 (R4 Step 1.5) + ASSEMBLE_MODULE_CONTRACT.md (7 declared artifacts).

DS-2 strict TDD: this file lands RED in a commit BEFORE assemble_module.py exists.
GREEN commit follows with the implementation.

Run with:
    python3 -m unittest Production.tools.tests.test_assemble_module -v

Mock-based — patches subprocess.check_output / subprocess.run for ffprobe/ffmpeg,
patches Production.tools.registered_write.register_asset for Directus side effects.
Tests run offline; no real ffmpeg / ffprobe / network required.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO))

_FIXTURE_ROOT = tempfile.mkdtemp(prefix="phase_c_test_root_")
os.environ.setdefault("MN_DROPBOX_ROOT", _FIXTURE_ROOT)

from Production.tools import assemble_module  # noqa: E402  RED until GREEN commit


# ----------------------------------------------------------------------------
# Test helpers — build synthetic ffprobe JSON roots + synthetic MP4 atom blobs.
# ----------------------------------------------------------------------------

def _canonical_ffprobe_root(
    *,
    duration: str = "10.0",
    size: str = "1500000",
    bit_rate: str = "1200000",
    audio_bit_rate: str = "128000",
    width: int = 1280,
    height: int = 720,
    fps: str = "24/1",
    video_codec: str = "h264",
    video_profile: str = "High",
    pix_fmt: str = "yuv420p",
    audio_codec: str = "aac",
    sample_rate: str = "44100",
    channels: int = 1,
    include_audio: bool = True,
) -> dict:
    """Return an ffprobe -show_streams -show_format JSON root matching canonical spec."""
    streams = [
        {
            "codec_type": "video",
            "codec_name": video_codec,
            "profile": video_profile,
            "pix_fmt": pix_fmt,
            "width": width,
            "height": height,
            "r_frame_rate": fps,
            "avg_frame_rate": fps,
            "duration": duration,
        }
    ]
    if include_audio:
        streams.append(
            {
                "codec_type": "audio",
                "codec_name": audio_codec,
                "bit_rate": audio_bit_rate,
                "sample_rate": sample_rate,
                "channels": channels,
                "duration": duration,
            }
        )
    return {
        "streams": streams,
        "format": {
            "duration": duration,
            "size": size,
            "bit_rate": bit_rate,
        },
    }


def _write_mp4_atoms(path: Path, *, moov_first: bool = True) -> None:
    """Write a minimal MP4 with ftyp + (moov|mdat) atoms in chosen order.

    Each atom is `<4-byte big-endian size><4-byte type tag><payload>`. We don't
    parse the payload — Step 5 only walks atom headers.
    """

    def atom(tag: bytes, payload: bytes) -> bytes:
        size = 8 + len(payload)
        return struct.pack(">I", size) + tag + payload

    ftyp = atom(b"ftyp", b"isom" + b"\x00" * 4 + b"isomiso2avc1mp41")
    moov = atom(b"moov", b"\x00" * 64)
    mdat = atom(b"mdat", b"\x00" * 64)

    with open(path, "wb") as fh:
        fh.write(ftyp)
        if moov_first:
            fh.write(moov)
            fh.write(mdat)
        else:
            fh.write(mdat)
            fh.write(moov)


def _make_dummy_beat(suffix: str = ".mp4") -> Path:
    fd, path = tempfile.mkstemp(suffix=suffix, dir=_FIXTURE_ROOT, prefix="beat_")
    with os.fdopen(fd, "wb") as fh:
        fh.write(b"fake-mp4-bytes-for-phase-c-tests-" + os.urandom(8))
    return Path(path)


# ============================================================================
# 1. Module-level imports + constants
# ============================================================================


class TestModuleSurface(unittest.TestCase):
    """assemble_module exposes the documented public surface."""

    def test_module_imports(self):
        self.assertTrue(hasattr(assemble_module, "assemble_module"))
        self.assertTrue(hasattr(assemble_module, "main"))

    def test_size_budget_constants_match_ld_283(self):
        self.assertEqual(assemble_module.MAX_MODULE_BYTES, 83_886_080)
        self.assertEqual(assemble_module.MAX_MODULE_DURATION_MS, 420_000)

    def test_bitrate_ceiling_matches_size_budget_video_v1(self):
        self.assertEqual(assemble_module.MAX_BITRATE_BPS, 1_900_000)

    def test_codec_recipe_hash_is_64char_lowercase_hex(self):
        h = assemble_module.compute_codec_recipe_hash()
        self.assertEqual(len(h), 64)
        self.assertRegex(h, r"^[a-f0-9]{64}$")
        self.assertEqual(h, assemble_module.compute_codec_recipe_hash())  # deterministic

    def test_steps_exposed_as_callables(self):
        for name in (
            "step_1_validate_inputs",
            "step_1_5_audio_parity_and_bitrate_gate",
            "step_2_build_concat_list",
            "step_3_concat_copy",
            "step_4_faststart_remux",
            "step_5_moov_validate",
            "step_6_codec_assert",
            "step_7_one_frame_decode",
            "step_8_full_duration_smoke",
            "step_9_compute_hashes",
            "step_10_emit_artifacts",
            "step_11_size_duration_gate",
            "step_12_register_assets",
            "step_13_emit_phase_boundaries",
        ):
            self.assertTrue(callable(getattr(assemble_module, name)), f"missing {name}")


# ============================================================================
# 2. Step 1 — input validation (ffprobe codec spec gate per LD-284)
# ============================================================================


class TestStep1ValidateInputs(unittest.TestCase):
    def test_passes_canonical_spec(self):
        beat = _make_dummy_beat()
        root = _canonical_ffprobe_root()
        with patch.object(assemble_module, "ffprobe_full", return_value=root):
            # Should not raise.
            result = assemble_module.step_1_validate_inputs([beat])
        self.assertEqual(len(result), 1)

    def test_hard_stops_on_codec_mismatch(self):
        beat = _make_dummy_beat()
        root = _canonical_ffprobe_root(video_codec="hevc")
        with patch.object(assemble_module, "ffprobe_full", return_value=root):
            with self.assertRaises(assemble_module.CodecMismatchError):
                assemble_module.step_1_validate_inputs([beat])

    def test_hard_stops_on_resolution_mismatch(self):
        beat = _make_dummy_beat()
        root = _canonical_ffprobe_root(width=640, height=480)
        with patch.object(assemble_module, "ffprobe_full", return_value=root):
            with self.assertRaises(assemble_module.CodecMismatchError):
                assemble_module.step_1_validate_inputs([beat])


# ============================================================================
# 3. Step 1.5 — audio parity + bitrate gate (R4)
# ============================================================================


class TestStep1_5AudioParityAndBitrate(unittest.TestCase):
    def test_audio_missing_triggers_silence_injection(self):
        beat = _make_dummy_beat()
        root_no_audio = _canonical_ffprobe_root(include_audio=False)
        root_with_audio = _canonical_ffprobe_root()
        injected_path = beat.with_suffix(".audiopatched.mp4")
        injected_path.write_bytes(b"patched")

        ffprobe_calls = {"n": 0}

        def fake_ffprobe(path):
            ffprobe_calls["n"] += 1
            # First call returns no-audio root; subsequent calls (post-inject) include audio.
            return root_no_audio if ffprobe_calls["n"] == 1 else root_with_audio

        with patch.object(assemble_module, "ffprobe_full", side_effect=fake_ffprobe), patch.object(
            assemble_module, "inject_silence_track", return_value=injected_path
        ) as mock_inject:
            result = assemble_module.step_1_5_audio_parity_and_bitrate_gate([beat])
        mock_inject.assert_called_once()
        # Result should include the patched path (post-injection).
        self.assertEqual(result, [injected_path])

    def test_bitrate_above_ceiling_hard_stops(self):
        beat = _make_dummy_beat()
        # 2,000,000 bps > 1,900,000 ceiling.
        root = _canonical_ffprobe_root(bit_rate="2000000")
        with patch.object(assemble_module, "ffprobe_full", return_value=root):
            with self.assertRaises(assemble_module.BitrateBudgetError):
                assemble_module.step_1_5_audio_parity_and_bitrate_gate([beat])

    def test_bitrate_na_falls_back_to_size_div_duration(self):
        # bit_rate "N/A" → derive from size_bytes (1,500,000) * 8 / 10s = 1,200,000 bps → under cap.
        root = _canonical_ffprobe_root(bit_rate="N/A", size="1500000", duration="10.0")
        result = assemble_module.derive_bitrate_bps(root, "/tmp/whatever.mp4")
        self.assertEqual(result, 1_200_000)

    def test_audio_codec_must_be_aac_mono_44100(self):
        beat = _make_dummy_beat()
        root = _canonical_ffprobe_root(audio_codec="mp3")
        with patch.object(assemble_module, "ffprobe_full", return_value=root):
            with self.assertRaises(assemble_module.CodecMismatchError):
                assemble_module.step_1_5_audio_parity_and_bitrate_gate([beat])

    def test_video_duration_s_prefers_video_stream_then_format(self):
        root = _canonical_ffprobe_root(duration="7.5")
        self.assertEqual(assemble_module.video_duration_s(root), 7.5)

        # Strip video duration; should fall back to format.duration.
        root2 = {
            "streams": [{"codec_type": "video", "codec_name": "h264"}],
            "format": {"duration": "3.25"},
        }
        self.assertEqual(assemble_module.video_duration_s(root2), 3.25)


# ============================================================================
# 4. Step 2 — concat-list construction
# ============================================================================


class TestStep2BuildConcatList(unittest.TestCase):
    def test_emits_file_lines_with_single_quote_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            beat_a = tmp_path / "beat with spaces.mp4"
            beat_b = tmp_path / "beat_b.mp4"
            beat_a.write_bytes(b"a")
            beat_b.write_bytes(b"b")
            out = tmp_path / "beat_list.txt"

            result = assemble_module.step_2_build_concat_list([beat_a, beat_b], out)
            self.assertEqual(result, out)
            text = out.read_text(encoding="utf-8")
            # ffmpeg concat demuxer expects:  file '<absolute path>'
            self.assertIn(f"file '{beat_a}'", text)
            self.assertIn(f"file '{beat_b}'", text)
            # Each line is its own row.
            non_blank = [ln for ln in text.splitlines() if ln.strip()]
            self.assertEqual(len(non_blank), 2)


# ============================================================================
# 5. Steps 3-4 — ffmpeg concat + faststart remux
# ============================================================================


class TestStep3And4Concat(unittest.TestCase):
    def test_step_3_invokes_ffmpeg_concat_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            list_path = tmp_path / "beat_list.txt"
            list_path.write_text("file 'foo.mp4'\n")
            out = tmp_path / "out_raw.mp4"

            with patch.object(assemble_module, "ffmpeg_run") as mock_run:
                mock_run.return_value = 0
                assemble_module.step_3_concat_copy(list_path, out)
            args = mock_run.call_args[0][0]
            # Must use concat demuxer + -c copy.
            self.assertIn("-f", args)
            self.assertIn("concat", args)
            self.assertIn("-c", args)
            self.assertIn("copy", args)
            self.assertIn("-safe", args)

    def test_step_4_invokes_movflags_faststart(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "out_raw.mp4"
            src.write_bytes(b"raw")
            dst = tmp_path / "out.mp4"

            with patch.object(assemble_module, "ffmpeg_run") as mock_run:
                mock_run.return_value = 0
                assemble_module.step_4_faststart_remux(src, dst)
            args = mock_run.call_args[0][0]
            self.assertIn("-movflags", args)
            faststart_idx = args.index("-movflags") + 1
            self.assertIn("+faststart", args[faststart_idx])


# ============================================================================
# 6. Step 5 — MOOV-before-MDAT validation
# ============================================================================


class TestStep5MoovValidate(unittest.TestCase):
    def test_passes_when_moov_before_mdat(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "good.mp4"
            _write_mp4_atoms(mp4, moov_first=True)
            assemble_module.step_5_moov_validate(mp4)  # no raise

    def test_hard_stops_when_moov_after_mdat(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "bad.mp4"
            _write_mp4_atoms(mp4, moov_first=False)
            with self.assertRaises(assemble_module.MoovPositionError):
                assemble_module.step_5_moov_validate(mp4)


# ============================================================================
# 7. Step 6 — full ffprobe codec assert against canonical spec
# ============================================================================


class TestStep6CodecAssert(unittest.TestCase):
    def test_passes_canonical_spec(self):
        mp4 = _make_dummy_beat()
        with patch.object(assemble_module, "ffprobe_full", return_value=_canonical_ffprobe_root()):
            root = assemble_module.step_6_codec_assert(mp4)
        self.assertIn("streams", root)

    def test_hard_stops_on_resolution_mismatch(self):
        mp4 = _make_dummy_beat()
        with patch.object(
            assemble_module,
            "ffprobe_full",
            return_value=_canonical_ffprobe_root(width=640, height=480),
        ):
            with self.assertRaises(assemble_module.CodecMismatchError):
                assemble_module.step_6_codec_assert(mp4)


# ============================================================================
# 8. Steps 7-8 — decode tests
# ============================================================================


class TestSteps7And8Decode(unittest.TestCase):
    def test_step_7_invokes_frames_v_1(self):
        mp4 = _make_dummy_beat()
        with patch.object(assemble_module, "ffmpeg_run", return_value=0) as mock_run:
            assemble_module.step_7_one_frame_decode(mp4)
        args = mock_run.call_args[0][0]
        self.assertIn("-frames:v", args)
        idx = args.index("-frames:v") + 1
        self.assertEqual(args[idx], "1")

    def test_step_7_hard_stops_on_nonzero_exit(self):
        mp4 = _make_dummy_beat()
        with patch.object(assemble_module, "ffmpeg_run", return_value=1):
            with self.assertRaises(assemble_module.DecodeError):
                assemble_module.step_7_one_frame_decode(mp4)

    def test_step_8_full_duration_smoke_hard_stops_on_nonzero_exit(self):
        mp4 = _make_dummy_beat()
        with patch.object(assemble_module, "ffmpeg_run", return_value=2):
            with self.assertRaises(assemble_module.DecodeError):
                assemble_module.step_8_full_duration_smoke(mp4)


# ============================================================================
# 9. Step 9 — source_hash + output_hash compute
# ============================================================================


class TestStep9Hashes(unittest.TestCase):
    def test_returns_64char_lowercase_hex_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "out.mp4"
            mp4.write_bytes(b"deterministic-bytes")
            source_hash, output_hash = assemble_module.step_9_compute_hashes(
                mp4,
                per_beat_hashes=["a" * 64, "b" * 64],
                audio_mix_hash="c" * 64,
                metadata={"module_id": "M001"},
            )
        self.assertRegex(source_hash, r"^[a-f0-9]{64}$")
        self.assertRegex(output_hash, r"^[a-f0-9]{64}$")

    def test_output_hash_matches_sha256_of_raw_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "out.mp4"
            payload = b"abc-payload-for-hash"
            mp4.write_bytes(payload)
            _, output_hash = assemble_module.step_9_compute_hashes(
                mp4,
                per_beat_hashes=["x" * 64],
                audio_mix_hash="y" * 64,
                metadata={"id": "M001"},
            )
        self.assertEqual(output_hash, hashlib.sha256(payload).hexdigest())

    def test_source_hash_deterministic_under_metadata_canonicalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "out.mp4"
            mp4.write_bytes(b"same-bytes")
            a, _ = assemble_module.step_9_compute_hashes(
                mp4,
                per_beat_hashes=["1" * 64],
                audio_mix_hash="2" * 64,
                metadata={"b": 2, "a": 1},
            )
            b, _ = assemble_module.step_9_compute_hashes(
                mp4,
                per_beat_hashes=["1" * 64],
                audio_mix_hash="2" * 64,
                metadata={"a": 1, "b": 2},
            )
        self.assertEqual(a, b)


# ============================================================================
# 10. Step 10 — emit 7 declared artifacts
# ============================================================================


class TestStep10EmitArtifacts(unittest.TestCase):
    def test_writes_seven_declared_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mp4 = tmp_path / "M001.mp4"
            mp4.write_bytes(b"deliverable")
            audio = tmp_path / "audio.mp3"
            audio.write_bytes(b"audio-bytes")
            out_dir = tmp_path / "output"
            out_dir.mkdir()

            with patch.object(assemble_module, "ffmpeg_run", return_value=0):
                artifacts = assemble_module.step_10_emit_artifacts(
                    out_path=mp4,
                    module_id="M001",
                    ffprobe_root=_canonical_ffprobe_root(),
                    source_hash="a" * 64,
                    output_hash="b" * 64,
                    audio_mix_path=audio,
                    manifest_phase_boundaries={
                        "story_start_ms": 0,
                        "phase_b_start_ms": 1000,
                        "phase_b_end_ms": 5000,
                    },
                    reward={"coins": 5, "items": []},
                    out_dir=out_dir,
                )
        self.assertEqual(len(artifacts), 7)

        names = sorted(p.name for p in artifacts)
        expected = sorted(
            [
                "M001.mp4",
                "M001.manifest.json",
                "M001.ffprobe.json",
                "M001.decode_test.log",
                "M001.size_report.json",
                "M001.sha256",
                "M001.listen_through.mp4",
            ]
        )
        self.assertEqual(names, expected)

        # Manifest is valid JSON with the expected fields.
        manifest = json.loads((out_dir / "M001.manifest.json").read_text())
        self.assertEqual(manifest["moduleId"], "M001")
        self.assertEqual(manifest["source_hash"], "a" * 64)
        self.assertEqual(manifest["output_hash"], "b" * 64)
        self.assertEqual(manifest["phaseBoundaries"]["story_start_ms"], 0)
        self.assertEqual(manifest["phaseBoundaries"]["phase_b_start_ms"], 1000)
        self.assertEqual(manifest["phaseBoundaries"]["phase_b_end_ms"], 5000)

        # sha256 sidecar file contains the output_hash on its first line.
        sha_text = (out_dir / "M001.sha256").read_text().strip()
        self.assertTrue(sha_text.startswith("b" * 64))


# ============================================================================
# 11. Step 11 — size + duration gate (LD-283)
# ============================================================================


class TestStep11SizeDurationGate(unittest.TestCase):
    def test_passes_within_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "ok.mp4"
            mp4.write_bytes(b"x" * 1024)  # tiny
            root = _canonical_ffprobe_root(duration="60.0")  # 60s, well under 7min
            assemble_module.step_11_size_duration_gate(mp4, root, module_id="M001")

    def test_hard_stops_above_80mb(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "huge.mp4"
            # Write a sparse 80MB+1 file (use truncate to avoid actually writing).
            with open(mp4, "wb") as fh:
                fh.truncate(assemble_module.MAX_MODULE_BYTES + 1)
            root = _canonical_ffprobe_root(duration="60.0")
            with self.assertRaises(assemble_module.SizeBudgetError):
                assemble_module.step_11_size_duration_gate(mp4, root, module_id="M001")

    def test_hard_stops_above_7min(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "long.mp4"
            mp4.write_bytes(b"x" * 1024)
            # 421s = 421,000ms > 420,000 ceiling.
            root = _canonical_ffprobe_root(duration="421.0")
            with self.assertRaises(assemble_module.DurationBudgetError):
                assemble_module.step_11_size_duration_gate(mp4, root, module_id="M001")


# ============================================================================
# 12. Step 12 — register_asset calls (per LD-421 + spec §3.2 Step 12)
# ============================================================================


class TestStep12RegisterAssets(unittest.TestCase):
    def test_calls_register_asset_with_codec_recipe_hash_per_artifact(self):
        recipe_hash = "f" * 64
        artifacts = [Path("/tmp/M001.mp4"), Path("/tmp/M001.manifest.json")]
        with patch.object(
            assemble_module, "register_asset", return_value=(123, "/tmp/M001.mp4")
        ) as mock_reg:
            results = assemble_module.step_12_register_assets(
                artifacts, module_id="M001", codec_recipe_hash=recipe_hash
            )
        self.assertEqual(len(results), 2)
        for call in mock_reg.call_args_list:
            self.assertEqual(call.kwargs.get("codec_recipe_hash"), recipe_hash)
            self.assertIsNone(call.kwargs.get("cdn_url"))  # set in Phase D
            self.assertIsNone(call.kwargs.get("manifest_published_at"))

    def test_treats_minus_one_return_as_queued_not_fatal(self):
        artifacts = [Path("/tmp/M001.mp4")]
        with patch.object(
            assemble_module, "register_asset", return_value=(-1, "/tmp/M001.mp4")
        ):
            # Must not raise; offline-queue is the documented contract.
            results = assemble_module.step_12_register_assets(
                artifacts, module_id="M001", codec_recipe_hash="0" * 64
            )
        self.assertEqual(results[0][0], -1)


# ============================================================================
# 13. Step 13 — phaseBoundaries emission (named-object form per LD-412)
# ============================================================================


class TestStep13PhaseBoundaries(unittest.TestCase):
    def test_writes_named_object_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "M001.manifest.json"
            manifest_path.write_text(json.dumps({"moduleId": "M001"}))
            raw = {
                "story_start_ms": 0,
                "phase_b_start_ms": 2000,
                "phase_b_end_ms": 8000,
            }
            assemble_module.step_13_emit_phase_boundaries(manifest_path, raw)
        manifest = json.loads(manifest_path.read_text())
        pb = manifest["phaseBoundaries"]
        self.assertEqual(pb["story_start_ms"], 0)
        self.assertEqual(pb["phase_b_start_ms"], 2000)
        self.assertEqual(pb["phase_b_end_ms"], 8000)

    def test_rejects_out_of_order_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "M001.manifest.json"
            manifest_path.write_text(json.dumps({"moduleId": "M001"}))
            with self.assertRaises(ValueError):
                assemble_module.step_13_emit_phase_boundaries(
                    manifest_path,
                    {
                        "story_start_ms": 5000,
                        "phase_b_start_ms": 2000,  # before story_start_ms
                        "phase_b_end_ms": 8000,
                    },
                )


# ============================================================================
# 14. CLI surface
# ============================================================================


class TestCliSurface(unittest.TestCase):
    def test_main_rejects_missing_required_args(self):
        with self.assertRaises(SystemExit):
            assemble_module.main([])

    def test_main_accepts_documented_flags(self):
        # We don't run the full pipeline here — patch assemble_module() itself so
        # CLI argparse + dispatch is verified independent of pipeline implementation.
        with patch.object(
            assemble_module, "assemble_module", return_value={"ok": True, "artifacts": []}
        ) as mock_pipe:
            rc = assemble_module.main(
                [
                    "--module",
                    "M001",
                    "--beats",
                    "/tmp/beats",
                    "--audio",
                    "/tmp/audio.mp3",
                    "--metadata",
                    "/tmp/meta.json",
                    "--out",
                    "/tmp/out",
                ]
            )
        self.assertEqual(rc, 0)
        mock_pipe.assert_called_once()


# ============================================================================
# 15. Orchestrator wiring (integration with mocks)
# ============================================================================


class TestOrchestrator(unittest.TestCase):
    def test_orchestrator_invokes_canonical_step_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            beats_dir = tmp_path / "beats"
            beats_dir.mkdir()
            beat = beats_dir / "beat_01_normalized.mp4"
            beat.write_bytes(b"beat-bytes")

            audio = tmp_path / "phaseB.mp3"
            audio.write_bytes(b"audio-bytes")

            metadata = tmp_path / "meta.json"
            metadata.write_text(
                json.dumps(
                    {
                        "moduleId": "M001",
                        "phaseBoundaries": {
                            "story_start_ms": 0,
                            "phase_b_start_ms": 1000,
                            "phase_b_end_ms": 5000,
                        },
                        "reward": {"coins": 5, "items": []},
                    }
                )
            )

            out_dir = tmp_path / "out"
            out_dir.mkdir()

            # Patch every step + helpers to confirm the orchestrator wires them
            # together in the canonical sequence — and that step_5 runs after
            # step_4 (MOOV check after faststart).
            call_log = []

            def record(name, *_a, **_k):
                call_log.append(name)
                return None

            def fake_step_1(beats):
                call_log.append("step_1")
                return [{"path": str(p)} for p in beats]

            def fake_step_1_5(beats):
                call_log.append("step_1_5")
                return list(beats)

            def fake_step_2(beats, out_path):
                call_log.append("step_2")
                Path(out_path).write_text("")
                return Path(out_path)

            def fake_step_3(list_path, out):
                call_log.append("step_3")
                Path(out).write_bytes(b"raw-mp4")

            def fake_step_4(src, dst):
                call_log.append("step_4")
                Path(dst).write_bytes(b"final-mp4")

            def fake_step_5(p):
                call_log.append("step_5")

            def fake_step_6(p):
                call_log.append("step_6")
                return _canonical_ffprobe_root()

            def fake_step_7(p):
                call_log.append("step_7")

            def fake_step_8(p):
                call_log.append("step_8")

            def fake_step_9(p, **k):
                call_log.append("step_9")
                return ("a" * 64, "b" * 64)

            def fake_step_10(**k):
                call_log.append("step_10")
                manifest = k["out_dir"] / f"{k['module_id']}.manifest.json"
                manifest.write_text(json.dumps({"moduleId": k["module_id"]}))
                return [
                    k["out_dir"] / f"{k['module_id']}.mp4",
                    manifest,
                ]

            def fake_step_11(p, root, module_id):
                call_log.append("step_11")

            def fake_step_12(artifacts, module_id, codec_recipe_hash):
                call_log.append("step_12")
                return [(1, str(a)) for a in artifacts]

            def fake_step_13(manifest, raw):
                call_log.append("step_13")

            patches = [
                patch.object(assemble_module, "step_1_validate_inputs", side_effect=fake_step_1),
                patch.object(
                    assemble_module,
                    "step_1_5_audio_parity_and_bitrate_gate",
                    side_effect=fake_step_1_5,
                ),
                patch.object(assemble_module, "step_2_build_concat_list", side_effect=fake_step_2),
                patch.object(assemble_module, "step_3_concat_copy", side_effect=fake_step_3),
                patch.object(assemble_module, "step_4_faststart_remux", side_effect=fake_step_4),
                patch.object(assemble_module, "step_5_moov_validate", side_effect=fake_step_5),
                patch.object(assemble_module, "step_6_codec_assert", side_effect=fake_step_6),
                patch.object(assemble_module, "step_7_one_frame_decode", side_effect=fake_step_7),
                patch.object(
                    assemble_module, "step_8_full_duration_smoke", side_effect=fake_step_8
                ),
                patch.object(assemble_module, "step_9_compute_hashes", side_effect=fake_step_9),
                patch.object(assemble_module, "step_10_emit_artifacts", side_effect=fake_step_10),
                patch.object(
                    assemble_module, "step_11_size_duration_gate", side_effect=fake_step_11
                ),
                patch.object(assemble_module, "step_12_register_assets", side_effect=fake_step_12),
                patch.object(
                    assemble_module, "step_13_emit_phase_boundaries", side_effect=fake_step_13
                ),
            ]
            for p in patches:
                p.start()
            try:
                result = assemble_module.assemble_module(
                    module_id="M001",
                    beats_dir=beats_dir,
                    audio_mix_path=audio,
                    metadata_path=metadata,
                    out_dir=out_dir,
                )
            finally:
                for p in patches:
                    p.stop()

        expected_order = [
            "step_1",
            "step_1_5",
            "step_2",
            "step_3",
            "step_4",
            "step_5",
            "step_6",
            "step_7",
            "step_8",
            "step_9",
            "step_10",
            "step_11",
            "step_12",
            "step_13",
        ]
        self.assertEqual(call_log, expected_order)
        self.assertIn("artifacts", result)


if __name__ == "__main__":
    unittest.main()
