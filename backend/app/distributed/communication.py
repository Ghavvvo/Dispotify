import asyncio
import aiohttp
import logging
import time
import socket
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class NodeInfo:
    id: str
    address: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}"

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
    def url(self) -> str:
        return f"http://{self.ip_address}:{self.port}"


class P2PClient:

    def __init__(self, timeout: float = 5.0, max_retries: int = 3, cache_ttl: float = 30.0):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl
        self._session: Optional[aiohttp.ClientSession] = None
        self._routing_table: Dict[str, CachedNodeAddress] = {}

    async def start(self):

        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            json_serialize=json.dumps
        )
        logger.info("P2P HTTP Client iniciado")

    async def resolve_node_address(self, node: NodeInfo) -> str:
        cached = self._routing_table.get(node.id)
        if cached and not cached.is_expired:
            logger.debug(f"Caché hit para {node.id}: {cached.ip_address}")
            return cached.url

        try:
            ip_address = await asyncio.get_event_loop().run_in_executor(
                None, socket.gethostbyname, node.address
            )

            self.update_routing_table(node.id, ip_address, node.port)

            logger.debug(f"DNS resolvió {node.address} -> {ip_address} para {node.id}")
            return f"http://{ip_address}:{node.port}"

        except socket.gaierror as e:
            error_msg = (
                f"No se pudo resolver dirección para nodo {node.id} (hostname: {node.address}). "
                f"DNS falló: {e}. No hay caché válida disponible."
            )
            logger.error(error_msg)
            raise P2PException(error_msg)

    def update_routing_table(self, node_id: str, ip_address: str, port: int):
        self._routing_table[node_id] = CachedNodeAddress(
            node_id=node_id,
            ip_address=ip_address,
            port=port,
            cached_at=time.time(),
            ttl=self.cache_ttl
        )
        logger.debug(f"Tabla de routing actualizada: {node_id} -> {ip_address}:{port}")

    def get_routing_table(self) -> Dict[str, CachedNodeAddress]:
        return self._routing_table.copy()

    def clear_expired_cache(self):
        expired_keys = [
            node_id for node_id, cached in self._routing_table.items()
            if cached.is_expired
        ]
        for node_id in expired_keys:
            del self._routing_table[node_id]
            logger.debug(f"Entrada de caché expirada eliminada: {node_id}")

    async def stop(self):

        if self._session:
            await self._session.close()
            self._session = None
        logger.info("P2P HTTP Client detenido")

    async def call_rpc(
            self,
            node: NodeInfo,
            method: str,
            endpoint: str,
            data: Optional[Dict[str, Any]] = None,
            retries: Optional[int] = None
    ) -> Dict[str, Any]:

        if not self._session:
            raise P2PException("Client no iniciado, llama a start() primero")

        retries = retries if retries is not None else self.max_retries
        last_error = None

        for attempt in range(retries):
            try:
                # Resolver dirección usando la estrategia híbrida
                resolved_url = await self.resolve_node_address(node)
                url = f"{resolved_url}{endpoint}"

                async with self._session.request(
                        method,
                        url,
                        json=data
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status >= 500:

                        last_error = f"Server error {response.status}"
                        logger.warning(
                            f"RPC {method} {url} falló con {response.status}, "
                            f"reintento {attempt + 1}/{retries}"
                        )
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                    else:

                        text = await response.text()
                        raise P2PException(
                            f"RPC failed: {response.status} - {text}"
                        )

            except aiohttp.ClientError as e:
                last_error = str(e)
                logger.warning(
                    f"RPC {method} a {node.id} error: {e}, "
                    f"reintento {attempt + 1}/{retries}"
                )
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            except asyncio.TimeoutError:
                last_error = "Timeout"
                logger.warning(
                    f"RPC {method} a {node.id} timeout, "
                    f"reintento {attempt + 1}/{retries}"
                )
                await asyncio.sleep(0.1 * (attempt + 1))
                continue

        raise P2PException(
            f"RPC {method} {endpoint} a {node.id} falló después de "
            f"{retries} intentos: {last_error}"
        )

    async def broadcast(
            self,
            nodes: List[NodeInfo],
            method: str,
            endpoint: str,
            data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Dict[str, Any]]:

        tasks = []
        node_ids = []

        for node in nodes:
            task = self.call_rpc(node, method, endpoint, data, retries=1)
            tasks.append(task)
            node_ids.append(node.id)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        responses = {}
        for node_id, result in zip(node_ids, results):
            if not isinstance(result, Exception):
                responses[node_id] = result
            else:
                logger.warning(f"Broadcast a {node_id} falló: {result}")

        return responses

    async def forward_upload(
            self,
            node: NodeInfo,
            endpoint: str,
            file_content: bytes,
            filename: str,
            form_data: Dict[str, Any],
            retries: Optional[int] = None
    ) -> Dict[str, Any]:
        if not self._session:
            raise P2PException("Client no iniciado")

        retries = retries if retries is not None else self.max_retries
        last_error = None

        for attempt in range(retries):
            try:
                resolved_url = await self.resolve_node_address(node)
                url = f"{resolved_url}{endpoint}"

                data = aiohttp.FormData()

                for key, value in form_data.items():
                    if value is not None:
                        data.add_field(key, str(value))

                data.add_field(
                    'file',
                    file_content,
                    filename=filename,
                    content_type='application/octet-stream'
                )

                async with self._session.post(url, data=data) as response:
                    response_data = await response.json()

                    if response.status in (200, 201):
                        return {"status": response.status, "data": response_data}
                    elif response.status >= 500:
                        last_error = f"Server error {response.status}"
                        logger.warning(
                            f"Forward upload a {url} falló con {response.status}, "
                            f"reintento {attempt + 1}/{retries}"
                        )
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                    else:
                        return {"status": response.status, "data": response_data}

            except aiohttp.ClientError as e:
                last_error = str(e)
                logger.warning(
                    f"Forward upload a {node.id} error: {e}, "
                    f"reintento {attempt + 1}/{retries}"
                )
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            except asyncio.TimeoutError:
                last_error = "Timeout"
                logger.warning(
                    f"Forward upload a {node.id} timeout, "
                    f"reintento {attempt + 1}/{retries}"
                )
                await asyncio.sleep(0.1 * (attempt + 1))
                continue

        raise P2PException(
            f"Forward upload a {node.id} falló después de "
            f"{retries} intentos: {last_error}"
        )


class P2PException(Exception):
    pass




_p2p_client: Optional[P2PClient] = None


def initialize_p2p_client(timeout: float = 5.0, max_retries: int = 3) -> P2PClient:
    global _p2p_client
    _p2p_client = P2PClient(timeout=timeout, max_retries=max_retries)
    return _p2p_client


def get_p2p_client() -> P2PClient:
    if _p2p_client is None:
        raise RuntimeError("P2P Client no inicializado")
    return _p2p_client