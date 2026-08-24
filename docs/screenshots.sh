#!/usr/bin/env bash
# Regenerate docs/img/*.png. Run from the repo root: docs/screenshots.sh
# Requires `freeze` (https://github.com/charmbracelet/freeze) and a local
# `patchbot` install (pip install -e .).
set -euo pipefail

cd "$(dirname "$0")/.."
PB="${PB:-patchbot}"
OUT=docs/img
mkdir -p "$OUT"
FREEZE_OPTS=(--window -W 1000 -w 100 --theme dracula)

freeze --execute "$PB scan examples/demo-npm --fail-on none" -o "$OUT/scan.png" "${FREEZE_OPTS[@]}"
freeze --execute "$PB scan examples/demo-npm --fail-on none --format json" -o "$OUT/scan-json.png" "${FREEZE_OPTS[@]}"
freeze --execute "$PB fix examples/demo-npm --dry-run" -o "$OUT/fix-dry-run.png" "${FREEZE_OPTS[@]}"
freeze --execute "$PB plugins" -o "$OUT/plugins.png" "${FREEZE_OPTS[@]}"
freeze .github/workflows/patchbot-fix-example.yml -o "$OUT/workflow.png" "${FREEZE_OPTS[@]}"

echo "Wrote screenshots to $OUT/"
echo "code-scanning.png and fix-pr.png are captured manually from GitHub: see README."
