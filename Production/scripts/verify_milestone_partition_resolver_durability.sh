#!/usr/bin/env bash
# verify_milestone_partition_resolver_durability.sh — MILESTONE_PARTITION_RESOLVER_V1
#
# Ensures milestone partition gate uses dedicated resolver — never event-authority chain.
# See Production/docs/TECH_SPEC_MILESTONE_PARTITION_RESOLVER_V1.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SB="${REPO_ROOT}/Production/tools/storyboard-v2"
RESOLVER="${SB}/src/state/resolveMilestonePartition.ts"
SPEC="${REPO_ROOT}/Production/docs/TECH_SPEC_MILESTONE_PARTITION_RESOLVER_V1.md"

fail() { echo "[milestone-partition-resolver] FAIL: $1" >&2; exit 1; }

[[ -f "$RESOLVER" ]] || fail "missing resolveMilestonePartition.ts"
[[ -f "$SPEC" ]] || fail "missing TECH_SPEC_MILESTONE_PARTITION_RESOLVER_V1.md"

grep -q 'MILESTONE_PARTITION_RESOLVER_V1' "$RESOLVER" \
  || fail "MILESTONE_PARTITION_RESOLVER_V1 marker missing in resolveMilestonePartition.ts"
grep -q 'milestonePartitionDeepLinkAuthorized' "$RESOLVER" \
  || fail "milestonePartitionDeepLinkAuthorized missing in resolveMilestonePartition.ts"
grep -q 'milestonePartitionDeepLinkAuthorized' "${SB}/src/state/scope.ts" \
  || fail "scope.ts must delegate to milestonePartitionDeepLinkAuthorized"
grep -q 'isDedicatedPortMilestoneDeepLink' "${SB}/src/state/scopeReconcile.ts" \
  || fail "scopeReconcile must use isDedicatedPortMilestoneDeepLink for layout branch"

# Milestone partition paths must NOT import event-authority resolver for gate decisions.
for f in \
  "${SB}/src/state/milestoneScopeGate.ts" \
  "${SB}/src/state/scopeReconcile.ts"; do
  if grep -q 'readAuthoritativeEventId' "$f" && grep -qE 'milestone|Milestone|isDedicatedPortMilestoneDeepLink' "$f"; then
    if grep -q 'readAuthoritativeEventId.*milestone\|milestone.*readAuthoritativeEventId' "$f" 2>/dev/null; then
      fail "$f must not use readAuthoritativeEventId for milestone partition gate"
    fi
  fi
  if grep -q 'resolveAuthoritativeEventIdFromParts' "$f"; then
    fail "$f must not call resolveAuthoritativeEventIdFromParts (event authority chain)"
  fi
done

# scope.ts milestone gate must not duplicate port-inference-only logic inline.
if grep -q 'resolveAuthoritativeEventIdFromParts\|readDedicatedPortEventId' "${SB}/src/state/scope.ts"; then
  fail "scope.ts milestone gate must not use event-authority port inference helpers"
fi

echo "[milestone-partition-resolver] source guards OK"

(
  cd "$SB"
  node --experimental-strip-types --test \
    src/state/__tests__/resolveMilestonePartition.test.ts \
    src/state/__tests__/scopeInjection.test.ts
) || fail "unit tests failed"

echo "[milestone-partition-resolver] OK — source + matrix + integration tests passed"
