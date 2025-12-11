from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Dispotify"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql://admin:password@db:5432/dispotify"
    NODE_ID: str = "node-1"

    # Node configuration
    NODE_ADDRESS: str = "localhost"
    NODE_PORT: int = 8000

    # Distributed system configuration
    VIRTUAL_NODES: int = 150
    REPLICATION_FACTOR: int = 2

    # Raft configuration
    RAFT_DATA_DIR: str = "/tmp/raft"
    RAFT_ELECTION_TIMEOUT_MIN: float = 0.15
    RAFT_ELECTION_TIMEOUT_MAX: float = 0.30
    RAFT_HEARTBEAT_INTERVAL: float = 0.1
    SOLO_MODE_TIMEOUT: float = 15.0
    RECOVERY_GRACE_PERIOD: float = 30.0

    # Bootstrap configuration
    BOOTSTRAP_SERVICE: str | None = None

    UPLOAD_DIR: str = "./music_files"
    MAX_FILE_SIZE: int = 100 * 1024 * 1024
    ALLOWED_EXTENSIONS: str = ".mp3,.wav,.flac,.ogg"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()