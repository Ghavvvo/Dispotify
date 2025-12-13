import asyncio
import socket
import logging
import os
from typing import List
from app.distributed.communication import NodeInfo

logger = logging.getLogger(__name__)

class DNSBootstrap:
    def __init__(self, service_name: str, port: int = 8000):
        self.service_name = service_name
        self.port = port

    async def discover_peers(self) -> List[NodeInfo]:
        try:
            # Resolver el nombre del servicio para obtener todas las IPs de los contenedores
            hostnames = await asyncio.get_event_loop().run_in_executor(
                None, socket.gethostbyname_ex, self.service_name
            )
            _, _, addresses = hostnames
            
            peers = []
            for addr in addresses:
                # Generar ID basado en IP (convención simple para Docker)
                node_id = f"node-{addr.replace('.', '-')}"
                peers.append(NodeInfo(id=node_id, address=addr, port=self.port))
            
            logger.info(f"DNS Bootstrap: encontrados {len(peers)} peers para {self.service_name}")
            return peers
        except Exception as e:
            logger.warning(f"DNS Bootstrap falló para {self.service_name}: {e}")
            return []
