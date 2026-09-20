from ..core.layer import MemoryLayer
from ..core.database import Database
from typing import List


class EpisodicMemory(MemoryLayer):
    def __init__(self, db: Database):
        super().__init__(db, "episodic")

    def log_event(self, action: str, result: str, metadata: dict = None, **kwargs) -> "Memory":
        content = f"Action: {action}\nResult: {result}"
        return self.add_memory(content, metadata=metadata or {}, **kwargs)

    def recent(self, limit: int = 10) -> List[dict]:
        return self.db.search_by_type("episodic", limit=limit)
