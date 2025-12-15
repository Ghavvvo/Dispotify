


echo "Starting leader-resolver proxy..."
cd /app/leader-resolver
node server.js &


sleep 2


echo "Starting frontend..."
cd /app
pnpm run dev --host 0.0.0.0 --port 3000
