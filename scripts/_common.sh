#!/usr/bin/env bash
#
# Shared configuration and helpers for the pr-reviewer scripts.
# Sourced by start.sh, stop.sh and restart.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_PATH="$PROJECT_DIR/app.py"

# Settings, the database and workspaces live under DATA_DIR (same default and
# override as the app itself). The pid file and log live here too.
export DATA_DIR="${DATA_DIR:-$PROJECT_DIR/data}"
PID_FILE="$DATA_DIR/pr_reviewer.pid"
LOG_FILE="$DATA_DIR/pr_reviewer.log"

# Prefer the project virtualenv, then python3.
if [[ -n "${PYTHON:-}" ]]; then
  :
elif [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON="$PROJECT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

# True when $1 is a live process.
is_running() {
  [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null
}

# PID recorded in the pid file (may be stale).
read_pid() {
  [[ -f "$PID_FILE" ]] && tr -d '[:space:]' < "$PID_FILE" || true
}

# Recorded PID, only when that process is still alive.
live_pid() {
  local pid
  pid="$(read_pid)"
  if is_running "$pid"; then
    printf '%s' "$pid"
  fi
}

# True when $1 looks like this project's pr-reviewer server, so we never stop an
# unrelated process (e.g. a shell whose command line merely mentions app.py).
# Matches both script-started servers (absolute app.py path) and a server you
# started by hand with `python3 app.py` from the project directory.
is_app_process() {
  local pid="${1:-}" exe arg
  [[ -n "$pid" && -r "/proc/$pid/cmdline" ]] || return 1

  # Must actually be a Python interpreter.
  exe="$(readlink "/proc/$pid/exe" 2>/dev/null || true)"
  [[ "$exe" == *python* || "$exe" == *pypy* ]] || return 1

  # app.py must be a distinct argument, not a substring of a longer command.
  local -a argv=()
  mapfile -d '' -t argv < "/proc/$pid/cmdline" 2>/dev/null || true

  local is_app=0 abs_path=0
  for arg in "${argv[@]}"; do
    [[ "$arg" == "$APP_PATH" ]] && abs_path=1
    if [[ "$arg" == "$APP_PATH" || "$arg" == "app.py" || "$arg" == */app.py ]]; then
      is_app=1
    fi
  done
  (( is_app )) || return 1

  # Confirm it belongs to *this* project.
  (( abs_path )) && return 0
  [[ "$(readlink "/proc/$pid/cwd" 2>/dev/null || true)" == "$PROJECT_DIR" ]]
}

# The live app PID: the recorded one if it is ours, otherwise the first process
# whose command line references app.py.
find_pid() {
  local pid candidate
  pid="$(read_pid)"
  if is_running "$pid" && is_app_process "$pid"; then
    printf '%s' "$pid"
    return 0
  fi
  while IFS= read -r candidate; do
    if is_app_process "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  done < <(pgrep -f -- "app.py" 2>/dev/null || true)
  return 0
}
