from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.schemas.music import MusicCreate, MusicResponse, MusicUpdate
from app.services.music_service import MusicService
from app.utils.file_handler import FileHandler

router = APIRouter(prefix="/music", tags=["Music"])

@router.post("/upload", response_model=MusicResponse, status_code=201)
async def upload_music(
        nombre: str,
        autor: str,
        album: Optional[str] = None,
        genero: Optional[str] = None,
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    file_path, file_size = await FileHandler.save_file(file)

    try:
        music_data = MusicCreate(
            nombre=nombre,
            autor=autor,
            album=album,
            genero=genero
        )
        music = MusicService.create_music(db, music_data, file_path, file_size)
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
        db: Session = Depends(get_db)
):
    return MusicService.search_music(db, q or "", genero, autor)

@router.get("/{music_id}", response_model=MusicResponse)
def get_music(music_id: int, db: Session = Depends(get_db)):
    music = MusicService.get_music_by_id(db, music_id)
    if not music:
        raise HTTPException(status_code=404, detail="Music not found")
    return music

@router.get("/{music_id}/stream")
def stream_music(music_id: int, db: Session = Depends(get_db)):
    music = MusicService.get_music_by_id(db, music_id)
    if not music:
        raise HTTPException(status_code=404, detail="Music not found")

    return FileResponse(
        music.file_path,
        media_type="audio/mpeg",
        filename=f"{music.nombre}.mp3"
    )

@router.delete("/{music_id}", status_code=204)
def delete_music(music_id: int, db: Session = Depends(get_db)):
    music = MusicService.get_music_by_id(db, music_id)
    if not music:
        raise HTTPException(status_code=404, detail="Music not found")

    FileHandler.delete_file(music.file_path)
    MusicService.delete_music(db, music_id)