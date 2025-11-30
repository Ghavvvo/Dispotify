import asyncio
import time
import logging
from typing import Dict, Callable, Awaitable, Any, Optional
from app.distributed.raft import RaftNode, get_raft_node
from app.distributed.communication import NodeInfo, get_p2p_client, P2PClient

logger = logging.getLogger(__name__)


class EventQueue:
    def __init__(
            self,
            raft_node: RaftNode,
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

    def _register_event_handler(self):
        original_callback = self.raft_node._on_command_applied

        async def combined_callback(command: dict):
            if command.get("type") == "event":
                await self._handle_event(command)

            if original_callback:
                await original_callback(command)

        self.raft_node._on_command_applied = combined_callback

    async def _handle_event(self, command: dict):

        event_type = command.get("event_type")
        event_data = command.get("data")
        self._events_received += 1
        handler = self._handlers.get(event_type)

        if handler:
            try:
                await handler(event_data)
                logger.debug(f"Evento '{event_type}' procesado exitosamente")
            except Exception as e:
                logger.error(
                    f"Error procesando evento '{event_type}': {e}",
                    exc_info=True
                )
        else:
            logger.debug(
                f"No hay handler registrado para evento '{event_type}', ignorando"
            )

    async def publish(
            self,
            event_type: str,
            data: dict,
            timeout: float = 5.0
    ) -> bool:

        self._events_published += 1

        if self.use_raft:
            return await self._publish_via_raft(event_type, data, timeout)
        else:
            return await self._publish_via_broadcast(event_type, data)

    async def _publish_via_raft(
            self,
            event_type: str,
            data: dict,
            timeout: float
    ) -> bool:

        try:
            command = {
                "type": "event",
                "event_type": event_type,
                "data": data,
                "publisher": self.node_id,
                "timestamp": time.time()
            }

            success = await self.raft_node.submit_command(command, timeout=timeout)
            if success:
                logger.info(f"Evento '{event_type}' publicado via Raft")
                return True
            else:
                logger.warning(
                    f"Evento '{event_type}' no se replicó a mayoría del cluster"
                )
                return False
        except Exception as e:
            logger.error(f"Error publicando evento via Raft: {e}")
            return False

    async def _publish_via_broadcast(
            self,
            event_type: str,
            data: dict
    ) -> bool:

        try:

            all_nodes = self.raft_node.cluster_nodes

            event_payload = {
                "event_type": event_type,
                "data": data,
                "publisher": self.node_id,
                "timestamp": time.time()
            }

            responses = await self.p2p_client.broadcast(
                nodes=all_nodes,
                method="POST",
                endpoint="/internal/event",
                data=event_payload
            )

            logger.info(
                f"Evento '{event_type}' enviado via broadcast "
                f"({len(responses)}/{len(all_nodes)} nodos respondieron)"
            )

            return len(responses) > 0

        except Exception as e:
            logger.error(f"Error publicando evento via broadcast: {e}")
            return False

    def subscribe(
            self,
            event_type: str,
            handler: Callable[[dict], Awaitable[None]]
    ):

        if event_type in self._handlers:
            logger.warning(
                f"Ya existe handler para '{event_type}', sobrescribiendo"
            )

        self._handlers[event_type] = handler
        logger.info(f"Handler registrado para evento '{event_type}'")

    def unsubscribe(self, event_type: str):

        if event_type in self._handlers:
            del self._handlers[event_type]
            logger.info(f"Handler removido para evento '{event_type}'")

    async def handle_incoming_event(self, event: dict):

        event_type = event.get("event_type")
        data = event.get("data")

        if event_type and data:
            handler = self._handlers.get(event_type)
            if handler:
                try:
                    await handler(data)
                    logger.debug(
                        f"Evento broadcast '{event_type}' procesado"
                    )
                except Exception as e:
                    logger.error(
                        f"Error procesando evento broadcast '{event_type}': {e}"
                    )

    def get_stats(self) -> dict:

        return {
            "events_published": self._events_published,
            "events_received": self._events_received,
            "handlers_registered": len(self._handlers),
            "handler_types": list(self._handlers.keys()),
            "mode": "raft" if self.use_raft else "broadcast"
        }


_event_queue: Optional[EventQueue] = None


def initialize_event_queue(
        raft_node: RaftNode,
        node_id: str,
        use_raft: bool = True
) -> EventQueue:
    global _event_queue
    _event_queue = EventQueue(raft_node, node_id, use_raft)
    return _event_queue


def get_event_queue() -> EventQueue:
    if _event_queue is None:
        raise RuntimeError("Event Queue no inicializado")
    return _event_queue

