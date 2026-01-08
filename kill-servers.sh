#!/bin/bash
# Kill all running Math OCR servers

echo "Stopping all Math OCR servers..."

# Kill process on port 8000 (Python API)
PORT_8000=$(lsof -ti:8000 2>/dev/null)
if [ -n "$PORT_8000" ]; then
  echo "  Killing process on port 8000: $PORT_8000"
  kill -9 $PORT_8000 2>/dev/null
else
  echo "  No process on port 8000"
fi

# Kill process on port 3000 (Next.js)
PORT_3000=$(lsof -ti:3000 2>/dev/null)
if [ -n "$PORT_3000" ]; then
  echo "  Killing process on port 3000: $PORT_3000"
  kill -9 $PORT_3000 2>/dev/null
else
  echo "  No process on port 3000"
fi

# Also kill by process name as backup
PYTHON_PIDS=$(ps aux | grep -E "uvicorn|api_server" | grep -v grep | awk '{print $2}')
if [ -n "$PYTHON_PIDS" ]; then
  echo "  Killing Python API processes: $PYTHON_PIDS"
  echo "$PYTHON_PIDS" | xargs kill -9 2>/dev/null
fi

NEXT_PIDS=$(ps aux | grep -E "next-server|next dev" | grep -v grep | awk '{print $2}')
if [ -n "$NEXT_PIDS" ]; then
  echo "  Killing Next.js processes: $NEXT_PIDS"
  echo "$NEXT_PIDS" | xargs kill -9 2>/dev/null
fi

sleep 1
echo "Done! You can now run ./start.sh"
