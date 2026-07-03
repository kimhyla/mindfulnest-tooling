#!/usr/bin/env bash
# BG_O3_EXPORT_LINEAGE_HYDRATE_V1 — client stitch hydrate pins export lineage sig.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SB="$ROOT/Production/tools/storyboard-v2/src/utils"
fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

grep -q 'BG_O3_EXPORT_LINEAGE_HYDRATE_V1' "$SB/stitchJobMediaHydrate.ts" \
  && mark 'BG_O3_EXPORT_LINEAGE_HYDRATE_V1 marker' \
  || err 'missing BG_O3_EXPORT_LINEAGE_HYDRATE_V1 marker'

grep -q 'bg_o3_export_lineage_sig' "$SB/stitchJobMediaHydrate.ts" \
  && mark 'stitchJobMediaHydrate lineage field' \
  || err 'missing bg_o3_export_lineage_sig in stitchJobMediaHydrate'

grep -q 'stitchSlotBgO3ExportLineageMatches' "$SB/stitchMuxVideoLineage.ts" \
  && mark 'stitchSlotBgO3ExportLineageMatches helper' \
  || err 'missing stitchSlotBgO3ExportLineageMatches'

grep -q 'stitchSlotBgO3ExportLineageMatches' "$SB/stitchJobMediaHydrate.ts" \
  && mark 'hydrate calls lineage matcher' \
  || err 'hydrate missing lineage matcher call'

exit "$fail"
