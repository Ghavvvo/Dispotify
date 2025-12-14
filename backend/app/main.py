from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.routes import internal, music, cluster
from app.distributed.raft import get_raft_node
from app.distributed.replication import get_replication_manager
# Import models to ensure they are registered with SQLAlchemy
from app.models import music as music_model
import logging
import os
import socket

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
# Ensure data directory exists for SQLite
os.makedirs("./data", exist_ok=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json"
)

# Middleware to add node information to response headers
class NodeInfoMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Get node information
        node_id = settings.NODE_ID
        
        # Get container hostname (which is the container name in Docker)
        hostname = socket.gethostname()
        
        # Get container IP address
        try:
            container_ip = socket.gethostbyname(hostname)
        except:
            container_ip = "unknown"
        
        # Get the port from environment or default
        port = os.getenv("PORT", "8000")
        
        # Add custom headers with node information
        response.headers["X-Node-ID"] = node_id
        response.headers["X-Node-Hostname"] = hostname
        response.headers["X-Node-IP"] = container_ip
        response.headers["X-Node-Port"] = port
        
        return response

# Mount static files
app.mount("/static/music", StaticFiles(directory=settings.UPLOAD_DIR), name="music")

# Add Node Info Middleware
app.add_middleware(NodeInfoMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Node-ID", "X-Node-Hostname", "X-Node-IP", "X-Node-Port"],
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
