"""Library audio upload — cr_upload tier sfx/ambient/transitions."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers import cropper  # noqa: E402


class _FakeHandler:
    def __init__(self, event_dir: Path):
        self.app = mock.Mock()
        self.app.event_dir = event_dir
        self.app.event_generation = 1
        self.app.scope_type = "event"
        self.app.active_milestone_id = None
        self._responses: list[tuple] = []

    def _scope_body(self, body):
        return body

    def _assert_event_scope(self, scope, allow_missing=False, allow_missing_video_role=False):
        return True

    def _check_event_pin(self, pin, label):
        return True

    def _send_json(self, code, payload):
        self._responses.append((code, payload))
        return payload

    def _send_error_v59(self, code, **kwargs):
        self._responses.append((code, kwargs))
        return kwargs


def test_cr_upload_sfx_writes_to_sound_library(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    h = _FakeHandler(event_dir)
    raw = b"\xff\xfb\x90" + b"\x00" * 64
    body = {
        "filename": "magic_sound.mp3",
        "file_b64": base64.b64encode(raw).decode(),
        "tier": "sfx",
    }
    with mock.patch("server_handlers.phases._data_root", return_value=tmp_path):
        cropper.handle_cr_upload(h, body)

    code, payload = h._responses[-1]
    assert code == 200
    assert payload["ok"] is True
    assert payload["tier"] == "sfx"
    dest = tmp_path / "assets" / "sound_library" / "sfx" / "magic_sound.mp3"
    assert dest.is_file()
    assert dest.read_bytes() == raw


def test_cr_upload_rejects_non_audio_extension(tmp_path: Path) -> None:
    h = _FakeHandler(tmp_path / "Event_1")
    body = {
        "filename": "tile.png",
        "file_b64": base64.b64encode(b"png").decode(),
        "tier": "sfx",
    }
    cropper.handle_cr_upload(h, body)
    code, payload = h._responses[-1]
    assert code == 400
    assert payload["error_code"] == "INVALID_FILENAME_EXTENSION"
