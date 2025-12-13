import asyncio
import logging
import time
import random
import os
from enum import Enum
from typing import List, Dict, Optional, Set
from .communication import NodeInfo, CommunicationLayer

logger = logging.getLogger(__name__)

class RaftState(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"
    PARTITION_LEADER = "partition_leader"
    SOLO = "solo"

class RaftNode:
    _instance = None

    def __init__(self):
        self.node_id = os.getenv("NODE_ID", f"node-{random.randint(1000,9999)}")
        # Address/Port will be updated when we know our IP or from env
        self.address = os.getenv("NODE_ADDRESS", "0.0.0.0") 
        self.port = int(os.getenv("PORT", "8000"))
        
        self.state = RaftState.FOLLOWER
        self.current_term = 0
        self.voted_for = None
        self.log = []
        self.commit_index = 0
        self.last_applied = 0
        
        self.peers: Dict[str, NodeInfo] = {}
        self.reachable_peers: Set[str] = set()
        self.leader_id = None
        
        self.comm = CommunicationLayer()
        self.last_heartbeat_received = time.time()
        self.election_timeout = random.uniform(3.0, 6.0)
        
        self.running = False
        self.bootstrap_service = os.getenv("BOOTSTRAP_SERVICE", "dispotify-cluster")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = RaftNode()
        return cls._instance

    async def start(self):
        self.running = True
        logger.info(f"Starting RaftNode {self.node_id} on {self.address}:{self.port}")
        asyncio.create_task(self.run_loop())
        asyncio.create_task(self.discovery_loop())

    async def discovery_loop(self):
        while self.running:
            ips = self.comm.discover_nodes(self.bootstrap_service)
            for ip in ips:
                # We assume standard port 8000 or same as ours
                target_port = self.port 
                
                # Create temp NodeInfo to probe
                temp_node = NodeInfo(id="unknown", address=ip, port=target_port)
                
                try:
                    resp = await self.comm.send_rpc(temp_node, "GET", "/health")
                    if resp and resp.get("status") == "healthy":
                        node_id = resp.get("node_id")
                        if node_id and node_id != self.node_id:
                            if node_id not in self.peers:
                                logger.info(f"Discovered peer {node_id} at {ip}")
                                new_node = NodeInfo(id=node_id, address=ip, port=target_port)
                                self.add_peer(new_node)
                            else:
                                # Update address if changed
                                if self.peers[node_id].address != ip:
                                    self.peers[node_id].address = ip
                except Exception:
                    pass
            await asyncio.sleep(5)

    async def run_loop(self):
        while self.running:
            now = time.time()
            
            if self.state in [RaftState.LEADER, RaftState.PARTITION_LEADER]:
                if now - self.last_heartbeat_received >= 1.0: # Send heartbeat every 1s
                    await self.send_heartbeats()
                    self.last_heartbeat_received = now # Reset to avoid spamming if loop is fast
            
            elif self.state in [RaftState.FOLLOWER, RaftState.CANDIDATE, RaftState.SOLO]:
                if now - self.last_heartbeat_received > self.election_timeout:
                    logger.info(f"Election timeout ({self.election_timeout}s). Starting election.")
                    await self.start_election()

            await asyncio.sleep(0.1)

    async def start_election(self):
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.election_timeout = random.uniform(3.0, 6.0)
        self.last_heartbeat_received = time.time()
        
        # Calculate reachable quorum
        reachable = [p for p in self.peers.values() if p.id in self.reachable_peers]
        # Include self
        total_votes_needed = (len(reachable) + 1) // 2 + 1
        
        logger.info(f"Starting election Term {self.current_term}. Reachable: {len(reachable)}. Needed: {total_votes_needed}")

        if len(reachable) == 0:
            self.state = RaftState.SOLO
            self.leader_id = self.node_id
            logger.info("No peers reachable. Entering SOLO mode.")
            return

        votes = 1 # Vote for self
        
        for peer in reachable:
            try:
                resp = await self.comm.send_rpc(
                    peer, "POST", "/raft/request-vote",
                    {
                        "term": self.current_term,
                        "candidate_id": self.node_id,
                        "last_log_index": len(self.log) - 1,
                        "last_log_term": self.log[-1]["term"] if self.log else 0
                    }
                )
                if resp and resp.get("vote_granted"):
                    votes += 1
            except Exception:
                pass

        if votes >= total_votes_needed:
            if len(self.peers) > 0 and len(reachable) < len(self.peers) // 2:
                 self.state = RaftState.PARTITION_LEADER
            else:
                 self.state = RaftState.LEADER
            
            self.leader_id = self.node_id
            logger.info(f"Won election! State: {self.state}")
            await self.send_heartbeats()
        else:
            self.state = RaftState.FOLLOWER

    async def send_heartbeats(self):
        # Send AppendEntries to all peers
        for peer_id, peer in self.peers.items():
            asyncio.create_task(self._send_heartbeat_to_peer(peer))

    async def _send_heartbeat_to_peer(self, peer):
        try:
            resp = await self.comm.send_rpc(
                peer, "POST", "/raft/append-entries",
                {
                    "term": self.current_term,
                    "leader_id": self.node_id,
                    "prev_log_index": len(self.log) - 1,
                    "prev_log_term": self.log[-1]["term"] if self.log else 0,
                    "entries": [],
                    "leader_commit": self.commit_index
                }
            )
            if resp:
                self.reachable_peers.add(peer.id)
                if resp.get("term") > self.current_term:
                    self.current_term = resp.get("term")
                    self.state = RaftState.FOLLOWER
                    self.voted_for = None
            else:
                if peer.id in self.reachable_peers:
                    self.reachable_peers.remove(peer.id)
        except Exception:
            if peer.id in self.reachable_peers:
                self.reachable_peers.remove(peer.id)

    async def handle_request_vote(self, data: dict):
        term = data.get("term")
        candidate_id = data.get("candidate_id")
        
        if term > self.current_term:
            self.current_term = term
            self.state = RaftState.FOLLOWER
            self.voted_for = None
            
        vote_granted = False
        if (term >= self.current_term and 
            (self.voted_for is None or self.voted_for == candidate_id)):
            vote_granted = True
            self.voted_for = candidate_id
            self.last_heartbeat_received = time.time()
            
        return {"term": self.current_term, "vote_granted": vote_granted}

    async def handle_append_entries(self, data: dict):
        term = data.get("term")
        leader_id = data.get("leader_id")
        
        if term >= self.current_term:
            self.current_term = term
            self.state = RaftState.FOLLOWER
            self.leader_id = leader_id
            self.last_heartbeat_received = time.time()
            
            # Add leader to peers if unknown (simple discovery)
            # In real impl we need address/port in heartbeat
            
            return {"term": self.current_term, "success": True}
        
        return {"term": self.current_term, "success": False}

    def add_peer(self, node: NodeInfo):
        self.peers[node.id] = node
        self.reachable_peers.add(node.id)

    def is_leader(self):
        return self.state in [RaftState.LEADER, RaftState.PARTITION_LEADER, RaftState.SOLO]

    def get_all_nodes(self):
        return list(self.peers.values()) + [NodeInfo(id=self.node_id, address=self.address, port=self.port)]

    def get_alive_nodes(self):
        return [p for p in self.peers.values() if p.id in self.reachable_peers] + [NodeInfo(id=self.node_id, address=self.address, port=self.port)]

    def get_leader(self):
        return self.leader_id

    @property
    def partition_id(self):
        # Simple partition ID based on leader ID
        return self.leader_id if self.leader_id else "unknown"

    @property
    def epoch_number(self):
        return self.current_term

    def can_serve_read(self):
        # Allow reads if we have a leader or are in partition leader mode
        return self.leader_id is not None

    def get_eventual_read_status(self):
        return {
            "lag": self.commit_index - self.last_applied,
            "commit_index": self.commit_index,
            "last_applied": self.last_applied
        }

    async def submit_command(self, command: dict, timeout: float = 10.0):
        if not self.is_leader():
            return False
        
        entry = {"term": self.current_term, "command": command}
        self.log.append(entry)
        # In a real Raft, we wait for replication. 
        # Here for simplicity/MVP, we assume success if we are leader.
        return True

def get_raft_node():
    return RaftNode.get_instance()
