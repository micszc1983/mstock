#!/usr/bin/env bash
set +e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$PROJECT_DIR/backend.pid" ]; then
  kill "$(cat "$PROJECT_DIR/backend.pid")" 2>/dev/null
  rm -f "$PROJECT_DIR/backend.pid"
fi

if [ -f "$PROJECT_DIR/frontend.pid" ]; then
  kill "$(cat "$PROJECT_DIR/frontend.pid")" 2>/dev/null
  rm -f "$PROJECT_DIR/frontend.pid"
fi

pkill -f "uvicorn main:app" 2>/dev/null
pkill -f "npm run dev" 2>/dev/null
pkill -f "npm run serve" 2>/dev/null
pkill -f "vite" 2>/dev/null
pkill -f "frontend/server.mjs" 2>/dev/null
pkill -f "node.*5173" 2>/dev/null

echo "Zatrzymano backend i frontend."
