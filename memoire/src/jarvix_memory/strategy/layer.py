from ..core.layer import MemoryLayer
from ..core.database import Database
from ..core.models import Memory
import json
from typing import List, Dict, Any


class StrategyMemory(MemoryLayer):
    """Strategy = 'in this situation, prefer A because B is expensive'"""

    def __init__(self, db: Database):
        super().__init__(db, "strategy")

    def add_strategy(
        self,
        name: str,
        situation: str,
        steps: List[str],
        rationale: str = None,
        metadata: Dict[str, Any] = None,
    ) -> Memory:
        meta = metadata or {}
        meta.update({
            "name": name,
            "situation": situation,
            "steps": steps,
            "rationale": rationale,
            "attempts": 0,
            "successes": 0,
            "total_cost_minutes": 0.0,
        })
        return self.add_memory(
            f"Strategy: {name}\nSituation: {situation}\nSteps: {' -> '.join(steps)}",
            metadata=meta,
        )

    def record_attempt(self, strategy_id: str, success: bool, cost_minutes: float = 0.0) -> bool:
        mem = self.db.get_memory(strategy_id)
        if not mem:
            return False
        meta = json.loads(mem.get("metadata", "{}"))
        meta["attempts"] = meta.get("attempts", 0) + 1
        if success:
            meta["successes"] = meta.get("successes", 0) + 1
        meta["total_cost_minutes"] = meta.get("total_cost_minutes", 0.0) + cost_minutes
        meta["last_attempt"] = {"success": success, "cost_minutes": cost_minutes}
        self.db.update_memory(strategy_id, metadata=json.dumps(meta))
        return True

    def success_rate(self, strategy_id: str) -> Dict[str, Any]:
        mem = self.db.get_memory(strategy_id)
        if not mem:
            return {"error": "not found"}
        meta = json.loads(mem.get("metadata", "{}"))
        attempts = meta.get("attempts", 0)
        successes = meta.get("successes", 0)
        return {
            "name": meta.get("name"),
            "attempts": attempts,
            "successes": successes,
            "rate": successes / attempts if attempts > 0 else 0.0,
            "avg_cost_minutes": (
                meta.get("total_cost_minutes", 0.0) / attempts if attempts > 0 else 0.0
            ),
        }

    def best_for_situation(self, situation: str, limit: int = 3) -> List[Dict]:
        all_strategies = self.db.search_by_type("strategy", limit=50)
        scored = []
        for s in all_strategies:
            meta = json.loads(s.get("metadata", "{}"))
            attempts = meta.get("attempts", 0)
            successes = meta.get("successes", 0)
            rate = successes / attempts if attempts > 0 else 0.5
            sit = meta.get("situation", "")
            relevance = 1.0 if situation.lower() in sit.lower() else 0.3
            score = rate * relevance
            scored.append({"strategy": s, "score": score, "rate": rate})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def leaderboard(self, limit: int = 10) -> List[Dict]:
        all_s = self.db.search_by_type("strategy", limit=100)
        stats = []
        for s in all_s:
            meta = json.loads(s.get("metadata", "{}"))
            attempts = meta.get("attempts", 0)
            if attempts == 0:
                continue
            stats.append({
                "id": s["id"],
                "name": meta.get("name"),
                "attempts": attempts,
                "successes": meta.get("successes", 0),
                "rate": meta.get("successes", 0) / attempts,
                "avg_cost": meta.get("total_cost_minutes", 0.0) / attempts,
            })
        stats.sort(key=lambda x: x["rate"], reverse=True)
        return stats[:limit]

    def recommend(self, situation: str, min_samples: int = 1,
                  cost_weight: float = 0.2, limit: int = 3) -> List[Dict]:
        """P1.5 — value/cost strategy selection:
        value = rate x situation_relevance / (1 + cost_weight x avg_cost_minutes).
        Strategies below min_samples are listed as 'unproven', not recommended."""
        scored = []
        for s in self.db.search_by_type("strategy", limit=100):
            meta = json.loads(s.get("metadata", "{}"))
            attempts, successes = meta.get("attempts", 0), meta.get("successes", 0)
            rate = successes / attempts if attempts > 0 else None
            avg_cost = meta.get("total_cost_minutes", 0.0) / attempts if attempts > 0 else 0.0
            relevance = 1.0 if situation.lower() in (meta.get("situation", "") or "").lower() else 0.3
            if rate is None or attempts < min_samples:
                scored.append({"id": s["id"], "name": meta.get("name"),
                               "proven": False, "relevance": relevance,
                               "attempts": attempts})
                continue
            value = (rate * relevance) / (1.0 + cost_weight * avg_cost)
            scored.append({
                "id": s["id"], "name": meta.get("name"), "proven": True,
                "rate": round(rate, 3), "avg_cost_min": round(avg_cost, 2),
                "value": round(value, 4), "attempts": attempts,
                "steps": meta.get("steps", []),
            })
        proven = [x for x in scored if x.get("proven")]
        proven.sort(key=lambda x: x["value"], reverse=True)
        unproven = [x for x in scored if not x.get("proven")]
        return {"recommended": proven[:limit], "unproven": unproven[:3]}
