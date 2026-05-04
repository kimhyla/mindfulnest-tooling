#!/usr/bin/env python3
"""
Poll a WaveSpeed job and download the result if complete.
Usage: python3 poll_job.py <job_id> [output_path]

Example:
  python3 poll_job.py d1a8939146164cfbb9d5878e43573a8c
  python3 poll_job.py d1a8939146164cfbb9d5878e43573a8c ../Event_1/animation_clips/beat_03_lipsync_v2.mp4
"""

# --- WA-C14 Doppler migration (per LD-208) ---
# credential_store reads from Doppler env vars first, falls back to API_KEYS_MASTER.md.
import os as _os, sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve()
while _p.parent != _p and _p.name != "Production":
    _p = _p.parent
if _p.name == "Production":
    _sys.path.insert(0, str(_p))
from lib.credential_store import get_secret  # noqa: E402
# --- end WA-C14 boilerplate ---
import sys, json, subprocess, os
from pathlib import Path

API_KEY = get_secret("WAVESPEED_API_KEY")

if len(sys.argv) < 2:
    print("Usage: python3 poll_job.py <job_id> [output_path]")
    sys.exit(1)

job_id = sys.argv[1]
dest = Path(sys.argv[2]) if len(sys.argv) > 2 else None
url = f"https://api.wavespeed.ai/api/v3/predictions/{job_id}/result"

print(f"Polling: {url}")
r = subprocess.run(
    ["curl", "-s", "-S", "-m", "20",
     "-H", f"Authorization: Bearer {API_KEY}", url],
    capture_output=True, text=True, timeout=30
)

if r.returncode != 0:
    print(f"WaveSpeed unreachable (curl exit {r.returncode}). Try again in a few minutes.")
    sys.exit(1)

data = json.loads(r.stdout)
inner = data.get("data") or {}
status = inner.get("status") or data.get("status", "unknown")
print(f"Status: {status}")

if status == "completed":
    outputs = [o for o in (inner.get("outputs") or []) if o]
    output_url = (outputs[0] if outputs else None) or inner.get("output") or data.get("video")
    print(f"Output URL: {output_url}")

    if dest and output_url:
        print(f"Downloading to {dest}...")
        subprocess.run(["curl", "-s", "-o", str(dest), "-m", "120", output_url], timeout=130)
        print(f"Done! {dest.name} ({dest.stat().st_size:,} bytes)")
    elif output_url:
        print(f"\nTo download:\ncurl -o output.mp4 \"{output_url}\"")
elif status in ("failed", "error"):
    err = inner.get("error") or data.get("error", "unknown")
    print(f"Job failed: {err}")
else:
    print(f"Still processing. Try again in a minute.")
    print(f"Full response: {json.dumps(data, indent=2)[:500]}")
