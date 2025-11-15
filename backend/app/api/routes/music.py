from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.schemas.music import MusicCreate, MusicResponse, MusicUpdate
from app.services.music_service import MusicService
from app.utils.file_handler import FileHandler
from pathlib import Path

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
    # Guardar el archivo físicamente
    file_path, file_size = await FileHandler.save_file(file)
    
    try:
        # Generar la URL basada en el nombre del archivo
        filename = Path(file_path).name
        url = f"/static/music/{filename}"
        
        # Crear el registro en la base de datos
        music_data = MusicCreate(
            nombre=nombre,
            autor=autor,
            album=album,
            genero=genero
        )
        music = MusicService.create_music(db, music_data, url, file_size)
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

    # Extraer el nombre del archivo de la URL y construir la ruta completa
    filename = Path(music.url).name
    file_path = Path("./music_files") / filename
    
    # Eliminar el archivo físico
    FileHandler.delete_file(str(file_path))
    
    # Eliminar el registro de la base de datos
    MusicService.delete_music(db, music_id)