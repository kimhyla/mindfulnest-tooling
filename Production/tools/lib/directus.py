"""
Directus API client for MindfulNest production pipeline.

Handles authentication (auto-refresh JWT), CRUD operations,
the 7-query bootstrap protocol, and all known schema quirks.

Usage:
    from lib.credentials import load_credentials
    from lib.directus import DirectusClient, parse_module_id

    creds = load_credentials()
    client = DirectusClient(creds["directus_url"],
                            creds["directus_email"],
                            creds["directus_password"])
    state = client.bootstrap(module_id=1)
"""

# PEP 563: all annotations become strings, making `X | None` syntax
# evaluate lazily and work on Python 3.9 (needed for /usr/bin/python3
# which is 3.9.6 on macOS; launchd cron calls this interpreter).
from __future__ import annotations

import http.client
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Fresh-connection HTTPS helper (counter-agent C1 HIGH finding, April 16 2026)
#
# lib/directus.py is imported by the long-lived production_server.py process.
# Previously used urllib.request.urlopen which shares module-level opener +
# cached SSL context across calls. After hours of uptime, polls entered stuck
# state (same bug that hit WaveSpeed poll — see production_server.py:
# _wavespeed_request). Fix: fresh SSLContext with OP_NO_TICKET + fresh
# HTTPSConnection per call, explicit close in finally. Stdlib only, no deps.
# ---------------------------------------------------------------------------

def _fresh_https_request(
    method: str,
    url: str,
    *,
    headers: dict,
    body: bytes | None = None,
    timeout: int = 30,
):
    """Return (status_code, body_bytes). Raises urllib.error.URLError on
    network failure so existing handlers continue to match. Always closes
    the connection before returning."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"unsupported URL scheme: {url!r}")
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    req_headers = dict(headers)
    req_headers.setdefault("Connection", "close")
    if parsed.scheme == "https":
        ctx = ssl.create_default_context()
        ctx.options |= ssl.OP_NO_TICKET
        ctx.options |= ssl.OP_NO_COMPRESSION
        conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(parsed.netloc, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=req_headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    except (TimeoutError, http.client.HTTPException, OSError) as exc:
        raise urllib.error.URLError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def parse_module_id(raw):
    """Convert 'M1', 'arc1_m1', 'm5', or int to integer.

    CRITICAL: Directus prod_visual_assets.module_id is INTEGER.
    Passing 'M1' (string) causes HTTP 500. This function prevents that.

    Args:
        raw: str like 'M1', 'arc1_m3', int, or None

    Returns:
        int or None
    """
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    match = re.search(r'[Mm](\d+)', str(raw))
    if match:
        return int(match.group(1))
    # Try direct int conversion
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Directus Client
# ---------------------------------------------------------------------------

class DirectusClient:
    """Stateful Directus API client with auto-refresh JWT token.

    Token TTL is 15 minutes. Client re-authenticates automatically
    when token has < 2 minutes remaining.
    """

    # Token refresh buffer (seconds before expiry to re-auth)
    _REFRESH_BUFFER = 120  # 2 minutes

    def __init__(self, url, email, password):
        self.url = url.rstrip("/")
        self._email = email
        self._password = password
        self._token = None
        self._token_expires_at = 0  # epoch timestamp

    # === Authentication ===

    def authenticate(self):
        """POST /auth/login -> JWT token. Stores token and expiry."""
        payload = json.dumps({
            "email": self._email,
            "password": self._password
        }).encode("utf-8")

        try:
            status, raw = _fresh_https_request(
                "POST", f"{self.url}/auth/login",
                headers={"Content-Type": "application/json"},
                body=payload,
                timeout=15,
            )
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot reach Directus at {self.url}: {e}")

        if status >= 400:
            raise ConnectionError(
                f"Directus auth failed (HTTP {status}): {raw[:500].decode('utf-8', errors='replace')}"
            )
        body = json.loads(raw.decode("utf-8"))

        data = body.get("data", {})
        self._token = data.get("access_token")
        expires_in = data.get("expires", 900000)  # ms, default 15 min

        if not self._token:
            raise ConnectionError(
                "Directus auth returned no access_token. "
                "Check email/password in API_KEYS_MASTER.md."
            )

        # expires_in from Directus is in milliseconds
        self._token_expires_at = time.time() + (expires_in / 1000)
        return self._token

    def _ensure_auth(self):
        """Re-authenticate if token is missing or about to expire."""
        now = time.time()
        if self._token is None or now >= (self._token_expires_at - self._REFRESH_BUFFER):
            self.authenticate()

    def _headers(self):
        """Return auth headers for API requests."""
        self._ensure_auth()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json"
        }

    # === Generic CRUD ===

    def _request(self, method, path, data=None, params=None):
        """Make an authenticated HTTP request to Directus.

        Args:
            method: 'GET', 'POST', 'PATCH', 'DELETE'
            path: API path (e.g., '/items/prod_modules')
            data: dict to send as JSON body
            params: dict of query parameters

        Returns:
            Parsed JSON response body

        Raises:
            DirectusError on HTTP errors with details
        """
        url = f"{self.url}{path}"
        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            url = f"{url}?{query}"

        body = json.dumps(data).encode("utf-8") if data else None
        headers = self._headers()

        try:
            status, raw_bytes = _fresh_https_request(
                method, url, headers=headers, body=body, timeout=30,
            )
        except urllib.error.URLError as e:
            raise DirectusError(
                f"Network error on {method} {path}: {e}",
                status=0,
                detail=str(e),
            )

        raw = raw_bytes.decode("utf-8")
        if 200 <= status < 300:
            return json.loads(raw) if raw else {}

        # Parse error details for HTTP 4xx/5xx
        try:
            error_json = json.loads(raw)
            errors = error_json.get("errors", [])
            detail = errors[0].get("message", raw) if errors else raw
        except (json.JSONDecodeError, IndexError):
            detail = raw
        raise DirectusError(
            f"HTTP {status} on {method} {path}: {detail}",
            status=status,
            detail=detail,
        )

    def get(self, collection, filters=None, sort=None, limit=None, fields=None):
        """Query items from a collection.

        Args:
            collection: Collection name (e.g., 'prod_modules')
            filters: dict of {field: {operator: value}} or None
                     Example: {"module_id": {"_eq": 1}, "status": {"_eq": "approved"}}
            sort: str or list, e.g., '-created_at' or ['arc_number', 'module_index']
            limit: int, max records to return
            fields: str or list of field names to return

        Returns:
            list of dicts (the 'data' array from Directus response)
        """
        params = {}

        if filters:
            for field, ops in filters.items():
                if isinstance(ops, dict):
                    for op, val in ops.items():
                        params[f"filter[{field}][{op}]"] = val
                else:
                    # Shorthand: {"field": value} -> {"field": {"_eq": value}}
                    params[f"filter[{field}][_eq]"] = ops

        if sort:
            params["sort"] = sort if isinstance(sort, str) else ",".join(sort)

        if limit is not None:
            params["limit"] = limit

        if fields:
            params["fields"] = fields if isinstance(fields, str) else ",".join(fields)

        result = self._request("GET", f"/items/{collection}", params=params)
        return result.get("data", [])

    def get_one(self, collection, item_id, fields=None):
        """Get a single item by ID.

        Returns:
            dict (the item)
        """
        params = {}
        if fields:
            params["fields"] = fields if isinstance(fields, str) else ",".join(fields)

        result = self._request("GET", f"/items/{collection}/{item_id}", params=params)
        return result.get("data", {})

    def create(self, collection, data):
        """Create a new item.

        Args:
            collection: Collection name
            data: dict of field values

        Returns:
            dict (the created item with its ID)
        """
        result = self._request("POST", f"/items/{collection}", data=data)
        return result.get("data", {})

    def update(self, collection, item_id, data):
        """Update an existing item.

        Args:
            collection: Collection name
            item_id: Record ID
            data: dict of fields to update

        Returns:
            dict (the updated item)
        """
        result = self._request("PATCH", f"/items/{collection}/{item_id}", data=data)
        return result.get("data", {})

    def get_fields(self, collection):
        """Get field definitions for a collection (schema introspection).

        Returns:
            list of field definition dicts
        """
        result = self._request("GET", f"/fields/{collection}")
        return result.get("data", [])

    # === Smoke Test ===

    def smoke_test(self):
        """Test Directus connectivity: auth, query, schema.

        Returns:
            dict: {"auth": bool, "query": bool, "schema": bool, "errors": list}
        """
        result = {"auth": False, "query": False, "schema": False, "errors": []}

        # Test 1: Authentication
        try:
            self.authenticate()
            result["auth"] = True
        except Exception as e:
            result["errors"].append(f"Auth: {e}")
            return result

        # Test 2: Query
        try:
            items = self.get("prod_visual_assets", limit=1)
            result["query"] = True
        except DirectusError as e:
            if e.status == 403:
                result["errors"].append(
                    "Query: Permission denied on prod_visual_assets. "
                    "Check admin policy."
                )
            else:
                result["errors"].append(f"Query: {e}")
        except Exception as e:
            result["errors"].append(f"Query: {e}")

        # Test 3: Schema — check expected fields exist on prod_visual_assets
        expected_fields = {
            "filename", "filepath", "module_id", "event_number",
            "status", "shot_number"
        }
        try:
            fields = self.get_fields("prod_visual_assets")
            field_names = {f.get("field", "") for f in fields}
            missing = expected_fields - field_names
            if missing:
                result["errors"].append(
                    f"Schema: Missing fields on prod_visual_assets: {missing}"
                )
            else:
                result["schema"] = True
        except Exception as e:
            result["errors"].append(f"Schema: {e}")

        return result

    # === 7-Query Bootstrap ===

    def bootstrap(self, module_id):
        """Run the 7-query session start protocol for a module.

        This replaces the manual dashboard-gate skill protocol.
        Reads all state needed to operate on a module.

        Args:
            module_id: int (e.g., 1 for M1)

        Returns:
            dict with keys:
                locked_decisions, module, activity, audio_assets,
                visual_assets, blockers, decisions, voice_profiles
        """
        self._ensure_auth()

        state = {}

        # Q1: Locked decisions (all — not module-specific)
        state["locked_decisions"] = self.get("prod_audio_locked_decisions")

        # Q2: Module state — find by m_number
        modules = self.get("prod_modules",
                           filters={"m_number": {"_eq": module_id}})
        if modules:
            state["module"] = modules[0]
        else:
            # Try by ID directly
            try:
                state["module"] = self.get_one("prod_modules", module_id)
            except DirectusError:
                state["module"] = {
                    "id": None,
                    "m_number": module_id,
                    "current_stage": "unknown",
                    "stage_status": "unknown",
                    "_error": f"Module M{module_id} not found in prod_modules"
                }

        # Q3: Recent activity (last 10)
        state["activity"] = self.get(
            "prod_activity_log",
            filters={"module_id": {"_eq": module_id}},
            sort="-created_at",
            limit=10
        )

        # Q4: Audio assets
        state["audio_assets"] = self.get(
            "prod_audio_assets",
            filters={"module_id": {"_eq": module_id}}
        )

        # Q5: Visual assets
        state["visual_assets"] = self.get(
            "prod_visual_assets",
            filters={"module_id": {"_eq": module_id}}
        )

        # Q6: Unresolved blockers
        state["blockers"] = self.get(
            "prod_blockers",
            filters={
                "module_id": {"_eq": module_id},
                "is_resolved": {"_eq": False}
            }
        )

        # Q7: Session decisions
        state["decisions"] = self.get(
            "prod_session_decisions",
            filters={"module_id": {"_eq": module_id}},
            sort="-created_at"
        )

        # Bonus: Voice profiles (all characters)
        state["voice_profiles"] = self.get("prod_voice_profiles")

        return state

    # === Convenience Methods ===

    def get_module(self, module_id):
        """Get a module by m_number.

        Args:
            module_id: int (1 for M1, 2 for M2, etc.)

        Returns:
            dict (module record) or None
        """
        modules = self.get("prod_modules",
                           filters={"m_number": {"_eq": module_id}})
        return modules[0] if modules else None

    def get_all_modules(self):
        """Get all modules, sorted by m_number.

        Returns:
            list of module dicts
        """
        return self.get("prod_modules", sort="m_number")

    def advance_stage(self, module_record_id, next_stage):
        """Move a module to the next pipeline stage.

        Sets current_stage and resets stage_status to 'not_started'.
        Logs the transition.

        Args:
            module_record_id: int (the record ID, not m_number)
            next_stage: str (stage key, e.g., 'phase_a_json')
        """
        self.update("prod_modules", module_record_id, {
            "current_stage": next_stage,
            "stage_status": "not_started"
        })

    def log_activity(self, module_id, action, details=None,
                     performed_by="pipeline", kim_verdict=None,
                     kim_feedback=None):
        """Create a prod_activity_log entry.

        IMPORTANT: Uses field 'action' (NOT 'description').
        Uses field 'details' as jsonb (NOT 'status').
        These are the CORRECT field names — using wrong names
        causes silent nulls with no error.

        Args:
            module_id: int
            action: str (required — what happened)
            details: dict (optional — structured metadata)
            performed_by: str (default 'pipeline')
            kim_verdict: str or None ('approved', 'rejected', 'needs_revision', 'pending')
            kim_feedback: str or None (Kim's exact words)
        """
        entry = {
            "module_id": module_id,
            "action": action,
            "performed_by": performed_by,
        }

        if details is not None:
            entry["details"] = details

        if kim_verdict is not None:
            entry["kim_verdict"] = kim_verdict

        if kim_feedback is not None:
            entry["kim_feedback"] = kim_feedback

        return self.create("prod_activity_log", entry)

    def register_audio_asset(self, module_id, filename, filepath,
                              asset_type, status="candidate", **kwargs):
        """Register an audio file in prod_audio_assets.

        Args:
            module_id: int (NOT 'M1')
            filename: str (e.g., 'm1_voice_stem_v2.mp3')
            filepath: str (full path)
            asset_type: str (e.g., 'voice_stem', 'gong_candidate', 'phase_b_mix')
            status: str (default 'candidate')
            **kwargs: Additional fields (duration_seconds, version, etc.)
        """
        data = {
            "module_id": module_id,
            "file_name": filename,
            "file_path": filepath,
            "file_type": asset_type,
            "status": status,
        }
        data.update(kwargs)
        return self.create("prod_audio_assets", data)

    def register_visual_asset(self, module_id, filename, filepath,
                               shot_number, **kwargs):
        """Register an image/video in prod_visual_assets.

        CRITICAL: module_id MUST be int, not string 'M1'.
        All three of filename, filepath, shot_number are REQUIRED.

        Args:
            module_id: int (NOT 'M1' — causes HTTP 500)
            filename: str (REQUIRED)
            filepath: str (REQUIRED)
            shot_number: int (REQUIRED)
            **kwargs: asset_type, status, width, height, event_number, purpose
        """
        data = {
            "module_id": module_id,
            "filename": filename,
            "filepath": filepath,
            "shot_number": shot_number,
        }
        data.update(kwargs)
        return self.create("prod_visual_assets", data)

    def get_approved_visual_assets(self, module_id, event_number=None):
        """Get approved visual assets for a module (optionally filtered by event).

        Args:
            module_id: int
            event_number: int or None

        Returns:
            list of asset dicts
        """
        filters = {
            "module_id": {"_eq": module_id},
            "status": {"_eq": "approved"}
        }
        if event_number is not None:
            filters["event_number"] = {"_eq": event_number}

        return self.get("prod_visual_assets", filters=filters, sort="id")

    def get_voice_profile(self, character_name):
        """Get voice settings for a character.

        Args:
            character_name: str (e.g., 'Myrrhin', 'Guide Bird')

        Returns:
            dict or None
        """
        profiles = self.get("prod_voice_profiles",
                            filters={"character_name": {"_eq": character_name}})
        return profiles[0] if profiles else None

    def get_locked_decisions(self):
        """Get all locked decisions as a key-value dict.

        Returns:
            dict: {decision_key: decision_value}
        """
        rows = self.get("prod_audio_locked_decisions")
        return {r["decision_key"]: r["decision_value"] for r in rows
                if "decision_key" in r}

    def update_session_state(self, module_record_id, checklist=None, notes=None):
        """Update session handoff fields on a module.

        Args:
            module_record_id: int (record ID)
            checklist: list of {"description": str, "done": bool} or None
            notes: str or None
        """
        data = {}
        if checklist is not None:
            data["session_checklist"] = checklist
        if notes is not None:
            data["session_resumption_notes"] = notes

        if data:
            self.update("prod_modules", module_record_id, data)


# ---------------------------------------------------------------------------
# Custom Exception
# ---------------------------------------------------------------------------

class DirectusError(Exception):
    """Error from Directus API with HTTP status and detail."""

    def __init__(self, message, status=None, detail=None):
        super().__init__(message)
        self.status = status
        self.detail = detail
