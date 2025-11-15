from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

class MusicBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200, description="Nombre de la canción")
    autor: str = Field(..., min_length=1, max_length=200, description="Artista o autor")
    album: Optional[str] = Field(None, max_length=200, description="Nombre del álbum")
    genero: Optional[str] = Field(None, max_length=100, description="Género musical")

class MusicCreate(MusicBase):
    pass

class MusicUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    autor: Optional[str] = Field(None, min_length=1, max_length=200)
    album: Optional[str] = Field(None, max_length=200)
    genero: Optional[str] = Field(None, max_length=100)

class MusicResponse(MusicBase):
    id: int
    url: str
    duracion: Optional[float] = None
    file_size: Optional[int] = None
    format: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class MusicList(BaseModel):
    total: int
    items: list[MusicResponse]
    page: int
    page_size: int