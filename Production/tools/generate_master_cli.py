"""
CLI client for the stillgen Phase 1 endpoint.

Calls POST /api/v3/character/generate_master, writes preview to disk, prompts for
approval, then calls POST /api/v3/character/approve_master.

Usage:
    python Production/tools/generate_master_cli.py \
        --character benson \
        --pose "seated on a mushroom, looking up" \
        --costume "green scarf" \
        --hero-ref 51 \
        --style painterly \
        [--dry-run] \
        [--allow-over-cap] \
        [--server http://127.0.0.1:8787] \
        [--output-dir ./previews] \
        [--yes]          # non-interactive auto-approve
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
import uuid


def _post_json(url: str, body: dict, timeout: int = 300) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            parsed = {"error": {"code": "http_error", "message": body_bytes[:500].decode("utf-8", "replace")}}
        return exc.code, parsed


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a character master via BFL Kontext Pro.")
    p.add_argument("--character", required=True, help="Character id (e.g. 'tessa', 'benson').")
    p.add_argument("--pose", required=True, help="Pose description.")
    p.add_argument("--costume", default=None, help="Optional costume hint.")
    p.add_argument("--hero-ref", type=int, required=True, help="hero_reference_asset_id (prod_visual_assets.id).")
    p.add_argument("--style", default=None, help="Style tier hint (painterly / linework / etc).")
    p.add_argument("--dry-run", action="store_true", help="Skip BFL; return placeholder preview.")
    p.add_argument("--allow-over-cap", action="store_true", help="Bypass daily cost cap.")
    p.add_argument("--server", default="http://127.0.0.1:8787", help="Stillgen server base URL.")
    p.add_argument("--output-dir", default="./previews", help="Where to save preview PNGs.")
    p.add_argument("--yes", action="store_true", help="Non-interactive: auto-approve the preview.")
    p.add_argument("--no", action="store_true", help="Non-interactive: auto-reject the preview.")
    p.add_argument("--mutation-id", default=None, help="Override mutation_id (default: uuid4).")
    args = p.parse_args()

    if args.yes and args.no:
        print("ERROR: --yes and --no are mutually exclusive.", file=sys.stderr)
        return 2

    mid = args.mutation_id or str(uuid.uuid4())
    os.makedirs(args.output_dir, exist_ok=True)

    gen_body = {
        "character_id": args.character,
        "pose_description": args.pose,
        "costume_hint": args.costume,
        "hero_reference_asset_id": args.hero_ref,
        "style_tier": args.style,
        "dry_run": args.dry_run,
        "mutation_id": mid,
        "allow_over_cap": args.allow_over_cap,
    }
    gen_url = args.server.rstrip("/") + "/api/v3/character/generate_master"
    print(f"[cli] POST {gen_url}  mutation_id={mid}  dry_run={args.dry_run}")
    status, resp = _post_json(gen_url, gen_body, timeout=300)
    if status != 200:
        print(f"[cli] generate FAILED ({status}): {json.dumps(resp, indent=2)}", file=sys.stderr)
        return 1

    data_uri = resp.get("preview_data_uri", "")
    if data_uri.startswith("data:image/png;base64,"):
        png = base64.b64decode(data_uri.split(",", 1)[1])
        preview_path = os.path.join(args.output_dir, f"preview_{mid}.png")
        with open(preview_path, "wb") as f:
            f.write(png)
        print(f"[cli] preview written: {preview_path}  ({resp.get('file_size_bytes')}B, "
              f"{resp['dimensions']['width']}x{resp['dimensions']['height']}, "
              f"cost ${resp.get('estimated_cost_usd', 0):.4f}, "
              f"session ${resp.get('session_spend_usd', 0):.4f})")
    else:
        print(f"[cli] WARN: preview_data_uri missing; raw response: {json.dumps(resp, indent=2)[:500]}")

    if args.dry_run:
        print("[cli] dry-run — no approval step.")
        return 0

    # Approval
    if args.yes:
        decision = True
    elif args.no:
        decision = False
    else:
        ans = input("[cli] Approve this master? [y/N]: ").strip().lower()
        decision = ans in ("y", "yes")

    app_url = args.server.rstrip("/") + "/api/v3/character/approve_master"
    app_body = {"mutation_id": mid, "approved": decision}
    print(f"[cli] POST {app_url}  approved={decision}")
    status, resp = _post_json(app_url, app_body, timeout=60)
    if status != 200:
        print(f"[cli] approve FAILED ({status}): {json.dumps(resp, indent=2)}", file=sys.stderr)
        return 1
    print(f"[cli] {json.dumps(resp, indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
