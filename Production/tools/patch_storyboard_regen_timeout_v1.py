#!/usr/bin/env python3
"""
Path B patch — REGEN-TIMEOUT-V1 (2026-04-25)

Adds a 30-second AbortController timeout to the storyboard's "Regen Audio"
button fetch call. Without this, if the server restarts mid-request the
browser hangs indefinitely with the spinner going. With the timeout, the
fetch aborts after 30s and shows "✗ Timed out — server restarted?" so Kim
knows to click again.
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_regen_timeout_v1_backup.html"

SENTINEL = "REGEN-TIMEOUT-V1"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


# The exact existing fetch call (no timeout)
OLD = (
    'fetch(SERVER+"/api/beat/regenerate_audio",{method:"POST",'
    'headers:{"Content-Type":"application/json"},'
    'body:JSON.stringify({beat:bid})})'
    '.then(function(r){return r.json();})'
    '.then(function(d){btn.disabled=false;btn.textContent="\U0001f399 Regen Audio";'
    'if(!si)return;var tr=d.tts_regen||{};'
    'if(tr.ok){si.textContent="\u2713 audio regen: "+tr.audio_file+" ("+(tr.audio_duration_s||0).toFixed(2)+"s, "+(tr.elapsed_s||0).toFixed(1)+"s call)";si.style.color="#2ecc71";}'
    'else{si.textContent="\u2717 "+((tr.error||d.error||"unknown").substring(0,80));si.style.color="#e74c3c";}})'
    '.catch(function(err){btn.disabled=false;btn.textContent="\U0001f399 Regen Audio";'
    'if(si){si.textContent="\u2717 "+err.message;si.style.color="#e74c3c";}});'
)

# Replacement: same call with 30s AbortController timeout
NEW = (
    '/* REGEN-TIMEOUT-V1: 30s abort so hung requests fail visibly */'
    'var _rac=new AbortController();'
    'var _rat=setTimeout(function(){_rac.abort();},30000);'
    'fetch(SERVER+"/api/beat/regenerate_audio",{method:"POST",'
    'headers:{"Content-Type":"application/json"},'
    'body:JSON.stringify({beat:bid}),signal:_rac.signal})'
    '.then(function(r){clearTimeout(_rat);return r.json();})'
    '.then(function(d){btn.disabled=false;btn.textContent="\U0001f399 Regen Audio";'
    'if(!si)return;var tr=d.tts_regen||{};'
    'if(tr.ok){si.textContent="\u2713 audio regen: "+tr.audio_file+" ("+(tr.audio_duration_s||0).toFixed(2)+"s, "+(tr.elapsed_s||0).toFixed(1)+"s call)";si.style.color="#2ecc71";}'
    'else{si.textContent="\u2717 "+((tr.error||d.error||"unknown").substring(0,80));si.style.color="#e74c3c";}})'
    '.catch(function(err){clearTimeout(_rat);btn.disabled=false;btn.textContent="\U0001f399 Regen Audio";'
    'if(si){si.textContent="\u2717 "+(err.name==="AbortError"?"Timed out \u2014 server restarted?":err.message);si.style.color="#e74c3c";}});'
)


def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if SENTINEL in html:
        print(f"ERROR: already patched ('{SENTINEL}' found).")
        sys.exit(1)

    if OLD not in html:
        print("ERROR: target fetch string not found — storyboard may have changed.")
        print("  Looking for the fetch call starting with:")
        print(f"  {OLD[:80]}...")
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
    print("  • Regen Audio button now aborts after 30s")
    print("  • Shows '✗ Timed out — server restarted?' on timeout")
    print("  • clearTimeout() on success/error prevents spurious aborts")


if __name__ == "__main__":
    main()
