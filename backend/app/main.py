from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager
import logging
import os

from app.core.config import settings
from app.core.database import engine, Base
from app.api.routes import music
from app.api.routes import distributed
from app.api.routes import internal

from app.distributed.grpc_communication import (
    GRPCClient,
    NodeInfo,
    initialize_grpc_client
)
from app.distributed.grpc_raft import (
    RaftNode,
    initialize_raft,
    get_raft_node
)
from app.distributed.grpc_raft_server import (
    initialize_grpc_raft_server,
    get_grpc_raft_server
)
from app.distributed.discovery import (
    ServiceDiscovery,
    initialize_discovery
)
from app.distributed.locks import (
    LockManager,
    initialize_lock_manager
)
from app.distributed.events import (
    EventQueue,
    initialize_event_queue
)
from app.distributed.replication import (
    ReplicationManager,
    initialize_replication_manager
)
from app.distributed.consistent_hash import ConsistentHashRing

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando sistema distribuido con descubrimiento dinámico...")

    # Bootstrap: Definir este nodo
    this_node = NodeInfo(
        id=settings.NODE_ID,
        address=os.getenv("NODE_ADDRESS", "localhost"),
        port=int(os.getenv("NODE_PORT", "8000"))
    )
    logger.info(f"Nodo local: {this_node.id} @ {this_node.address}:{this_node.port}")

    # Inicialmente el cluster solo contiene este nodo
    # Los demás nodos se descubrirán dinámicamente
    cluster_nodes = [this_node]

    grpc_client = initialize_grpc_client(timeout=5.0, max_retries=3)
    await grpc_client.start()
    logger.info("gRPC Client iniciado")

    raft_node = initialize_raft(
        node_id=settings.NODE_ID,
        node_info=this_node,
        cluster_nodes=None,  # El cluster se formará dinámicamente
        data_dir=os.getenv("RAFT_DATA_DIR", "/data/raft"),
        election_timeout_min=float(os.getenv("RAFT_ELECTION_TIMEOUT_MIN", "1.5")),
        election_timeout_max=float(os.getenv("RAFT_ELECTION_TIMEOUT_MAX", "3.0")),
        heartbeat_interval=float(os.getenv("RAFT_HEARTBEAT_INTERVAL", "0.5"))
    )

    discovery = None
    hash_ring = None

    async def on_become_leader():
        logger.info("Este nodo se convirtio en LIDER del cluster")

    async def on_lose_leadership():
        logger.info("Este nodo dejo de ser lider")

    async def on_command_applied(command: dict):
        cmd_type = command.get("type")

        if cmd_type == "add_node":
            node_id = command.get("node_id")
            address = command.get("address")
            port = command.get("port")

            if node_id and address and port and discovery and hash_ring:
                new_node = NodeInfo(id=node_id, address=address, port=port)
                discovery.add_node(new_node)
                hash_ring.add_node(node_id)
                logger.info(f"Nodo agregado al sistema completo: {node_id}")

        elif cmd_type == "remove_node":
            node_id = command.get("node_id")

            if node_id and discovery and hash_ring:
                discovery.remove_node(node_id)
                hash_ring.remove_node(node_id)
                logger.info(f"Nodo eliminado del sistema completo: {node_id}")

    raft_node.set_callbacks(
        on_become_leader=on_become_leader,
        on_lose_leadership=on_lose_leadership,
        on_command_applied=on_command_applied
    )

    await raft_node.start()
    logger.info(f"Raft Node iniciado (term={raft_node.current_term})")

    grpc_port = int(os.getenv("GRPC_PORT", str(this_node.port + 1000)))
    grpc_server = initialize_grpc_raft_server(raft_node, grpc_port)
    await grpc_server.start()
    logger.info(f"gRPC Raft Server iniciado en puerto {grpc_port}")

    discovery = initialize_discovery(
        health_check_interval=float(os.getenv("HEALTH_CHECK_INTERVAL", "5.0")),
        failure_threshold=int(os.getenv("FAILURE_THRESHOLD", "3"))
    )

    hash_ring = ConsistentHashRing(
        nodes=[this_node.id],
        virtual_nodes=int(os.getenv("VIRTUAL_NODES", "150"))
    )

    discovery.add_node(this_node)

    await discovery.start()
    logger.info("Service Discovery iniciado (modo dinamico)")

    lock_manager = initialize_lock_manager(
        raft_node=raft_node,
        node_id=settings.NODE_ID
    )
    logger.info("Distributed Locks inicializado")

    event_queue = initialize_event_queue(
        raft_node=raft_node,
        node_id=settings.NODE_ID,
        use_raft=os.getenv("USE_RAFT_FOR_EVENTS", "true").lower() == "true"
    )
    await event_queue.start()
    logger.info("Event Queue iniciado")

    replication_manager = initialize_replication_manager(
        raft_node=raft_node,
        node_id=settings.NODE_ID,
        storage_path=Path(settings.UPLOAD_DIR),
        hash_ring=hash_ring,
        replication_factor=int(os.getenv("REPLICATION_FACTOR", "3"))
    )
    await replication_manager.start()
    logger.info("File Replication Manager iniciado")

    bootstrap_service = os.getenv("BOOTSTRAP_SERVICE")
    if bootstrap_service:
        logger.info(f"Iniciando bootstrap DNS con servicio: {bootstrap_service}")

        from app.distributed.bootstrap import DNSBootstrap
        bootstrap = DNSBootstrap(
            service_name=bootstrap_service,
            port=this_node.port
        )

        peers = await bootstrap.discover_peers()

        if peers:
            logger.info(f"Bootstrap descubrio {len(peers)} peers potenciales")

            leader = await bootstrap.find_leader(peers)

            if leader:
                logger.info(f"Intentando registrarse con lider {leader.id}")
                success, cluster_nodes = await bootstrap.register_with_leader(leader, this_node)

                if success and cluster_nodes:
                    logger.info(f"Registro exitoso. Cluster tiene {len(cluster_nodes)} nodos")

                    for node_info in cluster_nodes:
                        if node_info["id"] != this_node.id:
                            peer_node = NodeInfo(
                                id=node_info["id"],
                                address=node_info["address"],
                                port=node_info["port"]
                            )
                            discovery.add_node(peer_node)
                            raft_node.add_cluster_node(peer_node)
                            hash_ring.add_node(peer_node.id)

                    logger.info("Nodos del cluster agregados localmente")
                else:
                    logger.warning("Fallo en registro con lider")
            else:
                logger.info("No se encontro lider, este nodo podria ser el primero del cluster")
        else:
            logger.info("No se descubrieron peers via DNS, modo standalone")
    else:
        logger.info("BOOTSTRAP_SERVICE no configurado, modo standalone")

    logger.info("Sistema distribuido iniciado correctamente")
    logger.info(f"   - Nodo: {settings.NODE_ID}")
    logger.info(f"   - Address: {this_node.address}:{this_node.port}")
    logger.info(f"   - Modo: Descubrimiento Dinamico")
    logger.info(f"   - Raft term: {raft_node.current_term}")
    logger.info(f"   - Nodos conocidos: {discovery.get_cluster_size()}")

    app.state.grpc_client = grpc_client
    app.state.grpc_server = grpc_server
    app.state.raft_node = raft_node
    app.state.discovery = discovery
    app.state.lock_manager = lock_manager
    app.state.event_queue = event_queue
    app.state.replication_manager = replication_manager
    app.state.hash_ring = hash_ring
    app.state.this_node = this_node

    yield

    logger.info("Deteniendo sistema distribuido...")

    await replication_manager.stop()
    await event_queue.stop()
    await discovery.stop()
    await grpc_server.stop()
    await raft_node.stop()
    await grpc_client.stop()

    logger.info("Sistema distribuido detenido")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

music_dir = Path(settings.UPLOAD_DIR)
music_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/music", StaticFiles(directory=str(music_dir)), name="music")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(music.router, prefix=settings.API_PREFIX)
app.include_router(distributed.router, prefix=f"{settings.API_PREFIX}/distributed")
app.include_router(internal.router)


@app.get("/")
def root():
    return {
        "message": "Dispotify API - Sistema Distribuido",
        "version": settings.VERSION,
        "distributed": True,
        "architecture": "Peer-to-Peer (gRPC Communication)",
        "features": [
            "Raft Consensus",
            "Leader Election via gRPC",
            "Log Replication via gRPC",
            "File Replication",
            "Consistent Hashing",
            "Tolerancia a Fallos con Quorum"
        ]
    }


@app.get("/health")
async def health():
    try:
        raft_node = get_raft_node()
        return {
            "status": "healthy",
            "service": "api-service",
            "node_id": settings.NODE_ID,
            "version": settings.VERSION,
            "raft": {
                "state": raft_node.state.value,
                "term": raft_node.current_term,
                "leader_id": raft_node.leader_id
            }
        }
    except:
        return {
            "status": "healthy",
            "service": "api-service",
            "node_id": settings.NODE_ID,
            "version": settings.VERSION
        }

