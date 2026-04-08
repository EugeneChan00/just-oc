#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYSTEM_OPENCODE="$HOME/.config/opencode"

ln -sfn "$PROJECT_DIR/.opencode" "$SYSTEM_OPENCODE"

echo "Symlinked $PROJECT_DIR/.opencode -> $SYSTEM_OPENCODE"
