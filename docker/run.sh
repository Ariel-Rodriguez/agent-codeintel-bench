#!/usr/bin/env bash
# Host-side controller for the isolated container. One command per lifecycle step.
#
#   docker/run.sh build    build the image
#   docker/run.sh run      prepare inputs, run the suite, write results to out/
#   docker/run.sh shell    interactive shell inside the container
#   docker/run.sh agent    run one Pi agent with PROMPT.md as the first prompt
#   docker/run.sh down     stop and remove containers + anonymous volumes
#   docker/run.sh clean    down + remove the image
set -euo pipefail
cd "$(dirname "$0")"
COMPOSE=(docker compose -f compose.yaml)

mkdir -p ../inputs ../out ../.no-auth

case "${1:-run}" in
  build) "${COMPOSE[@]}" build ;;
  run)   "${COMPOSE[@]}" run --rm bench run ;;
  shell) "${COMPOSE[@]}" run --rm bench shell ;;
  agent) "${COMPOSE[@]}" run --rm bench agent ;;
  down)  "${COMPOSE[@]}" down --volumes --remove-orphans ;;
  clean) "${COMPOSE[@]}" down --volumes --remove-orphans --rmi local ;;
  *)     echo "usage: run.sh [build|run|shell|agent|down|clean]" >&2; exit 2 ;;
esac
