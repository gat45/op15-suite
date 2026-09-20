from ..core.layer import MemoryLayer
from ..core.database import Database
from typing import List, Optional


class DecisionMemory(MemoryLayer):
    def __init__(self, db: Database):
        super().__init__(db, "decision")

    def log_decision(self, decision: str, reasoning: str, alternatives: list = None, **kwargs) -> "Memory":
        content = f"Decision: {decision}\nReasoning: {reasoning}"
        metadata = {"alternatives": alternatives or []}
        return self.add_memory(content, metadata=metadata, **kwargs)

    def recent_decisions(self, limit: int = 10) -> List[dict]:
        return self.db.search_by_type("decision", limit=limit)
