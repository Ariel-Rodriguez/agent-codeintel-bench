#!/usr/bin/env bash
# Container entrypoint. Modes:
#   run    prepare from /inputs (if present), run the suite, copy results to /bench/out
#   probe  static scan + no-network load of an untrusted extension
#   shell  drop into a shell for interactive work
#   agent  run one Pi agent with PROMPT.md as the first prompt
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

probe() {
  local target="${PROBE_TARGET:-/inputs/tool}"
  [ -e "$target" ] || target="$ROOT/examples/untrusted-extension"
  echo "== static scan: $target =="
  python3 "$ROOT/harness/scan_extension.py" "$target" || true
  echo
  echo "== dynamic load (network=none, read-only root, caps dropped) =="
  local entry
  entry="$(find "$target" -type f \( -name '*.js' -o -name '*.mjs' -o -name '*.cjs' \) | head -1 || true)"
  if [ -z "$entry" ]; then
    echo "no JS entry found under $target"
    return 0
  fi
  echo "entry: $entry"
  if node --experimental-permission --allow-fs-read="$target" -e 'process.exit(0)' >/dev/null 2>&1; then
    PROBE_RUN=1 node --experimental-permission --allow-fs-read="$target" "$entry" 2>&1 | head -60 || true
  else
    PROBE_RUN=1 node "$entry" 2>&1 | head -60 || true
  fi
  echo "(access-denied and DNS-resolution failures above are the expected, contained outcome)"
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
  probe)
    probe
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
    echo "usage: entrypoint.sh [run|probe|shell|agent]" >&2
    exit 2
    ;;
esac
