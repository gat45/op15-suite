from ..core.layer import MemoryLayer
from ..core.database import Database
import json
from typing import List


class ProceduralMemory(MemoryLayer):
    def __init__(self, db: Database):
        super().__init__(db, "procedural")

    def add_skill(self, name: str, procedure: str, success_rate: float = 1.0, **kwargs) -> "Memory":
        metadata = {"name": name, "success_rate": success_rate}
        return self.add_memory(procedure, metadata=metadata, **kwargs)

    def get_skill(self, name: str) -> dict:
        all_skills = self.db.search_by_type("procedural", limit=100)
        for s in all_skills:
            meta = json.loads(s.get("metadata", "{}"))
            if meta.get("name") == name:
                return s
        results = self.search(name)
        return results[0] if results else None
