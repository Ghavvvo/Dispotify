# Instrucciones para Ejecutar Dispotify en Docker Swarm con 2 Hosts usando Docker Run

**Fecha:** 12 de diciembre de 2025  
**Objetivo:** Ejecutar los nodos de Dispotify en un cluster Docker Swarm distribuido en 2 hosts físicos para alta disponibilidad y tolerancia a fallos, usando comandos docker run con restricciones de Swarm.

## Prerrequisitos
- Docker instalado en ambos hosts.
- Docker Swarm inicializado en el host manager: `docker swarm init --advertise-addr 10.6.121.225`.
- El segundo host unido al swarm como manager: Obtén el token de manager en el host 1 con `docker swarm join-token manager`, luego en el host 2 ejecuta `docker swarm join --token <MANAGER_TOKEN> <IP_MANAGER>:2377`.
- Imágenes construidas y disponibles en ambos hosts o en un registry compartido (e.g., Docker Hub).
- Red overlay creada: `docker network create --driver overlay --attachable dispotify-network`.
- Cada contenedor que participe en RAFT debe conectarse con `--network-alias dispotify-cluster` para que el DNS interno resuelva el nombre usado por `BOOTSTRAP_SERVICE`.
- `NODE_ADDRESS` es opcional; si no se especifica, el backend detecta automáticamente su IP overlay.
- Volúmenes normales de Docker para persistencia.

## Arquitectura
- **Host 1 (Manager):** Ejecuta servicios de backend-1 y frontend.
- **Host 2 (Manager):** Ejecuta servicios de backend-2 y backend-3.
- **Balanceo:** Usa Docker Swarm para distribuir y balancear carga.
- **Persistencia:** Usa volúmenes normales de Docker.

## Paso 1: Preparar Imágenes
Construye y sube las imágenes a un registry (e.g., Docker Hub):
```bash
# En el host manager
docker build -t herrera/dispotify-backend ./backend
docker build -t herrera/dispotify-frontend ./frontend
docker push herrera/dispotify-backend
docker push herrera/dispotify-frontend
```

dock
## Paso 3: Ejecutar Contenedores con Docker Run
En el host manager, ejecuta los siguientes comandos para crear los contenedores:

### Backend-1 (en Host 1)
```bash
docker run -d \
  --name dispotify-backend-1 \
  --network dispotify-network \
  --publish 8001:8000 \
  --env NODE_ID=node-1 \
  --env BOOTSTRAP_SERVICE=dispotify-cluster \
  --volume raft_data_node1:/app/raft_data \
  --volume music_files_node1:/app/music_files \
  herrera/dispotify-backend
```

### Backend-2 (en Host 2)
```bash
docker run -d \
  --name dispotify-backend-2 \
  --network dispotify-network \
  --publish 8002:8000 \
  --env NODE_ID=node-2 \
  --env NODE_ADDRESS=backend-2 \
  --env BOOTSTRAP_SERVICE=dispotify-cluster \
  --volume raft_data_node2:/app/raft_data \
  --volume music_files_node2:/app/music_files \
  herrera/dispotify-backend
```

### Backend-3 (en Host 2)
```bash
docker run -d \
  --name dispotify-backend-3 \
  --network dispotify-network \
  --publish 8003:8000 \
  --env NODE_ID=node-3 \
  --env NODE_ADDRESS=backend-3 \
  --env BOOTSTRAP_SERVICE=dispotify-cluster \
  --volume raft_data_node3:/app/raft_data \
  --volume music_files_node3:/app/music_files \
  herrera/dispotify-backend
```

### Frontend (en Host 1)
```bash
docker run -d \
  --name dispotify-frontend \
  --network dispotify-network \
  --publish 3000:3000 \
  --env VITE_API_URL=http://backend-1:8000/api/v1/ \
  herrera/dispotify-frontend
```

## Paso 4: Verificar Despliegue
- **Contenedores:** `docker ps`
- **Logs:** `docker logs dispotify-backend-1`, etc.
- **Health Checks:** Desde cualquier host, `curl http://<IP_HOST1>:8001/health`, etc.

## Paso 5: Pruebas
- Sube archivos via POST a `http://<IP_HOST1>:8001/api/v1/music/upload`.
- Verifica replicación en otros nodos.
- Simula fallos: Detén un host y verifica que los contenedores se redistribuyan (nota: con docker run, no hay replicación automática; necesitarías scripts para manejar fallos).

## Limpieza
```bash
docker rm -f dispotify-backend-1 dispotify-backend-2 dispotify-backend-3 dispotify-frontend
docker network rm dispotify-network
```

## Notas
- Asegura que los nombres de host (`host1`, `host2`) coincidan con `docker node ls`.
- Docker run en Swarm no maneja replicas automáticamente; para alta disponibilidad, considera usar docker service o scripts de monitoreo.
- Monitorea con `docker stats` y logs para tolerancia a fallos.
