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
        # Ensure filename is safe
        filename = file_id
        file_path = self.storage_path / filename
        
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_data)
            
        checksum = hashlib.md5(file_data).hexdigest()
        
        logger.info(f"Stored file {file_id} at {file_path}")
        
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
        
        metadata["file_id"] = file_id
        
        async with httpx.AsyncClient() as client:
            for peer in peers:
                if peer.id == self.node_id:
                    continue
                    
                try:
                    url = f"http://{peer.address}:{peer.port}/internal/replicate"
                    
                    # Prepare multipart upload
                    files = {'file': open(file_path, 'rb')}
                    data = {'metadata': json.dumps(metadata)}
                    
                    logger.info(f"Replicating {file_id} to {peer.id} at {url}")
                    resp = await client.post(url, files=files, data=data, timeout=10.0)
                    files['file'].close()
                    
                    if resp.status_code == 200:
                        logger.info(f"Replication to {peer.id} successful")
                    else:
                        logger.warning(f"Replication to {peer.id} failed: {resp.status_code}")
                        
                except Exception as e:
                    logger.error(f"Error replicating to {peer.id}: {e}")

def get_replication_manager():
    return ReplicationManager.get_instance()
