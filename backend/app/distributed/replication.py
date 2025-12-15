import os
import hashlib
import logging
from pathlib import Path
import aiofiles

logger = logging.getLogger(__name__)

class ReplicationManager:
    _instance = None
    
    def __init__(self):
        self.storage_path = Path("/app/music_files")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.node_id = os.getenv("NODE_ID", "unknown")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ReplicationManager()
        return cls._instance

    async def receive_file(self, file_data: bytes, metadata: dict):
        file_id = metadata.get("file_id")
        song_name = metadata.get("nombre", "unknown")
        filename = file_id
        file_path = self.storage_path / filename
        
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_data)
            
        checksum = hashlib.md5(file_data).hexdigest()
        
        logger.info(f"[REPLICATION] Stored file {file_id} ({song_name}) at {file_path}, size: {len(file_data)} bytes, checksum: {checksum}")
        
        return {
            "file_id": file_id,
            "checksum": checksum,
            "file_size": len(file_data)
        }

    async def replicate_file(self, file_id: str, file_path: Path, metadata: dict):
        from .raft import get_raft_node
        import httpx
        import json
        
        raft_node = get_raft_node()
        peers = raft_node.get_alive_nodes()
        song_name = metadata.get("nombre", "unknown")
        
        if not file_path.exists():
            logger.error(f"[REPLICATION] File {file_id} ({song_name}) does not exist at {file_path}")
            return
        
        file_size = file_path.stat().st_size
        logger.info(f"[REPLICATION] Starting replication of {file_id} ({song_name}), size: {file_size} bytes to {len(peers)} peers")
        
        metadata["file_id"] = file_id
        
        async with httpx.AsyncClient() as client:
            for peer in peers:
                if peer.id == self.node_id:
                    continue
                    
                file_handle = None
                try:
                    url = f"http:
                    
                    file_handle = open(file_path, 'rb')
                    files = {'file': file_handle}
                    data = {'metadata': json.dumps(metadata)}
                    
                    logger.info(f"[REPLICATION] Sending {file_id} ({song_name}) to {peer.id} at {url}")
                    resp = await client.post(url, files=files, data=data, timeout=30.0)
                    
                    if resp.status_code == 200:
                        logger.info(f"[REPLICATION] Success to {peer.id} for {file_id} ({song_name})")
                    else:
                        logger.warning(f"[REPLICATION] Failed to {peer.id} for {file_id}: status {resp.status_code}")
                        
                except Exception as e:
                    logger.error(f"[REPLICATION] Error sending to {peer.id} for {file_id}: {e}")
                finally:
                    if file_handle:
                        file_handle.close()

def get_replication_manager():
    return ReplicationManager.get_instance()
