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


async def _replicate_merge_files_targeted(files_metadata: list, target_node_ids: list):
    """
    Replicate files received during partition merge ONLY to specific target nodes.
    This avoids sending files to nodes that already have them.
    
    Args:
        files_metadata: List of file metadata dicts
        target_node_ids: List of node IDs that should receive these files
    """
    import asyncio
    import httpx
    import json
    from pathlib import Path
    
    # Wait a bit to ensure files are received
    await asyncio.sleep(2)
    
    replication_manager = get_replication_manager()
    raft_node = get_raft_node()
    
    logger.info(f"[MERGE_REPLICATION_TARGETED] Starting targeted replication of {len(files_metadata)} files to {len(target_node_ids)} specific nodes")
    logger.info(f"[MERGE_REPLICATION_TARGETED] Target nodes: {target_node_ids}")
    
    # Get peer information for target nodes
    target_peers = []
    for peer in raft_node.get_alive_nodes():
        if peer.id in target_node_ids:
            target_peers.append(peer)
    
    logger.info(f"[MERGE_REPLICATION_TARGETED] Found {len(target_peers)} target peers")
    
    for file_meta in files_metadata:
        file_id = file_meta["file_id"]
        file_path = replication_manager.storage_path / file_id
        
        # Wait for file to be available (with timeout)
        max_wait = 30  # seconds
        waited = 0
        while not file_path.exists() and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1
        
        if file_path.exists():
            logger.info(f"[MERGE_REPLICATION_TARGETED] Replicating {file_id} ({file_meta['nombre']}) to {len(target_peers)} target nodes")
            
            async with httpx.AsyncClient() as client:
                for peer in target_peers:
                    if peer.id == replication_manager.node_id:
                        continue
                    
                    file_handle = None
                    try:
                        url = f"http://{peer.address}:{peer.port}/internal/replicate"
                        
                        file_handle = open(file_path, 'rb')
                        files = {'file': file_handle}
                        data = {'metadata': json.dumps(file_meta)}
                        
                        logger.info(f"[MERGE_REPLICATION_TARGETED] Sending {file_id} to {peer.id}")
                        resp = await client.post(url, files=files, data=data, timeout=30.0)
                        
                        if resp.status_code == 200:
                            logger.info(f"[MERGE_REPLICATION_TARGETED] Success to {peer.id} for {file_id}")
                        else:
                            logger.warning(f"[MERGE_REPLICATION_TARGETED] Failed to {peer.id}: status {resp.status_code}")
                            
                    except Exception as e:
                        logger.error(f"[MERGE_REPLICATION_TARGETED] Error sending to {peer.id}: {e}")
                    finally:
                        if file_handle:
                            file_handle.close()
        else:
            logger.error(f"[MERGE_REPLICATION_TARGETED] File {file_id} not found after waiting {max_wait}s")


class BidirectionalMergeRequest(BaseModel):
    node_id: str
    our_term: int
    our_log: list
    partition_songs: list


@router.post("/internal/partition-merge-bidirectional")
async def handle_bidirectional_partition_merge(merge_request: BidirectionalMergeRequest):
    """
    Handle bidirectional partition merge using Raft logs as source of truth.
    Optimized to avoid sending duplicate files.
    
    Strategy:
    1. Ex-leader sends list of files their partition has
    2. Leader compares and identifies missing files for each partition
    3. Leader requests missing files from ex-leader
    4. Leader distributes files only to nodes that need them:
       - Files from ex-leader partition → only to leader's original partition
       - Files from leader partition → only to ex-leader's partition
    """
    try:
        from app.core.database import SessionLocal
        from app.models.music import Music
        import time
        
        raft_node = get_raft_node()
        
        if not raft_node.is_leader():
            raise HTTPException(
                status_code=400,
                detail="Only the leader can handle partition merges"
            )
        
        logger.info(f"[MERGE_BIDIRECTIONAL] Received merge from {merge_request.node_id}: "
                   f"term={merge_request.our_term}, log_entries={len(merge_request.our_log)}, "
                   f"songs={len(merge_request.partition_songs)}")
        
        db = SessionLocal()
        
        try:
            # Step 1: Get our current state
            our_songs = db.query(Music).all()
            our_urls = {song.url for song in our_songs}
            their_urls = {song["url"] for song in merge_request.partition_songs}
            
            logger.info(f"[MERGE_BIDIRECTIONAL] Our partition: {len(our_songs)} songs, "
                       f"Their partition: {len(merge_request.partition_songs)} songs")
            
            # Step 2: Analyze logs to determine what operations each partition has
            # Extract create_music commands from their log
            their_log_operations = {}
            for log_entry in merge_request.our_log:
                command = log_entry.get("command")
                if command and command.get("type") == "create_music":
                    url = command.get("url")
                    if url:
                        their_log_operations[url] = command
            
            # Extract create_music commands from our log
            our_log_operations = {}
            for log_entry in raft_node.log:
                command = log_entry.get("command")
                if command and command.get("type") == "create_music":
                    url = command.get("url")
                    if url:
                        our_log_operations[url] = command
            
            logger.info(f"[MERGE_BIDIRECTIONAL] Log analysis: "
                       f"We have {len(our_log_operations)} create operations, "
                       f"They have {len(their_log_operations)} create operations")
            
            # Step 3: Determine what WE (leader's partition) need from THEM
            files_we_need = []
            songs_we_need = []
            
            for url, command in their_log_operations.items():
                if url not in our_urls and url not in our_log_operations:
                    # This is a song they have that we don't
                    file_id = url.split('/')[-1]
                    files_we_need.append(file_id)
                    
                    # Find the song data
                    song_data = next((s for s in merge_request.partition_songs if s["url"] == url), None)
                    if song_data:
                        songs_we_need.append(song_data)
                        logger.info(f"[MERGE_BIDIRECTIONAL] Our partition needs: {song_data['nombre']}")
            
            # Step 4: Determine what THEY (ex-leader's partition) need from US
            files_they_need = []
            songs_they_need = []
            
            for url, command in our_log_operations.items():
                if url not in their_urls and url not in their_log_operations:
                    # This is a song we have that they don't
                    file_id = url.split('/')[-1]
                    
                    if file_id == "null" or not file_id:
                        logger.warning(f"[MERGE_BIDIRECTIONAL] Suspicious file_id '{file_id}' derived from url '{url}'")
                        
                    files_they_need.append(file_id)
                    
                    # Find the song in our database
                    song = db.query(Music).filter(Music.url == url).first()
                    if song:
                        songs_they_need.append({
                            "nombre": song.nombre,
                            "autor": song.autor,
                            "album": song.album,
                            "genero": song.genero,
                            "url": song.url,
                            "file_size": song.file_size,
                            "partition_id": song.partition_id,
                            "epoch_number": song.epoch_number
                        })
                        logger.info(f"[MERGE_BIDIRECTIONAL] Their partition needs: {song.nombre} (found in DB)")
                    else:
                        # Fallback to command data if not in DB yet
                        logger.warning(f"[MERGE_BIDIRECTIONAL] Song {url} not found in DB but exists in log. Using log data.")
                        songs_they_need.append({
                            "nombre": command.get("nombre"),
                            "autor": command.get("autor"),
                            "album": command.get("album"),
                            "genero": command.get("genero"),
                            "url": command.get("url"),
                            "file_size": command.get("file_size"),
                            "partition_id": command.get("partition_id"),
                            "epoch_number": command.get("epoch_number")
                        })
            
            # Step 5: Add songs we're missing to our database via Raft
            # This will replicate metadata to ALL nodes via Raft
            logger.info(f"[MERGE_BIDIRECTIONAL] Adding {len(songs_we_need)} songs from their partition via Raft")
            for song_data in songs_we_need:
                command = {
                    "type": "create_music",
                    "nombre": song_data["nombre"],
                    "autor": song_data["autor"],
                    "album": song_data.get("album"),
                    "genero": song_data.get("genero"),
                    "url": song_data["url"],
                    "file_size": song_data["file_size"],
                    "partition_id": song_data.get("partition_id"),
                    "epoch_number": song_data.get("epoch_number"),
                    "conflict_flag": False,
                    "merge_timestamp": time.time()
                }
                
                success = await raft_node.submit_command(command, timeout=15.0)
                if not success:
                    logger.error(f"[MERGE_BIDIRECTIONAL] Failed to add song {song_data['nombre']}")
            
            # Step 6: Identify which nodes belong to which original partition
            # Nodes from ex-leader's partition will need files from our partition
            # Nodes from our partition will need files from their partition
            
            # Get all current peers
            all_peers = raft_node.get_alive_nodes()
            
            # The ex-leader and its followers are the ones we just merged with
            # We'll send them files they need
            ex_leader_partition_nodes = [merge_request.node_id]
            
            # Our partition nodes are the ones that were already with us
            # (This is a simplification - in production you'd track this more carefully)
            our_partition_nodes = [peer.id for peer in all_peers if peer.id != merge_request.node_id and peer.id != raft_node.node_id]
            
            logger.info(f"[MERGE_BIDIRECTIONAL] Partition mapping: "
                       f"Our partition: {our_partition_nodes}, "
                       f"Their partition: {ex_leader_partition_nodes}")
            
            # Step 7: Schedule targeted replication
            # Files from their partition → only to our partition nodes
            if files_we_need:
                import asyncio
                asyncio.create_task(_replicate_merge_files_targeted(
                    files_metadata=[
                        {
                            "file_id": song["url"].split('/')[-1],
                            "nombre": song["nombre"],
                            "autor": song["autor"],
                            "album": song.get("album"),
                            "genero": song.get("genero"),
                            "url": song["url"],
                            "file_size": song["file_size"]
                        }
                        for song in songs_we_need
                    ],
                    target_node_ids=our_partition_nodes  # Only send to our original partition
                ))
            
            logger.info(f"[MERGE_BIDIRECTIONAL] Merge complete. "
                       f"Our partition needs {len(files_we_need)} files (Leader needs), "
                       f"Their partition needs {len(files_they_need)} files (Requester needs)")
            
            # Correct mapping of response keys:
            # files_we_need: Files the Leader needs (Requester should send these)
            # files_you_need: Files the Requester needs (Leader will provide these)
            
            return {
                "success": True,
                "message": "Bidirectional merge processed",
                "files_we_need": files_we_need,    # CORRECTED: Files Leader needs
                "files_you_need": files_they_need, # CORRECTED: Files Requester needs
                "songs_you_need": songs_they_need,  # Songs the requester needs
                "songs_added": len(songs_we_need),
                "merge_strategy": "raft_log_based_optimized",
                "target_nodes_for_their_files": ex_leader_partition_nodes  # Who needs files from their partition
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"[MERGE_BIDIRECTIONAL] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
