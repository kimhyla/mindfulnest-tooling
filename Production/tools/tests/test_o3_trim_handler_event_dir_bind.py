"""Apply Cut NameError class — handler must bind event_dir before nested trim/cut uses it.

Event_6 resolution Container 4 (filename post_beat_04) toast:
  Cut failed: name 'event_dir' is not defined
Trace: handle_bg_kling_o3_trim → _apply_option_trim_to_work_beat → event_dir=event_dir

Root: PR #130 added event_dir=event_dir kwargs for Dropbox duration probes but never
assigned event_dir in the handler. Grep-only trim tests never executed the path.
"""
from __future__ import annotations

import ast
import copy
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from server_handlers import background as bgh

TOOLS = Path(__file__).resolve().parent.parent
HANDLERS = TOOLS / "server_handlers"
BACKGROUND = HANDLERS / "background.py"

EVENT6_POST_BEAT_04 = "bg_arc1_event6_post_beat_04"
EVENT6_POST_CLIP = "bg_arc1_event6_post_beat_04_g1_element_o3_master_delivery.mp4"


def _direct_assign_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = {a.arg for a in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]}
    if fn.args.vararg:
        names.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        names.add(fn.args.kwarg.arg)

    class _Assigns(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is fn:
                self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if node is fn:
                self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
            self.generic_visit(node)

        def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
            self.generic_visit(node)

    _Assigns().visit(fn)
    return names


def _unbound_event_dir_loads(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[tuple[str, set[str]]] = []

        def _push(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            self.stack.append((node.name, _direct_assign_names(node)))
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._push(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._push(node)

        def visit_Name(self, node: ast.Name) -> None:
            if not isinstance(node.ctx, ast.Load) or node.id != "event_dir":
                return
            if not self.stack:
                return
            if any("event_dir" in assigned for _, assigned in self.stack):
                return
            fn = self.stack[-1][0]
            hits.append(f"{path.name}:{node.lineno}:{fn}")

    _Visitor().visit(tree)
    return hits


def test_server_handlers_never_load_unbound_event_dir() -> None:
    """Category invariant: event_dir=event_dir is illegal unless some enclosing scope binds it."""
    violations: list[str] = []
    for path in sorted(HANDLERS.glob("*.py")):
        violations.extend(_unbound_event_dir_loads(path))
    assert violations == [], (
        "event_dir used without assignment in enclosing handler "
        f"(PR #130 NameError class): {violations}"
    )


def test_trim_handler_assigns_event_dir_at_entry() -> None:
    src = BACKGROUND.read_text(encoding="utf-8")
    start = src.index("def handle_bg_kling_o3_trim")
    end = src.index("\ndef ", start + 1)
    block = src[start:end]
    assert "event_dir = _handler_event_dir(h)" in block
    assert "event_dir=event_dir" in block


def _option_trim_body(*, preview_only: bool) -> dict:
    return {
        "beat_id": EVENT6_POST_BEAT_04,
        "slot_index": 0,
        "trim_start": 1.44,
        "video_path": EVENT6_POST_CLIP,
        "preview_only": preview_only,
        "scope_event_id": "Event_6",
        "scope_video_role": "resolution",
    }


def _fake_bg(event_dir: Path, video: Path, beat: dict) -> MagicMock:
    bg = MagicMock()
    bg.read_sidecar_for_poll_snapshot.return_value = {"beats": [beat]}
    bg._migrate_sidecar.side_effect = lambda sc, **_k: sc
    bg.find_beat.return_value = (0, copy.deepcopy(beat))
    bg.refresh_o3_ui_slot_layout.return_value = None
    trim_result = {
        "trim_start": 1.44,
        "trim_back": None,
        "raw_duration_s": 5.065,
        "effective_duration_s": 3.625,
        "video_path": str(video),
        "slot_index": 0,
    }
    captured: dict = {}

    def _set_trim(*_a, **kwargs):
        captured["event_dir"] = kwargs.get("event_dir")
        return dict(trim_result)

    bg.set_o3_option_trim.side_effect = _set_trim
    opt = {
        "slot_index": 0,
        "video_path": str(video),
        "trim_start_s": 1.44,
        "kling_o3_baked_path": str(video),
    }
    bg.find_o3_option_by_slot_index.return_value = opt
    bg.option_has_o3_trim.return_value = True
    bg.beat_is_still_insert.return_value = False
    bg.bake_o3_active_export_clip.return_value = {
        "baked": True,
        "baked_path": str(video),
        "baked_token": "tok",
    }
    bg.update_beat_locked.return_value = (True, beat)
    bg.kling_o3_trim_is_active.return_value = True
    bg.beat_has_o3_sidecar_cut.return_value = False
    bg.kling_o3_ui_trim_preview_path.return_value = video
    bg.find_kling_o3_ui_trim_preview_by_window.return_value = video
    bg.sidecar_io_transient.return_value = False
    bg.o3_trim_shortening_requested.return_value = True
    bg.o3_trim_effective_is_shorter.return_value = True
    bg.captured = captured
    return bg


@pytest.mark.parametrize("preview_only", [False, True])
def test_event6_resolution_beat4_apply_cut_binds_event_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preview_only: bool,
) -> None:
    event_dir = tmp_path / "Event_6"
    event_dir.mkdir()
    video = event_dir / EVENT6_POST_CLIP
    video.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"x" * 200)
    beat = {
        "beat_id": EVENT6_POST_BEAT_04,
        "kling_o3_status": "approved",
        "kling_o3_video_path": str(video),
        "kling_o3_options": [
            {"slot_index": 0, "video_path": str(video), "generation": 1},
        ],
    }
    bg = _fake_bg(event_dir, video, beat)
    responses: list = []
    h = MagicMock()
    h.app.event_dir = event_dir
    h._assert_event_scope.return_value = True
    h._scope_body.side_effect = lambda body: body
    h._send_json.side_effect = lambda code, body: responses.append(("ok", code, body))
    h._send_error_v59.side_effect = lambda *a, **k: responses.append(("err", a, k))

    monkeypatch.setattr(bgh, "_bg_module", lambda: bg)
    monkeypatch.setattr(bgh, "_bg_o3_trim_audit", lambda *_a, **_k: None)
    monkeypatch.setattr(bgh, "_data_root", lambda _h: tmp_path)

    import server_handlers.milestone_scope as ms

    @contextmanager
    def _lock():
        yield

    monkeypatch.setattr(ms, "production_bg_scope_lock", _lock)
    monkeypatch.setattr(ms, "rebind_bg_paths_from_app", lambda _app: None)

    def _no_stitch(*_a, **_k):
        return []

    monkeypatch.setattr(
        "bg_o3_stitch_invalidation.invalidate_stitch_slot_for_bg_o3_selection_change",
        _no_stitch,
        raising=False,
    )

    bgh.handle_bg_kling_o3_trim(h, _option_trim_body(preview_only=preview_only))

    assert bg.captured.get("event_dir") == event_dir
    assert responses, "handler returned without send_json/send_error"
    assert responses[0][0] == "ok", responses
    assert responses[0][1] == 200
    assert responses[0][2].get("ok") is True
