from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.sql import func
from app.core.database import Base

class Music(Base):
    __tablename__ = "music"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, index=True)
    autor = Column(String, nullable=False, index=True)
    album = Column(String, index=True)
    genero = Column(String, index=True)
    duracion = Column(Float)
    file_path = Column(String, nullable=False, unique=True)
    file_size = Column(Integer)
    format = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Music {self.nombre} by {self.autor}>"