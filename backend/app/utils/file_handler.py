from pathlib import Path
import aiofiles
import uuid
import hashlib
from fastapi import UploadFile, HTTPException
from app.core.config import settings

class FileHandler:
    @staticmethod
    async def save_file(file: UploadFile) -> tuple[str, int, str]:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        file_ext = Path(file.filename).suffix.lower()
        allowed_exts = [ext.strip() for ext in settings.ALLOWED_EXTENSIONS.split(",")]
        if file_ext not in allowed_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {allowed_exts}"
            )

        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = upload_dir / unique_filename

        file_size = 0
        sha256_hash = hashlib.sha256()
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file.read(8192):
                if file_size + len(chunk) > settings.MAX_FILE_SIZE:
                    await f.close()
                    file_path.unlink()
                    raise HTTPException(status_code=413, detail="File too large")
                await f.write(chunk)
                sha256_hash.update(chunk)
                file_size += len(chunk)

        return str(file_path), file_size, sha256_hash.hexdigest()

    @staticmethod
    def delete_file(file_path: str):
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass