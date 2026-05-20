# TECHNICAL DEBT: _send_json error paths in this module remain pre-V59
# Phase 7 (per PR #60 scope). Continued migration tracked under
# SHORTCUT_V59_PHASE_7_BEATS_V2_MIGRATION_V1 (to be locked in a follow-up
# pass). The helper docstring documents dual-shape acceptance, so this is
# not a client-break — only governance hygiene.
"""V2 beat/state handlers — V59 Phase 4 Pass 1 module 3.

Handlers extracted from production_server.py for /api/v2/* routes.
Each function takes the live `ProductionHandler` instance as `h`.
"""
from __future__ import annotations

import os
import sys
import threading
import traceback
import urllib.parse
from datetime import datetime, timezone

import scope_router
from lib.paths import DROPBOX_ROOT

# V59 Phase 4 cross-review fix (CI follow-up):
# missing module-level references from extracted handler bodies.
from tools.production_server import (  # noqa: E402
    TIER1A_ENABLED,
    _t1_enabled,
    _v2_read_beat_version,
    _write_sidecar_L_json,
    patch_state,
)

# V59 Phase 4 cross-review fix (body_key_contract CI failure):
# missing module-level variable references from extracted handler bodies.
from tools.production_server import (  # noqa: E402
    _FORWARDED_V2_DIALOGUE_FIELDS,
    _PATCH_STATE_DEDUP,
    _PATCH_STATE_DEDUP_MAX,
    _V2_MODULE_ALLOWED_FIELDS,
    _V2_MODULE_FIELD_VALIDATORS,
)


def handle_v2_patch(h, path: str, body: dict) -> None:
    """POST /api/v2/beat/<beat_id>/patch"""
    from production_server import (
        TIER1A_ENABLED,
        _FORWARDED_V2_DIALOGUE_FIELDS,
        _PATCH_STATE_DEDUP,
        _PATCH_STATE_DEDUP_MAX,
        _v2_read_beat_version,
        _write_sidecar_L_json,
        patch_state,
    )

    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)
    except scope_router.ScopeError as e:
        return h._send_error_v59(
            e.http_status,
            error_code=e.code.upper(),
            error_message=e.code,
            retry_safe=False,
            extra=e.detail or None,
        )

    parts = [p for p in path.split("/") if p]
    if len(parts) != 5 or parts[0] != "api" or parts[1] != "v2" or parts[2] != "beat" or parts[4] != "patch":
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"malformed path: {path!r}",
                   retry_safe=False,
                   extra={"status": "error"},
               )
    beat_id = parts[3]

    field = body.get("field")
    value = body.get("value")
    mutation_id = body.get("mutation_id")
    expected_version = body.get("expected_version")

    if not field:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_FIELD",
                   error_message="missing 'field'",
                   retry_safe=False,
                   extra={"status": "error"},
               )

    if field == "dialogue":
        if os.environ.get("MINDFULNEST_WRITE_PATH", "v2") == "legacy":
            return h._send_error_v59(
                       503,
                       error_code="V2_WRITE_PATH_DISABLED_VIA",
                       error_message="v2 write path disabled via MINDFULNEST_WRITE_PATH=legacy",
                       retry_safe=True,
                       extra={"status": "disabled"},
                   )
        if not isinstance(value, str):
            return h._send_error_v59(
                       400,
                       error_code="GENERIC_ERROR",
                       error_message=f"dialogue value must be str, got {type(value).__name__}",
                       retry_safe=False,
                       extra={"status": "error"},
                   )
        if mutation_id:
            cached = _PATCH_STATE_DEDUP.get(mutation_id)
            if cached is not None:
                _PATCH_STATE_DEDUP.move_to_end(mutation_id)
                return h._send_json(200, {**cached, "status": "dedup", "cached": True})
        _state_pre = h.app.state.read_state()
        current_v = _v2_read_beat_version(_state_pre, beat_id)
        if expected_version is not None and expected_version != current_v:
            return h._send_json(409, {
                "status": "conflict",
                "current_version": current_v,
                "expected": expected_version,
            })

        _captured = {"status": None, "payload": None}
        _orig_send_json = h._send_json

        def _capture(status, payload):
            _captured["status"] = status
            _captured["payload"] = payload

        h._send_json = _capture  # type: ignore[assignment]
        try:
            legacy_body = {
                "beat": beat_id,
                "text": value,
                "scope_event_id": scope.event_id,
                "scope_target_video": scope.video_role,
            }
            if TIER1A_ENABLED:
                for _f in _FORWARDED_V2_DIALOGUE_FIELDS:
                    if _f in body:
                        legacy_body[_f] = body[_f]
            h._handle_beat_update_text(legacy_body)
        finally:
            h._send_json = _orig_send_json  # type: ignore[assignment]

        legacy_status = _captured["status"] or 500
        legacy_payload = _captured["payload"] or {}
        if legacy_status == 200:
            _bump_holder = {"v": None}
            def _bump_partition(partition, _bid=beat_id, _h=_bump_holder):
                b = partition.setdefault("beats", {}).setdefault(_bid, {})
                v = int(b.get("_version", 0) or 0) + 1
                b["_version"] = v
                _h["v"] = v
            try:
                h.app.state.mutate_video_state(scope.video_role, _bump_partition)
                new_v = _bump_holder["v"]
                if new_v is None:
                    new_v = current_v + 1
            except Exception as exc:  # noqa: BLE001
                new_v = current_v + 1
                print(f"[v2 dialogue] version bump failed: {exc}")
            try:
                fresh = h.app.state.read_state()
                _write_sidecar_L_json(h.app, fresh)
            except Exception as exc:  # noqa: BLE001
                print(f"[v2 dialogue] sidecar write failed: {exc}")
            response = {
                "status": "applied",
                "new_version": new_v,
                "beat": {"text": value, "_version": new_v},
                "legacy": legacy_payload,
                "source": "legacy_dialogue_via_v2",
            }
            if mutation_id:
                _PATCH_STATE_DEDUP[mutation_id] = response
                while len(_PATCH_STATE_DEDUP) > _PATCH_STATE_DEDUP_MAX:
                    _PATCH_STATE_DEDUP.popitem(last=False)
            return h._send_json(200, response)
        return h._send_json(legacy_status, {
            "status": "error",
            "error": "legacy dialogue handler rejected",
            "legacy_status": legacy_status,
            "legacy_payload": legacy_payload,
        })

    result = patch_state(
        h.app, beat_id, field, value,
        mutation_id=mutation_id,
        expected_version=expected_version,
        video_role=scope.video_role,
    )
    status = result.get("status")
    if status == "applied" or status == "dedup":
        return h._send_json(200, result)
    if status == "conflict":
        return h._send_json(409, result)
    if status == "disabled":
        return h._send_json(503, result)
    return h._send_json(400, result)


def handle_v2_beat_create(h, body: dict) -> None:
    """POST /api/v2/beat/create — Tier 3 (April 18 2026)."""
    from production_server import (
        _PATCH_STATE_DEDUP,
        _PATCH_STATE_DEDUP_MAX,
        _t1_enabled,
        _write_sidecar_L_json,
    )

    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)
    except scope_router.ScopeError as e:
        return h._send_error_v59(
            e.http_status,
            error_code=e.code.upper(),
            error_message=e.code,
            retry_safe=False,
            extra=e.detail or None,
        )

    if os.environ.get("MINDFULNEST_WRITE_PATH", "v2") == "legacy":
        return h._send_error_v59(
                   503,
                   error_code="V2_WRITE_PATH_DISABLED_VIA",
                   error_message="v2 write path disabled via MINDFULNEST_WRITE_PATH=legacy",
                   retry_safe=True,
                   extra={"status": "disabled"},
               )
    if not _t1_enabled():
        return h._send_error_v59(
                   503,
                   error_code="TIER_FEATURE_FLAG_DISABLED_MINDFULNEST",
                   error_message="Tier 1 feature flag disabled (MINDFULNEST_T1_ENABLED=0)",
                   retry_safe=True,
                   extra={"status": "disabled"},
               )

    insert_after = body.get("insert_after")
    if insert_after is not None and not isinstance(insert_after, str):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"insert_after must be str or null, got {type(insert_after).__name__}",
                   retry_safe=False,
                   extra={"status": "error"},
               )

    mutation_id = body.get("mutation_id")
    if mutation_id:
        cached = _PATCH_STATE_DEDUP.get(mutation_id)
        if cached is not None:
            _PATCH_STATE_DEDUP.move_to_end(mutation_id)
            return h._send_json(200, {**cached, "status": "dedup", "cached": True})

    result_out: dict = {}

    def _apply_partition(partition, _ia=insert_after, _out=result_out):
        beats = partition.setdefault("beats", {})
        max_num = 0
        for bid in beats.keys():
            if not bid.startswith("beat_"):
                continue
            try:
                n = int(bid.split("_", 1)[1])
                if n > max_num:
                    max_num = n
            except (IndexError, ValueError):
                continue
        new_num = max_num + 1
        new_bid = f"beat_{new_num:02d}"
        while new_bid in beats:
            new_num += 1
            new_bid = f"beat_{new_num:02d}"
        _src_bid = _ia if (_ia and _ia in beats) else None
        if not _src_bid:
            _cur_order = partition.get("display_order")
            if isinstance(_cur_order, list) and _cur_order:
                _src_bid = _cur_order[-1]
            elif beats:
                _src_bid = max(beats.keys())
        _inherited_speaker = ""
        if _src_bid and _src_bid in beats:
            _inherited_speaker = (
                beats[_src_bid].get("speaker")
                or (beats[_src_bid].get("phase_1") or {}).get("speaker")
                or ""
            )
        beats[new_bid] = {
            "text": "",
            "speaker": _inherited_speaker,
            "phase_1": {"status": "pending", "options": []},
            "_version": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        existing_order = partition.get("display_order")
        if not isinstance(existing_order, list):
            order = sorted(
                [b for b in beats.keys() if b != new_bid],
                key=lambda s: (len(s), s),
            )
        else:
            order = [b for b in existing_order if b in beats and b != new_bid]
        insert_idx = None
        if _ia and _ia in order:
            insert_idx = order.index(_ia) + 1
            order.insert(insert_idx, new_bid)
        else:
            order.append(new_bid)
            insert_idx = len(order) - 1
        partition["display_order"] = order
        _out["beat_id"] = new_bid
        _out["inserted_after"] = _ia if _ia in (order[:insert_idx]) else None
        _out["display_order_len"] = len(order)

    try:
        h.app.state.mutate_video_state(scope.video_role, _apply_partition)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat create failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"status": "error"},
               )

    try:
        fresh = h.app.state.read_state()
        _write_sidecar_L_json(h.app, fresh)
    except Exception as exc:  # noqa: BLE001
        print(f"[v2 beat_create] sidecar write failed: {exc}")

    response = {
        "status": "created",
        "beat_id": result_out.get("beat_id"),
        "inserted_after": result_out.get("inserted_after"),
        "display_order_len": result_out.get("display_order_len"),
    }
    if mutation_id:
        _PATCH_STATE_DEDUP[mutation_id] = response
        while len(_PATCH_STATE_DEDUP) > _PATCH_STATE_DEDUP_MAX:
            _PATCH_STATE_DEDUP.popitem(last=False)

    def _async_audit():
        try:
            from lib.directus import try_post_or_queue
            try_post_or_queue("prod_activity_log", {
                "action": "v2_beat_create",
                "details": {
                    "task_id": "tier3-server-20260418",
                    "beat_id": response["beat_id"],
                    "inserted_after": response["inserted_after"],
                    "mutation_id": mutation_id,
                    "ld_key": "TIER3_BEAT_CREATE_ENDPOINT",
                },
                "performed_by": "production_server.tier3",
            })
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_async_audit, daemon=True).start()

    return h._send_json(200, response)


def handle_v2_beat_delete(h, body: dict) -> None:
    """POST /api/v2/beat/delete — remove a beat from production state."""
    from production_server import _write_sidecar_L_json

    try:
        scope = scope_router.resolve(body, h.app.event_dir.name)
    except scope_router.ScopeError as e:
        return h._send_error_v59(
            e.http_status,
            error_code=e.code.upper(),
            error_message=e.code,
            retry_safe=False,
            extra=e.detail or None,
        )

    beat_id = body.get("beat_id")
    if not isinstance(beat_id, str) or not beat_id:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_BEAT_ID",
                   error_message="beat_id required and must be non-empty string",
                   retry_safe=False,
               )

    result_out: dict = {}

    def _apply_partition(partition, _bid=beat_id, _out=result_out):
        beats = partition.get("beats") or {}
        if _bid not in beats:
            _out["not_found"] = True
            return
        del beats[_bid]
        order = partition.get("display_order")
        if isinstance(order, list) and _bid in order:
            order.remove(_bid)
        _out["deleted"] = True

    try:
        h.app.state.mutate_video_state(scope.video_role, _apply_partition)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat delete failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
               )

    if result_out.get("not_found"):
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat {beat_id!r} not found",
                   retry_safe=False,
               )

    try:
        fresh = h.app.state.read_state()
        _write_sidecar_L_json(h.app, fresh)
    except Exception as exc:  # noqa: BLE001
        print(f"[v2 beat_delete] sidecar write failed: {exc}")

    return h._send_json(200, {"status": "deleted", "beat_id": beat_id})


def handle_v2_get(h, path: str) -> None:
    """GET /api/v2/beat/<beat_id>"""
    parts = [p for p in path.split("/") if p]
    if len(parts) != 4 or parts[0] != "api" or parts[1] != "v2" or parts[2] != "beat":
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"malformed path: {path!r}",
                   retry_safe=False,
               )
    beat_id = parts[3]
    state = h.app.state.read_state()
    beat = (((state.get("videos") or {}).get("intro") or {}).get("beats") or {}).get(beat_id)
    if beat is None:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat {beat_id!r} not found",
                   retry_safe=False,
               )
    image_key = (((state.get("videos") or {}).get("intro") or {}).get("image_overrides") or {}).get(beat_id)
    return h._send_json(200, {
        "beat_id": beat_id,
        "beat": beat,
        "image_override": image_key,
        "_version": int(beat.get("_version", 0) or 0),
    })


def handle_v2_sidecar(h) -> None:
    """GET /api/v2/storyboard/L.json[?event_id=<id>]"""
    from production_server import _write_sidecar_L_json

    if not h._assert_event_scope({}, allow_missing=True):
        return

    try:
        qs = urllib.parse.urlparse(h.path).query
        params = urllib.parse.parse_qs(qs)
        qs_eid = params.get("event_id")
        if qs_eid:
            client_event = qs_eid[0]
            server_event = h.app.event_dir.name
            if client_event != server_event:
                print(
                    f"[scope-guard] HTTP 409 on GET {h.path}: "
                    f"qs event_id={client_event!r} != server event_id={server_event!r}",
                    flush=True,
                )
                return h._send_error_v59(
                           409,
                           error_code="SCOPE_MISMATCH",
                           error_message="scope_mismatch",
                           retry_safe=False,
                           extra={"code": "SCOPE_VALIDATION_V1", "expected_event_id": server_event, "got_event_id": client_event},
                       )
    except Exception:
        pass
    sidecar_path = h.app.event_dir / (h.app.storyboard_path.stem + ".L.json")
    if not sidecar_path.exists():
        try:
            state = h.app.state.read_state()
            _write_sidecar_L_json(h.app, state)
        except Exception as exc:  # noqa: BLE001
            return h._send_error_v59(
                       404,
                       error_code="SIDECAR_NOT_YET_MATERIALIZED",
                       error_message="sidecar not yet materialized",
                       retry_safe=False,
                       extra={"detail": str(exc)},
                   )
    if not sidecar_path.exists():
        return h._send_error_v59(
                   404,
                   error_code="SIDECAR_UNAVAILABLE",
                   error_message="sidecar unavailable",
                   retry_safe=False,
               )
    try:
        body = sidecar_path.read_bytes()
    except OSError as exc:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"sidecar read failed: {exc}",
                   retry_safe=True,
               )
    h.send_response(200)
    h._cors_headers()
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def handle_v2_event_state(h, path: str) -> None:
    """GET /api/v2/event/<event_id>/state"""
    try:
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 4:
            url_event = parts[3]
            server_event = h.app.event_dir.name
            if url_event != server_event:
                print(
                    f"[scope-guard] HTTP 409 on GET {path}: "
                    f"url event_id={url_event!r} != server event_id={server_event!r}",
                    flush=True,
                )
                return h._send_error_v59(
                           409,
                           error_code="SCOPE_MISMATCH",
                           error_message="scope_mismatch",
                           retry_safe=False,
                           extra={"code": "SCOPE_VALIDATION_V1", "expected_event_id": server_event, "got_event_id": url_event, "hint": "URL <event_id> path component does not match "
                        "the event this server is pinned to. Reload your "
                        "client tab to re-resolve scope."},
                       )
    except Exception as exc:
        print(f"[scope-guard] WARN: URL parse on {path} raised {exc!r}; "
              f"falling through to server-pinned event.", flush=True)
    state = h.app.state.read_state()
    try:
        event_dir_abs = str((DROPBOX_ROOT / h.app.event_dir).resolve())
        for _role, _part in (state.get("videos") or {}).items():
            if not isinstance(_part, dict):
                continue
            _abs_map = _part.get("image_overrides_abs") or {}
            _beats = _part.setdefault("beats", {})
            for _bid, _ap in _abs_map.items():
                _beat = _beats.setdefault(_bid, {})
                # Blocker #145 / DS-22: image_overrides_abs is canonical; always
                # project image_path so drag-drop crop updates render (old guard
                # only filled when image_path was absent → stale thumb).
                if _ap and os.path.isfile(_ap):
                    try:
                        _beat["image_path"] = os.path.relpath(_ap, event_dir_abs)
                    except ValueError:
                        print(
                            f"[v2-state] WARN: image_path relpath failed for "
                            f"beat_id={_bid!r} source={_ap!r} "
                            f"(outside event dir {event_dir_abs!r}); "
                            f"keeping prior image_path={_beat.get('image_path')!r}",
                            file=sys.stderr,
                            flush=True,
                        )
    except Exception as _exc:
        print(f"[v2-state] WARN: image_path projection failed: {_exc!r}", flush=True)

    try:
        clips_dir = h.app.state.clips_dir
        for _role, _part in (state.get("videos") or {}).items():
            if not isinstance(_part, dict):
                continue
            for _bid, _beat in (_part.get("beats") or {}).items():
                if not isinstance(_beat, dict):
                    continue
                _ls = _beat.get("lipsync")
                if not isinstance(_ls, dict):
                    continue
                _fname = _ls.get("file")
                if not _fname:
                    continue
                _fp = clips_dir / _fname
                try:
                    if _fp.is_file():
                        _ls["file_mtime"] = int(_fp.stat().st_mtime)
                except OSError:
                    pass
    except Exception as _exc:
        print(f"[v2-state] WARN: lipsync file_mtime projection failed: {_exc!r}", flush=True)

    # Tier 1 / T1-1 (2026-05-19) — file_exists enrichment for every *.file
    # ref. Closes Kim's smoke #1-3 (archived option ▶ → generic codec toast).
    # PR #73 + P3 added this to /api/state but the v59 client hydrates from
    # THIS endpoint (/api/v2/event/<id>/state) — feature-parity audit T1-1.
    # Mirrors production_server._read_state_with_file_flags._annotate_block.
    try:
        clips_dir = h.app.state.clips_dir
        event_dir = h.app.event_dir  # Bug-B3 (spec §2 Topic-2): magic + end_frame
        end_frames_dir = event_dir / "end_frames"

        def _annotate(block, field: str = "file") -> None:
            if not isinstance(block, dict):
                return
            f = block.get(field)
            if field == "image_path":
                block["image_path_exists"] = bool(
                    f and isinstance(f, str) and os.path.exists(f)
                )
            else:
                block["file_exists"] = bool(f and (clips_dir / f).is_file())

        # Bug-B3 (spec §2 Topic-2, 2026-05-20): annotate magic + end_frame
        # paths which resolve against EVENT_DIR (not clips_dir). Without these,
        # orphan references silently 404 on <video src=...>. Mirrors the
        # production_server._read_state_with_file_flags extension.
        def _annotate_beat_field(beat: dict, field: str, base_dir) -> None:
            if not isinstance(beat, dict):
                return
            f = beat.get(field)
            if not (f and isinstance(f, str)):
                beat[f"{field}_exists"] = False
                return
            beat[f"{field}_exists"] = (base_dir / f).is_file()

        for _role, _part in (state.get("videos") or {}).items():
            if not isinstance(_part, dict):
                continue
            for _bid, _beat in (_part.get("beats") or {}).items():
                if not isinstance(_beat, dict):
                    continue
                _p1 = _beat.get("phase_1")
                if isinstance(_p1, dict):
                    for _opt in (_p1.get("options") or []):
                        _annotate(_opt)
                _p2 = _beat.get("phase_2")
                if isinstance(_p2, dict):
                    for _opt in (_p2.get("options") or []):
                        _annotate(_opt)
                _annotate(_beat.get("lipsync"))
                _final = _beat.get("final")
                if isinstance(_final, dict):
                    _annotate(_final, "file")
                    _annotate(_final, "image_path")
                # Bug-B3 — magic_*_path resolves to event_dir
                _annotate_beat_field(_beat, "magic_still_path", event_dir)
                _annotate_beat_field(_beat, "magic_video_path", event_dir)
                # Bug-B3 — end_frame_path resolves to event_dir/end_frames/
                _annotate_beat_field(_beat, "end_frame_path", end_frames_dir)
    except Exception as _exc:
        print(f"[v2-state] WARN: file_exists enrichment failed: {_exc!r}", flush=True)

    return h._send_json(200, state)


def handle_v2_module_patch(h, body: dict) -> None:
    """POST /api/v2/module/patch"""
    from production_server import (
        _V2_MODULE_ALLOWED_FIELDS,
        _V2_MODULE_FIELD_VALIDATORS,
        _write_sidecar_L_json,
    )

    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": "v2_module_patch",
    }
    if not h._check_event_pin(_pin, "v2_module_patch_pre_work"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": "v2_module_patch"},
               )

    field = body.get("field")
    value = body.get("value")
    if not field:
        return h._send_error_v59(
                   400,
                   error_code="MISSING_FIELD",
                   error_message="missing 'field'",
                   retry_safe=False,
                   extra={"status": "error", "hint": "Body must include 'field' and 'value'."},
               )
    if field not in _V2_MODULE_ALLOWED_FIELDS:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"field {field!r} not in module whitelist",
                   retry_safe=False,
                   extra={"status": "error", "hint": f"Allowed: {sorted(_V2_MODULE_ALLOWED_FIELDS)}"},
               )
    validator = _V2_MODULE_FIELD_VALIDATORS.get(field)
    if validator is None:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"field {field!r} whitelisted but has no validator",
                   retry_safe=True,
                   extra={"status": "error", "hint": "Internal: add a _V2_MODULE_FIELD_VALIDATORS entry."},
               )
    try:
        value = validator(value)
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"{field}: {exc}",
                   retry_safe=False,
                   extra={"status": "error", "hint": f"Validator rejected the value. See error detail for the specific constraint."},
               )
    except (TypeError, KeyError) as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"{field}: {type(exc).__name__}: {exc}",
                   retry_safe=False,
                   extra={"status": "error", "hint": "Value shape does not match field's schema."},
               )

    def _apply(state, _f=field, _v=value):
        state[_f] = _v
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]

    if not h._check_event_pin(_pin, "phase_b_mix_audio_apply_mutate"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": "phase_b_mix_audio"},
               )
    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"status": "error", "hint": "State.json could not be persisted. Check Directus reachability."},
               )

    try:
        fresh = h.app.state.read_state()
        _write_sidecar_L_json(h.app, fresh)
    except Exception as exc:  # noqa: BLE001
        print(f"[v2 module_patch] sidecar write failed: {exc}")

    return h._send_json(200, {
        "status": "applied",
        "field": field,
        "value": value,
        "new_version": new_version,
    })


def handle_v2_beat_swap_to_a(h, beat_id: str, body: dict) -> None:
    """POST /api/v2/beat/<beat_id>/swap_to_a — park a B/C favorite in slot A."""
    from production_server import _write_sidecar_L_json

    try:
        scope = scope_router.resolve(body, h.app.event_dir.name, require_beat_id=False)
    except scope_router.ScopeError as e:
        return h._send_error_v59(
            e.http_status,
            error_code=e.code.upper(),
            error_message=e.code,
            retry_safe=False,
            extra=e.detail or None,
        )

    from_slot = body.get("from_slot")
    if not isinstance(from_slot, int) or isinstance(from_slot, bool):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"from_slot must be int >= 2, got {from_slot!r}",
                   retry_safe=False,
                   extra={"hint": "Body must include {\"from_slot\": N} where N is 2 (Option B), 3 (Option C), 4 (Option D), etc."},
               )
    if from_slot < 2:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"from_slot must be >= 2, got {from_slot}",
                   retry_safe=False,
                   extra={"hint": "Slot 1 is already A — nothing to swap. Pass 2 (B), 3 (C), 4 (D), etc."},
               )

    pre_state = h.app.state.read_state()
    pre_partition = ((pre_state.get("videos") or {}).get(scope.video_role) or {})
    pre_beat = (pre_partition.get("beats") or {}).get(beat_id)
    if pre_beat is None:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"beat {beat_id!r} not found in videos.{scope.video_role}.beats",
                   retry_safe=False,
                   extra={"hint": "Verify beat_id exists in the partition. Check /api/v2/event/<id>/state."},
               )
    pre_phase1 = pre_beat.get("phase_1") or {}
    pre_options = pre_phase1.get("options") or []
    if len(pre_options) < from_slot:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"phase_1 has {len(pre_options)} option(s); cannot swap from slot {from_slot}",
                   retry_safe=False,
                   extra={"hint": f"Beat must have at least {from_slot} options for from_slot={from_slot}."},
               )
    src_option = pre_options[from_slot - 1]
    if not isinstance(src_option, dict) or not src_option.get("file"):
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"option at slot {from_slot} is empty or missing a file",
                   retry_safe=False,
                   extra={"hint": "Cannot swap an empty/pending option into slot A. Generate it first."},
               )

    result_out: dict = {}

    def _apply_partition(partition, _bid=beat_id, _fs=from_slot, _out=result_out):
        beats = partition.setdefault("beats", {})
        beat = beats.get(_bid)
        if beat is None:
            raise KeyError(f"beat {_bid!r} not found at mutate time")
        phase1 = beat.setdefault("phase_1", {})
        options = phase1.setdefault("options", [])
        if len(options) < _fs:
            raise IndexError(
                f"phase_1 options shrank to {len(options)} before swap (expected >= {_fs})"
            )
        options[0], options[_fs - 1] = options[_fs - 1], options[0]

        sel = phase1.get("selected_option")
        if isinstance(sel, int):
            if sel == _fs:
                phase1["selected_option"] = 1
            elif sel == 1:
                phase1["selected_option"] = _fs

        ls = beat.get("lipsync")
        new_src_opt = None
        if isinstance(ls, dict):
            src_opt = ls.get("source_option")
            if isinstance(src_opt, int):
                if src_opt == _fs:
                    ls["source_option"] = 1
                elif src_opt == 1:
                    ls["source_option"] = _fs
            new_src_opt = ls.get("source_option")
            if "source_changed" in ls:
                ls["source_changed"] = False
            if "audio_changed" in ls:
                ls["audio_changed"] = False

        beat["_version"] = int(beat.get("_version", 0) or 0) + 1

        _out["beat"] = beat
        _out["new_selected_option"] = phase1.get("selected_option")
        _out["new_source_option"] = new_src_opt
        _out["new_version"] = beat["_version"]
        return _out

    try:
        h.app.state.mutate_video_state(scope.video_role, _apply_partition)
    except (KeyError, IndexError) as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"swap failed: {exc}",
                   retry_safe=False,
                   extra={"hint": "State changed between pre-flight and mutate. Retry."},
               )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"mutate_video_state failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "State.json could not be persisted. Check Directus reachability."},
               )

    try:
        fresh = h.app.state.read_state()
        _write_sidecar_L_json(h.app, fresh)
    except Exception as exc:  # noqa: BLE001
        print(f"[v2 swap_to_a] sidecar write failed: {exc}")

    return h._send_json(200, {
        "status": "swapped",
        "beat": beat_id,
        "from_slot": from_slot,
        "to_slot": 1,
        "new_selected_option": result_out.get("new_selected_option"),
        "new_source_option": result_out.get("new_source_option"),
        "new_version": result_out.get("new_version"),
    })
