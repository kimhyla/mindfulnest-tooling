"""Voice-first lipsync public-host readiness — shared by server, subprocess, and Beat Gen UI."""
from __future__ import annotations

import os
import shlex
from typing import Mapping

R2_ENV_KEYS = (
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ACCOUNT_ID",
    "R2_BUCKET_NAME",
)

CREDS_TO_R2_ENV = {
    "r2_access_key_id": "R2_ACCESS_KEY_ID",
    "r2_secret_access_key": "R2_SECRET_ACCESS_KEY",
    "r2_account_id": "R2_ACCOUNT_ID",
    "r2_bucket_name": "R2_BUCKET_NAME",
    "r2_cdn_base_url": "MN_R2_CDN_BASE_URL",
}

LIPSYNC_HOSTING_BLOCK_MESSAGE = (
    "Voice-first Generate needs Cloudflare R2 lipsync staging on this machine. "
    "Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID, and R2_BUCKET_NAME "
    "in Doppler or Production/API_KEYS_MASTER.md, then restart Event servers."
)

# Errors stamped before R2 was configured — obsolete once lipsync_public_host_ready().
_STALE_LIPSYNC_HOSTING_MARKERS = (
    "no lipsync input host returned byte-complete public files",
    "r2_cdn: unavailable or preflight failed",
    "production_staging: unavailable or preflight failed",
    "unsafe url: non-public host",
    "lipsync_hosting_not_configured",
)


def _merged_source(creds: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    if creds:
        for cred_key, env_key in CREDS_TO_R2_ENV.items():
            value = str(creds.get(cred_key) or "").strip()
            if value:
                merged[env_key] = value
    return merged


def r2_credentials_present(*, creds: Mapping[str, str] | None = None, env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else _merged_source(creds)
    return all(str(source.get(key) or "").strip() for key in R2_ENV_KEYS)


def public_staging_base_ready(*, creds: Mapping[str, str] | None = None, env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else _merged_source(creds)
    base = str(
        source.get("MN_LIPSYNC_PUBLIC_BASE_URL")
        or source.get("MN_LIPSYNC_STAGING_PUBLIC_BASE")
        or ""
    ).strip()
    if not base:
        return False
    try:
        from lipsync_staging import is_public_staging_base
    except ImportError:
        return False
    return is_public_staging_base(base)


def lipsync_public_host_ready(*, creds: Mapping[str, str] | None = None, env: Mapping[str, str] | None = None) -> bool:
    return r2_credentials_present(creds=creds, env=env) or public_staging_base_ready(creds=creds, env=env)


def lipsync_public_host_block_message() -> str:
    return LIPSYNC_HOSTING_BLOCK_MESSAGE


def is_stale_lipsync_hosting_failure(error_text: str | None) -> bool:
    """True when a persisted voice-fix error was caused by missing R2/public staging."""
    raw = str(error_text or "").strip().lower()
    if not raw:
        return False
    return any(marker in raw for marker in _STALE_LIPSYNC_HOSTING_MARKERS)


def inject_lipsync_r2_env(target: dict[str, str], creds: Mapping[str, str] | None = None) -> None:
    """Copy R2/CDN env into a subprocess or server env dict."""
    source = _merged_source(creds)
    for key in (*R2_ENV_KEYS, "MN_R2_CDN_BASE_URL"):
        value = str(source.get(key) or "").strip()
        if value:
            target[key] = value


def probe_lipsync_public_host_capabilities(*, creds: Mapping[str, str] | None = None) -> dict[str, object]:
    ready = lipsync_public_host_ready(creds=creds)
    return {
        "lipsync_public_host_ready": ready,
        "lipsync_r2_configured": r2_credentials_present(creds=creds),
        "lipsync_public_staging_ready": public_staging_base_ready(creds=creds),
        "lipsync_public_host_message": None if ready else lipsync_public_host_block_message(),
    }


def shell_export_lines(*, creds: Mapping[str, str] | None = None) -> list[str]:
    source = _merged_source(creds)
    lines: list[str] = []
    for key in (*R2_ENV_KEYS, "MN_R2_CDN_BASE_URL"):
        value = str(source.get(key) or "").strip()
        if value:
            lines.append(f"export {key}={shlex.quote(value)}")
    return lines


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Export lipsync public-host env for shell wrappers.")
    parser.add_argument("--shell-export", action="store_true")
    args = parser.parse_args()
    if not args.shell_export:
        parser.print_help()
        return 1
    creds = None
    try:
        from credentials import load_credentials  # type: ignore
    except ImportError:
        try:
            from tools.credentials_lib.credentials import load_credentials  # type: ignore
        except ImportError:
            load_credentials = None  # type: ignore[assignment]
    if load_credentials is not None:
        try:
            creds = load_credentials()
        except Exception:
            creds = None
    for line in shell_export_lines(creds=creds):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
