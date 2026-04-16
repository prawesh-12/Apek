#!/usr/bin/env bash
# Start script for Linux/macOS terminals.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/error-logs"
mkdir -p "$LOG_DIR"

RUN_TS="$(date '+%Y%m%d_%H%M%S')"
RUN_ID="${RUN_TS}_$RANDOM"
RUN_LOG_FILE="$LOG_DIR/run_${RUN_ID}.txt"

export APEK_RUN_LOG_FILE="$RUN_LOG_FILE"

{
	echo "Apek Run Debug Log"
	echo "run_id=$RUN_ID"
	echo "started_at_local=$(date '+%Y-%m-%d %H:%M:%S %Z')"
	echo "started_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
	echo "project_root=$SCRIPT_DIR"
	echo "ui_dir=$SCRIPT_DIR/ui"
	echo
} > "$RUN_LOG_FILE"

echo "[debug] logging enabled: $RUN_LOG_FILE"

cd "$SCRIPT_DIR/ui"

npm install
npx tsx src/App.tsx
