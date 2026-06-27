#!/usr/bin/env bash
# verify_scope_deep_link_durability.sh — SCOPE_DEEP_LINK_DURABILITY_V1
#
# Incident 2026-06-13: opening ?event=Event_2 while server pinned Event_1
# caused Beat Gen to fetch /api/v2/event/Event_2/state → 409 scope_mismatch.
# Fix: ScopeBoundary POSTs /api/event/load before tabs fetch scoped state.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SCOPE_BOUNDARY="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/ScopeBoundary.tsx"
SCOPE_RECONCILE="${REPO_ROOT}/Production/tools/storyboard-v2/src/state/scopeReconcile.ts"
SERVER_PORT="${MN_SERVER_PORT:-5111}"

fail() { echo "[scope-deep-link-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$SCOPE_BOUNDARY" ]] || fail "missing ScopeBoundary.tsx"
[[ -f "$SCOPE_RECONCILE" ]] || fail "missing scopeReconcile.ts"

grep -q 'SCOPE_DEEP_LINK_DURABILITY_V1' "$SCOPE_BOUNDARY" \
  || fail "SCOPE_DEEP_LINK_DURABILITY_V1 marker missing in ScopeBoundary.tsx"
grep -q 'loadEvent(urlEventId)' "$SCOPE_RECONCILE" \
  || fail "scopeReconcile must call loadEvent(urlEventId) on URL deep-link bootstrap"
grep -q "scope-boundary-url-bootstrap" "$SCOPE_RECONCILE" \
  || fail "scope-boundary-url-bootstrap event emission missing"
grep -q 'scope_mismatch 409' "$SCOPE_BOUNDARY" \
  || fail "scope_mismatch guard comment missing (regression doc)"

echo "[scope-deep-link-durability] source guards OK"

if curl -sf "http://localhost:${SERVER_PORT}/api/event/current" >/dev/null 2>&1; then
  python3 <<PY
import json, urllib.error, urllib.request

base = "http://localhost:${SERVER_PORT}"
port = int("${SERVER_PORT}")
dedicated_event = f"Event_{port - 5110}" if port >= 5111 else None

def post(path, body):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())

def get(path):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return r.status, json.loads(r.read().decode())

if dedicated_event:
    _, cur = get("/api/event/current")
    if cur.get("event_id") != dedicated_event:
        raise SystemExit(f"expected {dedicated_event} on :{port}, got {cur!r}")
    wrong = "Event_1" if dedicated_event != "Event_1" else "Event_99"
    try:
        get(f"/api/v2/event/{wrong}/state")
        raise SystemExit(f"expected 409 for {wrong} state on dedicated {dedicated_event} port")
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise SystemExit(f"expected 409, got HTTP {e.code}") from e
    try:
        post("/api/event/load", {"event_id": wrong})
        raise SystemExit(f"expected 409 blocking event/load to {wrong}")
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise SystemExit(f"expected 409 for event/load drift, got HTTP {e.code}") from e
        body = json.loads(e.read().decode())
        if body.get("error_code") != "DEDICATED_PORT_PIN_IMMUTABLE":
            raise SystemExit(f"expected DEDICATED_PORT_PIN_IMMUTABLE, got {body!r}")
    status, _ = get(f"/api/v2/event/{dedicated_event}/state")
    if status != 200:
        raise SystemExit(f"{dedicated_event} state must return 200 on dedicated port, got {status}")
    print(f"  live API: dedicated :{port} pin={dedicated_event}; cross-event 409; load drift blocked")
else:
    # Shared-port deep-link: explicit event/load swaps pin (ScopeBoundary on ?event=).
    st, load1 = post("/api/event/load", {"event_id": "Event_1"})
    if st != 200 or not load1.get("ok") or load1.get("event_id") != "Event_1":
        raise SystemExit(f"Event_1 load failed: HTTP {st} body={load1!r}")
    _, cur = get("/api/event/current")
    if cur.get("event_id") != "Event_1":
        raise SystemExit(f"expected Event_1 pin before test, got {cur.get('event_id')!r}")

    try:
        get("/api/v2/event/Event_2/state")
        raise SystemExit("expected 409 for Event_2 state while pinned Event_1")
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise SystemExit(f"expected 409, got HTTP {e.code}") from e
        body = json.loads(e.read().decode())
        if body.get("error_message") != "scope_mismatch":
            raise SystemExit(f"expected scope_mismatch, got {body!r}")

    post("/api/event/load", {"event_id": "Event_2"})
    _, cur2 = get("/api/event/current")
    if cur2.get("event_id") != "Event_2":
        raise SystemExit(f"event/load failed to swap to Event_2: {cur2!r}")

    status, _ = get("/api/v2/event/Event_2/state")
    if status != 200:
        raise SystemExit(f"Event_2 state must return 200 after load, got {status}")

    print("  live API: scope_mismatch before load, Event_2 state 200 after load")
PY
  echo "[scope-deep-link-durability] OK — source + live API smoke passed"
else
  echo "[scope-deep-link-durability] OK — source guards passed (server not reachable for live smoke)"
fi
