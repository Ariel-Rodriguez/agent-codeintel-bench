#!/usr/bin/env bash
# Run one Pi condition on one task and capture raw evidence.
#
# Usage: harness/run_condition.sh <arm> <run_id> <task> <prompt_file>
#
# Baseline vs enhanced is defined by env, so the harness is tool-agnostic:
#   BASELINE_TOOLS   tools allowed in baseline        (default read,bash,edit,write)
#   ENHANCED_TOOLS   tools allowed in enhanced        (default read,bash,edit,write)
#   CODEINTEL_EXT    path to an extension to load in enhanced (optional)
#   PI_PROVIDER      provider (default deepseek)
#   PI_MODEL         model    (default deepseek-flash)
#   PI_THINKING      thinking level (default high)
#
# Example (pi-codeindex):
#   ENHANCED_TOOLS='read,bash,edit,write,codeindex_*' \
#   CODEINTEL_EXT="$PWD/vendor/pi-codeindex/src/pi/index.ts" \
#   harness/run_condition.sh enhanced run1 navigation benchmarks/navigation/prompt.md
set -euo pipefail

ARM="${1:?arm}"; RUN_ID="${2:?run_id}"; TASK="${3:?task_id}"; PROMPT_FILE="${4:?prompt_file}"
shift 4

[ -f "$PROMPT_FILE" ] || { echo "unavailable: prompt $PROMPT_FILE not found" >&2; exit 2; }
PROMPT_FILE="$(cd "$(dirname "$PROMPT_FILE")" && pwd)/$(basename "$PROMPT_FILE")"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PI_PROVIDER:-deepseek}"
MODEL="${PI_MODEL:-deepseek-flash}"
THINKING="${PI_THINKING:-high}"

WT="$ROOT/work/experiment-$ARM"
CFG="$ROOT/configs/$ARM/pi-agent"
SESS="$ROOT/configs/$ARM/sessions"
OUT="$ROOT/results/$RUN_ID/$ARM/$TASK"

[ -d "$WT" ] || { echo "unavailable: run harness/prepare.sh first ($WT missing)" >&2; exit 2; }
mkdir -p "$OUT" "$SESS"

cp "$PROMPT_FILE" "$OUT/prompt.txt"
shasum -a 256 "$PROMPT_FILE" | awk '{print $1}' > "$OUT/prompt.sha256"
( cd "$WT" && git rev-parse HEAD > "$OUT/head_before.txt" && git status --porcelain > "$OUT/status_before.txt" )

if [ -n "${CONDITIONS_FILE:-}" ]; then
  python3 - "$CONDITIONS_FILE" "$ARM" "$OUT/condition.json" "$ROOT/harness" <<'PY'
import json, pathlib, sys
sys.path.insert(0, sys.argv[4])
from conditions import load_manifest, resolve_condition
pathlib.Path(sys.argv[3]).write_text(json.dumps(resolve_condition(load_manifest(sys.argv[1]), sys.argv[2])))
PY
  PI_PROVIDER="$PROVIDER" PI_MODEL="$MODEL" PI_THINKING="$THINKING" \
    PI_CODING_AGENT_DIR="$CFG" PI_CODING_AGENT_SESSION_DIR="$SESS" \
    python3 "$ROOT/harness/run_cell.py" --condition "$OUT/condition.json" \
      --workspace "$WT" --out "$OUT" --prompt "$PROMPT_FILE"
  ( cd "$WT" && git status --porcelain > "$OUT/status_after.txt" && git diff HEAD > "$OUT/final.patch" )
  exit 0
fi

if [ "$ARM" = "baseline" ]; then
  TOOLS="${BASELINE_TOOLS:-read,bash,edit,write}"
  EXTRA=()
else
  TOOLS="${ENHANCED_TOOLS:-read,bash,edit,write}"
  EXTRA=()
  [ -n "${CODEINTEL_EXT:-}" ] && EXTRA=(-e "$CODEINTEL_EXT")
fi

START="$(python3 -c 'import time; print(time.time())')"
set +e
(
  cd "$WT"
  env \
    PI_CODING_AGENT_DIR="$CFG" \
    PI_CODING_AGENT_SESSION_DIR="$SESS" \
    PI_SKIP_VERSION_CHECK=1 \
    PI_TELEMETRY=0 \
    pi \
      --provider "$PROVIDER" --model "$MODEL" --thinking "$THINKING" \
      --mode json --print \
      --no-extensions --no-mcp --no-skills --no-prompt-templates --no-themes \
      --no-context-files --no-approve \
      --tools "$TOOLS" \
      ${EXTRA[@]+"${EXTRA[@]}"} \
      ${1+"$@"} \
      "$(cat "$PROMPT_FILE")" \
      > "$OUT/stdout.jsonl" 2> "$OUT/stderr.log"
)
RC=$?
set -e

END="$(python3 -c 'import time; print(time.time())')"
echo "$RC" > "$OUT/exit_code"
python3 -c "print(round($END-$START, 3))" > "$OUT/wall_seconds"
( cd "$WT" && git status --porcelain > "$OUT/status_after.txt" && git diff > "$OUT/final.patch" )

echo "arm=$ARM task=$TASK exit=$RC wall=$(cat "$OUT/wall_seconds")s -> $OUT"
