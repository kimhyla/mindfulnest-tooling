"""
Centralized credential retrieval — Doppler-first, API_KEYS_MASTER.md fallback.

Per LD-208 RENT_DOPPLER_SECRETS: secrets live in Doppler (project `mindfulnest`,
config `dev`). Scripts invoked via `doppler run -- python3 <script>.py` get all
secrets as environment variables automatically.

During migration, this module falls back to parsing the legacy API_KEYS_MASTER.md
file if env vars aren't set. Closure: once all callers are verified running under
`doppler run`, the legacy fallback will be removed and API_KEYS_MASTER.md archived.

USAGE:
    from lib.credential_store import get_secret
    elevenlabs_key = get_secret("ELEVENLABS_API_KEY")

ENV VAR NAMES (match Doppler):
    ELEVENLABS_API_KEY, RUNWAY_API_KEY, WAVESPEED_API_KEY, BFL_API_KEY,
    FAL_KEY, REPLICATE_API_TOKEN, SEGMIND_API_KEY, EVOLINK_API_KEY,
    GEMINI_API_KEY, OPENAI_API_KEY, SUPABASE_PROJECT_REF, SUPABASE_DB_PASSWORD,
    SUPABASE_DB_USER, DIRECTUS_URL, DIRECTUS_ADMIN_EMAIL, DIRECTUS_ADMIN_PASSWORD,
    RAILWAY_PROJECT, RAILWAY_API_TOKEN
"""
from __future__ import annotations
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Locate Production/API_KEYS_MASTER.md relative to this file (lib/ sibling of scripts/)
_THIS_DIR = Path(__file__).resolve().parent
_LEGACY_MD = _THIS_DIR.parent / "API_KEYS_MASTER.md"

# Map env var names to the human-readable label used in API_KEYS_MASTER.md.
# Used only during transition for fallback lookup.
_LEGACY_LABEL_MAP = {
    "ELEVENLABS_API_KEY":        "**ElevenLabs**",
    "RUNWAY_API_KEY":            "**Runway**",
    "WAVESPEED_API_KEY":         "**WaveSpeed AI**",
    "BFL_API_KEY":               "**FLUX Kontext (BFL)**",
    "FAL_KEY":                   "**fal.ai**",
    "REPLICATE_API_TOKEN":       "**Replicate**",
    "SEGMIND_API_KEY":           "**Segmind**",
    "EVOLINK_API_KEY":           "**EvoLink**",
    "GEMINI_API_KEY":            "**Google Gemini**",
    "OPENAI_API_KEY":            "**OpenAI**",
    "ANTHROPIC_API_KEY":         "**Anthropic API**",
}


def _parse_legacy(label: str) -> Optional[str]:
    if not _LEGACY_MD.exists():
        return None
    try:
        content = _LEGACY_MD.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in content.splitlines():
        if label in line:
            # Extract the first backticked token
            m = re.search(r"`([^`]+)`", line)
            if m:
                return m.group(1)
    return None


def get_secret(env_name: str) -> str:
    """Retrieve a secret by env var name. Raises RuntimeError if not findable."""
    val = os.environ.get(env_name)
    if val:
        return val
    label = _LEGACY_LABEL_MAP.get(env_name)
    if label:
        legacy = _parse_legacy(label)
        if legacy:
            # Emit a one-time warning so callers know they're on the fallback path
            if not os.environ.get("_CREDSTORE_FALLBACK_WARNED"):
                print(
                    f"[credential_store] WARNING: {env_name} not in env — falling back "
                    f"to API_KEYS_MASTER.md. Prefix command with `doppler run -- ` for "
                    f"production use.",
                    file=sys.stderr,
                )
                os.environ["_CREDSTORE_FALLBACK_WARNED"] = "1"
            return legacy
    raise RuntimeError(
        f"{env_name} not available. Either:\n"
        f"  (a) run via `doppler run -- python3 <script>.py`, or\n"
        f"  (b) ensure {_LEGACY_MD} contains the key under label {label!r}.\n"
        f"See LD-208 (Doppler migration)."
    )


def get_secret_optional(env_name: str) -> Optional[str]:
    """Same as get_secret but returns None instead of raising when missing."""
    try:
        return get_secret(env_name)
    except RuntimeError:
        return None
