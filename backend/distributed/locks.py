import asyncio
import time
import logging
from typing import Optional
from contextlib import asynccontextmanager
from app.distributed.raft import RaftP2PNode, get_raft_node

logger = logging.getLogger(__name__)


class LockException(Exception):
    pass


class DistributedLock:

    def __init__(self, lock_name: str, holder_id: str, raft_node: RaftP2PNode):
        self.lock_name = lock_name
        self.holder_id = holder_id
        self.raft_node = raft_node
        self._acquired = False

    async def acquire(self, timeout: float = 10.0, blocking: bool = True) -> bool:

        if self._acquired:
            logger.warning(f"Lock {self.lock_name} ya adquirido por {self.holder_id}")
            return True

        start_time = time.time()

        while True:
            try:

                command = {
                    "type": "acquire_lock",
                    "lock_name": self.lock_name,
                    "holder_id": self.holder_id,
                    "timestamp": time.time()
                }

                success = await self.raft_node.submit_command(
                    command,
                    timeout=timeout
                )

                if success:
                    self._acquired = True
                    logger.info(
                        f"Lock '{self.lock_name}' adquirido por {self.holder_id}"
                    )
                    return True
                else:

                    if not blocking:
                        return False

                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        logger.warning(
                            f"Timeout adquiriendo lock '{self.lock_name}' "
                            f"después de {elapsed:.1f}s"
                        )
                        return False

                    await asyncio.sleep(0.5)

            except Exception as e:
                if "No soy líder" in str(e):

                    leader_id = self.raft_node.get_leader()
                    logger.warning(
                        f"No somos líder, líder actual: {leader_id}. "
                        f"Reintentando..."
                    )

                    if not blocking:
                        raise LockException(
                            f"Este nodo no es líder, redirigir a {leader_id}"
                        )

                    await asyncio.sleep(1.0)

                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        raise LockException(
                            f"Timeout esperando líder después de {elapsed:.1f}s"
                        )
                else:
                    raise LockException(f"Error adquiriendo lock: {e}")

    async def release(self):

        if not self._acquired:
            logger.warning(
                f"Intentando liberar lock '{self.lock_name}' "
                f"que no está adquirido"
            )
            return

        try:

            command = {
                "type": "release_lock",
                "lock_name": self.lock_name,
                "holder_id": self.holder_id,
                "timestamp": time.time()
            }

            await self.raft_node.submit_command(command, timeout=5.0)

            self._acquired = False
            logger.info(f"🔓 Lock '{self.lock_name}' liberado por {self.holder_id}")

        except Exception as e:
            logger.error(f"Error liberando lock '{self.lock_name}': {e}")

            self._acquired = False

    def is_acquired(self) -> bool:

        return self._acquired

    async def __aenter__(self):

        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):

        await self.release()
        return False


class LockManager:

    def __init__(self, raft_node: RaftP2PNode, node_id: str):
        self.raft_node = raft_node
        self.node_id = node_id

        self._register_lock_handler()

        logger.info(f"Lock Manager inicializado para nodo {node_id}")

    def _register_lock_handler(self):

        async def handle_lock_command(command: dict):
            cmd_type = command.get("type")

            if cmd_type == "acquire_lock":
                lock_name = command["lock_name"]
                holder_id = command["holder_id"]

                current_holder = self.raft_node.state_machine.get(
                    f"lock:{lock_name}"
                )

                if current_holder is None:

                    self.raft_node.state_machine[f"lock:{lock_name}"] = {
                        "holder_id": holder_id,
                        "acquired_at": command["timestamp"]
                    }
                    logger.debug(
                        f"Lock '{lock_name}' otorgado a {holder_id} "
                        f"(via state machine)"
                    )
                else:

                    logger.debug(
                        f"Lock '{lock_name}' ya tomado por "
                        f"{current_holder['holder_id']}"
                    )

            elif cmd_type == "release_lock":
                lock_name = command["lock_name"]
                holder_id = command["holder_id"]

                current_holder = self.raft_node.state_machine.get(
                    f"lock:{lock_name}"
                )

                if current_holder and current_holder["holder_id"] == holder_id:
                    del self.raft_node.state_machine[f"lock:{lock_name}"]
                    logger.debug(
                        f"Lock '{lock_name}' liberado por {holder_id} "
                        f"(via state machine)"
                    )

        original_callback = self.raft_node._on_command_applied

        async def combined_callback(command: dict):

            await handle_lock_command(command)

            if original_callback:
                await original_callback(command)

        self.raft_node._on_command_applied = combined_callback

    def create_lock(self, lock_name: str) -> DistributedLock:

        return DistributedLock(
            lock_name=lock_name,
            holder_id=self.node_id,
            raft_node=self.raft_node
        )

    @asynccontextmanager
    async def lock(self, lock_name: str, timeout: float = 10.0):

        lock = self.create_lock(lock_name)
        try:
            await lock.acquire(timeout=timeout)
            yield lock
        finally:
            await lock.release()

    def get_all_locks(self) -> dict:

        locks = {}
        for key, value in self.raft_node.state_machine.items():
            if key.startswith("lock:"):
                lock_name = key[5:]
                locks[lock_name] = value
        return locks


lock_manager: Optional[LockManager] = None


def initialize_lock_manager(
        raft_node: RaftP2PNode,
        node_id: str
) -> LockManager:
    global lock_manager
    lock_manager = LockManager(raft_node, node_id)
    return lock_manager


def get_lock_manager() -> LockManager:
    if lock_manager is None:
        raise RuntimeError("Lock Manager no inicializado")
    return lock_manager

