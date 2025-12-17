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
            existing = db.query(Music).filter(Music.url == command["url"]).first()
            if existing:
                logger.info(f"Music already exists (skipping): {command['url']}")
                return

            conflict_flags = []
            file_hash = command.get("file_hash")
            conflicting_songs = []

            if file_hash:
                dup_hash = db.query(Music).filter(Music.file_hash == file_hash).first()
                if dup_hash:
                    conflict_flags.append("DUPLICATE_FILE_HASH")
                    conflicting_songs.append(dup_hash)
                    logger.info(f"[CONFLICT] Detected DUPLICATE_FILE_HASH: {command['nombre']} conflicts with {dup_hash.nombre} (ID: {dup_hash.id})")

            dup_meta = db.query(Music).filter(
                Music.nombre == command["nombre"],
                Music.autor == command["autor"]
            ).first()
            if dup_meta:
                conflict_flags.append("DUPLICATE_METADATA")
                if dup_meta not in conflicting_songs:
                    conflicting_songs.append(dup_meta)
                logger.info(f"[CONFLICT] Detected DUPLICATE_METADATA: {command['nombre']} conflicts with existing song (ID: {dup_meta.id})")

            conflict_flag = ";".join(conflict_flags) if conflict_flags else None

            if conflicting_songs:
                for existing_song in conflicting_songs:
                    existing_conflicts = []
                    
                    if file_hash and existing_song.file_hash == file_hash:
                        existing_conflicts.append("DUPLICATE_FILE_HASH")
                    
                    if existing_song.nombre == command["nombre"] and existing_song.autor == command["autor"]:
                        existing_conflicts.append("DUPLICATE_METADATA")
                    
                    new_conflict_flag = ";".join(existing_conflicts)
                    
                    if existing_song.conflict_flag:
                        existing_flags = set(existing_song.conflict_flag.split(";"))
                        new_flags = set(existing_conflicts)
                        combined_flags = existing_flags.union(new_flags)
                        new_conflict_flag = ";".join(sorted(combined_flags))
                    
                    existing_song.conflict_flag = new_conflict_flag
                    existing_song.merge_timestamp = command.get("merge_timestamp")
                    db.commit()
                    logger.info(f"[CONFLICT] Marked existing song '{existing_song.nombre}' (ID: {existing_song.id}) with conflicts: {new_conflict_flag}")

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
                file_hash=file_hash,
                partition_id=command.get("partition_id"),
                epoch_number=command.get("epoch_number"),
                conflict_flag=conflict_flag,
                merge_timestamp=command.get("merge_timestamp")
            )
            logger.info(f"[CONFLICT] Applied create_music command: {command['nombre']} with conflicts: {conflict_flag}")
        except Exception as e:
            logger.error(f"Error applying create_music: {e}")
        finally:
            db.close()
