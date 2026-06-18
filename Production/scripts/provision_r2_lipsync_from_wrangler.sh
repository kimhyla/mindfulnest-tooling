#!/usr/bin/env bash
# provision_r2_lipsync_from_wrangler.sh — create R2 bucket + API token after dashboard enablement
#
# Prerequisite: R2 enabled on Cloudflare account (one-time dashboard click).
# Uses wrangler OAuth credentials from ~/.wrangler/config/default.toml.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUCKET="${MN_R2_BUCKET_NAME:-mindfulnest-lipsync-staging}"
ACCOUNT_ID="${R2_ACCOUNT_ID:-7cfef657b045cb89c625f92051f5d7d7}"
WRANGLER_CONFIG="${HOME}/Library/Preferences/.wrangler/config/default.toml"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

fail() { echo "[provision-r2] FATAL: $1" >&2; exit 1; }

command -v npx >/dev/null || fail "npx required"
[[ -f "$WRANGLER_CONFIG" ]] || fail "run wrangler login first"

echo "[provision-r2] checking R2 entitlement..."
if ! npx wrangler r2 bucket list >/dev/null 2>&1; then
  fail "R2 not enabled (code 10042). Open https://dash.cloudflare.com/${ACCOUNT_ID}/r2/overview and click Get started / Purchase R2, then re-run this script."
fi

echo "[provision-r2] ensuring bucket ${BUCKET}..."
if ! npx wrangler r2 bucket list 2>/dev/null | grep -q "${BUCKET}"; then
  npx wrangler r2 bucket create "${BUCKET}" --location wnam
fi

echo "[provision-r2] creating R2 API token (lipsync-staging)..."
TOKEN_JSON="$(python3 - <<PY
import json, re, subprocess, sys, urllib.request
from pathlib import Path

config = Path("${WRANGLER_CONFIG}").read_text()
m = re.search(r'oauth_token = "([^"]+)"', config)
if not m:
    raise SystemExit("missing oauth_token in wrangler config")
oauth = m.group(1)
account = "${ACCOUNT_ID}"
body = json.dumps({
    "name": "mindfulnest-lipsync-staging",
    "permission": {"prefixes": ["lipsync-staging/"], "buckets": ["${BUCKET}"]},
}).encode()
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/temp-access-credentials",
    data=body,
    method="POST",
    headers={"Authorization": f"Bearer {oauth}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
except urllib.error.HTTPError as e:
    print(e.read().decode(), file=sys.stderr)
    raise
if not payload.get("success"):
    raise SystemExit(json.dumps(payload))
result = payload.get("result") or {}
print(json.dumps({
    "access_key_id": result.get("accessKeyId") or result.get("access_key_id"),
    "secret_access_key": result.get("secretAccessKey") or result.get("secret_access_key"),
}))
PY
)"

ACCESS_KEY="$(printf '%s' "$TOKEN_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("access_key_id") or "")')"
SECRET_KEY="$(printf '%s' "$TOKEN_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("secret_access_key") or "")')"
if [[ -z "$ACCESS_KEY" || -z "$SECRET_KEY" ]]; then
  fail "R2 token creation returned empty keys — create token manually in dashboard (R2 → Manage R2 API Tokens)"
fi

export R2_ACCESS_KEY_ID="$ACCESS_KEY"
export R2_SECRET_ACCESS_KEY="$SECRET_KEY"
export R2_ACCOUNT_ID="$ACCOUNT_ID"
export R2_BUCKET_NAME="$BUCKET"

bash "${SCRIPT_DIR}/configure_r2_lipsync_hosting.sh"

echo "[provision-r2] ALL PASSED"
