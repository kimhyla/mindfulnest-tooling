# Milestone Partition Resolver v1

**Status:** Approved — 2026-06-26  
**Owner:** mindfulnest-tooling (`storyboard-v2/src/state/`)  
**Amends:** `SCOPE_CLIENT_AUTHORITY_SPEC_v1.md`, `TECH_SPEC_STITCH_SCOPE_PARTITION_V1.md`  
**Marker:** `MILESTONE_PARTITION_RESOLVER_V1`

---

## 1. Problem

Two different client scope questions were conflated:

| Question | Resolver | Precedence |
|----------|----------|------------|
| Which **event** owns this tab/server box? | `readAuthoritativeEventId()` | `?event=` → port → `activeScope` |
| May we inject **`scope_milestone_id`** / adopt milestone stitch layout? | `milestonePartitionDeepLinkAuthorized()` | `?milestone=` **and** (`?event=` or `activeScope` matches dedicated port) — **never port-inference alone** |

Copying the event-authority chain into milestone gates caused false positives when:

- Tab on `:5111` (Event_1 port number) with `activeScope=Event_2` and stale `?milestone=`
- Tab on `:5112` with `activeScope=Event_3` and `?milestone=` only

Port inference (`readDedicatedPortEventId`) is correct for **event heal** on dedicated servers; it is **wrong** for **milestone partition** authorization.

---

## 2. Architecture

```
scopeAuthorityResolve.ts     ← shared pure port math (existing)
resolveMilestonePartition.ts ← milestone partition gate ONLY (new)
resolveAuthoritativeClientScope.ts ← event authority ONLY (unchanged)
scope.ts                     ← signal/DOM adapter; delegates to partition resolver
```

### 2.1 Pure API — `milestonePartitionDeepLinkAuthorized(input)`

```typescript
interface MilestonePartitionDeepLinkInput {
  milestoneId: string | null;
  urlEventId: string | null;
  activeScopeEventId: string;
  port: number;
}
```

**Returns `true` when:**

1. `milestoneId` is non-empty, **and**
2. `urlEventId` matches dedicated port for `port`, **or**
3. `activeScopeEventId` matches dedicated port for `port` and URL does not contradict (`!urlEventId || urlEventId === activeScopeEventId`)

**Never** consults `resolveAuthoritativeEventIdFromParts` or port-inferred event alone.

### 2.2 Browser adapter — `isDedicatedPortMilestoneDeepLink()` in `scope.ts`

Reads `window.location` + `activeScope` signal; calls pure resolver.

### 2.3 Forbidden in milestone partition paths

Files: `scope.ts` (gate only), `milestoneScopeGate.ts`, `scopeReconcile.ts` (milestone layout branch)

- Must **not** call `readAuthoritativeEventId()` for partition authorization
- Must **not** duplicate `resolveAuthoritativeEventIdFromParts` precedence for milestone decisions
- Must use `isDedicatedPortMilestoneDeepLink()` or `milestonePartitionDeepLinkAuthorized()`

Enforced by `verify_milestone_partition_resolver_durability.sh`.

---

## 3. Tests

| Gate | File |
|------|------|
| Matrix unit | `src/state/__tests__/resolveMilestonePartition.test.ts` |
| Integration | `src/state/__tests__/scopeInjection.test.ts` |
| Durability grep | `Production/scripts/verify_milestone_partition_resolver_durability.sh` |
| Deploy bundle | `verify_scope_client_authority_durability.sh` (includes partition tests) |

### 3.1 Matrix cases (mandatory)

| port | urlEvent | activeScope | milestone | Expected |
|------|----------|-------------|-----------|----------|
| 5111 | — | Event_2 | yes | false |
| 5112 | Event_2 | Event_2 | yes | true |
| 5112 | — | Event_2 | yes | true |
| 5112 | — | Event_3 | yes | false |
| 5112 | Event_3 | Event_2 | yes | false |

---

## 4. Deploy / QA

1. `node --experimental-strip-types --test src/state/__tests__/resolveMilestonePartition.test.ts`
2. `bash Production/scripts/verify_milestone_partition_resolver_durability.sh`
3. Full deploy + live E2E on `:5112` milestone URL
4. Browser: `data-active-project-type=milestone` on dedicated deep link; event slots on stale `:5111` + mismatched activeScope

---

## 5. References

- Incident: E2E missing `stitcher-multiphase-segment-standalone` after port-inferred milestone layout on Event_2 server
- `Production/scripts/event_server_port.sh`
