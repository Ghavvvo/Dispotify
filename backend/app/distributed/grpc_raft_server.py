import grpc
import json
import logging
from typing import Optional
from concurrent import futures

try:
    from app.distributed.proto import raft_pb2, raft_pb2_grpc
except ImportError:
    raft_pb2 = None
    raft_pb2_grpc = None

logger = logging.getLogger(__name__)


class RaftServicer:
    def __init__(self, raft_node):
        self.raft_node = raft_node

    async def RequestVote(self, request, context):
        request_dict = {
            "term": request.term,
            "candidate_id": request.candidate_id,
            "last_log_index": request.last_log_index,
            "last_log_term": request.last_log_term
        }
        
        response_dict = await self.raft_node.handle_request_vote(request_dict)
        
        return raft_pb2.RequestVoteResponse(
            term=response_dict["term"],
            vote_granted=response_dict["vote_granted"],
            from_node=response_dict["from_node"]
        )

    async def AppendEntries(self, request, context):
        entries = []
        for entry in request.entries:
            entries.append({
                "term": entry.term,
                "index": entry.index,
                "command": json.loads(entry.command)
            })
        
        request_dict = {
            "term": request.term,
            "leader_id": request.leader_id,
            "prev_log_index": request.prev_log_index,
            "prev_log_term": request.prev_log_term,
            "entries": entries,
            "leader_commit": request.leader_commit
        }
        
        response_dict = await self.raft_node.handle_append_entries(request_dict)
        
        return raft_pb2.AppendEntriesResponse(
            term=response_dict["term"],
            success=response_dict["success"],
            from_node=response_dict["from_node"]
        )

    async def GetStatus(self, request, context):
        status = self.raft_node.get_status()
        
        return raft_pb2.GetStatusResponse(
            node_id=status["node_id"],
            state=status["state"],
            term=status["term"],
            leader_id=status.get("leader_id", ""),
            log_size=status["log_size"],
            commit_index=status["commit_index"],
            last_applied=status["last_applied"],
            cluster_size=status["cluster_size"]
        )


class GRPCRaftServer:
    def __init__(self, raft_node, port: int, max_workers: int = 10):
        self.raft_node = raft_node
        self.port = port
        self.max_workers = max_workers
        self.server: Optional[grpc.aio.Server] = None

    async def start(self):
        if raft_pb2 is None or raft_pb2_grpc is None:
            raise RuntimeError("Proto files not generated. Run generate_protos.py first")
        
        self.server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=self.max_workers))
        
        servicer = RaftServicer(self.raft_node)
        raft_pb2_grpc.add_RaftServiceServicer_to_server(servicer, self.server)
        
        self.server.add_insecure_port(f"[::]:{self.port}")
        await self.server.start()
        
        logger.info(f"gRPC Raft Server iniciado en puerto {self.port}")

    async def stop(self):
        if self.server:
            await self.server.stop(grace=5)
            logger.info("gRPC Raft Server detenido")


_grpc_raft_server: Optional[GRPCRaftServer] = None


def initialize_grpc_raft_server(raft_node, port: int) -> GRPCRaftServer:
    global _grpc_raft_server
    _grpc_raft_server = GRPCRaftServer(raft_node, port)
    return _grpc_raft_server


def get_grpc_raft_server() -> GRPCRaftServer:
    if _grpc_raft_server is None:
        raise RuntimeError("gRPC Raft Server no inicializado")
    return _grpc_raft_server
