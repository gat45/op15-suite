from ..core.database import Database
from ..core.models import Memory, MemoryType
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class VerificationEngine:
    """CLAIM -> VERIFICATION -> EVIDENCE -> VERIFIED/REJECTED"""

    def __init__(self, db: Database):
        self.db = db

    def claim(self, content: str, source: str = None, metadata: Dict[str, Any] = None) -> Memory:
        memory = Memory(
            type=MemoryType.EVIDENCE,
            content=content,
            status="provisional",
            source=source,
            metadata=metadata or {},
        )
        memory.metadata["verdict"] = "claim"
        memory.metadata["evidence"] = []
        self.db.insert_memory(memory)
        return memory

    def add_evidence(
        self,
        claim_id: str,
        evidence_type: str,
        description: str,
        passed: bool,
        details: Dict[str, Any] = None,
    ) -> Optional[Dict]:
        mem = self.db.get_memory(claim_id)
        if not mem:
            return None

        evidence = {
            "id": str(uuid.uuid4()),
            "type": evidence_type,
            "description": description,
            "passed": passed,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        meta = json.loads(mem.get("metadata", "{}"))
        ev_list = meta.get("evidence", [])
        ev_list.append(evidence)
        meta["evidence"] = ev_list

        self.db.update_memory(claim_id, metadata=json.dumps(meta))
        return evidence

    def resolve(self, claim_id: str) -> Dict[str, Any]:
        mem = self.db.get_memory(claim_id)
        if not mem:
            return {"error": "claim not found"}

        meta = json.loads(mem.get("metadata", "{}"))
        evidence_list = meta.get("evidence", [])

        if not evidence_list:
            verdict = "inconclusive"
        else:
            passed = sum(1 for e in evidence_list if e.get("passed"))
            total = len(evidence_list)
            ratio = passed / total if total > 0 else 0
            if ratio >= 0.8:
                verdict = "verified"
            elif ratio <= 0.2:
                verdict = "rejected"
            else:
                verdict = "inconclusive"

        meta["verdict"] = verdict
        meta["resolved_at"] = datetime.utcnow().isoformat()
        meta["evidence_summary"] = {
            "total": len(evidence_list),
            "passed": sum(1 for e in evidence_list if e.get("passed")),
            "failed": sum(1 for e in evidence_list if not e.get("passed")),
        }

        status_map = {
            "verified": "verified",
            "rejected": "invalid",
            "inconclusive": "provisional",
        }
        self.db.update_memory(
            claim_id,
            metadata=json.dumps(meta),
            status=status_map.get(verdict, "provisional"),
        )

        return {
            "claim_id": claim_id,
            "verdict": verdict,
            "evidence_summary": meta["evidence_summary"],
        }

    def get_claims(self, verdict: str = None, limit: int = 20) -> List[Dict]:
        conn = self.db._connect()
        if verdict:
            rows = conn.execute(
                "SELECT * FROM memories WHERE type = ? AND metadata LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                ("evidence", f'%"verdict": "{verdict}"%', limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE type = ? ORDER BY created_at DESC LIMIT ?",
                ("evidence", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def verified_count(self) -> int:
        conn = self.db._connect()
        row = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE type = 'evidence' AND status = 'verified'"
        ).fetchone()
        return row[0] if row else 0
