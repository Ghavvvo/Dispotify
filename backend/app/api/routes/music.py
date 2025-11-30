from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
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
                if getattr(raft_node, "is_leader", None) and raft_node.is_leader():
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
                else:
                    logger.info("Nodo no líder: se omitió replicación en upload")
        except Exception as rep_e:
            logger.error(f"Error replicando archivo tras upload: {rep_e}")

        return music
    except Exception as e:
        FileHandler.delete_file(file_path)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[MusicResponse])
def list_music(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        db: Session = Depends(get_db)
):
    return MusicService.get_all_music(db, skip, limit)

@router.get("/search", response_model=List[MusicResponse])
def search_music(
        q: Optional[str] = Query(None, description="Search query"),
        genero: Optional[str] = None,
        autor: Optional[str] = None,
        album: Optional[str] = None,
        db: Session = Depends(get_db)
):
    return MusicService.search_music(db, q or "", genero, autor, album)

@router.get("/{music_id}", response_model=MusicResponse)
def get_music(music_id: int, db: Session = Depends(get_db)):
    music = MusicService.get_music_by_id(db, music_id)
    if not music:
        raise HTTPException(status_code=404, detail="Music not found")
    return music

@router.delete("/{music_id}", status_code=204)
def delete_music(music_id: int, db: Session = Depends(get_db)):
    music = MusicService.get_music_by_id(db, music_id)
    if not music:
        raise HTTPException(status_code=404, detail="Music not found")

    filename = Path(music.url).name
    file_path = Path("./music_files") / filename

    FileHandler.delete_file(str(file_path))

    MusicService.delete_music(db, music_id)