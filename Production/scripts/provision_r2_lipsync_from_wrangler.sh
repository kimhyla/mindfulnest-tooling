#!/usr/bin/env bash
# provision_r2_lipsync_from_wrangler.sh — create R2 bucket + S3 credentials after dashboard enablement
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUCKET="${MN_R2_BUCKET_NAME:-mindfulnest-lipsync-staging}"
ACCOUNT_ID="${R2_ACCOUNT_ID:-7cfef657b045cb89c625f92051f5d7d7}"
WRANGLER_CONFIG="${HOME}/Library/Preferences/.wrangler/config/default.toml"
PUBLIC_BASE="${MN_R2_CDN_BASE_URL:-}"
CURL="${CURL:-/usr/bin/curl}"
PYTHON="${PYTHON:-python3}"

fail() { echo "[provision-r2] FATAL: $1" >&2; exit 1; }

command -v npx >/dev/null || fail "npx required"
[[ -f "$WRANGLER_CONFIG" ]] || fail "run wrangler login first"

oauth_token() {
  "$PYTHON" - <<'PY'
import re
from pathlib import Path
text = Path(__import__("os").environ["WRANGLER_CONFIG"]).read_text(encoding="utf-8")
m = re.search(r'oauth_token = "([^"]+)"', text)
print(m.group(1) if m else "")
PY
}

export WRANGLER_CONFIG

echo "[provision-r2] checking R2 entitlement..."
if ! npx wrangler r2 bucket list >/dev/null 2>&1; then
  fail "R2 not enabled. Open https://dash.cloudflare.com/${ACCOUNT_ID}/r2/overview"
fi

echo "[provision-r2] ensuring bucket ${BUCKET}..."
if ! npx wrangler r2 bucket list 2>/dev/null | grep -q "${BUCKET}"; then
  npx wrangler r2 bucket create "${BUCKET}" --location wnam
fi

echo "[provision-r2] enabling public r2.dev URL..."
npx wrangler r2 bucket dev-url enable "${BUCKET}" 2>/dev/null || true
PUBLIC_BASE="$(npx wrangler r2 bucket dev-url get "${BUCKET}" 2>/dev/null | awk '/https:/{print $NF; exit}' | tr -d "'\"")
if [[ -z "$PUBLIC_BASE" ]]; then
  OAUTH="$(oauth_token)"
  DOMAIN="$("$CURL" -sS -X PUT "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET}/domains/managed" \
    -H "Authorization: Bearer ${OAUTH}" -H "Content-Type: application/json" \
    -d '{"enabled":true}' | "$PYTHON" -c 'import json,sys; print((json.load(sys.stdin).get("result") or {}).get("domain") or "")')"
  [[ -n "$DOMAIN" ]] && PUBLIC_BASE="https://${DOMAIN}"
fi
[[ -n "$PUBLIC_BASE" ]] || fail "could not resolve public r2.dev base URL"
export MN_R2_CDN_BASE_URL="${PUBLIC_BASE%/}"
echo "  public base → ${MN_R2_CDN_BASE_URL}"

if [[ -z "${R2_ACCESS_KEY_ID:-}" || -z "${R2_SECRET_ACCESS_KEY:-}" ]]; then
  echo "[provision-r2] creating scoped account API token..."
  OAUTH="$(oauth_token)"
  [[ -n "$OAUTH" ]] || fail "missing wrangler oauth token"
  R2_RESOURCE="com.cloudflare.edge.r2.bucket.${ACCOUNT_ID}_default_${BUCKET}"
  TOKEN_BODY="$("$PYTHON" - <<PY
import json
print(json.dumps({
  "name": "mindfulnest-lipsync-staging",
  "policies": [{
    "effect": "allow",
    "resources": {"${R2_RESOURCE}": "*"},
    "permission_groups": [
      {"id": "2efd5506f9c8494dacb1fa10a3e7d5b6"},
      {"id": "6a018a9f2fc74eb6b293b0c548f38b39"},
    ],
  }],
}))
PY
)"
  TOKEN_JSON="$("$CURL" -sS -X POST "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/tokens" \
    -H "Authorization: Bearer ${OAUTH}" -H "Content-Type: application/json" -d "$TOKEN_BODY")"
  TOKEN_OK="$(printf '%s' "$TOKEN_JSON" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("0" if d.get("success") else "1")')"
  if [[ "$TOKEN_OK" != "0" ]]; then
    echo "[provision-r2] Create R2 API token in dashboard:" >&2
    echo "  https://dash.cloudflare.com/${ACCOUNT_ID}/r2/api_tokens" >&2
    echo "  Object Read and Write on bucket ${BUCKET}" >&2
    open "https://dash.cloudflare.com/${ACCOUNT_ID}/r2/api_tokens" 2>/dev/null || true
    fail "paste keys: R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... bash $0"
  fi
  export R2_ACCESS_KEY_ID="$(printf '%s' "$TOKEN_JSON" | "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["result"]["id"])')"
  TOKEN_VALUE="$(printf '%s' "$TOKEN_JSON" | "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["result"]["value"])')"
  export R2_SECRET_ACCESS_KEY="$(printf '%s' "$TOKEN_VALUE" | shasum -a 256 | awk '{print $1}')"
fi

export R2_ACCOUNT_ID="$ACCOUNT_ID"
export R2_BUCKET_NAME="$BUCKET"
bash "${SCRIPT_DIR}/configure_r2_lipsync_hosting.sh"
echo "[provision-r2] ALL PASSED"
