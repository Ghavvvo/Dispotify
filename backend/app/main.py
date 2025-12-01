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

from app.distributed.communication import (
    P2PClient,
    NodeInfo,
    initialize_p2p_client,
    parse_cluster_nodes
)
from app.distributed.raft import (
    RaftNode,
    initialize_raft,
    get_raft_node
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
    logger.info("Iniciando sistema distribuido ...")

    cluster_nodes_str = os.getenv("CLUSTER_NODES", "")
    if not cluster_nodes_str:
        logger.warning("CLUSTER_NODES no configurado, modo standalone")
        cluster_nodes = [NodeInfo(
            id=settings.NODE_ID,
            address=os.getenv("NODE_ADDRESS", "localhost"),
            port=int(os.getenv("NODE_PORT", "8000"))
        )]
    else:
        cluster_nodes = parse_cluster_nodes(cluster_nodes_str)

    logger.info(f"Cluster configurado con {len(cluster_nodes)} nodos")

    this_node = next((n for n in cluster_nodes if n.id == settings.NODE_ID), None)
    if not this_node:
        this_node = NodeInfo(
            id=settings.NODE_ID,
            address=os.getenv("NODE_ADDRESS", "localhost"),
            port=int(os.getenv("NODE_PORT", "8000"))
        )
        logger.warning(f"Este nodo ({settings.NODE_ID}) no está en CLUSTER_NODES")

    p2p_client = initialize_p2p_client(timeout=5.0, max_retries=3)
    await p2p_client.start()
    logger.info("P2P HTTP Client iniciado")

    raft_node = initialize_raft(
        node_id=settings.NODE_ID,
        node_info=this_node,
        cluster_nodes=cluster_nodes,
        data_dir=os.getenv("RAFT_DATA_DIR", "/data/raft"),
        election_timeout_min=float(os.getenv("RAFT_ELECTION_TIMEOUT_MIN", "1.5")),
        election_timeout_max=float(os.getenv("RAFT_ELECTION_TIMEOUT_MAX", "3.0")),
        heartbeat_interval=float(os.getenv("RAFT_HEARTBEAT_INTERVAL", "0.5"))
    )

    async def on_become_leader():
        logger.info("Este nodo se convirtió en LÍDER del cluster (")

    async def on_lose_leadership():
        logger.info("Este nodo dejó de ser líder ")

    async def on_command_applied(command: dict):
        logger.debug(f"Comando aplicado: {command.get('type')}")

    raft_node.set_callbacks(
        on_become_leader=on_become_leader,
        on_lose_leadership=on_lose_leadership,
        on_command_applied=on_command_applied
    )

    await raft_node.start()
    logger.info(
        f"Raft Node iniciado "
        f"(term={raft_node.current_term}, cluster_size={len(cluster_nodes)})"
    )

    discovery = initialize_discovery(
        cluster_nodes=cluster_nodes,
        health_check_interval=float(os.getenv("HEALTH_CHECK_INTERVAL", "5.0")),
        failure_threshold=int(os.getenv("FAILURE_THRESHOLD", "3"))
    )
    await discovery.start()
    logger.info("Service Discovery iniciado")

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

    node_ids = [n.id for n in cluster_nodes]
    hash_ring = ConsistentHashRing(
        nodes=node_ids,
        virtual_nodes=int(os.getenv("VIRTUAL_NODES", "150"))
    )
    logger.info(f"Consistent Hash Ring inicializado con {len(node_ids)} nodos")

    replication_manager = initialize_replication_manager(
        raft_node=raft_node,
        node_id=settings.NODE_ID,
        storage_path=Path(settings.UPLOAD_DIR),
        hash_ring=hash_ring,
        replication_factor=int(os.getenv("REPLICATION_FACTOR", "3"))
    )
    await replication_manager.start()
    logger.info("File Replication Manager iniciado")

    logger.info(" Sistema distribuido  iniciado correctamente")
    logger.info(f"   - Nodo: {settings.NODE_ID}")
    logger.info(f"   - Address: {this_node.address}:{this_node.port}")
    logger.info(f"   - Cluster size: {len(cluster_nodes)}")
    logger.info(f"   - Raft term: {raft_node.current_term}")
    logger.info(f"   - Nodos vivos: {discovery.get_alive_count()}/{len(cluster_nodes)}")

    app.state.p2p_client = p2p_client
    app.state.raft_node = raft_node
    app.state.discovery = discovery
    app.state.lock_manager = lock_manager
    app.state.event_queue = event_queue
    app.state.replication_manager = replication_manager
    app.state.hash_ring = hash_ring
    app.state.cluster_nodes = cluster_nodes

    yield

    logger.info(" Deteniendo sistema distribuido ...")

    await replication_manager.stop()
    await event_queue.stop()
    await discovery.stop()
    await raft_node.stop()
    await p2p_client.stop()

    logger.info("Sistema distribuido  detenido")


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
        "architecture": "Peer-to-Peer (HTTP Direct Communication)",
        "features": [
            "Raft Consensus",
            "Leader Election via HTTP",
            "Log Replication via HTTP",
            "File Replication ",
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

