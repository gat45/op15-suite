from ..core.layer import MemoryLayer
from ..core.database import Database
from ..core.models import Memory
import json
from typing import List, Dict, Any


class LearningLayer(MemoryLayer):
    """Experience -> Memory -> Evaluation -> Learning -> Updated policy"""

    def __init__(self, db: Database):
        super().__init__(db, "learning")

    def record_outcome(
        self,
        experience_id: str,
        evaluation: str,
        score: float,
        what_was_learned: str,
        policy_update: Dict[str, Any] = None,
    ) -> Memory:
        meta = {
            "experience_id": experience_id,
            "evaluation": evaluation,
            "score": score,
            "what_was_learned": what_was_learned,
            "policy_update": policy_update or {},
        }
        return self.add_memory(
            f"Learning from {experience_id}: {what_was_learned}",
            metadata=meta,
            confidence=min(score, 1.0),
        )

    def get_learnings(self, context: str, limit: int = 10) -> List[Dict]:
        results = self.db.search_fts(f"learning {context}", limit=limit)
        for r in results:
            meta = json.loads(r.get("metadata", "{}"))
            r["score"] = meta.get("score", 0.0)
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results

    def get_policies(self) -> Dict[str, Any]:
        all_l = self.db.search_by_type("learning", limit=200)
        policies = {}
        for l in all_l:
            meta = json.loads(l.get("metadata", "{}"))
            for key, value in meta.get("policy_update", {}).items():
                if key not in policies:
                    policies[key] = []
                policies[key].append({
                    "value": value,
                    "score": meta.get("score", 0.0),
                })
        return policies

    def should_abandon(self, strategy_id: str, threshold: float = 0.3) -> Dict[str, Any]:
        all_l = self.db.search_by_type("learning", limit=100)
        scores = []
        for l in all_l:
            meta = json.loads(l.get("metadata", "{}"))
            if meta.get("experience_id") == strategy_id:
                scores.append(meta.get("score", 0.0))
        if not scores:
            return {"abandon": False, "reason": "no data"}
        avg = sum(scores) / len(scores)
        return {
            "abandon": avg < threshold,
            "avg_score": avg,
            "samples": len(scores),
        }
