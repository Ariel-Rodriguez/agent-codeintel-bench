#!/usr/bin/env bash
# Host-side orchestrator for an isolated, counterbalanced A/B experiment.
#
# Each condition runs in a FRESH container that receives only:
#   - the corpus, read-only at /corpus
#   - that task's prompt, read-only at /task/prompt.md (and fixture.patch if any)
#   - an output directory
# References (reference.json) and other runs are NEVER mounted into the agent
# container; scoring happens here, on the host, after the stream is captured.
#
# Usage:
#   CORPUS=<dir|zip> TASKS=<dir> RUN_ID=run1 TRIALS=3 harness/run_isolated.sh
#
# Env:
#   TASK_LIST        tasks to run (default: "navigation impact repair")
#   BASE_IMAGE       baseline image (default: agent-codeintel-bench)
#   BENCH_IMAGE      enhanced/tool image (default: agent-codeintel-bench-tool:tool)
#   OUT              results root on the host (default: <repo>/out)
#   UPSTREAM_BASE_URL  model origin for the gateway (required by compose)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORPUS="${CORPUS:?set CORPUS to the repository directory or zip}"
TASKS="${TASKS:?set TASKS to the directory holding <task>/prompt.md}"
RUN_ID="${RUN_ID:-run1}"
TRIALS="${TRIALS:-3}"
TASK_LIST="${TASK_LIST:-navigation impact repair}"
BASE_IMAGE="${BASE_IMAGE:-agent-codeintel-bench}"
ENHANCED_IMAGE="${BENCH_IMAGE:-agent-codeintel-bench-tool:tool}"
OUT="${OUT:-$ROOT/out}"

TMP_CORPUS=""
cleanup() { [ -n "$TMP_CORPUS" ] && rm -rf "$TMP_CORPUS"; }
trap cleanup EXIT

if [ -f "$CORPUS" ] && printf '%s' "$CORPUS" | grep -qi '\.zip$'; then
  TMP_CORPUS="$(mktemp -d)"
  unzip -q "$CORPUS" -d "$TMP_CORPUS"
  entries=$(find "$TMP_CORPUS" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')
  only="$(find "$TMP_CORPUS" -mindepth 1 -maxdepth 1 | head -1)"
  if [ "$entries" = "1" ] && [ -d "$only" ]; then CORPUS="$only"; else CORPUS="$TMP_CORPUS"; fi
fi
[ -d "$CORPUS" ] || { echo "error: corpus is not a directory: $CORPUS" >&2; exit 2; }
[ -n "${UPSTREAM_BASE_URL:-}" ] || { echo "error: UPSTREAM_BASE_URL is required (model origin, no /v1)" >&2; exit 2; }

mkdir -p "$OUT" "$ROOT/.no-auth"
# The container runs as an unprivileged user; make the result bind-mount writable.
chmod 777 "$OUT" 2>/dev/null || true
compose() { docker compose -f "$ROOT/docker/compose.yaml" "$@"; }

run_one() {
  local arm="$1" task="$2" image="$3" label="$4"
  local prompt="$TASKS/$task/prompt.md"
  [ -f "$prompt" ] || { echo "error: missing prompt $prompt" >&2; exit 2; }

  echo ">>> $label $arm/$task (image=$image) $(date +%T)"
  # Mount ONLY this cell's output directory: never expose prior runs, sibling
  # cells, or scored artifacts to the agent container.
  local cell="$OUT/$label/$arm/$task"
  mkdir -p "$cell"
  chmod 777 "$cell" 2>/dev/null || true
  local volumes=(-v "$CORPUS:/corpus:ro" -v "$prompt:/task/prompt.md:ro" -v "$cell:/out")
  [ -f "$TASKS/$task/fixture.patch" ] && volumes+=(-v "$TASKS/$task/fixture.patch:/task/fixture.patch:ro")
  BENCH_IMAGE="$image" compose run --rm \
    -e ARM="$arm" -e TASK="$task" \
    -e BASELINE_TOOLS -e ENHANCED_TOOLS -e CODEINTEL_EXT -e TOOL_ENTRY \
    -e PI_PROVIDER -e PI_MODEL -e PI_THINKING \
    "${volumes[@]}" bench run-one
}

trial=0
while [ "$trial" -lt "$TRIALS" ]; do
  trial=$((trial + 1))
  label="$RUN_ID-t$trial"
  if [ $((trial % 2)) -eq 1 ]; then ORDER=(baseline enhanced); else ORDER=(enhanced baseline); fi
  for task in $TASK_LIST; do
    for arm in "${ORDER[@]}"; do
      if [ "$arm" = "baseline" ]; then run_one baseline "$task" "$BASE_IMAGE" "$label"
      else run_one enhanced "$task" "$ENHANCED_IMAGE" "$label"; fi
    done
  done
  echo ">>> scoring $label (host-side)"
  python3 "$ROOT/harness/evaluate.py" --results "$OUT" --references "$TASKS" --label "$label"
done

# Combine all trial summaries into out/<RUN_ID>/summary.jsonl
python3 - "$OUT" "$RUN_ID" "$TRIALS" <<'PY'
import json, pathlib, sys
out, run_id, trials = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
rows = []
for t in range(1, trials + 1):
    summary = out / f"{run_id}-t{t}" / "summary.jsonl"
    if summary.exists():
        for line in summary.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["trial"] = t
                rows.append(row)
dest = out / run_id
dest.mkdir(parents=True, exist_ok=True)
(dest / "summary.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
print(f"combined {len(rows)} cells into {dest}/summary.jsonl")
PY
