# Instrucciones para Ejecutar Dispotify en Docker Swarm con 2 Hosts

**Fecha:** 12 de diciembre de 2025  
**Objetivo:** Ejecutar los nodos de Dispotify en un cluster Docker Swarm distribuido en 2 hosts físicos para alta disponibilidad y tolerancia a fallos.

## Prerrequisitos
- Docker instalado en ambos hosts.
- Docker Swarm inicializado en el host manager: `docker swarm init --advertise-addr <IP_MANAGER>`.
- El segundo host unido al swarm: `docker swarm join --token <TOKEN> <IP_MANAGER>:2377`.
- Imágenes construidas y disponibles en ambos hosts o en un registry compartido (e.g., Docker Hub).
- Red overlay creada: `docker network create --driver overlay dispotify-overlay`.
- Almacenamiento compartido (e.g., NFS) para volúmenes persistentes, ya que no se permiten volúmenes locales ni RAM.

## Arquitectura
- **Host 1 (Manager):** Ejecuta servicios de backend-1 y frontend.
- **Host 2 (Worker):** Ejecuta servicios de backend-2 y backend-3.
- **Balanceo:** Usa Docker Swarm para distribuir y balancear carga.
- **Persistencia:** Usa NFS para volúmenes compartidos entre hosts.

## Paso 1: Preparar Imágenes
Construye y sube las imágenes a un registry (e.g., Docker Hub):
```bash
# En el host manager
docker build -t herrera/dispotify-backend ./backend
docker build -t herrera/dispotify-frontend ./frontend
docker push herrera/dispotify-backend
docker push herrera/dispotify-frontend
```

## Paso 2: Configurar Almacenamiento NFS
- Configura un servidor NFS en uno de los hosts o externo.
- Monta volúmenes NFS en ambos hosts para `/mnt/nfs/raft_data_node1`, `/mnt/nfs/music_files_node1`, etc.

Ejemplo en `/etc/fstab`:
```
nfs-server:/export/raft_data_node1 /mnt/nfs/raft_data_node1 nfs defaults 0 0
nfs-server:/export/music_files_node1 /mnt/nfs/music_files_node1 nfs defaults 0 0
# Repite para node2 y node3
```

## Paso 3: Crear docker-compose.yml para Swarm
Crea un archivo `docker-compose.swarm.yml`:

```yaml
version: '3.8'

services:
  backend-1:
    image: herrera/dispotify-backend
    networks:
      - dispotify-overlay
    ports:
      - "8001:8000"
    environment:
      NODE_ID: node-1
      NODE_ADDRESS: backend-1
      NODE_PORT: 8000
      API_PORT: 8000
      VIRTUAL_NODES: 150
      REPLICATION_FACTOR: 2
      UPLOAD_DIR: /app/music_files
      RAFT_DATA_DIR: /app/raft_data
      BOOTSTRAP_SERVICE: dispotify-cluster
    volumes:
      - /mnt/nfs/raft_data_node1:/app/raft_data
      - /mnt/nfs/music_files_node1:/app/music_files
    deploy:
      placement:
        constraints:
          - node.hostname == host1  # Host manager
      replicas: 1
      restart_policy:
        condition: on-failure

  backend-2:
    image: herrera/dispotify-backend
    networks:
      - dispotify-overlay
    ports:
      - "8002:8000"
    environment:
      NODE_ID: node-2
      NODE_ADDRESS: backend-2
      NODE_PORT: 8000
      API_PORT: 8000
      VIRTUAL_NODES: 150
      REPLICATION_FACTOR: 2
      UPLOAD_DIR: /app/music_files
      RAFT_DATA_DIR: /app/raft_data
      BOOTSTRAP_SERVICE: dispotify-cluster
    volumes:
      - /mnt/nfs/raft_data_node2:/app/raft_data
      - /mnt/nfs/music_files_node2:/app/music_files
    deploy:
      placement:
        constraints:
          - node.hostname == host2  # Host worker
      replicas: 1
      restart_policy:
        condition: on-failure

  backend-3:
    image: herrera/dispotify-backend
    networks:
      - dispotify-overlay
    ports:
      - "8003:8000"
    environment:
      NODE_ID: node-3
      NODE_ADDRESS: backend-3
      NODE_PORT: 8000
      API_PORT: 8000
      VIRTUAL_NODES: 150
      REPLICATION_FACTOR: 2
      UPLOAD_DIR: /app/music_files
      RAFT_DATA_DIR: /app/raft_data
      BOOTSTRAP_SERVICE: dispotify-cluster
    volumes:
      - /mnt/nfs/raft_data_node3:/app/raft_data
      - /mnt/nfs/music_files_node3:/app/music_files
    deploy:
      placement:
        constraints:
          - node.hostname == host2  # Host worker
      replicas: 1
      restart_policy:
        condition: on-failure

  frontend:
    image: herrera/dispotify-frontend
    networks:
      - dispotify-overlay
    ports:
      - "3000:3000"
    environment:
      VITE_API_URL: http://backend-1:8000/api/v1/  # Apunta al backend-1 en la red overlay
    deploy:
      placement:
        constraints:
          - node.hostname == host1  # Host manager
      replicas: 1
      restart_policy:
        condition: on-failure

networks:
  dispotify-overlay:
    external: true
```

## Paso 4: Desplegar el Stack
En el host manager:
```bash
docker stack deploy -c docker-compose.swarm.yml dispotify
```

## Paso 5: Verificar Despliegue
- **Servicios:** `docker stack services dispotify`
- **Tareas:** `docker stack ps dispotify`
- **Logs:** `docker service logs dispotify_backend-1`, etc.
- **Health Checks:** Desde cualquier host, `curl http://<IP_HOST1>:8001/health`, etc.

## Paso 6: Pruebas
- Sube archivos via POST a `http://<IP_HOST1>:8001/api/v1/music/upload`.
- Verifica replicación en otros nodos.
- Simula fallos: Detén un host y verifica que los servicios se redistribuyan.

## Limpieza
```bash
docker stack rm dispotify
docker network rm dispotify-overlay
```

## Notas
- Asegura que los nombres de host (`host1`, `host2`) coincidan con `docker node ls`.
- Para escalabilidad, aumenta replicas en el deploy.
- Monitorea con `docker stats` y logs para tolerancia a fallos.
- Si no hay NFS, considera alternativas como GlusterFS o volúmenes en cloud.</content>
<parameter name="filePath">/home/herrera/Documents/Dispotify/instrucciones_ejecucion_swarm.md
