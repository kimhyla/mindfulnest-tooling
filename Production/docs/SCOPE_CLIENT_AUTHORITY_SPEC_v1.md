# Storyboard — Client Scope Authority Spec v1

**Status:** Approved — 2026-06-21  
**Owner:** mindfulnest-tooling (`storyboard-v2/src/state/`, `storyboard-v2/src/api/client.ts`)  
**Supersedes / amends:** SCOPE_MISMATCH_AUTO_HEAL_V1, SCOPE_DEEP_LINK_DURABILITY_V1, SCOPE_RESTART_RECONCILE_V1, EVENT_DEDICATED_PORT_V1  
**Motivation:** Library drop and other mutations failed with `scope_mismatch` while UI showed Event_2 — caused by **split client scope authority** (stale `activeScope` vs URL/dedicated port/server) and **stale JS bundle** after deploy (tab on build `f438b8c`, server on `7f00af0`).

---

## 1. Problem statement

### 1.1 Symptoms

- Red banner: *"Scope mismatch… Restart the client tab"*
- Toast: *"Drop failed: scope_mismatch"* on library drag onto BG option slot
- Scope chip shows `Event_2:global:vN` but snapshot POST sends wrong `scope_event_id`
- Occurs after **long-lived tab**, **server restart/deploy**, or **hard refresh skipped**

### 1.2 Root causes (category)

| # | Root cause | Patch (banned) | Category fix |
|---|------------|----------------|--------------|
| R1 | Multiple client scope sources (URL, port, `activeScope`, pin memory) diverge | Retry drop once | Single **authoritative resolver** before every mutation |
| R2 | Dedicated-port heal requires `activeScope.event_id === server` before sync | Manual reload only | **Port+URL truth**: on `:511N`, authoritative event is `Event_N`; sync `activeScope` without `event/load` |
| R3 | Snapshot fail-closed uses caller-passed stale scope | Skip snapshot on drop | Snapshot + mutation use **same resolved scope** |
| R4 | Deploy changes server + HTML `build-sha` but tab keeps old JS | Tell operator to hard refresh | **Build-sha drift gate** blocks mutations + prompts reload |
| R5 | `ServerRehydrateWatcher` reconciles scope on down→up only, not on build-sha change | — | Drift check on visibility/poll/restart |

---

## 2. Architecture — one resolver

```
┌─────────────────────────────────────────────────────────┐
│  Authoritative event (client)                            │
│  1. URL ?event=Event_N   (wins when present)            │
│  2. Dedicated port 5110+N → Event_N                      │
│  3. activeScope.event_id (only when not on dedicated port)│
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
              syncAuthoritativeClientScope()
              (GET /api/event/current — no event/load on dedicated port)
                          │
                          ▼
              activeScope rewritten when drift detected
                          │
                          ▼
              pathappPatch / snapshot / apiGet heal
```

**Server authority unchanged:** `_assert_event_scope` + `_scope_body` (LD-456, LD-461).

### 2.1 Milestone partition gate ≠ event authority

**Do not** use `readAuthoritativeEventId()` or `resolveAuthoritativeEventIdFromParts` for milestone stitch partition decisions (`scope_milestone_id` injection, `DEDICATED_PORT_MILESTONE_LAYOUT_V1`).

Use `milestonePartitionDeepLinkAuthorized()` in `resolveMilestonePartition.ts` — requires `?milestone=` **and** (`?event=` or `activeScope`) matching the dedicated port; **never port-inference alone**.

See `Production/docs/TECH_SPEC_MILESTONE_PARTITION_RESOLVER_V1.md`.

---

## 3. Components

### 3.1 `readDedicatedPortEventId()` — `scopeAuthority.ts`

- Parse `window.location.port` → `Event_${port - 5110}` when port ≥ 5111
- Matches `Production/scripts/event_server_port.sh` `port_to_event_id`

### 3.2 `readAuthoritativeEventId()` — `resolveAuthoritativeClientScope.ts`

```typescript
readUrlEventId() ?? readDedicatedPortEventId() ?? activeScope.event_id
```

### 3.3 `syncAuthoritativeClientScope(hint, source)` — async

**When authoritative event A is known and `isDedicatedPortForEvent(A)`:**

1. `fetchEventCurrentWithRetry({ forDedicatedPort: true })`
2. If `current.event_id !== A` → return `false` (infra mismatch; do not mutate)
3. If `activeScope.event_id !== A` or generation drift → rewrite `activeScope`, `noteClientPinnedEvent(A)`, emit `mn:scope-healed`
4. Return `true`

**When not dedicated port:** delegate to existing `healServerScopeIfAuthorized` / `reconcileClientScope` paths (unchanged).

### 3.4 `healServerScopeIfAuthorized()` — rewrite

**Order:**

1. Run dedicated-port branch (§3.3) when URL/port authoritative event matches dedicated port
2. If server matches → return `true` (no `event/load` on dedicated port)
3. Else existing shared-port `event/load` heal when `clientMayPinServerTo`

### 3.5 `pathappPatch()` — mutation gate

**Before snapshot (order):**

1. **BUILD_SHA_DRIFT_V1:** if `clientBundleStale` → return `CLIENT_BUNDLE_STALE` (retry_safe, hint reload)
2. **SCOPE_CLIENT_AUTHORITY_V1:** `await syncAuthoritativeClientScope(scope, 'pathappPatch')` unless `_scopeHealRetry`
3. Use `activeScope.value` for snapshot + payload (not stale closure)

### 3.6 `buildShaDrift.ts` — deploy freshness

- **Bundled sha:** read `<meta name="build-sha">` once at module init
- **Live sha:** fetch `/` with `cache: 'no-store'`, parse meta (on poll / visibility / server up)
- **Drift:** live ≠ bundled → `clientBundleStale = true`, toast once, `setScopeReady(false, 'build-sha-drift')`
- **Recovery:** operator hard refresh (only fix for stale JS)

### 3.7 `ServerRehydrateWatcher`

On every successful probe (mount, visibility, poll, restart):

- `await checkBuildShaDrift()`
- If drift → toast + block mutations (§3.6)
- Else existing `syncScopeFromProbe` / `reconcileScopeAfterRestart`

---

## 4. Operator outcomes

| Situation | What Kim sees |
|-----------|----------------|
| Dedicated port + stale activeScope | Drop succeeds (scope synced silently) |
| Deploy while tab open | Toast: *"Storyboard updated — reload page to continue editing"*; mutations blocked until reload |
| Wrong port for URL event | Existing wrong-port banner (unchanged) |
| True cross-event attack | Server 409 (unchanged) |

---

## 5. Tests (mandatory)

| Gate | File |
|------|------|
| Resolver unit | `src/state/__tests__/resolveAuthoritativeClientScope.test.ts` |
| Build-sha drift unit | `src/state/__tests__/buildShaDrift.test.ts` |
| Milestone partition matrix | `src/state/__tests__/resolveMilestonePartition.test.ts` |
| Source markers | `Production/scripts/verify_scope_client_authority_durability.sh` |
| Milestone partition durability | `Production/scripts/verify_milestone_partition_resolver_durability.sh` |
| E2E dedicated drift | `e2e/scope_dedicated_port_authority.spec.ts` |
| Existing suite | `verify_scope_mismatch_auto_heal_durability.sh` still passes |

---

## 6. Deploy / QA

1. `npm run build` in `storyboard-v2`
2. `bash Production/scripts/deploy_option_b.sh --event Event_2`
3. Proof: live `build-sha` = git HEAD; Option B verify 7/7
4. Browser: open `:5112/?event=Event_2`, confirm scope chip, library drop on BG slot returns 200 (no scope_mismatch)

---

## 7. Out of scope

- Server-side scope guard changes (already correct)
- Stitcher mux persistence (separate spec)
- Multi-tab `event/load` ping-pong on shared port (unchanged)

---

## 8. References

- Incident: library drop scope_mismatch, build `f438b8c` tab vs `7f00af0` server
- `Production/scripts/event_server_port.sh`
- `storyboard-v2/src/api/client.ts` pathappPatch
