import logging
from app.core.database import SessionLocal
from app.services.music_service import MusicService
from app.schemas.music import MusicCreate
from app.models.music import Music

logger = logging.getLogger(__name__)

class StateMachine:
    def apply(self, command: dict):
        cmd_type = command.get("type")
        if cmd_type == "create_music":
            self._apply_create_music(command)
        else:
            logger.warning(f"Unknown command type: {cmd_type}")

    def _apply_create_music(self, command: dict):
        db = SessionLocal()
        try:
            # Check if already exists by URL to ensure idempotency
            existing = db.query(Music).filter(Music.url == command["url"]).first()
            if existing:
                logger.info(f"Music already exists (skipping): {command['url']}")
                return

            music_data = MusicCreate(
                nombre=command["nombre"],
                autor=command["autor"],
                album=command.get("album"),
                genero=command.get("genero")
            )

            MusicService.create_music(
                db, 
                music_data, 
                url=command["url"], 
                file_size=command["file_size"],
                partition_id=command.get("partition_id"),
                epoch_number=command.get("epoch_number"),
                conflict_flag=command.get("conflict_flag"),
                merge_timestamp=command.get("merge_timestamp")
            )
            logger.info(f"Applied create_music command: {command['nombre']}")
        except Exception as e:
            logger.error(f"Error applying create_music: {e}")
        finally:
            db.close()
