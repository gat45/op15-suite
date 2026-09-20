from ..core.layer import MemoryLayer
from ..core.database import Database
from ..core.models import Memory
import json
import logging
from typing import List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ActionMemory(MemoryLayer):
    """Memory -> Recommendation -> Planner -> Action"""

    def __init__(self, db: Database):
        super().__init__(db, "action")

    def propose(
        self,
        description: str,
        based_on: List[str] = None,
        priority: int = 5,
        metadata: Dict[str, Any] = None,
    ) -> Memory:
        meta = metadata or {}
        meta["based_on"] = based_on or []
        meta["priority"] = priority
        meta["status"] = ActionStatus.PROPOSED.value
        return self.add_memory(description, metadata=meta)

    def approve(self, action_id: str) -> bool:
        return self._set_status(action_id, ActionStatus.APPROVED.value)

    def execute(self, action_id: str, result: str = None, success: bool = True) -> bool:
        status = ActionStatus.EXECUTED.value if success else ActionStatus.FAILED.value
        return self._set_status(action_id, status, result=result)

    def skip(self, action_id: str, reason: str = None) -> bool:
        return self._set_status(action_id, ActionStatus.SKIPPED.value, result=reason)

    def propose_next_actions(self, context: str, limit: int = 5) -> List[Dict]:
        hypotheses = self.db.search_fts(f"hypothesis {context}", limit=5)
        errors = self.db.search_fts(f"error {context}", limit=3)
        evidence = self.db.search_fts(f"evidence {context}", limit=5)

        actions = []
        for h in hypotheses:
            meta = json.loads(h.get("metadata", "{}"))
            if meta.get("status") == "provisional":
                actions.append({
                    "description": f"Test hypothesis: {h['content'][:100]}",
                    "based_on": [h["id"]],
                    "priority": 7,
                    "source": "hypothesis",
                })

        for e in errors:
            meta = json.loads(e.get("metadata", "{}"))
            if not meta.get("resolved"):
                actions.append({
                    "description": f"Investigate error: {e['content'][:100]}",
                    "based_on": [e["id"]],
                    "priority": 8,
                    "source": "error",
                })

        for ev in evidence:
            meta = json.loads(ev.get("metadata", "{}"))
            if meta.get("verdict") == "inconclusive":
                actions.append({
                    "description": f"Re-verify: {ev['content'][:100]}",
                    "based_on": [ev["id"]],
                    "priority": 6,
                    "source": "evidence",
                })

        actions.sort(key=lambda a: a["priority"], reverse=True)
        return actions[:limit]

    def pending(self) -> List[Dict]:
        conn = self.db._connect()
        rows = conn.execute(
            "SELECT * FROM memories WHERE type = 'action' "
            "AND metadata LIKE ? ORDER BY created_at DESC",
            (f'%"status": "{ActionStatus.PROPOSED.value}"%',),
        ).fetchall()
        return [dict(row) for row in rows]

    def history(self, limit: int = 20) -> List[Dict]:
        conn = self.db._connect()
        rows = conn.execute(
            "SELECT * FROM memories WHERE type = 'action' "
            "AND metadata LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f'%"status": "{ActionStatus.EXECUTED.value}"%', limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _set_status(self, action_id: str, status: str, result: str = None) -> bool:
        mem = self.db.get_memory(action_id)
        if not mem:
            return False
        meta = json.loads(mem.get("metadata", "{}"))
        meta["status"] = status
        if result:
            meta["result"] = result
        self.db.update_memory(action_id, metadata=json.dumps(meta))
        return True
