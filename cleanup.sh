

docker rm -f dispotify-backend-1 dispotify-backend-2 dispotify-frontend

docker volume rm raft_data_node1 music_files_node1 db_data_node1 raft_data_node2 music_files_node2 db_data_node2

docker run -d \
  --name dispotify-backend-1 \
  --network dispotify-network \
  --network-alias dispotify-cluster \
  --publish 8001:8000 \
  --env NODE_ID=node-1 \
  --env BOOTSTRAP_SERVICE=dispotify-cluster \
  --volume raft_data_node1:/app/raft_data \
  --volume music_files_node1:/app/music_files \
  --volume db_data_node1:/app/data \
  --volume ./backend/app:/app/app \
  herrera/dispotify-backend

docker run -d \
  --name dispotify-backend-2 \
  --network dispotify-network \
  --network-alias dispotify-cluster \
  --publish 8002:8000 \
  --env NODE_ID=node-2 \
  --env BOOTSTRAP_SERVICE=dispotify-cluster \
  --volume raft_data_node2:/app/raft_data \
  --volume music_files_node2:/app/music_files \
  --volume db_data_node2:/app/data \
  --volume ./backend/app:/app/app \
  herrera/dispotify-backend




docker run -d \
  --name dispotify-frontend \
  --network dispotify-network \
  --publish 3000:3000 \
  --publish 3001:3001 \
  --env VITE_API_URL=http:
  --env VITE_STATIC_URL=http:
  --env CLUSTER_DNS_NAME=dispotify-cluster \
  --env BACKEND_PORT=8000 \
  --env LEADER_ENDPOINT=/cluster/leader \
  --env SERVICE_PORT=3001 \
  --env LEADER_CACHE_TTL=5000 \
  --volume ./frontend/src:/app/src \
  herrera/dispotify-frontend