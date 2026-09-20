from .models import Memory, MemoryType
from .database import Database
from typing import List, Optional


class MemoryLayer:
    def __init__(self, db: Database, layer_type: str):
        self.db = db
        self.layer_type = layer_type

    def add_memory(self, content: str, **kwargs) -> Memory:
        memory = Memory(
            type=self.layer_type,
            content=content,
            **kwargs
        )
        self.db.insert_memory(memory)
        return memory

    def get(self, memory_id: str) -> Optional[dict]:
        return self.db.get_memory(memory_id)

    def search(self, query: str, limit: int = 20) -> List[dict]:
        type_results = self.db.search_by_type(self.layer_type, limit=limit * 3)
        if not query or query.strip() == "":
            return type_results[:limit]
        query_lower = query.lower()
        return [r for r in type_results if query_lower in r.get("content", "").lower()][:limit]

    def list_all(self, limit: int = 50) -> List[dict]:
        return self.db.search_by_type(self.layer_type, limit=limit)

    def count(self) -> int:
        return self.db.count(self.layer_type)
