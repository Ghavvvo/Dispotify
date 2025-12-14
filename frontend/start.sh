#!/bin/sh

# Start the leader-resolver proxy in the background
echo "Starting leader-resolver proxy..."
cd /app/leader-resolver
node server.js &

# Wait a moment for the proxy to start
sleep 2

# Start the frontend
echo "Starting frontend..."
cd /app
pnpm run dev --host 0.0.0.0 --port 3000
