import asyncio
import time
import logging
from typing import Dict, Callable, Awaitable, Any, Optional

from app.distributed.raft import RaftP2PNode, get_raft_node
from app.distributed.communication import NodeInfo, get_p2p_client, P2PClient

logger = logging.getLogger(__name__)


class EventQueue:
    def __init__(
            self,
            raft_node: RaftP2PNode,
            node_id: str,
            use_raft: bool = True
    ):
        self.raft_node = raft_node
        self.node_id = node_id
        self.use_raft = use_raft
        self.p2p_client: Optional[P2PClient] = None
        self._handlers: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._events_published = 0
        self._events_received = 0
        self._register_event_handler()

        logger.info(
            f"Event Queue inicializado para nodo {node_id} "
            f"(mode={'raft' if use_raft else 'broadcast'})"
        )

    async def start(self):
        self.p2p_client = get_p2p_client()
        logger.info("Event Queue iniciado")

    async def stop(self):
        logger.info("Event Queue detenido")



