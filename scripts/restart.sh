#!/usr/bin/env bash
#
# Restart the pr-reviewer server (stop, then start).
#
# Usage: scripts/restart.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/stop.sh"
"$SCRIPT_DIR/start.sh"
