from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
import json
import logging
from app.distributed.replication import get_p2p_replication_manager
from app.distributed.events import get_event_queue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal"])

@router.post("/internal/replicate")
async def receive_replicated_file(
    file: UploadFile = File(...),
    metadata: str = Form(...)
):
    
    try:
        
        metadata_dict = json.loads(metadata)
        file_id = metadata_dict.get("file_id")
        
        logger.info(f"Recibiendo réplica de archivo {file_id}")
        
        
        file_data = await file.read()
        
        
        replication_manager = get_p2p_replication_manager()
        result = await replication_manager.receive_file(file_data, metadata_dict)
        
        return {
            "success": True,
            "file_id": result["file_id"],
            "checksum": result["checksum"],
            "file_size": result["file_size"]
        }
        
    except Exception as e:
        logger.error(f"Error recibiendo archivo replicado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/internal/file/{file_id}")
async def get_replicated_file(file_id: str):
    
    try:
        from pathlib import Path
        from fastapi.responses import FileResponse
        
        replication_manager = get_p2p_replication_manager()
        storage_path = replication_manager.storage_path
        
        
        file_path = None
        for f in storage_path.iterdir():
            if f.is_file() and file_id in f.name:
                file_path = f
                break
        
        if not file_path or not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Archivo {file_id} no encontrado en este nodo"
            )
        
        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type='application/octet-stream'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo archivo {file_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/internal/file/{file_id}")
async def delete_replicated_file(file_id: str):
    
    try:
        from pathlib import Path
        
        replication_manager = get_p2p_replication_manager()
        storage_path = replication_manager.storage_path
        
        
        deleted = False
        for f in storage_path.iterdir():
            if f.is_file() and file_id in f.name:
                f.unlink()
                deleted = True
                logger.info(f"Archivo {file_id} eliminado de este nodo")
                break
        
        if not deleted:
            logger.warning(f"Archivo {file_id} no encontrado en este nodo")
        
        return {
            "success": True,
            "file_id": file_id,
            "deleted": deleted
        }
        
    except Exception as e:
        logger.error(f"Error eliminando archivo {file_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/internal/event")
async def receive_broadcast_event(event: dict):
    
    try:
        event_queue = get_event_queue()
        await event_queue.handle_incoming_event(event)
        
        return {
            "success": True,
            "event_type": event.get("event_type")
        }
        
    except Exception as e:
        logger.error(f"Error recibiendo evento broadcast: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/internal/replicas")
async def list_local_replicas():
    
    try:
        replication_manager = get_p2p_replication_manager()
        storage_path = replication_manager.storage_path
        
        replicas = []
        for f in storage_path.iterdir():
            if f.is_file():
                replicas.append({
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime
                })
        
        return {
            "node_id": replication_manager.node_id,
            "storage_path": str(storage_path),
            "replicas": replicas,
            "total": len(replicas)
        }
        
    except Exception as e:
        logger.error(f"Error listando réplicas locales: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/raft/request-vote")
async def raft_request_vote(request: dict):
    
    try:
        from app.distributed.raft import get_raft_node

        raft_node = get_raft_node()

        
        response = await raft_node.handle_request_vote(request)

        return response

    except Exception as e:
        logger.error(f"Error en RequestVote RPC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/raft/append-entries")
async def raft_append_entries(request: dict):
    
    try:
        from app.distributed.raft import get_raft_node

        raft_node = get_raft_node()

        
        response = await raft_node.handle_append_entries(request)

        return response

    except Exception as e:
        logger.error(f"Error en AppendEntries RPC: {e}")
        raise HTTPException(status_code=500, detail=str(e))