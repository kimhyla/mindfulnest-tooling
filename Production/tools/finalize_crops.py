#!/usr/bin/env python3
"""
finalize_crops.py — Validate, copy, and register crop assets in Directus.

Reads a crop manifest JSON, validates dimensions, copies crops to Cropper/ folder,
and registers them in Directus prod_visual_assets.
"""

import json
import sys
import os
import shutil
import argparse
import urllib.request
import urllib.error
import ssl
from pathlib import Path

# Import validation functions from asset_validation.py (same directory)
sys.path.insert(0, os.path.dirname(__file__))
from asset_validation import validate_crop_dimensions, register_visual_asset


# ============================================================================
# Constants
# ============================================================================

DEFAULT_CROPPER_DIR = "/sessions/admiring-quirky-noether/mnt/Claude Mindfulnest Project Files/Cropper"
DIRECTUS_URL = "https://directus-production-3460.up.railway.app"


def _load_directus_credentials() -> tuple[str, str]:
    """Doppler-first Directus creds — blocker #97 (no hardcoded secrets).

    Mirrors build_storyboard.py / production_server.parse_api_keys (LD-208):
    DIRECTUS_ADMIN_* env wins; legacy DIRECTUS_EMAIL/PASSWORD accepted;
    API_KEYS_MASTER.md table fallback for local python3 runs.
    """
    email = (
        os.environ.get("DIRECTUS_ADMIN_EMAIL")
        or os.environ.get("DIRECTUS_EMAIL")
    )
    password = (
        os.environ.get("DIRECTUS_ADMIN_PASSWORD")
        or os.environ.get("DIRECTUS_PASSWORD")
    )
    if email and password:
        return email, password

    script_dir = os.path.dirname(os.path.abspath(__file__))
    for rel in ("../API_KEYS_MASTER.md", "../../Production/API_KEYS_MASTER.md"):
        path = os.path.normpath(os.path.join(script_dir, rel))
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        file_email = file_password = None
        for line in content.split("\n"):
            if "Directus" in line and "Admin Email" in line:
                parts = line.split("|")
                if len(parts) >= 4:
                    file_email = parts[3].strip().strip("`").strip()
            elif "Directus" in line and "Admin Password" in line:
                parts = line.split("|")
                if len(parts) >= 4:
                    file_password = parts[3].strip().strip("`").strip()
        if file_email and file_password:
            return file_email, file_password

    raise SystemExit(
        "finalize_crops: missing Directus credentials (blocker #97). "
        "Set DIRECTUS_ADMIN_EMAIL/DIRECTUS_ADMIN_PASSWORD via Doppler "
        "(or legacy DIRECTUS_EMAIL/DIRECTUS_PASSWORD), or place "
        "API_KEYS_MASTER.md under Production/."
    )


DIRECTUS_EMAIL, DIRECTUS_PASSWORD = _load_directus_credentials()


# ============================================================================
# Directus Authentication
# ============================================================================

def directus_authenticate(ssl_context):
    """
    Authenticate with Directus and return the access token.

    Args:
        ssl_context: ssl.SSLContext for secure connections

    Returns:
        str: access_token

    Raises:
        Exception: if authentication fails
    """
    auth_url = f"{DIRECTUS_URL}/auth/login"
    auth_data = json.dumps({
        "email": DIRECTUS_EMAIL,
        "password": DIRECTUS_PASSWORD
    }).encode('utf-8')

    request = urllib.request.Request(
        auth_url,
        data=auth_data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(request, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            token = data.get("data", {}).get("access_token")
            if not token:
                raise Exception("No access_token in auth response")
            return token
    except urllib.error.HTTPError as e:
        raise Exception(f"Directus auth failed: {e.code} {e.reason}")


# ============================================================================
# Manifest Loading & Validation
# ============================================================================

def load_manifest(manifest_path):
    """
    Load crop manifest from JSON file.

    Args:
        manifest_path (str): path to crop_manifest.json

    Returns:
        list: array of crop dicts

    Raises:
        FileNotFoundError: if manifest not found
        json.JSONDecodeError: if manifest is invalid JSON
    """
    with open(manifest_path, 'r') as f:
        return json.load(f)


def validate_manifest_entry(entry):
    """
    Validate a single manifest entry.

    Args:
        entry (dict): should have 'name', 'width', 'height', 'source_file'

    Returns:
        tuple: (is_valid, error_message or None)
    """
    required_fields = ['name', 'width', 'height', 'source_file']
    for field in required_fields:
        if field not in entry:
            return False, f"Missing field: {field}"

    if not isinstance(entry['width'], int) or not isinstance(entry['height'], int):
        return False, "width and height must be integers"

    if entry['width'] <= 0 or entry['height'] <= 0:
        return False, "width and height must be positive"

    source_file = entry['source_file']
    if not os.path.exists(source_file):
        return False, f"source_file not found: {source_file}"

    return True, None


# ============================================================================
# Processing Pipeline
# ============================================================================

def process_crop(entry, cropper_dir, module_id, ssl_context, dry_run=False):
    """
    Process a single crop: validate, copy, register.

    Args:
        entry (dict): manifest entry
        cropper_dir (str): destination directory for crops
        module_id (int): module_id for Directus registration
        ssl_context: SSL context for network calls
        dry_run (bool): if True, validate only, don't copy or register

    Returns:
        dict: report with keys: name, width, height, valid, error, copied, registered
    """
    report = {
        "name": entry.get("name", "UNKNOWN"),
        "width": entry.get("width", 0),
        "height": entry.get("height", 0),
        "valid": False,
        "error": None,
        "copied": False,
        "registered": False,
    }

    # Step 1: Validate manifest entry structure
    is_valid, error = validate_manifest_entry(entry)
    if not is_valid:
        report["error"] = f"Manifest validation failed: {error}"
        return report

    # Step 2: Validate crop dimensions (asset_validation.py)
    name = entry["name"]
    width = entry["width"]
    height = entry["height"]
    source_file = entry["source_file"]

    is_valid_dims, dim_error = validate_crop_dimensions(width, height)
    if not is_valid_dims:
        report["error"] = f"Dimension validation failed: {dim_error}"
        return report

    report["valid"] = True

    # If dry_run, stop here
    if dry_run:
        return report

    # Step 3: Copy to Cropper/ folder
    dest_filename = f"{name}.png"
    dest_path = os.path.join(cropper_dir, dest_filename)

    try:
        os.makedirs(cropper_dir, exist_ok=True)
        shutil.copy2(source_file, dest_path)
        report["copied"] = True
    except Exception as e:
        report["error"] = f"Copy failed: {e}"
        return report

    # Step 4: Register in Directus via asset_validation.register_visual_asset
    # Calculate relative path from project root
    project_root = "/sessions/admiring-quirky-noether/mnt/Claude Mindfulnest Project Files"
    try:
        rel_path = os.path.relpath(dest_path, project_root)
    except ValueError:
        rel_path = f"Cropper/{dest_filename}"

    asset_data = {
        "module_id": module_id,
        "filename": dest_filename,
        "filepath": rel_path,
        "asset_type": "crop_4x3",
        "width": width,
        "height": height,
        "status": "approved",
    }

    try:
        # register_visual_asset needs Directus auth token
        token = directus_authenticate(ssl_context)
        register_visual_asset(asset_data, token, ssl_context)
        report["registered"] = True
    except Exception as e:
        report["error"] = f"Directus registration failed: {e}"
        # Even if registration fails, the file was copied; don't undo that
        return report

    return report


# ============================================================================
# Report & Output
# ============================================================================

def print_report(reports, dry_run=False):
    """
    Print a formatted report of all processed crops.

    Args:
        reports (list): list of report dicts from process_crop
        dry_run (bool): if True, note that this was a dry run
    """
    print("\n" + "=" * 80)
    if dry_run:
        print("FINALIZE CROPS — DRY RUN (validation only, no changes)")
    else:
        print("FINALIZE CROPS — REPORT")
    print("=" * 80)

    for i, report in enumerate(reports, 1):
        name = report["name"]
        width = report["width"]
        height = report["height"]
        valid = report["valid"]
        error = report["error"]
        copied = report["copied"]
        registered = report["registered"]

        status_icon = "✓" if valid else "✗"
        print(f"\n[{i}] {name}")
        print(f"    Dimensions: {width}x{height} {status_icon}")

        if error:
            print(f"    ERROR: {error}")

        if not dry_run:
            if copied:
                print(f"    Copied: ✓")
            if registered:
                print(f"    Registered: ✓")

        if valid and not error:
            if dry_run:
                print(f"    Status: Ready to finalize")
            else:
                print(f"    Status: Complete")

    # Summary
    valid_count = sum(1 for r in reports if r["valid"])
    error_count = sum(1 for r in reports if r["error"])
    copied_count = sum(1 for r in reports if r["copied"])
    registered_count = sum(1 for r in reports if r["registered"])

    print("\n" + "-" * 80)
    print(f"Summary: {len(reports)} crops processed")
    print(f"  Valid: {valid_count}")
    print(f"  Errors: {error_count}")
    if not dry_run:
        print(f"  Copied: {copied_count}")
        print(f"  Registered: {registered_count}")
    print("=" * 80 + "\n")


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Validate, copy, and register crop assets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 finalize_crops.py --manifest crop_manifest.json --module-id 1
  python3 finalize_crops.py --manifest crop_manifest.json --dry-run
  python3 finalize_crops.py --manifest crop_manifest.json --cropper-dir /custom/path
        """
    )

    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to crop_manifest.json"
    )
    parser.add_argument(
        "--module-id",
        type=int,
        default=1,
        help="Module ID for Directus registration (default: 1)"
    )
    parser.add_argument(
        "--cropper-dir",
        default=DEFAULT_CROPPER_DIR,
        help=f"Destination directory for crops (default: {DEFAULT_CROPPER_DIR})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, don't copy or register"
    )

    args = parser.parse_args()

    # Load manifest
    try:
        manifest = load_manifest(args.manifest)
    except FileNotFoundError:
        print(f"ERROR: Manifest file not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in manifest: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(manifest, list):
        print("ERROR: Manifest must be a JSON array", file=sys.stderr)
        sys.exit(1)

    if not manifest:
        print("WARNING: Manifest is empty", file=sys.stderr)
        sys.exit(0)

    # Set up SSL context
    ssl_context = ssl.create_default_context()

    # Process each crop
    reports = []
    for entry in manifest:
        report = process_crop(
            entry,
            args.cropper_dir,
            args.module_id,
            ssl_context,
            dry_run=args.dry_run
        )
        reports.append(report)

    # Print report
    print_report(reports, dry_run=args.dry_run)

    # Exit with appropriate code
    error_count = sum(1 for r in reports if r["error"])
    if error_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
