"""
Schema-aware payload validator for prod_* Directus collections + override file loader.

Normative design: Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v4.md (v4-D row §0.1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional, Set

from lib.directus_admin_client import DirectusAdminClient

# -----------------------------------------------------------------------------
# Public vocabulary + registry (§3.9, §5)
# -----------------------------------------------------------------------------

OVERRIDE_FILE_REASON_VOCAB: Set[str] = {
    "truly_absent",
    "broken_symlink",
    "toctou_vanished",
    "metadata_os_error",
    "json_parse_error",
    "layout_error",
    "permission_denied",
    "io_error",
}

RETIRED_FIELDS_REGISTRY: dict[str, dict[str, str]] = {}

# Duplicate of lib/directus._AUTO_FIELDS — keep validator import-light vs directus.py.
_AUTO_FIELDS: Set[str] = {
    "id",
    "date_created",
    "date_updated",
    "created_at",
    "updated_at",
    "user_created",
    "user_updated",
    "sort",
}

_SCHEMA_TTL_SEC = 15 * 60
_SCHEMA_CACHE: dict[str, tuple[set[str], float]] = {}
_OVERRIDE_DATA: dict[str, Any] = {}
_OVERRIDE_LOAD_PATH: Optional[str] = None

_VALIDATOR_INTERNAL_BYPASS = threading.local()
_LOG = logging.getLogger(__name__)

# Lazy Directus client for validator-emitted activity rows (optional when creds missing).
_ACTIVITY_CLIENT: DirectusAdminClient | None | bool = False

ModeName = Literal["strict", "warn", "skip"]


class OverrideFileMalformedError(Exception):
    """§3.10 — path is always str; kind is a §3.9 token; cause is optional BaseException."""

    def __init__(self, path: str, kind: str, cause: Optional[BaseException]) -> None:
        super().__init__(f"override file malformed: {path}: {kind}")
        self.path = path
        self.kind = kind
        self.cause = cause


class SchemaProbeError(Exception):
    def __init__(self, collection: str, cause: BaseException) -> None:
        super().__init__(f"schema probe failed for {collection}: {cause}")
        self.collection = collection
        self.cause = cause


class UnknownPayloadKeyError(Exception):
    def __init__(self, collection: str, keys: list[str]) -> None:
        super().__init__(f"unknown payload keys for {collection}: {keys}")
        self.collection = collection
        self.keys = keys


class RetiredPayloadKeyError(Exception):
    def __init__(self, collection: str, field: str, retire_date: str) -> None:
        super().__init__(
            f"retired field {field!r} for {collection} (retire_date={retire_date}) out of grace window"
        )
        self.collection = collection
        self.field = field
        self.retire_date = retire_date


# -----------------------------------------------------------------------------
# Paths + env
# -----------------------------------------------------------------------------


def _default_state_dir() -> Path:
    return Path(os.path.expanduser("~/.claude/state"))


def _override_file_path() -> Path:
    env = os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_PATH")
    if env:
        return Path(env).expanduser()
    return _default_state_dir() / "payload_validator_overrides.json"


def _log_file_path() -> Path:
    env = os.environ.get("MN_PAYLOAD_VALIDATOR_LOG_PATH")
    if env:
        return Path(env).expanduser()
    return _default_state_dir() / "payload_validator.log"


def _fail_mode_loud() -> bool:
    return os.environ.get("MN_PAYLOAD_VALIDATOR_OVERRIDE_FILE_FAIL_MODE") == "loud"


def _validator_disabled() -> bool:
    return os.environ.get("MN_PAYLOAD_VALIDATOR_DISABLE") == "1"


# -----------------------------------------------------------------------------
# Bypass (§9.3) — prevents re-entry when posting validator diagnostics.
# -----------------------------------------------------------------------------


@contextmanager
def _internal_bypass() -> Any:
    prev = getattr(_VALIDATOR_INTERNAL_BYPASS, "active", False)
    _VALIDATOR_INTERNAL_BYPASS.active = True
    try:
        yield
    finally:
        _VALIDATOR_INTERNAL_BYPASS.active = prev


def _bypass_active() -> bool:
    return bool(getattr(_VALIDATOR_INTERNAL_BYPASS, "active", False))


# -----------------------------------------------------------------------------
# Override layout (v3 §9.2 layout rules; vocab Case D → layout_error)
# -----------------------------------------------------------------------------


def _validate_override_layout(parsed: Any) -> bool:
    if not isinstance(parsed, dict):
        return False
    for coll, cfg in parsed.items():
        if not isinstance(coll, str) or not coll.startswith("prod_"):
            return False
        if not isinstance(cfg, dict):
            return False
        allowed_sub = {"mode", "extra_allowed_keys", "max_payload_size_bytes", "_note"}
        if any(k not in allowed_sub for k in cfg):
            return False
        if "mode" in cfg and cfg["mode"] not in ("strict", "warn", "skip"):
            return False
        if "extra_allowed_keys" in cfg:
            eak = cfg["extra_allowed_keys"]
            if not isinstance(eak, list) or not all(isinstance(x, str) for x in eak):
                return False
        if "max_payload_size_bytes" in cfg:
            m = cfg["max_payload_size_bytes"]
            if not isinstance(m, int) or isinstance(m, bool) or m < 0:
                return False
    return True


def _describe_layout_failure(parsed: Any) -> str:
    if not isinstance(parsed, dict):
        return "top_level_not_object"
    for coll, cfg in parsed.items():
        if not isinstance(coll, str) or not coll.startswith("prod_"):
            return f"bad_collection_key:{coll!r}"
        if not isinstance(cfg, dict):
            return f"collection_value_not_object:{coll!r}"
        allowed_sub = {"mode", "extra_allowed_keys", "max_payload_size_bytes", "_note"}
        bad = [k for k in cfg if k not in allowed_sub]
        if bad:
            return f"unknown_subkeys:{coll}:{bad}"
        if "mode" in cfg and cfg["mode"] not in ("strict", "warn", "skip"):
            return f"bad_mode:{coll}:{cfg['mode']!r}"
        if "extra_allowed_keys" in cfg:
            eak = cfg["extra_allowed_keys"]
            if not isinstance(eak, list) or not all(isinstance(x, str) for x in eak):
                return f"bad_extra_allowed_keys:{coll}"
        if "max_payload_size_bytes" in cfg:
            m = cfg["max_payload_size_bytes"]
            if not isinstance(m, int) or isinstance(m, bool) or m < 0:
                return f"bad_max_payload_size_bytes:{coll}"
    return "unknown_layout_failure"


# -----------------------------------------------------------------------------
# Activity client + Rule 35 read-back
# -----------------------------------------------------------------------------


def _activity_client(explicit: Optional[DirectusAdminClient]) -> Optional[DirectusAdminClient]:
    if explicit is not None:
        return explicit
    global _ACTIVITY_CLIENT
    if _ACTIVITY_CLIENT is False:
        try:
            _ACTIVITY_CLIENT = DirectusAdminClient()
        except RuntimeError:
            _ACTIVITY_CLIENT = None
    return _ACTIVITY_CLIENT if _ACTIVITY_CLIENT else None


def _post_prod_activity_log(client: DirectusAdminClient, body: dict) -> None:
    """LD-597: only action, details, performed_by, module_id."""
    with _internal_bypass():
        created = client.post_item("prod_activity_log", body, retry_post=True)
        if not isinstance(created, dict):
            return
        item_id = created.get("id")
        if item_id is None:
            return
        client.get_item("prod_activity_log", item_id)


def _append_log_line(message: str) -> None:
    log_path = _log_file_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except OSError as exc:
        _LOG.error("payload_validator log write failed: %s", exc)


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _emit_override_malformed(
    *,
    path_obj: Path,
    case_id: str,
    reason: str,
    client: Optional[DirectusAdminClient],
    content_bytes: Optional[bytes],
    parse_error: Optional[str],
    layout_error: Optional[str],
    os_error: Optional[str],
    errno_val: Optional[int],
    symlink_target: Optional[str],
    recovery_action: str,
    fail_mode: str,
    raise_exc: Optional[OverrideFileMalformedError],
) -> None:
    try:
        path_abs = str(path_obj.resolve())
    except OSError:
        path_abs = str(path_obj)

    sha_hex: Optional[str] = None
    if content_bytes is not None:
        sha_hex = hashlib.sha256(content_bytes).hexdigest()

    extras: list[str] = [
        f"path={path_abs}",
        f"case={case_id}",
        f"reason={reason}",
    ]
    if os_error:
        extras.append(f"os_error={os_error}")
    if parse_error:
        extras.append(f"parse_error={parse_error}")
    if layout_error:
        extras.append(f"layout_error={layout_error}")

    log_line = (
        f"[PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED] {_iso_utc()} "
        + " ".join(extras)
    )
    _append_log_line(log_line)

    details: dict[str, Any] = {
        "path": path_abs,
        "case": case_id,
        "reason": reason,
        "content_sha256": sha_hex,
        "attempted_at": _iso_utc(),
        "recovery_action": recovery_action,
        "fail_mode": fail_mode,
    }
    if parse_error is not None:
        details["parse_error"] = parse_error
    if layout_error is not None:
        details["layout_error"] = layout_error
    if os_error is not None:
        details["os_error"] = os_error
    if errno_val is not None:
        details["errno"] = errno_val
    if symlink_target is not None:
        details["symlink_target"] = symlink_target

    dc = _activity_client(client)
    if dc is not None:
        payload = {
            "action": "PAYLOAD_VALIDATOR_OVERRIDE_FILE_MALFORMED",
            "details": details,
            "performed_by": "payload_validator",
            "module_id": None,
        }
        _post_prod_activity_log(dc, payload)

    if raise_exc is not None:
        raise raise_exc


# -----------------------------------------------------------------------------
# Override file loader — §9.2 resolution order: A → A3 → A1 → A2 → E → E2 → C → D → B
# -----------------------------------------------------------------------------


def _fs_lstat(path: Path) -> Any:
    return path.lstat()


def _fs_is_symlink(path: Path) -> bool:
    return path.is_symlink()


def _fs_exists(path: Path) -> bool:
    return path.exists()


def _fs_read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def load_override_file(path: Optional[Path] = None, client: Optional[DirectusAdminClient] = None) -> dict[str, Any]:
    """Public entry for tests — loads override JSON dict or {} on fail-safe paths."""
    p = path if path is not None else _override_file_path()
    return _load_override_at(p, client=client)


def _load_override_at(path_obj: Path, client: Optional[DirectusAdminClient]) -> dict[str, Any]:
    global _OVERRIDE_LOAD_PATH
    _OVERRIDE_LOAD_PATH = str(path_obj)
    loud = _fail_mode_loud()
    recovery = "raised_OverrideFileMalformedError" if loud else "defaults_used"
    fm = "loud" if loud else "safe"

    def _maybe_raise(kind: str, cause: Optional[BaseException]) -> Optional[OverrideFileMalformedError]:
        if not loud:
            return None
        return OverrideFileMalformedError(str(path_obj), kind, cause)

    # Case A vs A3 — lstat
    try:
        _fs_lstat(path_obj)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="A3",
            reason="metadata_os_error",
            client=client,
            content_bytes=None,
            parse_error=None,
            layout_error=None,
            os_error=str(exc),
            errno_val=getattr(exc, "errno", None),
            symlink_target=None,
            recovery_action=recovery,
            fail_mode=fm,
            raise_exc=_maybe_raise("metadata_os_error", exc),
        )
        return {}

    # Case A1 / A2 / secondary A3 — metadata after lstat
    try:
        is_link = _fs_is_symlink(path_obj)
        exists_now = _fs_exists(path_obj)
    except OSError as exc:
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="A3",
            reason="metadata_os_error",
            client=client,
            content_bytes=None,
            parse_error=None,
            layout_error=None,
            os_error=str(exc),
            errno_val=getattr(exc, "errno", None),
            symlink_target=None,
            recovery_action=recovery,
            fail_mode=fm,
            raise_exc=_maybe_raise("metadata_os_error", exc),
        )
        return {}

    symlink_target: Optional[str] = None
    if is_link and not exists_now:
        try:
            symlink_target = os.readlink(path_obj)
        except OSError:
            symlink_target = None
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="A1",
            reason="broken_symlink",
            client=client,
            content_bytes=None,
            parse_error=None,
            layout_error=None,
            os_error=None,
            errno_val=None,
            symlink_target=symlink_target,
            recovery_action=recovery,
            fail_mode=fm,
            raise_exc=_maybe_raise("broken_symlink", None),
        )
        return {}

    if not exists_now:
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="A2",
            reason="toctou_vanished",
            client=client,
            content_bytes=None,
            parse_error=None,
            layout_error=None,
            os_error=None,
            errno_val=None,
            symlink_target=None,
            recovery_action=recovery,
            fail_mode=fm,
            raise_exc=_maybe_raise("toctou_vanished", None),
        )
        return {}

    # Case E / E2 — read
    content_bytes: Optional[bytes] = None
    try:
        content_bytes = _fs_read_bytes(path_obj)
    except PermissionError as exc:
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="E",
            reason="permission_denied",
            client=client,
            content_bytes=None,
            parse_error=None,
            layout_error=None,
            os_error=str(exc),
            errno_val=getattr(exc, "errno", None),
            symlink_target=None,
            recovery_action=recovery,
            fail_mode=fm,
            raise_exc=_maybe_raise("permission_denied", exc),
        )
        return {}
    except OSError as exc:
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="E2",
            reason="io_error",
            client=client,
            content_bytes=None,
            parse_error=None,
            layout_error=None,
            os_error=str(exc),
            errno_val=getattr(exc, "errno", None),
            symlink_target=None,
            recovery_action=recovery,
            fail_mode=fm,
            raise_exc=_maybe_raise("io_error", exc),
        )
        return {}

    assert content_bytes is not None
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="E2",
            reason="io_error",
            client=client,
            content_bytes=content_bytes,
            parse_error=None,
            layout_error=None,
            os_error=str(exc),
            errno_val=getattr(exc, "errno", None),
            symlink_target=None,
            recovery_action=recovery,
            fail_mode=fm,
            raise_exc=_maybe_raise("io_error", exc),
        )
        return {}

    # Case C
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="C",
            reason="json_parse_error",
            client=client,
            content_bytes=content_bytes,
            parse_error=str(exc),
            layout_error=None,
            os_error=None,
            errno_val=None,
            symlink_target=None,
            recovery_action=recovery,
            fail_mode=fm,
            raise_exc=_maybe_raise("json_parse_error", exc),
        )
        return {}

    # Case D
    if not _validate_override_layout(parsed):
        desc = _describe_layout_failure(parsed)
        _emit_override_malformed(
            path_obj=path_obj,
            case_id="D",
            reason="layout_error",
            client=client,
            content_bytes=content_bytes,
            parse_error=None,
            layout_error=desc,
            os_error=None,
            errno_val=None,
            symlink_target=None,
            recovery_action=recovery,
            fail_mode=fm,
            # §3.10: no synthetic BaseException for layout — use None (spec pseudocode passed str).
            raise_exc=_maybe_raise("layout_error", None),
        )
        return {}

    return parsed  # Case B


def _refresh_overrides(client: Optional[DirectusAdminClient] = None) -> None:
    global _OVERRIDE_DATA
    if _bypass_active():
        return
    _OVERRIDE_DATA = _load_override_at(_override_file_path(), client=client)


# Initial load (fail-safe / diagnostic if malformed)
_refresh_overrides(None)


# -----------------------------------------------------------------------------
# Schema cache
# -----------------------------------------------------------------------------


def _schema_field_names(client: DirectusAdminClient, collection: str) -> set[str]:
    try:
        rows = client.fields(collection)
    except Exception as exc:
        raise SchemaProbeError(collection, exc) from exc
    names: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and "field" in row:
            names.add(str(row["field"]))
    return names


def _cached_fields(client: DirectusAdminClient, collection: str) -> set[str]:
    now = time.time()
    hit = _SCHEMA_CACHE.get(collection)
    if hit and now - hit[1] < _SCHEMA_TTL_SEC:
        return hit[0]
    fields = _schema_field_names(client, collection)
    _SCHEMA_CACHE[collection] = (fields, now)
    return fields


def invalidate_schema_cache(collection: Optional[str] = None) -> None:
    """Flush schema cache and reload override file (§5.0 + §9.2 re-read)."""
    if collection is None:
        _SCHEMA_CACHE.clear()
    else:
        _SCHEMA_CACHE.pop(collection, None)
    _refresh_overrides(None)


def cached_collections() -> list[str]:
    """Public accessor returning the list of currently-cached collection names.

    Stable API surface for callers (e.g. the Directus MCP schema tool) that
    need to enumerate cached collections without reaching into the private
    ``_SCHEMA_CACHE`` dict. Maintainability barrier: refactors of the cache
    structure only need to preserve this function's signature.
    """
    return list(_SCHEMA_CACHE.keys())


# -----------------------------------------------------------------------------
# Mode + validation
# -----------------------------------------------------------------------------


def _collection_override(collection: str) -> dict[str, Any]:
    raw = _OVERRIDE_DATA.get(collection)
    return raw if isinstance(raw, dict) else {}


def _effective_mode(collection: str, mode: Optional[ModeName]) -> ModeName:
    if mode is not None:
        return mode
    o = _collection_override(collection)
    m = o.get("mode")
    if m in ("strict", "warn", "skip"):
        return m  # type: ignore[return-value]
    return "warn"


def _extra_allowed(collection: str) -> set[str]:
    o = _collection_override(collection)
    raw = o.get("extra_allowed_keys")
    if isinstance(raw, list):
        return {str(x) for x in raw if isinstance(x, str)}
    return set()


def _max_payload_bytes(collection: str) -> Optional[int]:
    o = _collection_override(collection)
    m = o.get("max_payload_size_bytes")
    if isinstance(m, int) and not isinstance(m, bool) and m >= 0:
        return m
    return None


def _payload_byte_size(payload: dict) -> int:
    return len(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))


def _within_retired_grace(collection: str, field: str) -> bool:
    coll_reg = RETIRED_FIELDS_REGISTRY.get(collection, {})
    retire_iso = coll_reg.get(field)
    if not retire_iso:
        return False
    try:
        retire_day = datetime.fromisoformat(retire_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - retire_day.replace(tzinfo=timezone.utc)
        return delta.days < 14
    except ValueError:
        return False


def validate_payload(
    collection: str,
    payload: dict[str, Any],
    mode: Optional[ModeName] = None,
    *,
    allow_auto_field_overrides: bool = False,
    client: Optional[DirectusAdminClient] = None,
) -> dict[str, Any]:
    """
    Validate payload keys against Directus schema for prod_* collections.

    Returns:
        {
          "stripped_auto_fields": [...],
          "retired_fields_used": [...],
          "payload": <copy suitable for POST/PATCH>,
        }
    """
    if _bypass_active() or _validator_disabled():
        return {
            "stripped_auto_fields": [],
            "retired_fields_used": [],
            "payload": dict(payload),
        }

    if not (
        collection.startswith("prod_")
        or collection.startswith("app_")
        or collection.startswith("coppa_")
    ):
        return {
            "stripped_auto_fields": [],
            "retired_fields_used": [],
            "payload": dict(payload),
        }

    eff = _effective_mode(collection, mode)
    if eff == "skip":
        return {
            "stripped_auto_fields": [],
            "retired_fields_used": [],
            "payload": dict(payload),
        }

    dc = client or _activity_client(None)
    if dc is None:
        raise SchemaProbeError(collection, RuntimeError("DirectusAdminClient unavailable for schema probe"))

    working = dict(payload)
    stripped: list[str] = []
    for af in _AUTO_FIELDS:
        if af in working:
            if allow_auto_field_overrides:
                continue
            stripped.append(af)
            del working[af]

    max_b = _max_payload_bytes(collection)
    if max_b is not None and _payload_byte_size(working) > max_b:
        if eff == "strict":
            raise UnknownPayloadKeyError(
                collection,
                ["<payload exceeds override max_payload_size_bytes>"],
            )
        _LOG.warning("payload_validator: %s exceeds max_payload_size_bytes (warn mode)", collection)

    try:
        allowed = _cached_fields(dc, collection) | _extra_allowed(collection)
    except SchemaProbeError:
        raise

    unknown_candidates = sorted(k for k in working if k not in allowed)
    retired_hits: list[str] = []
    for uk in unknown_candidates:
        reg = RETIRED_FIELDS_REGISTRY.get(collection, {})
        if uk in reg:
            if _within_retired_grace(collection, uk):
                retired_hits.append(uk)
            else:
                raise RetiredPayloadKeyError(collection, uk, reg[uk])
    unknown = sorted(u for u in unknown_candidates if u not in retired_hits)
    for rk in retired_hits:
        working.pop(rk, None)

    if unknown:
        if eff == "strict":
            raise UnknownPayloadKeyError(collection, unknown)
        _LOG.warning(
            "payload_validator warn mode: %s unknown keys %s — proceeding",
            collection,
            unknown,
        )

    return {
        "stripped_auto_fields": stripped,
        "retired_fields_used": retired_hits,
        "payload": working,
    }
