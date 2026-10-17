#!/usr/bin/env bash
#
# Start the pr-reviewer server in the background.
#
# Usage: scripts/start.sh
#
# The host and port come from Settings (data/settings.json). Override the data
# folder with DATA_DIR, and the interpreter with PYTHON.

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

existing="$(find_pid)"
if [[ -n "$existing" ]]; then
  echo "pr-reviewer is already running (pid $existing)."
  echo "Logs: $LOG_FILE"
  exit 0
fi

mkdir -p "$DATA_DIR"
cd "$PROJECT_DIR"

nohup "$PYTHON" "$APP_PATH" >>"$LOG_FILE" 2>&1 &
new_pid=$!
echo "$new_pid" > "$PID_FILE"

# Confirm it stayed up (a bad port or import error exits right away).
sleep 1
if is_running "$new_pid"; then
  echo "Started pr-reviewer (pid $new_pid)."
  echo "Logs: $LOG_FILE"
else
  echo "pr-reviewer failed to start. See $LOG_FILE" >&2
  rm -f "$PID_FILE"
  exit 1
fi
