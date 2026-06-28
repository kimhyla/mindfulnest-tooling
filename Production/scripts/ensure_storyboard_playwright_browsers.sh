#!/usr/bin/env bash
# Ensure Playwright browser binaries exist for storyboard-v2 live E2E (deploy g.4).
# Category fix: g.4 failed when chromium-headless-shell was never installed for the
# pinned @playwright/test version — not because Stitch regressed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SB="${REPO_ROOT}/Production/tools/storyboard-v2"

if [[ ! -d "$SB/node_modules/@playwright/test" ]]; then
  echo "[playwright-browsers] FATAL: storyboard-v2 deps missing — run: cd Production/tools/storyboard-v2 && npm ci" >&2
  exit 1
fi

cd "$SB"
# Idempotent: downloads only when the version Playwright expects is absent.
npx playwright install chromium
echo "[playwright-browsers] OK — chromium ready for live E2E"
