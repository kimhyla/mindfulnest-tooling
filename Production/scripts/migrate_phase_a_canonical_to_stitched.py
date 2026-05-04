"""S4 T59 — Phase A state field rename + atomic file migration.

Per spec §3.9: reserve "canonical" exclusively for fly-in/fly-out source
clips. Phase A's stitched output gets its proper name.

Migration steps (idempotent — safe to re-run):
  1. Snapshot current state.json into .backups/state/<UTC>.json.
  2. For each phase_a_canonical_*.mp4 in event_dir, rename to
     phase_a_stitched_*.mp4 atomically (os.replace).
  3. Rewrite state.json:
       phase_a_canonical_file  -> phase_a_stitched_file (value updated)
       phase_a_canonical_mtime -> phase_a_stitched_mtime
  4. Verify glob phase_a_canonical_*.mp4 is empty.
  5. Verify state.json has phase_a_stitched_* keys + no phase_a_canonical_*.

Run from project root:
    python3 Production/scripts/migrate_phase_a_canonical_to_stitched.py
    python3 Production/scripts/migrate_phase_a_canonical_to_stitched.py --apply
"""
from __future__ import annotations
import json, os, shutil, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EVENT_DIR = PROJECT_ROOT / "Production" / "Event_1"
STATE_PATH = EVENT_DIR / "production_state.json"
SNAPSHOT_DIR = EVENT_DIR / ".backups" / "state"


def main() -> int:
    apply = "--apply" in sys.argv

    if not STATE_PATH.exists():
        print(f"[!] state.json not found at {STATE_PATH}")
        return 2

    canonical_files = sorted(EVENT_DIR.glob("phase_a_canonical_*.mp4"))
    print(f"Found {len(canonical_files)} phase_a_canonical_*.mp4 files.")
    for f in canonical_files[:5]:
        print(f"  - {f.name}")
    if len(canonical_files) > 5:
        print(f"  ... and {len(canonical_files) - 5} more")

    state = json.loads(STATE_PATH.read_text())
    has_canonical_file = "phase_a_canonical_file" in state
    has_canonical_mtime = "phase_a_canonical_mtime" in state
    has_stitched_file = "phase_a_stitched_file" in state
    print(f"\nstate.json:")
    print(f"  phase_a_canonical_file present:  {has_canonical_file} (value={state.get('phase_a_canonical_file')!r})")
    print(f"  phase_a_canonical_mtime present: {has_canonical_mtime}")
    print(f"  phase_a_stitched_file present:   {has_stitched_file}")

    if not canonical_files and not has_canonical_file and not has_canonical_mtime:
        print("\n[ok] no migration needed — already migrated or never had canonical files.")
        return 0

    if not apply:
        print("\n[dry-run] re-run with --apply to commit migration.")
        return 0

    # Step 1 — Snapshot.
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
    snap_path = SNAPSHOT_DIR / f"{ts}_pre_phase_a_migration.json"
    shutil.copy2(STATE_PATH, snap_path)
    print(f"\n[ok] snapshot: {snap_path.relative_to(EVENT_DIR)}")

    # Step 2 — Rename files atomically.
    rename_map: list[tuple[Path, Path]] = []
    for old in canonical_files:
        new_name = old.name.replace("phase_a_canonical_", "phase_a_stitched_", 1)
        new = old.parent / new_name
        if new.exists():
            print(f"  [skip] {new.name} already exists; leaving {old.name} in place")
            continue
        rename_map.append((old, new))
    for old, new in rename_map:
        os.replace(old, new)
        print(f"  renamed: {old.name} -> {new.name}")

    # Step 3 — Rewrite state.json.
    if has_canonical_file:
        old_value = state.pop("phase_a_canonical_file")
        new_value = old_value.replace("phase_a_canonical_", "phase_a_stitched_", 1) if isinstance(old_value, str) else old_value
        # Only set the new key if the corresponding renamed file exists.
        if isinstance(new_value, str) and (EVENT_DIR / new_value).exists():
            state["phase_a_stitched_file"] = new_value
            print(f"  state: phase_a_canonical_file -> phase_a_stitched_file = {new_value!r}")
        else:
            print(f"  state: phase_a_canonical_file dropped (target {new_value!r} not on disk)")
    if has_canonical_mtime:
        state["phase_a_stitched_mtime"] = state.pop("phase_a_canonical_mtime")
        print(f"  state: phase_a_canonical_mtime -> phase_a_stitched_mtime")

    tmp = STATE_PATH.with_suffix(f".json.tmp.{uuid.uuid4().hex[:8]}")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    os.replace(tmp, STATE_PATH)
    print(f"  state.json rewritten ({len(json.dumps(state))} bytes)")

    # Step 4 — Verify.
    leftover = sorted(EVENT_DIR.glob("phase_a_canonical_*.mp4"))
    if leftover:
        print(f"\n[!] WARN: {len(leftover)} phase_a_canonical_*.mp4 files still present:")
        for f in leftover[:5]:
            print(f"    {f.name}")
        return 3

    state2 = json.loads(STATE_PATH.read_text())
    leftover_keys = [k for k in state2 if k.startswith("phase_a_canonical_")]
    if leftover_keys:
        print(f"\n[!] WARN: state.json still has phase_a_canonical_* keys: {leftover_keys}")
        return 4

    print("\n[ok] migration complete:")
    print(f"     - {len(rename_map)} files renamed")
    print(f"     - state.json now uses phase_a_stitched_* keys")
    print(f"     - glob phase_a_canonical_*.mp4 empty")
    print(f"     - snapshot at {snap_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
