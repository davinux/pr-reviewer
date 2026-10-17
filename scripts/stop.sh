#!/usr/bin/env bash
#
# Stop the pr-reviewer server started with scripts/start.sh.
#
# Usage: scripts/stop.sh

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

pid="$(find_pid)"
if [[ -z "$pid" ]]; then
  echo "pr-reviewer is not running."
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping pr-reviewer (pid $pid)..."
kill "$pid" 2>/dev/null || true

# Wait up to ~10s for a clean shutdown.
for _ in $(seq 1 20); do
  is_running "$pid" || break
  sleep 0.5
done

if is_running "$pid"; then
  echo "Did not stop cleanly; sending SIGKILL." >&2
  kill -9 "$pid" 2>/dev/null || true
fi

rm -f "$PID_FILE"
echo "Stopped."
