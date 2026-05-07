#!/usr/bin/env python3
"""
CSS fix — CRFIX-LIBFIX-V7 (2026-04-25)

Root cause: <input type="file"> inside .mn-lib-upload-btn has no display:none,
so it renders as a visible file-picker inside the label, making the label a
huge tall rectangle instead of a compact button.

Fix: hide the input, fix button height to 32px.
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_libfixv7_backup.html"

SENTINEL = "CRFIX-LIBFIX-V7"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<style>
/* =========================================================
   CRFIX-LIBFIX-V7 (2026-04-25)
   Fix: hide the file input inside the upload label so it
   looks like a compact button, not a giant rectangle.
   ========================================================= */

/* Constrain the label to button size */
body > label.mn-lib-upload-btn {
  height: 32px !important;
  line-height: 32px !important;
  overflow: hidden !important;
  padding: 0 8px !important;
  white-space: nowrap !important;
}

/* Hide the file input — clicking the label triggers it via browser default */
body > label.mn-lib-upload-btn input[type="file"],
body > label.mn-lib-upload-btn input.mn-lib-upload-input {
  position: absolute !important;
  width: 0 !important;
  height: 0 !important;
  opacity: 0 !important;
  overflow: hidden !important;
  pointer-events: none !important;
}
</style>
<!-- CRFIX-LIBFIX-V7 -->
"""


def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if SENTINEL in html:
        print(f"ERROR: already patched ('{SENTINEL}' found).")
        sys.exit(1)

    if "CRFIX-LIBFIX-V6" not in html:
        print("ERROR: CRFIX-LIBFIX-V6 not found — apply V6 patch first.")
        sys.exit(1)

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 fingerprint changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    expected = PATCH.count(SENTINEL)
    if patched.count(SENTINEL) != expected:
        print(f"ABORT: sentinel {patched.count(SENTINEL)} ≠ {expected}")
        sys.exit(1)
    print(f"  ✓ Sentinel ×{expected}")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".html", dir=HTML_PATH.parent)
    try:
        with open(tmp_fd, 'w', encoding="utf-8") as f:
            f.write(patched)
        shutil.move(tmp_path, str(HTML_PATH))
    except Exception as e:
        import os; os.unlink(tmp_path)
        print(f"ABORT: write failed — {e}"); sys.exit(1)

    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")
    print()
    print("Fix applied:")
    print("  • input[type=file] inside label now 0x0 invisible (clicking label still triggers it)")
    print("  • label constrained to height:32px — looks like a compact button")
    print()
    print("Remind Kim: Cmd+Shift+R to reload.")


if __name__ == "__main__":
    main()
