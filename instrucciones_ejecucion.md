# Instrucciones para Ejecutar los 3 Nodos de Dispotify

**Fecha:** 12 de diciembre de 2025  
**Objetivo:** Ejecutar los nodos de API uno por uno para probar el descubrimiento y sincronización dinámica.

## Prerrequisitos
- Docker instalado.
- Red Docker creada: `docker network create dispotify-network` (si no existe).
- Imagen construida: `docker build -t dispotify-backend ./backend` (solo una vez, ya que el código se monta en vivo).

## Nota Importante
Ahora el código se monta en vivo via volúmenes. Cambia el código en tu host y Uvicorn recargará automáticamente (--reload). **No necesitas reconstruir la imagen** para cambios en el código Python.

## Paso 1: Construir la Imagen (Solo una vez)
```bash
cd /home/herrera/Documents/Dispotify
docker build -t dispotify-backend ./backend
```

## Paso 2: Ejecutar el Primer Nodo (node-1)
```bash
docker run -d \
  --name node1 \
  --network dispotify-network \
  --network-alias dispotify-cluster \
  -p 8001:8000 \
  -v $(pwd)/backend/app:/app/app \
  -v $(pwd)/backend/requirements.txt:/app/requirements.txt \
  -e NODE_ID=node-1 \
  -e NODE_ADDRESS=node1 \
  -e NODE_PORT=8000 \
  -e API_PORT=8000 \
  -e VIRTUAL_NODES=150 \
  -e REPLICATION_FACTOR=2 \
  -e UPLOAD_DIR=/app/music_files \
  -e RAFT_DATA_DIR=/app/raft_data \
  -e BOOTSTRAP_SERVICE=dispotify-cluster \
  -v $(pwd)/raft_data_node1:/app/raft_data \
  -v $(pwd)/music_files_node1:/app/music_files \
  dispotify-backend
```

- **Explicación:** Inicia el primer nodo en modo SOLO. Espera a que esté listo (verifica logs: `docker logs node1`).

## Paso 3: Ejecutar el Segundo Nodo (node-2)
```bash
docker run -d \
  --name node2 \
  --network dispotify-network \
  --network-alias dispotify-cluster \
  -p 8002:8000 \
  -v $(pwd)/backend/app:/app/app \
  -v $(pwd)/backend/requirements.txt:/app/requirements.txt \
  -e NODE_ID=node-2 \
  -e NODE_ADDRESS=node2 \
  -e NODE_PORT=8000 \
  -e API_PORT=8000 \
  -e VIRTUAL_NODES=150 \
  -e REPLICATION_FACTOR=2 \
  -e UPLOAD_DIR=/app/music_files \
  -e RAFT_DATA_DIR=/app/raft_data \
  -e BOOTSTRAP_SERVICE=dispotify-cluster \
  -v $(pwd)/raft_data_node2:/app/raft_data \
  -v $(pwd)/music_files_node2:/app/music_files \
  dispotify-backend
```

- **Explicación:** Inicia el segundo nodo, que descubre al primero via DNS (`dispotify-cluster`), se registra y sincroniza.

## Paso 4: Ejecutar el Tercer Nodo (node-3)
```bash
docker run -d \
  --name node3 \
  --network dispotify-network \
  --network-alias dispotify-cluster \
  -p 8003:8000 \
  -v $(pwd)/backend/app:/app/app \
  -v $(pwd)/backend/requirements.txt:/app/requirements.txt \
  -e NODE_ID=node-3 \
  -e NODE_ADDRESS=node3 \
  -e NODE_PORT=8000 \
  -e API_PORT=8000 \
  -e VIRTUAL_NODES=150 \
  -e REPLICATION_FACTOR=2 \
  -e UPLOAD_DIR=/app/music_files \
  -e RAFT_DATA_DIR=/app/raft_data \
  -e BOOTSTRAP_SERVICE=dispotify-cluster \
  -v $(pwd)/raft_data_node3:/app/raft_data \
  -v $(pwd)/music_files_node3:/app/music_files \
  dispotify-backend
```

- **Explicación:** Inicia el tercer nodo, que descubre a los anteriores via DNS (`dispotify-cluster`), se registra y sincroniza.

## Paso 5: Ejecutar el Frontend (Opcional)
```bash
docker run -d \
  --name frontend \
  --network dispotify-network \
  -p 3000:3000 \
  -e VITE_API_URL=http://localhost:8001/ \
  dispotify-frontend
```

- **Nota:** Primero construye la imagen: `docker build -t dispotify-frontend ./frontend`. El frontend se conecta al backend-1 via localhost:8001 desde el host.

## Verificación
- **Health Checks:** `curl http://localhost:8001/health`, `curl http://localhost:8002/health` y `curl http://localhost:8003/health`
- **Logs:** 
  - Ver logs en tiempo real: `docker logs -f node1`, `docker logs -f node2` y `docker logs -f node3`
  - Ver logs completos: `docker logs node1`, `docker logs node2` y `docker logs node3`
  - Para ver descubrimiento, merges y errores: Busca mensajes como "Bootstrap descubrio", "Merge de logs completado", o "Error".
- **Pruebas:** Sube un archivo a uno (e.g., via POST a `http://localhost:8001/api/v1/music/upload`), verifica replicación en los otros.

## Limpieza
```bash
docker stop node1 node2 node3
docker rm node1 node2 node3
docker network rm dispotify-network  # Opcional
```

## Notas
- Todos los datos (código, archivos de música y datos Raft) se persisten en volúmenes locales.
- Si hay errores, verifica que la red y aliases estén correctos.
- Para más nodos, repite el comando con nuevos nombres y puertos.
- **Cambios en código:** Edita los archivos en `./backend/app/` y Uvicorn recargará automáticamente. No reconstruyas la imagen.
