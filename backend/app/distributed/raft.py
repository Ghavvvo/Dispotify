import asyncio
import logging
import time
import random
import os
import socket
import aiofiles
from enum import Enum
from typing import List, Dict, Optional, Set
from .communication import NodeInfo, CommunicationLayer
from .state_machine import StateMachine

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
        try:
            self.address = socket.gethostbyname(socket.gethostname())
        except:
            self.address = os.getenv("NODE_ADDRESS", "0.0.0.0") 
        self.port = int(os.getenv("PORT", "8000"))
        
        self.state = RaftState.FOLLOWER
        self.current_term = 0
        self.voted_for = None
        self.log = []
        self.commit_index = -1
        self.last_applied = -1
        
        self.peers: Dict[str, NodeInfo] = {}
        self.reachable_peers: Set[str] = set()
        self.match_index: Dict[str, int] = {}
        self.next_index: Dict[str, int] = {}
        self.leader_id = None
        
        self.comm = CommunicationLayer()
        self.last_heartbeat_received = time.time()
        self.election_timeout = random.uniform(3.0, 6.0)
        
        self.running = False
        self.bootstrap_service = os.getenv("BOOTSTRAP_SERVICE", "dispotify-cluster")
        self.state_machine = StateMachine()

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
        asyncio.create_task(self.apply_loop())

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

    async def apply_loop(self):
        while self.running:
            if self.commit_index > self.last_applied:
                # Increment last_applied first to get the correct index
                self.last_applied += 1
                
                # Ensure we don't go out of bounds if log was truncated
                if self.last_applied < len(self.log):
                    entry = self.log[self.last_applied]
                    command = entry.get("command")
                    if command:
                        logger.info(f"[APPLY] Applying log index {self.last_applied}: {command.get('type')} - {command.get('nombre', 'N/A')}")
                        # Run in executor to avoid blocking async loop with DB ops
                        await asyncio.to_thread(self.state_machine.apply, command)
                    else:
                        logger.warning(f"[APPLY] Log entry {self.last_applied} has no command")
                else:
                    logger.warning(f"[APPLY] last_applied={self.last_applied} >= log length={len(self.log)}")
                    # Adjust last_applied back if we went out of bounds
                    self.last_applied = len(self.log) - 1
            else:
                await asyncio.sleep(0.1)

    async def run_loop(self):
        while self.running:
            now = time.time()
            
            if self.state in [RaftState.LEADER, RaftState.PARTITION_LEADER, RaftState.SOLO]:
                if now - self.last_heartbeat_received >= 1.0: # Send heartbeat every 1s
                    await self.send_heartbeats()
                    self.last_heartbeat_received = now # Reset to avoid spamming if loop is fast
            
            elif self.state in [RaftState.FOLLOWER, RaftState.CANDIDATE]:
                if now - self.last_heartbeat_received > self.election_timeout:
                    logger.info(f"Election timeout ({self.election_timeout}s). Starting election.")
                    await self.start_election()
                    
                # Check if leader is dead (if we are follower and haven't heard from leader)
                # This is implicitly handled by election timeout, but if we have peers in our list
                # and we timeout, we start election.
                # If we are the ONLY node left (leader died and we are the only follower),
                # start_election will fail to find peers and should transition to SOLO.

            await asyncio.sleep(0.1)

    async def start_election(self):
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.election_timeout = random.uniform(3.0, 6.0)
        self.last_heartbeat_received = time.time()
        
        # Filter out unreachable peers before calculating quorum
        # This is crucial: if leader died, it might still be in self.peers but unreachable
        # We need to try to contact them or rely on previous reachability?
        # Better: Try to contact everyone. If they don't reply, they are not reachable.
        
        # Calculate reachable quorum
        # In standard Raft, quorum is based on configuration.
        # Here we want dynamic quorum based on reachable nodes.
        
        # First, let's try to ping/vote request everyone.
        reachable_count = 0
        votes = 1 # Vote for self
        
        peers_to_remove = []
        
        for peer_id, peer in self.peers.items():
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
                if resp:
                    reachable_count += 1
                    if resp.get("vote_granted"):
                        votes += 1
                else:
                    peers_to_remove.append(peer_id)
            except Exception:
                peers_to_remove.append(peer_id)

        # Remove dead peers
        for pid in peers_to_remove:
            if pid in self.peers:
                del self.peers[pid]
            if pid in self.reachable_peers:
                self.reachable_peers.remove(pid)
            logger.info(f"Peer {pid} removed due to failure during election")

        # If no one is reachable, go SOLO
        if reachable_count == 0:
            self.state = RaftState.SOLO
            self.leader_id = self.node_id
            logger.info("No peers reachable during election. Entering SOLO mode.")
            return

        # Calculate quorum based on WHO ANSWERED (Dynamic Quorum)
        # +1 for self
        total_participating = reachable_count + 1
        needed = (total_participating // 2) + 1
        
        logger.info(f"Election Term {self.current_term}. Votes: {votes}/{total_participating} (Needed: {needed})")

        if votes >= needed:
            if len(self.peers) > 0 and reachable_count < len(self.peers) // 2:
                 self.state = RaftState.PARTITION_LEADER
            else:
                 self.state = RaftState.LEADER
            
            self.leader_id = self.node_id
            logger.info(f"Won election! State: {self.state}")
            await self.send_heartbeats()
        else:
            self.state = RaftState.FOLLOWER

    def update_commit_index(self):
        # Calculate match_indices including self
        match_indices = [len(self.log) - 1] # Leader has everything
        for peer_id in self.peers:
            match_indices.append(self.match_index.get(peer_id, -1))
        
        match_indices.sort(reverse=True)
        
        # N is the index that is replicated on majority
        n = len(match_indices)
        if n == 0: return
        
        N = match_indices[n // 2]
        
        if N > self.commit_index and N < len(self.log):
            # Only commit entries from current term by counting replicas
            if self.log[N]["term"] == self.current_term:
                self.commit_index = N
                logger.info(f"Leader commit_index updated to {self.commit_index}")

    async def send_heartbeats(self):
        # Send AppendEntries to all peers
        for peer_id, peer in self.peers.items():
            asyncio.create_task(self._send_heartbeat_to_peer(peer))
            
        # Auto-transition from SOLO if we have peers
        if self.state == RaftState.SOLO and len(self.reachable_peers) > 0:
            self.state = RaftState.LEADER
            logger.info(f"Peers reachable ({len(self.reachable_peers)}). Transitioning SOLO -> LEADER")
            
        # Auto-transition to SOLO if we lost all peers
        if self.state in [RaftState.LEADER, RaftState.PARTITION_LEADER] and len(self.reachable_peers) == 0:
            self.state = RaftState.SOLO
            logger.info("No peers reachable. Transitioning LEADER -> SOLO")

    async def _send_heartbeat_to_peer(self, peer):
        try:
            prev_log_index = self.next_index.get(peer.id, len(self.log)) - 1
            prev_log_term = 0
            if prev_log_index >= 0 and prev_log_index < len(self.log):
                prev_log_term = self.log[prev_log_index]["term"]
            
            entries = []
            if len(self.log) > prev_log_index + 1:
                entries = self.log[prev_log_index + 1:]

            # Include known peers for membership sync
            known_peers = [n.dict() for n in self.get_all_nodes()]

            resp = await self.comm.send_rpc(
                peer, "POST", "/raft/append-entries",
                {
                    "term": self.current_term,
                    "leader_id": self.node_id,
                    "prev_log_index": prev_log_index,
                    "prev_log_term": prev_log_term,
                    "entries": entries,
                    "leader_commit": self.commit_index,
                    "known_peers": known_peers
                }
            )
            if resp:
                self.reachable_peers.add(peer.id)
                if resp.get("term") > self.current_term:
                    self.current_term = resp.get("term")
                    self.state = RaftState.FOLLOWER
                    self.voted_for = None
                    return

                # Check if peer was a partition leader - trigger merge from our side
                if resp.get("was_partition_leader") and resp.get("merge_needed"):
                    logger.info(f"[MERGE] Peer {peer.id} was partition leader (term {resp.get('old_term')}). Initiating merge from leader side.")
                    asyncio.create_task(self._initiate_leader_side_merge(peer))

                if resp.get("success"):
                    # Update match_index and next_index
                    if entries:
                        self.match_index[peer.id] = prev_log_index + len(entries)
                        self.next_index[peer.id] = self.match_index[peer.id] + 1
                        self.update_commit_index()
                else:
                    # Decrement next_index and retry (simple backoff)
                    self.next_index[peer.id] = max(0, self.next_index.get(peer.id, 1) - 1)
            else:
                if peer.id in self.reachable_peers:
                    self.reachable_peers.remove(peer.id)
                # Remove from peers if unreachable (Dynamic Membership)
                if peer.id in self.peers:
                    del self.peers[peer.id]
                    logger.info(f"Peer {peer.id} removed due to failure")
        except Exception:
            if peer.id in self.reachable_peers:
                self.reachable_peers.remove(peer.id)
            # Remove from peers if unreachable (Dynamic Membership)
            if peer.id in self.peers:
                del self.peers[peer.id]
                logger.info(f"Peer {peer.id} removed due to failure")

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
        prev_log_index = data.get("prev_log_index")
        prev_log_term = data.get("prev_log_term")
        entries = data.get("entries")
        leader_commit = data.get("leader_commit")
        
        logger.debug(f"[APPEND_ENTRIES] Received from {leader_id}: prev_log_index={prev_log_index}, entries={len(entries) if entries else 0}, leader_commit={leader_commit}, my_commit={self.commit_index}")
        
        if term < self.current_term:
            return {"term": self.current_term, "success": False}

        # Detect partition merge scenario
        was_partition_leader = self.state == RaftState.PARTITION_LEADER
        was_solo = self.state == RaftState.SOLO
        was_leader = self.is_leader()
        old_term = self.current_term
        old_state = self.state
        old_leader_id = self.leader_id
        
        self.current_term = term
        self.state = RaftState.FOLLOWER
        self.leader_id = leader_id
        self.last_heartbeat_received = time.time()
        
        # Trigger merge if we were isolated (PARTITION_LEADER or SOLO) and now joining a leader
        should_merge = False
        merge_reason = ""
        
        if was_partition_leader and term > old_term:
            should_merge = True
            merge_reason = f"Was partition leader (term {old_term}), now joining leader {leader_id} (term {term})"
        elif was_solo and term >= old_term:
            # SOLO node joining any leader (even same term means we were isolated)
            should_merge = True
            merge_reason = f"Was SOLO (term {old_term}), now joining leader {leader_id} (term {term})"
        
        if should_merge:
            logger.info(f"[MERGE] Detected partition merge. {merge_reason}")
            asyncio.create_task(self._handle_partition_merge(leader_id))
        
        # Return merge notification to the new leader if we were a leader
        response = {"term": self.current_term, "success": False}
        if was_leader and should_merge:
            response["was_partition_leader"] = True
            response["old_term"] = old_term
            response["merge_needed"] = True
        
        # Sync membership with leader
        known_peers = data.get("known_peers", [])
        if known_peers:
            current_peer_ids = set(self.peers.keys())
            new_peer_ids = set()
            for p_data in known_peers:
                # Skip self
                if p_data.get("id") == self.node_id:
                    continue
                
                p = NodeInfo(**p_data)
                new_peer_ids.add(p.id)
                
                if p.id not in self.peers:
                    self.add_peer(p)
                    logger.info(f"Added peer {p.id} from leader sync")
                elif self.peers[p.id].address != p.address:
                    self.peers[p.id].address = p.address
            
            # Remove peers not in leader's list
            for pid in current_peer_ids:
                if pid not in new_peer_ids:
                    if pid in self.peers:
                        del self.peers[pid]
                    if pid in self.reachable_peers:
                        self.reachable_peers.remove(pid)
                    logger.info(f"Removed peer {pid} (not in leader's list)")

        # Log consistency check
        if prev_log_index >= 0:
            if len(self.log) <= prev_log_index:
                return {"term": self.current_term, "success": False}
            if self.log[prev_log_index]["term"] != prev_log_term:
                # Conflict: delete everything from here
                self.log = self.log[:prev_log_index]
                return {"term": self.current_term, "success": False}
        
        # Append new entries
        if entries:
            logger.info(f"[APPEND_ENTRIES] Received {len(entries)} entries from leader {leader_id}")
            # If we have existing entries that conflict, delete them
            # (Already handled partially above, but standard Raft says:)
            # 3. If an existing entry conflicts with a new one (same index but different terms),
            # delete the existing entry and all that follow it.
            # 4. Append any new entries not already in the log
            
            current_idx = prev_log_index + 1
            for entry in entries:
                if len(self.log) > current_idx:
                    if self.log[current_idx]["term"] != entry["term"]:
                        self.log = self.log[:current_idx]
                        self.log.append(entry)
                else:
                    self.log.append(entry)
                current_idx += 1
            logger.info(f"[APPEND_ENTRIES] Log now has {len(self.log)} entries")

        # Update commit index
        if leader_commit > self.commit_index:
            old_commit = self.commit_index
            self.commit_index = min(leader_commit, len(self.log) - 1)
            logger.info(f"[APPEND_ENTRIES] Updated commit_index from {old_commit} to {self.commit_index}")
        elif leader_commit >= 0 and len(self.log) > 0:
            # Even if leader_commit is not greater, ensure we're at least at the right level
            self.commit_index = min(leader_commit, len(self.log) - 1)
            logger.info(f"[APPEND_ENTRIES] Set commit_index to {self.commit_index} (leader_commit={leader_commit}, log_len={len(self.log)})")
            
        return {"term": self.current_term, "success": True}

    def add_peer(self, node: NodeInfo):
        self.peers[node.id] = node
        self.reachable_peers.add(node.id)
        # Initialize next_index for new peer to 0 (will send all log entries)
        if node.id not in self.next_index:
            self.next_index[node.id] = 0
        if node.id not in self.match_index:
            self.match_index[node.id] = -1
        
        # If we are leader, trigger immediate sync for the new peer
        if self.is_leader():
            asyncio.create_task(self._sync_new_peer(node))
    
    async def _sync_new_peer(self, peer: NodeInfo):
        """Synchronize a newly connected peer with full history"""
        logger.info(f"[SYNC] Starting full synchronization for new peer {peer.id}")
        
        try:
            # Step 1: Send full log history via append_entries
            # This will be handled automatically by the heartbeat mechanism
            # since next_index[peer.id] = 0
            
            # Step 2: Send all music files
            from .replication import get_replication_manager
            from app.core.database import SessionLocal
            from app.models.music import Music
            
            replication_manager = get_replication_manager()
            db = SessionLocal()
            
            try:
                # Get all songs from database
                all_songs = db.query(Music).all()
                logger.info(f"[SYNC] Found {len(all_songs)} songs to sync to {peer.id}")
                
                # Send each file to the new peer
                for song in all_songs:
                    if not song.url:
                        logger.warning(f"[SYNC] Song {song.nombre} has no URL, skipping file sync")
                        continue
                        
                    file_id = song.url.split('/')[-1]  # Extract file_id from URL
                    
                    if file_id == "null" or not file_id:
                        logger.warning(f"[SYNC] Song {song.nombre} has invalid file_id '{file_id}' from url '{song.url}', skipping")
                        continue
                        
                    file_path = replication_manager.storage_path / file_id
                    
                    if file_path.exists():
                        metadata = {
                            "file_id": file_id,
                            "nombre": song.nombre,
                            "autor": song.autor,
                            "album": song.album,
                            "genero": song.genero,
                            "url": song.url,
                            "file_size": song.file_size,
                            "partition_id": song.partition_id,
                            "epoch_number": song.epoch_number
                        }
                        
                        await self._send_file_to_peer(peer, file_path, metadata)
                    else:
                        logger.warning(f"[SYNC] File {file_id} not found locally for song {song.nombre}")
                
                logger.info(f"[SYNC] Completed full synchronization for peer {peer.id}")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"[SYNC] Error synchronizing peer {peer.id}: {e}", exc_info=True)
    
    async def _send_file_to_peer(self, peer: NodeInfo, file_path, metadata: dict):
        """Send a single file to a peer"""
        import httpx
        import json
        
        try:
            url = f"http://{peer.address}:{peer.port}/internal/replicate"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(file_path, 'rb') as f:
                    files = {'file': f}
                    data = {'metadata': json.dumps(metadata)}
                    
                    logger.info(f"[SYNC] Sending file {metadata['file_id']} ({metadata['nombre']}) to {peer.id}")
                    resp = await client.post(url, files=files, data=data)
                    
                    if resp.status_code == 200:
                        logger.info(f"[SYNC] Successfully sent {metadata['file_id']} to {peer.id}")
                    else:
                        logger.warning(f"[SYNC] Failed to send {metadata['file_id']} to {peer.id}: status {resp.status_code}")
                        
        except Exception as e:
            logger.error(f"[SYNC] Error sending file to {peer.id}: {e}")
    
    async def _initiate_leader_side_merge(self, peer: NodeInfo):
        """
        Initiated by the winning leader when it detects a peer was a partition leader.
        This ensures the leader also pulls data from the former partition leader.
        """
        logger.info(f"[MERGE_LEADER] Initiating leader-side merge with former partition leader {peer.id}")
        
        # The peer will already be sending us their data via _handle_partition_merge
        # But we need to ensure we also send them what they're missing
        # This is handled automatically by the bidirectional endpoint
        # We just need to wait a bit for their merge request to arrive
        await asyncio.sleep(1)
        logger.info(f"[MERGE_LEADER] Merge coordination with {peer.id} in progress via bidirectional endpoint")
    
    async def _handle_partition_merge(self, new_leader_id: str):
        """Handle bidirectional merge when this partition joins another partition"""
        logger.info(f"[MERGE] Starting bidirectional partition merge with leader {new_leader_id}")
        
        try:
            import httpx
            from app.core.database import SessionLocal
            from app.models.music import Music
            from .replication import get_replication_manager
            
            db = SessionLocal()
            replication_manager = get_replication_manager()
            
            try:
                # Step 1: Collect our partition's log and data
                our_songs = db.query(Music).all()
                our_log_entries = [
                    {
                        "term": entry.get("term"),
                        "command": entry.get("command")
                    }
                    for entry in self.log
                ]
                
                logger.info(f"[MERGE] Our partition: {len(our_songs)} songs, {len(our_log_entries)} log entries, term={self.current_term}")
                
                # Find the new leader's address
                leader_peer = None
                for peer in self.peers.values():
                    if peer.id == new_leader_id:
                        leader_peer = peer
                        break
                
                if not leader_peer:
                    logger.error(f"[MERGE] Could not find leader {new_leader_id} in peers")
                    return
                
                # Step 2: Send bidirectional merge request with our log and songs
                merge_data = {
                    "node_id": self.node_id,
                    "our_term": self.current_term,
                    "our_log": our_log_entries,
                    "partition_songs": [
                        {
                            "nombre": song.nombre,
                            "autor": song.autor,
                            "album": song.album,
                            "genero": song.genero,
                            "url": song.url,
                            "file_size": song.file_size,
                            "partition_id": song.partition_id,
                            "epoch_number": song.epoch_number,
                            "created_at": song.created_at.isoformat() if song.created_at else None
                        }
                        for song in our_songs
                    ]
                }
                
                url = f"http://{leader_peer.address}:{leader_peer.port}/internal/partition-merge-bidirectional"
                
                async with httpx.AsyncClient(timeout=120.0) as client:
                    logger.info(f"[MERGE] Sending bidirectional merge request to leader {new_leader_id}")
                    resp = await client.post(url, json=merge_data)
                    
                    if resp.status_code == 200:
                        result = resp.json()
                        logger.info(f"[MERGE] Merge response received from leader")
                        
                        # Step 3: Process what we need from the leader
                        files_we_need = result.get("files_you_need", [])
                        songs_we_need = result.get("songs_you_need", [])
                        
                        logger.info(f"[MERGE] We need {len(files_we_need)} files and {len(songs_we_need)} songs from leader")
                        if len(files_we_need) != len(songs_we_need):
                            logger.warning(f"[MERGE] Mismatch between files needed ({len(files_we_need)}) and songs needed ({len(songs_we_need)}). This might indicate metadata sync issues.")
                        
                        # Step 4: Apply missing songs from leader to our database
                        logger.info(f"[MERGE] Starting metadata synchronization for {len(songs_we_need)} songs")
                        for song_data in songs_we_need:
                            existing = db.query(Music).filter(Music.url == song_data["url"]).first()
                            if not existing:
                                logger.info(f"[MERGE] Creating metadata for song: {song_data['nombre']} (URL: {song_data['url']})")
                                from app.services.music_service import MusicService
                                from app.schemas.music import MusicCreate
                                
                                music_data = MusicCreate(
                                    nombre=song_data["nombre"],
                                    autor=song_data["autor"],
                                    album=song_data.get("album"),
                                    genero=song_data.get("genero")
                                )
                                
                                MusicService.create_music(
                                    db,
                                    music_data,
                                    url=song_data["url"],
                                    file_size=song_data["file_size"],
                                    partition_id=song_data.get("partition_id"),
                                    epoch_number=song_data.get("epoch_number")
                                )
                                logger.info(f"[MERGE] Successfully added metadata for: {song_data['nombre']}")
                            else:
                                logger.info(f"[MERGE] Metadata already exists for: {song_data['nombre']} (skipping)")
                        
                        # Step 5: Request files we need from leader
                        logger.info(f"[MERGE] Starting physical file synchronization for {len(files_we_need)} files")
                        for file_id in files_we_need:
                            if file_id == "null" or not file_id:
                                logger.error(f"[MERGE] Skipping invalid file_id '{file_id}'. This explains why physical file might be copied with null name but metadata failed.")
                                continue
                                
                            try:
                                file_url = f"http://{leader_peer.address}:{leader_peer.port}/internal/file/{file_id}"
                                logger.info(f"[MERGE] Requesting physical file {file_id} from leader")
                                
                                file_resp = await client.get(file_url, timeout=60.0)
                                if file_resp.status_code == 200:
                                    file_path = replication_manager.storage_path / file_id
                                    async with aiofiles.open(file_path, 'wb') as f:
                                        await f.write(file_resp.content)
                                    logger.info(f"[MERGE] Successfully downloaded physical file {file_id} from leader")
                                else:
                                    logger.warning(f"[MERGE] Failed to download {file_id}: status {file_resp.status_code}. Metadata exists but physical file missing on leader?")
                            except Exception as e:
                                logger.error(f"[MERGE] Error downloading file {file_id}: {e}")
                        
                        # Step 6: Send files that the leader needs from us
                        files_to_send = result.get("files_we_need", [])
                        logger.info(f"[MERGE] Leader needs {len(files_to_send)} files from us (Reverse Sync)")
                        
                        for file_id in files_to_send:
                            song = next((s for s in our_songs if file_id in s.url), None)
                            if song:
                                file_path = replication_manager.storage_path / file_id
                                if file_path.exists():
                                    metadata = {
                                        "file_id": file_id,
                                        "nombre": song.nombre,
                                        "autor": song.autor,
                                        "album": song.album,
                                        "genero": song.genero,
                                        "url": song.url,
                                        "file_size": song.file_size
                                    }
                                    await self._send_file_to_peer(leader_peer, file_path, metadata)
                                    logger.info(f"[MERGE] Sent file {file_id} to leader")
                        
                        logger.info(f"[MERGE] Bidirectional partition merge completed successfully")
                    else:
                        logger.error(f"[MERGE] Merge request failed with status {resp.status_code}")
                        
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"[MERGE] Error during partition merge: {e}", exc_info=True)

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
        last_log_index = len(self.log) - 1
        
        # If SOLO, commit immediately
        if self.state == RaftState.SOLO:
            self.commit_index = last_log_index
            return True
            
        # Wait for replication
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Trigger heartbeat to speed up replication
            await self.send_heartbeats()
            
            if self.state in [RaftState.LEADER, RaftState.PARTITION_LEADER]:
                 # Calculate replication count for the new entry
                 # We count ourselves + peers that have matched this index
                 replication_count = 1 # Self
                 for peer_id in self.reachable_peers:
                     if self.match_index.get(peer_id, -1) >= last_log_index:
                         replication_count += 1
                 
                 # Calculate needed quorum based on reachable peers (Dynamic Quorum for Partition Tolerance)
                 total_reachable = len(self.reachable_peers) + 1
                 needed = (total_reachable // 2) + 1
                 
                 if replication_count >= needed:
                     self.commit_index = last_log_index
                     return True
            else:
                # Lost leadership
                return False
            
            await asyncio.sleep(0.1)
            
        return False

def get_raft_node():
    return RaftNode.get_instance()
