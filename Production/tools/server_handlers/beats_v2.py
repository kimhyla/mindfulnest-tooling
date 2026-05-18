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
        return h._send_json(e.http_status, {"status": "error", "error": e.code, **e.detail})

    parts = [p for p in path.split("/") if p]
    if len(parts) != 5 or parts[0] != "api" or parts[1] != "v2" or parts[2] != "beat" or parts[4] != "patch":
        return h._send_json(400, {"status": "error", "error": f"malformed path: {path!r}"})
    beat_id = parts[3]

    field = body.get("field")
    value = body.get("value")
    mutation_id = body.get("mutation_id")
    expected_version = body.get("expected_version")

    if not field:
        return h._send_json(400, {"status": "error", "error": "missing 'field'"})

    if field == "dialogue":
        if os.environ.get("MINDFULNEST_WRITE_PATH", "v2") == "legacy":
            return h._send_json(503, {
                "status": "disabled",
                "error": "v2 write path disabled via MINDFULNEST_WRITE_PATH=legacy",
            })
        if not isinstance(value, str):
            return h._send_json(400, {
                "status": "error",
                "error": f"dialogue value must be str, got {type(value).__name__}",
            })
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
        return h._send_json(e.http_status, {"error": e.code, **e.detail})

    if os.environ.get("MINDFULNEST_WRITE_PATH", "v2") == "legacy":
        return h._send_json(503, {
            "status": "disabled",
            "error": "v2 write path disabled via MINDFULNEST_WRITE_PATH=legacy",
        })
    if not _t1_enabled():
        return h._send_json(503, {
            "status": "disabled",
            "error": "Tier 1 feature flag disabled (MINDFULNEST_T1_ENABLED=0)",
        })

    insert_after = body.get("insert_after")
    if insert_after is not None and not isinstance(insert_after, str):
        return h._send_json(400, {
            "status": "error",
            "error": f"insert_after must be str or null, got {type(insert_after).__name__}",
        })

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
        return h._send_json(500, {
            "status": "error",
            "error": f"beat create failed: {type(exc).__name__}: {exc}",
        })

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
            _libdir = os.path.join(os.path.dirname(__file__), os.pardir, "credentials_lib")
            if _libdir not in sys.path:
                sys.path.insert(0, _libdir)
            from credentials import load_credentials  # type: ignore
            from directus import DirectusClient  # type: ignore
            creds = load_credentials()
            dc = DirectusClient(
                creds["directus_url"],
                creds["directus_email"],
                creds["directus_password"],
            )
            dc.create("prod_activity_log", {
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
        return h._send_json(e.http_status, {"error": e.code, **e.detail})

    beat_id = body.get("beat_id")
    if not isinstance(beat_id, str) or not beat_id:
        return h._send_json(400, {"error": "beat_id required and must be non-empty string"})

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
        return h._send_json(500, {
            "error": f"beat delete failed: {type(exc).__name__}: {exc}",
        })

    if result_out.get("not_found"):
        return h._send_json(404, {"error": f"beat {beat_id!r} not found"})

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
        return h._send_json(400, {"error": f"malformed path: {path!r}"})
    beat_id = parts[3]
    state = h.app.state.read_state()
    beat = (((state.get("videos") or {}).get("intro") or {}).get("beats") or {}).get(beat_id)
    if beat is None:
        return h._send_json(404, {"error": f"beat {beat_id!r} not found"})
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
                return h._send_json(409, {
                    "error": "scope_mismatch",
                    "code": "SCOPE_VALIDATION_V1",
                    "expected_event_id": server_event,
                    "got_event_id": client_event,
                })
    except Exception:
        pass
    sidecar_path = h.app.event_dir / (h.app.storyboard_path.stem + ".L.json")
    if not sidecar_path.exists():
        try:
            state = h.app.state.read_state()
            _write_sidecar_L_json(h.app, state)
        except Exception as exc:  # noqa: BLE001
            return h._send_json(404, {"error": "sidecar not yet materialized", "detail": str(exc)})
    if not sidecar_path.exists():
        return h._send_json(404, {"error": "sidecar unavailable"})
    try:
        body = sidecar_path.read_bytes()
    except OSError as exc:
        return h._send_json(500, {"error": f"sidecar read failed: {exc}"})
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
                return h._send_json(409, {
                    "error": "scope_mismatch",
                    "code": "SCOPE_VALIDATION_V1",
                    "expected_event_id": server_event,
                    "got_event_id": url_event,
                    "hint": (
                        "URL <event_id> path component does not match "
                        "the event this server is pinned to. Reload your "
                        "client tab to re-resolve scope."
                    ),
                })
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
                if not _beat.get("image_path") and _ap and os.path.isfile(_ap):
                    try:
                        _beat["image_path"] = os.path.relpath(_ap, event_dir_abs)
                    except ValueError:
                        pass
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
        return h._send_json(423, {
            "error": "event_changed_pre_work",
            "code": "ASYNC_JOB_GENERATION_PIN_V1",
            "handler": "v2_module_patch",
        })

    field = body.get("field")
    value = body.get("value")
    if not field:
        return h._send_json(400, {
            "status": "error", "error": "missing 'field'",
            "hint": "Body must include 'field' and 'value'.",
        })
    if field not in _V2_MODULE_ALLOWED_FIELDS:
        return h._send_json(400, {
            "status": "error",
            "error": f"field {field!r} not in module whitelist",
            "hint": f"Allowed: {sorted(_V2_MODULE_ALLOWED_FIELDS)}",
        })
    validator = _V2_MODULE_FIELD_VALIDATORS.get(field)
    if validator is None:
        return h._send_json(500, {
            "status": "error",
            "error": f"field {field!r} whitelisted but has no validator",
            "hint": "Internal: add a _V2_MODULE_FIELD_VALIDATORS entry.",
        })
    try:
        value = validator(value)
    except ValueError as exc:
        return h._send_json(400, {
            "status": "error",
            "error": f"{field}: {exc}",
            "hint": f"Validator rejected the value. See error detail for the specific constraint.",
        })
    except (TypeError, KeyError) as exc:
        return h._send_json(400, {
            "status": "error",
            "error": f"{field}: {type(exc).__name__}: {exc}",
            "hint": "Value shape does not match field's schema.",
        })

    def _apply(state, _f=field, _v=value):
        state[_f] = _v
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]

    if not h._check_event_pin(_pin, "phase_b_mix_audio_apply_mutate"):
        return h._send_json(423, {"error": "event_changed_mid_job", "code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": "phase_b_mix_audio"})
    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_json(500, {
            "status": "error",
            "error": f"mutate_state failed: {type(exc).__name__}: {exc}",
            "hint": "State.json could not be persisted. Check Directus reachability.",
        })

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
        return h._send_json(e.http_status, {"error": e.code, **e.detail})

    from_slot = body.get("from_slot")
    if not isinstance(from_slot, int) or isinstance(from_slot, bool):
        return h._send_json(400, {
            "error": f"from_slot must be int >= 2, got {from_slot!r}",
            "hint": "Body must include {\"from_slot\": N} where N is 2 (Option B), 3 (Option C), 4 (Option D), etc.",
        })
    if from_slot < 2:
        return h._send_json(400, {
            "error": f"from_slot must be >= 2, got {from_slot}",
            "hint": "Slot 1 is already A — nothing to swap. Pass 2 (B), 3 (C), 4 (D), etc.",
        })

    pre_state = h.app.state.read_state()
    pre_partition = ((pre_state.get("videos") or {}).get(scope.video_role) or {})
    pre_beat = (pre_partition.get("beats") or {}).get(beat_id)
    if pre_beat is None:
        return h._send_json(400, {
            "error": f"beat {beat_id!r} not found in videos.{scope.video_role}.beats",
            "hint": "Verify beat_id exists in the partition. Check /api/v2/event/<id>/state.",
        })
    pre_phase1 = pre_beat.get("phase_1") or {}
    pre_options = pre_phase1.get("options") or []
    if len(pre_options) < from_slot:
        return h._send_json(400, {
            "error": f"phase_1 has {len(pre_options)} option(s); cannot swap from slot {from_slot}",
            "hint": f"Beat must have at least {from_slot} options for from_slot={from_slot}.",
        })
    src_option = pre_options[from_slot - 1]
    if not isinstance(src_option, dict) or not src_option.get("file"):
        return h._send_json(400, {
            "error": f"option at slot {from_slot} is empty or missing a file",
            "hint": "Cannot swap an empty/pending option into slot A. Generate it first.",
        })

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
        return h._send_json(400, {
            "error": f"swap failed: {exc}",
            "hint": "State changed between pre-flight and mutate. Retry.",
        })
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_json(500, {
            "error": f"mutate_video_state failed: {type(exc).__name__}: {exc}",
            "hint": "State.json could not be persisted. Check Directus reachability.",
        })

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
