#!/usr/bin/env bash
# configure_r2_lipsync_hosting.sh — provision Cloudflare R2 for voice-first lipsync staging
#
# Writes the four required R2 secrets to Doppler (preferred) and API_KEYS_MASTER.md
# (fallback), then restarts dedicated Event servers and runs live smoke.
#
# Usage (env):
#   export R2_ACCESS_KEY_ID=...
#   export R2_SECRET_ACCESS_KEY=...
#   export R2_ACCOUNT_ID=...
#   export R2_BUCKET_NAME=...
#   # optional: MN_R2_CDN_BASE_URL=https://cdn.mindfulnest.app
#   bash Production/scripts/configure_r2_lipsync_hosting.sh
#
# Usage (args):
#   bash Production/scripts/configure_r2_lipsync_hosting.sh ACCESS_KEY SECRET ACCOUNT_ID BUCKET
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
KEYS_FILE="${DROPBOX}/Production/API_KEYS_MASTER.md"
DOPPLER_PROJECT="${MN_DOPPLER_PROJECT:-mindfulnest}"
DOPPLER_CONFIG="${MN_DOPPLER_CONFIG:-dev}"

export R2_ACCESS_KEY_ID="${1:-${R2_ACCESS_KEY_ID:-}}"
export R2_SECRET_ACCESS_KEY="${2:-${R2_SECRET_ACCESS_KEY:-}}"
export R2_ACCOUNT_ID="${3:-${R2_ACCOUNT_ID:-}}"
export R2_BUCKET_NAME="${4:-${R2_BUCKET_NAME:-}}"

fail() { echo "[configure-r2-lipsync] FATAL: $1" >&2; exit 1; }

for var in R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ACCOUNT_ID R2_BUCKET_NAME; do
  if [[ -z "${!var}" ]]; then
    fail "missing ${var} — set env or pass four args (see script header)"
  fi
done

[[ -f "$KEYS_FILE" ]] || fail "missing ${KEYS_FILE}"

echo "[configure-r2-lipsync] patching API_KEYS_MASTER.md Infrastructure table..."
python3 - "$KEYS_FILE" <<'PY'
import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
content = path.read_text(encoding="utf-8")

rows = [
    ("Access Key ID", os.environ["R2_ACCESS_KEY_ID"], "Env: R2_ACCESS_KEY_ID. Object Read/Write on lipsync staging prefix."),
    ("Secret Access Key", os.environ["R2_SECRET_ACCESS_KEY"], "Env: R2_SECRET_ACCESS_KEY. Rotate via Cloudflare R2 API tokens."),
    ("Account ID", os.environ["R2_ACCOUNT_ID"], "Env: R2_ACCOUNT_ID. Cloudflare dashboard → R2 overview."),
    ("Bucket Name", os.environ["R2_BUCKET_NAME"], "Env: R2_BUCKET_NAME. Lipsync staging objects (voice-first Beat Gen)."),
]
cdn = (os.environ.get("MN_R2_CDN_BASE_URL") or "").strip()
if cdn:
    rows.append(("CDN Public Base URL", cdn.rstrip("/"), "Env: MN_R2_CDN_BASE_URL. Optional custom domain for public GET."))

out = content
for cred_type, value, notes in rows:
    row_line = f"| **Cloudflare R2** | {cred_type} | `{value}` | {notes} |"
    pattern = rf"\|\s*\*\*Cloudflare R2\*\*[^|]*\|\s*{re.escape(cred_type)}[^|]*\|\s*`[^`]*`\s*\|[^|]*\|"
    if re.search(pattern, out, flags=re.IGNORECASE):
        out = re.sub(pattern, row_line, out, count=1, flags=re.IGNORECASE)
    else:
        marker = "\n---\n\n## Anthropic API"
        if marker not in out:
            fail_msg = "could not find Anthropic section anchor for R2 row insert"
            raise SystemExit(fail_msg)
        out = out.replace(marker, f"\n{row_line}{marker}", 1)

path.write_text(out, encoding="utf-8")
print("  OK  API_KEYS_MASTER.md updated (Cloudflare R2 rows)")
PY

if command -v doppler >/dev/null 2>&1; then
  echo "[configure-r2-lipsync] setting Doppler secrets (${DOPPLER_PROJECT}/${DOPPLER_CONFIG})..."
  doppler secrets set \
    "R2_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}" \
    "R2_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}" \
    "R2_ACCOUNT_ID=${R2_ACCOUNT_ID}" \
    "R2_BUCKET_NAME=${R2_BUCKET_NAME}" \
    --project "$DOPPLER_PROJECT" --config "$DOPPLER_CONFIG"
  if [[ -n "${MN_R2_CDN_BASE_URL:-}" ]]; then
    doppler secrets set "MN_R2_CDN_BASE_URL=${MN_R2_CDN_BASE_URL}" \
      --project "$DOPPLER_PROJECT" --config "$DOPPLER_CONFIG"
  fi
  echo "  OK  Doppler secrets set"
else
  echo "[configure-r2-lipsync] WARN: doppler CLI not found — API_KEYS_MASTER.md fallback only"
fi

echo "[configure-r2-lipsync] mirroring tooling → Dropbox (lipsync modules)..."
for rel in Production/tools/lipsync_public_host.py Production/tools/credentials_lib/credentials.py; do
  src="${REPO_ROOT}/${rel}"
  dst="${DROPBOX}/${rel}"
  [[ -f "$src" ]] || fail "missing tooling file ${rel}"
  cp "$src" "$dst"
done

echo "[configure-r2-lipsync] restarting dedicated Event servers..."
bash "${SCRIPT_DIR}/start_event_server.sh" Event_1 Event_2 Event_4

echo "[configure-r2-lipsync] live smoke (strict)..."
MN_LIPSYNC_SMOKE_STRICT=1 bash "${SCRIPT_DIR}/smoke_lipsync_public_host_live.sh"

echo "[configure-r2-lipsync] ALL PASSED — voice-first Generate unblocked on this machine"
