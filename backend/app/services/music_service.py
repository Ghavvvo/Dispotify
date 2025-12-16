from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from app.models.music import Music
from app.schemas.music import MusicCreate, MusicUpdate

class MusicService:
    @staticmethod
    def create_music(
            db: Session,
            music_data: MusicCreate,
            url: str,
            file_size: int,
            file_hash: str = None,
            partition_id: str = None,
            epoch_number: int = 0,
            conflict_flag: str = None,
            merge_timestamp: float = None
    ) -> Music:
        db_music = Music(
            **music_data.model_dump(),
            url=url,
            file_size=file_size,
            file_hash=file_hash,
            partition_id=partition_id,
            epoch_number=epoch_number,
            conflict_flag=conflict_flag,
            merge_timestamp=merge_timestamp
        )
        db.add(db_music)
        db.commit()
        db.refresh(db_music)
        return db_music

    @staticmethod
    def get_all_music(db: Session, skip: int = 0, limit: int = 100) -> List[Music]:
        return db.query(Music).offset(skip).limit(limit).all()

    @staticmethod
    def get_music_by_id(db: Session, music_id: int) -> Optional[Music]:
        return db.query(Music).filter(Music.id == music_id).first()

    @staticmethod
    def search_music(
            db: Session,
            query: str,
            genero: Optional[str] = None,
            autor: Optional[str] = None,
            album: Optional[str] = None
    ) -> List[Music]:
        filters = []

        if query:
            filters.append(
                or_(
                    Music.nombre.ilike(f"%{query}%"),
                    Music.autor.ilike(f"%{query}%"),
                    Music.album.ilike(f"%{query}%")
                )
            )

        if genero:
            filters.append(Music.genero.ilike(f"%{genero}%"))

        if autor:
            filters.append(Music.autor.ilike(f"%{autor}%"))

        if album:
            filters.append(Music.album.ilike(f"%{album}%"))

        query_obj = db.query(Music)
        for filter_condition in filters:
            query_obj = query_obj.filter(filter_condition)

        return query_obj.all()

    @staticmethod
    def update_music(db: Session, music_id: int, music_data: MusicUpdate) -> Optional[Music]:
        db_music = db.query(Music).filter(Music.id == music_id).first()
        if not db_music:
            return None

        update_data = music_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_music, key, value)

        db.commit()
        db.refresh(db_music)
        return db_music

    @staticmethod
    def delete_music(db: Session, music_id: int) -> bool:
        db_music = db.query(Music).filter(Music.id == music_id).first()
        if not db_music:
            return False

        db.delete(db_music)
        db.commit()
        return True