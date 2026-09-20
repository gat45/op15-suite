from ..core.layer import MemoryLayer
from ..core.database import Database
from ..core.models import Memory
import json
from typing import List, Dict, Any
from enum import Enum


class RecoveryStatus(str, Enum):
    FAILED = "failed"
    DIAGNOSED = "diagnosed"
    RETRYING = "retrying"
    RECOVERED = "recovered"
    ABANDONED = "abandoned"


class RecoveryLayer(MemoryLayer):
    """FAIL -> DIAGNOSE -> CHANGE HYPOTHESIS -> RETRY"""

    def __init__(self, db: Database):
        super().__init__(db, "recovery")

    def record_failure(
        self,
        action_id: str,
        error: str,
        hypothesis: str = None,
        metadata: Dict[str, Any] = None,
    ) -> Memory:
        meta = metadata or {}
        meta.update({
            "action_id": action_id,
            "error": error,
            "hypothesis": hypothesis,
            "status": RecoveryStatus.FAILED.value,
            "attempt": 1,
            "hypothesis_history": [hypothesis] if hypothesis else [],
        })
        return self.add_memory(
            f"Failure in {action_id}: {error}",
            metadata=meta,
        )

    def diagnose(self, recovery_id: str, diagnosis: str, new_hypothesis: str = None) -> Dict[str, Any]:
        mem = self.db.get_memory(recovery_id)
        if not mem:
            return {"error": "not found"}
        meta = json.loads(mem.get("metadata", "{}"))
        history = meta.get("hypothesis_history", [])
        meta["status"] = RecoveryStatus.DIAGNOSED.value
        meta["diagnosis"] = diagnosis
        out = {"diagnosed": True}
        if new_hypothesis:
            # REFLEX 6: never retry the same hypothesis twice
            if new_hypothesis in history:
                out = {"diagnosed": True, "duplicate_hypothesis": True,
                       "reason": "hypothese deja testee — changer de piste"}
            else:
                meta["hypothesis"] = new_hypothesis
                history.append(new_hypothesis)
                meta["hypothesis_history"] = history
        self.db.update_memory(recovery_id, metadata=json.dumps(meta))
        return out

    def retry(self, recovery_id: str) -> Dict[str, Any]:
        mem = self.db.get_memory(recovery_id)
        if not mem:
            return {"error": "not found"}
        meta = json.loads(mem.get("metadata", "{}"))
        attempt = meta.get("attempt", 1)
        if attempt >= 5:
            meta["status"] = RecoveryStatus.ABANDONED.value
            self.db.update_memory(recovery_id, metadata=json.dumps(meta))
            return {"abandoned": True, "reason": "max attempts reached", "attempt": attempt}
        # REFLEX 6: a retry is only allowed after a fresh diagnosis
        if meta.get("status") != RecoveryStatus.DIAGNOSED.value and attempt > 1:
            return {"blocked": True, "reason": "diagnosis requise avant un nouveau retry"}
        meta["status"] = RecoveryStatus.RETRYING.value
        meta["attempt"] = attempt + 1
        self.db.update_memory(recovery_id, metadata=json.dumps(meta))
        return {"retrying": True, "attempt": attempt + 1, "hypothesis": meta.get("hypothesis")}

    def mark_recovered(self, recovery_id: str) -> bool:
        mem = self.db.get_memory(recovery_id)
        if not mem:
            return False
        meta = json.loads(mem.get("metadata", "{}"))
        meta["status"] = RecoveryStatus.RECOVERED.value
        self.db.update_memory(recovery_id, metadata=json.dumps(meta))
        return True

    def active_recoveries(self) -> List[Dict]:
        conn = self.db._connect()
        rows = conn.execute(
            "SELECT * FROM memories WHERE type = 'recovery' "
            "AND (metadata LIKE ? OR metadata LIKE ?) "
            "ORDER BY created_at DESC",
            (f'%"status": "{RecoveryStatus.FAILED.value}"%',
             f'%"status": "{RecoveryStatus.RETRYING.value}"%'),
        ).fetchall()
        return [dict(row) for row in rows]

    def recovery_history(self, limit: int = 20) -> List[Dict]:
        conn = self.db._connect()
        rows = conn.execute(
            "SELECT * FROM memories WHERE type = 'recovery' "
            "AND metadata LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f'%"status": "{RecoveryStatus.RECOVERED.value}"%', limit),
        ).fetchall()
        return [dict(row) for row in rows]
