import httpx
import logging
import os
import socket
from pydantic import BaseModel
from typing import List, Optional

logger = logging.getLogger(__name__)

class NodeInfo(BaseModel):
    id: str
    address: str
    port: int
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, NodeInfo):
            return self.id == other.id
        return False

class CommunicationLayer:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=2.0)

    async def send_rpc(self, target_node: NodeInfo, method: str, endpoint: str, data: dict = None):
        url = f"http://{target_node.address}:{target_node.port}{endpoint}"
        try:
            if method == "POST":
                response = await self.client.post(url, json=data)
            elif method == "GET":
                response = await self.client.get(url, params=data)
            else:
                return None
            
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            return None

    def discover_nodes(self, service_name: str = "dispotify-cluster") -> List[str]:
        try:
            _, _, ip_list = socket.gethostbyname_ex(service_name)
            return ip_list
        except socket.gaierror:
            return []

class P2PException(Exception):
    pass

class P2PClient:
    def __init__(self):
        pass

    async def forward_upload(self, node: NodeInfo, endpoint: str, file_content: bytes, filename: str, form_data: dict):
        import httpx
        url = f"http://{node.address}:{node.port}{endpoint}"
        try:
            files = {'file': (filename, file_content)}
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, data=form_data, files=files, timeout=30.0)
                if resp.status_code in [200, 201]:
                    return {"status": resp.status_code, "data": resp.json()}
                else:
                    raise P2PException(f"Forward failed: {resp.status_code} {resp.text}")
        except Exception as e:
            raise P2PException(str(e))

_p2p_client = P2PClient()

def get_p2p_client():
    return _p2p_client
