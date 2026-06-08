#!/usr/bin/env bash
# setup_rhubarb_arm64.sh — build Rhubarb Lip Sync for Apple Silicon.
#
# Rhubarb official macOS release is x86-only. This script builds v1.14.0
# from source and installs to Production/tools/bin/rhubarb + bin/res/.
#
# Requires: git, cmake, boost (brew install cmake boost)
#
# Usage:
#   bash Production/scripts/setup_rhubarb_arm64.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLING_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BIN_DIR="$TOOLING_ROOT/Production/tools/bin"
TAG="v1.14.0"
BUILD_DIR="/tmp/rhubarb-src-build-$$"

command -v cmake >/dev/null || { echo "FATAL: cmake missing — brew install cmake" >&2; exit 1; }
command -v git >/dev/null || { echo "FATAL: git missing" >&2; exit 1; }

echo "[setup_rhubarb] cloning $TAG..."
rm -rf "$BUILD_DIR"
git clone --depth 1 --branch "$TAG" https://github.com/DanielSWolf/rhubarb-lip-sync.git "$BUILD_DIR/src"
mkdir -p "$BUILD_DIR/build"
cd "$BUILD_DIR/build"
cmake "$BUILD_DIR/src"
# Main rhubarb target builds even if Spine extras fail.
cmake --build . --target rhubarb -j"$(sysctl -n hw.ncpu 2>/dev/null || echo 4)" || true

RH="$BUILD_DIR/build/rhubarb/rhubarb"
if [[ ! -f "$RH" ]]; then
  echo "FATAL: rhubarb binary not found after build" >&2
  exit 1
fi

mkdir -p "$BIN_DIR"
cp "$RH" "$BIN_DIR/rhubarb"
chmod +x "$BIN_DIR/rhubarb"
rm -rf "$BIN_DIR/res"
cp -R "$BUILD_DIR/build/rhubarb/res" "$BIN_DIR/res"

echo "[setup_rhubarb] installed: $BIN_DIR/rhubarb"
"$BIN_DIR/rhubarb" --version
echo "[setup_rhubarb] ok — sphinx res at $BIN_DIR/res/sphinx"
