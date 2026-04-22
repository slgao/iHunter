#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== iHunters Germany — AI Export Platform ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found"
  exit 1
fi

# Create venv if needed
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate

echo "Installing dependencies..."
pip install -q -r backend/requirements.txt

echo ""
echo "Starting server at http://localhost:8000"
echo "Press Ctrl+C to stop."
echo ""

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
