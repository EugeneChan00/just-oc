#!/bin/bash
set -e

TARGET_DIR="${1:-$HOME/.config/opencode}"
KILO_TARGET="${2:-$HOME/.config/kilo/opencode}"

echo "Setting up just-oc symlinks..."
echo "Target: $TARGET_DIR"
echo "Kilo Target: $KILO_TARGET"

mkdir -p "$TARGET_DIR"
mkdir -p "$KILO_TARGET"

ln -sf "$(pwd)/.opencode" "$TARGET_DIR"
ln -sf "$(pwd)/.opencode" "$KILO_TARGET"

echo "Symlinks created:"
echo "  $TARGET_DIR -> $(pwd)/.opencode"
echo "  $KILO_TARGET -> $(pwd)/.opencode"
echo "Done!"
