"""
Phase-1 payload validator tests (override file §9.2 + vocab parity §15 row 9).

Run:
  PYTHONPATH=<Production> python3 -m unittest Production.tests.test_payload_validator -v

Or from Production/:
  python3 -m unittest tests.test_payload_validator -v
"""

from __future__ import annotations

import errno
import json
import os
import sys
import tempfile
import unittest
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Callable
from unittest.mock import patch

_PRODUCTION_ROOT = Path(__file__).resolve().parents[1]
if str(_PRODUCTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_PRODUCTION_ROOT))

from lib.payload_validator import (  # noqa: E402
    OVERRIDE_FILE_REASON_VOCAB,
    OverrideFileMalformedError,
    load_override_file,
)
import lib.payload_validator as pv  # noqa: E402


class FakeActivityClient:
    """Captures POST + read-back; no network."""

    def __init__(self) -> None:
        self.posted: list[tuple[str, dict]] = []
        self.readbacks: list[tuple[str, object]] = []

    def post_item(self, collection: str, data: dict, retry_post: bool = False):  # noqa: ARG002
        self.posted.append((collection, data))
        return {"id": len(self.posted)}

    def get_item(self, collection: str, item_id: object, fields: list[str] | None = None):  # noqa: ARG002
        self.readbacks.append((collection, item_id))
        return {"id": item_id}


class PayloadValidatorFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_log = os.environ.get("MN_PAYLOAD_VALIDATOR_LOG_PATH")
        self._prev_loud = os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE")
        self._td = tempfile.TemporaryDirectory()
        self.log_path = Path(self._td.name) / "payload_validator.log"

    def tearDown(self) -> None:
        if self._prev_log is None:
            os.environ.pop("MN_PAYLOAD_VALIDATOR_LOG_PATH", None)
        else:
            os.environ["MN_PAYLOAD_VALIDATOR_LOG_PATH"] = self._prev_log
        if self._prev_loud is None:
            os.environ.pop("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE", None)
        else:
            os.environ["MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE"] = self._prev_loud
        self._td.cleanup()
        os.environ.pop("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE", None)

    def _prep(self, fail_mode_safe: bool = True) -> FakeActivityClient:
        os.environ["MN_PAYLOAD_VALIDATOR_LOG_PATH"] = str(self.log_path)
        os.environ.pop("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE", None)
        if not fail_mode_safe:
            os.environ["MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE"] = "loud"
        return FakeActivityClient()

    def _tail_log_text(self) -> str:
        if not self.log_path.exists():
            return ""
        return self.log_path.read_text(encoding="utf-8")

    def test_b_valid_fixture(self) -> None:
        c = self._prep()
        p = Path(self._td.name) / "payload_validator_overrides.json"
        payload = {"prod_pv_fixture_collection": {"mode": "warn", "extra_allowed_keys": ["z"]}}
        p.write_text(json.dumps(payload), encoding="utf-8")

        got = load_override_file(p, client=c)
        self.assertEqual(got, payload)
        self.assertEqual(c.posted, [])
        self.assertEqual(c.readbacks, [])
        log = self._tail_log_text().strip()
        self.assertEqual(log, "")

    def test_c_invalid_json_fixture(self) -> None:
        c = self._prep()
        p = Path(self._td.name) / "bad.json"
        p.write_text("{ not json ", encoding="utf-8")

        got = load_override_file(p, client=c)
        self.assertEqual(got, {})
        self.assertTrue(c.posted)
        action, row = c.posted[0]
        self.assertEqual(action, "prod_activity_log")
        d = row["details"]
        self.assertEqual(d["case"], "C")
        self.assertEqual(d["reason"], "json_parse_error")

        token = "json_parse_error"
        self.assertIn(f"reason={token}", self._tail_log_text())
        self.assertIn(token, OVERRIDE_FILE_REASON_VOCAB)

    def test_d_invalid_layout_fixture(self) -> None:
        c = self._prep()
        p = Path(self._td.name) / "bad_layout.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")

        got = load_override_file(p, client=c)
        self.assertEqual(got, {})
        token = "layout_error"
        d = c.posted[0][1]["details"]
        self.assertEqual(d["reason"], token)
        self.assertEqual(d["case"], "D")
        self.assertIn(f"reason={token}", self._tail_log_text())

    def test_a1_broken_symlink_fixture(self) -> None:
        c = self._prep()
        real = Path(self._td.name) / "tgt"
        real.write_text("x", encoding="utf-8")
        link = Path(self._td.name) / "payload_validator_overrides.json"
        link.symlink_to(real)
        real.unlink()

        got = load_override_file(link, client=c)
        self.assertEqual(got, {})
        token = "broken_symlink"
        d = c.posted[0][1]["details"]
        self.assertEqual(d["reason"], token)
        self.assertEqual(d["case"], "A1")
        self.assertIn(f"reason={token}", self._tail_log_text())

        self.assertEqual(len(c.readbacks), len(c.posted))

    def test_a2_toctou_fixture(self) -> None:
        c = self._prep()
        p = Path(self._td.name) / "payload_validator_overrides.json"
        p.write_text("{}", encoding="utf-8")

        token = "toctou_vanished"
        with patch.object(pv, "_fs_exists", return_value=False):
            got = load_override_file(p, client=c)

        self.assertEqual(got, {})
        d = c.posted[0][1]["details"]
        self.assertEqual(d["reason"], token)
        self.assertEqual(d["case"], "A2")
        self.assertIn(f"reason={token}", self._tail_log_text())

    def test_a3_metadata_os_error_fixture(self) -> None:
        c = self._prep()
        p = Path(self._td.name) / "payload_validator_overrides.json"
        p.write_text("{}", encoding="utf-8")

        token = "metadata_os_error"
        exc = PermissionError(13, "permission denied metadata")

        with patch.object(pv, "_fs_lstat", side_effect=exc):
            got = load_override_file(p, client=c)

        self.assertEqual(got, {})
        d = c.posted[0][1]["details"]
        self.assertEqual(d["reason"], token)
        self.assertEqual(d["case"], "A3")
        self.assertIn("permission denied metadata", (d.get("os_error") or ""))
        self.assertIn(f"reason={token}", self._tail_log_text())

    def test_e_permission_denied_read_fixture(self) -> None:
        c = self._prep()
        p = Path(self._td.name) / "payload_validator_overrides.json"
        p.write_text("{}", encoding="utf-8")
        token = "permission_denied"
        exc = PermissionError(13, "chmod 000")

        with patch.object(pv, "_fs_read_bytes", side_effect=exc):
            got = load_override_file(p, client=c)

        self.assertEqual(got, {})
        d = c.posted[0][1]["details"]
        self.assertEqual(d["reason"], token)
        self.assertEqual(d["case"], "E")
        self.assertIn(f"reason={token}", self._tail_log_text())

    def test_e2_io_error_read_fixture(self) -> None:
        c = self._prep()
        p = Path(self._td.name) / "payload_validator_overrides.json"
        p.write_text("{}", encoding="utf-8")
        token = "io_error"

        exc = OSError(errno.EIO, "simulated input/output error")

        with patch.object(pv, "_fs_read_bytes", side_effect=exc):
            got = load_override_file(p, client=c)

        self.assertEqual(got, {})
        d = c.posted[0][1]["details"]
        self.assertEqual(d["reason"], token)
        self.assertEqual(d["case"], "E2")
        self.assertIn(f"reason={token}", self._tail_log_text())

    def test_vocab_grep_parity_diagnostic_fixture(self) -> None:
        """§15 audit row 9 — log reason= and activity-log details.reason match."""

        def run_c(root: Path) -> FakeActivityClient:
            fb = FakeActivityClient()
            path = root / "c.json"
            path.write_text("{ not json ", encoding="utf-8")
            load_override_file(path, client=fb)
            return fb

        def run_d(root: Path) -> FakeActivityClient:
            fb = FakeActivityClient()
            path = root / "d.json"
            path.write_text("[1, 2]", encoding="utf-8")
            load_override_file(path, client=fb)
            return fb

        def run_a1(root: Path) -> FakeActivityClient:
            fb = FakeActivityClient()
            t = root / "_t_sy"
            t.write_text("x", encoding="utf-8")
            lk = root / "_symlink_load.json"
            lk.symlink_to(t)
            t.unlink()
            load_override_file(lk, client=fb)
            return fb

        def run_a2(root: Path) -> FakeActivityClient:
            fb = FakeActivityClient()
            path = root / "a2.json"
            path.write_text("{}", encoding="utf-8")
            with patch.object(pv, "_fs_exists", return_value=False):
                load_override_file(path, client=fb)
            return fb

        def run_a3(root: Path) -> FakeActivityClient:
            fb = FakeActivityClient()
            path = root / "a3.json"
            path.write_text("{}", encoding="utf-8")
            with patch.object(pv, "_fs_lstat", side_effect=PermissionError(13)):
                load_override_file(path, client=fb)
            return fb

        def run_e(root: Path) -> FakeActivityClient:
            fb = FakeActivityClient()
            path = root / "e.json"
            path.write_text("{}", encoding="utf-8")
            with patch.object(pv, "_fs_read_bytes", side_effect=PermissionError(13)):
                load_override_file(path, client=fb)
            return fb

        def run_e2(root: Path) -> FakeActivityClient:
            fb = FakeActivityClient()
            path = root / "e2.json"
            path.write_text("{}", encoding="utf-8")
            err = OSError(errno.EIO, "eio")
            with patch.object(pv, "_fs_read_bytes", side_effect=err):
                load_override_file(path, client=fb)
            return fb

        run_map: tuple[tuple[str, Callable[[Path], FakeActivityClient]], ...] = (
            ("json_parse_error", run_c),
            ("layout_error", run_d),
            ("broken_symlink", run_a1),
            ("toctou_vanished", run_a2),
            ("metadata_os_error", run_a3),
            ("permission_denied", run_e),
            ("io_error", run_e2),
        )

        for expected_token, runner in run_map:
            with tempfile.TemporaryDirectory() as td2:
                log_path = Path(td2) / "pv_case.log"
                os.environ["MN_PAYLOAD_VALIDATOR_LOG_PATH"] = str(log_path)
                fb = runner(Path(td2))
                os.environ.pop("MN_PAYLOAD_VALIDATOR_LOG_PATH", None)
                self.assertTrue(fb.posted, msg=f"expected activity post for {expected_token}")
                r = fb.posted[0][1]["details"]["reason"]
                self.assertEqual(r, expected_token)
                logged = log_path.read_text(encoding="utf-8")
                self.assertIn(f"reason={expected_token}", logged)


def _path_bad_json(root: Path) -> Path:
    p = root / "jp.json"
    p.write_text("{ not json ", encoding="utf-8")
    return p


def _path_bad_layout(root: Path) -> Path:
    p = root / "ly.json"
    p.write_text("[1, 2]", encoding="utf-8")
    return p


def _path_broken_symlink(root: Path) -> Path:
    t = root / "_tgt"
    t.write_text("x", encoding="utf-8")
    lk = root / "_sl.json"
    lk.symlink_to(t)
    t.unlink()
    return lk


def _path_plain(root: Path) -> Path:
    p = root / "plain.json"
    p.write_text("{}", encoding="utf-8")
    return p


class LoudFailThreeWayTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("MN_PAYLOAD_VALIDATOR_LOG_PATH", None)
        os.environ.pop("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE", None)

    def test_loud_all_seven_raise_with_vocab_parity(self) -> None:
        """Fail-loud §5 + §3.10: log reason= == details.reason == exception.kind."""
        os.environ["MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE"] = "loud"
        cases: tuple[tuple[str, Callable[[Path], Path], AbstractContextManager[None]], ...] = (
            ("json_parse_error", _path_bad_json, nullcontext()),
            ("layout_error", _path_bad_layout, nullcontext()),
            ("broken_symlink", _path_broken_symlink, nullcontext()),
            (
                "toctou_vanished",
                _path_plain,
                patch.object(pv, "_fs_exists", return_value=False),
            ),
            (
                "metadata_os_error",
                _path_plain,
                patch.object(pv, "_fs_lstat", side_effect=PermissionError(13)),
            ),
            (
                "permission_denied",
                _path_plain,
                patch.object(pv, "_fs_read_bytes", side_effect=PermissionError(13)),
            ),
            (
                "io_error",
                _path_plain,
                patch.object(
                    pv, "_fs_read_bytes", side_effect=OSError(errno.EIO, "simulated")
                ),
            ),
        )

        for token, prep_path, mgr in cases:
            with tempfile.TemporaryDirectory() as td_raw:
                td = Path(td_raw)
                log_file = td / "loud.log"
                os.environ["MN_PAYLOAD_VALIDATOR_LOG_PATH"] = str(log_file)
                path = prep_path(td)
                fb = FakeActivityClient()
                with mgr:
                    with self.assertRaises(OverrideFileMalformedError) as ar:
                        load_override_file(path, client=fb)
                exc = ar.exception
                self.assertIsInstance(exc.path, str)
                self.assertEqual(exc.path, str(path))
                self.assertEqual(exc.kind, token)
                self.assertEqual(exc.kind, OVERRIDE_FILE_REASON_VOCAB.intersection({exc.kind}).pop())
                self.assertTrue(fb.posted)
                self.assertEqual(fb.posted[0][1]["details"]["reason"], token)
                self.assertIn(f"reason={token}", log_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
