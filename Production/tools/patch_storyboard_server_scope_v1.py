#!/usr/bin/env python3
"""
Path B patch — SERVER-SCOPE-V1 (2026-04-25)

Root cause fix for "🎙 Regen Audio stuck on regenerating…" forever.

The render() function is defined in the GLOBAL <script> block (lines 261-754).
It uses `SERVER` in both the onblur auto-regen and the explicit Regen Audio
onclick. But `SERVER` is NEVER declared in that global block — only `_TOP_SERVER`
is (line 313). All other `var SERVER = "http://localhost:5111"` declarations are
inside IIFEs and therefore local, not global.

When Kim clicks Regen Audio:
  1. btn.textContent = "🎙 regenerating…" — RUNS (button visually stuck)
  2. setTimeout(..., 30000) — RUNS (30s timer started)
  3. fetch(SERVER + ...) — THROWS ReferenceError: SERVER is not defined
  4. .catch() NEVER fires (fetch promise never created)
  5. Button stays "regenerating…" forever; 30s abort has no fetch to cancel.

Fix: add `var SERVER = _TOP_SERVER;` on the line after _TOP_SERVER is declared
in the global block. This propagates the correct server URL into all render()
fetch calls with zero structural changes.

Verification: base64 fingerprint must be byte-identical before/after.
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_server_scope_v1_backup.html"

SENTINEL = "SERVER-SCOPE-V1"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


# The exact existing string (unique — only one occurrence in the file)
OLD = 'var _TOP_SERVER = "http://localhost:5111";\nfunction freshBeatAudioUrl(i){'

# Add global SERVER alias on the line immediately after _TOP_SERVER declaration
NEW = ('var _TOP_SERVER = "http://localhost:5111";\n'
       'var SERVER = _TOP_SERVER; /* SERVER-SCOPE-V1: global alias for render() fetch calls */\n'
       'function freshBeatAudioUrl(i){')


def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if SENTINEL in html:
        print(f"ERROR: already patched ('{SENTINEL}' found).")
        sys.exit(1)

    if OLD not in html:
        print("ERROR: target string not found.")
        print(f"  Looking for: {OLD[:80]!r}...")
        sys.exit(1)

    count = html.count(OLD)
    if count != 1:
        print(f"ERROR: expected 1 match, found {count}. Aborting.")
        sys.exit(1)

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    patched = html.replace(OLD, NEW, 1)

    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 fingerprint changed.")
        sys.exit(1)
    print("  ✓ Base64 byte-identical")

    if patched.count(SENTINEL) != 1:
        print(f"ABORT: sentinel count {patched.count(SENTINEL)} ≠ 1")
        sys.exit(1)
    print("  ✓ Sentinel ×1")

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
    print("Patch applied:")
    print("  • var SERVER = _TOP_SERVER added to global scope")
    print("  • render() onblur auto-regen fetch now works")
    print("  • render() Regen Audio button onclick fetch now works")
    print("  • ReferenceError: SERVER is not defined — FIXED")


if __name__ == "__main__":
    main()
