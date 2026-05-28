#!/usr/bin/env python3
"""
Register Phase B watercolor animate v2 docs + lock decision in Directus.

Idempotent. Run after deploying wc_v13 encode fix.

  python3 Production/scripts/register_watercolor_animate_v2_20260528.py
  python3 Production/scripts/register_watercolor_animate_v2_20260528.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

BASE = "https://directus-production-3460.up.railway.app"
EMAIL = "kimhyla11@gmail.com"
PASSWORD = "directus11$"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

DOCS = [
    {
        "file_path": "Production/docs/WATERCOLOR_ANIMATE_PROCEDURAL_TECH_SPEC_v2.md",
        "doc_title": "Watercolor Animate Procedural Tech Spec v2 (PIL deterministic)",
        "doc_category": "tech_spec",
        "status": "active",
        "is_current": True,
        "doc_version": "2",
        "chain_id": "watercolor_animate_procedural",
        "has_locked_decisions": True,
        "notes": (
            "2026-05-28. Canonical encode: fixed white frame + hand-only center-split rub (wc_v13). "
            "Supersedes Claude+ffmpeg LD-470 implementation. motion_description parsed server-side."
        ),
    },
    {
        "file_path": "Production/docs/LESSONS_LEARNED_20260528_PHASE_B_WATERCOLOR_ANIMATE_V1.md",
        "doc_title": "Lessons Learned — Phase B Watercolor Animate (2026-05-28)",
        "doc_category": "lessons_learned",
        "status": "active",
        "is_current": True,
        "doc_version": "1",
        "chain_id": "phase_b_watercolor_animate",
        "has_locked_decisions": True,
        "notes": "Kim-verified fix for hands_rubbing frame slice / chromakey holes. LL-WCA-1..8.",
    },
]


def _req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def auth():
    return _req("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})["data"]["access_token"]


def get_schema(token, collection):
    data = _req("GET", f"/fields/{collection}", token)["data"]
    return {f["field"] for f in data}


def upsert_ref(token, fields_set, payload, dry=False):
    filtered = {k: v for k, v in payload.items() if k in fields_set}
    q = urllib.parse.quote(payload["file_path"])
    rows = _req("GET", f"/items/prod_reference_docs?filter[file_path][_eq]={q}&limit=1", token).get("data", [])
    if rows:
        rid = rows[0]["id"]
        if dry:
            print(f"  [dry] PATCH prod_reference_docs/{rid} {payload['file_path']}")
            return rid
        _req("PATCH", f"/items/prod_reference_docs/{rid}", token, body=filtered)
        print(f"  PATCH prod_reference_docs/{rid} {payload['file_path']}")
        return rid
    if dry:
        print(f"  [dry] POST prod_reference_docs {payload['file_path']}")
        return None
    row = _req("POST", "/items/prod_reference_docs", token, body=filtered)["data"]
    print(f"  POST prod_reference_docs/{row['id']} {payload['file_path']}")
    return row["id"]


def lock_ld(dry=False):
    cmd = [
        sys.executable,
        str(_HERE / "lock_decision.py"),
        "lock",
        "--key", "WATERCOLOR_ANIMATE_PIL_RENDERER_V1",
        "--name", "Watercolor animate — deterministic PIL renderer (wc_v13)",
        "--text", (
            "Phase B POST /api/watercolor/animate MUST use deterministic PIL frame rendering "
            "(WATERCOLOR_ANIMATE_PROCEDURAL_TECH_SPEC_v2). Fixed white frame + center-split "
            "hand-pigment rub only; cream/border never move. motion_description parsed "
            "server-side for oscillation frequency (NOT Claude/ffmpeg). "
            "Compositor recipe pin: wc_v13_hand_only_split. Supersedes Claude-era LD-470 implementation."
        ),
        "--severity", "critical",
        "--task-category", "architectural",
        "--enforcement-type", "lockfile",
        "--enforcement-artifact-ref", "WATERCOLOR_OVERLAY_RECIPE_VERSION=wc_v13_hand_only_split",
        "--related-files", (
            "Production/tools/server_handlers/background.py,"
            "Production/tools/credentials_lib/ffmpeg_stitch.py,"
            "Production/tools/path_picker.html,"
            "Production/docs/WATERCOLOR_ANIMATE_PROCEDURAL_TECH_SPEC_v2.md,"
            "Production/docs/LESSONS_LEARNED_20260528_PHASE_B_WATERCOLOR_ANIMATE_V1.md"
        ),
        "--keyword-synonyms", (
            "watercolor,animate,phase_b,hands_rubbing,pil,rub,wc_v13,LD-470"
        ),
        "--source-document", "WATERCOLOR_ANIMATE_PROCEDURAL_TECH_SPEC_v2.md",
    ]
    if dry:
        cmd.append("--dry-run")
    print("Locking decision WATERCOLOR_ANIMATE_PIL_RENDERER_V1...")
    subprocess.run(cmd, check=True, cwd=str(_REPO))


def supersede_ld470(dry=False):
    cmd = [
        sys.executable,
        str(_HERE / "lock_decision.py"),
        "supersede",
        "--key", "WATERCOLOR_ANIMATE_PROCEDURAL_V1",
        "--superseded-by-key", "WATERCOLOR_ANIMATE_PIL_RENDERER_V1",
    ]
    if dry:
        print("  [dry] would supersede WATERCOLOR_ANIMATE_PROCEDURAL_V1")
        return
    print("Superseding WATERCOLOR_ANIMATE_PROCEDURAL_V1 → WATERCOLOR_ANIMATE_PIL_RENDERER_V1...")
    try:
        subprocess.run(cmd, check=True, cwd=str(_REPO))
    except subprocess.CalledProcessError as exc:
        print(f"  WARN supersede failed (LD-470 may use different key): {exc}")


def rebuild_cache(dry=False):
    if dry:
        print("  [dry] rebuild-cache")
        return
    subprocess.run(
        [sys.executable, str(_HERE / "lock_decision.py"), "rebuild-cache"],
        check=True,
        cwd=str(_REPO),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = auth()
    fields = get_schema(token, "prod_reference_docs")

    print("Registering prod_reference_docs...")
    for doc in DOCS:
        payload = dict(doc)
        payload["updated_at"] = NOW
        upsert_ref(token, fields, payload, dry=args.dry_run)

    lock_ld(dry=args.dry_run)
    supersede_ld470(dry=args.dry_run)
    rebuild_cache(dry=args.dry_run)

    print("\nDone. Positive proof checklist:")
    print("  1. grep WATERCOLOR_OVERLAY_RECIPE_VERSION → wc_v13_hand_only_split")
    print("  2. Directus prod_locked_decisions → WATERCOLOR_ANIMATE_PIL_RENDERER_V1 active")
    print("  3. path_picker motion help → 'server PIL renderer' not Claude")
    print("  4. Re-animate any watercolor after deploy; Preview with Overlay at cue")


if __name__ == "__main__":
    main()
