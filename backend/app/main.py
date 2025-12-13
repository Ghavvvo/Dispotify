from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager
import logging
import os

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.models.music import Music
from app.api.routes import music
from app.api.routes import distributed
from app.api.routes import internal

from app.distributed.communication import (
    NodeInfo,
    initialize_p2p_client
)
from app.distributed.raft import (
    OperationalMode,
    initialize_raft,
    get_raft_node
)
from app.distributed.replication import (
    initialize_replication_manager
)
from app.distributed.consistent_hash import ConsistentHashRing
from app.distributed.bootstrap import DNSBootstrap

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def resolve_node_address() -> str:
    # Use container name for communication in overlay network
    node_id = os.getenv("NODE_ID", "node-1")
    container_name = f"dispotify-backend-{node_id.split('-')[1]}"
    logger.info(f"Resolved node address to container name: {container_name}")
    return container_name


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando sistema distribuido simplificado...")

    node_address = resolve_node_address()
    node_port = int(os.getenv("NODE_PORT", "8000"))
    this_node = NodeInfo(
        id=settings.NODE_ID,
        address=node_address,
        port=node_port
    )
    logger.info(f"Nodo local: {this_node.id} @ {this_node.address}:{this_node.port}")

    # 1. Inicializar P2P Client
    p2p_client = initialize_p2p_client(timeout=5.0, max_retries=3)
    await p2p_client.start()
    logger.info("P2P HTTP Client iniciado")

    # 2. Descubrir peers iniciales via DNS
    cluster_nodes = []
    bootstrap_service = os.getenv("BOOTSTRAP_SERVICE")
    if bootstrap_service:
        logger.info(f"Buscando peers via DNS en servicio: {bootstrap_service}")
        bootstrap = DNSBootstrap(service_name=bootstrap_service, port=node_port)
        peers = await bootstrap.discover_peers()
        # Filtrar nodo local
        cluster_nodes = [p for p in peers if p.id != this_node.id]
        logger.info(f"Peers iniciales encontrados: {len(cluster_nodes)}")

    # 3. Inicializar Raft Node
    raft_node = initialize_raft(
        node_id=settings.NODE_ID,
        node_info=this_node,
        cluster_nodes=cluster_nodes,
        data_dir=os.getenv("RAFT_DATA_DIR", "/data/raft"),
        election_timeout_min=float(os.getenv("RAFT_ELECTION_TIMEOUT_MIN", "1.5")),
        election_timeout_max=float(os.getenv("RAFT_ELECTION_TIMEOUT_MAX", "3.0")),
        heartbeat_interval=float(os.getenv("RAFT_HEARTBEAT_INTERVAL", "0.5"))
    )

    # 4. Inicializar Hash Ring
    # Inicialmente solo con nosotros y los peers conocidos via DNS
    initial_ring_nodes = [this_node.id] + [n.id for n in cluster_nodes]
    hash_ring = ConsistentHashRing(
        nodes=initial_ring_nodes,
        virtual_nodes=int(os.getenv("VIRTUAL_NODES", "150"))
    )

    # Callbacks de Raft
    async def on_become_leader():
        logger.info("Este nodo se convirtio en LIDER del cluster")

    async def on_lose_leadership():
        logger.info("Este nodo dejo de ser lider")

    async def on_command_applied(command: dict):
        cmd_type = command.get("type")

        if cmd_type == "add_node":
            node_id = command.get("node_id")
            if node_id:
                hash_ring.add_node(node_id)
                logger.info(f"Nodo agregado al anillo: {node_id}")
                
                # Si estábamos en SOLO y ahora hay más nodos, cambiar modo
                if raft_node.operational_mode == OperationalMode.SOLO and len(raft_node.cluster_nodes) > 0:
                    raft_node.operational_mode = OperationalMode.PARTITION_LEADER
                    logger.info("Cambiando de modo SOLO a PARTITION_LEADER")

        elif cmd_type == "remove_node":
            node_id = command.get("node_id")
            if node_id:
                hash_ring.remove_node(node_id)
                logger.info(f"Nodo eliminado del anillo: {node_id}")

        elif cmd_type == "create_music":
            try:
                db = SessionLocal()
                try:
                    existing = db.query(Music).filter(Music.url == command.get("url")).first()
                    if not existing:
                        new_music = Music(
                            nombre=command.get("nombre"),
                            autor=command.get("autor"),
                            album=command.get("album"),
                            genero=command.get("genero"),
                            url=command.get("url"),
                            file_size=command.get("file_size"),
                            partition_id=command.get("partition_id"),
                            epoch_number=command.get("epoch_number"),
                            conflict_flag=command.get("conflict_flag"),
                            merge_timestamp=command.get("merge_timestamp")
                        )
                        db.add(new_music)
                        db.commit()
                        logger.info(f"Musica creada en BD local: {command.get('nombre')}")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Error aplicando create_music: {e}")

        elif cmd_type == "delete_music":
            try:
                db = SessionLocal()
                try:
                    music_record = db.query(Music).filter(Music.id == command.get("music_id")).first()
                    if music_record:
                        db.delete(music_record)
                        db.commit()
                        logger.info(f"Musica eliminada de BD local: {command.get('music_id')}")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Error aplicando delete_music: {e}")

    raft_node.set_callbacks(
        on_become_leader=on_become_leader,
        on_lose_leadership=on_lose_leadership,
        on_command_applied=on_command_applied
    )

    # 5. Iniciar Raft
    await raft_node.start()
    logger.info(f"Raft Node iniciado (term={raft_node.current_term})")

    # 6. Inicializar Replication Manager
    replication_manager = initialize_replication_manager(
        raft_node=raft_node,
        node_id=settings.NODE_ID,
        storage_path=Path(settings.UPLOAD_DIR),
        hash_ring=hash_ring,
        replication_factor=int(os.getenv("REPLICATION_FACTOR", "3"))
    )
    await replication_manager.start()
    logger.info("File Replication Manager iniciado")

    # Inicializar DB
    data_dir = Path("./data")
    data_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    # Guardar estado en app
    app.state.p2p_client = p2p_client
    app.state.raft_node = raft_node
    app.state.replication_manager = replication_manager
    app.state.hash_ring = hash_ring
    app.state.this_node = this_node
    # Compatibilidad con endpoints existentes que esperaban cluster_nodes en state
    app.state.cluster_nodes = raft_node.cluster_nodes 

    yield

    logger.info("Deteniendo sistema distribuido...")
    await replication_manager.stop()
    await raft_node.stop()
    await p2p_client.stop()
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
app.include_router(distributed.router, prefix="/distributed")
app.include_router(internal.router)


@app.get("/")
def root():
    return {
        "message": "Dispotify API - Sistema Distribuido Simplificado",
        "version": settings.VERSION,
        "distributed": True,
        "status": "running"
    }


@app.get("/health")
async def health():
    try:
        raft_node = get_raft_node()
        return {
            "status": "healthy",
            "node_id": settings.NODE_ID,
            "raft_state": raft_node.state.value,
            "leader_id": raft_node.leader_id
        }
    except:
        return {"status": "unhealthy"}
