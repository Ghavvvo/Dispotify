from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.routes import internal, music, cluster
from app.distributed.raft import get_raft_node
from app.distributed.replication import get_replication_manager
# Import models to ensure they are registered with SQLAlchemy
from app.models import music as music_model
import logging
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json"
)

# Mount static files
app.mount("/static/music", StaticFiles(directory=settings.UPLOAD_DIR), name="music")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(internal.router)
app.include_router(cluster.router)
app.include_router(music.router, prefix=f"{settings.API_PREFIX}")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Dispotify Node...")
    
    # Initialize Database
    init_db()
    
    # Initialize Raft
    raft_node = get_raft_node()
    await raft_node.start()
    
    # Initialize Replication
    replication_manager = get_replication_manager()
    
    # Inject into app state for easy access if needed
    app.state.raft_node = raft_node
    app.state.replication_manager = replication_manager

@app.get("/")
def root():
    return {
        "message": "Dispotify API - Sistema Distribuido Simplificado",
        "version": settings.VERSION,
        "distributed": True,
        "status": "running",
        "node_id": get_raft_node().node_id
    }
