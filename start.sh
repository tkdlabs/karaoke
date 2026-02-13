#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Backend
cd server
if [ ! -d ".venv" ]; then
    echo "Creating Python venv..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi
python main.py &
BACKEND_PID=$!
cd ..

sleep 2

# Frontend
npm run dev &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo ""
echo "Frontend: http://localhost:3002"
echo "Backend:  http://localhost:8001"
echo ""

wait
