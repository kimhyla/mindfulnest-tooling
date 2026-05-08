"""
Centralized credential loading for MindfulNest production pipeline.

PRIORITY (post LD-227 Phase 1, 2026-05-08):
  1. Environment variables (Doppler injects these via `doppler run -- python3 ...`)
  2. API_KEYS_MASTER.md fallback (LD-227 SHORTCUT_CREDSTORE_MD_FALLBACK_20260418)

ENV-VAR NAME RESOLUTION:
  Each env-backed key reads the Doppler-canonical name FIRST, then falls back to a
  legacy bare name (preserves backward compat for callers that export the legacy form).
  See `_from_env` for the full mapping.

DICT KEYS RETURNED (caller-facing — STABLE; do NOT rename without a 24-caller audit):
  directus_url, directus_email, directus_password,
  elevenlabs_key, wavespeed_key, bfl_key, fal_key,
  replicate_key, segmind_key, runway_key,
  supabase_ref, supabase_password, railway_token

PHASE 4 PLAN (LD-227, separate session 14+ days after Phase 1 lands):
  Delete `_from_md_fallback`, `_emit_fallback_warning`, `_find_keys_file`,
  `_parse_keys_file`, `_read_file` and their call site in `load_credentials`.
  Replace API_KEYS_MASTER.md key VALUES with `<REDACTED>` (retain metadata).
  PATCH LD-227 status='superseded'.
"""

import os
import re
import sys


def load_credentials(keys_file=None):
    """Load all API credentials, env-FIRST with API_KEYS_MASTER.md fallback.

    Args:
        keys_file: Optional explicit path to API_KEYS_MASTER.md.
                   If None, searches standard locations on fallback.

    Returns:
        dict with keys (see module docstring for full list).

    Raises:
        ValueError: if required Directus keys are missing from BOTH env and MD.
    """
    creds = _from_env()

    required = ("directus_url", "directus_email", "directus_password")
    if not all(creds.get(k) for k in required):
        md_creds = _from_md_fallback(keys_file)
        if md_creds is not None:
            _emit_fallback_warning()
            # Per-key merge: env wins where present; MD fills only gaps.
            for k, v in md_creds.items():
                if not creds.get(k):
                    creds[k] = v

    missing = [k for k in required if not creds.get(k)]
    if missing:
        raise ValueError(
            f"Missing critical credentials: {', '.join(missing)}. "
            f"Either run via `doppler run -- python3 <script>.py` (Doppler project "
            f"`mindfulnest`) or ensure API_KEYS_MASTER.md exists with the required rows."
        )

    return creds


def _from_env():
    """Load credentials from environment variables.

    Doppler-canonical names read first; legacy bare names accepted as fallback.
    Dict keys returned to callers are STABLE (caller-facing API). The asymmetry
    between Doppler-side names (DIRECTUS_ADMIN_EMAIL) and dict-side names
    (directus_email) is intentional — the dict keys must not change without
    auditing all 24 caller files. See `Production/lib/credential_store.py`
    module docstring for the canonical Doppler name list.
    """
    return {
        "directus_url": os.environ.get(
            "DIRECTUS_URL",
            "https://directus-production-3460.up.railway.app",
        ),
        # Doppler-canonical first, legacy fallback.
        "directus_email": (
            os.environ.get("DIRECTUS_ADMIN_EMAIL")
            or os.environ.get("DIRECTUS_EMAIL", "")
        ),
        "directus_password": (
            os.environ.get("DIRECTUS_ADMIN_PASSWORD")
            or os.environ.get("DIRECTUS_PASSWORD", "")
        ),
        "elevenlabs_key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "wavespeed_key": os.environ.get("WAVESPEED_API_KEY", ""),
        "bfl_key": os.environ.get("BFL_API_KEY", ""),
        "fal_key": os.environ.get("FAL_KEY", ""),
        "replicate_key": os.environ.get("REPLICATE_API_TOKEN", ""),
        "segmind_key": os.environ.get("SEGMIND_API_KEY", ""),
        "runway_key": os.environ.get("RUNWAY_API_KEY", ""),
        "supabase_ref": (
            os.environ.get("SUPABASE_PROJECT_REF")
            or os.environ.get("SUPABASE_REF", "")
        ),
        "supabase_password": (
            os.environ.get("SUPABASE_DB_PASSWORD")
            or os.environ.get("SUPABASE_PASSWORD", "")
        ),
        "railway_token": (
            os.environ.get("RAILWAY_API_TOKEN")
            or os.environ.get("RAILWAY_TOKEN", "")
        ),
    }


def _emit_fallback_warning():
    """Emit a one-time stderr warning when the MD fallback is exercised.

    Process-env guard (mirrors `Production/lib/credential_store.py:75-83`):
    inherits across subprocesses by design — avoids stderr spam in long-running
    servers (e.g., production_server.py ThreadingHTTPServer where N concurrent
    requests would otherwise emit N duplicate warnings). Subprocess receiving
    the env will not re-warn even on its first MD fallback. Acceptable: the
    LD-227 Phase 3 monitoring goal needs one warning per process restart, not
    per request.
    """
    if not os.environ.get("_CREDSTORE_FALLBACK_WARNED"):
        print(
            "[credentials] WARNING: Doppler env vars not fully populated — falling "
            "back to API_KEYS_MASTER.md. Prefix command with `doppler run -- ` for "
            "production use (LD-227 SHORTCUT_CREDSTORE_MD_FALLBACK_20260418; "
            "fallback removal targeted Phase 4, 14+ days from this rollout).",
            file=sys.stderr,
        )
        os.environ["_CREDSTORE_FALLBACK_WARNED"] = "1"


# ============================================================================
# PHASE 4 REMOVAL TARGET (LD-227 SHORTCUT_CREDSTORE_MD_FALLBACK_20260418)
# ----------------------------------------------------------------------------
# Everything below this banner is the MD fallback path. Phase 4 deletes:
#   - _from_md_fallback
#   - _find_keys_file
#   - _parse_keys_file
#   - _read_file
# AND removes the call to _from_md_fallback inside load_credentials above.
# Closure trigger: 14 consecutive days with zero MD fallback warnings observed
# in production logs (post-Phase-1 launchd/server runs all under doppler run --).
# ============================================================================

def _from_md_fallback(keys_file=None):
    """Parse API_KEYS_MASTER.md and return credentials dict, or None if not found."""
    if keys_file is None:
        keys_file = _find_keys_file()

    if not keys_file or not os.path.exists(keys_file):
        return None

    content = _read_file(keys_file)
    return _parse_keys_file(content)


def _find_keys_file():
    """Search standard locations for API_KEYS_MASTER.md."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    candidates = [
        os.path.join(script_dir, "..", "..", "API_KEYS_MASTER.md"),   # tools/lib/ -> Production/
        os.path.join(script_dir, "..", "API_KEYS_MASTER.md"),          # tools/ -> tools/../
        os.path.join(script_dir, "..", "..", "..", "Production", "API_KEYS_MASTER.md"),
    ]

    for path in candidates:
        resolved = os.path.normpath(path)
        if os.path.exists(resolved):
            return resolved

    return None


def _read_file(path):
    """Read file contents as string."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_keys_file(content):
    """Parse API_KEYS_MASTER.md markdown tables into credential dict."""
    creds = {}

    # --- API Keys table (Service | Key | Plan/Notes) ---
    # Match rows with backtick-wrapped keys
    api_rows = re.findall(
        r'\|\s*\*\*([^*]+)\*\*[^|]*\|\s*`([^`]+)`\s*\|',
        content
    )

    for service_raw, key_value in api_rows:
        service = service_raw.strip().lower()

        # Skip endpoint-URL rows masquerading as keys (API_KEYS_MASTER.md has
        # an Endpoints table interleaved with the Keys table; URL rows also
        # use the **Service** | `value` pattern). A real API key never
        # contains a slash or starts with "api."/"http".
        if "/" in key_value or key_value.lower().startswith(("api.", "http")):
            continue

        if "elevenlabs" in service:
            creds["elevenlabs_key"] = key_value
        elif "wavespeed" in service:
            creds["wavespeed_key"] = key_value
        elif "flux" in service or "bfl" in service:
            creds["bfl_key"] = key_value
        elif "fal" in service:
            creds["fal_key"] = key_value
        elif "replicate" in service:
            creds["replicate_key"] = key_value
        elif "segmind" in service:
            creds["segmind_key"] = key_value
        elif "runway" in service:
            creds["runway_key"] = key_value

    # --- Infrastructure table (Service | Credential | Value | Notes) ---
    # Note: service may have parenthetical like **Directus** (Dashboard)
    # so we use [^|]* after the ** to consume "(Dashboard)" etc.
    infra_rows = re.findall(
        r'\|\s*\*\*([^*]+)\*\*[^|]*\|\s*([^|]+)\|\s*`([^`]+)`\s*\|([^|]*)\|',
        content
    )

    for service_raw, cred_type, value, notes in infra_rows:
        service = service_raw.strip().lower()
        cred_type = cred_type.strip().lower()

        if "directus" in service:
            if "email" in cred_type:
                creds["directus_email"] = value
            elif "password" in cred_type:
                creds["directus_password"] = value

            # Extract URL from notes
            url_match = re.search(r'(https://[^\s)]+)', notes)
            if url_match:
                # Clean trailing markers
                url = url_match.group(1).rstrip(")")
                # Remove any trailing text after the URL
                url = re.sub(r'\s.*$', '', url)
                creds["directus_url"] = url

        elif "supabase" in service:
            if "project ref" in cred_type:
                creds["supabase_ref"] = value
            elif "db password" in cred_type or "password" in cred_type:
                creds["supabase_password"] = value

        elif "railway" in service:
            if "api token" in cred_type or "token" in cred_type:
                creds["railway_token"] = value

    # Ensure Directus URL has a default if not found in notes
    if "directus_url" not in creds:
        creds["directus_url"] = "https://directus-production-3460.up.railway.app"

    return creds
