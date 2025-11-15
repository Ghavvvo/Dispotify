from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.core.config import settings
from app.core.database import engine, Base
from app.api.routes import music

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
)

# Crear directorio de música si no existe y montar archivos estáticos
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

@app.get("/")
def root():
    return {"message": "Music System API", "version": settings.VERSION}