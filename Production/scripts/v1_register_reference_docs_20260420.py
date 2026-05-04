#!/usr/bin/env python3
"""
Register V1 scope reference docs in prod_reference_docs.

- Register GAMEPLAY_SCOPE_v2.md as current (supersedes v1)
- Mark GAMEPLAY_SCOPE_v1.md as superseded
- Register PATH_A_BUILD_PLAN_v1.md as current
- Register SERVICES_LANDSCAPE_v1.md as current

Idempotent on file_path. Schema-introspected before writes. Uses Python urllib per CLAUDE.md §18.

Session: 2026-04-20
Preflight ID: 134
"""
import argparse, json, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = "https://directus-production-3460.up.railway.app"
EMAIL = "kimhyla11@gmail.com"
PASSWORD = "directus11$"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} on {method} {path}: {body_err}") from e


def auth():
    return _req("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})["data"]["access_token"]


def get_schema(token, collection):
    data = _req("GET", f"/fields/{collection}", token)["data"]
    return {f["field"] for f in data}


def find_by_path(token, file_path):
    q = urllib.parse.quote(file_path)
    resp = _req("GET", f"/items/prod_reference_docs?filter[file_path][_eq]={q}&limit=1", token)
    rows = resp.get("data", [])
    return rows[0] if rows else None


def upsert(token, fields_set, payload, dry=False):
    filtered = {k: v for k, v in payload.items() if k in fields_set}
    existing = find_by_path(token, payload["file_path"])
    if existing:
        if dry:
            return ("PATCH", existing["id"], filtered)
        return ("PATCH", existing["id"], _req("PATCH", f"/items/prod_reference_docs/{existing['id']}", token, body=filtered))
    if dry:
        return ("POST", None, filtered)
    resp = _req("POST", "/items/prod_reference_docs", token, body=filtered)
    return ("POST", resp["data"]["id"], resp["data"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = auth()
    fields = get_schema(token, "prod_reference_docs")
    print(f"Schema fields ({len(fields)}): {sorted(fields)}")

    # Pass 1: create/patch the three new docs and the v1 superseded row (without cross-IDs)
    entries = [
        {
            "file_path": "GAMEPLAY_SCOPE_v2.md",
            "doc_title": "Gameplay Scope v2 (V1 Shipping Scope)",
            "doc_category": "gameplay_scope",
            "status": "active",
            "is_current": True,
            "doc_version": "2",
            "chain_id": "gameplay_scope",
            "has_locked_decisions": True,
            "notes": "V1 locked scope (2026-04-20). 8 arcs, ~48 modules, 5 creatures + Oliver at M3, 6 stones, 5 fidget zones, Wishing Garden merged into Arc 3 Sweetrose Garden. Cross-refs LDs 332-346.",
            "updated_at": NOW,
        },
        {
            "file_path": "GAMEPLAY_SCOPE_v1.md",
            "doc_title": "Gameplay Scope v1 (SUPERSEDED)",
            "doc_category": "gameplay_scope",
            "status": "superseded",
            "is_current": False,
            "doc_version": "1",
            "chain_id": "gameplay_scope",
            "has_locked_decisions": False,
            "notes": "Superseded 2026-04-20 by GAMEPLAY_SCOPE_v2.md. V1 contained 9 arcs / 6 creatures / 54 modules; condensed per LDs 332-346.",
            "updated_at": NOW,
        },
        {
            "file_path": "PATH_A_BUILD_PLAN_v1.md",
            "doc_title": "Path A Build Plan v1 (Fidget Tap Primitive)",
            "doc_category": "build_plan",
            "status": "active",
            "is_current": True,
            "doc_version": "1",
            "chain_id": "path_a_build_plan",
            "has_locked_decisions": True,
            "notes": "Fidget zone technical spec: Reanimated + Skia + expo-haptics. Tap-only primitive, no fail states. Produced 2026-04-20 via 3-agent research sweep.",
            "updated_at": NOW,
        },
        {
            "file_path": "SERVICES_LANDSCAPE_v1.md",
            "doc_title": "Services Landscape v1 (Gameplay Services)",
            "doc_category": "architecture",
            "status": "active",
            "is_current": True,
            "doc_version": "1",
            "chain_id": "services_landscape",
            "has_locked_decisions": False,
            "notes": "Gameplay service inventory: Stone-Awakening, Decoration, Fidget-Zone, Spell-Book, Progression. Produced 2026-04-20 via 4-agent landscape sweep.",
            "updated_at": NOW,
        },
    ]

    results = []
    id_by_path = {}
    for e in entries:
        try:
            op, rid, payload = upsert(token, fields, e, dry=args.dry_run)
            print(f"[{op}] {e['file_path']} → id={rid}")
            results.append((op, rid, e["file_path"]))
            if rid:
                id_by_path[e["file_path"]] = rid
        except Exception as ex:
            print(f"[ERROR] {e['file_path']}: {ex}")
            results.append(("ERROR", None, e["file_path"]))

    # Pass 2: wire supersedes_id / superseded_by_id between v1 and v2
    if not args.dry_run and "GAMEPLAY_SCOPE_v1.md" in id_by_path and "GAMEPLAY_SCOPE_v2.md" in id_by_path:
        v1_id = id_by_path["GAMEPLAY_SCOPE_v1.md"]
        v2_id = id_by_path["GAMEPLAY_SCOPE_v2.md"]
        try:
            _req("PATCH", f"/items/prod_reference_docs/{v2_id}", token,
                 body={"supersedes_id": v1_id})
            _req("PATCH", f"/items/prod_reference_docs/{v1_id}", token,
                 body={"superseded_by_id": v2_id})
            print(f"[LINK] v2({v2_id}).supersedes_id={v1_id}; v1({v1_id}).superseded_by_id={v2_id}")
            results.append(("LINK", f"v1={v1_id}/v2={v2_id}", "gameplay_scope chain"))
        except Exception as ex:
            print(f"[LINK ERROR] {ex}")

    print(json.dumps({"mode": "dry" if args.dry_run else "live", "results": [list(r) for r in results]}, indent=2))


if __name__ == "__main__":
    main()
