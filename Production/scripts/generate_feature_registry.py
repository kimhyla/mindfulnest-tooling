#!/usr/bin/env python3
"""Walk storyboard-v2 components and emit Production/feature_registry.json.

V59 Phase 1 §2 — scans Production/tools/storyboard-v2/src/components/**/*.tsx
for data-testid="..." and testID="..." (RN/Preact compatibility), recording file,
line, and inferred tab bucket.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
COMPONENTS_GLOB = ROOT / "tools" / "storyboard-v2" / "src" / "components"
OUT_PATH = ROOT / "feature_registry.json"
SOURCE_GLOB = "Production/tools/storyboard-v2/src/components/**/*.tsx"

TESTID_RE = re.compile(
    r"""(?:data-testid|testID)\s*=\s*(?:\{\s*)?["']([^"']+)["']""",
)

TAB_FILE_MAP: dict[str, str] = {
    "StoryboardTab.tsx": "storyboard",
    "BeatGenTab.tsx": "beat_gen",
    "BgTab.tsx": "beat_gen",
    "CropperTab.tsx": "cropper",
    "CropperModal.tsx": "cropper",
    "CropperCanvas.tsx": "cropper",
    "PhaseATab.tsx": "phase_a",
    "PhaseBTab.tsx": "phase_b",
    "StitcherTab.tsx": "stitcher",
    "ProductionMapTab.tsx": "production_map",
}


def _infer_tab(file_path: Path) -> str:
    name = file_path.name
    if name in TAB_FILE_MAP:
        return TAB_FILE_MAP[name]
    if name.endswith("Tab.tsx"):
        stem = name[: -len("Tab.tsx")]
        return stem.lower()
    return "shared"


def _walk_testids() -> list[dict]:
    entries: list[dict] = []
    for tsx in sorted(COMPONENTS_GLOB.rglob("*.tsx")):
        rel = tsx.relative_to(REPO_ROOT).as_posix()
        tab = _infer_tab(tsx)
        text = tsx.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for m in TESTID_RE.finditer(line):
                entries.append(
                    {
                        "id": m.group(1),
                        "file": rel,
                        "line": line_no,
                        "tab": tab,
                    }
                )
    return entries


def main() -> int:
    if not COMPONENTS_GLOB.is_dir():
        print(f"ERROR: missing components dir {COMPONENTS_GLOB}", file=sys.stderr)
        return 2
    testids = _walk_testids()
    by_tab: dict[str, list[str]] = defaultdict(list)
    seen_per_tab: dict[str, set[str]] = defaultdict(set)
    for row in testids:
        tid = row["id"]
        tab = row["tab"]
        if tid not in seen_per_tab[tab]:
            seen_per_tab[tab].add(tid)
            by_tab[tab].append(tid)
    for tab in by_tab:
        by_tab[tab].sort()
    doc = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "Production/scripts/generate_feature_registry.py",
        "source_glob": SOURCE_GLOB,
        "testids": testids,
        "by_tab": dict(sorted(by_tab.items())),
    }
    OUT_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(
        f"FEATURE_REGISTRY_GENERATED testid_count={len(testids)} "
        f"tab_count={len(by_tab)} path={OUT_PATH.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
