from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.schemas.music import MusicCreate, MusicResponse, MusicUpdate
from app.services.music_service import MusicService
from app.models.music import Music
from app.utils.file_handler import FileHandler
from app.distributed.communication import get_p2p_client, P2PException
from pathlib import Path
import logging
import time

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
    raft_node = None
    if request and hasattr(request.app.state, "raft_node"):
        raft_node = request.app.state.raft_node

        if not raft_node.is_leader():
            leader_id = raft_node.get_leader()

            if not leader_id:
                raise HTTPException(
                    status_code=503,
                    detail="No hay líder disponible en el cluster"
                )

            leader_node = None
            if leader_id in raft_node.peers:
                leader_node = raft_node.peers[leader_id]
            
            
            if not leader_node and leader_id == raft_node.node_id:
                 
                 pass

            if not leader_node:
                raise HTTPException(
                    status_code=503,
                    detail=f"No se puede contactar al líder: {leader_id}"
                )

            file_content = await file.read()

            try:
                p2p_client = get_p2p_client()
                response = await p2p_client.forward_upload(
                    node=leader_node,
                    endpoint="/api/v1/music/upload",
                    file_content=file_content,
                    filename=file.filename,
                    form_data={
                        "nombre": nombre,
                        "autor": autor,
                        "album": album,
                        "genero": genero
                    }
                )

                return JSONResponse(
                    status_code=response["status"],
                    content=response["data"]
                )

            except P2PException as e:
                logger.error(f"Error en forward al líder {leader_id}: {e}")
                raise HTTPException(
                    status_code=503,
                    detail=f"Error al comunicarse con el líder: {str(e)}"
                )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo requerido")

    allowed_extensions = [".mp3", ".wav", ".flac", ".ogg"]
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado. Permitidos: {allowed_extensions}"
        )

    file_path, file_size, file_hash = await FileHandler.save_file(file)
    filename = Path(file_path).name
    url = f"/static/music/{filename}"

    existing_file = db.query(Music).filter(Music.file_hash == file_hash).first()
    if existing_file:
        FileHandler.delete_file(file_path)
        raise HTTPException(status_code=400, detail="Duplicate MP3 file detected")

    existing_song = db.query(Music).filter(Music.nombre == nombre, Music.autor == autor).first()
    if existing_song:
        FileHandler.delete_file(file_path)
        raise HTTPException(status_code=400, detail="Song with same name and author already exists")

    try:
        if raft_node:
            metadata_command = {
                "type": "create_music",
                "nombre": nombre,
                "autor": autor,
                "album": album,
                "genero": genero,
                "url": url,
                "file_size": file_size,
                "file_hash": file_hash,
                "filename": filename,
                "partition_id": raft_node.partition_id,
                "epoch_number": raft_node.epoch_number,
                "conflict_flag": None,
                "merge_timestamp": time.time()
            }

            success = await raft_node.submit_command(metadata_command, timeout=10.0)

            if not success:
                FileHandler.delete_file(file_path)
                raise HTTPException(
                    status_code=503,
                    detail="No se pudo alcanzar consenso en el cluster para los metadatos"
                )

            logger.info(f"Consenso Raft alcanzado para: {filename}")

            if hasattr(request.app.state, "replication_manager"):
                replication_manager = request.app.state.replication_manager
                try:
                    await replication_manager.replicate_file(
                        file_id=filename,
                        file_path=Path(file_path),
                        metadata={
                            "url": url,
                            "nombre": nombre,
                            "autor": autor,
                            "album": album,
                            "genero": genero,
                            "partition_id": raft_node.partition_id,
                            "epoch_number": raft_node.epoch_number
                        }
                    )
                except Exception as rep_e:
                    logger.warning(f"Replicacion de archivo parcial: {rep_e}")

        else:
            music_data = MusicCreate(
                nombre=nombre,
                autor=autor,
                album=album,
                genero=genero
            )
            music = MusicService.create_music(db, music_data, url, file_size, file_hash=file_hash)
            return music

        music = db.query(Music).filter(Music.url == url).first()

        if not music:
            music_data = MusicCreate(
                nombre=nombre,
                autor=autor,
                album=album,
                genero=genero
            )
            music = MusicService.create_music(db, music_data, url, file_size, file_hash=file_hash)

        return music

    except HTTPException:
        raise
    except Exception as e:
        FileHandler.delete_file(file_path)
        logger.error(f"Error en upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[MusicResponse])
async def list_music(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        q: Optional[str] = Query(None, description="Búsqueda general por nombre, autor o álbum"),
        genero: Optional[str] = Query(None, description="Filtrar por género"),
        autor: Optional[str] = Query(None, description="Filtrar por autor"),
        album: Optional[str] = Query(None, description="Filtrar por álbum"),
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

    
    if q or genero or autor or album:
        return MusicService.search_music(db, q or "", genero, autor, album)
    
    
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
