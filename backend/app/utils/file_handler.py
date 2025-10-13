from pathlib import Path
import aiofiles
import uuid
from fastapi import UploadFile, HTTPException
from app.core.config import settings

class FileHandler:
    @staticmethod
    async def save_file(file: UploadFile) -> tuple[str, int]:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {settings.ALLOWED_EXTENSIONS}"
            )

        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = settings.UPLOAD_DIR / unique_filename

        file_size = 0
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file.read(8192):
                if file_size + len(chunk) > settings.MAX_FILE_SIZE:
                    await f.close()
                    file_path.unlink()
                    raise HTTPException(status_code=413, detail="File too large")
                await f.write(chunk)
                file_size += len(chunk)

        return str(file_path), file_size

    @staticmethod
    def delete_file(file_path: str):
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass