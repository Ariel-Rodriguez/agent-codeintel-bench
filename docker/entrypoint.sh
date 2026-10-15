#!/usr/bin/env bash
# Container entrypoint. Modes:
#   run    prepare from /inputs (if present), run the suite, copy results to /bench/out
#   shell  drop into a shell for interactive work
#   agent  run one Pi agent with PROMPT.md as the bootstrap prompt
set -euo pipefail
MODE="${1:-run}"
ROOT=/bench

prepare_from_inputs() {
  local repo="" tool=""
  if   [ -f /inputs/repo.zip ]; then repo=/inputs/repo.zip
  elif [ -d /inputs/repo ];     then repo=/inputs/repo
  fi
  if [ -d /inputs/tool ]; then tool=/inputs/tool
  elif [ -f /inputs/tool ]; then tool=/inputs/tool
  fi

  if [ -z "$repo" ] && [ -z "$tool" ]; then
    echo "no inputs found; using the bundled fixture with no tool (baseline vs baseline)"
  fi

  local args=(--repo "${repo:-$ROOT/fixtures/widget-service}")
  if [ -n "$tool" ]; then
    args+=(--tool "$tool" --tool-tools "${ENHANCED_TOOLS:-read,bash,edit,write}")
  fi
  "$ROOT/harness/setup_test.sh" "${args[@]}"
}

case "$MODE" in
  run)
    prepare_from_inputs
    mkdir -p "$ROOT/out"
    # shellcheck disable=SC1091
    [ -f "$ROOT/work/experiment.env" ] && . "$ROOT/work/experiment.env"
    "$ROOT/harness/run_suite.sh" "${RUN_ID:-run1}"
    "$ROOT/harness/evaluate.py" "${RUN_ID:-run1}"
    cp -R "$ROOT/results/." "$ROOT/out/" 2>/dev/null || true
    echo "results copied to /bench/out"
    ;;
  shell)
    exec bash
    ;;
  agent)
    prepare_from_inputs
    exec pi \
      --provider "${PI_PROVIDER:-deepseek}" \
      --model "${PI_MODEL:-deepseek-flash}" \
      --thinking "${PI_THINKING:-high}" \
      --tools read,bash,edit,write \
      --no-approve \
      "$(cat "$ROOT/PROMPT.md")"
    ;;
  *)
    echo "usage: entrypoint.sh [run|shell|agent]" >&2
    exit 2
    ;;
esac
