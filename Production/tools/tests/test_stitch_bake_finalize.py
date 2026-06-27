"""Stitch bake canonical + Directus finalize contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_resolve_m_and_event_numbers_from_production_state(tmp_path: Path) -> None:
    from stitch_bake_finalize import resolve_m_and_event_numbers

    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    (event_dir / "production_state.json").write_text(
        json.dumps({"event_id": "M1E1"}),
        encoding="utf-8",
    )
    assert resolve_m_and_event_numbers(event_dir) == (1, 1)


def test_resolve_m_and_event_numbers_from_folder_name(tmp_path: Path) -> None:
    from stitch_bake_finalize import resolve_m_and_event_numbers

    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    assert resolve_m_and_event_numbers(event_dir) == (2, 2)


def test_finalize_stitch_bake_pins_registers_and_approves(tmp_path: Path) -> None:
    from stitch_bake_finalize import finalize_stitch_bake

    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    exports = event_dir / "exports"
    exports.mkdir()
    bake = exports / "stitch_Event_1_stitch_test.mp4"
    bake.write_bytes(b"\x00" * 128)

    stitch_tools = tmp_path / "tools"
    stitch_tools.mkdir()
    stitch_state = stitch_tools / "stitch_editor_state.json"
    stitch_state.write_text(
        json.dumps({"version": 1, "jobs": {"Event_1_stitch": {"slots": {}}}}),
        encoding="utf-8",
    )

    pin_result = {
        "ok": True,
        "canonical_path": str(event_dir / "M1_event_1_final.mp4"),
        "canonical_name": "M1_event_1_final.mp4",
        "sha256": "abc",
    }
    (event_dir / "M1_event_1_final.mp4").write_bytes(b"\x00" * 128)

    with patch("stitch_bake_finalize.pin_canonical_module", return_value=pin_result):
        with patch("registered_write.register_asset", return_value=(42, pin_result["canonical_path"])):
            with patch("registered_write.approve_asset", return_value=True):
                mock_client = MagicMock()
                mock_client._request.return_value = {"data": []}
                with patch("registered_write._client", return_value=mock_client):
                    result = finalize_stitch_bake(
                        event_dir,
                        bake,
                        module_id=1,
                        m_number=1,
                        event_num=1,
                        stitch_state_path=stitch_state,
                    )

    assert result["asset_id"] == 42
    assert result["directus_approved"] is True
    assert result["canonical_name"] == "M1_event_1_final.mp4"


def test_stitch_exports_dir_uses_active_event_dir() -> None:
    src = Path(__file__).resolve().parents[1] / "production_server.py"
    text = src.read_text(encoding="utf-8")
    assert 'Path(self.app.event_dir) / "exports"' in text
    assert 'Production" / "Event_1" / "exports"' not in text


def test_stitch_bake_handler_uses_finalize_contract() -> None:
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "stitch_editor.py"
    text = src.read_text(encoding="utf-8")
    assert "finalize_stitch_bake" in text
    assert "STITCH_BAKE_CANONICAL_DIRECTUS_V1" in text
    assert "register_asset(" not in text.split("def handle_stitch_bake")[1].split("def handle_")[0]
