

import hashlib
from typing import List, Optional, Dict, Set
from bisect import bisect_right
import logging

logger = logging.getLogger(__name__)


class ConsistentHashRing:
    
    
    def __init__(self, nodes: List[str] = None, virtual_nodes: int = 150):
        
        self.virtual_nodes = virtual_nodes
        
        
        self.ring: Dict[int, str] = {}
        
        
        self.sorted_keys: List[int] = []
        
        
        self.node_map: Dict[str, List[int]] = {}
        
        
        if nodes:
            for node in nodes:
                self.add_node(node)
        
        logger.info(
            f"Consistent Hash Ring inicializado con {len(nodes or [])} nodos "
            f"y {virtual_nodes} nodos virtuales por nodo"
        )
    
    def _hash(self, key: str) -> int:
        
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)
    
    def add_node(self, node_id: str):
        
        if node_id in self.node_map:
            logger.warning(f"Nodo {node_id} ya existe en el ring")
            return
        
        self.node_map[node_id] = []
        
        
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_value = self._hash(virtual_key)
            
            self.ring[hash_value] = node_id
            self.node_map[node_id].append(hash_value)
        
        
        self.sorted_keys = sorted(self.ring.keys())
        
        logger.info(
            f"Nodo añadido al ring: {node_id} "
            f"({self.virtual_nodes} nodos virtuales)"
        )
    
    def remove_node(self, node_id: str):
        
        if node_id not in self.node_map:
            logger.warning(f"Nodo {node_id} no existe en el ring")
            return
        
        
        for hash_value in self.node_map[node_id]:
            del self.ring[hash_value]
        
        del self.node_map[node_id]
        
        
        self.sorted_keys = sorted(self.ring.keys())
        
        logger.info(f"Nodo eliminado del ring: {node_id}")
    
    def get_node(self, key: str) -> Optional[str]:
        
        if not self.ring:
            return None
        
        hash_value = self._hash(key)
        
        
        index = bisect_right(self.sorted_keys, hash_value)
        
        
        if index == len(self.sorted_keys):
            index = 0
        
        return self.ring[self.sorted_keys[index]]
    
    def get_nodes(self, key: str, count: int = 1) -> List[str]:
        
        if not self.ring or count < 1:
            return []
        
        
        count = min(count, len(self.node_map))
        
        hash_value = self._hash(key)
        nodes: List[str] = []
        nodes_set: Set[str] = set()
        
        
        index = bisect_right(self.sorted_keys, hash_value)
        
        
        iterations = 0
        max_iterations = len(self.sorted_keys)
        
        while len(nodes) < count and iterations < max_iterations:
            
            if index >= len(self.sorted_keys):
                index = 0
            
            node_id = self.ring[self.sorted_keys[index]]
            
            
            if node_id not in nodes_set:
                nodes.append(node_id)
                nodes_set.add(node_id)
            
            index += 1
            iterations += 1
        
        return nodes
    
    def get_node_load(self) -> Dict[str, int]:
        
        return {
            node_id: len(virtual_nodes)
            for node_id, virtual_nodes in self.node_map.items()
        }
    
    def get_stats(self) -> dict:
        
        return {
            "total_nodes": len(self.node_map),
            "virtual_nodes_per_node": self.virtual_nodes,
            "total_virtual_nodes": len(self.ring),
            "ring_size": len(self.sorted_keys),
            "nodes": list(self.node_map.keys())
        }
    
    def redistribute_keys(
        self,
        keys: List[str]
    ) -> Dict[str, List[str]]:
        
        distribution: Dict[str, List[str]] = {
            node_id: [] for node_id in self.node_map.keys()
        }
        
        for key in keys:
            node = self.get_node(key)
            if node:
                distribution[node].append(key)
        
        return distribution
    
    def __len__(self) -> int:
        
        return len(self.node_map)
    
    def __contains__(self, node_id: str) -> bool:
        
        return node_id in self.node_map
    
    def __repr__(self) -> str:
        return (
            f"ConsistentHashRing("
            f"nodes={len(self.node_map)}, "
            f"virtual_nodes={self.virtual_nodes})"
        )


class ReplicaManager:
    
    
    def __init__(
        self,
        hash_ring: ConsistentHashRing,
        replication_factor: int = 3
    ):
        
        self.hash_ring = hash_ring
        self.replication_factor = replication_factor
        
        logger.info(
            f"Replica Manager inicializado con factor de replicación: "
            f"{replication_factor}"
        )
    
    def get_replica_nodes(self, key: str) -> List[str]:
        
        return self.hash_ring.get_nodes(key, self.replication_factor)
    
    def should_store(self, key: str, node_id: str) -> bool:
        
        replica_nodes = self.get_replica_nodes(key)
        return node_id in replica_nodes
    
    def get_replication_plan(
        self,
        keys: List[str]
    ) -> Dict[str, Dict[str, List[str]]]:
        
        plan = {}
        
        for key in keys:
            replica_nodes = self.get_replica_nodes(key)
            plan[key] = {
                "primary": replica_nodes[0] if replica_nodes else None,
                "replicas": replica_nodes[1:] if len(replica_nodes) > 1 else []
            }
        
        return plan

