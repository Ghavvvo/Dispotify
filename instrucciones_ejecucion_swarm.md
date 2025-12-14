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
- Ejecuta los comandos `docker run` desde la raíz del proyecto Dispotify en cada host (para que `./backend` resuelva correctamente).

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

## Paso 3: Ejecutar Contenedores con Docker Run
En el host manager, ejecuta los siguientes comandos para crear los contenedores:

### Backend-1 (en Host 1)
```bash
docker run -d \
  --name dispotify-backend-1 \
  --network dispotify-network \
  --network-alias dispotify-cluster \
  --publish 8001:8000 \
  --env NODE_ID=node-1 \
  --env BOOTSTRAP_SERVICE=dispotify-cluster \
  --volume raft_data_node1:/app/raft_data \
  --volume music_files_node1:/app/music_files \
  --volume ./backend:/app \
  herrera/dispotify-backend
```

### Backend-2 (en Host 2)
```bash
docker run -d \
  --name dispotify-backend-2 \
  --network dispotify-network \
  --network-alias dispotify-cluster \
  --publish 8002:8000 \
  --env NODE_ID=node-2 \
  --env BOOTSTRAP_SERVICE=dispotify-cluster \
  --volume raft_data_node2:/app/raft_data \
  --volume music_files_node2:/app/music_files \
  --volume ./backend:/app \
  herrera/dispotify-backend
```

### Backend-3 (en Host 2)
```bash
docker run -d \
  --name dispotify-backend-3 \
  --network dispotify-network \
  --network-alias dispotify-cluster \
  --publish 8003:8000 \
  --env NODE_ID=node-3 \
  --env BOOTSTRAP_SERVICE=dispotify-cluster \
  --volume raft_data_node3:/app/raft_data \
  --volume music_files_node3:/app/music_files \
  --volume ./backend:/app \
  herrera/dispotify-backend
```

### Frontend con Leader Proxy integrado (en Host 1)
El frontend ahora incluye el proxy leader-resolver en el mismo contenedor:
```bash
docker run -d \
  --name dispotify-frontend \
  --network dispotify-network \
  --publish 3000:3000 \
  --publish 3001:3001 \
  --env VITE_API_URL=http://localhost:3001/api/v1/ \
  --env VITE_STATIC_URL=http://localhost:3001 \
  --env CLUSTER_DNS_NAME=dispotify-cluster \
  --env BACKEND_PORT=8000 \
  --env LEADER_ENDPOINT=/cluster/leader \
  --env SERVICE_PORT=3001 \
  --env LEADER_CACHE_TTL=5000 \
  herrera/dispotify-frontend
```

**Variables de entorno del Frontend:**
| Variable | Default | Descripción |
|----------|---------|-------------|
| `VITE_API_URL` | - | URL de la API (apunta al proxy interno) |
| `VITE_STATIC_URL` | - | URL para archivos estáticos |

**Variables de entorno del Leader Proxy (integrado):**
| Variable | Default | Descripción |
|----------|---------|-------------|
| `CLUSTER_DNS_NAME` | `dispotify-cluster` | Nombre DNS/alias de red de los backends |
| `BACKEND_PORT` | `8000` | Puerto interno donde escuchan los backends |
| `LEADER_ENDPOINT` | `/cluster/leader` | Endpoint que devuelve info del líder |
| `SERVICE_PORT` | `3001` | Puerto donde escucha el proxy |
| `LEADER_CACHE_TTL` | `5000` | TTL del caché del líder en ms |

**Puertos expuestos:**
- `3000` → Frontend (Vite)
- `3001` → Leader Proxy (integrado en el mismo contenedor)

**Endpoints del Proxy:**
- `/api/*` → Redirige al líder automáticamente
- `/static/*` → Archivos estáticos del líder
- `/health` → Health check del proxy
- `/cluster/leader` → Info del líder (debugging)

**Nota:** El frontend apunta al Leader Proxy interno (puerto 3001), que se encarga de redirigir automáticamente todas las peticiones al líder actual del clúster.

## Paso 4: Verificar Despliegue
- **Contenedores:** `docker ps`
- **Logs:** `docker logs dispotify-backend-1`, `docker logs dispotify-frontend`, etc.
- **Health Checks:** Desde cualquier host, `curl http://<IP_HOST1>:8001/health`, etc.
- **Estado del Cluster:** `curl http://<IP_HOST1>:8001/cluster/status` (Ver líder, término, nodos conectados)
- **Archivos en Nodo:** `curl http://<IP_HOST1>:8001/cluster/files`
- **Leader Proxy (integrado en frontend):** `curl http://<IP_HOST1>:3001/cluster/leader` (Obtener líder actual del clúster)

## Paso 5: Pruebas
- Sube archivos via POST a `http://<IP_HOST1>:8001/api/v1/music/upload`.
- Verifica replicación en otros nodos.
- Simula fallos: Detén un host y verifica que los contenedores se redistribuyan (nota: con docker run, no hay replicación automática; necesitarías scripts para manejar fallos).

## Limpieza
```bash
docker rm -f dispotify-backend-1 dispotify-backend-2 dispotify-backend-3 dispotify-frontend
docker network rm dispotify-network
docker volume rm raft_data_node1 music_files_node1 raft_data_node2 music_files_node2 raft_data_node3 music_files_node3
```

## Notas
- Asegura que los nombres de host (`host1`, `host2`) coincidan con `docker node ls`.
- Docker run en Swarm no maneja replicas automáticamente; para alta disponibilidad, considera usar docker service o scripts de monitoreo.
- Monitorea con `docker stats` y logs para tolerancia a fallos.
