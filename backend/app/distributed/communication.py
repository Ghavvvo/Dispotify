import asyncio
import aiohttp
import logging
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


class P2PClient:

    def __init__(self, timeout: float = 5.0, max_retries: int = 3):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):

        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            json_serialize=json.dumps
        )
        logger.info("P2P HTTP Client iniciado")

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
        url = f"{node.url}{endpoint}"
        last_error = None

        for attempt in range(retries):
            try:
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
                    f"RPC {method} {url} error: {e}, "
                    f"reintento {attempt + 1}/{retries}"
                )
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            except asyncio.TimeoutError:
                last_error = "Timeout"
                logger.warning(
                    f"RPC {method} {url} timeout, "
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


class P2PException(Exception):
    pass


def parse_cluster_nodes(nodes_str: str) -> List[NodeInfo]:
    nodes = []

    for i, node_part in enumerate(nodes_str.split(",")):
        parts = node_part.strip().split(":")

        if len(parts) == 3:

            node_id, address, port = parts
        elif len(parts) == 2:

            address, port = parts
            node_id = f"node{i + 1}"
        else:
            raise ValueError(
                f"Formato inválido para nodo: {node_part}. "
                f"Debe ser 'id:address:port' o 'address:port'"
            )

        nodes.append(NodeInfo(
            id=node_id,
            address=address,
            port=int(port)
        ))

    return nodes


_p2p_client: Optional[P2PClient] = None


def initialize_p2p_client(timeout: float = 5.0, max_retries: int = 3) -> P2PClient:
    global _p2p_client
    _p2p_client = P2PClient(timeout=timeout, max_retries=max_retries)
    return _p2p_client


def get_p2p_client() -> P2PClient:
    if _p2p_client is None:
        raise RuntimeError("P2P Client no inicializado")
    return _p2p_client