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

@router.get("/leader")
async def get_cluster_leader():
    """
    Get the current leader information.
    Returns the leader's host and port as seen by this node.
    """
    try:
        raft_node = get_raft_node()
        leader_id = raft_node.get_leader()
        
        if not leader_id:
            raise HTTPException(status_code=503, detail="No leader elected yet")
        
        # If this node is the leader
        if leader_id == raft_node.node_id:
            return {
                "leaderHost": raft_node.address,
                "leaderPort": raft_node.port,
                "leaderId": leader_id
            }
        
        # Find leader in peers
        if leader_id in raft_node.peers:
            leader_node = raft_node.peers[leader_id]
            return {
                "leaderHost": leader_node.address,
                "leaderPort": leader_node.port,
                "leaderId": leader_id
            }
        
        # Leader ID known but not in peers (shouldn't happen normally)
        raise HTTPException(status_code=503, detail=f"Leader {leader_id} not found in peers")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cluster leader: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files")
async def get_node_files():
    """
    List all files stored locally on this node.
    """
    try:
        from app.core.database import get_db
        from app.models.music import Music
        
        replication_manager = get_replication_manager()
        storage_path = replication_manager.storage_path
        
        # Get physical files
        physical_files = {}
        if storage_path.exists():
            for f in storage_path.iterdir():
                if f.is_file():
                    physical_files[f.name] = {
                        "filename": f.name,
                        "size": f.stat().st_size,
                        "modified": f.stat().st_mtime,
                        "song_name": None
                    }
        
        # Get metadata from database
        db = next(get_db())
        try:
            songs = db.query(Music).all()
            metadata_list = []
            
            for song in songs:
                filename = song.url.split('/')[-1] if song.url else None
                metadata_list.append({
                    "id": song.id,
                    "song_name": song.nombre,
                    "author": song.autor,
                    "filename": filename,
                    "has_file": filename in physical_files if filename else False
                })
                
                # Add song name to physical file if exists
                if filename and filename in physical_files:
                    physical_files[filename]["song_name"] = song.nombre
        finally:
            db.close()
        
        return {
            "node_id": replication_manager.node_id,
            "storage_path": str(storage_path),
            "physical_files_count": len(physical_files),
            "metadata_count": len(metadata_list),
            "physical_files": list(physical_files.values()),
            "metadata": metadata_list
        }
    except Exception as e:
        logger.error(f"Error getting node files: {e}")
        raise HTTPException(status_code=500, detail=str(e))
