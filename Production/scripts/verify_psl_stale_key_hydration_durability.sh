#!/usr/bin/env bash
# PSL_STALE_KEY_HYDRATION_GUARD_V1 — stale session payloads must not hydrate
# global UI signals after the active partition key changed mid-flight.
# Spec: Production/docs/TECH_SPEC_PSL_STALE_KEY_HYDRATION_GUARD_V1.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SB="$ROOT/Production/tools/storyboard-v2"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

test -f "$SB/src/state/sessionHydrationAuthority.ts" \
  && grep -q 'PSL_STALE_KEY_HYDRATION_GUARD_V1' "$SB/src/state/sessionHydrationAuthority.ts" \
  && grep -q 'sessionPayloadMayHydrate' "$SB/src/state/sessionHydrationAuthority.ts" \
  && mark 'sessionHydrationAuthority.ts authority module' \
  || err 'missing sessionHydrationAuthority.ts or marker'

for store in bgSessionStore mapSessionStore storyboardSessionStore stitchJobSessionStore; do
  grep -q 'sessionPayloadMayHydrate' "$SB/src/state/${store}.ts" \
    && grep -q 'PSL_STALE_KEY_HYDRATION_GUARD_V1' "$SB/src/state/${store}.ts" \
    && mark "${store} guarded hydration" \
    || err "${store} missing stale-key hydration guard"
done

grep -q 'syncUrlVideoParam' "$SB/src/state/videoRole.ts" \
  && grep -q 'syncUrlVideoParam' "$SB/src/components/VideoSelector.tsx" \
  && mark 'VideoSelector URL ?video= sync on server-role adoption' \
  || err 'missing syncUrlVideoParam wiring'

test -f "$ROOT/Production/docs/TECH_SPEC_PSL_STALE_KEY_HYDRATION_GUARD_V1.md" \
  && mark 'TECH_SPEC_PSL_STALE_KEY_HYDRATION_GUARD_V1.md' \
  || err 'missing TECH_SPEC_PSL_STALE_KEY_HYDRATION_GUARD_V1.md'

(
  cd "$SB"
  npx --yes vitest run src/state/__tests__/sessionHydrationStaleKey.test.ts
) && mark 'vitest sessionHydrationStaleKey.test.ts' || err 'vitest sessionHydrationStaleKey.test.ts failed'

if [[ "$fail" -ne 0 ]]; then
  echo "[psl-stale-key-hydration] FAILED"
  exit 1
fi
echo "[psl-stale-key-hydration] OK — authority + 4 store guards + behavior tests passed"
