"""
MindfulNest Layer 2: Image Size Validation for Directus Asset Registration

This module enforces hard dimension validation when registering visual assets
in Directus. It prevents undersized crops from being registered, ensuring all
production storyboards and video beats meet quality standards.

Usage:
    from asset_validation import validate_crop_dimensions, register_visual_asset, audit_registry_dimensions

    # Test a local image
    result = validate_crop_dimensions("/path/to/image.png", min_shortest_side=600)
    print(result)

    # Register an asset with validation
    response = register_visual_asset(
        token="...",
        directus_url="https://...",
        asset_data={
            "module_id": 1,
            "filename": "tessa_closeup.png",
            "filepath": "/path/to/tessa_closeup.png",
            "asset_type": "crop_4x3",
            "width": 1016,
            "height": 762
        }
    )

    # Audit all registered crops
    report = audit_registry_dimensions(token, directus_url)
"""

import json
import os
from pathlib import Path
from PIL import Image
import urllib.request
import urllib.error
import urllib.parse


# ---------------------------------------------------------------------------
# Layer 2a: Image Dimension Validation
# ---------------------------------------------------------------------------

def validate_crop_dimensions(filepath, min_shortest_side=600):
    """
    Validate that a crop image meets minimum dimension requirements.

    This is the core validation gate. All crops must have a shortest side
    >= min_shortest_side (default 600px) to ensure video playback quality.

    Args:
        filepath (str): Absolute path to the image file
        min_shortest_side (int): Minimum pixel count for the shorter dimension.
                                 Default 600px ensures 4:3 crops fill iPad screens.

    Returns:
        dict: {
            "valid": bool,           # True if dimensions pass
            "width": int,            # Image width in pixels
            "height": int,           # Image height in pixels
            "shortest_side": int,    # min(width, height)
            "reason": str            # Human-readable explanation
        }

    Example responses:
        Valid:   {"valid": True, "width": 1016, "height": 762, "shortest_side": 762,
                  "reason": "OK"}
        Invalid: {"valid": False, "width": 503, "height": 377, "shortest_side": 377,
                  "reason": "Shortest side 377px < 600px minimum"}
        Error:   {"valid": False, "width": None, "height": None, "shortest_side": None,
                  "reason": "File not found: /path/to/image.png"}
    """
    # Check file exists
    if not os.path.isfile(filepath):
        return {
            "valid": False,
            "width": None,
            "height": None,
            "shortest_side": None,
            "reason": f"File not found: {filepath}"
        }

    # Open image and get dimensions
    try:
        img = Image.open(filepath)
        width, height = img.size
    except Exception as e:
        return {
            "valid": False,
            "width": None,
            "height": None,
            "shortest_side": None,
            "reason": f"Cannot read image: {e}"
        }

    shortest_side = min(width, height)

    # Validate
    if shortest_side < min_shortest_side:
        return {
            "valid": False,
            "width": width,
            "height": height,
            "shortest_side": shortest_side,
            "reason": f"Shortest side {shortest_side}px < {min_shortest_side}px minimum"
        }

    return {
        "valid": True,
        "width": width,
        "height": height,
        "shortest_side": shortest_side,
        "reason": "OK"
    }


# ---------------------------------------------------------------------------
# Layer 2b: Directus Registration with Validation Gate
# ---------------------------------------------------------------------------

def register_visual_asset(token, directus_url, asset_data, enforce_dimensions=True, min_shortest_side=600):
    """
    Register a visual asset in Directus prod_visual_assets with dimension validation.

    This function acts as a validation gate: if enforce_dimensions=True and the
    asset is a crop, it validates dimensions BEFORE attempting Directus write.
    Undersized assets are rejected with a clear error message.

    Args:
        token (str): Directus JWT access token (from /auth/login)
        directus_url (str): Directus instance URL (e.g., https://directus-production-3460.up.railway.app)
        asset_data (dict): Asset metadata to register:
            {
                "module_id": 1,              # (int, REQUIRED) Directus prod_modules.m_number
                "filename": "tessa.png",     # (str, REQUIRED) Filename only
                "filepath": "/abs/path",     # (str, REQUIRED) Absolute local path for validation
                "asset_type": "crop_4x3",    # (str, REQUIRED) One of: crop_4x3, crop, crop_square, tts_audio, config, reference_master, production_tool, etc.
                "width": 1016,               # (int, OPTIONAL) Pre-measured width (used if file not accessible)
                "height": 762,               # (int, OPTIONAL) Pre-measured height (used if file not accessible)
                "event_number": 1,           # (int, OPTIONAL)
                "shot_number": 1,            # (int, OPTIONAL)
                "status": "approved",        # (str, OPTIONAL) Default "approved"
                ... any other fields ...
            }
        enforce_dimensions (bool): If True, validate dimensions for crop assets.
                                    If False, skip validation (escape hatch).
                                    Default: True
        min_shortest_side (int): Minimum pixel count for shortest dimension.
                                 Default: 600px

    Returns:
        dict: {
            "registered": bool,          # True if successfully written to Directus
            "id": directus_record_id,    # If registered: Directus-generated ID
            "reason": str,               # Status message or error explanation
            "validation": dict           # (if validated) Result from validate_crop_dimensions()
        }

    Example responses:
        Success:   {"registered": True, "id": 42, "reason": "Asset registered in Directus",
                   "validation": {"valid": True, "width": 1016, "height": 762, ...}}
        Reject:    {"registered": False, "id": None, "reason": "Shortest side 377px < 600px minimum",
                   "validation": {"valid": False, "width": 503, "height": 377, ...}}
        No-check:  {"registered": True, "id": 42, "reason": "Asset registered (non-crop, no validation)",
                   "validation": None}
        Error:     {"registered": False, "id": None, "reason": "HTTP 500: ...", "validation": None}
    """
    asset_type = asset_data.get("asset_type", "unknown")
    crop_types = {"crop_4x3", "crop", "crop_square"}
    is_crop = asset_type in crop_types

    validation_result = None

    # ========== VALIDATION GATE ==========
    if enforce_dimensions and is_crop:
        filepath = asset_data.get("filepath")
        if not filepath:
            return {
                "registered": False,
                "id": None,
                "reason": "asset_data['filepath'] required for dimension validation",
                "validation": None
            }

        validation_result = validate_crop_dimensions(filepath, min_shortest_side)
        if not validation_result["valid"]:
            return {
                "registered": False,
                "id": None,
                "reason": validation_result["reason"],
                "validation": validation_result
            }

    # ========== DIRECTUS WRITE ==========
    try:
        url = f"{directus_url.rstrip('/')}/items/prod_visual_assets"

        # Prepare request
        payload = json.dumps(asset_data).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        # Execute
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            body = json.loads(resp.read().decode("utf-8"))
            record_id = body.get("data", {}).get("id")

            return {
                "registered": True,
                "id": record_id,
                "reason": "Asset registered in Directus",
                "validation": validation_result
            }
        except urllib.error.HTTPError as e:
            error_body = ""
            if e.fp:
                try:
                    error_body = e.read().decode("utf-8")
                    error_json = json.loads(error_body)
                    errors = error_json.get("errors", [])
                    if errors:
                        error_body = errors[0].get("message", error_body)
                except:
                    pass

            return {
                "registered": False,
                "id": None,
                "reason": f"HTTP {e.code}: {error_body}",
                "validation": validation_result
            }

    except Exception as e:
        return {
            "registered": False,
            "id": None,
            "reason": f"Error registering asset: {e}",
            "validation": validation_result
        }


# ---------------------------------------------------------------------------
# Layer 2c: Audit All Registered Crops
# ---------------------------------------------------------------------------

def audit_registry_dimensions(token, directus_url, module_id=None, min_shortest_side=600):
    """
    Audit all crop assets in Directus prod_visual_assets for dimension compliance.

    Queries all crop-type assets (crop_4x3, crop, crop_square) from the registry
    and checks dimensions against the minimum threshold. Useful for session-start
    validation and compliance reports.

    Args:
        token (str): Directus JWT access token
        directus_url (str): Directus instance URL
        module_id (int, optional): If provided, audit only assets for this module.
                                   If None, audit all modules.
        min_shortest_side (int): Minimum pixel count for shortest dimension.
                                 Default: 600px

    Returns:
        dict: {
            "total_crops": int,           # Total crop assets in registry
            "audit_timestamp": str,       # ISO timestamp
            "module_id_filter": int|None, # Module filter applied (or None for all)
            "min_shortest_side": int,     # Dimension threshold used
            "results": [                  # Array of audit results
                {
                    "id": 42,
                    "module_id": 1,
                    "filename": "tessa_closeup.png",
                    "asset_type": "crop_4x3",
                    "width": 1016,
                    "height": 762,
                    "shortest_side": 762,
                    "status": "ok"  # "ok" or "undersized"
                },
                ...
            ],
            "summary": {
                "ok_count": int,
                "undersized_count": int,
                "undersized_assets": [  # List of undersized filenames
                    {"filename": "bad_crop.png", "shortest_side": 377}
                ]
            },
            "error": str|None             # If query failed, error message here
        }
    """
    from datetime import datetime, timezone

    crop_types = ["crop_4x3", "crop", "crop_square"]

    try:
        # Build query: all crop-type assets
        url = f"{directus_url.rstrip('/')}/items/prod_visual_assets"

        # Filter for crop types
        params = {
            "filter[asset_type][_in]": ",".join(crop_types)
        }

        # Optional module filter
        if module_id is not None:
            params["filter[module_id][_eq]"] = str(module_id)

        # Add fields to ensure we get dimensions
        params["fields"] = "id,module_id,filename,asset_type,width,height,status"
        params["limit"] = 1000  # Allow large audits

        # Build URL with query string
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        req = urllib.request.Request(full_url, headers=headers, method="GET")
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read().decode("utf-8"))

        assets = body.get("data", [])

        # Audit each asset
        results = []
        ok_count = 0
        undersized_count = 0
        undersized_list = []

        for asset in assets:
            asset_id = asset.get("id")
            module_id_val = asset.get("module_id")
            filename = asset.get("filename", "unknown")
            asset_type = asset.get("asset_type")
            width = asset.get("width")
            height = asset.get("height")

            if width is None or height is None:
                status = "unknown"
                shortest = None
            else:
                shortest = min(width, height)
                status = "ok" if shortest >= min_shortest_side else "undersized"

                if status == "undersized":
                    undersized_count += 1
                    undersized_list.append({"filename": filename, "shortest_side": shortest})
                else:
                    ok_count += 1

            results.append({
                "id": asset_id,
                "module_id": module_id_val,
                "filename": filename,
                "asset_type": asset_type,
                "width": width,
                "height": height,
                "shortest_side": shortest,
                "status": status
            })

        return {
            "total_crops": len(assets),
            "audit_timestamp": datetime.now(timezone.utc).isoformat(),
            "module_id_filter": module_id,
            "min_shortest_side": min_shortest_side,
            "results": results,
            "summary": {
                "ok_count": ok_count,
                "undersized_count": undersized_count,
                "undersized_assets": undersized_list
            },
            "error": None
        }

    except urllib.error.HTTPError as e:
        error_body = ""
        if e.fp:
            try:
                error_body = e.read().decode("utf-8")
            except:
                pass
        return {
            "total_crops": 0,
            "audit_timestamp": datetime.now(timezone.utc).isoformat(),
            "module_id_filter": module_id,
            "min_shortest_side": min_shortest_side,
            "results": [],
            "summary": {"ok_count": 0, "undersized_count": 0, "undersized_assets": []},
            "error": f"HTTP {e.code}: {error_body}"
        }
    except Exception as e:
        return {
            "total_crops": 0,
            "audit_timestamp": datetime.now(timezone.utc).isoformat(),
            "module_id_filter": module_id,
            "min_shortest_side": min_shortest_side,
            "results": [],
            "summary": {"ok_count": 0, "undersized_count": 0, "undersized_assets": []},
            "error": f"Query failed: {e}"
        }


# ---------------------------------------------------------------------------
# Test / CLI Interface
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        # Test: python3 asset_validation.py validate /path/to/image.png
        filepath = sys.argv[2] if len(sys.argv) > 2 else None
        if not filepath:
            print("Usage: python3 asset_validation.py validate <filepath>")
            sys.exit(1)

        result = validate_crop_dimensions(filepath)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 asset_validation.py validate <filepath>")
        print("       (DRY RUN) register_visual_asset() and audit_registry_dimensions() available via import")
