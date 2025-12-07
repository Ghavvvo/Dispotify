import asyncio
import grpc
import logging
import time
import socket
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NodeInfo:
    id: str
    address: str
    port: int

    @property
    def grpc_address(self) -> str:
        return f"{self.address}:{self.port}"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, NodeInfo) and self.id == other.id


@dataclass
class CachedNodeAddress:
    node_id: str
    ip_address: str
    port: int
    cached_at: float
    ttl: float = 30.0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.cached_at) > self.ttl

    @property
    def grpc_address(self) -> str:
        return f"{self.ip_address}:{self.port}"


class GRPCClient:
    def __init__(self, timeout: float = 5.0, max_retries: int = 3, cache_ttl: float = 30.0):
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl
        self._channels: Dict[str, grpc.aio.Channel] = {}
        self._routing_table: Dict[str, CachedNodeAddress] = {}

    async def start(self):
        logger.info("gRPC Client iniciado")

    async def resolve_node_address(self, node: NodeInfo) -> str:
        cached = self._routing_table.get(node.id)
        if cached and not cached.is_expired:
            return cached.grpc_address

        try:
            ip_address = await asyncio.get_event_loop().run_in_executor(
                None, socket.gethostbyname, node.address
            )
            self.update_routing_table(node.id, ip_address, node.port)
            return f"{ip_address}:{node.port}"
        except socket.gaierror as e:
            raise GRPCException(f"No se pudo resolver dirección para nodo {node.id}: {e}")

    def update_routing_table(self, node_id: str, ip_address: str, port: int):
        self._routing_table[node_id] = CachedNodeAddress(
            node_id=node_id,
            ip_address=ip_address,
            port=port,
            cached_at=time.time(),
            ttl=self.cache_ttl
        )

    def get_routing_table(self) -> Dict[str, CachedNodeAddress]:
        return self._routing_table.copy()

    def clear_expired_cache(self):
        expired_keys = [
            node_id for node_id, cached in self._routing_table.items()
            if cached.is_expired
        ]
        for node_id in expired_keys:
            del self._routing_table[node_id]

    async def get_channel(self, node: NodeInfo) -> grpc.aio.Channel:
        if node.id not in self._channels:
            address = await self.resolve_node_address(node)
            self._channels[node.id] = grpc.aio.insecure_channel(address)
        return self._channels[node.id]

    async def stop(self):
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()
        logger.info("gRPC Client detenido")


class GRPCException(Exception):
    pass


_grpc_client: Optional[GRPCClient] = None


def initialize_grpc_client(timeout: float = 5.0, max_retries: int = 3) -> GRPCClient:
    global _grpc_client
    _grpc_client = GRPCClient(timeout=timeout, max_retries=max_retries)
    return _grpc_client


def get_grpc_client() -> GRPCClient:
    if _grpc_client is None:
        raise RuntimeError("gRPC Client no inicializado")
    return _grpc_client
