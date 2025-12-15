from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.routes import internal, music, cluster
from app.distributed.raft import get_raft_node
from app.distributed.replication import get_replication_manager

from app.models import music as music_model
import logging
import os
import socket


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

os.makedirs("./data", exist_ok=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json"
)


class NodeInfoMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        
        node_id = settings.NODE_ID
        
        
        hostname = socket.gethostname()
        
        
        try:
            container_ip = socket.gethostbyname(hostname)
        except:
            container_ip = "unknown"
        
        
        port = os.getenv("PORT", "8000")
        
        
        response.headers["X-Node-ID"] = node_id
        response.headers["X-Node-Hostname"] = hostname
        response.headers["X-Node-IP"] = container_ip
        response.headers["X-Node-Port"] = port
        
        return response


app.mount("/static/music", StaticFiles(directory=settings.UPLOAD_DIR), name="music")


app.add_middleware(NodeInfoMiddleware)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Node-ID", "X-Node-Hostname", "X-Node-IP", "X-Node-Port"],
)


app.include_router(internal.router)
app.include_router(cluster.router)
app.include_router(music.router, prefix=f"{settings.API_PREFIX}")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Dispotify Node...")
    
    
    init_db()
    
    
    raft_node = get_raft_node()
    await raft_node.start()
    
    
    replication_manager = get_replication_manager()
    
    
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
