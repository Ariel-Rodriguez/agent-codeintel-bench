#!/usr/bin/env bash
# Run a counterbalanced A/B suite sequentially.
#
# Usage: harness/run_suite.sh <run_id>
# Runs, per task: baseline then enhanced, OR enhanced then baseline, alternating
# by run parity so order is balanced across runs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:?run_id}"

# Parse run index from trailing digits for parity (run1, run2, ...).
N="${RUN_ID//[!0-9]/}"; N="${N:-0}"
if [ $((N % 2)) -eq 0 ]; then ORDER=(baseline enhanced); else ORDER=(enhanced baseline); fi
echo "run $RUN_ID order: ${ORDER[*]}"

run () { "$ROOT/harness/run_condition.sh" "$1" "$RUN_ID" "$2" "$ROOT/benchmarks/$2/prompt.md"; }

for task in navigation impact repair; do
  for arm in "${ORDER[@]}"; do run "$arm" "$task"; done
done
echo "suite $RUN_ID complete"
