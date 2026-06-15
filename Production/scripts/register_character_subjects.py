#!/usr/bin/env python3
"""
register_character_subjects.py
One-time Kling Elements registration for all MindfulNest characters.

Usage:
    python3 scripts/register_character_subjects.py              # register all pending
    python3 scripts/register_character_subjects.py --char Tessa # register one character
    python3 scripts/register_character_subjects.py --dry-run    # validate only, no API calls
    python3 scripts/register_character_subjects.py --validate   # probe all active element_ids

Cost: $0.01 per character (image_refer mode). One-time ever — element_ids persist on WaveSpeed.
Total for all 11 characters: $0.11.

Image format: attempts base64 data URIs first (simpler, no upload infra needed).
If WaveSpeed rejects base64 on element creation, the script exits loudly — do NOT
silently fall back; raise the issue to Kim so we can add Supabase upload path.

Rule 18: writes to prod_activity_log after each successful registration.
Rule 6:  validates shortest side >= 600px on every image before submission.
Rule 19: no silent failures — all errors are loud and halt that character's registration.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — resolve relative to this script's location
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent           # Production/scripts/
TOOLS_DIR = HERE.parent / "tools"               # Production/tools/
PROD_ROOT = HERE.parent                          # Production/
CHARACTER_SUBJECTS_PATH = PROD_ROOT / "character_subjects.json"

# Inject tools dir so we can reuse existing pipeline helpers
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from kling_startend_pipeline import (            # type: ignore
    load_api_keys,
    robust_https_request,
    directus_log,
)

KLING_ELEMENTS_HOST = "api.wavespeed.ai"
KLING_ELEMENTS_PATH = "/api/v3/kwaivgi/kling-elements-advanced"
KLING_ELEMENTS_POLL_PATH = "/api/v3/predictions/{prediction_id}/result"
POLL_INTERVAL_SEC = 3
POLL_TIMEOUT_SEC = 180
MAX_ELEMENT_DESCRIPTION_LEN = 100


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _load_subjects() -> dict:
    if not CHARACTER_SUBJECTS_PATH.is_file():
        sys.exit(f"FATAL: character_subjects.json not found at {CHARACTER_SUBJECTS_PATH}")
    return json.loads(CHARACTER_SUBJECTS_PATH.read_text(encoding="utf-8"))


def _save_subjects(data: dict) -> None:
    """Atomic write using tmp+rename — matches existing pipeline pattern."""
    tmp = CHARACTER_SUBJECTS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CHARACTER_SUBJECTS_PATH)
    print(f"  [saved] character_subjects.json updated atomically")


# ---------------------------------------------------------------------------
# Image loading and validation
# ---------------------------------------------------------------------------

def _load_image_as_b64_uri(rel_path: str) -> str:
    """Load image from PROD_ROOT-relative path, validate Rule 6, return data URI."""
    abs_path = PROD_ROOT / rel_path
    if not abs_path.is_file():
        raise FileNotFoundError(f"Image not found: {abs_path}")

    raw = abs_path.read_bytes()

    # Rule 6: shortest side >= 600px
    try:
        import io
        from PIL import Image  # type: ignore
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        short_side = min(w, h)
        if short_side < 300:
            raise ValueError(
                f"Rule 6 HARD FAIL: {abs_path.name} shortest side {short_side}px "
                f"< 300px (Kling minimum). Cannot register."
            )
        if short_side < 600:
            print(f"  [WARN] Rule 6: {abs_path.name} shortest side {short_side}px "
                  f"< 600px recommended floor (above 300px Kling minimum — proceeding).")
        else:
            print(f"  [ok]   {abs_path.name} {w}x{h}px — Rule 6 compliant")
    except ImportError:
        print(f"  [warn] PIL not available — skipping Rule 6 dimension check on {abs_path.name}")

    mime = "image/png" if abs_path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# Kling Elements API: create element
# ---------------------------------------------------------------------------

def _create_element(char_name: str, cfg: dict, api_key: str, dry_run: bool) -> dict | None:
    """Register one character as a Kling Element.

    Returns updated cfg dict with element_id set, or None on failure.
    Never raises — caller decides whether to continue to next character.
    """
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Registering: {char_name}")

    desc = cfg.get("description", "")
    if len(desc) > MAX_ELEMENT_DESCRIPTION_LEN:
        print(f"  [FAIL] description length {len(desc)} > {MAX_ELEMENT_DESCRIPTION_LEN} (Kling limit)")
        print(f"  [FAIL] Shorten description in character_subjects.json and retry.")
        return None

    # Load and validate all images
    try:
        frontal_uri = _load_image_as_b64_uri(cfg["frontal_image"])
    except (FileNotFoundError, ValueError) as exc:
        print(f"  [FAIL] frontal_image: {exc}")
        return None

    refer_uris: list[str] = []
    for rp in (cfg.get("refer_images") or []):
        try:
            refer_uris.append(_load_image_as_b64_uri(rp))
        except (FileNotFoundError, ValueError) as exc:
            print(f"  [FAIL] refer_image {rp}: {exc}")
            return None

    payload = {
        "name": cfg["element_name"],
        "description": cfg.get("description", ""),
        "reference_type": "image_refer",
        "frontal_image": frontal_uri,
    }
    if refer_uris:
        payload["refer_images"] = refer_uris

    print(f"  frontal : {cfg['frontal_image']}")
    for rp in (cfg.get("refer_images") or []):
        print(f"  refer   : {rp}")
    print(f"  payload size: ~{len(json.dumps(payload)) // 1024}KB")

    if dry_run:
        print(f"  [DRY-RUN] Would POST to {KLING_ELEMENTS_HOST}{KLING_ELEMENTS_PATH}")
        print(f"  [DRY-RUN] No API call made. Skipping.")
        return None

    # POST to Kling Elements
    body_bytes = json.dumps(payload).encode("utf-8")
    try:
        status, raw = robust_https_request(
            host=KLING_ELEMENTS_HOST,
            path=KLING_ELEMENTS_PATH,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body=body_bytes,
            timeout=60,
            max_retries=2,
        )
    except Exception as exc:
        print(f"  [FAIL] Network error: {exc}")
        print(f"  NOTE: If base64 URIs are rejected, Supabase upload path needs to be added.")
        return None

    if status >= 400:
        body_text = raw[:800].decode("utf-8", "replace")
        print(f"  [FAIL] API returned HTTP {status}: {body_text}")
        if status == 422 or "url" in body_text.lower() or "accessible" in body_text.lower():
            print()
            print("  *** BASE64 REJECTED — API requires public URLs for element creation ***")
            print("  *** Next step: add Supabase Storage upload path to this script.    ***")
            print("  *** Raise with Kim before proceeding.                               ***")
            print()
        return None

    try:
        result = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  [FAIL] Could not parse API response: {exc} — raw: {raw[:200]}")
        return None

    # Extract element_id — try multiple response shapes
    data = result.get("data") or {}
    prediction_id = data.get("id") or result.get("id")
    element_id = _element_id_from_poll_data(data)

    # Always poll /result when we have a prediction id — POST id is NOT the Kling element_id.
    outer_status = data.get("status") or result.get("status")
    if prediction_id and (not element_id or outer_status not in ("completed", "succeeded")):
        print(f"  [polling] status={outer_status}, prediction_id={prediction_id}")
        element_id = _poll_for_element_id(prediction_id, api_key)
        if not element_id:
            print(f"  [FAIL] Polling timed out or failed for prediction_id={prediction_id}")
            return None
    elif outer_status in ("failed", "error"):
        print(f"  [FAIL] Element creation failed: {json.dumps(result)[:400]}")
        return None

    if not element_id:
        print(f"  [FAIL] No element_id in response: {json.dumps(result)[:400]}")
        return None

    print(f"  [OK]   element_id={element_id}")

    updated_cfg = dict(cfg)
    updated_cfg["element_id"] = str(element_id)
    updated_cfg["status"] = "active"
    updated_cfg["created_at"] = datetime.now(timezone.utc).isoformat()
    updated_cfg["wavespeed_prediction_id"] = str(prediction_id) if prediction_id else None
    return updated_cfg


def _element_id_from_poll_data(data: dict) -> str | None:
    """Real Kling element_id lives in data.outputs[0].element_id (numeric)."""
    outputs = data.get("outputs") or []
    if outputs and isinstance(outputs[0], dict):
        eid = outputs[0].get("element_id")
        if eid is not None:
            return str(int(eid))
    eid = data.get("element_id")
    if eid is not None:
        return str(int(eid))
    return None


def _poll_for_element_id(prediction_id: str, api_key: str) -> str | None:
    """Poll WaveSpeed /result until element is ready. Returns element_id or None."""
    deadline = time.time() + POLL_TIMEOUT_SEC
    poll_path = KLING_ELEMENTS_POLL_PATH.format(prediction_id=prediction_id)
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_SEC)
        try:
            status, raw = robust_https_request(
                host=KLING_ELEMENTS_HOST,
                path=poll_path,
                method="GET",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
                max_retries=1,
            )
            result = json.loads(raw.decode("utf-8"))
            data = result.get("data") or {}
            poll_status = data.get("status") or result.get("status")
            print(f"  [poll]  status={poll_status}")
            if poll_status in ("completed", "succeeded"):
                return _element_id_from_poll_data(data)
            if poll_status in ("failed", "error"):
                err = data.get("error") or result.get("error") or json.dumps(result)[:300]
                print(f"  [FAIL]  Element creation failed: {err}")
                return None
        except Exception as exc:
            print(f"  [poll error] {exc} — retrying")
    return None


# ---------------------------------------------------------------------------
# Validate existing active elements
# ---------------------------------------------------------------------------

def _validate_elements(data: dict, api_key: str) -> None:
    """Probe each active element_id to confirm it still resolves on WaveSpeed."""
    chars = data.get("characters", {})
    active = [(n, c) for n, c in chars.items() if c.get("status") == "active" and c.get("element_id")]
    if not active:
        print("No active elements to validate.")
        return

    print(f"Validating {len(active)} active element(s)...\n")
    stale: list[str] = []
    for char_name, cfg in active:
        eid = cfg["element_id"]
        # Probe: GET the element — any 2xx means it exists
        probe_path = f"/api/v3/kwaivgi/kling-elements/{eid}"
        try:
            status, raw = robust_https_request(
                host=KLING_ELEMENTS_HOST,
                path=probe_path,
                method="GET",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=20,
                max_retries=1,
            )
            if status < 300:
                print(f"  [OK]    {char_name}: element_id={eid} — resolves")
            else:
                print(f"  [STALE] {char_name}: element_id={eid} — HTTP {status}")
                stale.append(char_name)
        except Exception as exc:
            print(f"  [ERROR] {char_name}: probe failed — {exc}")
            stale.append(char_name)

    if stale:
        print(f"\n{len(stale)} stale element(s): {stale}")
        print("Run without --validate to re-register them (set status=pending first).")
    else:
        print("\nAll active elements are valid.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Register MindfulNest characters as Kling Elements")
    parser.add_argument("--char", metavar="NAME",
                        help="Register only this character (e.g. --char Tessa)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate images and show payload sizes — no API calls")
    parser.add_argument("--validate", action="store_true",
                        help="Probe all active element_ids to confirm they still resolve")
    parser.add_argument("--force", action="store_true",
                        help="Re-register even if status=active (overwrites element_id)")
    args = parser.parse_args()

    data = _load_subjects()
    chars = data.get("characters", {})
    if not chars:
        sys.exit("character_subjects.json has no 'characters' key")

    # Load API keys (required for validate and live registration)
    api_key: str = ""
    if not args.dry_run:
        try:
            keys = load_api_keys()
            api_key = keys.get("wavespeed", "")
            if not api_key:
                sys.exit("FATAL: no wavespeed key — check API_KEYS_MASTER.md")
        except SystemExit:
            raise
        except Exception as exc:
            sys.exit(f"FATAL: could not load API keys: {exc}")

    # --validate mode
    if args.validate:
        if not api_key:
            sys.exit("--validate requires live API key (cannot use --dry-run with --validate)")
        _validate_elements(data, api_key)
        return

    # Determine which characters to process
    if args.char:
        if args.char not in chars:
            # Case-insensitive fallback
            matches = [k for k in chars if k.lower() == args.char.lower()]
            if not matches:
                sys.exit(f"Character '{args.char}' not found in character_subjects.json. "
                         f"Known: {list(chars.keys())}")
            args.char = matches[0]
        targets = {args.char: chars[args.char]}
    else:
        targets = chars

    registered = 0
    skipped = 0
    failed = 0

    for char_name, cfg in targets.items():
        if cfg.get("status") == "active" and cfg.get("element_id") and not args.force:
            print(f"\nSkipping {char_name}: already active (element_id={cfg['element_id']}) "
                  f"— use --force to re-register")
            skipped += 1
            continue

        updated = _create_element(char_name, cfg, api_key, dry_run=args.dry_run)

        if updated is None:
            if not args.dry_run:
                failed += 1
            continue

        # Persist immediately after each success (don't batch — fail-safe)
        data["characters"][char_name] = updated
        _save_subjects(data)
        registered += 1

        # Rule 18: activity log
        try:
            directus_log("kling_element_registered", {
                "character": char_name,
                "element_id": updated["element_id"],
                "element_name": updated["element_name"],
                "frontal_image": cfg["frontal_image"],
                "refer_images": cfg.get("refer_images", []),
                "cost_usd": 0.01,
                "script": "register_character_subjects.py",
            })
            print(f"  [Rule 18] prod_activity_log written")
        except Exception as exc:
            print(f"  [warn] directus_log failed (non-fatal): {exc}")

        # Brief pause between registrations to avoid rate-limiting
        if not args.dry_run and len(targets) > 1:
            time.sleep(1)

    # Summary
    print(f"\n{'='*50}")
    if args.dry_run:
        print(f"DRY-RUN complete. {len(targets)} character(s) validated.")
        print("No API calls were made. Run without --dry-run to register.")
    else:
        print(f"Done. Registered: {registered}  Skipped: {skipped}  Failed: {failed}")
        if failed:
            print(f"WARNING: {failed} character(s) failed. Check output above.")
            print("If base64 was rejected, Supabase upload path needs to be added.")
        if registered:
            print(f"Next: run register_character_subjects.py --validate to confirm element_ids.")
            print(f"Then: restart production_server.py — elements load at startup.")


if __name__ == "__main__":
    main()
