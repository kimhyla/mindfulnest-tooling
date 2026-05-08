"""
Directus admin client — short admin requests with retries.

Spec v2 §C9 SPLIT: this is for short-lived admin operations (POST /items/*, PATCH, GET with small
filter). NOT for long polling (see wavespeed_poll_client.py for that; LD-137 forbids urllib/requests
on poll paths).

LD-76 compliance: Python urllib.request for Directus (never curl). This module wraps urllib with
retry semantics.

Usage:
    from lib.directus_admin_client import DirectusAdminClient
    client = DirectusAdminClient()  # reads creds from API_KEYS_MASTER.md or env
    ld = client.post_item("prod_locked_decisions", {...})
    rows = client.get_items("app_blockers", filters={"is_resolved": {"_eq": False}})
"""

from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional


DIRECTUS_URL = "https://directus-production-3460.up.railway.app"
MAX_RETRIES = 3
BACKOFF_BASE = 0.3  # seconds, exponential
RETRY_STATUS_CODES = {429, 502, 503, 504}


@dataclass
class DirectusAdminError(Exception):
    status: int
    body: str
    path: str
    method: str

    def __str__(self) -> str:
        return f"DirectusAdminError {self.method} {self.path} → {self.status}: {self.body[:200]}"


class DirectusAdminClient:
    """
    Short-request client. Handles login, token refresh, and retry for idempotent methods (GET, PUT, PATCH, DELETE).
    POST is NOT retried by default (non-idempotent) — caller opts in via retry_post=True.
    """

    def __init__(self, base_url: str = DIRECTUS_URL, email: Optional[str] = None, password: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        # Doppler-canonical names first (DIRECTUS_ADMIN_*), legacy bare names as fallback,
        # API_KEYS_MASTER.md as last resort (LD-227 SHORTCUT_CREDSTORE_MD_FALLBACK_20260418).
        self._email = (
            email
            or os.environ.get("DIRECTUS_ADMIN_EMAIL")
            or os.environ.get("DIRECTUS_EMAIL")
            or self._read_from_keys_file("Admin Email")
        )
        self._password = (
            password
            or os.environ.get("DIRECTUS_ADMIN_PASSWORD")
            or os.environ.get("DIRECTUS_PASSWORD")
            or self._read_from_keys_file("Admin Password")
        )
        if not self._email or not self._password:
            raise RuntimeError(
                "Directus credentials not found. Run via `doppler run -- ` (Doppler "
                "project `mindfulnest`) or set DIRECTUS_ADMIN_EMAIL/DIRECTUS_ADMIN_PASSWORD "
                "env vars (or legacy DIRECTUS_EMAIL/DIRECTUS_PASSWORD), or ensure "
                "API_KEYS_MASTER.md is reachable."
            )
        self._token: Optional[str] = None

    @staticmethod
    def _candidate_keys_paths() -> list[str]:
        """Return ordered list of candidate locations for API_KEYS_MASTER.md.

        Cross-platform per LD DIRECTUS_ADMIN_CLIENT_CROSS_PLATFORM_PATH_V1:
          1. Mac CloudStorage Dropbox path (darwin-native)
          2. Generic ~/Dropbox path (Windows, Linux, Mac with symlinks)
          3. Project-relative (for cloned/copied project folders)

        All candidates are tried in order (belt-and-suspenders) because some
        Mac users have ~/Dropbox symlinks and some Windows users have
        OneDrive-redirected Dropbox paths.
        """
        rel = "Dropbox/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md"
        mac_native = os.path.expanduser(
            "~/Library/CloudStorage/" + rel
        )
        generic = os.path.expanduser("~/" + rel)
        project_rel = os.path.abspath(
            os.path.join(os.getcwd(), "Production", "API_KEYS_MASTER.md")
        )
        # Order by platform preference, but always try ALL three.
        if sys.platform == "darwin":
            return [mac_native, generic, project_rel]
        return [generic, mac_native, project_rel]

    @staticmethod
    def _read_from_keys_file(field: str) -> Optional[str]:
        candidates = DirectusAdminClient._candidate_keys_paths()
        for keys_path in candidates:
            if not os.path.exists(keys_path):
                continue
            with open(keys_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "**Directus**" in line and field in line:
                        # crude table parse: look for `value` in backticks
                        parts = line.split("`")
                        if len(parts) >= 2:
                            return parts[1].strip()
            # File existed and was parsed but field not found — no need to
            # scan further files (they'd have the same content anyway).
            return None
        # No candidate existed — warn the operator so silent offline-queueing
        # is visible in stderr. Do NOT raise (silent queuing remains correct
        # offline behavior per feedback_desktop_no_hooks.md).
        print(
            "WARNING: DirectusAdminClient could not locate API_KEYS_MASTER.md. "
            "Tried: " + ", ".join(candidates),
            file=sys.stderr,
        )
        return None

    def _login(self) -> str:
        payload = json.dumps({"email": self._email, "password": self._password}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/auth/login",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            self._token = json.loads(r.read())["data"]["access_token"]
        return self._token

    def _headers(self) -> dict:
        if not self._token:
            self._login()
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, data: Optional[dict] = None, retry_post: bool = False) -> Any:
        body = json.dumps(data).encode() if data is not None else None
        idempotent = method in {"GET", "PUT", "PATCH", "DELETE"} or retry_post
        last_err: Optional[Exception] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}{path}", data=body, headers=self._headers(), method=method
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    if not raw:
                        return None
                    return json.loads(raw).get("data")
            except urllib.error.HTTPError as e:
                body_str = e.read().decode()
                # 401: token expired, try once more
                if e.code == 401 and attempt == 0:
                    self._token = None
                    continue
                # Retry-on-status for idempotent methods
                if e.code in RETRY_STATUS_CODES and idempotent and attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue
                raise DirectusAdminError(status=e.code, body=body_str, path=path, method=method) from e
            except urllib.error.URLError as e:
                # Network error — retry on idempotent
                last_err = e
                if idempotent and attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue
                raise

        if last_err:
            raise last_err
        raise RuntimeError("Directus request failed after retries")

    # Public API
    def get_item(self, collection: str, item_id: int | str, fields: Optional[list[str]] = None) -> Any:
        q = ""
        if fields:
            q = "?" + urllib.parse.urlencode({"fields": ",".join(fields)})
        return self._request("GET", f"/items/{collection}/{item_id}{q}")

    def get_items(self, collection: str, filters: Optional[dict] = None, fields: Optional[list[str]] = None,
                  sort: Optional[str] = None, limit: int = -1) -> list:
        params: dict = {"limit": str(limit)}
        if filters:
            params["filter"] = json.dumps(filters)
        if fields:
            params["fields"] = ",".join(fields)
        if sort:
            params["sort"] = sort
        q = "?" + urllib.parse.urlencode(params)
        return self._request("GET", f"/items/{collection}{q}") or []

    def post_item(self, collection: str, data: dict, retry_post: bool = False) -> Any:
        return self._request("POST", f"/items/{collection}", data=data, retry_post=retry_post)

    def patch_item(self, collection: str, item_id: int | str, data: dict) -> Any:
        return self._request("PATCH", f"/items/{collection}/{item_id}", data=data)

    def patch_items_bulk(self, collection: str, keys: list[int | str], data: dict) -> Any:
        return self._request("PATCH", f"/items/{collection}", data={"keys": keys, "data": data})

    def delete_item(self, collection: str, item_id: int | str) -> Any:
        return self._request("DELETE", f"/items/{collection}/{item_id}")

    def fields(self, collection: str) -> list:
        return self._request("GET", f"/fields/{collection}") or []


if __name__ == "__main__":
    # Smoke test: list recent LDs
    client = DirectusAdminClient()
    lds = client.get_items("prod_locked_decisions", sort="-id", fields=["id", "decision_key"], limit=5)
    print(f"Latest 5 LDs:")
    for ld in lds:
        print(f"  LD-{ld['id']:3} {ld['decision_key']}")
