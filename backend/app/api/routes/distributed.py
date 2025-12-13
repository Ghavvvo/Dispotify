from fastapi import APIRouter, Request, HTTPException
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["distributed"])


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "dispotify-p2p"
    }


@router.get("/raft/status")
async def get_raft_status(request: Request):
    try:
        raft_node = request.app.state.raft_node
        # Assuming get_status() exists or we construct it
        return {
            "node_id": raft_node.node_id,
            "state": raft_node.state.value,
            "term": raft_node.current_term,
            "leader_id": raft_node.leader_id,
            "commit_index": raft_node.commit_index,
            "last_applied": raft_node.last_applied,
            "log_length": len(raft_node.log)
        }
    except Exception as e:
        logger.error(f"Error getting Raft status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operational-status")
async def get_operational_status(request: Request):
    """Endpoint para obtener el estado operativo detallado del nodo"""
    try:
        raft_node = request.app.state.raft_node
        
        all_nodes = raft_node.get_all_nodes()
        alive_nodes = raft_node.get_alive_nodes()

        return {
            "node_id": raft_node.node_id,
            "operational_mode": raft_node.operational_mode.value,
            "raft_state": raft_node.state.value,
            "is_leader": raft_node.state.value == "leader",
            "leader_id": raft_node.leader_id,
            "term": raft_node.current_term,
            "partition_id": raft_node.partition_id,
            "epoch_number": raft_node.epoch_number,

            # Nodos
            "all_nodes": [n.id for n in all_nodes],
            "alive_nodes": [n.id for n in alive_nodes],
            "cluster_size": len(all_nodes)
        }
    except Exception as e:
        logger.error(f"Error getting operational status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leader")
async def get_leader_info(request: Request):
    try:
        raft_node = request.app.state.raft_node
        leader_id = raft_node.leader_id

        if not leader_id:
            return {
                "leader_id": None,
                "message": "No leader elected yet"
            }

        all_nodes = raft_node.get_all_nodes()
        leader_node = next((n for n in all_nodes if n.id == leader_id), None)

        return {
            "leader_id": leader_id,
            "leader_address": f"{leader_node.address}:{leader_node.port}" if leader_node else None,
            "is_leader": raft_node.state.value == "leader",
            "term": raft_node.current_term
        }
    except Exception as e:
        logger.error(f"Error getting leader info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cluster/nodes")
async def get_cluster_nodes(request: Request):
    try:
        raft_node = request.app.state.raft_node
        all_nodes = raft_node.get_all_nodes()
        alive_nodes_ids = {n.id for n in raft_node.get_alive_nodes()}

        nodes_info = []
        for node in all_nodes:
            is_alive = node.id in alive_nodes_ids
            nodes_info.append({
                "id": node.id,
                "address": node.address,
                "port": node.port,
                "url": f"http://{node.address}:{node.port}",
                "alive": is_alive
            })

        return {
            "total": len(nodes_info),
            "alive": len(alive_nodes_ids),
            "nodes": nodes_info
        }
    except Exception as e:
        logger.error(f"Error getting cluster nodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replication/stats")
async def get_replication_stats(request: Request):
    try:
        replication_manager = request.app.state.replication_manager
        hash_ring = request.app.state.hash_ring

        return {
            "replication_factor": replication_manager.replication_factor,
            "storage_path": str(replication_manager.storage_path),
            "hash_ring_nodes": len(hash_ring.node_map),
            "virtual_nodes": len(hash_ring.ring)
        }
    except Exception as e:
        logger.error(f"Error getting replication stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/node/info")
async def get_node_info(request: Request):
    try:
        raft_node = request.app.state.raft_node
        
        return {
            "node_id": raft_node.node_id,
            "node_info": {
                "address": raft_node.node_info.address,
                "port": raft_node.node_info.port
            },
            "raft": {
                "state": raft_node.state.value,
                "term": raft_node.current_term,
                "leader_id": raft_node.leader_id,
                "is_leader": raft_node.state.value == "leader"
            },
            "cluster": {
                "total_nodes": len(raft_node.get_all_nodes()),
                "alive_nodes": len(raft_node.get_alive_nodes())
            }
        }
    except Exception as e:
        logger.error(f"Error getting node info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/replicate")
async def test_file_replication(request: Request, file_id: str, content: str):
    try:
        import hashlib
        import time

        raft_node = request.app.state.raft_node
        node_id = raft_node.node_id

        checksum = hashlib.md5(content.encode('utf-8')).hexdigest()

        command = {
            "type": "file_replicate",
            "file_id": file_id,
            "content": content,
            "checksum": checksum,
            "size": len(content),
            "origin_node": node_id,
            "timestamp": time.time()
        }

        logger.info(f"[{node_id}] Enviando comando de replicación: {file_id}")

        success = await raft_node.submit_command(command, timeout=5.0)

        if success:
            logger.info(f"[{node_id}] Archivo {file_id} replicado via Raft")
            return {
                "success": True,
                "message": f"Archivo {file_id} replicado a mayoría del cluster",
                "node_id": node_id,
                "file_id": file_id,
                "size": len(content),
                "checksum": checksum
            }
        else:
            return {
                "success": False,
                "message": f"Archivo {file_id} no se pudo replicar a mayoría",
                "node_id": node_id
            }

    except Exception as e:
        logger.error(f"Error replicando archivo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test/state")
async def get_state_machine_state(request: Request):
    try:
        raft_node = request.app.state.raft_node

        return {
            "node_id": raft_node.node_id,
            "state": raft_node.state.value,
            "term": raft_node.current_term,
            "state_machine": raft_node.state_machine,
            "log_length": len(raft_node.log),
            "commit_index": raft_node.commit_index,
            "last_applied": raft_node.last_applied
        }

    except Exception as e:
        logger.error(f"Error obteniendo state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consistency/status")
async def get_consistency_status(request: Request):
    """
    Retorna el estado del modelo de consistencia híbrido del sistema.
    """
    try:
        raft_node = request.app.state.raft_node
        replication_manager = request.app.state.replication_manager

        # Calcular quórum para archivos
        replication_factor = replication_manager.replication_factor
        quorum_required = (replication_factor // 2) + 1

        return {
            "consistency_model": "HYBRID",
            "metadata": {
                "write_consistency": "STRONG (Raft)",
                "write_mechanism": "Log Raft + Majority Consensus",
                "read_consistency": "EVENTUAL",
                "read_mechanism": "Any Raft replica"
            },
            "files_mp3": {
                "write_consistency": "STRONG (Quorum)",
                "write_mechanism": f"(R/2)+1 = {quorum_required} of {replication_factor} replicas",
                "read_consistency": "EVENTUAL",
                "read_mechanism": "Nearest available replica"
            },
            "node_status": {
                "node_id": raft_node.node_id,
                "is_leader": raft_node.state.value == "leader",
                "leader_id": raft_node.leader_id
            },
            "replication": {
                "factor": replication_factor,
                "quorum_required": quorum_required,
                "storage_path": str(replication_manager.storage_path)
            }
        }
    except Exception as e:
        logger.error(f"Error getting consistency status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
