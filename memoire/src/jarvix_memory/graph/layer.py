from ..core.layer import MemoryLayer
from ..core.database import Database
import json
from typing import List, Dict, Any


class GraphMemory(MemoryLayer):
    def __init__(self, db: Database):
        super().__init__(db, "graph")

    def add_relation(self, subject: str, predicate: str, obj: str, metadata: Dict[str, Any] = None) -> "Memory":
        content = f"{subject} --[{predicate}]--> {obj}"
        meta = metadata or {}
        meta.update({"subject": subject, "predicate": predicate, "object": obj})
        return self.add_memory(content, metadata=meta)

    def get_relations_for_entity(self, entity: str) -> List[Dict]:
        return self.search(entity)

    def get_by_predicate(self, predicate: str) -> List[Dict]:
        all_graph = self.db.search_by_type("graph", limit=200)
        return [
            r for r in all_graph
            if json.loads(r.get("metadata", "{}")).get("predicate") == predicate
        ]
