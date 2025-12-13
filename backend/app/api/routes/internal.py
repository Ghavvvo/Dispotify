from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
import json
import logging
from pydantic import BaseModel
from app.distributed.replication import get_replication_manager
from app.distributed.raft import get_raft_node
from app.distributed.communication import NodeInfo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal"])


class NodeRegistration(BaseModel):
    node_id: str
    address: str
    port: int


@router.post("/internal/register")
async def register_node(registration: NodeRegistration, request: Request):
    try:
        raft_node = get_raft_node()

        if not raft_node.is_leader():
            if raft_node.leader_id:
                return {
                    "success": False,
                    "error": "not_leader",
                    "leader_id": raft_node.leader_id,
                    "message": f"Este nodo no es el lider. Lider actual: {raft_node.leader_id}"
                }
            else:
                return {
                    "success": False,
                    "error": "no_leader",
                    "message": "No hay lider electo actualmente"
                }

        new_node = NodeInfo(
            id=registration.node_id,
            address=registration.address,
            port=registration.port
        )

        command = {
            "type": "add_node",
            "node_id": new_node.id,
            "address": new_node.address,
            "port": new_node.port
        }

        success = await raft_node.submit_command(command)

        if success:
            all_nodes = raft_node.get_all_nodes()
            return {
                "success": True,
                "message": f"Nodo {registration.node_id} registrado exitosamente",
                "cluster_nodes": [
                    {"id": n.id, "address": n.address, "port": n.port}
                    for n in all_nodes
                ]
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Fallo al propagar registro via Raft"
            )

    except Exception as e:
        logger.error(f"Error registrando nodo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    try:
        raft_node = get_raft_node()
        return {
            "status": "healthy",
            "node_id": raft_node.node_id,
            "state": raft_node.state.value,
            "term": raft_node.current_term
        }
    except Exception as e:
        logger.error(f"Error en health check: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="unhealthy")


@router.get("/internal/cluster-info")
async def get_cluster_info(request: Request):
    try:
        raft_node = get_raft_node()
        
        all_nodes = raft_node.get_all_nodes()
        alive_nodes = raft_node.get_alive_nodes()
        alive_ids = {n.id for n in alive_nodes}

        return {
            "leader_id": raft_node.leader_id,
            "this_node_id": raft_node.node_id,
            "is_leader": raft_node.is_leader(),
            "term": raft_node.current_term,
            "log_size": len(raft_node.log),
            "commit_index": raft_node.commit_index,
            "cluster_size": len(all_nodes),
            "alive_count": len(alive_nodes),
            "nodes": [
                {
                    "id": n.id,
                    "address": n.address,
                    "port": n.port,
                    "status": "alive" if n.id in alive_ids else "dead"
                }
                for n in all_nodes
            ]
        }
    except Exception as e:
        logger.error(f"Error obteniendo info del cluster: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class SyncRequest(BaseModel):
    node_id: str
    node_address: str
    node_port: int
    current_log_size: int
    current_term: int


@router.post("/internal/request-sync")
async def request_sync(sync_request: SyncRequest):
    try:
        import asyncio
        raft_node = get_raft_node()

        if not raft_node.is_leader():
            return {
                "success": False,
                "error": "not_leader",
                "leader_id": raft_node.leader_id,
                "message": "Este nodo no es el líder"
            }
        requesting_node = NodeInfo(
            id=sync_request.node_id,
            address=sync_request.node_address,
            port=sync_request.node_port
        )

        node_in_cluster = any(n.id == sync_request.node_id for n in raft_node.get_all_nodes())

        if not node_in_cluster:
            # Si el nodo no está en el cluster, enviamos comando add_node para replicarlo
            logger.info(f"Nodo {sync_request.node_id} solicitando sync pero no está en cluster. Iniciando add_node.")
            command = {
                "type": "add_node",
                "node_id": requesting_node.id,
                "address": requesting_node.address,
                "port": requesting_node.port
            }
            # No esperamos a que termine para no bloquear, pero iniciamos el proceso
            asyncio.create_task(raft_node.submit_command(command))
            
            # También lo agregamos localmente temporalmente para permitir sync inmediata?
            # Mejor esperar a que se aplique el comando, pero para sync inmediata:
            raft_node.add_peer(requesting_node)
        else:
            # asyncio.create_task(raft_node._sync_node(requesting_node))
            pass

        logger.info(
            f"Sync solicitada por {sync_request.node_id} "
            f"(log_size={sync_request.current_log_size}, term={sync_request.current_term})"
        )

        return {
            "success": True,
            "message": f"Sincronización iniciada para {sync_request.node_id}",
            "leader_log_size": len(raft_node.log),
            "leader_term": raft_node.current_term,
            "cluster_id": "dispotify-cluster",
            "leader_id": raft_node.node_id
        }

    except Exception as e:
        logger.error(f"Error en request-sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        
        
        replication_manager = get_replication_manager()
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
        
        replication_manager = get_replication_manager()
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
        
        replication_manager = get_replication_manager()
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


@router.post("/raft/append-entries")
async def raft_append_entries(request: Request):
    try:
        data = await request.json()
        raft_node = get_raft_node()
        response = await raft_node.handle_append_entries(data)
        return response
    except Exception as e:
        logger.error(f"Error en append-entries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/raft/request-vote")
async def raft_request_vote(request: Request):
    try:
        data = await request.json()
        raft_node = get_raft_node()
        response = await raft_node.handle_request_vote(data)
        return response
    except Exception as e:
        logger.error(f"Error en request-vote: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/internal/replicas")
async def list_local_replicas():
    
    try:
        replication_manager = get_replication_manager()
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
