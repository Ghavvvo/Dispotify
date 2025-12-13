from fastapi import APIRouter, HTTPException
from app.distributed.raft import get_raft_node
from app.distributed.replication import get_replication_manager
import logging

router = APIRouter(prefix="/cluster", tags=["Cluster Status"])
logger = logging.getLogger(__name__)

@router.get("/status")
async def get_node_status():
    """
    Get current node status, leader info, and cluster membership.
    """
    try:
        raft_node = get_raft_node()
        
        all_nodes = raft_node.get_all_nodes()
        alive_nodes = raft_node.get_alive_nodes()
        alive_ids = {n.id for n in alive_nodes}
        
        return {
            "node_id": raft_node.node_id,
            "state": raft_node.state.value,
            "term": raft_node.current_term,
            "leader_id": raft_node.leader_id,
            "partition_id": raft_node.partition_id,
            "commit_index": raft_node.commit_index,
            "last_applied": raft_node.last_applied,
            "peers_count": len(raft_node.peers),
            "reachable_peers_count": len(raft_node.reachable_peers),
            "nodes": [
                {
                    "id": n.id,
                    "address": n.address,
                    "port": n.port,
                    "status": "alive" if n.id in alive_ids else "unreachable"
                }
                for n in all_nodes
            ]
        }
    except Exception as e:
        logger.error(f"Error getting cluster status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files")
async def get_node_files():
    """
    List all files stored locally on this node.
    """
    try:
        replication_manager = get_replication_manager()
        storage_path = replication_manager.storage_path
        
        files = []
        if storage_path.exists():
            for f in storage_path.iterdir():
                if f.is_file():
                    files.append({
                        "filename": f.name,
                        "size": f.stat().st_size,
                        "modified": f.stat().st_mtime
                    })
        
        return {
            "node_id": replication_manager.node_id,
            "storage_path": str(storage_path),
            "file_count": len(files),
            "files": files
        }
    except Exception as e:
        logger.error(f"Error getting node files: {e}")
        raise HTTPException(status_code=500, detail=str(e))
