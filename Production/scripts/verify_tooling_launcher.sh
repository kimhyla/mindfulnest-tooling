#!/usr/bin/env bash
# Verify production_server processes run from mindfulnest-tooling (not Dropbox code).
# Exit 0 when every listener on 5111–5119 uses the tooling server path.
set -euo pipefail

TOOLING="${MN_TOOLING_ROOT:-${HOME}/Projects/mindfulnest-tooling}"
EXPECTED="${TOOLING}/Production/tools/production_server.py"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"

fail=0
echo "=== Launcher verify (LD-505 tooling code root) ==="
echo "Expected server: ${EXPECTED}"
echo ""

if [[ ! -f "$EXPECTED" ]]; then
  echo "FAIL: tooling server missing at ${EXPECTED}" >&2
  exit 1
fi

for port in $(seq 5111 5119); do
  listener_pids=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' | xargs echo 2>/dev/null || true)
  listener_count=0
  if [[ -n "${listener_pids// /}" ]]; then
    read -r -a _listener_arr <<< "$listener_pids"
    listener_count="${#_listener_arr[@]}"
  fi
  if (( listener_count > 1 )); then
    echo "FAIL port ${port}: ${listener_count} duplicate listeners (${listener_pids})"
    fail=1
    continue
  fi
  pid=$(echo "$listener_pids" | awk '{print $1}')
  [[ -z "$pid" ]] && pid=$(lsof -ti:"$port" 2>/dev/null || true)
  [[ -z "$pid" ]] && continue
  # macOS ps: show full command
  cmd=$(ps -p "$pid" -o args= 2>/dev/null || true)
  if [[ -z "$cmd" ]]; then
    echo "WARN port ${port}: pid ${pid} but no ps args"
    continue
  fi
  if [[ "$cmd" == *"${EXPECTED}"* ]]; then
    if [[ "$cmd" == *"${DROPBOX}/Production/tools/production_server.py"* ]]; then
      echo "FAIL port ${port}: tooling path present but Dropbox path also in argv"
      fail=1
    elif [[ "$cmd" != *"--event-dir"*"${DROPBOX}"* ]]; then
      echo "FAIL port ${port}: event-dir not under Dropbox data root"
      echo "       ${cmd}"
      fail=1
    else
      code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:${port}/api/health" 2>/dev/null || echo "000")
      echo "OK   port ${port}  HTTP ${code}  tooling server  event-dir→Dropbox"
    fi
  elif [[ "$cmd" == *"production_server.py"* ]]; then
    echo "FAIL port ${port}: still running non-tooling server"
    echo "       ${cmd}"
    fail=1
  fi
done

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "Launcher verify FAILED — reload launchd plists from Production/scripts/launchd/" >&2
  exit 1
fi

echo ""
echo "Launcher verify OK"
