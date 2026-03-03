#!/bin/bash
# Dev convenience script — starts frontend and backend for local development.
# Expects a .venv to exist in server/ (create one with: cd server && python3 -m venv .venv && pip install -r requirements.txt)
# For deployment, use deploy.sh instead.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Backend
cd server
if [ ! -d ".venv" ]; then
    echo "Error: no .venv found in server/. Run deploy.sh or set up manually:"
    echo "  cd server && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi
source .venv/bin/activate
python main.py &
BACKEND_PID=$!
cd ..

sleep 2

# Frontend
npm run dev -- -p 3002 &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo ""
echo "Frontend: http://localhost:3002"
echo "Backend:  http://localhost:8001"
echo ""

wait
