import asyncio
import aiohttp
import aiofiles
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
import json
import time

from app.distributed.raft import RaftNode, get_raft_node
from app.distributed.communication import (
    NodeInfo,
    P2PClient,
    get_p2p_client,
    P2PException
)
from app.distributed.consistent_hash import ConsistentHashRing

logger = logging.getLogger(__name__)


@dataclass
class FileReplica:
    
    file_id: str
    node_id: str
    file_path: str
    file_size: int
    checksum: str
    replicated_at: float


class P2PReplicationManager:
    
    
    def __init__(
        self,
        raft_node: RaftNode,
        node_id: str,
        storage_path: Path,
        hash_ring: ConsistentHashRing,
        replication_factor: int = 3
    ):
        self.raft_node = raft_node
        self.node_id = node_id
        self.storage_path = Path(storage_path)
        self.hash_ring = hash_ring
        self.replication_factor = replication_factor
        self.p2p_client: Optional[P2PClient] = None
        
        
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        
        self._register_replication_handler()
        
        logger.info(
            f"P2P Replication Manager inicializado "
            f"(storage={storage_path}, factor={replication_factor})"
        )
    
    async def start(self):
        
        self.p2p_client = get_p2p_client()
        logger.info("P2P Replication Manager iniciado")
    
    async def stop(self):
        
        logger.info("P2P Replication Manager detenido")
    
    def _register_replication_handler(self):
        
        original_callback = self.raft_node._on_command_applied
        
        async def combined_callback(command: dict):
            
            if command.get("type") == "file_replicated":
                await self._handle_file_replicated(command)
            
            
            if original_callback:
                await original_callback(command)
        
        self.raft_node._on_command_applied = combined_callback
    
    async def _handle_file_replicated(self, command: dict):
        
        file_id = command.get("file_id")
        replicas = command.get("replicas", [])
        
        
        self.raft_node.state_machine[f"file_replicas:{file_id}"] = {
            "file_id": file_id,
            "replicas": replicas,
            "replication_factor": len(replicas),
            "created_at": command.get("timestamp")
        }
        
        logger.info(
            f"Archivo {file_id} replicado a {len(replicas)} nodos: {replicas}"
        )
    
    def _select_replica_nodes(self, file_id: str) -> List[NodeInfo]:
        
        
        node_ids = self.hash_ring.get_nodes(file_id, self.replication_factor)
        
        
        all_nodes = [self.raft_node.node_info] + self.raft_node.cluster_nodes
        selected_nodes = []
        
        for node_id in node_ids:
            node = next((n for n in all_nodes if n.id == node_id), None)
            if node:
                selected_nodes.append(node)
        
        return selected_nodes
    
    async def _calculate_checksum(self, file_path: Path) -> str:
        
        sha256 = hashlib.sha256()
        
        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    async def replicate_file(
        self,
        file_id: str,
        file_path: Path,
        metadata: Optional[Dict] = None
    ) -> bool:
        
        if not self.raft_node.is_leader():
            leader_id = self.raft_node.get_leader()
            raise Exception(
                f"Este nodo no es líder. Redirigir replicación a {leader_id}"
            )
        
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
        
        logger.info(f"Iniciando replicación de archivo {file_id}")
        
        
        checksum = await self._calculate_checksum(file_path)
        file_size = file_path.stat().st_size
        
        
        target_nodes = self._select_replica_nodes(file_id)
        
        
        target_nodes = [n for n in target_nodes if n.id != self.node_id]
        
        if not target_nodes:
            logger.warning(
                f"No hay otros nodos disponibles para replicar {file_id}"
            )
            return True
        
        logger.info(
            f"Replicando {file_id} a {len(target_nodes)} nodos: "
            f"{[n.id for n in target_nodes]}"
        )
        
        
        tasks = []
        for node in target_nodes:
            task = self._send_file_to_node(
                node=node,
                file_id=file_id,
                file_path=file_path,
                checksum=checksum,
                metadata=metadata or {}
            )
            tasks.append(task)
        
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        
        successful_nodes = []
        for i, result in enumerate(results):
            if not isinstance(result, Exception) and result:
                successful_nodes.append(target_nodes[i].id)
            else:
                error = result if isinstance(result, Exception) else "Unknown error"
                logger.error(
                    f"Error replicando a {target_nodes[i].id}: {error}"
                )
        
        
        total_replicas = len(successful_nodes) + 1  
        
        if total_replicas < self.replication_factor:
            logger.warning(
                f"Replicación incompleta: {total_replicas}/{self.replication_factor} "
                f"réplicas"
            )
        
        
        command = {
            "type": "file_replicated",
            "file_id": file_id,
            "replicas": successful_nodes + [self.node_id],
            "checksum": checksum,
            "file_size": file_size,
            "metadata": metadata or {},
            "timestamp": time.time()
        }
        
        try:
            await self.raft_node.submit_command(command, timeout=5.0)
            logger.info(
                f"Archivo {file_id} replicado exitosamente "
                f"({total_replicas} réplicas)"
            )
            return True
        except Exception as e:
            logger.error(f"Error registrando replicación en Raft: {e}")
            return False
    
    async def _send_file_to_node(
        self,
        node: NodeInfo,
        file_id: str,
        file_path: Path,
        checksum: str,
        metadata: Dict
    ) -> bool:
        
        try:
            logger.debug(f"Enviando {file_id} a {node.id}...")
            
            
            metadata_json = json.dumps({
                "file_id": file_id,
                "checksum": checksum,
                "original_name": file_path.name,
                **metadata
            })
            
            
            async with aiofiles.open(file_path, 'rb') as f:
                file_data = await f.read()
            
            data = aiohttp.FormData()
            data.add_field(
                'file',
                file_data,
                filename=file_path.name,
                content_type='application/octet-stream'
            )
            data.add_field('metadata', metadata_json)
            
            
            url = f"{node.url}/internal/replicate"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(
                            f"✅ Archivo {file_id} enviado a {node.id} "
                            f"({result.get('checksum')})"
                        )
                        return True
                    else:
                        text = await response.text()
                        logger.error(
                            f"Error HTTP {response.status} enviando a {node.id}: {text}"
                        )
                        return False
                        
        except asyncio.TimeoutError:
            logger.error(f"Timeout enviando {file_id} a {node.id}")
            return False
        except Exception as e:
            logger.error(f"Error enviando {file_id} a {node.id}: {e}")
            return False
    
    async def receive_file(
        self,
        file_data: bytes,
        metadata: Dict
    ) -> Dict:
        
        file_id = metadata.get("file_id")
        expected_checksum = metadata.get("checksum")
        original_name = metadata.get("original_name", file_id)
        
        logger.info(f"Recibiendo réplica de archivo {file_id}")
        
        
        temp_path = self.storage_path / f"{file_id}.tmp"
        final_path = self.storage_path / original_name
        
        try:
            
            async with aiofiles.open(temp_path, 'wb') as f:
                await f.write(file_data)
            
            
            actual_checksum = await self._calculate_checksum(temp_path)
            
            if actual_checksum != expected_checksum:
                temp_path.unlink()
                raise Exception(
                    f"Checksum mismatch: expected {expected_checksum}, "
                    f"got {actual_checksum}"
                )
            
            
            temp_path.rename(final_path)
            
            logger.info(
                f"✅ Archivo {file_id} recibido y verificado "
                f"(checksum={actual_checksum})"
            )
            
            return {
                "status": "success",
                "file_id": file_id,
                "checksum": actual_checksum,
                "file_size": len(file_data),
                "path": str(final_path)
            }
            
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            
            logger.error(f"Error recibiendo archivo {file_id}: {e}")
            raise
    
    def get_file_replicas(self, file_id: str) -> Optional[Dict]:
        
        return self.raft_node.state_machine.get(f"file_replicas:{file_id}")
    
    def get_all_replicas(self) -> Dict[str, Dict]:
        
        replicas = {}
        for key, value in self.raft_node.state_machine.items():
            if key.startswith("file_replicas:"):
                file_id = key.split(":", 1)[1]
                replicas[file_id] = value
        return replicas
    
    async def verify_replica(self, file_id: str, file_path: Path) -> bool:
        
        replica_info = self.get_file_replicas(file_id)
        
        if not replica_info:
            logger.warning(f"No hay info de réplicas para {file_id}")
            return False
        
        if not file_path.exists():
            logger.warning(f"Archivo no existe: {file_path}")
            return False
        
        
        actual_checksum = await self._calculate_checksum(file_path)
        expected_checksum = replica_info.get("checksum")
        
        if actual_checksum == expected_checksum:
            logger.info(f"Réplica de {file_id} verificada correctamente")
            return True
        else:
            logger.error(
                f"❌ Checksum mismatch para {file_id}: "
                f"expected {expected_checksum}, got {actual_checksum}"
            )
            return False
    
    async def delete_file(self, file_id: str) -> bool:
        
        if not self.raft_node.is_leader():
            leader_id = self.raft_node.get_leader()
            raise Exception(f"No soy líder, redirigir a {leader_id}")
        
        logger.info(f"Eliminando archivo {file_id} del cluster")
        
        
        replica_info = self.get_file_replicas(file_id)
        
        if not replica_info:
            logger.warning(f"No hay info de réplicas para {file_id}")
            return False
        
        replica_nodes = replica_info.get("replicas", [])
        
        
        all_nodes = [self.raft_node.node_info] + self.raft_node.cluster_nodes
        target_nodes = [n for n in all_nodes if n.id in replica_nodes]
        
        tasks = []
        for node in target_nodes:
            task = self._delete_file_on_node(node, file_id)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        
        command = {
            "type": "file_deleted",
            "file_id": file_id,
            "timestamp": time.time()
        }
        
        await self.raft_node.submit_command(command, timeout=5.0)
        
        
        key = f"file_replicas:{file_id}"
        if key in self.raft_node.state_machine:
            del self.raft_node.state_machine[key]
        
        logger.info(f"Archivo {file_id} eliminado del cluster")
        return True
    
    async def _delete_file_on_node(self, node: NodeInfo, file_id: str) -> bool:
        
        try:
            response = await self.p2p_client.call_rpc(
                node=node,
                method="DELETE",
                endpoint=f"/internal/file/{file_id}",
                retries=2
            )
            return response.get("success", False)
        except Exception as e:
            logger.error(f"Error eliminando {file_id} de {node.id}: {e}")
            return False



_p2p_replication_manager: Optional[P2PReplicationManager] = None


def initialize_p2p_replication_manager(
    raft_node: RaftNode,
    node_id: str,
    storage_path: Path,
    hash_ring: ConsistentHashRing,
    replication_factor: int = 3
) -> P2PReplicationManager:
    
    global _p2p_replication_manager
    _p2p_replication_manager = P2PReplicationManager(
        raft_node=raft_node,
        node_id=node_id,
        storage_path=storage_path,
        hash_ring=hash_ring,
        replication_factor=replication_factor
    )
    return _p2p_replication_manager


def get_p2p_replication_manager() -> P2PReplicationManager:
    
    if _p2p_replication_manager is None:
        raise RuntimeError("Replication Manager no inicializado")
    return _p2p_replication_manager