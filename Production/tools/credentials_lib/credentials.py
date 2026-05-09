"""
Centralized credential loading for MindfulNest production pipeline.

Reads API_KEYS_MASTER.md and extracts all credentials.
Falls back to environment variables if file not found.
"""

import os
import re


def load_credentials(keys_file=None):
    """Load all API credentials from API_KEYS_MASTER.md or environment.

    Args:
        keys_file: Optional explicit path to API_KEYS_MASTER.md.
                   If None, searches standard locations.

    Returns:
        dict with keys:
            directus_url, directus_email, directus_password,
            elevenlabs_key, wavespeed_key, bfl_key, fal_key,
            replicate_key, segmind_key, runway_key,
            supabase_ref, supabase_password, railway_token
    """
    # Try to find API_KEYS_MASTER.md
    if keys_file is None:
        keys_file = _find_keys_file()

    creds = {}

    if keys_file and os.path.exists(keys_file):
        content = _read_file(keys_file)
        creds = _parse_keys_file(content)
    else:
        # Fall back to environment variables
        creds = _from_env()

    # Validate critical credentials
    missing = []
    for key in ("directus_url", "directus_email", "directus_password"):
        if not creds.get(key):
            missing.append(key)

    if missing:
        raise ValueError(
            f"Missing critical credentials: {', '.join(missing)}. "
            f"Ensure API_KEYS_MASTER.md exists or set environment variables."
        )

    return creds


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


def _from_env():
    """Load credentials from environment variables."""
    return {
        "directus_url": os.environ.get(
            "DIRECTUS_URL",
            "https://directus-production-3460.up.railway.app"
        ),
        "directus_email": os.environ.get("DIRECTUS_EMAIL", ""),
        "directus_password": os.environ.get("DIRECTUS_PASSWORD", ""),
        "elevenlabs_key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "wavespeed_key": os.environ.get("WAVESPEED_API_KEY", ""),
        "bfl_key": os.environ.get("BFL_API_KEY", ""),
        "fal_key": os.environ.get("FAL_KEY", ""),
        "replicate_key": os.environ.get("REPLICATE_API_TOKEN", ""),
        "segmind_key": os.environ.get("SEGMIND_API_KEY", ""),
        "runway_key": os.environ.get("RUNWAY_API_KEY", ""),
        "supabase_ref": os.environ.get("SUPABASE_REF", ""),
        "supabase_password": os.environ.get("SUPABASE_PASSWORD", ""),
        "railway_token": os.environ.get("RAILWAY_TOKEN", ""),
    }
