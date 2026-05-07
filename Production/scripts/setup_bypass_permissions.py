#!/usr/bin/env python3
"""
Idempotent bootstrap: set bypassPermissions in both project-level and user-level
Claude Code settings. Run from terminal CLI on any machine after reinstall or
first-time Windows setup.

Usage:
    python3 Production/scripts/setup_bypass_permissions.py

Locked decision: BYPASS_PERMISSIONS_PERMANENT_V1 (2026-04-28)
"""
import json
import pathlib
import sys
import tempfile


def set_bypass(path: pathlib.Path, label: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  {label}: ERROR — could not parse JSON: {e}", file=sys.stderr)
            return False
    else:
        data = {}

    if data.get("defaultMode") == "bypassPermissions":
        print(f"  {label}: already set — no change needed")
        return True

    data["defaultMode"] = "bypassPermissions"
    data["skipAutoPermissionPrompt"] = True
    data.setdefault("permissions", {})
    data["permissions"]["defaultMode"] = "bypassPermissions"

    tmp = path.with_suffix(".json.tmp")
    try:
        serialized = json.dumps(data, indent=2)
        tmp.write_text(serialized, encoding="utf-8")
        # Validate JSON is parseable before committing
        json.loads(tmp.read_text(encoding="utf-8"))
        tmp.replace(path)
    except Exception as e:
        print(f"  {label}: ERROR — write failed: {e}", file=sys.stderr)
        if tmp.exists():
            tmp.unlink()
        return False

    # Verify
    check = json.loads(path.read_text(encoding="utf-8"))
    if check.get("defaultMode") != "bypassPermissions":
        print(f"  {label}: ERROR — verification failed after write", file=sys.stderr)
        return False

    print(f"  {label}: set to bypassPermissions ✓")
    return True


def main():
    success = True

    # 1. User-level (~/.claude/settings.json)
    print("User-level settings:")
    user_settings = pathlib.Path.home() / ".claude" / "settings.json"
    success &= set_bypass(user_settings, str(user_settings))

    # 2. Project-level (.claude/settings.json relative to this script)
    script_dir = pathlib.Path(__file__).resolve().parent        # Production/scripts/
    project_root = script_dir.parent.parent                      # project root
    project_settings = project_root / ".claude" / "settings.json"
    print("Project-level settings:")
    success &= set_bypass(project_settings, str(project_settings))

    if success:
        print("\nDone. Restart any running 'claude' sessions for changes to take effect.")
    else:
        print("\nOne or more writes failed — see errors above.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
