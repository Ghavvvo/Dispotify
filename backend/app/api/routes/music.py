from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.schemas.music import MusicCreate, MusicResponse, MusicUpdate
from app.services.music_service import MusicService
from app.utils.file_handler import FileHandler
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/music", tags=["Music"])

@router.post("/upload", response_model=MusicResponse, status_code=201)
async def upload_music(
        nombre: str = Form(...),
        autor: str = Form(...),
        album: Optional[str] = Form(None),
        genero: Optional[str] = Form(None),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        request: Request = None
):
    if request and hasattr(request.app.state, "raft_node"):
        raft_node = request.app.state.raft_node
        if not raft_node.is_leader():
            leader_id = raft_node.get_leader()
            raise HTTPException(
                status_code=307,
                detail=f"Este nodo no es el líder. Redirigir a: {leader_id}",
                headers={"X-Leader-Id": leader_id or "unknown"}
            )

    file_path, file_size = await FileHandler.save_file(file)
    
    try:

        filename = Path(file_path).name
        url = f"/static/music/{filename}"

        music_data = MusicCreate(
            nombre=nombre,
            autor=autor,
            album=album,
            genero=genero
        )

        music = MusicService.create_music(db, music_data, url, file_size)
        try:
            if request and hasattr(request.app.state, "raft_node") and hasattr(request.app.state, "replication_manager"):
                raft_node = request.app.state.raft_node
                replication_manager = request.app.state.replication_manager

                await replication_manager.replicate_file(
                    file_id=filename,
                    file_path=Path(file_path),
                    metadata={
                        "db_id": getattr(music, "id", None),
                        "url": url,
                        "nombre": nombre,
                        "autor": autor
                    }
                )

                metadata_command = {
                    "type": "create_music",
                    "music_id": music.id,
                    "nombre": nombre,
                    "autor": autor,
                    "album": album,
                    "genero": genero,
                    "url": url,
                    "file_size": file_size,
                    "filename": filename
                }

                success = await raft_node.submit_command(metadata_command, timeout=10.0)
                if not success:
                    logger.warning(
                        f"Metadata de {filename} no alcanzó consenso Raft, "
                        f"pero el archivo fue replicado con quórum"
                    )
                else:
                    logger.info(f"Metadata de {filename} registrada en Raft con consenso")

        except Exception as rep_e:
            logger.error(f"Error en replicación/consenso tras upload: {rep_e}")
            MusicService.delete_music(db, music.id)
            FileHandler.delete_file(file_path)
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo garantizar la durabilidad del archivo: {str(rep_e)}"
            )

        return music
    except HTTPException:
        raise
    except Exception as e:
        FileHandler.delete_file(file_path)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[MusicResponse])
async def list_music(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        db: Session = Depends(get_db),
        request: Request = None
):

    if request and hasattr(request.app.state, "raft_node"):
        raft_node = request.app.state.raft_node
        if not raft_node.can_serve_read():
            raise HTTPException(
                status_code=503,
                detail="Nodo no disponible para lecturas."
            )
        read_status = raft_node.get_eventual_read_status()
        if read_status["lag"] > 0:
            logger.debug(
                f"Lectura eventual con lag={read_status['lag']} "
                f"(commit={read_status['commit_index']}, applied={read_status['last_applied']})"
            )

    return MusicService.get_all_music(db, skip, limit)

@router.get("/{music_id}", response_model=MusicResponse)
async def get_music(
        music_id: int,
        db: Session = Depends(get_db),
        request: Request = None
):

    if request and hasattr(request.app.state, "raft_node"):
        raft_node = request.app.state.raft_node
        if not raft_node.can_serve_read():
            raise HTTPException(
                status_code=503,
                detail="Nodo no disponible para lecturas"
            )

    music = MusicService.get_music_by_id(db, music_id)
    if not music:
        raise HTTPException(status_code=404, detail="Music not found")
    return music
