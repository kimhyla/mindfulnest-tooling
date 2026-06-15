#!/usr/bin/env bash
# Lorelai Kling Element name contract — registry, resolver, and live registry file parity.
set -euo pipefail

SRC_TOOLING="${MN_TOOLING_ROOT:-/Users/kimberlysmith/Projects/mindfulnest-tooling}"
DEST_DROPBOX="${MN_DROPBOX_ROOT:-/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
SERVER_PORT="${MN_SERVER_PORT:-5111}"

echo "=== [1/4] Registry JSON contract (tooling + Dropbox) ==="
python3 - <<PY
import json
import sys
from pathlib import Path

paths = [
    Path("$SRC_TOOLING") / "Production/character_subjects.json",
    Path("$DEST_DROPBOX") / "Production/character_subjects.json",
]
for p in paths:
    if not p.is_file():
        raise SystemExit(f"FATAL: missing {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    entry = (data.get("characters") or {}).get("Lorelai") or {}
    proven = entry.get("proven_o3_bind") or {}
    element_name = str(entry.get("element_name") or "").strip()
    proven_name = str(proven.get("proven_element_name") or "").strip()
    element_id = str(proven.get("element_id") or entry.get("element_id") or "").strip()
    voice_id = str(proven.get("kling_voice_id") or entry.get("kling_voice_id") or "").strip()
    print(f"  {p.parent.name}/character_subjects.json")
    print(f"    element_name={element_name!r} proven_element_name={proven_name!r}")
    print(f"    element_id={element_id} voice_id={voice_id}")
    if element_name != "Loral":
        raise SystemExit(f"FATAL: element_name must be Loral, got {element_name!r} in {p}")
    if proven_name and proven_name != "Loral":
        raise SystemExit(f"FATAL: proven_element_name must be Loral, got {proven_name!r} in {p}")
    if element_id != "313441038164306":
        raise SystemExit(f"FATAL: unexpected Lorelai element_id {element_id}")
    if voice_id != "895210468825628751":
        raise SystemExit(f"FATAL: unexpected Lorelai voice_id {voice_id}")
print("  registry contract OK")
PY

echo "=== [2/4] Resolver + alignment gate (Dropbox runtime root) ==="
python3 - <<PY
import json
import sys
from pathlib import Path

dropbox = Path("$DEST_DROPBOX")
sys.path.insert(0, str(dropbox / "Production/tools"))
sys.path.insert(0, str(dropbox / "Production"))
import beat_generator as bg
import kling_character_registry as reg
from kling_o3_prompt import validate_element_list_alignment

reg.set_prod_root(dropbox / "Production")
proven = reg.get_proven_element_list_entry("Lorelai")
assert proven, "get_proven_element_list_entry returned None"
assert proven["element_name"] == "Loral", proven
assert proven["element_id"] == "313441038164306", proven
assert proven["voice_id"] == "895210468825628751", proven

sidecar = json.loads((dropbox / "Production/beat_generator_state.json").read_text(encoding="utf-8"))
_, beat30 = bg.find_beat(sidecar, "bg_arc1_event2_pre_beat_30")
assert beat30, "beat_30 missing from sidecar"
resolved = bg.resolve_o3_element_list_entry(beat30, "Lorelai")
assert resolved["element_name"] == "Loral", resolved
assert resolved["element_id"] == "313441038164306", resolved

prompt = str(beat30.get("kling_o3_prompt") or "")
assert "@Image1 (Loral)" in prompt, "beat_30 sidecar prompt must use @Image1 (Loral)"
errs = validate_element_list_alignment("Lorelai", resolved, prompt, beat=beat30)
if errs:
    raise SystemExit(f"FATAL: beat_30 alignment errors: {errs}")

bad = dict(resolved)
bad["element_name"] = "Laurel"
errs_bad = validate_element_list_alignment("Lorelai", bad, prompt, beat=beat30)
if not any("element_name must be 'Loral'" in e for e in errs_bad):
    raise SystemExit(f"FATAL: expected element_name mismatch gate, got {errs_bad}")
print("  resolver + alignment gate OK")
PY

echo "=== [3/4] Tooling↔Dropbox parity (critical paths incl. character_subjects.json) ==="
MN_TOOLING_ROOT="$SRC_TOOLING" MN_DROPBOX_ROOT="$DEST_DROPBOX" \
  python3 "$SRC_TOOLING/Production/scripts/verify_tooling_dropbox_parity.py"

echo "=== [4/4] Server HTTP smoke ==="
code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${SERVER_PORT}/")
if [[ "$code" != "200" ]]; then
  echo "FATAL: GET / returned $code" >&2
  exit 1
fi
echo "  GET / → $code"
echo "=== verify_lorelai_element_name_durability: ALL PASSED ==="
