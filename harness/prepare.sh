#!/usr/bin/env bash
# Prepare two identical working copies of the fixture plus isolated Pi configs.
#
# Usage: harness/prepare.sh
# Env:   FIXTURE=<dir>      fixture to copy (default fixtures/widget-service)
#        EXP_MODEL=<p/m>    provider/model (default deepseek/deepseek-flash)
#        EXP_THINKING=<lvl> thinking level (default high)
#        SKIP_VENV=1        do not create per-work-copy virtualenvs
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIXTURE="${FIXTURE:-$ROOT/fixtures/widget-service}"
MODEL="${EXP_MODEL:-deepseek/deepseek-flash}"
THINKING="${EXP_THINKING:-high}"
SRC="${PI_USER_AGENT_DIR:-$HOME/.pi/agent}"

command -v pi >/dev/null || { echo "unavailable: pi not found on PATH" >&2; exit 2; }
command -v tmux >/dev/null || true

mkdir -p "$ROOT/work" "$ROOT/configs"

for arm in baseline enhanced; do
  wt="$ROOT/work/experiment-$arm"
  rm -rf "$wt"
  cp -R "$FIXTURE" "$wt"
  ( cd "$wt" \
      && git init -q \
      && git add -A \
      && git -c user.email=bench@local -c user.name=bench commit -qm "fixture snapshot" )
  echo "prepared work copy: $wt"

  cfg="$ROOT/configs/$arm/pi-agent"
  sess="$ROOT/configs/$arm/sessions"
  mkdir -p "$cfg" "$sess"
  chmod 700 "$ROOT/configs/$arm" "$cfg"
  for f in auth.json models.json models-store.json; do
    [ -f "$SRC/$f" ] && install -m 600 "$SRC/$f" "$cfg/$f"
  done
  cat > "$cfg/settings.json" <<JSON
{
  "defaultProvider": "${MODEL%%/*}",
  "defaultModel": "${MODEL##*/}",
  "defaultThinkingLevel": "$THINKING",
  "packages": [],
  "enabledModels": ["$MODEL"]
}
JSON
  chmod 600 "$cfg/settings.json"

  if [ "${SKIP_VENV:-0}" != "1" ]; then
    python3 -m venv "$wt/.venv"
    "$wt/.venv/bin/pip" install -q -e "$wt" pytest
    echo "installed venv + pytest in $wt/.venv"
  fi
done

echo "done. edited configs (auth.json is gitignored, never commit it)."
