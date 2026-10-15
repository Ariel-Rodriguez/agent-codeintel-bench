#!/usr/bin/env bash
# Container entrypoint.
#
# Modes:
#   run-one   run ONE arm on ONE task in a fresh container (references are never
#             mounted; the host scores the raw stream)
#   probe     static scan + no-network load of the exact tool entry
#   shell     interactive shell
#   agent     one Pi agent with PROMPT.md as the bootstrap prompt
set -euo pipefail
MODE="${1:-run-one}"
ROOT=/bench

die() { echo "error: $*" >&2; exit 1; }

hydrate_caches() {
  # Build-time model cache must be present and copy cleanly; a partial copy would
  # silently change the treatment, so a failure is fatal.
  if [ -n "${TOOL_CACHE:-}" ] && [ -d "${TOOL_CACHE}/hf" ]; then
    mkdir -p "${HF_HOME:-$HOME/.cache/huggingface}"
    cp -R "${TOOL_CACHE}/hf/." "${HF_HOME:-$HOME/.cache/huggingface}/" \
      || die "cache hydration from ${TOOL_CACHE}/hf failed"
  fi
}

setup_agent_dir() {
  local cfg=/home/runner/.pi-agent
  rm -rf "$cfg"; mkdir -p "$cfg/sessions"
  for f in auth.json models.json models-store.json; do
    [ -f "/auth/$f" ] && cp "/auth/$f" "$cfg/$f"
  done
  if [ -n "${MODEL_GATEWAY:-}" ] && [ -f "$cfg/models.json" ]; then
    python3 - "$cfg/models.json" "${PI_PROVIDER:?}" "$MODEL_GATEWAY" <<'PY' || die "gateway rewrite failed"
import json, sys
path, provider, gateway = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.load(open(path))
providers = data.get("providers", {})
if provider not in providers:
    raise SystemExit(f"provider {provider!r} not found in models.json; refusing to run")
providers[provider]["baseUrl"] = gateway
json.dump(data, open(path, "w"), indent=2)
PY
  fi
  echo "$cfg"
}

run_one() {
  local arm="${ARM:?ARM required}" task="${TASK:?TASK required}"
  local prompt="${PROMPT_PATH:-/task/prompt.md}"
  [ -f "$prompt" ] || die "prompt not found at $prompt"

  [ -d /corpus ] || die "/corpus not mounted"

  local scratch
  if [ -n "${PERSIST_DIR:-}" ]; then
    # Cross-session run: the workspace (and any tool state on disk) survives
    # between stages. Seed once, then reuse.
    scratch="${PERSIST_DIR}/experiment-$arm"
    if [ ! -d "$scratch" ]; then
      mkdir -p "$scratch"
      cp -R /corpus/. "$scratch/"
    fi
  else
    scratch="/bench/work/experiment-$arm"
    rm -rf "$scratch"; mkdir -p "$scratch"
    cp -R /corpus/. "$scratch/"
  fi

  # A tool may require a fixture (e.g. an introduced bug) before the task.
  if [ -f /task/fixture.patch ]; then
    git -C "$scratch" init -q 2>/dev/null || true
    git -C "$scratch" apply /task/fixture.patch || die "fixture.patch did not apply"
  fi
  if [ ! -d "$scratch/.git" ]; then
    ( cd "$scratch" \
        && git init -q \
        && git add -A \
        && git -c user.email=bench@local -c user.name=bench commit -qm "condition snapshot" )
  fi

  local cfg; cfg="$(setup_agent_dir)"
  local out="/out/$RUN_ID/$arm/$task"
  mkdir -p "$out"
  cp "$prompt" "$out/prompt.txt"
  shasum -a 256 "$prompt" | awk '{print $1}' > "$out/prompt.sha256"
  ( cd "$scratch" && git rev-parse HEAD > "$out/head_before.txt" \
                 && git status --porcelain > "$out/status_before.txt" )

  local tools extra=()
  if [ "$arm" = "baseline" ]; then
    tools="${BASELINE_TOOLS:-read,bash,edit,write}"
  else
    tools="${ENHANCED_TOOLS:-read,bash,edit,write}"
    if [ -n "${CODEINTEL_EXT:-}" ]; then
      extra=(-e "$CODEINTEL_EXT")
    elif [ -n "${TOOL_ENTRY:-}" ] && [ -f "$TOOL_ENTRY" ]; then
      extra=(-e "$TOOL_ENTRY")
    else
      die "enhanced arm has no tool entry (TOOL_ENTRY/CODEINTEL_EXT); refusing to run a fake enhanced arm"
    fi
  fi

  local start end rc
  start="$(python3 -c 'import time; print(time.time())')"
  set +e
  ( cd "$scratch" && env \
      PI_CODING_AGENT_DIR="$cfg" \
      PI_CODING_AGENT_SESSION_DIR="$cfg/sessions" \
      PI_SKIP_VERSION_CHECK=1 PI_TELEMETRY=0 \
      pi \
        --provider "$PI_PROVIDER" --model "$PI_MODEL" --thinking "${PI_THINKING:-medium}" \
        --mode json --print \
        --no-extensions --no-mcp --no-skills --no-prompt-templates --no-themes \
        --no-context-files --no-approve \
        --tools "$tools" ${extra[@]+"${extra[@]}"} \
        "$(cat "$prompt")" \
        > "$out/stdout.jsonl" 2> "$out/stderr.log" )
  rc=$?
  set -e
  end="$(python3 -c 'import time; print(time.time())')"
  echo "$rc" > "$out/exit_code"
  python3 -c "print(round($end-$start, 3))" > "$out/wall_seconds"
  ( cd "$scratch" \
      && git status --porcelain > "$out/status_after.txt" \
      && git diff > "$out/final.patch" \
      && git ls-files --others --exclude-standard > "$out/untracked_files.txt" )

  # Fail closed: no stream or a non-zero exit is a failure, not a result.
  [ -s "$out/stdout.jsonl" ] || die "empty event stream for $arm/$task (rc=$rc)"
  [ "$rc" = "0" ] || { echo "arm=$arm task=$task FAILED rc=$rc" >&2; exit "$rc"; }
  echo "ok arm=$arm task=$task wall=$(cat "$out/wall_seconds")s -> $out"
}

probe() {
  local target="${PROBE_TARGET:-}"
  [ -n "$target" ] || { [ -e /inputs/tool ] && target=/inputs/tool; }
  [ -n "$target" ] || { [ -n "${TOOL_PATH:-}" ] && [ -e "$TOOL_PATH" ] && target="$TOOL_PATH"; }
  [ -n "$target" ] || target="$ROOT/examples/untrusted-extension"

  echo "== static scan: $target =="
  python3 "$ROOT/harness/scan_extension.py" "$target"

  echo
  echo "== dynamic load (network=none, read-only root, caps dropped) =="
  local entry="${TOOL_ENTRY:-}"
  if [ -z "$entry" ] || [ ! -f "$entry" ]; then
    entry="$(find "$target" -maxdepth 3 -type f \( -name 'index.js' -o -name 'index.mjs' -o -name 'index.cjs' \) -not -path '*/node_modules/*' | head -1 || true)"
  fi
  [ -n "$entry" ] || die "no declared or discoverable entry under $target"
  echo "entry: $entry"

  local rc=0 loader="$ROOT/harness/probe_load.mjs"
  if node --experimental-permission --allow-fs-read="$target" -e 'process.exit(0)' >/dev/null 2>&1; then
    node --experimental-strip-types --experimental-permission \
      --allow-fs-read="$target" --allow-fs-read="$loader" \
      "$loader" "$entry" 2>&1 || rc=$?
  else
    node --experimental-strip-types "$loader" "$entry" 2>&1 || rc=$?
  fi
  if [ "$rc" != "0" ]; then
    die "probe: the entry failed to load or register under a no-network, read-only container (rc=$rc)"
  fi
  echo "(load verified; container had no network and a read-only root)"
  return 0
}

case "$MODE" in
  run-one)
    hydrate_caches
    run_one
    ;;
  probe)
    probe
    ;;
  shell)
    exec bash
    ;;
  agent)
    hydrate_caches
    exec pi \
      --provider "${PI_PROVIDER:-deepseek}" \
      --model "${PI_MODEL:-deepseek-flash}" \
      --thinking "${PI_THINKING:-medium}" \
      --tools read,bash,edit,write \
      --no-approve \
      "$(cat "$ROOT/PROMPT.md")"
    ;;
  *)
    die "usage: entrypoint.sh [run-one|probe|shell|agent]"
    ;;
esac
