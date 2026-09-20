from ..core.layer import MemoryLayer
from ..core.database import Database
from typing import List


class SemanticMemory(MemoryLayer):
    def __init__(self, db: Database):
        super().__init__(db, "semantic")

    def add_fact(self, fact: str, confidence: float = 1.0, source: str = None, **kwargs) -> "Memory":
        return self.add_memory(fact, confidence=confidence, source=source, **kwargs)

    def get_facts(self, min_confidence: float = 0.5) -> List[dict]:
        all_semantic = self.db.search_by_type("semantic", limit=200)
        return [r for r in all_semantic if (r.get("confidence") or 0) >= min_confidence]
