#!/usr/bin/env python3
"""
lock_decision.py — canonical Directus writer for locked decisions.

Spec v2 §C4. Interface per Primary 3 + Counter 3 + Counter 4 synthesis.

Subcommands:
    lock       Register a new LD (or PATCH existing via decision_key upsert).
    supersede  Mark an old LD superseded by a new one (sets status + superseded_by_id).
    patch      PATCH fields on an existing LD by decision_key.
    rebuild-cache  Regenerate ~/.claude/mindfulnest-cache/locked_decisions.cache.json from Directus.
    flip-stage Flip prod_app_stages current row (stage3_locked → stage3_open, etc.) + audit.

Usage examples:
    python3 lock_decision.py lock \\
        --key FOO_BAR --name "Foo bar" --text "Decision text..." \\
        --severity critical --task-category architectural \\
        --enforcement-type lockfile \\
        --related-files "firestore.rules,firestore/__tests__/**" \\
        --keyword-synonyms "foo,bar,baz"

    python3 lock_decision.py supersede --key OLD_KEY --superseded-by-key NEW_KEY

    python3 lock_decision.py patch --key FOO_BAR --field notes --value "updated notes"

    python3 lock_decision.py rebuild-cache

    python3 lock_decision.py flip-stage stage3_open --reason "Wave A-D complete"
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
import tempfile
from datetime import datetime, timezone

try:
    import fcntl as _fcntl_mod
    _HAS_FCNTL = True
except ImportError:
    _fcntl_mod = None  # Windows — no flock; fall back to os.replace
    _HAS_FCNTL = False
from pathlib import Path

# Allow running from anywhere — sys.path the lib/ dir
_HERE = Path(__file__).resolve().parent
_LIB = _HERE.parent / "lib"
sys.path.insert(0, str(_LIB.parent))
from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError  # noqa: E402


CACHE_DIR = Path(os.path.expanduser("~/.claude/mindfulnest-cache"))
CACHE_FILE = CACHE_DIR / "locked_decisions.cache.json"
CACHE_LOCK_FILE = CACHE_DIR / "locked_decisions.cache.json.lock"
CACHE_SCHEMA_VERSION = 2
CACHE_TTL_SECONDS = 3600  # 1 hour per Counter 1 GAP 6


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_csv(s: str | None) -> list[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def _atomic_cache_write(payload: dict) -> None:
    """Atomic write: tmp → (flock on Unix) → fsync → rename/replace."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, prefix=".cache-", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
            # macOS F_FULLFSYNC for durable sync (no-op on other platforms)
            if _HAS_FCNTL:
                try:
                    F_FULLFSYNC = 51
                    _fcntl_mod.fcntl(f.fileno(), F_FULLFSYNC)
                except (OSError, AttributeError):
                    pass

        if _HAS_FCNTL:
            with open(CACHE_LOCK_FILE, "w") as lockfile:
                _fcntl_mod.flock(lockfile.fileno(), _fcntl_mod.LOCK_EX)
                try:
                    os.rename(tmp_path, CACHE_FILE)
                finally:
                    _fcntl_mod.flock(lockfile.fileno(), _fcntl_mod.LOCK_UN)
        else:
            # Windows: os.replace is atomic within the same filesystem volume
            os.replace(tmp_path, CACHE_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def cmd_lock(args, client: DirectusAdminClient) -> int:
    """Register new LD or upsert by decision_key."""
    payload = {
        "decision_key": args.key,
        "decision_name": args.name,
        "decision_text": args.text,
        "source_document": args.source_document or "lock_decision.py CLI",
        "task_category": args.task_category,
        "severity": args.severity,
        "status": "active",
        "date_locked": datetime.now(timezone.utc).date().isoformat(),
        "enforcement_type": args.enforcement_type,
        "enforcement_artifact_ref": args.enforcement_artifact_ref,
        "related_files": _split_csv(args.related_files),
        "keyword_synonyms": _split_csv(args.keyword_synonyms),
        "scope_domain": args.scope_domain,
        "supersedable": not args.not_supersedable,
        "schema_version": CACHE_SCHEMA_VERSION,
        "is_current": True,
    }
    # Idempotent upsert: check if decision_key exists
    existing = client.get_items(
        "prod_locked_decisions",
        filters={"decision_key": {"_eq": args.key}},
        fields=["id", "decision_key"],
        limit=1,
    )
    if existing:
        old_id = existing[0]["id"]
        if args.no_upsert:
            print(f"LD {args.key} already exists (id={old_id}); --no-upsert set → aborting", file=sys.stderr)
            return 2
        client.patch_item("prod_locked_decisions", old_id, payload)
        print(f"PATCHED LD-{old_id} {args.key}")
    else:
        row = client.post_item("prod_locked_decisions", payload)
        print(f"CREATED LD-{row['id']} {args.key}")

    if not args.no_rebuild_cache:
        _rebuild_cache(client)
    return 0


def cmd_supersede(args, client: DirectusAdminClient) -> int:
    """Mark old LD superseded by new one."""
    old = client.get_items("prod_locked_decisions",
                           filters={"decision_key": {"_eq": args.key}},
                           fields=["id", "decision_key", "supersedable"], limit=1)
    if not old:
        print(f"OLD key {args.key} not found", file=sys.stderr); return 2
    old = old[0]
    if old.get("supersedable") is False:
        print(f"LD-{old['id']} {args.key} is marked supersedable=false — abort", file=sys.stderr); return 3
    new = client.get_items("prod_locked_decisions",
                           filters={"decision_key": {"_eq": args.superseded_by_key}},
                           fields=["id"], limit=1)
    if not new:
        print(f"NEW key {args.superseded_by_key} not found", file=sys.stderr); return 2
    client.patch_item("prod_locked_decisions", old["id"], {
        "status": "superseded",
        "is_current": False,
        "superseded_by_id": new[0]["id"],
        "date_superseded": datetime.now(timezone.utc).date().isoformat(),
    })
    print(f"SUPERSEDED LD-{old['id']} {args.key} → LD-{new[0]['id']} {args.superseded_by_key}")
    if not args.no_rebuild_cache:
        _rebuild_cache(client)
    return 0


def cmd_patch(args, client: DirectusAdminClient) -> int:
    """PATCH a single field on an LD by decision_key."""
    row = client.get_items("prod_locked_decisions",
                           filters={"decision_key": {"_eq": args.key}},
                           fields=["id"], limit=1)
    if not row:
        print(f"key {args.key} not found", file=sys.stderr); return 2
    # Value is json if it looks like json, else string
    value: object = args.value
    try:
        value = json.loads(args.value)
    except (json.JSONDecodeError, TypeError):
        pass
    client.patch_item("prod_locked_decisions", row[0]["id"], {args.field: value})
    print(f"PATCHED LD-{row[0]['id']} {args.key}.{args.field} = {value!r}")
    if not args.no_rebuild_cache:
        _rebuild_cache(client)
    return 0


def _rebuild_cache(client: DirectusAdminClient) -> None:
    """Regenerate locked_decisions.cache.json from Directus source of truth."""
    lds = client.get_items(
        "prod_locked_decisions",
        filters={"status": {"_neq": "superseded"}},
        fields=["id", "decision_key", "decision_name", "severity", "task_category",
                "enforcement_type", "enforcement_artifact_ref", "related_files",
                "keyword_synonyms", "scope_domain", "supersedable", "is_current",
                "schema_version", "status"],
        limit=-1,
    )
    by_key: dict = {}
    by_related_file: dict[str, list[str]] = {}
    by_keyword: dict[str, list[str]] = {}

    for ld in lds:
        key = ld["decision_key"]
        by_key[key] = ld
        for rf in (ld.get("related_files") or []):
            by_related_file.setdefault(rf, []).append(key)
        for kw in (ld.get("keyword_synonyms") or []):
            by_keyword.setdefault(kw, []).append(key)

    now = _now_iso()
    ttl_expires = datetime.fromtimestamp(time.time() + CACHE_TTL_SECONDS, tz=timezone.utc).isoformat()
    payload = {
        "_meta": {
            "schema_version": CACHE_SCHEMA_VERSION,
            "built_at": now,
            "source_ld_count": len(lds),
            "directus_url": client.base_url,
            "ttl_expires_at": ttl_expires,
        },
        "by_key": by_key,
        "by_related_file": by_related_file,
        "by_keyword": by_keyword,
    }
    _atomic_cache_write(payload)
    print(f"CACHE rebuilt: {len(lds)} active LDs → {CACHE_FILE}")


def cmd_rebuild_cache(args, client: DirectusAdminClient) -> int:
    _rebuild_cache(client)
    return 0


def cmd_flip_stage(args, client: DirectusAdminClient) -> int:
    """Flip prod_app_stages current row (e.g., stage3_locked → stage3_open)."""
    current = client.get_items("prod_app_stages",
                               filters={"current": {"_eq": True}}, limit=1)
    target_name = args.target_stage
    # Check target exists; if not, create it
    target = client.get_items("prod_app_stages",
                              filters={"stage_name": {"_eq": target_name}}, limit=1)
    if not target:
        target_row = client.post_item("prod_app_stages", {
            "stage_name": target_name,
            "current": False,  # will be flipped below
            "flipped_at": None,
            "flipped_by": None,
            "reason": None,
        })
        target_id = target_row["id"]
    else:
        target_id = target[0]["id"]

    now = _now_iso()
    reason = args.reason or f"Flipped via lock_decision.py at {now}"
    flipper = args.by or os.environ.get("USER", "unknown")

    if current:
        cur = current[0]
        client.patch_item("prod_app_stages", cur["id"], {
            "current": False,
            "superseded_by_stage": target_name,
        })
    client.patch_item("prod_app_stages", target_id, {
        "current": True,
        "flipped_at": now,
        "flipped_by": flipper,
        "reason": reason,
    })
    print(f"FLIPPED stage: → {target_name} (id={target_id}) at {now} by {flipper}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lock_decision.py", description="Directus locked-decision writer")
    sub = p.add_subparsers(dest="cmd", required=True)

    # lock
    lp = sub.add_parser("lock", help="Register new LD (or upsert by decision_key)")
    lp.add_argument("--key", required=True)
    lp.add_argument("--name", required=True)
    lp.add_argument("--text", required=True)
    lp.add_argument("--severity", required=True, choices=["critical", "HIGH", "high", "MEDIUM", "medium", "LOW", "low"])
    lp.add_argument("--task-category", required=True)
    lp.add_argument("--enforcement-type", default="awareness_only",
                    choices=["structural", "db_rule", "linter", "ci_check", "test", "lockfile",
                             "wrapper", "code_invariant", "awareness_only", "human_gate"])
    lp.add_argument("--enforcement-artifact-ref", default=None)
    lp.add_argument("--related-files", default="", help="Comma-separated glob patterns")
    lp.add_argument("--keyword-synonyms", default="", help="Comma-separated keywords")
    lp.add_argument("--scope-domain", default="cross-cutting",
                    choices=["content", "production", "app-dev", "infra", "cross-cutting"])
    lp.add_argument("--not-supersedable", action="store_true", help="Mark LD as non-supersedable (security-critical)")
    lp.add_argument("--source-document", default=None)
    lp.add_argument("--no-upsert", action="store_true", help="Fail if key exists instead of PATCH")
    lp.add_argument("--no-rebuild-cache", action="store_true")
    lp.set_defaults(func=cmd_lock)

    # supersede
    sp = sub.add_parser("supersede", help="Mark LD as superseded by another LD")
    sp.add_argument("--key", required=True, help="Key of the LD being superseded (old)")
    sp.add_argument("--superseded-by-key", required=True, help="Key of the LD that supersedes (new)")
    sp.add_argument("--no-rebuild-cache", action="store_true")
    sp.set_defaults(func=cmd_supersede)

    # patch
    pp = sub.add_parser("patch", help="PATCH a single field on an existing LD by decision_key")
    pp.add_argument("--key", required=True)
    pp.add_argument("--field", required=True)
    pp.add_argument("--value", required=True)
    pp.add_argument("--no-rebuild-cache", action="store_true")
    pp.set_defaults(func=cmd_patch)

    # rebuild-cache
    rp = sub.add_parser("rebuild-cache", help="Regenerate locked_decisions.cache.json from Directus")
    rp.set_defaults(func=cmd_rebuild_cache)

    # flip-stage
    fp = sub.add_parser("flip-stage", help="Flip prod_app_stages current row")
    fp.add_argument("target_stage", help="Target stage name (e.g., stage3_open)")
    fp.add_argument("--reason", default=None)
    fp.add_argument("--by", default=None, help="Who is flipping (defaults to $USER)")
    fp.set_defaults(func=cmd_flip_stage)

    return p


def main() -> int:
    args = build_parser().parse_args()
    client = DirectusAdminClient()
    return args.func(args, client)


if __name__ == "__main__":
    sys.exit(main())
