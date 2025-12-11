from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager
import logging
import os

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.models.music import Music
from app.api.routes import music
from app.api.routes import distributed
from app.api.routes import internal

from app.distributed.communication import (
    P2PClient,
    NodeInfo,
    initialize_p2p_client
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
    logger.info("Iniciando sistema distribuido con descubrimiento dinámico...")

    # Crear tablas de base de datos si no existen
    logger.info("Inicializando base de datos...")
    Base.metadata.create_all(bind=engine)
    logger.info("Base de datos inicializada")

    this_node = NodeInfo(
        id=settings.NODE_ID,
        address=settings.NODE_ADDRESS,
        port=settings.NODE_PORT
    )
    logger.info(f"Nodo local: {this_node.id} @ {this_node.address}:{this_node.port}")

    p2p_client = initialize_p2p_client(timeout=5.0, max_retries=3)
    await p2p_client.start()
    logger.info("P2P HTTP Client iniciado")

    raft_node = initialize_raft(
        node_id=settings.NODE_ID,
        node_info=this_node,
        cluster_nodes=None,
        data_dir=settings.RAFT_DATA_DIR,  # Temporal, se pierde al reiniciar
        election_timeout_min=settings.RAFT_ELECTION_TIMEOUT_MIN,  # 150ms
        election_timeout_max=settings.RAFT_ELECTION_TIMEOUT_MAX,  # 300ms
        heartbeat_interval=settings.RAFT_HEARTBEAT_INTERVAL,      # 100ms
        solo_mode_timeout=settings.SOLO_MODE_TIMEOUT,            # 15s
        recovery_grace_period=settings.RECOVERY_GRACE_PERIOD     # 30s
    )

    discovery = None
    hash_ring = None

    async def on_become_leader():
        logger.info("Este nodo se convirtio en LIDER del cluster")

    async def on_lose_leadership():
        logger.info("Este nodo dejo de ser lider")

    async def on_mode_change(new_mode):
        """Callback cuando cambia el modo operativo del nodo"""
        from app.distributed.raft import OperationalMode

        if new_mode == OperationalMode.SOLITARIO:
            logger.warning(
                "⚠️  MODO SOLITARIO ACTIVADO - El nodo está completamente aislado. "
                "Las escrituras se aceptarán pero NO tienen garantías de durabilidad "
                "hasta reconectarse con el cluster."
            )
        elif new_mode == OperationalMode.COOPERATIVO:
            logger.info(
                "✓ MODO COOPERATIVO - El nodo está conectado con otros nodos. "
                "Operación normal con consenso distribuido."
            )
        elif new_mode == OperationalMode.RECUPERACION:
            logger.info(
                "↻ MODO RECUPERACION - Recuperando estado desde otros nodos..."
            )

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

        elif cmd_type == "create_music":
            try:
                db = SessionLocal()
                try:
                    existing = db.query(Music).filter(
                        Music.url == command.get("url")
                    ).first()

                    if not existing:
                        new_music = Music(
                            nombre=command.get("nombre"),
                            autor=command.get("autor"),
                            album=command.get("album"),
                            genero=command.get("genero"),
                            url=command.get("url"),
                            file_size=command.get("file_size")
                        )
                        db.add(new_music)
                        db.commit()
                        logger.info(f"Musica creada en BD local: {command.get('nombre')}")
                    else:
                        logger.debug(f"Musica ya existe en BD local: {command.get('url')}")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Error aplicando create_music a BD local: {e}")

        elif cmd_type == "delete_music":
            try:
                db = SessionLocal()
                try:
                    music_record = db.query(Music).filter(
                        Music.id == command.get("music_id")
                    ).first()

                    if music_record:
                        db.delete(music_record)
                        db.commit()
                        logger.info(f"Musica eliminada de BD local: {command.get('music_id')}")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Error aplicando delete_music a BD local: {e}")

    raft_node.set_callbacks(
        on_become_leader=on_become_leader,
        on_lose_leadership=on_lose_leadership,
        on_command_applied=on_command_applied,
        on_mode_change=on_mode_change
    )

    await raft_node.start()
    logger.info(f"Raft Node iniciado (term={raft_node.current_term})")

    discovery = initialize_discovery(
        health_check_interval=float(os.getenv("HEALTH_CHECK_INTERVAL", "5.0")),
        failure_threshold=int(os.getenv("FAILURE_THRESHOLD", "3"))
    )

    hash_ring = ConsistentHashRing(
        nodes=[this_node.id],
        virtual_nodes=settings.VIRTUAL_NODES
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
        replication_factor=settings.REPLICATION_FACTOR
    )
    await replication_manager.start()
    logger.info("File Replication Manager iniciado")

    bootstrap_service = settings.BOOTSTRAP_SERVICE
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

    app.state.p2p_client = p2p_client
    app.state.raft_node = raft_node
    app.state.discovery = discovery
    app.state.lock_manager = lock_manager
    app.state.event_queue = event_queue
    app.state.replication_manager = replication_manager
    app.state.hash_ring = hash_ring
    app.state.this_node = this_node

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

