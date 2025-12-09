
import asyncio
import time
import random
import json
import logging
from enum import Enum
from typing import List, Optional, Dict, Callable, Awaitable, Any
from dataclasses import dataclass
from pathlib import Path
import aiofiles

from app.distributed.communication import (
    P2PClient,
    NodeInfo,
    P2PException,
    get_p2p_client
)

logger = logging.getLogger(__name__)


class NodeState(Enum):

    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class LogEntry:

    term: int
    index: int
    command: Dict[str, Any]

    def to_dict(self):
        return {
            "term": self.term,
            "index": self.index,
            "command": self.command
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            term=data["term"],
            index=data["index"],
            command=data["command"]
        )
class RaftNode:


    def __init__(
            self,
            node_id: str,
            node_info: NodeInfo,
            cluster_nodes: Optional[List[NodeInfo]] = None,
            data_dir: str = "/data/raft",
            election_timeout_min: float = 1.5,
            election_timeout_max: float = 3.0,
            heartbeat_interval: float = 0.5
    ):
        self.node_id = node_id
        self.node_info = node_info
        self.cluster_nodes = [n for n in (cluster_nodes or []) if n.id != node_id]
        self.data_dir = Path(data_dir)
        self.election_timeout_min = election_timeout_min
        self.election_timeout_max = election_timeout_max
        self.heartbeat_interval = heartbeat_interval


        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = []


        self.state = NodeState.FOLLOWER
        self.leader_id: Optional[str] = None
        self.commit_index = -1
        self.last_applied = -1


        self.next_index: Dict[str, int] = {}
        self.match_index: Dict[str, int] = {}


        self._running = False
        self.last_heartbeat = time.time()
        self._election_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None


        self._on_become_leader: Optional[Callable[[], Awaitable[None]]] = None
        self._on_lose_leadership: Optional[Callable[[], Awaitable[None]]] = None
        self._on_command_applied: Optional[Callable[[dict], Awaitable[None]]] = None


        self.state_machine: Dict[str, Any] = {}


        self.p2p_client: Optional[P2PClient] = None


        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "log").mkdir(exist_ok=True)
        (self.data_dir / "snapshots").mkdir(exist_ok=True)

        logger.info(
            f"Nodo Raft {node_id} inicializado con {len(self.cluster_nodes)} peers"
        )

    def _random_election_timeout(self) -> float:

        return random.uniform(self.election_timeout_min, self.election_timeout_max)

    def add_cluster_node(self, node: NodeInfo):
        if node.id == self.node_id:
            logger.debug(f"No se puede agregar el nodo local al cluster")
            return

        if any(n.id == node.id for n in self.cluster_nodes):
            logger.debug(f"Nodo {node.id} ya existe en el cluster")
            return

        self.cluster_nodes.append(node)

        if self.state == NodeState.LEADER:
            self.next_index[node.id] = len(self.log)
            self.match_index[node.id] = -1

        logger.info(f"Nodo {node.id} agregado al cluster Raft (total: {len(self.cluster_nodes) + 1})")

    def remove_cluster_node(self, node_id: str):
        self.cluster_nodes = [n for n in self.cluster_nodes if n.id != node_id]
        if self.state == NodeState.LEADER:
            self.next_index.pop(node_id, None)
            self.match_index.pop(node_id, None)

        logger.info(f"Nodo {node_id} eliminado del cluster Raft (total: {len(self.cluster_nodes) + 1})")

    def get_cluster_nodes(self) -> List[NodeInfo]:
        return self.cluster_nodes.copy()

    async def start(self):

        if self._running:
            logger.warning(f"Nodo Raft {self.node_id} ya está corriendo")
            return

        self._running = True
        self.p2p_client = get_p2p_client()


        await self._load_state()
        await self._load_log()


        self._election_task = asyncio.create_task(self._election_timer_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_sender_loop())

        logger.info(
            f"Nodo Raft {self.node_id} iniciado "
            f"(term={self.current_term}, log_size={len(self.log)})"
        )

    async def stop(self):

        if not self._running:
            return

        logger.info(f"Deteniendo nodo Raft {self.node_id}...")

        self._running = False


        if self._election_task:
            self._election_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()


        await self._persist_state()

        logger.info(f" Nodo Raft {self.node_id} detenido")





    async def _load_state(self):

        state_file = self.data_dir / "state.json"

        if state_file.exists():
            async with aiofiles.open(state_file, "r") as f:
                content = await f.read()
                state = json.loads(content)
                self.current_term = state.get("current_term", 0)
                self.voted_for = state.get("voted_for")
                logger.info(
                    f"Estado cargado: term={self.current_term}, "
                    f"voted_for={self.voted_for}"
                )
        else:
            logger.info("No hay estado previo, iniciando limpio")

    async def _persist_state(self):

        state_file = self.data_dir / "state.json"

        state = {
            "current_term": self.current_term,
            "voted_for": self.voted_for,
            "updated_at": time.time()
        }

        async with aiofiles.open(state_file, "w") as f:
            await f.write(json.dumps(state, indent=2))

    async def _load_log(self):

        log_dir = self.data_dir / "log"
        log_files = sorted(log_dir.glob("*.log"))

        self.log = []
        for log_file in log_files:
            async with aiofiles.open(log_file, "r") as f:
                content = await f.read()
                entries = json.loads(content)
                for entry_data in entries:
                    self.log.append(LogEntry.from_dict(entry_data))

        logger.info(f"Log cargado: {len(self.log)} entradas")

    async def _persist_log_entry(self, entry: LogEntry):


        file_num = entry.index // 1000
        log_file = self.data_dir / "log" / f"{file_num:06d}.log"


        if log_file.exists():
            async with aiofiles.open(log_file, "r") as f:
                content = await f.read()
                entries = json.loads(content) if content else []
        else:
            entries = []


        entries.append(entry.to_dict())


        async with aiofiles.open(log_file, "w") as f:
            await f.write(json.dumps(entries, indent=2))

    async def _election_timer_loop(self):

        while self._running:
            try:

                if self.state in [NodeState.FOLLOWER, NodeState.CANDIDATE]:
                    elapsed = time.time() - self.last_heartbeat
                    timeout = self._random_election_timeout()

                    if elapsed >= timeout:
                        logger.warning(
                            f"Election timeout ({elapsed:.2f}s >= {timeout:.2f}s), "
                            f"iniciando elección"
                        )
                        await self._start_election()

                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error en election timer: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _start_election(self):


        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.leader_id = None
        await self._persist_state()

        logger.info(f" Iniciando elección para term {self.current_term}")


        votes_received = 1
        votes_needed = (len(self.cluster_nodes) + 1) // 2 + 1


        last_log_index = len(self.log) - 1
        last_log_term = self.log[-1].term if self.log else 0

        vote_requests = []
        for peer in self.cluster_nodes:
            request = {
                "term": self.current_term,
                "candidate_id": self.node_id,
                "last_log_index": last_log_index,
                "last_log_term": last_log_term
            }
            vote_requests.append(
                self.p2p_client.call_rpc(peer, "POST", "/raft/request-vote", request)
            )


        results = await asyncio.gather(*vote_requests, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.debug(f"Error pidiendo voto: {result}")
                continue

            if result.get("vote_granted"):
                votes_received += 1
                logger.info(
                    f"Voto recibido de {result.get('from_node')} "
                    f"({votes_received}/{votes_needed})"
                )


        if votes_received >= votes_needed and self.state == NodeState.CANDIDATE:
            await self._become_leader()
        else:
            logger.info(
                f"Elección perdida: {votes_received}/{votes_needed} votos"
            )

            self.state = NodeState.FOLLOWER

    async def _become_leader(self):

        logger.info(f"Convirtiéndose en LÍDER para term {self.current_term}")

        self.state = NodeState.LEADER
        self.leader_id = self.node_id


        last_log_index = len(self.log) - 1
        for peer in self.cluster_nodes:
            self.next_index[peer.id] = last_log_index + 1
            self.match_index[peer.id] = -1


        if self._on_become_leader:
            try:
                await self._on_become_leader()
            except Exception as e:
                logger.error(f"Error en callback on_become_leader: {e}")


        await self._send_heartbeats()
    async def _heartbeat_sender_loop(self):

        while self._running:
            try:
                if self.state == NodeState.LEADER:
                    await self._send_heartbeats()

                await asyncio.sleep(self.heartbeat_interval)

            except Exception as e:
                logger.error(f"Error en heartbeat sender: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _send_heartbeats(self):

        if self.state != NodeState.LEADER:
            return

        heartbeat_requests = []
        for peer in self.cluster_nodes:
            prev_log_index = self.next_index[peer.id] - 1
            prev_log_term = self.log[prev_log_index].term if prev_log_index >= 0 else 0


            entries_to_send = []
            next_idx = self.next_index[peer.id]
            if next_idx < len(self.log):

                entries_to_send = [e.to_dict() for e in self.log[next_idx:]]

            request = {
                "term": self.current_term,
                "leader_id": self.node_id,
                "prev_log_index": prev_log_index,
                "prev_log_term": prev_log_term,
                "entries": entries_to_send,
                "leader_commit": self.commit_index
            }

            heartbeat_requests.append(
                self._send_append_entries(peer, request)
            )

        await asyncio.gather(*heartbeat_requests, return_exceptions=True)

    async def _send_append_entries(self, peer: NodeInfo, request: dict):

        try:
            response = await self.p2p_client.call_rpc(
                peer, "POST", "/raft/append-entries", request
            )


            if response.get("term", 0) > self.current_term:

                await self._step_down(response["term"])
                return

            if response.get("success"):

                if request["entries"]:
                    last_entry_index = request["prev_log_index"] + len(request["entries"])
                    self.match_index[peer.id] = last_entry_index
                    self.next_index[peer.id] = last_entry_index + 1
            else:

                self.next_index[peer.id] = max(0, self.next_index[peer.id] - 1)

        except P2PException as e:
            logger.debug(f"Error enviando AppendEntries a {peer.id}: {e}")

    async def _step_down(self, new_term: int):

        logger.info(
            f"Descubierto term superior ({new_term} > {self.current_term}), "
            f"volviendo a FOLLOWER"
        )

        was_leader = self.state == NodeState.LEADER

        self.current_term = new_term
        self.state = NodeState.FOLLOWER
        self.voted_for = None
        self.leader_id = None
        await self._persist_state()

        if was_leader and self._on_lose_leadership:
            try:
                await self._on_lose_leadership()
            except Exception as e:
                logger.error(f"Error en callback on_lose_leadership: {e}")

    async def handle_request_vote(self, request: dict) -> dict:

        candidate_term = request["term"]
        candidate_id = request["candidate_id"]
        candidate_last_log_index = request["last_log_index"]
        candidate_last_log_term = request["last_log_term"]


        if candidate_term > self.current_term:
            await self._step_down(candidate_term)

        vote_granted = False


        if candidate_term < self.current_term:

            pass
        elif self.voted_for is not None and self.voted_for != candidate_id:

            pass
        else:

            my_last_log_index = len(self.log) - 1
            my_last_log_term = self.log[-1].term if self.log else 0

            log_is_up_to_date = (
                    candidate_last_log_term > my_last_log_term or
                    (candidate_last_log_term == my_last_log_term and
                     candidate_last_log_index >= my_last_log_index)
            )

            if log_is_up_to_date:
                vote_granted = True
                self.voted_for = candidate_id
                self.last_heartbeat = time.time()
                await self._persist_state()
                logger.info(f" Voto otorgado a {candidate_id} para term {candidate_term}")

        return {
            "term": self.current_term,
            "vote_granted": vote_granted,
            "from_node": self.node_id
        }

    async def handle_append_entries(self, request: dict) -> dict:

        leader_term = request["term"]
        leader_id = request["leader_id"]
        prev_log_index = request["prev_log_index"]
        prev_log_term = request["prev_log_term"]
        entries = request["entries"]
        leader_commit = request["leader_commit"]


        self.last_heartbeat = time.time()


        if leader_term > self.current_term:
            await self._step_down(leader_term)


        if leader_term == self.current_term and self.leader_id != leader_id:
            self.leader_id = leader_id
            self.state = NodeState.FOLLOWER
            logger.info(f"Reconociendo líder: {leader_id}")

        success = False

        if leader_term < self.current_term:

            pass
        elif prev_log_index >= 0 and (
                prev_log_index >= len(self.log) or
                self.log[prev_log_index].term != prev_log_term
        ):

            logger.debug(
                f"Log inconsistency: prev_index={prev_log_index}, "
                f"prev_term={prev_log_term}"
            )
        else:

            success = True


            if entries:
                for entry_data in entries:
                    entry = LogEntry.from_dict(entry_data)


                    if entry.index < len(self.log):
                        if self.log[entry.index].term != entry.term:
                            self.log = self.log[:entry.index]

                    if entry.index == len(self.log):
                        self.log.append(entry)
                        await self._persist_log_entry(entry)

            if leader_commit > self.commit_index:
                old_commit = self.commit_index
                self.commit_index = min(leader_commit, len(self.log) - 1)


                if self.commit_index > old_commit:
                    await self._apply_committed_entries(old_commit + 1, self.commit_index + 1)

        return {
            "term": self.current_term,
            "success": success,
            "from_node": self.node_id
        }

    async def _apply_committed_entries(self, start_index: int, end_index: int):

        for i in range(start_index, end_index):
            if i < len(self.log):
                entry = self.log[i]


                await self._apply_command(entry.command)

                self.last_applied = i

    async def _apply_command(self, command: dict):
        cmd_type = command.get("type")

        if cmd_type == "set":
            key = command.get("key")
            value = command.get("value")
            self.state_machine[key] = value

        elif cmd_type == "delete":
            key = command.get("key")
            self.state_machine.pop(key, None)

        elif cmd_type == "add_node":
            node_id = command.get("node_id")
            address = command.get("address")
            port = command.get("port")

            if node_id and address and port:
                new_node = NodeInfo(id=node_id, address=address, port=port)
                self.add_cluster_node(new_node)

                key = f"cluster:nodes:{node_id}"
                self.state_machine[key] = {
                    "id": node_id,
                    "address": address,
                    "port": port
                }
                logger.info(f"Comando add_node aplicado: {node_id}")

        elif cmd_type == "remove_node":
            node_id = command.get("node_id")
            if node_id:
                self.remove_cluster_node(node_id)
                key = f"cluster:nodes:{node_id}"
                self.state_machine.pop(key, None)
                logger.info(f"Comando remove_node aplicado: {node_id}")

        if self._on_command_applied:
            try:
                await self._on_command_applied(command)
            except Exception as e:
                logger.error(f"Error aplicando comando: {e}", exc_info=True)

    async def submit_command(self, command: dict, timeout: float = 10.0) -> bool:

        if not self.is_leader():
            raise Exception(f"No soy líder, líder actual: {self.leader_id}")


        entry = LogEntry(
            term=self.current_term,
            index=len(self.log),
            command=command
        )
        self.log.append(entry)
        await self._persist_log_entry(entry)


        start_time = time.time()
        while time.time() - start_time < timeout:

            replicated_count = 1
            for peer_id, match_idx in self.match_index.items():
                if match_idx >= entry.index:
                    replicated_count += 1


            if replicated_count >= (len(self.cluster_nodes) + 1) // 2 + 1:

                self.commit_index = entry.index
                await self._apply_committed_entries(self.last_applied + 1, self.commit_index + 1)
                return True

            await asyncio.sleep(0.1)

        logger.warning(f"Timeout esperando replicación de comando: {command}")
        return False

    def is_leader(self) -> bool:
        return self.state == NodeState.LEADER

    def get_leader(self) -> Optional[str]:
        return self.leader_id

    def can_serve_read(self) -> bool:
        return self._running and (self.leader_id is not None or self.is_leader())

    def get_eventual_read_status(self) -> dict:
        return {
            "commit_index": self.commit_index,
            "last_applied": self.last_applied,
            "lag": max(0, self.commit_index - self.last_applied)
        }

    def get_status(self) -> dict:

        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "term": self.current_term,
            "leader_id": self.leader_id,
            "log_size": len(self.log),
            "commit_index": self.commit_index,
            "last_applied": self.last_applied,
            "cluster_size": len(self.cluster_nodes) + 1
        }

    def set_callbacks(
            self,
            on_become_leader: Optional[Callable[[], Awaitable[None]]] = None,
            on_lose_leadership: Optional[Callable[[], Awaitable[None]]] = None,
            on_command_applied: Optional[Callable[[dict], Awaitable[None]]] = None
    ):

        self._on_become_leader = on_become_leader
        self._on_lose_leadership = on_lose_leadership
        self._on_command_applied = on_command_applied



_raft_node: Optional[RaftNode] = None


def initialize_raft(
        node_id: str,
        node_info: NodeInfo,
        cluster_nodes: List[NodeInfo],
        data_dir: str = "/data/raft",
        **kwargs
) -> RaftNode:

    global _raft_node
    _raft_node = RaftNode(
        node_id=node_id,
        node_info=node_info,
        cluster_nodes=cluster_nodes,
        data_dir=data_dir,
        **kwargs
    )
    return _raft_node


def get_raft_node() -> RaftNode:

    if _raft_node is None:
        raise RuntimeError("Raft Node no inicializado")
    return _raft_node