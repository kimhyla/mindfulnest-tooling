#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python3 _extract_pass2.py
wc -l production_server.py server_handlers/beats_legacy.py server_handlers/background.py server_handlers/cropper.py
grep "from server_handlers.beats_legacy" production_server.py | head
echo "beats_legacy shims: $(grep -c 'from server_handlers.beats_legacy' production_server.py || true)"
