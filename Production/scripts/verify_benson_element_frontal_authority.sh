#!/usr/bin/env bash
# verify_benson_element_frontal_authority.sh — live Benson Element frontal + beat ref parity
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLING="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PORT="${MN_SERVER_PORT:-5115}"
BASE="http://localhost:${PORT}"
DROPBOX="${MN_DROPBOX_ROOT:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
PROD="${MN_PROD_ROOT:-${DROPBOX}/Production}"
CANONICAL_REL="Benson/poses/benson_pose_neutral.png"

fail() { echo "[benson-frontal-authority] FATAL: $*" >&2; exit 1; }

curl -sf "${BASE}/" >/dev/null || fail "server not up on ${BASE}"

python3 <<PY
import hashlib, json, os, sys, urllib.request
from pathlib import Path

prod = Path("${PROD}").resolve()
canonical = prod / "${CANONICAL_REL}"
if not canonical.is_file():
    raise SystemExit(f"canonical missing: {canonical}")
canon_sha = hashlib.sha256(canonical.read_bytes()).hexdigest()[:16]

reg_path = prod / "character_subjects.json"
data = json.loads(reg_path.read_text(encoding="utf-8"))
b = (data.get("characters") or {}).get("Benson") or {}
frontal_rel = str(b.get("frontal_image") or "")
frontal = prod / frontal_rel if frontal_rel else None
if not frontal or not frontal.is_file():
    raise SystemExit(f"registry frontal missing: {frontal_rel!r}")
front_sha = hashlib.sha256(frontal.read_bytes()).hexdigest()[:16]
if front_sha != canon_sha:
    raise SystemExit(f"registry frontal sha mismatch: {front_sha} != {canon_sha} ({frontal_rel})")

base = "${BASE}"
with urllib.request.urlopen(base + "/api/bg/session-state", timeout=120) as r:
    session = json.loads(r.read().decode())
beats = [x for x in (session.get("beats") or []) if (x.get("speaker") or "").strip() == "Benson"]
if not beats:
    raise SystemExit("no Benson beats in session-state")
bad = []
for beat in beats:
    ref = (beat.get("reference_image") or {}).get("abs_path") or ""
    name = Path(ref).name.lower() if ref else ""
    if "chatgpt" in name and "jul_3" in name.replace(",", "").replace(" ", "_"):
        bad.append(beat.get("beat_id"))
if bad:
    raise SystemExit(f"Benson beats still on gray ChatGPT ref: {bad}")

print(f"[benson-frontal-authority] OK registry_frontal={frontal_rel} sha={front_sha} benson_beats={len(beats)}")
PY

echo "[benson-frontal-authority] OK — ${CANONICAL_REL} is Element frontal + Benson beat refs aligned"
