from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "Dispotify"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql://admin:password@db:5435/dispotify"

    UPLOAD_DIR: str = "./music_files"
    MAX_FILE_SIZE: int = 100 * 1024 * 1024
    ALLOWED_EXTENSIONS: str = ".mp3,.wav,.flac,.ogg"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()