#!/usr/bin/env bash
# Run SlingologyEIS locally from this checkout.
#
#   scripts/run_local.sh                  # local-server mode: Python engine + live UI (hot reload)
#   scripts/run_local.sh browser          # in-browser (Pyodide) mode, as published, on :8000
#   scripts/run_local.sh --sandbox        # server mode on a throwaway data root — your real
#                                         # workspaces are untouched (browser mode keeps its data
#                                         # in the browser's own storage, so it doesn't apply there)
#
# Server mode never touches web/dist, so a browser site served from it keeps working.
# Ctrl-C stops everything this script started.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="server"
SANDBOX=0
for arg in "$@"; do
  case "$arg" in
    server|browser) MODE="$arg" ;;
    --sandbox) SANDBOX=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg (try --help)" >&2; exit 2 ;;
  esac
done

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || { echo "No .venv found. Create it and run: .venv/bin/pip install -e \".[dev]\"" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required (Node.js 22)." >&2; exit 1; }
[ -d "$ROOT/web/node_modules" ] || (cd "$ROOT/web" && npm ci)

port_busy() { lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

if [ "$MODE" = "browser" ]; then
  port_busy 8000 && { echo "Port 8000 is already in use (an old site server?). Stop it first." >&2; exit 1; }
  echo "Building the in-browser site into web/dist …"
  (cd "$ROOT/web" && npm run build:browser)
  echo
  echo "Open http://127.0.0.1:8000/   (Ctrl-C to stop)"
  cd "$ROOT/web" && exec "$PY" -m http.server -d dist --bind 127.0.0.1 8000
fi

# ── Local-server mode ────────────────────────────────────────────────────────
port_busy 8420 && { echo "Port 8420 is already in use: an engine server is running. Stop it first" \
                         "(a server started before a code change serves the old code)." >&2; exit 1; }
if [ "$SANDBOX" = 1 ]; then
  export SLINGOLOGY_EIS_HOME="$(mktemp -d -t eis-sandbox)"
  echo "Sandbox data root: $SLINGOLOGY_EIS_HOME (your real workspaces are untouched)"
fi

"$ROOT/.venv/bin/slingology-eis" serve --port 8420 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 30); do port_busy 8420 && break; sleep 0.5; done
port_busy 8420 || { echo "The engine server didn't start." >&2; exit 1; }

echo "Engine on http://127.0.0.1:8420 — opening the UI (Ctrl-C to stop both)"
cd "$ROOT/web" && npx vite --port 5173 --open
