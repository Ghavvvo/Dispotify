import asyncio
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from app.distributed.communication import (
    NodeInfo,
    P2PClient,
    get_p2p_client,
    P2PException
)

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    ALIVE = "alive"
    SUSPECTED = "suspected"
    DEAD = "dead"


@dataclass
class NodeHealth:
    node: NodeInfo
    status: NodeStatus
    last_seen: float
    consecutive_failures: int
    response_time_ms: float = 0.0


class ServiceDiscovery:

    def __init__(
            self,
            health_check_interval: float = 5.0,
            failure_threshold: int = 3,
            timeout: float = 2.0
    ):
        self.health_check_interval = health_check_interval
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.node_health: Dict[str, NodeHealth] = {}
        self.p2p_client: Optional[P2PClient] = None
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None

        logger.info("Service Discovery inicializado (modo dinámico)")

    def add_node(self, node: NodeInfo):
        if node.id in self.node_health:
            logger.debug(f"Nodo {node.id} ya existe en discovery")
            return

        self.node_health[node.id] = NodeHealth(
            node=node,
            status=NodeStatus.SUSPECTED,
            last_seen=0.0,
            consecutive_failures=0
        )
        logger.info(f"Nodo {node.id} agregado a Service Discovery")

    def remove_node(self, node_id: str):
        if node_id in self.node_health:
            del self.node_health[node_id]
            logger.info(f"Nodo {node_id} eliminado de Service Discovery")

    def get_all_nodes(self) -> List[NodeInfo]:
        return [health.node for health in self.node_health.values()]

    async def start(self):

        if self._running:
            logger.warning("Service Discovery ya está corriendo")
            return

        self._running = True
        self.p2p_client = get_p2p_client()
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info("P2P Service Discovery iniciado")

    async def stop(self):

        if not self._running:
            return

        logger.info("Deteniendo Service Discovery...")

        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        logger.info("Service Discovery detenido")

    async def _health_check_loop(self):

        while self._running:
            try:
                tasks = []
                for node_id, health in self.node_health.items():
                    task = self._check_node_health(health)
                    tasks.append(task)

                await asyncio.gather(*tasks, return_exceptions=True)

                alive_count = sum(
                    1 for h in self.node_health.values()
                    if h.status == NodeStatus.ALIVE
                )

                self.p2p_client.clear_expired_cache()

                logger.debug(
                    f"Health check completado: {alive_count}/{len(self.node_health)} "
                    f"nodos vivos"
                )
                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                logger.error(f"Error en health check loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _check_node_health(self, health: NodeHealth):

        start_time = time.time()
        was_dead = health.status == NodeStatus.DEAD

        try:

            response = await self.p2p_client.call_rpc(
                node=health.node,
                method="GET",
                endpoint="/health",
                retries=1
            )

            response_time = (time.time() - start_time) * 1000

            health.status = NodeStatus.ALIVE
            health.last_seen = time.time()
            health.consecutive_failures = 0
            health.response_time_ms = response_time

            try:
                import socket
                ip_address = socket.gethostbyname(health.node.address)
                self.p2p_client.update_routing_table(
                    health.node.id,
                    ip_address,
                    health.node.port
                )
            except Exception as e:
                logger.debug(f"No se pudo actualizar routing table para {health.node.id}: {e}")

            if was_dead:
                logger.info(f"Nodo {health.node.id} recuperado de estado DEAD")

            logger.debug(
                f"Nodo {health.node.id} alive "
                f"(response_time={response_time:.1f}ms)"
            )

        except P2PException as e:

            health.consecutive_failures += 1

            if health.consecutive_failures >= self.failure_threshold:
                old_status = health.status
                health.status = NodeStatus.DEAD

                if old_status != NodeStatus.DEAD:
                    logger.warning(
                        f"Nodo {health.node.id} marcado como DEAD "
                        f"(fallos consecutivos: {health.consecutive_failures})"
                    )
            else:
                health.status = NodeStatus.SUSPECTED
                logger.debug(
                    f" Nodo {health.node.id} suspected "
                    f"(fallos: {health.consecutive_failures}/{self.failure_threshold})"
                )

        except Exception as e:
            logger.error(f"Error inesperado chequeando {health.node.id}: {e}")
            health.consecutive_failures += 1

    def get_alive_nodes(self) -> List[NodeInfo]:

        return [
            health.node
            for health in self.node_health.values()
            if health.status == NodeStatus.ALIVE
        ]

    def get_dead_nodes(self) -> List[NodeInfo]:
        return [
            health.node
            for health in self.node_health.values()
            if health.status == NodeStatus.DEAD]

    def is_node_alive(self, node_id: str) -> bool:
        health = self.node_health.get(node_id)
        return health is not None and health.status == NodeStatus.ALIVE

    def get_node_health(self, node_id: str) -> Optional[NodeHealth]:
        return self.node_health.get(node_id)

    def get_all_health(self) -> Dict[str, NodeHealth]:
        return self.node_health.copy()

    def get_cluster_size(self) -> int:
        return len(self.node_health)

    def get_alive_count(self) -> int:
        return sum(
            1 for h in self.node_health.values()
            if h.status == NodeStatus.ALIVE
        )


discovery: Optional[ServiceDiscovery] = None


def initialize_discovery(**kwargs) -> ServiceDiscovery:
    global discovery
    discovery = ServiceDiscovery(**kwargs)
    return discovery


def get_discovery() -> ServiceDiscovery:
    if discovery is None:
        raise RuntimeError("Service Discovery no inicializado")
    return discovery

