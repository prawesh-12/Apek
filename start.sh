#!/usr/bin/env bash
# Start script for Linux/macOS terminals.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/ui"

npm install
npx tsx src/App.tsx
