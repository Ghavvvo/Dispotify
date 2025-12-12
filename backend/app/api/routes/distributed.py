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
        return raft_node.get_status()
    except Exception as e:
        logger.error(f"Error getting Raft status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operational-status")
async def get_operational_status(request: Request):
    """Endpoint para obtener el estado operativo detallado del nodo"""
    try:
        raft_node = request.app.state.raft_node
        discovery = request.app.state.discovery

        operational_info = raft_node.get_operational_info()
        all_nodes = discovery.get_all_nodes()
        alive_nodes = discovery.get_alive_nodes()

        return {
            "node_id": raft_node.node_id,
            "operational_mode": operational_info["operational_mode"],
            "raft_state": raft_node.state.value,
            "is_leader": raft_node.is_leader(),
            "leader_id": raft_node.leader_id,
            "term": raft_node.current_term,

            # Vista activa
            "vista_activa": operational_info["vista_activa"],
            "vista_activa_count": operational_info["vista_activa_count"],
            "is_isolated": operational_info["is_isolated"],

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

        cluster_nodes = request.app.state.cluster_nodes
        leader_node = next((n for n in cluster_nodes if n.id == leader_id), None)

        return {
            "leader_id": leader_id,
            "leader_address": f"{leader_node.address}:{leader_node.port}" if leader_node else None,
            "is_leader": raft_node.state == "leader",
            "term": raft_node.current_term
        }
    except Exception as e:
        logger.error(f"Error getting leader info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cluster/nodes")
async def get_cluster_nodes(request: Request):
    try:
        discovery = request.app.state.discovery
        cluster_nodes = request.app.state.cluster_nodes

        nodes_info = []
        for node in cluster_nodes:
            is_alive = discovery.is_node_alive(node.id)
            nodes_info.append({
                "id": node.id,
                "address": node.address,
                "port": node.port,
                "url": f"http://{node.address}:{node.port}",
                "alive": is_alive
            })

        return {
            "total": len(nodes_info),
            "alive": sum(1 for n in nodes_info if n["alive"]),
            "nodes": nodes_info
        }
    except Exception as e:
        logger.error(f"Error getting cluster nodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locks")
async def get_locks_info(request: Request):
    try:
        lock_manager = request.app.state.lock_manager

        return {
            "total_locks": len(lock_manager.locks),
            "locks": [
                {
                    "resource": resource,
                    "holder": lock.holder,
                    "acquired_at": lock.acquired_at.isoformat() if hasattr(lock, 'acquired_at') else None
                }
                for resource, lock in lock_manager.locks.items()
            ]
        }
    except Exception as e:
        logger.error(f"Error getting locks info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/stats")
async def get_event_stats(request: Request):
    try:
        event_queue = request.app.state.event_queue

        return {
            "queue_size": event_queue.queue.qsize() if hasattr(event_queue, 'queue') else 0,
            "use_raft": event_queue.use_raft,
            "node_id": event_queue.node_id
        }
    except Exception as e:
        logger.error(f"Error getting event stats: {e}")
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
        discovery = request.app.state.discovery
        cluster_nodes = request.app.state.cluster_nodes

        return {
            "node_id": raft_node.node_id,
            "node_info": {
                "address": raft_node.node_info.address,
                "port": raft_node.node_info.port
            },
            "raft": {
                "state": raft_node.state,
                "term": raft_node.current_term,
                "leader_id": raft_node.leader_id,
                "is_leader": raft_node.state == "leader"
            },
            "cluster": {
                "total_nodes": len(cluster_nodes),
                "alive_nodes": discovery.get_alive_count()
            }
        }
    except Exception as e:
        logger.error(f"Error getting node info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/lock")
async def test_acquire_lock(request: Request, lock_name: str, duration: int = 10):
    try:
        import asyncio
        from app.distributed.locks import get_lock_manager

        lock_manager = get_lock_manager()
        node_id = request.app.state.raft_node.node_id

        logger.info(f"[{node_id}] Intentando adquirir lock: {lock_name}")

        try:

            async with lock_manager.lock(lock_name, timeout=5.0):
                logger.info(f"✅ [{node_id}] Lock {lock_name} adquirido, manteniéndolo por {duration}s")

                await asyncio.sleep(duration)

                logger.info(f"🔓 [{node_id}] Lock {lock_name} será liberado automáticamente")

            return {
                "success": True,
                "message": f"Lock {lock_name} mantenido por {duration}s y liberado",
                "node_id": node_id,
                "lock_name": lock_name,
                "duration": duration
            }

        except TimeoutError:
            return {
                "success": False,
                "message": f"Timeout: No se pudo adquirir lock {lock_name} (ya está en uso)",
                "node_id": node_id
            }

    except Exception as e:
        logger.error(f"Error en test de lock: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/event")
async def test_publish_event(request: Request, event_type: str, message: str):
    try:
        from app.distributed.events import get_event_queue

        event_queue = get_event_queue()
        node_id = request.app.state.raft_node.node_id

        event_data = {
            "message": message,
            "origin_node": node_id,
            "source": "test_endpoint",
            "timestamp": __import__('time').time()
        }

        logger.info(f"📤 [{node_id}] Publicando evento: {event_type}")

        success = await event_queue.publish(event_type, event_data, timeout=5.0)

        if success:
            logger.info(f"[{node_id}] Evento {event_type} publicado exitosamente")
            return {
                "success": True,
                "message": f"Evento {event_type} publicado y replicado",
                "node_id": node_id,
                "event_type": event_type,
                "event_data": event_data
            }
        else:
            return {
                "success": False,
                "message": f"Evento {event_type} no se pudo replicar a mayoría",
                "node_id": node_id
            }

    except Exception as e:
        logger.error(f"Error publicando evento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/replicate")
async def test_file_replication(request: Request, file_id: str, content: str):
    try:
        import hashlib

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
            "timestamp": __import__('time').time()
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
            "state": raft_node.state,
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

    Modelo de Consistencia:
    - Metadata Escritura: FUERTE (Raft) - Log Raft, mayoría
    - Metadata Lectura: EVENTUAL - Cualquier réplica Raft
    - Archivos MP3 Escritura: FUERTE (Quórum) - (R/2)+1 réplicas
    - Archivos MP3 Lectura/Stream: EVENTUAL - Réplica más cercana
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
                "is_leader": raft_node.is_leader(),
                "can_serve_reads": raft_node.can_serve_read(),
                "can_serve_writes": raft_node.is_leader(),
                "leader_id": raft_node.get_leader()
            },
            "raft_status": raft_node.get_eventual_read_status(),
            "replication": {
                "factor": replication_factor,
                "quorum_required": quorum_required,
                "storage_path": str(replication_manager.storage_path)
            }
        }
    except Exception as e:
        logger.error(f"Error getting consistency status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consistency/check")
async def check_consistency(request: Request):
    """
    Verifica la consistencia del cluster comparando commit_index entre nodos.
    Solo el líder puede ejecutar esta verificación.
    """
    try:
        raft_node = request.app.state.raft_node

        if not raft_node.is_leader():
            raise HTTPException(
                status_code=400,
                detail="Solo el líder puede verificar la consistencia del cluster"
            )

        from app.distributed.communication import get_p2p_client
        p2p_client = get_p2p_client()

        results = []
        leader_commit = raft_node.commit_index
        leader_applied = raft_node.last_applied

        for peer in raft_node.cluster_nodes:
            try:
                status = await p2p_client.call_rpc(peer, "GET", "/api/v1/distributed/raft/status")
                lag = leader_commit - status.get("commit_index", 0)
                results.append({
                    "node_id": peer.id,
                    "commit_index": status.get("commit_index", 0),
                    "last_applied": status.get("last_applied", 0),
                    "lag_from_leader": lag,
                    "status": "in_sync" if lag == 0 else ("lagging" if lag < 5 else "significantly_behind")
                })
            except Exception as e:
                results.append({
                    "node_id": peer.id,
                    "error": str(e),
                    "status": "unreachable"
                })

        all_in_sync = all(r.get("status") == "in_sync" for r in results)

        return {
            "leader": {
                "node_id": raft_node.node_id,
                "commit_index": leader_commit,
                "last_applied": leader_applied
            },
            "followers": results,
            "cluster_status": "consistent" if all_in_sync else "inconsistent",
            "total_nodes": len(results) + 1,
            "in_sync_count": sum(1 for r in results if r.get("status") == "in_sync") + 1
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking consistency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replication/status")
async def get_replication_status(request: Request):
    """Endpoint para ver archivos de música locales y estado de replicación"""
    try:
        replication_manager = request.app.state.replication_manager
        raft_node = request.app.state.raft_node

        import os
        files = []
        storage_path = replication_manager.storage_path
        if storage_path.exists():
            try:
                all_items = os.listdir(str(storage_path))
                files = [f for f in all_items if os.path.isfile(storage_path / f)]
            except Exception as e:
                logger.error(f"Error listing files: {e}")
                files = []

        # Check replication status
        replication_status = getattr(replication_manager, '_running', False)

        return {
            "node_id": raft_node.node_id,
            "music_files": files,
            "replication_status": "active" if replication_status else "inactive",
            "storage_path": str(storage_path),
            "file_count": len(files)
        }
    except Exception as e:
        logger.error(f"Error getting replication status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
