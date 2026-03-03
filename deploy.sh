#!/bin/bash
# deploy.sh — idempotent deployment script for karaoke
# Creates/updates a self-contained deploy dir; the git repo is never modified.
#
# Usage:
#   ./deploy.sh                              # deploys to ~/deployments/karaoke
#   DEPLOY_DIR=/srv/karaoke ./deploy.sh      # custom deploy dir
#   DEPLOY_DIR=... FRONTEND_MODE=prod ./deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="${DEPLOY_DIR:-$HOME/deployments/karaoke}"
AI_DEV_PATH="${AI_DEV_PATH:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-3002}"
FRONTEND_MODE="${FRONTEND_MODE:-dev}"

echo "========================================"
echo "Karaoke — Deploy"
echo "========================================"
echo "  Source:      $SCRIPT_DIR"
echo "  Deploy dir:  $DEPLOY_DIR"
echo "  AI dev path: $AI_DEV_PATH"
echo "  Backend:     port $BACKEND_PORT"
echo "  Frontend:    port $FRONTEND_PORT (mode: $FRONTEND_MODE)"
echo ""

# ── Directory structure ──────────────────────────────────────────────────────
echo "Creating directories..."
mkdir -p "$DEPLOY_DIR"/{data,logs}

# ── Python venv ──────────────────────────────────────────────────────────────
echo "Setting up Python venv..."
if [ ! -d "$DEPLOY_DIR/.venv" ]; then
  python3 -m venv "$DEPLOY_DIR/.venv"
fi
"$DEPLOY_DIR/.venv/bin/pip" install --quiet --upgrade pip
# cd into server/ so relative -e paths in requirements.txt resolve correctly
(cd "$SCRIPT_DIR/server" && "$DEPLOY_DIR/.venv/bin/pip" install -r requirements.txt)

# ── One-time data migration from git repo location ──────────────────────────
OLD_DATA="$SCRIPT_DIR/data"
if [ -d "$OLD_DATA" ] && [ -n "$(ls -A "$OLD_DATA" 2>/dev/null)" ]; then
  if [ -z "$(ls -A "$DEPLOY_DIR/data" 2>/dev/null)" ]; then
    echo "Migrating existing data from $OLD_DATA → $DEPLOY_DIR/data/ ..."
    cp -r "$OLD_DATA/." "$DEPLOY_DIR/data/"
    echo "Migration complete. Old data left in place at $OLD_DATA (remove manually when satisfied)."
  else
    echo "Deploy data dir already has content — skipping migration from $OLD_DATA"
  fi
fi

# ── Frontend deps ────────────────────────────────────────────────────────────
echo "Installing frontend dependencies..."
cd "$SCRIPT_DIR"
npm install --silent

# ── .env (write once; preserved on re-deploy) ────────────────────────────────
if [ ! -f "$DEPLOY_DIR/.env" ]; then
  echo "Writing .env..."
  cat > "$DEPLOY_DIR/.env" <<EOF
DEPLOY_DIR=$DEPLOY_DIR
AI_DEV_PATH=$AI_DEV_PATH
BACKEND_PORT=$BACKEND_PORT
FRONTEND_PORT=$FRONTEND_PORT
DATA_DIR=$DEPLOY_DIR/data
FRONTEND_MODE=$FRONTEND_MODE
EOF
else
  echo ".env already exists — preserving (edit $DEPLOY_DIR/.env to change settings)"
fi

# ── Generate start.sh ────────────────────────────────────────────────────────
cat > "$DEPLOY_DIR/start.sh" <<'STARTEOF'
#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load env
set -a; source "$SCRIPT_DIR/.env"; set +a
# Expand ~ in path vars
AI_DEV_PATH="${AI_DEV_PATH/#\~/$HOME}"
DEPLOY_DIR="${DEPLOY_DIR/#\~/$HOME}"
DATA_DIR="${DATA_DIR:-$DEPLOY_DIR/data}"

mkdir -p "$DEPLOY_DIR/logs" "$DATA_DIR"

# ── Backend ──────────────────────────────────────────────────────────────────
echo "Starting backend on port $BACKEND_PORT..."
cd "$AI_DEV_PATH/frontends/karaoke/server"
DATA_DIR="$DATA_DIR" PORT="$BACKEND_PORT" \
  nohup "$DEPLOY_DIR/.venv/bin/python" main.py \
  > "$DEPLOY_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$DATA_DIR/backend.pid"

sleep 2
if ! kill -0 $BACKEND_PID 2>/dev/null; then
  echo "ERROR: Backend failed to start — see $DEPLOY_DIR/logs/backend.log"
  tail -20 "$DEPLOY_DIR/logs/backend.log"
  exit 1
fi
echo "Backend started (PID: $BACKEND_PID)"

# ── Frontend ─────────────────────────────────────────────────────────────────
echo "Starting frontend on port $FRONTEND_PORT (mode: ${FRONTEND_MODE:-dev})..."
cd "$AI_DEV_PATH/frontends/karaoke"

if [ "${FRONTEND_MODE:-dev}" = "prod" ]; then
  echo "Building frontend..."
  npm run build
  nohup npm run start -- -p "$FRONTEND_PORT" \
    > "$DEPLOY_DIR/logs/frontend.log" 2>&1 &
else
  nohup npm run dev -- -p "$FRONTEND_PORT" \
    > "$DEPLOY_DIR/logs/frontend.log" 2>&1 &
fi
FRONTEND_PID=$!
echo $FRONTEND_PID > "$DATA_DIR/frontend.pid"

sleep 3
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
  echo "ERROR: Frontend failed to start — see $DEPLOY_DIR/logs/frontend.log"
  tail -20 "$DEPLOY_DIR/logs/frontend.log"
  kill $BACKEND_PID 2>/dev/null || true
  exit 1
fi
echo "Frontend started (PID: $FRONTEND_PID)"

echo ""
echo "Karaoke is running!"
echo "  Frontend: http://localhost:${FRONTEND_PORT}"
echo "  Backend:  http://localhost:${BACKEND_PORT}"
echo "  Logs:     $DEPLOY_DIR/logs/"
echo "  Data:     $DATA_DIR"
echo ""
echo "To stop: $SCRIPT_DIR/stop.sh"
STARTEOF

chmod +x "$DEPLOY_DIR/start.sh"

# ── Generate stop.sh ─────────────────────────────────────────────────────────
cat > "$DEPLOY_DIR/stop.sh" <<'STOPEOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a; source "$SCRIPT_DIR/.env"; set +a
DEPLOY_DIR="${DEPLOY_DIR/#\~/$HOME}"
DATA_DIR="${DATA_DIR:-$DEPLOY_DIR/data}"

echo "Stopping karaoke..."

stop_pid() {
  local name="$1"
  local port="$2"
  local pidfile="$DATA_DIR/${name}.pid"
  if [ -f "$pidfile" ]; then
    PID=$(cat "$pidfile")
    if kill -0 "$PID" 2>/dev/null; then
      echo "  Stopping $name (PID: $PID)..."
      kill "$PID"
    else
      echo "  $name PID $PID not found"
    fi
    rm -f "$pidfile"
  fi
  # Kill anything still holding the port (handles stale processes from previous runs)
  if [ -n "$port" ] && command -v fuser &>/dev/null; then
    fuser -k "${port}/tcp" 2>/dev/null && echo "  Killed stale process on port $port" || true
  fi
}

stop_pid backend "$BACKEND_PORT"
stop_pid frontend "$FRONTEND_PORT"
echo "Done"
STOPEOF

chmod +x "$DEPLOY_DIR/stop.sh"

echo ""
echo "========================================"
echo "Deploy complete!"
echo "========================================"
echo ""
echo "  Deploy dir:  $DEPLOY_DIR"
echo "  To start:    $DEPLOY_DIR/start.sh"
echo "  To stop:     $DEPLOY_DIR/stop.sh"
echo "  Config:      $DEPLOY_DIR/.env"
echo ""
