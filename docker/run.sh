#!/usr/bin/env bash
# Host-side controller for the isolated container. One command per lifecycle step.
#
#   docker/run.sh build    build the base image
#   docker/run.sh tool <tool-dir> [tag]   build a per-tool image (deps + caches baked in)
#   docker/run.sh run      prepare inputs, run the suite through the gateway, write out/
#   docker/run.sh probe    static scan + no-network load of the untrusted extension
#   docker/run.sh shell    interactive shell inside the bench container
#   docker/run.sh agent    run one Pi agent with PROMPT.md as the first prompt
#   docker/run.sh down     stop and remove containers + anonymous volumes
#   docker/run.sh clean    down + remove the image
set -euo pipefail
ORIG_PWD="$PWD"
cd "$(dirname "$0")"
COMPOSE=(docker compose -f compose.yaml)

mkdir -p ../inputs ../out ../.no-auth

case "${1:-run}" in
  build) "${COMPOSE[@]}" build ;;
  tool)
    shift
    if [ -n "${1:-}" ] && [ "${1#/}" = "$1" ]; then set -- "$ORIG_PWD/$1" "${@:2}"; fi
    ./build_tool_image.sh "$@"
    ;;
  run)   "${COMPOSE[@]}" run --rm bench run ;;
  probe) "${COMPOSE[@]}" run --rm probe probe ;;
  shell) "${COMPOSE[@]}" run --rm bench shell ;;
  agent) "${COMPOSE[@]}" run --rm bench agent ;;
  down)  "${COMPOSE[@]}" down --volumes --remove-orphans ;;
  clean) "${COMPOSE[@]}" down --volumes --remove-orphans --rmi local ;;
  *)     echo "usage: run.sh [build|tool|run|probe|shell|agent|down|clean]" >&2; exit 2 ;;
esac
