#!/bin/bash
# Quick start script for Math OCR app

set -e

echo "Starting Math OCR App..."
echo ""

# Load environment variables from .env.local if it exists
if [ -f ".env.local" ]; then
  echo "Loading environment variables from .env.local..."
  export $(grep -v '^#' .env.local | xargs)
  echo ""
fi

# Check if GEMINI_API_KEY is set
if [ -z "$GEMINI_API_KEY" ]; then
  echo "WARNING: GEMINI_API_KEY not set!"
  echo "   Add it to .env.local or export GEMINI_API_KEY='your-key'"
  echo "   Get your key from: https://aistudio.google.com/apikey"
  echo ""
  read -p "Continue anyway? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi

# Check if NEXTAUTH_SECRET is set
if [ -z "$NEXTAUTH_SECRET" ]; then
  echo "ERROR: NEXTAUTH_SECRET not set!"
  echo "   Add it to .env.local (should already be there)"
  echo "   Or generate one with: openssl rand -base64 32"
  exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
  echo "WARNING: uv not found. Install with:"
  echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo ""
  echo "   Or use pip instead:"
  echo "   pip install -r requirements.txt"
  echo "   python api_server.py"
  exit 1
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
  echo "Installing Node.js dependencies..."
  npm install
  echo ""
fi

# Install Python dependencies
echo "Checking Python dependencies..."
uv sync

# Create .env.local if it doesn't exist
if [ ! -f ".env.local" ]; then
  echo "Creating .env.local..."
  echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
fi

echo "Setup complete!"
echo ""

# Kill any existing processes on the ports
echo "Checking for existing processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null && echo "  Killed process on port 8000" || echo "  Port 8000 is free"
lsof -ti:3000 | xargs kill -9 2>/dev/null && echo "  Killed process on port 3000" || echo "  Port 3000 is free"
sleep 1
echo ""

echo "Starting servers..."
echo "  - Python API: http://localhost:8000"
echo "  - Next.js UI: http://localhost:3000"
echo "  - RQ Worker: background"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Function to cleanup on exit
cleanup() {
  echo ""
  echo "Stopping servers..."
  kill $API_PID $WORKER_PID $NEXTJS_PID 2>/dev/null || true
  exit 0
}

trap cleanup INT TERM

# Start API server in background
echo "Starting Python API server..."
uv run uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

# Wait a bit for API to start
sleep 2

# Start RQ worker in background
echo "Starting RQ worker..."
uv run python worker.py &
WORKER_PID=$!

# Start Next.js in background
echo "Starting Next.js dev server..."
npm run dev &
NEXTJS_PID=$!

# Wait for both processes
wait $API_PID $WORKER_PID $NEXTJS_PID
