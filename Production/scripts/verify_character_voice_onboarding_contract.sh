#!/usr/bin/env bash
# Character voice onboarding contract — Layer 1 delivery + Layer 2 tagged defaults.
# Wired into verify_o3_intro_contract.sh (deploy + pre-push) and smoke.yml CI.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
echo "[character-voice-onboarding] pytest roster contract + setup gates..."
python3 -m pytest \
  Production/tools/tests/test_character_voice_onboarding_gates.py \
  -q
echo "[character-voice-onboarding] ALL PASSED"
