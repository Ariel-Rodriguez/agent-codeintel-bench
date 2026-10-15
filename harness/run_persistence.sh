#!/usr/bin/env bash
# Cross-session persistence experiment: two stages per arm, each in a fresh
# container, sharing a per-arm workspace so that on-disk tool state (e.g. an
# index) can survive between stages. Chat history cannot be the mechanism
# because stage 2 is a new container and a new session.
#
# Usage:
#   CORPUS=<dir|zip> TASKS=<dir> RUN_ID=run1 harness/run_persistence.sh
#
# TASKS must contain:
#   persistence/stage1.md, persistence/stage2.md, persistence/reference.json
# optionally:
#   persistence/between.patch   applied to the workspace between the stages
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORPUS="${CORPUS:?set CORPUS}"
TASKS="${TASKS:?set TASKS}"
RUN_ID="${RUN_ID:-run1}"
BASE_IMAGE="${BASE_IMAGE:-agent-codeintel-bench}"
ENHANCED_IMAGE="${BENCH_IMAGE:-agent-codeintel-bench-tool:tool}"
OUT="${OUT:-$ROOT/out}"
STATE="${STATE:-$ROOT/out/.persist-$RUN_ID}"

TMP_CORPUS=""
cleanup() { [ -n "$TMP_CORPUS" ] && rm -rf "$TMP_CORPUS"; }
trap cleanup EXIT

if [ -f "$CORPUS" ] && printf '%s' "$CORPUS" | grep -qi '\.zip$'; then
  TMP_CORPUS="$(mktemp -d)"; unzip -q "$CORPUS" -d "$TMP_CORPUS"
  only="$(find "$TMP_CORPUS" -mindepth 1 -maxdepth 1 | head -1)"
  entries=$(find "$TMP_CORPUS" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')
  if [ "$entries" = "1" ] && [ -d "$only" ]; then CORPUS="$only"; else CORPUS="$TMP_CORPUS"; fi
fi
[ -d "$CORPUS" ] || { echo "error: corpus not a directory: $CORPUS" >&2; exit 2; }
[ -n "${UPSTREAM_BASE_URL:-}" ] || { echo "error: UPSTREAM_BASE_URL is required" >&2; exit 2; }

mkdir -p "$OUT" "$ROOT/.no-auth" "$STATE"
rm -rf "${STATE:?}"/*
compose() { docker compose -f "$ROOT/docker/compose.yaml" "$@"; }

stage() { # arm, output-name, prompt-file
  local arm="$1" name="$2" prompt="$3"
  [ -f "$prompt" ] || { echo "error: missing prompt $prompt" >&2; exit 2; }
  local image="$BASE_IMAGE"; [ "$arm" = "enhanced" ] && image="$ENHANCED_IMAGE"
  local cell="$OUT/$RUN_ID/$arm/$name"
  mkdir -p "$cell"; chmod 777 "$cell" 2>/dev/null || true
  local volumes=(-v "$CORPUS:/corpus:ro" -v "$prompt:/task/prompt.md:ro"
                 -v "$cell:/out" -v "$STATE:/persist")
  echo ">>> $RUN_ID $arm $name (image=$image) $(date +%T)"
  BENCH_IMAGE="$image" compose run --rm \
    -e ARM="$arm" -e TASK="$name" -e RUN_ID="$RUN_ID" -e PERSIST_DIR=/persist \
    -e BASELINE_TOOLS -e ENHANCED_TOOLS -e CODEINTEL_EXT -e TOOL_ENTRY \
    -e PI_PROVIDER -e PI_MODEL -e PI_THINKING \
    "${volumes[@]}" bench run-one
}

for arm in baseline enhanced; do
  stage "$arm" persistence_stage1 "$TASKS/persistence/stage1.md"
done

# Inject a source change between the sessions, for both arms, so the tool's
# on-disk state becomes stale.
if [ -f "$TASKS/persistence/between.patch" ]; then
  for arm in baseline enhanced; do
    ws="$STATE/experiment-$arm"
    if [ -d "$ws/.git" ]; then
      git -C "$ws" apply "$TASKS/persistence/between.patch" \
        || { echo "error: between.patch did not apply to $arm workspace" >&2; exit 1; }
      git -C "$ws" -c user.email=bench@local -c user.name=bench commit -qam "between-stage change" || true
    fi
  done
fi

for arm in enhanced baseline; do
  stage "$arm" persistence_stage2 "$TASKS/persistence/stage2.md"
done

echo ">>> scoring (host-side)"
python3 "$ROOT/harness/evaluate.py" --results "$OUT" --references "$TASKS" --label "$RUN_ID"
