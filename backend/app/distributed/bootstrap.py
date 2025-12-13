import asyncio
import socket
import logging
import os
from typing import List, Optional
import aiohttp
from app.distributed.communication import NodeInfo, get_p2p_client, P2PException
from app.distributed.netutils import get_local_ip, get_overlay_network

logger = logging.getLogger(__name__)


class DNSBootstrap:

    def __init__(
        self,
        service_name: str,
        port: int = 8000,
        max_retries: int = 5,
        retry_delay: float = 2.0
    ):
        self.service_name = service_name
        self.port = port
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.scan_max_hosts = max(1, int(os.getenv("BOOTSTRAP_MAX_SCAN_HOSTS", "512")))
        self.scan_concurrency = max(1, int(os.getenv("BOOTSTRAP_SCAN_CONCURRENCY", "32")))
        self._local_ip: Optional[str] = None

    async def discover_peers(self) -> List[NodeInfo]:
        peers = []

        for attempt in range(self.max_retries):
            try:
                hostnames = await asyncio.get_event_loop().run_in_executor(
                    None, socket.gethostbyname_ex, self.service_name
                )

                _, _, addresses = hostnames

                for addr in addresses:
                    node_id = f"node-{addr.replace('.', '-')}"
                    peers.append(NodeInfo(
                        id=node_id,
                        address=addr,
                        port=self.port
                    ))

                if peers:
                    logger.info(f"DNS Bootstrap descubrio {len(peers)} peers")
                    return self._deduplicate(peers)

            except socket.gaierror as e:
                logger.warning(
                    f"DNS Bootstrap intento {attempt + 1}/{self.max_retries} fallo: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)

        logger.warning("DNS Bootstrap no pudo descubrir peers via DNS, escaneando red overlay")
        fallback_peers = await self._discover_via_overlay_scan()
        if fallback_peers:
            logger.info(f"Overlay scan descubrio {len(fallback_peers)} peers")
        else:
            logger.warning("No se encontraron peers en el overlay")
        return fallback_peers

    def _deduplicate(self, peers: List[NodeInfo]) -> List[NodeInfo]:
        unique = {}
        for peer in peers:
            unique[peer.address] = peer
        return list(unique.values())

    def _get_local_ip(self) -> Optional[str]:
        if not self._local_ip:
            try:
                self._local_ip = get_local_ip()
            except OSError:
                self._local_ip = None
        return self._local_ip

    async def _discover_via_overlay_scan(self) -> List[NodeInfo]:
        try:
            net = get_overlay_network()
        except OSError as e:
            logger.warning(f"No se pudo obtener red overlay: {e}")
            return []

        local_ip = self._get_local_ip()
        timeout = aiohttp.ClientTimeout(total=1.5)
        session = aiohttp.ClientSession(timeout=timeout)
        semaphore = asyncio.Semaphore(self.scan_concurrency)
        tasks = []
        for idx, ip in enumerate(net.hosts()):
            if idx >= self.scan_max_hosts:
                break
            ip_str = str(ip)
            if ip_str == local_ip:
                continue
            tasks.append(self._probe_host(ip_str, session, semaphore))

        peers: List[NodeInfo] = []
        try:
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, tuple):
                        node_id, addr = result
                        peers.append(NodeInfo(id=node_id, address=addr, port=self.port))
        finally:
            await session.close()

        return self._deduplicate(peers)

    async def _probe_host(self, ip: str, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore):
        url = f"http://{ip}:{self.port}/health"
        async with semaphore:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        node_id = data.get("node_id") or f"node-{ip.replace('.', '-')}"
                        return node_id, ip
            except Exception:
                return None

    async def find_leader(self, peers: List[NodeInfo]) -> Optional[NodeInfo]:
        p2p_client = get_p2p_client()

        for peer in peers:
            try:
                response = await p2p_client.call_rpc(
                    peer,
                    "GET",
                    "/internal/cluster-info",
                    retries=1
                )

                if response.get("is_leader"):
                    logger.info(f"Lider encontrado: {peer.id}")
                    return peer

                leader_id = response.get("leader_id")
                if leader_id:
                    for p in peers:
                        if p.id == leader_id:
                            logger.info(f"Lider encontrado via redirect: {leader_id}")
                            return p

            except P2PException:
                continue

        logger.warning("No se pudo encontrar lider en el cluster")
        return None

    async def register_with_leader(
        self,
        leader: NodeInfo,
        this_node: NodeInfo
    ):
        p2p_client = get_p2p_client()

        try:
            response = await p2p_client.call_rpc(
                leader,
                "POST",
                "/internal/register",
                data={
                    "node_id": this_node.id,
                    "address": this_node.address,
                    "port": this_node.port
                },
                retries=3
            )

            if response.get("success"):
                logger.info(f"Registrado exitosamente con lider {leader.id}")

                cluster_nodes = response.get("cluster_nodes", [])
                return True, cluster_nodes
            else:
                error = response.get("error", "unknown")
                if error == "not_leader":
                    new_leader_id = response.get("leader_id")
                    logger.info(f"Nodo ya no es lider, nuevo lider: {new_leader_id}")
                    return False, []

                logger.error(f"Registro rechazado: {response.get('message')}")
                return False, []

        except P2PException as e:
            logger.error(f"Error registrando con lider: {e}")
            return False, []


_bootstrap: Optional[DNSBootstrap] = None


def initialize_bootstrap(service_name: str, port: int = 8000) -> DNSBootstrap:
    global _bootstrap
    _bootstrap = DNSBootstrap(service_name, port)
    return _bootstrap


def get_bootstrap() -> DNSBootstrap:
    if _bootstrap is None:
        raise RuntimeError("Bootstrap no inicializado")
    return _bootstrap
